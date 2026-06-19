#!/usr/bin/env python3
"""
Phase 4: Build curated zone with revisit detection.

Promotes auto-resolved staging mentions (requires_manual_review = 0) into the
curated zone:
  - curated_movies          one canonical row per tmdb_id
  - curated_episode_movies  one row per episode mention (revisits allowed)
  - curated_audits          one provenance row per movie created

Revisit detection: for each canonical movie, its episode links are ordered by
(episode_date, episode_number); the Nth chronological appearance gets
revisit_sequence = N, and is_revisit is true for N > 1.

Idempotent: the curated zone is fully derived from staging, so it is cleared and
rebuilt on every run. (Manual-review items are not promoted here — they enter via
the Phase 4 approval workflow once reviewed.)
"""

import os
import sys
import json
import logging
import sqlite3
import uuid
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv('config/.env')

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)


def _best_candidate(candidate_json, tmdb_id):
    """Return the stored candidate matching tmdb_id (fallback: first/best)."""
    if not candidate_json:
        return {}
    try:
        cands = json.loads(candidate_json)
    except (ValueError, TypeError):
        return {}
    for c in cands:
        if c.get('id') == tmdb_id:
            return c
    return cands[0] if cands else {}


def build_curated(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Idempotent rebuild of derived curated data
    cursor.execute('DELETE FROM curated_audits')
    cursor.execute('DELETE FROM curated_episode_movies')
    cursor.execute('DELETE FROM curated_movies')

    # Pull every auto-resolved mention with its episode context
    cursor.execute('''
        SELECT m.staging_mention_id, m.staging_episode_id, m.tmdb_id,
               m.confidence_score, m.director_normalized, m.candidate_json,
               m.mention_order,
               e.episode_number, e.episode_date, e.episode_title
        FROM staging_movie_mentions m
        JOIN staging_episodes e ON e.staging_episode_id = m.staging_episode_id
        WHERE m.requires_manual_review = 0 AND m.tmdb_id IS NOT NULL
    ''')
    rows = cursor.fetchall()
    logger.info(f"Promoting {len(rows)} resolved mentions to curated zone")

    # Group mentions by canonical movie (tmdb_id)
    by_movie = defaultdict(list)
    for r in rows:
        (mention_id, staging_episode_id, tmdb_id, confidence, director,
         candidate_json, mention_order, ep_num, ep_date, ep_title) = r
        cand = _best_candidate(candidate_json, tmdb_id)
        by_movie[tmdb_id].append({
            'staging_episode_id': staging_episode_id,
            'confidence': confidence or 0.0,
            'director': director,
            'mention_order': mention_order or 1,
            'episode_number': ep_num,
            'episode_date': ep_date,
            'episode_title': ep_title,
            'cand': cand,
        })

    now = datetime.utcnow().isoformat()
    movie_id_by_tmdb = {}
    movie_count = link_count = revisit_links = 0

    for tmdb_id, mentions in by_movie.items():
        # Chronological order drives revisit sequencing
        mentions.sort(key=lambda x: (x['episode_date'] or '', x['episode_number'] or 0))

        cand = mentions[0]['cand']
        title = cand.get('title') or mentions[0]['episode_title']
        year = int(cand['year']) if cand.get('year') else None
        directors = sorted({m['director'] for m in mentions if m['director']})
        dates = [m['episode_date'] for m in mentions if m['episode_date']]
        min_conf = min(m['confidence'] for m in mentions)
        confidence_band = ('high' if min_conf >= 0.85
                           else 'medium' if min_conf >= 0.6 else 'low')

        movie_id = str(uuid.uuid4())
        movie_id_by_tmdb[tmdb_id] = movie_id

        cursor.execute('''
            INSERT INTO curated_movies
                (movie_id, tmdb_id, title, year, directors,
                 rating_tmdb, popularity_tmdb, data_sources, enriched_at,
                 first_episode_date, last_episode_date,
                 total_episodes_featured, revisit_count, canonical_key_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            movie_id, tmdb_id, title, year,
            json.dumps(directors) if directors else None,
            cand.get('vote_average'), cand.get('popularity'),
            json.dumps({'tmdb': now}), now,
            min(dates) if dates else None,
            max(dates) if dates else None,
            len(mentions), len(mentions) - 1, confidence_band,
        ))
        movie_count += 1

        # Episode-movie links with revisit sequencing
        for seq, m in enumerate(mentions, start=1):
            is_revisit = seq > 1
            cursor.execute('''
                INSERT INTO curated_episode_movies
                    (episode_movie_id, staging_episode_id, movie_id,
                     episode_number, episode_date, episode_title,
                     mention_order, mention_type,
                     is_revisit, revisit_sequence, revisit_type, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                str(uuid.uuid4()), m['staging_episode_id'], movie_id,
                m['episode_number'], m['episode_date'], m['episode_title'],
                m['mention_order'], 'central_topic',
                1 if is_revisit else 0, seq,
                'regular_revisit' if is_revisit else None,
                'enrichment_pipeline',
            ))
            link_count += 1
            if is_revisit:
                revisit_links += 1

        # Provenance audit row for the canonical movie
        cursor.execute('''
            INSERT INTO curated_audits
                (audit_id, movie_id, field_changed, old_value, new_value,
                 enriched_from, enriched_at, enriched_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (str(uuid.uuid4()), movie_id, 'created', None,
              f"{title} ({year})", 'tmdb', now, 'automation_v1'))

    conn.commit()
    conn.close()
    logger.info(f"✓ Curated build complete: {movie_count} canonical movies, "
                f"{link_count} episode links, {revisit_links} revisit links")
    return movie_count, link_count, revisit_links


def main():
    db_path = os.getenv('DB_PATH', 'rewatchables.db')
    if not Path(db_path).exists():
        logger.error(f"{db_path} not found.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Phase 4: Build curated zone with revisit detection")
    logger.info("=" * 60)
    build_curated(db_path)
    logger.info("=" * 60)


if __name__ == '__main__':
    main()
