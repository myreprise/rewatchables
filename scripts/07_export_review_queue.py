#!/usr/bin/env python3
"""
Phase 4: Export the manual-review queue to CSV.

Takes every staging mention still flagged for manual review (and not already
approved/rejected in a prior pass), records it in the `manual_review_queue`
table as 'pending', and writes a human-editable CSV.

The reviewer fills two columns per row in the CSV:
  - action          : approve | reject | skip   (blank/skip = leave for later)
  - chosen_tmdb_id  : the correct TMDB id (usually copied from a candidate)
  - reviewer / notes: optional

Then run 08_apply_review.py to apply the decisions.
"""

import os
import sys
import csv
import json
import logging
import sqlite3
import uuid
from pathlib import Path
from dotenv import load_dotenv

load_dotenv('config/.env')

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

CSV_PATH = 'data/manual_review.csv'


def _readable_candidates(candidate_json):
    """One-line, reviewer-friendly rendering of the scored candidates."""
    if not candidate_json:
        return ''
    try:
        cands = json.loads(candidate_json)
    except (ValueError, TypeError):
        return ''
    parts = []
    for c in cands:
        parts.append(f"id={c.get('id')} | {c.get('title')} ({c.get('year')}) "
                     f"| conf={c.get('confidence')}")
    return '  ||  '.join(parts)


def _existing_decisions(csv_path):
    """Rows in the CSV that a human has already acted on.

    Returned verbatim so a re-export preserves them; without this the file is
    the only place some decisions live and an export would drop them.
    """
    path = Path(csv_path)
    if not path.exists():
        return []
    try:
        with open(path, newline='', encoding='utf-8') as f:
            return [r for r in csv.DictReader(f)
                    if (r.get('action') or '').strip()
                    and (r.get('staging_mention_id') or '').strip()]
    except (OSError, csv.Error) as e:
        logger.warning(f"Could not read existing {path}: {e}")
        return []


def export_queue(db_path, csv_path=CSV_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Refresh only the 'pending' rows; keep prior approved/rejected decisions.
    cursor.execute("DELETE FROM manual_review_queue WHERE queue_status = 'pending'")

    cursor.execute('''
        SELECT m.staging_mention_id, m.title_raw, m.year_parsed,
               m.director_raw, m.candidate_json, m.confidence_score
        FROM staging_movie_mentions m
        WHERE m.requires_manual_review = 1
          AND m.resolution_method = 'unresolved'
          AND m.staging_mention_id NOT IN (
              SELECT staging_mention_id FROM manual_review_queue
              WHERE queue_status IN ('approved', 'rejected')
          )
        ORDER BY m.confidence_score DESC
    ''')
    rows = cursor.fetchall()

    csv_rows = []
    for (mention_id, title_raw, year, director, candidate_json, conf) in rows:
        review_id = str(uuid.uuid4())
        cursor.execute('''
            INSERT INTO manual_review_queue
                (review_id, staging_mention_id, movie_title_raw, year_parsed,
                 director_raw, candidates, queue_status)
            VALUES (?, ?, ?, ?, ?, ?, 'pending')
        ''', (review_id, mention_id, title_raw, year, director,
              candidate_json or '[]'))
        csv_rows.append({
            'review_id': review_id,
            'staging_mention_id': mention_id,
            'title_raw': title_raw,
            'year_parsed': year,
            'best_confidence': conf,
            'candidates': _readable_candidates(candidate_json),
            'action': '',          # reviewer fills: approve | reject | skip
            'chosen_tmdb_id': '',  # reviewer fills
            'reviewer': '',
            'notes': '',
        })

    conn.commit()
    conn.close()

    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ['review_id', 'staging_mention_id', 'title_raw', 'year_parsed',
                  'best_confidence', 'candidates', 'action', 'chosen_tmdb_id',
                  'reviewer', 'notes']

    # MERGE, never clobber. This file is the durable record of human decisions
    # and 08_apply_review replays it after a staging rebuild. Overwriting it
    # wholesale erased every prior decision whenever nothing was pending --
    # which is the normal state once review is caught up.
    kept = _existing_decisions(csv_path)
    pending = [r for r in csv_rows
               if r['staging_mention_id'] not in
               {k['staging_mention_id'] for k in kept}]

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept + pending)

    logger.info(f"✓ Exported {len(pending)} new item(s) to {csv_path} "
                f"({len(kept)} existing decision(s) preserved)")
    return len(pending)


def main():
    db_path = os.getenv('DB_PATH', 'rewatchables.db')
    if not Path(db_path).exists():
        logger.error(f"{db_path} not found.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Phase 4: Export manual-review queue")
    logger.info("=" * 60)
    n = export_queue(db_path)
    logger.info(f"Edit {CSV_PATH} (set action + chosen_tmdb_id), "
                f"then run 08_apply_review.py")
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
