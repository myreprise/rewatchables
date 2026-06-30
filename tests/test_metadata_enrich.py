"""
Unit + integration tests for 09_enrich_metadata.py.
All network calls are mocked — no real API calls.
"""

import importlib.util
import json
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

spec = importlib.util.spec_from_file_location(
    "enrich_metadata",
    Path(__file__).parent.parent / "scripts" / "09_enrich_metadata.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

enrich_metadata = mod.enrich_metadata
_parse          = mod._parse
fetch_details   = mod.fetch_details


# ---------------------------------------------------------------------------
# Sample TMDB detail payload (matches Heat/id=949 shape)
# ---------------------------------------------------------------------------

SAMPLE_DETAIL = {
    "id": 949,
    "title": "Heat",
    "overview": "Obsessive master thief Neil McCauley leads a top-notch crew.",
    "runtime": 170,
    "poster_path": "/e09dLw1Ljtccd2P4NsuUvVtS5du.jpg",
    "genres": [
        {"id": 80, "name": "Crime"},
        {"id": 18, "name": "Drama"},
        {"id": 28, "name": "Action"},
    ],
    "credits": {
        "cast": [
            {"name": "Al Pacino",    "order": 0},
            {"name": "Robert De Niro", "order": 1},
            {"name": "Val Kilmer",   "order": 2},
            {"name": "Jon Voight",   "order": 3},
            {"name": "Tom Sizemore", "order": 4},
        ]
    },
}


# ---------------------------------------------------------------------------
# _parse unit tests (pure function, no DB/network)
# ---------------------------------------------------------------------------

class TestParse:
    def test_genres_as_json_array(self):
        genres, *_ = _parse(SAMPLE_DETAIL)
        assert json.loads(genres) == ["Crime", "Drama", "Action"]

    def test_runtime(self):
        _, runtime, *_ = _parse(SAMPLE_DETAIL)
        assert runtime == 170

    def test_cast_names_top_cast(self):
        _, _, cast_names, *_ = _parse(SAMPLE_DETAIL)
        cast = json.loads(cast_names)
        assert cast[0] == "Al Pacino"
        assert cast[1] == "Robert De Niro"
        assert len(cast) == 5  # only 5 in sample

    def test_cast_capped_at_10(self):
        data = dict(SAMPLE_DETAIL)
        data["credits"] = {"cast": [
            {"name": f"Actor {i}", "order": i} for i in range(15)
        ]}
        _, _, cast_names, *_ = _parse(data)
        assert len(json.loads(cast_names)) == 10

    def test_cast_sorted_by_order(self):
        data = dict(SAMPLE_DETAIL)
        data["credits"] = {"cast": [
            {"name": "Third",  "order": 2},
            {"name": "First",  "order": 0},
            {"name": "Second", "order": 1},
        ]}
        _, _, cast_names, *_ = _parse(data)
        cast = json.loads(cast_names)
        assert cast == ["First", "Second", "Third"]

    def test_plot_summary(self):
        *_, plot_summary, _ = _parse(SAMPLE_DETAIL)
        assert "Neil McCauley" in plot_summary

    def test_poster_url_constructed(self):
        *_, poster_url = _parse(SAMPLE_DETAIL)
        assert poster_url.startswith("https://image.tmdb.org/t/p/w500/")
        assert "/e09dLw1" in poster_url

    def test_missing_poster_returns_none(self):
        data = {**SAMPLE_DETAIL, "poster_path": None}
        *_, poster_url = _parse(data)
        assert poster_url is None

    def test_empty_genres_returns_empty_list(self):
        data = {**SAMPLE_DETAIL, "genres": []}
        genres, *_ = _parse(data)
        assert json.loads(genres) == []

    def test_missing_credits_returns_none_cast(self):
        data = {**SAMPLE_DETAIL, "credits": {}}
        _, _, cast_names, *_ = _parse(data)
        assert cast_names is None

    def test_empty_overview_returns_none(self):
        data = {**SAMPLE_DETAIL, "overview": ""}
        *_, plot_summary, _ = _parse(data)
        assert plot_summary is None

    def test_whitespace_overview_returns_none(self):
        data = {**SAMPLE_DETAIL, "overview": "   "}
        *_, plot_summary, _ = _parse(data)
        assert plot_summary is None

    def test_none_runtime_stays_none(self):
        data = {**SAMPLE_DETAIL, "runtime": None}
        _, runtime, *_ = _parse(data)
        assert runtime is None


# ---------------------------------------------------------------------------
# DB integration fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    schema_dir = Path(__file__).parent.parent / "sql" / "schemas"
    for fname in ["raw_zone.sql", "staging_zone.sql", "curated_zone.sql"]:
        conn.executescript((schema_dir / fname).read_text())

    # Seed two curated movies: one needing enrichment, one already done
    for tmdb_id, title, already_done in [
        (949,  "Heat",         False),
        (9390, "Jerry Maguire", True),
    ]:
        movie_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO curated_movies "
            "(movie_id, tmdb_id, title, year, genres, runtime_minutes, cast_names, "
            " plot_summary, poster_url_tmdb, total_episodes_featured, revisit_count, "
            " canonical_key_confidence) "
            "VALUES (?, ?, ?, 1995, ?, ?, ?, ?, ?, 1, 0, 'high')",
            (
                movie_id, tmdb_id, title,
                '["Drama"]' if already_done else None,
                120        if already_done else None,
                '["Tom Cruise"]' if already_done else None,
                "A great film." if already_done else None,
                "https://example.com/poster.jpg" if already_done else None,
            )
        )
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# enrich_metadata integration tests
# ---------------------------------------------------------------------------

def _mock_response(data):
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = data
    return mock


