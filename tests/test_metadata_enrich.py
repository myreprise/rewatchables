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

enrich_metadata   = mod.enrich_metadata
_parse            = mod._parse
fetch_details     = mod.fetch_details
_ensure_column    = mod._ensure_column
ensure_cache_table = mod.ensure_cache_table


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
        # gender is TMDB's enum: 1 female, 2 male, 0 not set.
        "cast": [
            {"id": 1158, "name": "Al Pacino",      "order": 0, "gender": 2},
            {"id": 380,  "name": "Robert De Niro", "order": 1, "gender": 2},
            {"id": 5576, "name": "Val Kilmer",     "order": 2, "gender": 2},
            {"id": 2879, "name": "Jon Voight",     "order": 3, "gender": 2},
            {"id": 5586, "name": "Tom Sizemore",   "order": 4, "gender": 2},
        ]
    },
    "keywords": {
        "keywords": [
            {"id": 642,  "name": "robbery"},
            {"id": 703,  "name": "detective"},
            {"id": 9748, "name": "heist"},
        ]
    },
    "budget": 60000000,
    "revenue": 187436818,
}


PARSE_FIELDS = ("genres", "runtime", "cast_names", "cast_ids", "plot_summary",
                "poster_url", "keywords", "budget", "revenue", "people")


def parsed(data):
    """_parse's return tuple, keyed by name.

    These tests used to unpack it positionally, which meant every new field
    09_enrich_metadata collected broke a dozen assertions that did not care
    about it. The field order lives here once instead.
    """
    fields = _parse(data)
    assert len(fields) == len(PARSE_FIELDS), "PARSE_FIELDS is out of date"
    return dict(zip(PARSE_FIELDS, fields))


# ---------------------------------------------------------------------------
# _parse unit tests (pure function, no DB/network)
# ---------------------------------------------------------------------------

