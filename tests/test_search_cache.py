"""
Tests for the TMDB search cache in 04_enrich.py.

The cache exists because 03_normalize clears staging, which resets every mention
to 'unresolved' and sends the whole catalogue back through the resolver. Before
it, that cost ~481 TMDB searches every rebuild.

Two invariants carry the design and are the bulk of what is tested here:

  * a genuine zero-result search IS cached (otherwise unmatchable titles are
    re-queried forever), while a FAILED search is NOT (otherwise an outage gets
    frozen in as "no such film")
  * the cache holds RAW candidates, so scoring and the auto-resolve threshold
    stay re-derivable offline

All network calls are mocked — no real API calls.
"""

import importlib.util
import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

spec = importlib.util.spec_from_file_location(
    "enrich", Path(__file__).parent.parent / "scripts" / "04_enrich.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

cache_key               = mod.cache_key
cache_get               = mod.cache_get
cache_put               = mod.cache_put
ensure_cache_table      = mod.ensure_cache_table
search_tmdb_cached      = mod.search_tmdb_cached
enrich_staging_mentions = mod.enrich_staging_mentions
warm_cache_from_staging = mod.warm_cache_from_staging

SCHEMA_DIR = Path(__file__).parent.parent / "sql" / "schemas"

# Raw TMDB search shape, as search_tmdb returns it (pre-scoring).
HEAT = [
    {"id": 949, "title": "Heat", "year": "1995",
     "popularity": 22.5, "vote_average": 7.9},
    {"id": 30707, "title": "Heat", "year": "1972",
     "popularity": 1.2, "vote_average": 5.0},
]


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    for name in ("raw_zone.sql", "staging_zone.sql", "curated_zone.sql"):
        c.executescript((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    return c


# ---------------------------------------------------------------------------
# cache_key
# ---------------------------------------------------------------------------

class TestCacheKey:
    def test_normalizes_the_title(self):
        # Same film, three source spellings, one cache entry.
        assert (cache_key("The Insider", 1999)
                == cache_key("insider", 1999)
                == cache_key("The  Insider!", 1999))

    def test_strips_podcast_annotations(self):
        assert cache_key("Batman (1989)", 1989) == cache_key("Batman", 1989)

    def test_year_is_part_of_the_key(self):
        assert cache_key("Heat", 1995) != cache_key("Heat", 1972)

    def test_missing_year_collapses_to_empty_string(self):
        # Not NULL: SQLite treats NULLs as distinct in a unique index, so a
        # nullable year column would let unyeared searches insert a duplicate
        # row on every run instead of hitting the cache.
        assert cache_key("Heat", None) == "heat|"
        assert cache_key("Heat", None) == cache_key("Heat", 0)


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_miss_returns_none(self, conn):
        assert cache_get(conn.cursor(), "Heat", 1995) is None

    def test_put_then_get(self, conn):
        cur = conn.cursor()
        cache_put(cur, "Heat", 1995, HEAT)
        assert cache_get(cur, "Heat", 1995) == HEAT

    def test_empty_result_is_cached_and_distinct_from_a_miss(self, conn):
        cur = conn.cursor()
        cache_put(cur, "Nonexistent Film", 1999, [])
        # [] not None: TMDB was asked and knows nothing. Without this, the one
        # class of title that never resolves is re-queried on every single run.
        assert cache_get(cur, "Nonexistent Film", 1999) == []

    def test_result_count_recorded(self, conn):
        cur = conn.cursor()
        cache_put(cur, "Heat", 1995, HEAT)
        cache_put(cur, "Nothing", None, [])
        counts = dict(cur.execute(
            "SELECT query_title, result_count FROM tmdb_search_cache"))
        assert counts == {"Heat": 2, "Nothing": 0}

    def test_reput_replaces_rather_than_duplicating(self, conn):
        cur = conn.cursor()
        cache_put(cur, "Heat", 1995, HEAT)
        cache_put(cur, "Heat", 1995, HEAT[:1])
        assert cur.execute(
            "SELECT COUNT(*) FROM tmdb_search_cache").fetchone()[0] == 1
        assert cache_get(cur, "Heat", 1995) == HEAT[:1]

    def test_corrupt_entry_reads_as_a_miss(self, conn):
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tmdb_search_cache (cache_key, query_title, "
            "candidates_json, result_count) VALUES (?, ?, ?, ?)",
            (cache_key("Heat", 1995), "Heat", "{not json", 0))
        assert cache_get(cur, "Heat", 1995) is None

    def test_ensure_cache_table_is_idempotent(self, conn):
        cur = conn.cursor()
        ensure_cache_table(cur)
        cache_put(cur, "Heat", 1995, HEAT)
        ensure_cache_table(cur)
        assert cache_get(cur, "Heat", 1995) == HEAT


# ---------------------------------------------------------------------------
# search_tmdb_cached — the network-avoidance contract
# ---------------------------------------------------------------------------

class TestSearchThroughCache:
    def test_miss_calls_the_api_and_stores_the_result(self, conn):
        cur = conn.cursor()
        with patch.object(mod, "search_tmdb", return_value=HEAT) as api:
            cands, networked = search_tmdb_cached(cur, ":memory:", "Heat", 1995)
        assert cands == HEAT and networked is True
        assert api.call_count == 1
        assert cache_get(cur, "Heat", 1995) == HEAT

    def test_hit_does_not_call_the_api(self, conn):
        cur = conn.cursor()
        cache_put(cur, "Heat", 1995, HEAT)
        with patch.object(mod, "search_tmdb") as api:
            cands, networked = search_tmdb_cached(cur, ":memory:", "Heat", 1995)
        assert cands == HEAT and networked is False
        api.assert_not_called()

    def test_cached_empty_result_does_not_call_the_api(self, conn):
        cur = conn.cursor()
        cache_put(cur, "Nonexistent", 1999, [])
        with patch.object(mod, "search_tmdb") as api:
            cands, networked = search_tmdb_cached(cur, ":memory:", "Nonexistent", 1999)
        assert cands == [] and networked is False
        api.assert_not_called()

    def test_refresh_bypasses_a_hit(self, conn):
        cur = conn.cursor()
        cache_put(cur, "Heat", 1995, HEAT[:1])
        with patch.object(mod, "search_tmdb", return_value=HEAT) as api:
            cands, networked = search_tmdb_cached(
                cur, ":memory:", "Heat", 1995, refresh=True)
        assert api.call_count == 1
        assert cands == HEAT and networked is True
        assert cache_get(cur, "Heat", 1995) == HEAT   # and overwrites

    def test_failed_search_is_not_cached(self, conn):
        # search_tmdb returns None on HTTP error / missing key / exhausted
        # retries. Storing [] for that would freeze a transient outage in as
        # "no such film" and every later run would trust it.
        cur = conn.cursor()
        with patch.object(mod, "search_tmdb", return_value=None):
            cands, networked = search_tmdb_cached(cur, ":memory:", "Heat", 1995)
        assert cands is None and networked is True
        assert cur.execute(
            "SELECT COUNT(*) FROM tmdb_search_cache").fetchone()[0] == 0

    def test_failure_then_success_caches_the_success(self, conn):
        cur = conn.cursor()
        with patch.object(mod, "search_tmdb", return_value=None):
            search_tmdb_cached(cur, ":memory:", "Heat", 1995)
        with patch.object(mod, "search_tmdb", return_value=HEAT):
            search_tmdb_cached(cur, ":memory:", "Heat", 1995)
        assert cache_get(cur, "Heat", 1995) == HEAT

    def test_yeared_and_unyeared_searches_are_separate_entries(self, conn):
        cur = conn.cursor()
        cache_put(cur, "Heat", 1995, HEAT[:1])
        with patch.object(mod, "search_tmdb", return_value=HEAT) as api:
            search_tmdb_cached(cur, ":memory:", "Heat", None)
        assert api.call_count == 1
        assert cache_get(cur, "Heat", 1995) == HEAT[:1]
        assert cache_get(cur, "Heat", None) == HEAT


# ---------------------------------------------------------------------------
# End-to-end through enrich_staging_mentions — the actual rebuild cost
# ---------------------------------------------------------------------------

def _seed_mention(conn, mention_id, title, year):
    cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO raw_ingest_runs "
        "(ingest_run_id, source_url, sync_status) VALUES ('r1', 'x', 'success')")
    cur.execute(
        "INSERT OR IGNORE INTO raw_episodes "
        "(raw_episode_id, ingest_run_id, source_hash) VALUES (?, 'r1', ?)",
        (f"raw-{mention_id}", f"h-{mention_id}"))
    cur.execute(
        "INSERT OR IGNORE INTO staging_episodes "
        "(staging_episode_id, raw_episode_id) VALUES (?, ?)",
        (f"se-{mention_id}", f"raw-{mention_id}"))
    # requires_manual_review = 1 mirrors what 03_normalize inserts: everything
    # arrives flagged, and only a confident match in 04 clears the flag.
    cur.execute(
        "INSERT INTO staging_movie_mentions "
        "(staging_mention_id, staging_episode_id, raw_episode_id, mention_order, "
        " title_raw, title_normalized, year_parsed, resolution_method, "
        " requires_manual_review) "
        "VALUES (?, ?, ?, 1, ?, ?, ?, 'unresolved', 1)",
        (mention_id, f"se-{mention_id}", f"raw-{mention_id}",
         title, title.lower(), year))
    conn.commit()


class TestRebuildCost:
    def test_second_pass_makes_no_api_calls(self, conn, tmp_path, monkeypatch):
        """The whole point: re-resolving a rebuilt staging zone is free."""
        db = tmp_path / "t.db"
        disk = sqlite3.connect(db)
        for name in ("raw_zone.sql", "staging_zone.sql", "curated_zone.sql"):
            disk.executescript((SCHEMA_DIR / name).read_text(encoding="utf-8"))
        _seed_mention(disk, "m1", "Heat", 1995)
        disk.close()

        monkeypatch.setattr(mod, "RATE_LIMIT_SLEEP", 0)

        with patch.object(mod, "search_tmdb", return_value=HEAT) as api:
            enrich_staging_mentions(str(db))
        assert api.call_count == 1

        # Simulate what 03_normalize does on every rebuild.
        disk = sqlite3.connect(db)
        disk.execute("UPDATE staging_movie_mentions SET resolution_method = "
                     "'unresolved', tmdb_id = NULL, candidate_json = NULL")
        disk.commit()
        disk.close()

        with patch.object(mod, "search_tmdb", return_value=HEAT) as api:
            enrich_staging_mentions(str(db))
        api.assert_not_called()

        # ...and it still resolved, from cache alone.
        disk = sqlite3.connect(db)
        method, tmdb_id = disk.execute(
            "SELECT resolution_method, tmdb_id FROM staging_movie_mentions"
        ).fetchone()
        disk.close()
        assert method == "exact_tmdb" and tmdb_id == 949

    def test_search_failure_leaves_the_mention_for_retry(self, conn, tmp_path,
                                                         monkeypatch):
        db = tmp_path / "t.db"
        disk = sqlite3.connect(db)
        for name in ("raw_zone.sql", "staging_zone.sql", "curated_zone.sql"):
            disk.executescript((SCHEMA_DIR / name).read_text(encoding="utf-8"))
        _seed_mention(disk, "m1", "Heat", 1995)
        disk.close()

        monkeypatch.setattr(mod, "RATE_LIMIT_SLEEP", 0)
        with patch.object(mod, "search_tmdb", return_value=None):
            enrich_staging_mentions(str(db))

        disk = sqlite3.connect(db)
        method, review = disk.execute(
            "SELECT resolution_method, requires_manual_review "
            "FROM staging_movie_mentions").fetchone()
        disk.close()
        # Still unresolved, NOT recorded as unmatchable: an outage is not a
        # data problem, and the next run must pick it up again.
        assert method == "unresolved"
        assert review == 1   # the seeded default, untouched


# ---------------------------------------------------------------------------
# warm_cache_from_staging — filling the cache from an already-resolved database
# ---------------------------------------------------------------------------

class TestWarmCache:
    def test_seeds_raw_candidates_stripped_of_scoring(self, tmp_path):
        db = tmp_path / "t.db"
        disk = sqlite3.connect(db)
        for name in ("raw_zone.sql", "staging_zone.sql", "curated_zone.sql"):
            disk.executescript((SCHEMA_DIR / name).read_text(encoding="utf-8"))
        _seed_mention(disk, "m1", "Heat", 1995)
        scored = [{**HEAT[0], "confidence": 0.98,
                   "title_similarity": 1.0, "year_score": 1.0}]
        disk.execute("UPDATE staging_movie_mentions SET candidate_json = ?",
                     (json.dumps(scored),))
        disk.commit()
        disk.close()

        seeded, _ = warm_cache_from_staging(str(db))
        assert seeded == 1

        disk = sqlite3.connect(db)
        cached = cache_get(disk.cursor(), "Heat", 1995)
        disk.close()
        # The derived scoring fields are gone, so retuning the thresholds
        # re-derives from the raw shape rather than replaying frozen scores.
        assert cached == HEAT[:1]

    def test_does_not_overwrite_a_real_search_result(self, tmp_path):
        db = tmp_path / "t.db"
        disk = sqlite3.connect(db)
        for name in ("raw_zone.sql", "staging_zone.sql", "curated_zone.sql"):
            disk.executescript((SCHEMA_DIR / name).read_text(encoding="utf-8"))
        _seed_mention(disk, "m1", "Heat", 1995)
        disk.execute("UPDATE staging_movie_mentions SET candidate_json = ?",
                     (json.dumps([HEAT[1]]),))
        cache_put(disk.cursor(), "Heat", 1995, HEAT)
        disk.commit()
        disk.close()

        seeded, skipped = warm_cache_from_staging(str(db))
        assert (seeded, skipped) == (0, 1)

        disk = sqlite3.connect(db)
        assert cache_get(disk.cursor(), "Heat", 1995) == HEAT
        disk.close()
