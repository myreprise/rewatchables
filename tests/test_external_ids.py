"""
Unit + integration tests for 10_resolve_external_ids.py.
All network calls are mocked — no real API calls.
"""

import sqlite3
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from rewatchables.pipeline import s10_resolve_external_ids as mod

resolve_external_ids = mod.resolve_external_ids
fetch_external_ids   = mod.fetch_external_ids
fetch_wikidata       = mod.fetch_wikidata
fetch_page_ids       = mod.fetch_page_ids
ensure_cache_table   = mod._ensure_column and mod.ensure_cache_table
_ensure_column       = mod._ensure_column


def _resp(payload, status=200):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = payload
    return m


# ---------------------------------------------------------------------------
# Hop 1: TMDB external_ids
# ---------------------------------------------------------------------------

class TestFetchExternalIds:
    def test_extracts_both_ids(self):
        with patch("requests.get", return_value=_resp(
                {"wikidata_id": "Q105598", "imdb_id": "tt0095016"})):
            assert fetch_external_ids(562) == {
                "wikidata_qid": "Q105598", "imdb_id": "tt0095016"}

    def test_missing_wikidata_is_none_not_empty_string(self):
        with patch("requests.get", return_value=_resp(
                {"wikidata_id": "", "imdb_id": "tt1"})):
            assert fetch_external_ids(1)["wikidata_qid"] is None

    def test_404_returns_none(self):
        with patch("requests.get", return_value=_resp({}, status=404)):
            assert fetch_external_ids(999999) is None

    def test_retries_then_gives_up(self):
        with patch("requests.get", side_effect=Exception("boom")), \
             patch("time.sleep"):
            assert fetch_external_ids(1) is None


# ---------------------------------------------------------------------------
# Hop 2: Wikidata
# ---------------------------------------------------------------------------

WD_PAYLOAD = {"entities": {
    "Q105598": {
        "claims": {"P646": [{"mainsnak": {"datavalue": {"value": "/m/0p3_y"}}}]},
        "sitelinks": {"enwiki": {"title": "Die Hard"}},
    },
    "Q104123": {
        "claims": {},                                   # no freebase id
        "sitelinks": {"enwiki": {"title": "Pulp Fiction"}},
    },
    "Q999": {"claims": {}, "sitelinks": {}},            # no article at all
}}


class TestFetchWikidata:
    def test_extracts_freebase_and_title(self):
        with patch("requests.get", return_value=_resp(WD_PAYLOAD)), \
             patch("time.sleep"):
            out = fetch_wikidata(["Q105598", "Q104123", "Q999"])
        assert out["Q105598"] == {"freebase_id": "/m/0p3_y",
                                  "enwiki_title": "Die Hard"}
        assert out["Q104123"]["freebase_id"] is None
        assert out["Q999"]["enwiki_title"] is None

    def test_batches_in_fifties(self):
        qids = [f"Q{i}" for i in range(120)]
        with patch("requests.get", return_value=_resp({"entities": {}})) as g, \
             patch("time.sleep"):
            fetch_wikidata(qids)
        assert g.call_count == 3          # 50 + 50 + 20

    def test_failed_batch_does_not_abort(self):
        with patch("requests.get", side_effect=Exception("down")), \
             patch("time.sleep"):
            assert fetch_wikidata(["Q1"]) == {}


# ---------------------------------------------------------------------------
# Hop 3: Wikipedia page ids
# ---------------------------------------------------------------------------

class TestFetchPageIds:
    def test_plain_title(self):
        payload = {"query": {"pages": {"97646": {"title": "Die Hard"}}}}
        with patch("requests.get", return_value=_resp(payload)), \
             patch("time.sleep"):
            assert fetch_page_ids({"Die Hard"}) == {"Die Hard": 97646}

    def test_follows_redirect_back_to_requested_title(self):
        payload = {"query": {
            "redirects": [{"from": "Crash (2004 film)", "to": "Crash (2004)"}],
            "pages": {"1749535": {"title": "Crash (2004)"}},
        }}
        with patch("requests.get", return_value=_resp(payload)), \
             patch("time.sleep"):
            out = fetch_page_ids({"Crash (2004 film)"})
        assert out == {"Crash (2004 film)": 1749535}

    def test_missing_page_is_omitted(self):
        # The API returns negative ids for titles with no article.
        payload = {"query": {"pages": {"-1": {"title": "Nonexistent"}}}}
        with patch("requests.get", return_value=_resp(payload)), \
             patch("time.sleep"):
            assert fetch_page_ids({"Nonexistent"}) == {}


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    schema_dir = Path(__file__).parent.parent / "sql" / "schemas"
    for fname in ["raw_zone.sql", "staging_zone.sql", "curated_zone.sql"]:
        conn.executescript((schema_dir / fname).read_text())
    conn.execute(
        "INSERT INTO curated_movies (movie_id, tmdb_id, title, year, "
        "total_episodes_featured, revisit_count, canonical_key_confidence) "
        "VALUES (?, 562, 'Die Hard', 1988, 1, 0, 'high')", (str(uuid.uuid4()),))
    conn.commit()
    conn.close()
    return db_path


def _patched_run(db_path):
    """Run the resolver with all three hops mocked."""
    with patch.object(mod, "fetch_external_ids",
                      return_value={"wikidata_qid": "Q105598",
                                    "imdb_id": "tt0095016"}) as h1, \
         patch.object(mod, "fetch_wikidata",
                      return_value={"Q105598": {"freebase_id": "/m/0p3_y",
                                                "enwiki_title": "Die Hard"}}) as h2, \
         patch.object(mod, "fetch_page_ids", return_value={"Die Hard": 97646}) as h3, \
         patch("time.sleep"):
        result = resolve_external_ids(db_path)
    return result, h1, h2, h3


