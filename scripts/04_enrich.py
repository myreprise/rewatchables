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
"""

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
from dotenv import load_dotenv

# Load environment variables
load_dotenv('config/.env')

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

TMDB_API_KEY = os.getenv('TMDB_API_KEY')
TMDB_BASE_URL = "https://api.themoviedb.org/3"

CONFIDENCE_THRESHOLD = float(os.getenv('MATCH_CONFIDENCE_THRESHOLD', '0.85'))
YEAR_WINDOW = int(os.getenv('MATCH_YEAR_WINDOW', '2'))
RATE_LIMIT_SLEEP = 0.25  # ~4 req/sec, well under TMDB's 40 req / 10 sec


def normalize_title(title):
    """Lowercase, drop a leading 'the', strip punctuation, collapse whitespace."""
    if not title:
        return ''
    t = title.lower().strip()
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


def log_api_call(db_path, api_source, query, status_code, response_time_ms,
                 rate_limit_remaining=None, error=None):
    """Log API call for monitoring."""
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


def search_tmdb(db_path, title, year=None):
    """Search TMDB for a movie. Returns list of raw candidate dicts (top 5)."""
    if not TMDB_API_KEY:
        logger.warning("TMDB_API_KEY not set, skipping TMDB enrichment")
        return []

    url = f"{TMDB_BASE_URL}/search/movie"
    params = {'api_key': TMDB_API_KEY, 'query': title}
    if year:
        params['year'] = year

    try:
        start_time = time.time()
        response = requests.get(url, params=params, timeout=8)
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
            return []
    except requests.Timeout:
        log_api_call(db_path, 'tmdb', title, None, None, error="timeout")
        logger.warning(f"TMDB search timeout for '{title}'")
        return []
    except Exception as e:
        log_api_call(db_path, 'tmdb', title, None, None, error=str(e))
        logger.error(f"TMDB search error for '{title}': {e}")
        return []


def enrich_staging_mentions(db_path, limit=None):
    """Search, score, and resolve unresolved staging mentions."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

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
                f"(threshold={CONFIDENCE_THRESHOLD}, year_window=±{YEAR_WINDOW})")

    auto, manual, nohit = 0, 0, 0

    for mention_id, title_raw, title_norm, year in mentions:
        search_title = (title_raw or title_norm or '').strip()
        candidates = search_tmdb(db_path, search_title, year)

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
            time.sleep(RATE_LIMIT_SLEEP)
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
        time.sleep(RATE_LIMIT_SLEEP)

    conn.close()
    logger.info(f"✓ Enrichment complete: {auto} auto-resolved, "
                f"{manual} queued for review, {nohit} no TMDB hit")
    return auto, manual, nohit


def main():
    db_path = os.getenv('DB_PATH', 'rewatchables.db')

    if not Path(db_path).exists():
        logger.error(f"{db_path} not found.")
        sys.exit(1)
    if not TMDB_API_KEY:
        logger.error("TMDB_API_KEY not set in config/.env — cannot enrich.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Phase 3: Enrich from TMDB")
    logger.info("=" * 60)

    enrich_staging_mentions(db_path)

    logger.info("=" * 60)


if __name__ == '__main__':
    main()
