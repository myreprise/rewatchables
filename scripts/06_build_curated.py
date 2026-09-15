#!/usr/bin/env python3
"""
Phase 4: Build curated zone with revisit detection.

Promotes auto-resolved staging mentions (requires_manual_review = 0) into the
curated zone:
  - curated_movies          one canonical row per tmdb_id
  - curated_episode_movies  one row per episode mention (revisits allowed)
  - curated_audits          one provenance row per movie created

Revisit detection: for each canonical movie, its episode links are ordered by
(episode_date, episode_number) and sequenced over DISTINCT episode numbers -- the
Nth distinct episode gets revisit_sequence = N, and is_revisit is true for N > 1.

Sequencing on distinct numbers rather than rows matters: the 1999 series was
published twice, once on Luminary and again on the Spotify feed years later, so
ten films carry two rows bearing the SAME episode number. Those are one episode
republished, not a rewatch. Both rows are kept (no airing is discarded) but they
share revisit_sequence = 1, and total_episodes_featured counts distinct episodes.

The source sheet's curated `revisited` column arrives via staging as
revisited_flag and is stored on curated_movies unchanged -- that is the value the
app displays. revisit_count is derived independently, and the two are compared at
the end of the build: any film where they disagree is logged as a divergence.

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


def _episode_key(mention):
    """Identity of the episode a mention belongs to, for revisit sequencing.

    Episode number, because a republished episode reuses it and must not read as
    a second airing. Rows with no episode number fall back to their own mention
    id so they cannot be silently merged with each other.
    """
    ep_num = mention.get('episode_number')
    if ep_num is None or str(ep_num).strip() == '':
        return ('mention', mention['mention_id'])
    return ('episode', str(ep_num).strip())


def _ensure_column(cursor, table, column, decl="TEXT"):
    """Add `column` to `table` if it is missing (no-op when already present).

    CREATE TABLE IF NOT EXISTS cannot widen an existing table, so databases
    created before a column was introduced need an explicit ALTER.
    """
    existing = {r[1] for r in cursor.execute(f"PRAGMA table_info({table})")}
    if existing and column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        logger.info(f"Migrated {table}: added {column} column")


def build_curated(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Databases built before the curated `revisited` flag existed
    _ensure_column(cursor, 'curated_movies', 'revisited_flag', 'INTEGER')
    _ensure_column(cursor, 'staging_movie_mentions', 'revisited_flag', 'INTEGER')

    # Idempotent rebuild of derived curated data
    cursor.execute('DELETE FROM curated_audits')
    cursor.execute('DELETE FROM curated_episode_movies')
    cursor.execute('DELETE FROM curated_movies')

    # Pull every auto-resolved mention with its episode context
    cursor.execute('''
        SELECT m.staging_mention_id, m.staging_episode_id, m.tmdb_id,
               m.confidence_score, m.director_normalized, m.candidate_json,
               m.mention_order, m.revisited_flag,
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
         candidate_json, mention_order, revisited_flag,
         ep_num, ep_date, ep_title) = r
        cand = _best_candidate(candidate_json, tmdb_id)
        by_movie[tmdb_id].append({
            'mention_id': mention_id,
            'staging_episode_id': staging_episode_id,
            'confidence': confidence or 0.0,
            'director': director,
            'mention_order': mention_order or 1,
            'revisited_flag': revisited_flag,
            'episode_number': ep_num,
            'episode_date': ep_date,
            'episode_title': ep_title,
            'cand': cand,
        })

    now = datetime.utcnow().isoformat()
    movie_id_by_tmdb = {}
    movie_count = link_count = revisit_links = 0
    derived_revisited = 0
    divergences = []

    for tmdb_id, mentions in by_movie.items():
        # Chronological order drives revisit sequencing
        mentions.sort(key=lambda x: (x['episode_date'] or '', x['episode_number'] or 0))

        # Sequence over DISTINCT episode numbers, so a republished episode does
        # not read as a rewatch. A row with no episode number cannot be matched
        # to another, so it keys on its own mention id and stays distinct.
        seq_by_episode = {}
        for m in mentions:
            key = _episode_key(m)
            if key not in seq_by_episode:
                seq_by_episode[key] = len(seq_by_episode) + 1
        distinct_episodes = len(seq_by_episode)

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

        # Curated ground truth from the sheet. All mentions of a film carry the
        # same value; max() picks it up while tolerating a NULL on some rows.
        flags = [m['revisited_flag'] for m in mentions
                 if m['revisited_flag'] is not None]
        revisited_flag = max(flags) if flags else None

        cursor.execute('''
            INSERT INTO curated_movies
                (movie_id, tmdb_id, title, year, directors,
                 rating_tmdb, popularity_tmdb, data_sources, enriched_at,
                 first_episode_date, last_episode_date,
                 total_episodes_featured, revisit_count, revisited_flag,
                 canonical_key_confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            movie_id, tmdb_id, title, year,
            json.dumps(directors) if directors else None,
            cand.get('vote_average'), cand.get('popularity'),
            json.dumps({'tmdb': now}), now,
            min(dates) if dates else None,
            max(dates) if dates else None,
            distinct_episodes, distinct_episodes - 1, revisited_flag,
            confidence_band,
        ))
        movie_count += 1
        if distinct_episodes > 1:
            derived_revisited += 1

        # Curated flag vs derived count: independent sources for the same fact,
        # so a disagreement means the sheet or the episode numbering moved.
        if revisited_flag is not None and revisited_flag != int(distinct_episodes > 1):
            divergences.append(
                f"{title} ({year}): revisited={revisited_flag} but "
                f"{distinct_episodes} distinct episode(s)"
            )

        # Episode-movie links with revisit sequencing. Every airing is kept,
        # including a republication, but rows sharing an episode number share a
        # sequence number and so are not counted as revisits.
        for m in mentions:
            seq = seq_by_episode[_episode_key(m)]
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

    flagged = sum(1 for ms in by_movie.values()
                  if any(m['revisited_flag'] == 1 for m in ms))
    logger.info(f"✓ Curated build complete: {movie_count} canonical movies, "
                f"{link_count} episode links, {revisit_links} revisit links")
    logger.info(f"  Revisited films: {flagged} flagged in source, "
                f"{derived_revisited} derived from episode numbering")

    if divergences:
        logger.warning(
            f"{len(divergences)} film(s) where the source `revisited` flag "
            f"disagrees with the derived episode count:")
        for d in divergences:
            logger.warning(f"  - {d}")

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
