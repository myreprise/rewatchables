#!/usr/bin/env python3
"""
Phase C: Enrich curated_movies with detailed TMDB metadata.

For each canonical movie lacking metadata, calls:
  GET /movie/{tmdb_id}?append_to_response=credits

Fills five previously-null columns:
  genres           JSON array of genre name strings
  runtime_minutes  integer
  cast_names       JSON array of top-10 billed actor names
  plot_summary     overview text
  poster_url_tmdb  full URL  (https://image.tmdb.org/t/p/w500/<path>)

Idempotent: skips movies where all five columns are already filled.
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
from dotenv import load_dotenv

load_dotenv("config/.env")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
POSTER_BASE_URL = "https://image.tmdb.org/t/p/w500"
RATE_LIMIT_SLEEP = 0.26   # ~3.8 req/sec, comfortably under 40/10 s
MAX_CAST = 10


def _redact(text):
    if text and TMDB_API_KEY:
        return str(text).replace(TMDB_API_KEY, "***")
    return text


def fetch_details(tmdb_id):
    """
    Fetch movie detail + credits in one call.
    Returns a dict with keys: genres, runtime, cast, overview, poster_path.
    Returns None on unrecoverable error.
    """
    url = f"{TMDB_BASE_URL}/movie/{tmdb_id}"
    params = {"api_key": TMDB_API_KEY, "append_to_response": "credits"}

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


def _parse(data):
    """Extract the five target fields from a raw TMDB detail response."""
    genres = json.dumps([g["name"] for g in data.get("genres") or []])
    runtime = data.get("runtime") or None
    cast = [c["name"] for c in
            sorted(data.get("credits", {}).get("cast") or [],
                   key=lambda x: x.get("order", 9999))[:MAX_CAST]]
    cast_names = json.dumps(cast) if cast else None
    plot_summary = (data.get("overview") or "").strip() or None
    poster_path = data.get("poster_path")
    poster_url = f"{POSTER_BASE_URL}{poster_path}" if poster_path else None
    return genres, runtime, cast_names, plot_summary, poster_url


def ensure_cache_table(cursor):
    """Create the metadata cache if it does not yet exist.

    The schema also defines this table, but existing databases predating the
    cache won't have it (02_load_raw only runs the schema on a fresh db), so
    create it here defensively.
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tmdb_metadata_cache (
            tmdb_id INTEGER PRIMARY KEY,
            genres TEXT,
            runtime_minutes INTEGER,
            cast_names TEXT,
            plot_summary TEXT,
            poster_url_tmdb TEXT,
            cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def cache_get(cursor, tmdb_id):
    """Return the five cached columns for tmdb_id, or None on a cache miss.

    A returned row (even with NULL members) means TMDB was already queried for
    this id; None means it has never been fetched.
    """
    return cursor.execute(
        "SELECT genres, runtime_minutes, cast_names, plot_summary, poster_url_tmdb "
        "FROM tmdb_metadata_cache WHERE tmdb_id = ?", (tmdb_id,)
    ).fetchone()


def cache_put(cursor, tmdb_id, genres, runtime, cast_names, plot_summary, poster_url):
    """Write-through the parsed metadata for tmdb_id into the cache."""
    cursor.execute(
        "INSERT OR REPLACE INTO tmdb_metadata_cache "
        "(tmdb_id, genres, runtime_minutes, cast_names, plot_summary, "
        " poster_url_tmdb, cached_at) "
        "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
        (tmdb_id, genres, runtime, cast_names, plot_summary, poster_url))


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
           OR runtime_minutes IS NULL
           OR cast_names IS NULL
           OR plot_summary IS NULL
           OR poster_url_tmdb IS NULL
        ORDER BY title
    """)
    pending = cursor.fetchall()
    total = cursor.execute("SELECT COUNT(*) FROM curated_movies").fetchone()[0]
    logger.info(f"Enriching metadata for {len(pending)}/{total} movies "
                f"({total - len(pending)} already complete)")

    enriched = from_cache = from_api = errors = 0
    for movie_id, tmdb_id, title in pending:
        cached = cache_get(cursor, tmdb_id)
        if cached is not None:
            # Cache hit: refill curated_movies from local storage, no API call.
            genres, runtime, cast_names, plot_summary, poster_url = cached
            from_cache += 1
        else:
            # Cache miss: fetch once, then write through to the cache.
            data = fetch_details(tmdb_id)
            if data is None:
                errors += 1
                time.sleep(RATE_LIMIT_SLEEP)
                continue
            genres, runtime, cast_names, plot_summary, poster_url = _parse(data)
            cache_put(cursor, tmdb_id, genres, runtime, cast_names,
                      plot_summary, poster_url)
            from_api += 1

        cursor.execute("""
            UPDATE curated_movies
            SET genres          = ?,
                runtime_minutes = ?,
                cast_names      = ?,
                plot_summary    = ?,
                poster_url_tmdb = ?,
                updated_at      = CURRENT_TIMESTAMP
            WHERE movie_id = ?
        """, (genres, runtime, cast_names, plot_summary, poster_url, movie_id))

        conn.commit()
        enriched += 1
        if enriched % 50 == 0:
            logger.info(f"  {enriched}/{len(pending)} enriched...")
        # Rate-limit only when we actually called the API; cache hits are free.
        if cached is None:
            time.sleep(RATE_LIMIT_SLEEP)

    conn.close()
    logger.info(f"✓ Metadata enrichment complete: {enriched} enriched "
                f"({from_cache} from cache, {from_api} from API), {errors} errors")
    return enriched, errors


def main():
    db_path = os.getenv("DB_PATH", "rewatchables.db")
    if not Path(db_path).exists():
        logger.error(f"{db_path} not found.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Phase C: Enrich curated_movies metadata from TMDB")
    logger.info("=" * 60)
    enrich_metadata(db_path)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
