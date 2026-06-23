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


def enrich_metadata(db_path):
    if not TMDB_API_KEY:
        logger.error("TMDB_API_KEY not set in config/.env")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

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

    enriched = errors = 0
    for movie_id, tmdb_id, title in pending:
        data = fetch_details(tmdb_id)
        if data is None:
            errors += 1
            time.sleep(RATE_LIMIT_SLEEP)
            continue

        genres, runtime, cast_names, plot_summary, poster_url = _parse(data)

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
        time.sleep(RATE_LIMIT_SLEEP)

    conn.close()
    logger.info(f"✓ Metadata enrichment complete: {enriched} enriched, {errors} errors")
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
