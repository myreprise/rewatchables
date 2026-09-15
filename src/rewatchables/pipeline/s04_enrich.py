#!/usr/bin/env python3
"""
Phase 3: Enrich from TMDB
Searches TMDB for each staging movie mention, scores the candidates, and either
auto-resolves high-confidence matches or queues low-confidence ones for manual
review. Handles rate limiting and logs every API call.

Scoring:
    confidence = 0.75 * title_similarity + 0.25 * year_score
    - title_similarity: difflib ratio on normalized titles (0..1)
    - year_score: 1.0 exact, 0.6 within MATCH_YEAR_WINDOW, 0.5 if no year to
      compare, 0.0 if outside window
Auto-resolve when confidence >= MATCH_CONFIDENCE_THRESHOLD AND title_similarity >= 0.6
(the title guard stops a good year from rescuing a wrong title).

SEARCH RESULTS ARE CACHED. 03_normalize clears staging, which resets every
mention to 'unresolved' and sends the whole catalogue back through here. The
`tmdb_search_cache` table means that costs nothing: a full rebuild re-scores
from local storage and only a genuinely new title reaches the network.

What is cached is the raw candidate list, not the resolution. Scoring and the
threshold are applied fresh on every run, so retuning MATCH_YEAR_WINDOW or
MATCH_CONFIDENCE_THRESHOLD re-resolves the entire catalogue offline. Pass
--refresh to bypass the cache and re-query TMDB.
"""

import argparse
import os
import sys
import re
import logging
import sqlite3
import uuid
import json
import time
from difflib import SequenceMatcher
import requests
from pathlib import Path

from rewatchables import config

logger = logging.getLogger(__name__)

TMDB_API_KEY = os.getenv('TMDB_API_KEY')
TMDB_BASE_URL = "https://api.themoviedb.org/3"

CONFIDENCE_THRESHOLD = float(os.getenv('MATCH_CONFIDENCE_THRESHOLD', '0.85'))
YEAR_WINDOW = int(os.getenv('MATCH_YEAR_WINDOW', '2'))
RATE_LIMIT_SLEEP = 0.25  # ~4 req/sec, well under TMDB's 40 req / 10 sec


