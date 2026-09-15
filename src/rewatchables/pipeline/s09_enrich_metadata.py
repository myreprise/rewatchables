#!/usr/bin/env python3
"""
Phase C: Enrich curated_movies with detailed TMDB metadata.

For each canonical movie lacking metadata, calls:
  GET /movie/{tmdb_id}?append_to_response=credits,keywords

Fills seven previously-null columns:
  genres           JSON array of genre name strings
  keywords         JSON array of TMDB keyword strings (thematic tags)
  runtime_minutes  integer
  cast_names       JSON array of top-10 billed actor names
  cast_ids         JSON array of TMDB person ids, parallel to cast_names
  plot_summary     overview text
  poster_url_tmdb  full URL  (https://image.tmdb.org/t/p/w500/<path>)

Also fills the `curated_people` dimension: one row per credited person, with
the gender TMDB records for them. Every cast member in the `credits` sub-object
already carries `id` and `gender`, so this is a read of a payload we were
fetching and discarding -- not an extra call.

Idempotent: skips movies where all six columns are already filled.
Re-running after future xlsx reloads only costs calls for newly added movies.

Persistent cache: every fetched payload is written through to the
`tmdb_metadata_cache` table (keyed by tmdb_id). Because 06_build_curated wipes
and rebuilds curated_movies on every run — clearing these five columns — the
cache lets us refill from local storage instead of re-calling TMDB. A TMDB call
is made only for a tmdb_id never seen before. So after adding one new film, a
full pipeline re-run costs exactly one metadata call, not one per movie.
"""

import json
import logging
import os
import sqlite3
import sys
import time
from pathlib import Path

import requests

from rewatchables import config

logger = logging.getLogger(__name__)

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
POSTER_BASE_URL = "https://image.tmdb.org/t/p/w500"
RATE_LIMIT_SLEEP = 0.26   # ~3.8 req/sec, comfortably under 40/10 s
MAX_CAST = 10

# TMDB's gender enum. 0 is "not set" rather than an assertion about the person,
# so it is stored as 'unknown' and never guessed at -- see curated_people in
# sql/schemas/curated_zone.sql. Anything outside the enum maps to 'unknown' too.
GENDER_CODES = {0: "unknown", 1: "F", 2: "M", 3: "NB"}


def _redact(text):
    if text and TMDB_API_KEY:
        return str(text).replace(TMDB_API_KEY, "***")
    return text


def fetch_details(tmdb_id):
    """
    Fetch movie detail + credits + keywords in one call.
    Returns a dict with keys: genres, runtime, cast, overview, poster_path,
    keywords.
    Returns None on unrecoverable error.
    """
    url = f"{TMDB_BASE_URL}/movie/{tmdb_id}"
    params = {"api_key": TMDB_API_KEY, "append_to_response": "credits,keywords"}

    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=10)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 404:
                logger.warning(f"tmdb_id {tmdb_id} returned 404 — skipping")
                return None
            logger.warning(f"tmdb_id {tmdb_id} HTTP {r.status_code} (attempt {attempt+1}/3)")
            time.sleep(2 * (attempt + 1))
        except (requests.Timeout, requests.ConnectionError) as e:
            logger.warning(f"tmdb_id {tmdb_id} transient error (attempt {attempt+1}/3): "
                           f"{_redact(str(e))}")
            time.sleep(2 * (attempt + 1))
        except Exception as e:
            logger.error(f"tmdb_id {tmdb_id} unexpected error: {_redact(str(e))}")
            return None

    logger.error(f"tmdb_id {tmdb_id} gave up after 3 attempts")
    return None


def _money(value):
    """TMDB reports an unknown budget or revenue as 0, not null.

    Carried through as 0 it would read as a film that cost nothing or earned
    nothing, which is a different and much louder claim than "not published".
    Every downstream average, ratio and rank would be wrong. Map it to NULL.
    """
    try:
        value = int(value or 0)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _parse(data):
    """Extract the target fields from a raw TMDB detail response.

    Returns the movie-level tuple plus `people`: one (person_id, name, gender)
    per billed cast member, for the curated_people dimension. cast_names and
    cast_ids are built in one pass over the same sorted slice, so they stay
    positionally parallel by construction rather than by convention.
    """
    genres = json.dumps([g["name"] for g in data.get("genres") or []])
    # keywords live under the appended sub-object: {"keywords": {"keywords": [...]}}
    keywords = json.dumps([k["name"] for k in
                           (data.get("keywords") or {}).get("keywords") or []])
    runtime = data.get("runtime") or None
    billed = sorted(data.get("credits", {}).get("cast") or [],
                    key=lambda x: x.get("order", 9999))[:MAX_CAST]
    cast_names = json.dumps([c["name"] for c in billed]) if billed else None
    cast_ids = json.dumps([c.get("id") for c in billed]) if billed else None
    # A cast entry with no id cannot be keyed, so it is left out of the
    # dimension. cast_ids still carries its null in position, so the two
    # arrays keep lining up with cast_names.
    people = [(c["id"], c["name"], GENDER_CODES.get(c.get("gender"), "unknown"))
              for c in billed if c.get("id") is not None]
    plot_summary = (data.get("overview") or "").strip() or None
    poster_path = data.get("poster_path")
    poster_url = f"{POSTER_BASE_URL}{poster_path}" if poster_path else None
    budget = _money(data.get("budget"))
    revenue = _money(data.get("revenue"))
    return (genres, runtime, cast_names, cast_ids, plot_summary, poster_url,
            keywords, budget, revenue, people)