class TestParse:
    def test_genres_as_json_array(self):
        genres = parsed(SAMPLE_DETAIL)["genres"]
        assert json.loads(genres) == ["Crime", "Drama", "Action"]

    def test_runtime(self):
        runtime = parsed(SAMPLE_DETAIL)["runtime"]
        assert runtime == 170

    def test_cast_names_top_cast(self):
        cast_names = parsed(SAMPLE_DETAIL)["cast_names"]
        cast = json.loads(cast_names)
        assert cast[0] == "Al Pacino"
        assert cast[1] == "Robert De Niro"
        assert len(cast) == 5  # only 5 in sample

    def test_cast_capped_at_10(self):
        data = dict(SAMPLE_DETAIL)
        data["credits"] = {"cast": [
            {"name": f"Actor {i}", "order": i} for i in range(15)
        ]}
        cast_names = parsed(data)["cast_names"]
        assert len(json.loads(cast_names)) == 10

    def test_cast_sorted_by_order(self):
        data = dict(SAMPLE_DETAIL)
        data["credits"] = {"cast": [
            {"name": "Third",  "order": 2},
            {"name": "First",  "order": 0},
            {"name": "Second", "order": 1},
        ]}
        cast_names = parsed(data)["cast_names"]
        cast = json.loads(cast_names)
        assert cast == ["First", "Second", "Third"]

    def test_plot_summary(self):
        plot_summary = parsed(SAMPLE_DETAIL)["plot_summary"]
        assert "Neil McCauley" in plot_summary

    def test_poster_url_constructed(self):
        poster_url = parsed(SAMPLE_DETAIL)["poster_url"]
        assert poster_url.startswith("https://image.tmdb.org/t/p/w500/")
        assert "/e09dLw1" in poster_url

    def test_missing_poster_returns_none(self):
        data = {**SAMPLE_DETAIL, "poster_path": None}
        poster_url = parsed(data)["poster_url"]
        assert poster_url is None

    def test_empty_genres_returns_empty_list(self):
        data = {**SAMPLE_DETAIL, "genres": []}
        genres = parsed(data)["genres"]
        assert json.loads(genres) == []

    def test_missing_credits_returns_none_cast(self):
        data = {**SAMPLE_DETAIL, "credits": {}}
        cast_names = parsed(data)["cast_names"]
        assert cast_names is None

    def test_empty_overview_returns_none(self):
        data = {**SAMPLE_DETAIL, "overview": ""}
        plot_summary = parsed(data)["plot_summary"]
        assert plot_summary is None

    def test_whitespace_overview_returns_none(self):
        data = {**SAMPLE_DETAIL, "overview": "   "}
        plot_summary = parsed(data)["plot_summary"]
        assert plot_summary is None

    def test_none_runtime_stays_none(self):
        data = {**SAMPLE_DETAIL, "runtime": None}
        runtime = parsed(data)["runtime"]
        assert runtime is None

    def test_keywords_as_json_array(self):
        keywords = parsed(SAMPLE_DETAIL)["keywords"]
        assert json.loads(keywords) == ["robbery", "detective", "heist"]

    def test_empty_keywords_returns_empty_array(self):
        # Mirrors genres: "[]" not NULL, so NULL can mean "not yet fetched".
        data = {**SAMPLE_DETAIL, "keywords": {"keywords": []}}
        keywords = parsed(data)["keywords"]
        assert json.loads(keywords) == []

    def test_missing_keywords_key_returns_empty_array(self):
        data = {k: v for k, v in SAMPLE_DETAIL.items() if k != "keywords"}
        keywords = parsed(data)["keywords"]
        assert json.loads(keywords) == []

    def test_null_keywords_object_returns_empty_array(self):
        data = {**SAMPLE_DETAIL, "keywords": None}
        keywords = parsed(data)["keywords"]
        assert json.loads(keywords) == []


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

    # Seed two curated movies: one needing enrichment, one already done.
    #
    # "Already done" now has to include the financials and the cast ids. Both
    # are part of the enriched set, so a row with every text column filled but
    # no recorded fetch of either is genuinely still pending -- the cache row
    # below is what makes Jerry Maguire complete rather than merely populated.
    for tmdb_id, title, already_done in [
        (949,  "Heat",         False),
        (9390, "Jerry Maguire", True),
    ]:
        movie_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO curated_movies "
            "(movie_id, tmdb_id, title, year, genres, keywords, runtime_minutes, "
            " cast_names, cast_ids, plot_summary, poster_url_tmdb, "
            " total_episodes_featured, revisit_count, canonical_key_confidence) "
            "VALUES (?, ?, ?, 1995, ?, ?, ?, ?, ?, ?, ?, 1, 0, 'high')",
            (
                movie_id, tmdb_id, title,
                '["Drama"]' if already_done else None,
                '["sports agent"]' if already_done else None,
                120        if already_done else None,
                '["Tom Cruise"]' if already_done else None,
                '[500]'    if already_done else None,
                "A great film." if already_done else None,
                "https://example.com/poster.jpg" if already_done else None,
            )
        )
        if already_done:
            conn.execute(
                "INSERT INTO tmdb_metadata_cache "
                "(tmdb_id, genres, keywords, runtime_minutes, cast_names, "
                " cast_ids, plot_summary, poster_url_tmdb, budget_tmdb, "
                " revenue_tmdb, financials_cached_at, cast_cached_at) "
                "VALUES (?, '[\"Drama\"]', '[\"sports agent\"]', 120, "
                "        '[\"Tom Cruise\"]', '[500]', 'A great film.', "
                "        'https://example.com/poster.jpg', 50000000, 273600000, "
                "        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (tmdb_id,))
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
            "SELECT genres, runtime_minutes, cast_names, plot_summary, "
            "poster_url_tmdb, keywords FROM curated_movies WHERE tmdb_id = 949"
        ).fetchone()
        conn.close()

        assert json.loads(row[0]) == ["Crime", "Drama", "Action"]
        assert row[1] == 170
        assert "Al Pacino" in json.loads(row[2])
        assert row[3] is not None
        assert row[4].startswith("https://image.tmdb.org")
        assert json.loads(row[5]) == ["robbery", "detective", "heist"]

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
    clears the six enriched columns while the cache survives. Optionally
    restrict to a single tmdb_id."""
    conn = sqlite3.connect(db_path)
    sql = ("UPDATE curated_movies SET genres=NULL, keywords=NULL, "
           "runtime_minutes=NULL, cast_names=NULL, plot_summary=NULL, "
           "poster_url_tmdb=NULL")
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
            "SELECT genres, runtime_minutes, cast_names, plot_summary, "
            "poster_url_tmdb, budget_tmdb, revenue_tmdb, financials_cached_at "
            "FROM tmdb_metadata_cache WHERE tmdb_id = 949"
        ).fetchone()
        conn.close()
        assert row is not None
        assert json.loads(row[0]) == ["Crime", "Drama", "Action"]
        assert row[1] == 170
        assert row[5] == 60000000
        assert row[6] == 187436818
        assert row[7] is not None

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



# ---------------------------------------------------------------------------
# Schema migration: widen databases created before `keywords` existed
# ---------------------------------------------------------------------------

def _cols(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


class TestKeywordsMigration:
    def _legacy_db(self, tmp_path):
        """A db shaped like one built before keywords was introduced."""
        db_path = str(tmp_path / "legacy.db")
        conn = sqlite3.connect(db_path)
        conn.executescript("""
            CREATE TABLE curated_movies (
                movie_id TEXT PRIMARY KEY, tmdb_id INTEGER UNIQUE, title TEXT,
                genres TEXT, runtime_minutes INTEGER, cast_names TEXT,
                plot_summary TEXT, poster_url_tmdb TEXT, updated_at TIMESTAMP
            );
            CREATE TABLE tmdb_metadata_cache (
                tmdb_id INTEGER PRIMARY KEY, genres TEXT, runtime_minutes INTEGER,
                cast_names TEXT, plot_summary TEXT, poster_url_tmdb TEXT,
                cached_at TIMESTAMP
            );
            INSERT INTO tmdb_metadata_cache VALUES
                (949, '["Crime"]', 170, '["Al Pacino"]', 'Thieves.', 'u', 'now');
        """)
        conn.commit()
        return db_path, conn

    def test_adds_missing_column_to_both_tables(self, tmp_path):
        db_path, conn = self._legacy_db(tmp_path)
        assert "keywords" not in _cols(conn, "curated_movies")
        assert "keywords" not in _cols(conn, "tmdb_metadata_cache")

        ensure_cache_table(conn.cursor())
        conn.commit()

        assert "keywords" in _cols(conn, "curated_movies")
        assert "keywords" in _cols(conn, "tmdb_metadata_cache")
        conn.close()

    def test_migration_preserves_cached_rows(self, tmp_path):
        db_path, conn = self._legacy_db(tmp_path)
        ensure_cache_table(conn.cursor())
        conn.commit()

        row = conn.execute(
            "SELECT genres, runtime_minutes, keywords FROM tmdb_metadata_cache "
            "WHERE tmdb_id = 949").fetchone()
        conn.close()
        # Payload survives the ALTER; only the new column is null.
        assert json.loads(row[0]) == ["Crime"]
        assert row[1] == 170
        assert row[2] is None

    def test_migration_is_idempotent(self, tmp_path):
        db_path, conn = self._legacy_db(tmp_path)
        cur = conn.cursor()
        ensure_cache_table(cur)
        ensure_cache_table(cur)   # second call must not raise "duplicate column"
        conn.commit()
        assert "keywords" in _cols(conn, "tmdb_metadata_cache")
        conn.close()

    def test_ensure_column_noop_on_absent_table(self, tmp_path):
        conn = sqlite3.connect(str(tmp_path / "empty.db"))
        _ensure_column(conn.cursor(), "does_not_exist", "keywords")  # must not raise
        conn.close()

    def test_prekeywords_cache_row_is_refetched_then_converges(self, tmp_path):
        """A cache row written before keywords existed must be refetched once,
        then stop being refetched -- otherwise every run re-calls the API."""
        db_path = str(tmp_path / "stale.db")
        conn = sqlite3.connect(db_path)
        schema_dir = Path(__file__).parent.parent / "sql" / "schemas"
        for fname in ["raw_zone.sql", "staging_zone.sql", "curated_zone.sql"]:
            conn.executescript((schema_dir / fname).read_text())
        conn.execute(
            "INSERT INTO curated_movies (movie_id, tmdb_id, title, year, "
            "total_episodes_featured, revisit_count, canonical_key_confidence) "
            "VALUES (?, 949, 'Heat', 1995, 1, 0, 'high')", (str(uuid.uuid4()),))
        # Legacy cache row: every column filled except keywords.
        conn.execute(
            "INSERT INTO tmdb_metadata_cache (tmdb_id, genres, runtime_minutes, "
            "cast_names, plot_summary, poster_url_tmdb, keywords) "
            "VALUES (949, '[\"Crime\"]', 170, '[\"Al Pacino\"]', 'Thieves.', 'u', NULL)")
        conn.commit()
        conn.close()

        with patch("requests.get", return_value=_mock_response(SAMPLE_DETAIL)) as g1:
            enrich_metadata(db_path)
        assert g1.call_count == 1, "stale row should trigger exactly one refetch"

        conn = sqlite3.connect(db_path)
        cached_kw, curated_kw = conn.execute(
            "SELECT c.keywords, m.keywords FROM tmdb_metadata_cache c "
            "JOIN curated_movies m ON m.tmdb_id = c.tmdb_id WHERE c.tmdb_id = 949"
        ).fetchone()
        conn.close()
        assert json.loads(cached_kw) == ["robbery", "detective", "heist"]
        assert json.loads(curated_kw) == ["robbery", "detective", "heist"]

        # Second run must be free -- the row is no longer stale.
        with patch("requests.get", return_value=_mock_response(SAMPLE_DETAIL)) as g2:
            enriched, errors = enrich_metadata(db_path)
        assert g2.call_count == 0
        assert (enriched, errors) == (0, 0)

    def test_film_with_no_keywords_does_not_refetch_forever(self, tmp_path):
        """A film TMDB has no keywords for caches as "[]" and stays cached."""
        db_path = str(tmp_path / "nokw.db")
        conn = sqlite3.connect(db_path)
        schema_dir = Path(__file__).parent.parent / "sql" / "schemas"
        for fname in ["raw_zone.sql", "staging_zone.sql", "curated_zone.sql"]:
            conn.executescript((schema_dir / fname).read_text())
        conn.execute(
            "INSERT INTO curated_movies (movie_id, tmdb_id, title, year, "
            "total_episodes_featured, revisit_count, canonical_key_confidence) "
            "VALUES (?, 949, 'Heat', 1995, 1, 0, 'high')", (str(uuid.uuid4()),))
        conn.commit()
        conn.close()

        no_kw = {**SAMPLE_DETAIL, "keywords": {"keywords": []}}
        with patch("requests.get", return_value=_mock_response(no_kw)) as g1:
            enrich_metadata(db_path)
        assert g1.call_count == 1

        with patch("requests.get", return_value=_mock_response(no_kw)) as g2:
            enrich_metadata(db_path)
        assert g2.call_count == 0, "empty keywords must not look like a stale row"


# ---------------------------------------------------------------------------
# Budget and revenue
#
# TMDB reports an unknown budget or revenue as 0 rather than null. Carried
# through, a film whose budget nobody published reads as a film that cost
# nothing -- which then anchors every ratio, average and ranking built on it.
# ---------------------------------------------------------------------------

_money = mod._money


class TestMoney:
    def test_positive_amount_passes_through(self):
        assert _money(60000000) == 60000000

    def test_zero_becomes_none(self):
        """The whole point: 0 from TMDB means 'not published', not 'free'."""
        assert _money(0) is None

    def test_missing_becomes_none(self):
        assert _money(None) is None

    def test_negative_becomes_none(self):
        assert _money(-5) is None

    def test_non_numeric_becomes_none(self):
        assert _money("n/a") is None

    def test_numeric_string_is_accepted(self):
        assert _money("60000000") == 60000000


class TestParseFinancials:
    def test_budget_and_revenue_extracted(self):
        p = parsed(SAMPLE_DETAIL)
        budget, revenue = p["budget"], p["revenue"]
        assert budget == 60000000
        assert revenue == 187436818

    def test_zero_budget_parses_to_none(self):
        p = parsed({**SAMPLE_DETAIL, "budget": 0})
        budget, revenue = p["budget"], p["revenue"]
        assert budget is None
        assert revenue == 187436818

    def test_absent_financials_parse_to_none(self):
        data = {k: v for k, v in SAMPLE_DETAIL.items()
                if k not in ("budget", "revenue")}
        p = parsed(data)
        budget, revenue = p["budget"], p["revenue"]
        assert budget is None and revenue is None


class TestFinancialsCache:
    def test_financials_written_to_curated(self, tmp_db):
        with patch("requests.get", return_value=_mock_response(SAMPLE_DETAIL)):
            enrich_metadata(tmp_db)
        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT budget_tmdb, revenue_tmdb FROM curated_movies WHERE tmdb_id = 949"
        ).fetchone()
        conn.close()
        assert row == (60000000, 187436818)

    def test_a_film_with_no_published_budget_does_not_refetch_forever(self, tmp_db):
        """The reason the cache marks the fetch rather than the value.

        Budget and revenue may both be legitimately NULL after a successful
        call. Testing staleness on the values would put such a film back in the
        pending set on every single run, re-billing the API forever.
        """
        payload = {**SAMPLE_DETAIL, "budget": 0, "revenue": 0}
        with patch("requests.get", return_value=_mock_response(payload)) as g1:
            enrich_metadata(tmp_db)
        assert g1.call_count == 1

        conn = sqlite3.connect(tmp_db)
        budget, revenue, marker = conn.execute(
            "SELECT budget_tmdb, revenue_tmdb, financials_cached_at "
            "FROM tmdb_metadata_cache WHERE tmdb_id = 949"
        ).fetchone()
        conn.close()
        assert budget is None and revenue is None
        assert marker is not None, "the fetch must be recorded even when it found nothing"

        # Second run: nothing left to do, and crucially no second API call.
        with patch("requests.get", return_value=_mock_response(payload)) as g2:
            enrich_metadata(tmp_db)
        assert g2.call_count == 0

    def test_cache_row_predating_the_columns_is_refetched_once(self, tmp_path):
        """Existing databases carry 455 rows cached before financials existed."""
        db = tmp_path / "legacy.db"
        conn = sqlite3.connect(db)
        conn.executescript("""
            CREATE TABLE curated_movies (
                movie_id TEXT PRIMARY KEY, tmdb_id INTEGER, title TEXT,
                genres TEXT, keywords TEXT, runtime_minutes INTEGER,
                cast_names TEXT, plot_summary TEXT, poster_url_tmdb TEXT,
                updated_at TIMESTAMP);
            CREATE TABLE tmdb_metadata_cache (
                tmdb_id INTEGER PRIMARY KEY, genres TEXT, keywords TEXT,
                runtime_minutes INTEGER, cast_names TEXT, plot_summary TEXT,
                poster_url_tmdb TEXT, cached_at TIMESTAMP);
        """)
        conn.execute(
            "INSERT INTO curated_movies (movie_id, tmdb_id, title) "
            "VALUES ('m1', 949, 'Heat')")
        conn.execute(
            "INSERT INTO tmdb_metadata_cache (tmdb_id, genres, keywords, "
            "runtime_minutes, cast_names, plot_summary, poster_url_tmdb) "
            "VALUES (949, '[]', '[]', 170, '[]', 'x', 'y')")
        conn.commit()
        conn.close()

        with patch("requests.get", return_value=_mock_response(SAMPLE_DETAIL)) as g1:
            enrich_metadata(str(db))
        assert g1.call_count == 1, "a pre-financials row must be refetched once"

        # And exactly once: the second run is served from the widened cache.
        with patch("requests.get", return_value=_mock_response(SAMPLE_DETAIL)) as g2:
            enrich_metadata(str(db))
        assert g2.call_count == 0
