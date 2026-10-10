"""
Tests for local TMDB images: the URL the app draws (rewatchables/images.py)
and the step that downloads them (s14_cache_images).

No network. The download is driven through a stub session, and IMAGE_DIR is
pointed at tmp_path so nothing lands in the real static/ folder.
"""

import json
import sqlite3

import pytest

from rewatchables import images
from rewatchables.pipeline import s14_cache_images as s14

POSTER = "https://image.tmdb.org/t/p/w500/gKaePbkEkaqvMtw74EyhhkfCKKh.jpg"
NAME = "gKaePbkEkaqvMtw74EyhhkfCKKh.jpg"
LOCAL = "Heat (1995).jpg"
PORTRAITS = {images.file_name(p) for p in images.PORTRAITS.values()}
N = 1 + len(PORTRAITS)   # images per size in the `db` fixture


def _reset():
    images._on_disk.cache_clear()
    images._manifest.cache_clear()


@pytest.fixture
def image_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(images, "IMAGE_DIR", tmp_path / "tmdb")
    _reset()
    yield tmp_path / "tmdb"
    _reset()


class TestLocalName:
    def test_title_and_year(self):
        assert images.local_name("Heat", 1995, POSTER) == LOCAL

    @pytest.mark.parametrize("title, year, expected", [
        ("Mad Max: Fury Road", 2015, "Mad Max - Fury Road (2015).jpg"),
        ("Face/Off", 1997, "Face-Off (1997).jpg"),
        ("What About Bob?", 1991, "What About Bob (1991).jpg"),
        ("Ocean's Eleven", 2001, "Ocean's Eleven (2001).jpg"),
        ("Tom Cruise", None, "Tom Cruise.jpg"),
    ])
    def test_windows_safe(self, title, year, expected):
        assert images.local_name(title, year, POSTER) == expected


class TestSrc:
    def test_file_name_from_a_url_or_a_path(self):
        assert images.file_name(POSTER) == NAME
        assert images.file_name(f"/{NAME}") == NAME

    @pytest.mark.parametrize("empty", [None, "", float("nan")])
    def test_no_poster_stays_no_poster(self, empty, image_dir):
        assert images.src(empty, "w185") is None

    def test_falls_back_to_tmdb_at_the_asked_size(self, image_dir):
        assert images.src(POSTER, "w185") == \
            f"https://image.tmdb.org/t/p/w185/{NAME}"

    def test_prefers_the_local_copy_by_its_manifest_name(self, image_dir):
        (image_dir / "w342").mkdir(parents=True)
        (image_dir / "w342" / LOCAL).write_bytes(b"jpg")
        s14.write_manifest({NAME: LOCAL})
        assert images.src(POSTER, "w342") == "app/static/tmdb/w342/Heat%20%281995%29.jpg"
        # Only the size that is on disk is local.
        assert images.src(POSTER, "w185").startswith("https://image.tmdb.org/")

    def test_a_file_without_a_manifest_entry_is_not_used(self, image_dir):
        (image_dir / "w342").mkdir(parents=True)
        (image_dir / "w342" / LOCAL).write_bytes(b"jpg")
        assert images.src(POSTER, "w342").startswith("https://image.tmdb.org/")


class _Response:
    def __init__(self, status, content=b""):
        self.status_code = status
        self.content = content


class _Session:
    """Answers 200 with the URL as the body, except for names in `missing`."""

    def __init__(self, missing=()):
        self.missing = set(missing)
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        if url.rsplit("/", 1)[-1] in self.missing:
            return _Response(404)
        return _Response(200, url.encode())


def _db(tmp_path, movies, upcoming=None):
    path = tmp_path / "t.db"
    conn = sqlite3.connect(path)
    cols = "(title TEXT, year INTEGER, tmdb_id INTEGER, poster_url_tmdb TEXT)"
    conn.execute(f"CREATE TABLE curated_movies {cols}")
    conn.executemany("INSERT INTO curated_movies VALUES (?,?,?,?)", movies)
    if upcoming is not None:
        conn.execute(f"CREATE TABLE curated_upcoming_films {cols}")
        conn.executemany("INSERT INTO curated_upcoming_films VALUES (?,?,?,?)",
                         upcoming)
    conn.commit()
    return conn, str(path)