class TestResolveExternalIds:
    def test_fills_all_four_columns(self, tmp_db):
        _patched_run(tmp_db)
        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT wikidata_qid, freebase_id, wikipedia_page_id, wikipedia_url "
            "FROM curated_movies WHERE tmdb_id = 562").fetchone()
        conn.close()
        assert row == ("Q105598", "/m/0p3_y", 97646,
                       "https://en.wikipedia.org/wiki/Die_Hard")

    def test_writes_through_to_cache(self, tmp_db):
        _patched_run(tmp_db)
        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT wikidata_qid, freebase_id, wikipedia_page_id, imdb_id, resolved "
            "FROM external_id_cache WHERE tmdb_id = 562").fetchone()
        conn.close()
        assert row == ("Q105598", "/m/0p3_y", 97646, "tt0095016", 1)

    def test_second_run_is_a_noop(self, tmp_db):
        _patched_run(tmp_db)
        (from_cache, resolved, errors), h1, _, _ = _patched_run(tmp_db)
        assert (from_cache, resolved, errors) == (0, 0, 0)
        assert h1.call_count == 0, "nothing should be pending on a second run"

    def test_rebuild_refills_from_cache_without_api(self, tmp_db):
        _patched_run(tmp_db)
        # Simulate 06_build_curated wiping the curated columns.
        conn = sqlite3.connect(tmp_db)
        conn.execute("UPDATE curated_movies SET wikidata_qid=NULL, freebase_id=NULL, "
                     "wikipedia_page_id=NULL, wikipedia_url=NULL")
        conn.commit()
        conn.close()

        (from_cache, resolved, errors), h1, _, _ = _patched_run(tmp_db)
        assert (from_cache, resolved) == (1, 0)
        assert h1.call_count == 0, "cache must satisfy the refill with no API call"

        conn = sqlite3.connect(tmp_db)
        row = conn.execute("SELECT freebase_id, wikipedia_page_id FROM "
                           "curated_movies WHERE tmdb_id = 562").fetchone()
        conn.close()
        assert row == ("/m/0p3_y", 97646)

    def test_film_without_freebase_id_is_not_retried(self, tmp_db):
        """Films postdating the 2016 Freebase freeze have no P646. They must
        cache as resolved, not be retried on every run."""
        with patch.object(mod, "fetch_external_ids",
                          return_value={"wikidata_qid": "Q1", "imdb_id": "tt1"}), \
             patch.object(mod, "fetch_wikidata",
                          return_value={"Q1": {"freebase_id": None,
                                               "enwiki_title": "Dunkirk (2017 film)"}}), \
             patch.object(mod, "fetch_page_ids",
                          return_value={"Dunkirk (2017 film)": 51923}), \
             patch("time.sleep"):
            resolve_external_ids(tmp_db)

        conn = sqlite3.connect(tmp_db)
        assert conn.execute("SELECT resolved FROM external_id_cache WHERE "
                            "tmdb_id = 562").fetchone()[0] == 1
        conn.close()

        # freebase_id stays NULL, so the pending query still selects it --
        # but the cache must answer it without hitting the API.
        (from_cache, resolved, _), h1, _, _ = _patched_run(tmp_db)
        assert h1.call_count == 0
        assert from_cache == 1

    def test_url_is_percent_encoded(self, tmp_db):
        with patch.object(mod, "fetch_external_ids",
                          return_value={"wikidata_qid": "Q1", "imdb_id": None}), \
             patch.object(mod, "fetch_wikidata",
                          return_value={"Q1": {"freebase_id": "/m/x",
                                               "enwiki_title": "Amélie"}}), \
             patch.object(mod, "fetch_page_ids", return_value={"Amélie": 1}), \
             patch("time.sleep"):
            resolve_external_ids(tmp_db)
        conn = sqlite3.connect(tmp_db)
        url = conn.execute("SELECT wikipedia_url FROM curated_movies "
                           "WHERE tmdb_id = 562").fetchone()[0]
        conn.close()
        assert url == "https://en.wikipedia.org/wiki/Am%C3%A9lie"


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

class TestMigration:
    def _legacy(self, tmp_path):
        conn = sqlite3.connect(str(tmp_path / "legacy.db"))
        conn.executescript("""
            CREATE TABLE curated_movies (
                movie_id TEXT PRIMARY KEY, tmdb_id INTEGER UNIQUE, title TEXT,
                wikidata_qid TEXT, wikipedia_url TEXT, updated_at TIMESTAMP
            );
        """)
        conn.commit()
        return conn

    def test_adds_bridge_columns(self, tmp_path):
        conn = self._legacy(tmp_path)
        def cols():
            return {r[1] for r in conn.execute("PRAGMA table_info(curated_movies)")}

        assert "freebase_id" not in cols()
        ensure_cache_table(conn.cursor())
        conn.commit()
        assert {"freebase_id", "wikipedia_page_id"} <= cols()
        conn.close()

    def test_migration_is_idempotent(self, tmp_path):
        conn = self._legacy(tmp_path)
        cur = conn.cursor()
        ensure_cache_table(cur)
        ensure_cache_table(cur)      # must not raise "duplicate column"
        conn.commit()
        conn.close()

    def test_ensure_column_noop_on_absent_table(self, tmp_path):
        conn = sqlite3.connect(str(tmp_path / "e.db"))
        _ensure_column(conn.cursor(), "nope", "freebase_id")
        conn.close()
