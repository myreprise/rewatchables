"""
Tests for vendor_cmu_subset.py — the CMU corpus subset extractor.

The case that matters most: CMU's Wikipedia page ids come from a Nov 2012 dump
and some articles have been recreated since, so a page-id-only match silently
drops films. Matching on freebase_id first is what keeps them.
"""

import csv
import importlib.util
import json
import sqlite3
import uuid
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "vendor_cmu_subset",
    Path(__file__).parent.parent / "scripts" / "vendor_cmu_subset.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

vendor = mod.vendor


# Three films, each exercising a different match path:
#   Die Hard  — freebase and page id both agree
#   Big       — freebase agrees, page id drifted (CMU 168597 vs current 38444154)
#   Ghost     — in the corpus but NOT one of ours; must be excluded
MOVIE_ROWS = [
    ["97646",  "/m/0p3_y",  "Die Hard", "1988-07-15", "140767956", "131.0",
     "{}", "{}", '{"/m/02kdv5l": "Action"}'],
    ["168597", "/m/016ky6", "Big",      "1988-06-03", "151668774", "104.0",
     "{}", "{}", '{"/m/06n90": "Comedy"}'],
    ["99999",  "/m/0zzzzz", "Ghost",    "1990-07-13", "505702588", "127.0",
     "{}", "{}", '{"/m/06n90": "Romance"}'],
]

CHAR_ROWS = [
    ["97646",  "/m/0p3_y",  "1988-07-15", "John McClane", "1955-03-19", "M",
     "1.83", "/m/0x67", "Bruce Willis", "33", "/m/a1", "/m/c1", "/m/a1"],
    ["168597", "/m/016ky6", "1988-06-03", "Josh Baskin",  "1956-07-09", "M",
     "1.78", "/m/0x67", "Tom Hanks",    "31", "/m/a2", "/m/c2", "/m/a2"],
    ["99999",  "/m/0zzzzz", "1990-07-13", "Sam Wheat",    "1955-10-11", "M",
     "1.80", "/m/0x67", "Patrick Swayze", "34", "/m/a3", "/m/c3", "/m/a3"],
]

SUMMARIES = {
    "97646":  "NYPD officer John McClane travels to Los Angeles for Christmas.",
    "168597": "A boy makes a wish to be big and wakes up an adult.",
    "99999":  "A murdered banker returns as a ghost.",
}


@pytest.fixture
def source(tmp_path):
    d = tmp_path / "MovieSummaries"
    d.mkdir()
    with open(d / "movie.metadata.tsv", "w", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter="\t", lineterminator="\n").writerows(MOVIE_ROWS)
    with open(d / "character.metadata.tsv", "w", encoding="utf-8", newline="") as f:
        csv.writer(f, delimiter="\t", lineterminator="\n").writerows(CHAR_ROWS)
    with open(d / "plot_summaries.txt", "w", encoding="utf-8", newline="") as f:
        for pid, text in SUMMARIES.items():
            f.write(f"{pid}\t{text}\n")
    return d


@pytest.fixture
def db(tmp_path):
    """Two curated films. 'Big' carries the CURRENT page id, which does not
    match the corpus — only its freebase_id does."""
    p = str(tmp_path / "test.db")
    conn = sqlite3.connect(p)
    schema_dir = Path(__file__).parent.parent / "sql" / "schemas"
    for fname in ["raw_zone.sql", "staging_zone.sql", "curated_zone.sql"]:
        conn.executescript((schema_dir / fname).read_text())
    for tmdb_id, title, year, fb, pid in [
        (562, "Die Hard", 1988, "/m/0p3_y", 97646),
        (2280, "Big", 1988, "/m/016ky6", 38444154),
    ]:
        conn.execute(
            "INSERT INTO curated_movies (movie_id, tmdb_id, title, year, "
            "freebase_id, wikipedia_page_id, total_episodes_featured, "
            "revisit_count, canonical_key_confidence) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, 0, 'high')",
            (str(uuid.uuid4()), tmdb_id, title, year, fb, pid))
    conn.commit()
    conn.close()
    return p


def _read(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


class TestVendor:
    def test_keeps_only_our_films(self, source, db, tmp_path):
        out = tmp_path / "out"
        movies, summaries, chars = vendor(source, out, db)
        assert (movies, summaries, chars) == (2, 2, 2)
        names = {r["name"] for r in _read(out / "movies.tsv")}
        assert names == {"Die Hard", "Big"}
        assert "Ghost" not in names, "corpus films we don't cover must be excluded"

    def test_page_id_drift_still_matches_via_freebase(self, source, db, tmp_path):
        """'Big' has a current page id of 38444154 but the corpus knows it as
        168597. Matching on freebase_id is what saves it."""
        out = tmp_path / "out"
        vendor(source, out, db)
        rows = {r["name"]: r for r in _read(out / "movies.tsv")}
        assert "Big" in rows
        assert rows["Big"]["wikipedia_page_id"] == "168597"   # corpus id, not ours

        with open(out / "plot_summaries.tsv", encoding="utf-8") as f:
            next(f)
            pids = {line.split("\t", 1)[0] for line in f}
        assert "168597" in pids

    def test_headers_are_added(self, source, db, tmp_path):
        out = tmp_path / "out"
        vendor(source, out, db)
        assert _read(out / "movies.tsv")[0].keys() >= {"freebase_id", "name"}
        chars = _read(out / "characters.tsv")
        assert chars[0]["actor_name"] in {"Bruce Willis", "Tom Hanks"}
        assert chars[0]["actor_age_at_release"] in {"33", "31"}

    def test_summary_text_is_verbatim(self, source, db, tmp_path):
        out = tmp_path / "out"
        vendor(source, out, db)
        with open(out / "plot_summaries.tsv", encoding="utf-8") as f:
            next(f)
            got = dict(line.rstrip("\n").split("\t", 1) for line in f)
        assert got["97646"] == SUMMARIES["97646"]

    def test_writes_provenance_and_manifest(self, source, db, tmp_path):
        out = tmp_path / "out"
        vendor(source, out, db)
        prov = (out / "PROVENANCE.md").read_text(encoding="utf-8")
        # CC BY-SA requires attribution travel with the data.
        assert "Attribution-ShareAlike" in prov
        assert "Bamman" in prov
        assert mod.SOURCE_URL in prov

        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert set(manifest["files"]) == {"movies.tsv", "plot_summaries.tsv",
                                          "characters.tsv"}
        for meta in manifest["files"].values():
            assert len(meta["sha256"]) == 64 and meta["bytes"] > 0

    def test_exits_when_bridge_is_empty(self, source, tmp_path):
        """Without 10_resolve_external_ids having run there is nothing to match
        on; fail loudly rather than writing three empty files."""
        p = str(tmp_path / "bare.db")
        conn = sqlite3.connect(p)
        schema_dir = Path(__file__).parent.parent / "sql" / "schemas"
        for fname in ["raw_zone.sql", "staging_zone.sql", "curated_zone.sql"]:
            conn.executescript((schema_dir / fname).read_text())
        conn.execute(
            "INSERT INTO curated_movies (movie_id, tmdb_id, title, year, "
            "total_episodes_featured, revisit_count, canonical_key_confidence) "
            "VALUES (?, 1, 'Nope', 1999, 1, 0, 'high')", (str(uuid.uuid4()),))
        conn.commit()
        conn.close()
        with pytest.raises(SystemExit):
            vendor(source, tmp_path / "out", p)

    def test_missing_source_file_exits(self, db, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(SystemExit):
            vendor(empty, tmp_path / "out", db)