def _ensure_column(cursor, table, column, decl="TEXT"):
    """Add `column` to `table` if it is missing (no-op when already present).

    CREATE TABLE IF NOT EXISTS cannot widen an existing table, so databases
    created before a column was introduced need an explicit ALTER.
    """
    existing = {r[1] for r in cursor.execute(f"PRAGMA table_info({table})")}
    if existing and column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        logger.info(f"Migrated {table}: added {column} column")


def ensure_cache_table(cursor):
    """Create the metadata cache if it does not yet exist, and migrate it.

    The schema also defines this table, but existing databases predating the
    cache won't have it (02_load_raw only runs the schema on a fresh db), so
    create it here defensively. Databases predating the `keywords` column are
    widened in place rather than rebuilt, preserving every cached payload.
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tmdb_metadata_cache (
            tmdb_id INTEGER PRIMARY KEY,
            genres TEXT,
            keywords TEXT,
            runtime_minutes INTEGER,
            cast_names TEXT,
            plot_summary TEXT,
            poster_url_tmdb TEXT,
            cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _ensure_column(cursor, "tmdb_metadata_cache", "keywords")
    _ensure_column(cursor, "curated_movies", "keywords")
    for table in ("tmdb_metadata_cache", "curated_movies"):
        _ensure_column(cursor, table, "budget_tmdb", "INTEGER")
        _ensure_column(cursor, table, "revenue_tmdb", "INTEGER")
        _ensure_column(cursor, table, "cast_ids")
    _ensure_column(cursor, "tmdb_metadata_cache", "financials_cached_at",
                   "TIMESTAMP")
    _ensure_column(cursor, "tmdb_metadata_cache", "cast_cached_at", "TIMESTAMP")
    ensure_people_table(cursor)


def ensure_people_table(cursor):
    """Create the people dimension if it does not yet exist.

    Same defensive reason as the cache above: the schema defines it, but
    02_load_raw only applies the schema to a fresh database.
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS curated_people (
            tmdb_person_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            gender TEXT CHECK(gender IN ('F', 'M', 'NB', 'unknown')),
            gender_source TEXT CHECK(gender_source IN ('tmdb', 'cmu', 'manual')),
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_curated_people_name "
                   "ON curated_people(name)")


def people_put(cursor, people):
    """Upsert (person_id, name, gender) rows into the people dimension.

    A row whose gender_source is 'manual' is left alone: a hand correction
    exists precisely because TMDB's answer was wrong, so a later refetch must
    not undo it. Rows sourced from TMDB or CMU are refreshed.
    """
    cursor.executemany("""
        INSERT INTO curated_people
            (tmdb_person_id, name, gender, gender_source, updated_at)
        VALUES (?, ?, ?, 'tmdb', CURRENT_TIMESTAMP)
        ON CONFLICT(tmdb_person_id) DO UPDATE SET
            name          = excluded.name,
            gender        = excluded.gender,
            gender_source = 'tmdb',
            updated_at    = CURRENT_TIMESTAMP
        WHERE curated_people.gender_source IS NOT 'manual'
    """, people)


def cache_get(cursor, tmdb_id):
    """Return the cached columns for tmdb_id, or None on a cache miss.

    A returned row means TMDB was already queried for this id; None means it
    has never been fetched. Most columns may legitimately be NULL (a film with
    no poster, say), but `keywords` is always written as a JSON array — so a
    NULL there marks a row cached before keywords were collected, and is
    reported as a miss so the payload gets refetched once. `financials_cached_at`
    plays the same role for budget/revenue -- and is a separate marker precisely
    because those two may be legitimately NULL after a successful fetch.
    `cast_cached_at` is the same again for cast ids and gender.
    """
    return cursor.execute(
        "SELECT genres, runtime_minutes, cast_names, plot_summary, poster_url_tmdb, "
        "keywords, budget_tmdb, revenue_tmdb, financials_cached_at, "
        "cast_ids, cast_cached_at "
        "FROM tmdb_metadata_cache WHERE tmdb_id = ?", (tmdb_id,)
    ).fetchone()


