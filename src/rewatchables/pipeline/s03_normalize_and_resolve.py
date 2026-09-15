#!/usr/bin/env python3
"""
Phase 3: Normalize and resolve movie keys
Parses episodes from raw zone into staging zone with title/year normalization
and initial API matching attempts.

STAGING IDS ARE DETERMINISTIC.

Staging is cleared and rebuilt on every run. When these ids were uuid4 they
changed on each rebuild, which silently detached everything keyed to them:
manual resolutions in staging_movie_mentions, data/manual_review.csv, and the
approved rows in manual_review_queue. A rebuild therefore discarded human work
and let 04 re-derive the wrong match it had corrected.

They are now uuid5 over a business key -- episode number, air date, and episode
title -- so the same source row always yields the same id and manual decisions
survive a rebuild.

Why that key: `ep` alone is not unique (the podcast reuses an episode number
when it revisits a film, e.g. American Pie is ep 68 in both 2019 and 2023), and
source_hash is too brittle -- it covers every column, so editing an unrelated
field like a Rotten Tomatoes score would break the link. ep+date+title is
unique across all 479 rows and stable against edits elsewhere in the row.
"""

import sys
import logging
import sqlite3
import re
from pathlib import Path

from rewatchables import config
# The business key and the deterministic ids derived from it are shared with
# 02_load_raw, which upserts on the same key. Re-exported here so callers and
# tests can keep importing them from this module.
from rewatchables.keys import (  # noqa: F401  (re-exported)
    STAGING_NAMESPACE,
    episode_business_key,
    make_episode_id,
    make_mention_id,
    normalize_date,
)

logger = logging.getLogger(__name__)