@pytest.fixture
def db(tmp_path):
    conn, path = _db(tmp_path, [("Heat", 1995, 949, POSTER),
                                ("No Poster", 2000, 1, None)])
    conn.close()
    return path


class TestWanted:
    def test_posters_and_portraits_once_each(self, tmp_path):
        # No curated_upcoming_films: skipped, not fatal.
        conn, _ = _db(tmp_path, [("Heat", 1995, 949, POSTER),
                                 ("Heat", 1995, 949, POSTER)])
        names = s14.wanted(conn)
        assert set(names) == {NAME} | PORTRAITS
        assert names[NAME] == LOCAL
        assert {"Tom Cruise.jpg", "Tom Hanks.jpg"} <= set(names.values())

    def test_a_graduated_film_is_named_from_curated_movies(self, tmp_path):
        conn, _ = _db(tmp_path, [("Heat", 1995, 949, POSTER)],
                      upcoming=[("heat", 1995, 949, POSTER)])
        assert s14.wanted(conn)[NAME] == LOCAL

    def test_a_title_collision_takes_the_tmdb_id(self, tmp_path):
        other = "https://image.tmdb.org/t/p/w500/other.jpg"
        conn, _ = _db(tmp_path, [("Heat", 1995, 949, POSTER)],
                      upcoming=[("Heat", 1995, 12345, other)])
        names = s14.wanted(conn)
        assert names[NAME] == LOCAL
        assert names["other.jpg"] == "Heat (1995) [12345].jpg"


class TestCacheImages:
    def test_downloads_every_size_under_the_title(self, db, image_dir):
        assert s14.cache_images(db, session=_Session()) == \
            (N * len(images.SIZES), 0, 0, 0)
        for size in images.SIZES:
            body = (image_dir / size / LOCAL).read_bytes()
            assert body == f"https://image.tmdb.org/t/p/{size}/{NAME}".encode()
        assert images.read_manifest()[NAME] == LOCAL

    def test_a_second_run_fetches_nothing(self, db, image_dir):
        s14.cache_images(db, session=_Session())
        session = _Session()
        assert s14.cache_images(db, session=session) == \
            (0, 0, N * len(images.SIZES), 0)
        assert session.urls == []

    def test_files_saved_under_the_tmdb_name_are_renamed(self, db, image_dir):
        """What the first version of step 14 left on disk."""
        for size in images.SIZES:
            (image_dir / size).mkdir(parents=True)
            (image_dir / size / NAME).write_bytes(b"old")
        session = _Session()
        downloaded, renamed, _, _ = s14.cache_images(db, session=session)
        assert renamed == len(images.SIZES)
        assert downloaded == len(PORTRAITS) * len(images.SIZES)
        assert NAME not in {u.rsplit("/", 1)[-1] for u in session.urls}
        for size in images.SIZES:
            assert (image_dir / size / LOCAL).read_bytes() == b"old"
            assert not (image_dir / size / NAME).exists()

    def test_a_retitled_film_is_renamed_not_refetched(self, tmp_path, image_dir):
        conn, path = _db(tmp_path, [("Heat", 1995, 949, POSTER)])
        conn.close()
        s14.cache_images(path, session=_Session())
        conn = sqlite3.connect(path)
        conn.execute("UPDATE curated_movies SET title = 'Heat: Director''s Cut'")
        conn.commit()
        conn.close()
        session = _Session()
        _, renamed, _, _ = s14.cache_images(path, session=session)
        assert renamed == len(images.SIZES)
        assert session.urls == []
        for size in images.SIZES:
            assert (image_dir / size / "Heat - Director's Cut (1995).jpg").exists()
            assert not (image_dir / size / LOCAL).exists()

    def test_a_failure_is_counted_and_leaves_no_file(self, db, image_dir):
        downloaded, _, _, failed = s14.cache_images(
            db, session=_Session(missing={NAME}))
        assert failed == len(images.SIZES)
        assert downloaded == len(PORTRAITS) * len(images.SIZES)
        assert not any(image_dir.rglob(LOCAL))
        assert not any(image_dir.rglob("*.part"))

    def test_the_manifest_is_valid_json(self, db, image_dir):
        s14.cache_images(db, session=_Session())
        json.loads((image_dir / images.MANIFEST).read_text(encoding="utf-8"))