def cache_put(cursor, tmdb_id, genres, runtime, cast_names, cast_ids,
              plot_summary, poster_url, keywords, budget, revenue):
    """Write-through the parsed metadata for tmdb_id into the cache."""
    cursor.execute(
        "INSERT OR REPLACE INTO tmdb_metadata_cache "
        "(tmdb_id, genres, runtime_minutes, cast_names, cast_ids, plot_summary, "
        " poster_url_tmdb, keywords, budget_tmdb, revenue_tmdb, "
        " financials_cached_at, cast_cached_at, cached_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, "
        "        CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        (tmdb_id, genres, runtime, cast_names, cast_ids, plot_summary,
         poster_url, keywords, budget, revenue))


def enrich_metadata(db_path):
    if not TMDB_API_KEY:
        logger.error("TMDB_API_KEY not set in config/.env")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    ensure_cache_table(cursor)

    # Only fetch movies that are still missing metadata
    cursor.execute("""
        SELECT movie_id, tmdb_id, title
        FROM curated_movies
        WHERE genres IS NULL
           OR keywords IS NULL
           OR runtime_minutes IS NULL
           OR cast_names IS NULL
           OR cast_ids IS NULL
           OR plot_summary IS NULL
           OR poster_url_tmdb IS NULL
           OR tmdb_id NOT IN (SELECT tmdb_id FROM tmdb_metadata_cache
                              WHERE financials_cached_at IS NOT NULL
                                AND cast_cached_at IS NOT NULL)
        ORDER BY title
    """)
    pending = cursor.fetchall()
    total = cursor.execute("SELECT COUNT(*) FROM curated_movies").fetchone()[0]
    logger.info(f"Enriching metadata for {len(pending)}/{total} movies "
                f"({total - len(pending)} already complete)")

    enriched = from_cache = from_api = errors = stale = 0
    for movie_id, tmdb_id, title in pending:
        cached = cache_get(cursor, tmdb_id)
        if cached is not None and (cached[5] is None or cached[8] is None
                                   or cached[10] is None):
            # Row predates the keywords, the financial columns or the cast ids:
            # refetch once to complete it. Tested on the marker, not on the
            # values, so a film whose budget TMDB does not know settles after
            # one fetch instead of being re-requested on every run forever.
            cached = None
            stale += 1
        if cached is not None:
            # Cache hit: refill curated_movies from local storage, no API call.
            # The people rows these cast_ids point at are already in
            # curated_people -- the rebuild does not clear that table -- so a
            # cache hit needs no person write either.
            (genres, runtime, cast_names, plot_summary, poster_url,
             keywords, budget, revenue, _fin_at, cast_ids, _cast_at) = cached
            from_cache += 1
        else:
            # Cache miss: fetch once, then write through to the cache.
            data = fetch_details(tmdb_id)
            if data is None:
                errors += 1
                time.sleep(RATE_LIMIT_SLEEP)
                continue
            (genres, runtime, cast_names, cast_ids, plot_summary, poster_url,
             keywords, budget, revenue, people) = _parse(data)
            cache_put(cursor, tmdb_id, genres, runtime, cast_names, cast_ids,
                      plot_summary, poster_url, keywords, budget, revenue)
            if people:
                people_put(cursor, people)
            from_api += 1

        cursor.execute("""
            UPDATE curated_movies
            SET genres          = ?,
                keywords        = ?,
                runtime_minutes = ?,
                cast_names      = ?,
                cast_ids        = ?,
                plot_summary    = ?,
                poster_url_tmdb = ?,
                budget_tmdb     = ?,
                revenue_tmdb    = ?,
                updated_at      = CURRENT_TIMESTAMP
            WHERE movie_id = ?
        """, (genres, keywords, runtime, cast_names, cast_ids, plot_summary,
              poster_url, budget, revenue, movie_id))

        conn.commit()
        enriched += 1
        if enriched % 50 == 0:
            logger.info(f"  {enriched}/{len(pending)} enriched...")
        # Rate-limit only when we actually called the API; cache hits are free.
        if cached is None:
            time.sleep(RATE_LIMIT_SLEEP)

    people_total = cursor.execute(
        "SELECT COUNT(*) FROM curated_people").fetchone()[0]
    unknown = cursor.execute(
        "SELECT COUNT(*) FROM curated_people WHERE gender = 'unknown'"
    ).fetchone()[0]
    conn.close()

    logger.info(f"✓ Metadata enrichment complete: {enriched} enriched "
                f"({from_cache} from cache, {from_api} from API), {errors} errors")
    logger.info(f"  curated_people: {people_total} people, "
                f"{unknown} with gender unknown to TMDB")
    if stale:
        logger.info(f"  ({stale} cache rows refetched to backfill new columns)")
    return enriched, errors


def main():
    db_path = str(config.db_path())
    if not Path(db_path).exists():
        logger.error(f"{db_path} not found.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Phase C: Enrich curated_movies metadata from TMDB")
    logger.info("=" * 60)
    enrich_metadata(db_path)
    logger.info("=" * 60)


if __name__ == "__main__":
    config.setup_logging()
    main()
