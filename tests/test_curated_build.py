"""
Integration tests for 06_build_curated.py (revisit detection + canonical build).
Uses an in-memory SQLite DB seeded with hand-crafted staging rows — no real API.
"""

import json
import sqlite3
import uuid
import importlib.util
import pytest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "build_curated", Path(__file__).parent.parent / "scripts" / "06_build_curated.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

build_curated = mod.build_curated


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db():
    """Return an in-memory SQLite connection with the full schema applied."""
    conn = sqlite3.connect(":memory:")
    schema_dir = Path(__file__).parent.parent / "sql" / "schemas"
    for fname in ["raw_zone.sql", "staging_zone.sql", "curated_zone.sql"]:
        conn.executescript((schema_dir / fname).read_text())
    return conn


def _episode(conn, ep_num, ep_date, title, tmdb_id, confidence=1.0):
    """Insert one staging_episode + one resolved staging_movie_mention."""
    ep_id  = str(uuid.uuid4())
    raw_id = str(uuid.uuid4())
    men_id = str(uuid.uuid4())

    # Minimal raw_ingest_run so FK is satisfied
    run_id = "test-run"
    conn.execute(
        "INSERT OR IGNORE INTO raw_ingest_runs (ingest_run_id, source_url, sync_status) "
        "VALUES (?, 'test', 'success')", (run_id,)
    )
    conn.execute(
        "INSERT OR IGNORE INTO raw_episodes (raw_episode_id, ingest_run_id, source_hash) "
        "VALUES (?, ?, ?)", (raw_id, run_id, raw_id)
    )
    conn.execute(
        "INSERT INTO staging_episodes "
        "(staging_episode_id, raw_episode_id, episode_number, episode_date, episode_title, validation_status) "
        "VALUES (?, ?, ?, ?, ?, 'pending')",
        (ep_id, raw_id, ep_num, ep_date, title)
    )
    cand = json.dumps([{"id": tmdb_id, "title": title, "year": None,
                        "popularity": 10, "vote_average": 7.0,
                        "confidence": confidence}])
    conn.execute(
        "INSERT INTO staging_movie_mentions "
        "(staging_mention_id, staging_episode_id, raw_episode_id, mention_order, "
        " title_raw, title_normalized, year_parsed, resolution_method, "
        " confidence_score, tmdb_id, candidate_json, requires_manual_review) "
        "VALUES (?, ?, ?, 1, ?, ?, NULL, 'exact_tmdb', ?, ?, ?, 0)",
        (men_id, ep_id, raw_id, title, title.lower(), confidence, tmdb_id, cand)
    )
    conn.commit()
    return ep_id, men_id


# ---------------------------------------------------------------------------
# Tests need build_curated to accept an open connection, but the real script
# takes a db_path string. We write to a temp file instead.
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    schema_dir = Path(__file__).parent.parent / "sql" / "schemas"
    for fname in ["raw_zone.sql", "staging_zone.sql", "curated_zone.sql"]:
        conn.executescript((schema_dir / fname).read_text())
    conn.commit()
    conn.close()
    return db_path


def _seed(db_path, rows):
    """rows = list of (ep_num, ep_date, title, tmdb_id, confidence)"""
    conn = sqlite3.connect(db_path)
    for args in rows:
        _episode(conn, *args)
    conn.close()


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