class TestEnrichMetadata:
    def test_fills_null_columns(self, tmp_db):
        with patch("requests.get", return_value=_mock_response(SAMPLE_DETAIL)):
            enriched, errors = enrich_metadata(tmp_db)

        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT genres, runtime_minutes, cast_names, plot_summary, poster_url_tmdb "
            "FROM curated_movies WHERE tmdb_id = 949"
        ).fetchone()
        conn.close()

        assert json.loads(row[0]) == ["Crime", "Drama", "Action"]
        assert row[1] == 170
        assert "Al Pacino" in json.loads(row[2])
        assert row[3] is not None
        assert row[4].startswith("https://image.tmdb.org")

    def test_skips_already_enriched(self, tmp_db):
        with patch("requests.get", return_value=_mock_response(SAMPLE_DETAIL)) as mock_get:
            enrich_metadata(tmp_db)
        # Only one movie (Heat) needed enrichment; Jerry Maguire was already done
        assert mock_get.call_count == 1

    def test_idempotent_second_run(self, tmp_db):
        with patch("requests.get", return_value=_mock_response(SAMPLE_DETAIL)):
            e1, _ = enrich_metadata(tmp_db)
        with patch("requests.get", return_value=_mock_response(SAMPLE_DETAIL)) as mock_get:
            e2, _ = enrich_metadata(tmp_db)
        assert e1 == 1
        assert e2 == 0          # everything already filled
        assert mock_get.call_count == 0

    def test_returns_correct_counts(self, tmp_db):
        with patch("requests.get", return_value=_mock_response(SAMPLE_DETAIL)):
            enriched, errors = enrich_metadata(tmp_db)
        assert enriched == 1
        assert errors == 0

    def test_404_counted_as_error(self, tmp_db):
        mock = MagicMock()
        mock.status_code = 404
        with patch("requests.get", return_value=mock):
            enriched, errors = enrich_metadata(tmp_db)
        assert enriched == 0
        assert errors == 1

    def test_network_error_counted_as_error(self, tmp_db):
        with patch("requests.get", side_effect=Exception("network down")):
            enriched, errors = enrich_metadata(tmp_db)
        assert errors == 1

    def test_already_enriched_row_unchanged(self, tmp_db):
        conn = sqlite3.connect(tmp_db)
        before = conn.execute(
            "SELECT genres, runtime_minutes FROM curated_movies WHERE tmdb_id=9390"
        ).fetchone()
        conn.close()

        with patch("requests.get", return_value=_mock_response(SAMPLE_DETAIL)):
            enrich_metadata(tmp_db)

        conn = sqlite3.connect(tmp_db)
        after = conn.execute(
            "SELECT genres, runtime_minutes FROM curated_movies WHERE tmdb_id=9390"
        ).fetchone()
        conn.close()
        assert before == after


# ---------------------------------------------------------------------------
# Persistent cache: avoid re-fetching metadata the db already has
# ---------------------------------------------------------------------------

def _null_out_curated_metadata(db_path, tmdb_id=None):
    """Simulate 06_build_curated wiping + rebuilding curated_movies, which
    clears the five enriched columns while the cache survives. Optionally
    restrict to a single tmdb_id."""
    conn = sqlite3.connect(db_path)
    sql = ("UPDATE curated_movies SET genres=NULL, runtime_minutes=NULL, "
           "cast_names=NULL, plot_summary=NULL, poster_url_tmdb=NULL")
    params = ()
    if tmdb_id is not None:
        sql += " WHERE tmdb_id = ?"
        params = (tmdb_id,)
    conn.execute(sql, params)
    conn.commit()
    conn.close()


class TestMetadataCache:
    def test_fetch_writes_through_to_cache(self, tmp_db):
        with patch("requests.get", return_value=_mock_response(SAMPLE_DETAIL)):
            enrich_metadata(tmp_db)

        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT genres, runtime_minutes, cast_names, plot_summary, poster_url_tmdb "
            "FROM tmdb_metadata_cache WHERE tmdb_id = 949"
        ).fetchone()
        conn.close()
        assert row is not None
        assert json.loads(row[0]) == ["Crime", "Drama", "Action"]
        assert row[1] == 170

    def test_rebuild_refills_from_cache_without_api(self, tmp_db):
        # First run: cache miss → one real API call, metadata + cache populated.
        with patch("requests.get", return_value=_mock_response(SAMPLE_DETAIL)) as g1:
            enrich_metadata(tmp_db)
        assert g1.call_count == 1

        # Simulate a curated rebuild that clears Heat's enriched columns.
        # (Heat is the movie that went through the cache on the first run.)
        _null_out_curated_metadata(tmp_db, tmdb_id=949)

        # Second run: curated_movies is missing Heat's metadata again, but the
        # cache has it → zero API calls, columns refilled from local storage.
        with patch("requests.get", return_value=_mock_response(SAMPLE_DETAIL)) as g2:
            enriched, errors = enrich_metadata(tmp_db)
        assert g2.call_count == 0
        assert errors == 0
        assert enriched == 1  # Heat refilled from cache

        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT genres, runtime_minutes FROM curated_movies WHERE tmdb_id = 949"
        ).fetchone()
        conn.close()
        assert json.loads(row[0]) == ["Crime", "Drama", "Action"]
        assert row[1] == 170

    def test_404_miss_not_cached(self, tmp_db):
        # A 404 yields no payload; nothing should be cached, so a later run
        # is free to retry.
        mock = MagicMock()
        mock.status_code = 404
        with patch("requests.get", return_value=mock):
            enrich_metadata(tmp_db)

        conn = sqlite3.connect(tmp_db)
        cached = conn.execute(
            "SELECT COUNT(*) FROM tmdb_metadata_cache WHERE tmdb_id = 949"
        ).fetchone()[0]
        conn.close()
        assert cached == 0