def strip_annotations(title):
    """Remove podcast annotations (parentheticals, bracketed/quoted asides)
    that break TMDB search, e.g. 'Batman (1989)' -> 'Batman'."""
    if not title:
        return ''
    t = str(title)
    # Strip quoted asides first so nested cases like '("A Few Good (Re)Men")'
    # are removed as a unit before the paren pass runs
    t = re.sub(r'[\"""][^\"""]*[\"""]', ' ', t)
    t = re.sub(r'\([^)]*\)', ' ', t)
    t = re.sub(r'\[[^\]]*\]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


def normalize_title(title):
    """Lowercase, drop a leading 'the', strip punctuation, collapse whitespace."""
    if not title:
        return ''
    t = strip_annotations(title).lower().strip()
    t = re.sub(r'^the\s+', '', t)
    t = re.sub(r'[^a-z0-9\s]', '', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


def score_candidate(query_title, query_year, cand_title, cand_year):
    """Return (confidence, title_similarity, year_score) for one candidate."""
    title_sim = SequenceMatcher(None, normalize_title(query_title),
                                normalize_title(cand_title)).ratio()

    if query_year and cand_year:
        diff = abs(int(query_year) - int(cand_year))
        if diff == 0:
            year_score = 1.0
        elif diff <= YEAR_WINDOW:
            year_score = 0.6
        else:
            year_score = 0.0
    else:
        year_score = 0.5  # neutral when we can't compare

    confidence = 0.75 * title_sim + 0.25 * year_score
    return round(confidence, 4), round(title_sim, 4), year_score


def _redact(text):
    """Never persist the API key (it leaks into requests' exception strings)."""
    if text and TMDB_API_KEY:
        return text.replace(TMDB_API_KEY, '***')
    return text


def log_api_call(db_path, api_source, query, status_code, response_time_ms,
                 rate_limit_remaining=None, error=None):
    """Log API call for monitoring."""
    error = _redact(error)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    call_id = str(uuid.uuid4())
    cursor.execute('''
        INSERT INTO api_call_log (call_id, api_source, query_text, response_status_code,
                                  response_time_ms, rate_limit_remaining, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (call_id, api_source, query, status_code, response_time_ms,
          rate_limit_remaining, error))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Search cache. See the tmdb_search_cache block in sql/schemas/staging_zone.sql
# for why this stores raw candidates rather than resolutions.
# ---------------------------------------------------------------------------

def cache_key(title, year):
    """Identity of a TMDB search: normalized title plus year, '' when unyeared.

    Normalized because that is the form score_candidate compares, so two source
    spellings that score identically share one cache entry. The year is folded
    into the key rather than kept as a nullable column -- SQLite treats NULLs as
    distinct in a unique index, so a NULL year would insert a fresh duplicate on
    every run instead of hitting.
    """
    return f"{normalize_title(title)}|{year if year else ''}"


def ensure_cache_table(cursor):
    """Create the search cache if it does not exist.

    Databases predating this table were built by an 02_load_raw run that
    executed the schema files once, at creation; replaying the whole schema here
    would be heavier than it needs to be, so just this table is created.
    """
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tmdb_search_cache (
            cache_key TEXT PRIMARY KEY,
            query_title TEXT NOT NULL,
            query_year INTEGER,
            candidates_json TEXT NOT NULL,
            result_count INTEGER NOT NULL,
            cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')


def cache_get(cursor, title, year):
    """Cached candidates for a search, or None on a miss.

    A miss is None; a hit that found nothing is [] . Keeping those distinct is
    the point -- a title TMDB has no match for must not be re-queried forever.
    """
    row = cursor.execute(
        "SELECT candidates_json FROM tmdb_search_cache WHERE cache_key = ?",
        (cache_key(title, year),)
    ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row[0])
    except (ValueError, TypeError):
        return None   # corrupt entry: treat as a miss and re-fetch


def cache_put(cursor, title, year, candidates):
    """Write a search result through to the cache."""
    cursor.execute(
        "INSERT OR REPLACE INTO tmdb_search_cache "
        "(cache_key, query_title, query_year, candidates_json, result_count, cached_at) "
        "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
        (cache_key(title, year), title, year,
         json.dumps(candidates), len(candidates))
    )


def search_tmdb_cached(cursor, db_path, title, year=None, refresh=False):
    """Search TMDB through the cache. Returns (candidates, hit_network).

    `candidates` is a list on success (possibly empty) or None if the search
    failed; the caller must keep those apart, because a failure should leave the
    mention alone rather than record it as unmatchable.

    `hit_network` tells the caller whether to pay the rate-limit sleep. Without
    it a fully cached rebuild would still idle for two minutes doing nothing.
    """
    if not refresh:
        cached = cache_get(cursor, title, year)
        if cached is not None:
            return cached, False

    candidates = search_tmdb(db_path, title, year)
    # Only a successful search is cacheable. Storing [] for an HTTP error or a
    # missing API key would freeze a transient outage in as "no such film" and
    # every later run would trust it.
    if candidates is not None:
        cache_put(cursor, title, year, candidates)
    return candidates, True


def search_tmdb(db_path, title, year=None):
    """Search TMDB for a movie. Returns the top 5 raw candidate dicts.

    A successful search returns a list, which may be empty when TMDB genuinely
    knows no such film. A FAILED search returns None. The distinction exists for
    the cache: an empty list is a durable answer worth storing, while an HTTP
    error or a missing API key is a transient condition that must not be frozen
    in as "no such movie".
    """
    if not TMDB_API_KEY:
        logger.warning("TMDB_API_KEY not set, skipping TMDB enrichment")
        return None

    url = f"{TMDB_BASE_URL}/search/movie"
    params = {'api_key': TMDB_API_KEY, 'query': title}
    if year:
        params['year'] = year

    last_err = None
    for attempt in range(3):  # retry transient network/timeouts with backoff
        try:
            start_time = time.time()
            response = requests.get(url, params=params, timeout=10)
            elapsed_ms = int((time.time() - start_time) * 1000)
            rate_limit_remaining = response.headers.get('x-ratelimit-remaining')

            if response.status_code == 200:
                results = response.json().get('results', [])
                log_api_call(db_path, 'tmdb', title, 200, elapsed_ms, rate_limit_remaining)
                candidates = []
                for r in results[:5]:
                    candidates.append({
                        'id': r['id'],
                        'title': r['title'],
                        'year': r.get('release_date', '')[:4] if r.get('release_date') else None,
                        'popularity': r.get('popularity', 0),
                        'vote_average': r.get('vote_average', 0),
                    })
                return candidates
            else:
                log_api_call(db_path, 'tmdb', title, response.status_code, elapsed_ms,
                             error=f"HTTP {response.status_code}")
                logger.warning(f"TMDB search failed: {response.status_code} for '{title}'")
                return None
        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = e
            logger.warning(f"TMDB transient error for '{title}' "
                           f"(attempt {attempt+1}/3): {_redact(str(e))}")
            time.sleep(2 * (attempt + 1))
        except Exception as e:
            log_api_call(db_path, 'tmdb', title, None, None, error=str(e))
            logger.error(f"TMDB search error for '{title}': {_redact(str(e))}")
            return None

    log_api_call(db_path, 'tmdb', title, None, None, error=str(last_err))
    logger.error(f"TMDB search gave up after retries for '{title}': {_redact(str(last_err))}")
    return None


# Fields 04 adds to a candidate when scoring it. Stripped on the way back into
# the cache, which holds the raw TMDB shape so scoring stays re-derivable.
SCORED_FIELDS = ('confidence', 'title_similarity', 'year_score')


def warm_cache_from_staging(db_path):
    """Seed the search cache from candidates already stored on staging mentions.

    Every resolved mention kept the candidate list its search returned, so a
    database resolved before the cache existed can fill it from local storage
    instead of re-querying all ~481 titles.

    One caveat, deliberately accepted: when the yeared search came back empty,
    04 retried without the year and stored THOSE candidates. The backfill cannot
    tell the two apart afterwards, so it files them under the yeared key. The
    effect is that a rebuild reproduces exactly the resolution the database
    already has -- which is the point of the backfill -- but the entry is
    labelled with a query that did not produce it. Use --refresh to re-fetch.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    ensure_cache_table(cursor)

    rows = cursor.execute('''
        SELECT title_raw, title_normalized, year_parsed, candidate_json
        FROM staging_movie_mentions
        WHERE candidate_json IS NOT NULL AND candidate_json != ''
    ''').fetchall()

    seeded = skipped = 0
    for title_raw, title_norm, year, candidate_json in rows:
        search_title = (strip_annotations(title_raw) or title_norm or '').strip()
        if not search_title:
            skipped += 1
            continue
        try:
            scored = json.loads(candidate_json)
        except (ValueError, TypeError):
            skipped += 1
            continue
        if not isinstance(scored, list) or not scored:
            skipped += 1
            continue

        raw = [{k: v for k, v in c.items() if k not in SCORED_FIELDS}
               for c in scored]
        # Do not overwrite a real search result with a reconstructed one.
        if cache_get(cursor, search_title, year) is None:
            cache_put(cursor, search_title, year, raw)
            seeded += 1
        else:
            skipped += 1

    conn.commit()
    total = cursor.execute("SELECT COUNT(*) FROM tmdb_search_cache").fetchone()[0]
    conn.close()
    logger.info(f"✓ Warmed cache from staging: {seeded} seeded, {skipped} skipped "
                f"({total} entries total)")
    return seeded, skipped


def enrich_staging_mentions(db_path, limit=None, refresh=False):
    """Search, score, and resolve unresolved staging mentions.

    Searches go through the persistent cache unless `refresh` is set, so a
    staging rebuild re-scores the whole catalogue without touching the network.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    ensure_cache_table(cursor)
    conn.commit()

    query = '''
        SELECT staging_mention_id, title_raw, title_normalized, year_parsed
        FROM staging_movie_mentions
        WHERE resolution_method = 'unresolved'
    '''
    if limit:
        query += f' LIMIT {limit}'
    cursor.execute(query)
    mentions = cursor.fetchall()
    logger.info(f"Enriching {len(mentions)} unresolved mentions "
                f"(threshold={CONFIDENCE_THRESHOLD}, year_window=±{YEAR_WINDOW}, "
                f"cache={'bypassed' if refresh else 'on'})")

    auto, manual, nohit, failed = 0, 0, 0, 0
    from_cache, from_api = 0, 0

    for mention_id, title_raw, title_norm, year in mentions:
        # Search on the de-annotated title; fall back to the stored normalized form
        search_title = strip_annotations(title_raw) or title_norm or ''
        search_title = search_title.strip()
        candidates, networked = search_tmdb_cached(
            cursor, db_path, search_title, year, refresh)
        if networked:
            from_api += 1
            time.sleep(RATE_LIMIT_SLEEP)
        else:
            from_cache += 1

        # Fallback: a wrong source year filters out all results — retry without it
        # and let the scorer judge the title/year match.
        if not candidates and year:
            candidates, networked = search_tmdb_cached(
                cursor, db_path, search_title, None, refresh)
            if networked:
                from_api += 1
                time.sleep(RATE_LIMIT_SLEEP)
            else:
                from_cache += 1

        if candidates is None:
            # The search itself failed. Leave the mention untouched so a retry
            # picks it up; recording it as unmatchable would bury a transient
            # outage as a data problem.
            failed += 1
            continue

        if not candidates:
            nohit += 1
            cursor.execute('''
                UPDATE staging_movie_mentions
                SET requires_manual_review = 1,
                    resolution_notes = ?,
                    confidence_score = 0.0,
                    processed_at = CURRENT_TIMESTAMP
                WHERE staging_mention_id = ?
            ''', ("No TMDB matches found", mention_id))
            conn.commit()
            continue

        # Score every candidate, keep them sorted best-first for the review queue
        scored = []
        for c in candidates:
            conf, tsim, ysc = score_candidate(search_title, year, c['title'], c['year'])
            scored.append({**c, 'confidence': conf, 'title_similarity': tsim,
                           'year_score': ysc})
        scored.sort(key=lambda x: (x['confidence'], x['popularity']), reverse=True)
        best = scored[0]

        if best['confidence'] >= CONFIDENCE_THRESHOLD and best['title_similarity'] >= 0.6:
            auto += 1
            # Map to schema-allowed resolution methods based on how we matched
            if best['year_score'] == 1.0:
                method = 'exact_tmdb'
            elif best['year_score'] == 0.6:
                method = 'year_window_tmdb'
            else:
                method = 'fuzzy_tmdb'
            cursor.execute('''
                UPDATE staging_movie_mentions
                SET resolution_method = ?,
                    tmdb_id = ?,
                    confidence_score = ?,
                    candidate_json = ?,
                    requires_manual_review = 0,
                    resolution_notes = ?,
                    processed_at = CURRENT_TIMESTAMP
                WHERE staging_mention_id = ?
            ''', (method, best['id'], best['confidence'], json.dumps(scored),
                  f"Auto-matched '{best['title']}' ({best['year']}) "
                  f"conf={best['confidence']}", mention_id))
        else:
            manual += 1
            cursor.execute('''
                UPDATE staging_movie_mentions
                SET tmdb_id = ?,
                    confidence_score = ?,
                    candidate_json = ?,
                    requires_manual_review = 1,
                    resolution_notes = ?,
                    processed_at = CURRENT_TIMESTAMP
                WHERE staging_mention_id = ?
            ''', (best['id'], best['confidence'], json.dumps(scored),
                  f"Best candidate '{best['title']}' below threshold "
                  f"(conf={best['confidence']}, title_sim={best['title_similarity']})",
                  mention_id))

        conn.commit()

    conn.commit()
    conn.close()
    logger.info(f"✓ Enrichment complete: {auto} auto-resolved, "
                f"{manual} queued for review, {nohit} no TMDB hit"
                + (f", {failed} search failure(s) left for retry" if failed else ""))
    logger.info(f"  Searches: {from_cache} from cache, {from_api} from TMDB")
    return auto, manual, nohit


def main():
    ap = argparse.ArgumentParser(description="Resolve staging mentions against TMDB.")
    ap.add_argument("--refresh", action="store_true",
                    help="bypass the search cache and re-query TMDB for every mention")
    ap.add_argument("--limit", type=int, metavar="N",
                    help="process at most N mentions")
    ap.add_argument("--warm-cache", action="store_true",
                    help="seed the search cache from candidates already stored "
                         "on staging mentions, then exit (no API calls)")
    args = ap.parse_args()

    db_path = str(config.db_path())

    if not Path(db_path).exists():
        logger.error(f"{db_path} not found.")
        sys.exit(1)
    # A missing key is fatal only when something might actually need fetching.
    # With a warm cache a full rebuild resolves offline, and refusing to run
    # would make the pipeline depend on a credential it never uses.
    if not TMDB_API_KEY and args.refresh:
        logger.error("TMDB_API_KEY not set in config/.env — cannot run --refresh.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Phase 3: Enrich from TMDB")
    logger.info("=" * 60)

    if args.warm_cache:
        warm_cache_from_staging(db_path)
        logger.info("=" * 60)
        return

    enrich_staging_mentions(db_path, limit=args.limit, refresh=args.refresh)

    logger.info("=" * 60)


if __name__ == '__main__':
    config.setup_logging()
    main()