class TestCanonicalMovies:
    def test_one_movie_one_episode(self, tmp_db):
        _seed(tmp_db, [(1, "2015-01-01", "Heat", 949, 1.0)])
        movies, links, revisits = build_curated(tmp_db)
        assert movies == 1
        assert links == 1
        assert revisits == 0

    def test_dedup_same_tmdb_id(self, tmp_db):
        """Two episodes with the same tmdb_id → one canonical movie."""
        _seed(tmp_db, [
            (1, "2015-01-01", "Heat", 949, 1.0),
            (50, "2018-06-01", "Heat", 949, 1.0),
        ])
        movies, links, revisits = build_curated(tmp_db)
        assert movies == 1
        assert links == 2
        assert revisits == 1

    def test_two_different_movies(self, tmp_db):
        _seed(tmp_db, [
            (1, "2015-01-01", "Heat",           949,  1.0),
            (2, "2015-01-08", "Jerry Maguire",  9390, 1.0),
        ])
        movies, links, revisits = build_curated(tmp_db)
        assert movies == 2
        assert links == 2
        assert revisits == 0

    def test_no_duplicate_canonical_movies(self, tmp_db):
        _seed(tmp_db, [
            (1, "2015-01-01", "Heat", 949, 1.0),
            (2, "2016-01-01", "Heat", 949, 1.0),
            (3, "2017-01-01", "Heat", 949, 1.0),
        ])
        build_curated(tmp_db)
        conn = sqlite3.connect(tmp_db)
        dupes = conn.execute(
            "SELECT COUNT(*) FROM (SELECT tmdb_id FROM curated_movies "
            "GROUP BY tmdb_id HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        conn.close()
        assert dupes == 0


class TestRevisitSequencing:
    def test_first_appearance_is_not_revisit(self, tmp_db):
        _seed(tmp_db, [(1, "2015-01-01", "Heat", 949, 1.0)])
        build_curated(tmp_db)
        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT is_revisit, revisit_sequence FROM curated_episode_movies"
        ).fetchone()
        conn.close()
        assert row[0] == 0
        assert row[1] == 1

    def test_second_appearance_is_revisit(self, tmp_db):
        _seed(tmp_db, [
            (1,  "2015-01-01", "Heat", 949, 1.0),
            (50, "2018-06-01", "Heat", 949, 1.0),
        ])
        build_curated(tmp_db)
        conn = sqlite3.connect(tmp_db)
        rows = conn.execute(
            "SELECT revisit_sequence, is_revisit "
            "FROM curated_episode_movies ORDER BY revisit_sequence"
        ).fetchall()
        conn.close()
        assert rows[0] == (1, 0)
        assert rows[1] == (2, 1)

    def test_three_appearances_sequenced_correctly(self, tmp_db):
        _seed(tmp_db, [
            (1,   "2015-01-01", "Heat", 949, 1.0),
            (116, "2020-01-24", "Heat", 949, 1.0),
            (227, "2021-11-02", "Heat", 949, 1.0),
        ])
        build_curated(tmp_db)
        conn = sqlite3.connect(tmp_db)
        rows = conn.execute(
            "SELECT revisit_sequence, is_revisit "
            "FROM curated_episode_movies ORDER BY revisit_sequence"
        ).fetchall()
        conn.close()
        assert len(rows) == 3
        assert rows[0] == (1, 0)
        assert rows[1] == (2, 1)
        assert rows[2] == (3, 1)

    def test_sequencing_uses_date_order_not_insertion_order(self, tmp_db):
        """Insert later episode first; sequence must follow chronology."""
        _seed(tmp_db, [
            (50, "2018-06-01", "Heat", 949, 1.0),  # inserted first but later date
            (1,  "2015-01-01", "Heat", 949, 1.0),
        ])
        build_curated(tmp_db)
        conn = sqlite3.connect(tmp_db)
        rows = conn.execute(
            "SELECT episode_number, revisit_sequence "
            "FROM curated_episode_movies ORDER BY revisit_sequence"
        ).fetchall()
        conn.close()
        # Episode 1 (2015) should be seq=1, episode 50 (2018) should be seq=2
        assert rows[0][0] == 1
        assert rows[1][0] == 50

    def test_revisit_type_set_on_revisit(self, tmp_db):
        _seed(tmp_db, [
            (1,  "2015-01-01", "Heat", 949, 1.0),
            (50, "2018-06-01", "Heat", 949, 1.0),
        ])
        build_curated(tmp_db)
        conn = sqlite3.connect(tmp_db)
        rows = conn.execute(
            "SELECT revisit_type FROM curated_episode_movies ORDER BY revisit_sequence"
        ).fetchall()
        conn.close()
        assert rows[0][0] is None           # first episode: no revisit_type
        assert rows[1][0] == "regular_revisit"

    def test_curated_movies_revisit_count(self, tmp_db):
        _seed(tmp_db, [
            (1,   "2015-01-01", "Heat", 949, 1.0),
            (116, "2020-01-24", "Heat", 949, 1.0),
            (227, "2021-11-02", "Heat", 949, 1.0),
        ])
        build_curated(tmp_db)
        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT revisit_count, total_episodes_featured FROM curated_movies"
        ).fetchone()
        conn.close()
        assert row[0] == 2   # two revisits
        assert row[1] == 3   # three appearances total

    def test_first_and_last_episode_dates(self, tmp_db):
        _seed(tmp_db, [
            (1,   "2015-01-01", "Heat", 949, 1.0),
            (116, "2020-06-15", "Heat", 949, 1.0),
        ])
        build_curated(tmp_db)
        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT first_episode_date, last_episode_date FROM curated_movies"
        ).fetchone()
        conn.close()
        assert row[0] == "2015-01-01"
        assert row[1] == "2020-06-15"


class TestConfidenceBand:
    def test_high_confidence(self, tmp_db):
        _seed(tmp_db, [(1, "2015-01-01", "Heat", 949, 0.95)])
        build_curated(tmp_db)
        conn = sqlite3.connect(tmp_db)
        band = conn.execute("SELECT canonical_key_confidence FROM curated_movies").fetchone()[0]
        conn.close()
        assert band == "high"

    def test_medium_confidence(self, tmp_db):
        _seed(tmp_db, [(1, "2015-01-01", "Heat", 949, 0.70)])
        build_curated(tmp_db)
        conn = sqlite3.connect(tmp_db)
        band = conn.execute("SELECT canonical_key_confidence FROM curated_movies").fetchone()[0]
        conn.close()
        assert band == "medium"

    def test_low_confidence(self, tmp_db):
        _seed(tmp_db, [(1, "2015-01-01", "Heat", 949, 0.40)])
        build_curated(tmp_db)
        conn = sqlite3.connect(tmp_db)
        band = conn.execute("SELECT canonical_key_confidence FROM curated_movies").fetchone()[0]
        conn.close()
        assert band == "low"


class TestIdempotency:
    def test_double_build_same_result(self, tmp_db):
        _seed(tmp_db, [
            (1,  "2015-01-01", "Heat",          949,  1.0),
            (2,  "2015-01-08", "Jerry Maguire", 9390, 1.0),
            (50, "2018-06-01", "Heat",          949,  1.0),
        ])
        r1 = build_curated(tmp_db)
        r2 = build_curated(tmp_db)
        assert r1 == r2

    def test_audit_rows_not_duplicated(self, tmp_db):
        _seed(tmp_db, [(1, "2015-01-01", "Heat", 949, 1.0)])
        build_curated(tmp_db)
        build_curated(tmp_db)
        conn = sqlite3.connect(tmp_db)
        count = conn.execute("SELECT COUNT(*) FROM curated_audits").fetchone()[0]
        conn.close()
        assert count == 1  # one canonical movie → one audit row
