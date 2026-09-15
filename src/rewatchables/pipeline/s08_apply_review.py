#!/usr/bin/env python3
"""
Phase 4: Apply manual-review decisions from CSV.

Reads the CSV produced by 07_export_review_queue.py and applies each decision:
  - approve : resolve the staging mention to the chosen TMDB id
              (resolution_method='manual_approved'), mark the queue row approved
  - reject  : mark the queue row rejected, leave the mention unresolved/excluded
  - skip/'' : leave for a later pass

If the chosen id is not among the stored candidates, its title/year are fetched
from TMDB so the curated build has canonical metadata. Finally the curated zone
is rebuilt (subprocess to 06_build_curated.py) so approvals appear and revisit
sequences are recomputed.
"""

import os
import sys
import csv
import json
import time
import logging
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
import requests

from rewatchables import config, http

logger = logging.getLogger(__name__)

CSV_PATH = config.DATA_DIR / 'manual_review.csv'
TMDB_API_KEY = os.getenv('TMDB_API_KEY')
TMDB_BASE_URL = "https://api.themoviedb.org/3"


def get_movie_details(tmdb_id):
    """Fetch minimal canonical metadata for a chosen TMDB id."""
    if not TMDB_API_KEY:
        return None
    try:
        r = http.get(f"{TMDB_BASE_URL}/movie/{tmdb_id}",
                     params={'api_key': TMDB_API_KEY}, timeout=10,
                     what=f"TMDB details for id {tmdb_id}", secret=TMDB_API_KEY)
        if r.status_code == 200:
            d = r.json()
            return {
                'id': d['id'],
                'title': d.get('title'),
                'year': (d.get('release_date') or '')[:4] or None,
                'popularity': d.get('popularity', 0),
                'vote_average': d.get('vote_average', 0),
                'confidence': 1.0,
                'title_similarity': None,
                'year_score': None,
            }
    except requests.RequestException as e:
        logger.warning(f"Could not fetch TMDB details for id {tmdb_id}: "
                       f"{http.redact(str(e), TMDB_API_KEY)}")
    return None


def _ensure_candidate(candidate_json, tmdb_id):
    """Return candidate_json guaranteed to contain the chosen id (fetch if needed)."""
    try:
        cands = json.loads(candidate_json) if candidate_json else []
    except (ValueError, TypeError):
        cands = []
    if any(c.get('id') == tmdb_id for c in cands):
        return json.dumps(cands)
    details = get_movie_details(tmdb_id)
    time.sleep(0.25)
    if details:
        cands.insert(0, details)
    return json.dumps(cands)


def apply_decisions(db_path, csv_path=CSV_PATH):
    if not Path(csv_path).exists():
        logger.error(f"{csv_path} not found. Run 07_export_review_queue.py first.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    now = datetime.utcnow().isoformat()
    approved = rejected = skipped = 0

    with open(csv_path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            action = (row.get('action') or '').strip().lower()
            mention_id = row.get('staging_mention_id')
            review_id = row.get('review_id')
            reviewer = (row.get('reviewer') or '').strip() or 'manual'
            notes = (row.get('notes') or '').strip()

            if action == 'approve':
                chosen = (row.get('chosen_tmdb_id') or '').strip()
                if not chosen.isdigit():
                    logger.warning(f"Skipping approve for {mention_id}: "
                                   f"invalid chosen_tmdb_id {chosen!r}")
                    continue
                tmdb_id = int(chosen)

                cursor.execute('SELECT candidate_json FROM staging_movie_mentions '
                               'WHERE staging_mention_id = ?', (mention_id,))
                cur = cursor.fetchone()
                candidate_json = _ensure_candidate(cur[0] if cur else None, tmdb_id)

                cursor.execute('''
                    UPDATE staging_movie_mentions
                    SET resolution_method = 'manual_approved',
                        tmdb_id = ?,
                        confidence_score = 1.0,
                        candidate_json = ?,
                        requires_manual_review = 0,
                        manual_review_approver = ?,
                        manual_review_timestamp = ?,
                        resolution_notes = ?,
                        processed_at = CURRENT_TIMESTAMP
                    WHERE staging_mention_id = ?
                ''', (tmdb_id, candidate_json, reviewer, now,
                      f"Manually approved tmdb_id={tmdb_id}. {notes}".strip(),
                      mention_id))
                cursor.execute('''
                    UPDATE manual_review_queue
                    SET queue_status = 'approved', reviewer_name = ?,
                        approval_notes = ?, resolved_at = ?
                    WHERE review_id = ?
                ''', (reviewer, notes, now, review_id))
                approved += 1

            elif action == 'reject':
                cursor.execute('''
                    UPDATE manual_review_queue
                    SET queue_status = 'rejected', reviewer_name = ?,
                        approval_notes = ?, resolved_at = ?
                    WHERE review_id = ?
                ''', (reviewer, notes or 'rejected by reviewer', now, review_id))
                rejected += 1
            else:
                skipped += 1

    conn.commit()
    conn.close()
    logger.info(f"✓ Applied: {approved} approved, {rejected} rejected, {skipped} skipped")
    return approved, rejected, skipped


def main():
    db_path = str(config.db_path())
    if not Path(db_path).exists():
        logger.error(f"{db_path} not found.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Phase 4: Apply manual-review decisions")
    logger.info("=" * 60)
    approved, rejected, skipped = apply_decisions(db_path)

    if approved:
        logger.info("Rebuilding curated zone to include approvals...")
        subprocess.run(
            [sys.executable, '-m', 'rewatchables.pipeline.s06_build_curated'],
            check=True, cwd=config.ROOT)
    logger.info("=" * 60)


if __name__ == '__main__':
    config.setup_logging()
    main()