def strip_annotations(title):
    """
    Remove podcast-specific annotations that break title matching while keeping
    the underlying film title intact, e.g.:
      'Forrest Gump (Live from D.C.)' -> 'Forrest Gump'
      'Batman (1989)'                 -> 'Batman'
      'Boogie Nights (Part 1 and 2)'  -> 'Boogie Nights'
      'Heat ("The Three-Heat")'       -> 'Heat'
    """
    if not title:
        return ''
    t = str(title)
    # Drop quoted asides first (before parens, so nested cases like
    # '("A Few Good (Re)Men")' are removed as a unit)
    t = re.sub(r'[\"""][^\"""]*[\"""]', ' ', t)
    # Drop parenthetical / bracketed asides
    t = re.sub(r'\([^)]*\)', ' ', t)
    t = re.sub(r'\[[^\]]*\]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()

def normalize_title(title):
    """
    Normalize movie title for matching.
    - Strip podcast annotations (parentheticals, quoted asides)
    - Convert to lowercase
    - Remove leading "The"
    - Remove special characters except &, -, '
    """
    if not title:
        return None

    title = strip_annotations(title)
    title = str(title).lower().strip()

    # Remove leading "The"
    if title.startswith('the '):
        title = title[4:]

    # Remove most special chars, keep &, -, '
    title = re.sub(r"[^a-z0-9\s&\-']", '', title)

    return title.strip()

def parse_year(year_raw):
    """Extract year as integer."""
    if not year_raw:
        return None

    year_str = str(year_raw).strip()

    match = re.search(r'\d{4}', year_str)
    if match:
        year = int(match.group())
        if 1850 <= year <= 2100:
            return year

    return None


def parse_revisited(revisited_raw):
    """Parse the sheet's `revisited` flag to 1/0, or None when absent.

    The raw zone stores every value as text, so a 1 arrives as '1', '1.0' or
    'True' depending on how pandas typed the column. Anything unrecognised
    (including the literal 'nan' an empty cell becomes) is None rather than 0,
    so "not flagged" stays distinguishable from "explicitly not a revisit".
    """
    if revisited_raw is None:
        return None
    s = str(revisited_raw).strip().lower()
    if s in ('1', '1.0', 'true', 'yes', 'y'):
        return 1
    if s in ('0', '0.0', 'false', 'no', 'n'):
        return 0
    return None


def normalize_director(director_raw):
    """Normalize director name."""
    if not director_raw:
        return None
    return str(director_raw).strip()

def process_raw_to_staging(db_path, limit=None):
    """
    Transform raw_episodes into staging_episodes and staging_movie_mentions.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Databases built before the curated `revisited` flag existed.
    # CREATE TABLE IF NOT EXISTS cannot widen an existing table.
    existing = {r[1] for r in cursor.execute('PRAGMA table_info(staging_movie_mentions)')}
    if existing and 'revisited_flag' not in existing:
        cursor.execute('ALTER TABLE staging_movie_mentions ADD COLUMN revisited_flag INTEGER')
        logger.info('Migrated staging_movie_mentions: added revisited_flag column')

    # Idempotent rebuild: clear staging so re-runs don't duplicate.
    # Safe while the curated zone is empty (nothing references these rows yet).
    cursor.execute('DELETE FROM staging_movie_mentions')
    cursor.execute('DELETE FROM staging_episodes')

    # Read the view, not the table. raw_episodes is append-only version history
    # -- an edited airing keeps its old row alongside the new one -- so selecting
    # from it directly would stage both versions as separate episodes.
    #
    # This used to re-derive the "which rows are current" filter here, with a
    # comment on both copies warning that they had to be changed together. The
    # view owns that definition now, so the raw and staging zones cannot drift.
    query = '''
        SELECT raw_episode_id, ep, date, title, year, director, is_film,
               revisited
        FROM raw_episodes_current
    '''
    if limit:
        query += f' LIMIT {limit}'

    cursor.execute(query)
    raw_rows = cursor.fetchall()
    logger.info(f"Processing {len(raw_rows)} raw episodes into staging")

    staged_count = 0
    mention_count = 0
    skipped_nonfilm = 0
    for (raw_episode_id, ep, date, ep_title, year_raw, director_raw, is_film,
         revisited_raw) in raw_rows:
        try:
            # Deterministic: the same source row always yields the same id,
            # so manual review decisions survive a staging rebuild.
            staging_episode_id = make_episode_id(ep, date, ep_title)
            
            cursor.execute('''
                INSERT INTO staging_episodes
                    (staging_episode_id, raw_episode_id, episode_number, episode_title, episode_date, validation_status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                staging_episode_id,
                raw_episode_id,
                ep,
                ep_title,
                normalize_date(date),
                'pending'
            ))
            
            staged_count += 1

            # Only films get a movie mention; non-film episodes (mailbags,
            # selection shows) are staged but not sent to the resolver.
            if str(is_film).strip() not in ('1', '1.0', 'True', 'true'):
                skipped_nonfilm += 1
                continue

            # Deterministic; see make_mention_id.
            staging_mention_id = make_mention_id(ep, date, ep_title, 1)
            title_normalized = normalize_title(ep_title)  # Using episode title as movie title for now
            year_parsed = parse_year(year_raw)
            director_normalized = normalize_director(director_raw)

            cursor.execute('''
                INSERT INTO staging_movie_mentions
                    (staging_mention_id, staging_episode_id, raw_episode_id, mention_order,
                     title_raw, title_normalized, year_raw, year_parsed, director_raw, director_normalized,
                     revisited_flag, resolution_method, confidence_score, requires_manual_review)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                staging_mention_id,
                staging_episode_id,
                raw_episode_id,
                1,  # Assuming 1 movie mention per episode row for now
                ep_title,
                title_normalized,
                year_raw,
                year_parsed,
                director_raw,
                director_normalized,
                parse_revisited(revisited_raw),
                'unresolved',
                0.0,
                1  # Mark all for manual review in this phase
            ))

            mention_count += 1
        except Exception as e:
            logger.warning(f"Failed to process raw_episode_id {raw_episode_id}: {e}")
            continue

    conn.commit()
    conn.close()

    logger.info(f"✓ Staged {staged_count} episodes "
                f"({mention_count} film mentions, {skipped_nonfilm} non-film skipped)")
    return staged_count

def main():
    db_path = str(config.db_path())
    
    if not Path(db_path).exists():
        logger.error(f"{db_path} not found. Run 02_load_raw.py first.")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("Phase 3: Normalize and resolve movie keys")
    logger.info("=" * 60)
    
    process_raw_to_staging(db_path)
    
    logger.info("=" * 60)

if __name__ == '__main__':
    config.setup_logging()
    main()
