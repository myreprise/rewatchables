#!/usr/bin/env python3
"""
Phase 3: Normalize and resolve movie keys
Parses episodes from raw zone into staging zone with title/year normalization 
and initial API matching attempts.
"""

import os
import sys
import logging
import sqlite3
import uuid
import re
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv('config/.env')

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
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
        return title
    t = str(title)
    # Drop parenthetical / bracketed asides (the bulk of the noise)
    t = re.sub(r'\([^)]*\)', ' ', t)
    t = re.sub(r'\[[^\]]*\]', ' ', t)
    # Drop quoted asides (straight and curly quotes)
    t = re.sub(r'[\"“”][^\"“”]*[\"“”]', ' ', t)
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
    
    # Try to extract 4-digit year
    match = re.search(r'\d{4}', year_str)
    if match:
        year = int(match.group())
        # Sanity check
        if 1850 <= year <= 2100:
            return year
    
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

    # Idempotent rebuild: clear staging so re-runs don't duplicate.
    # Safe while the curated zone is empty (nothing references these rows yet).
    cursor.execute('DELETE FROM staging_movie_mentions')
    cursor.execute('DELETE FROM staging_episodes')

    # Fetch raw episodes
    query = 'SELECT raw_episode_id, ep, date, title, year, director, is_film FROM raw_episodes'
    if limit:
        query += f' LIMIT {limit}'

    cursor.execute(query)
    raw_rows = cursor.fetchall()
    logger.info(f"Processing {len(raw_rows)} raw episodes into staging")

    staged_count = 0
    mention_count = 0
    skipped_nonfilm = 0
    for raw_episode_id, ep, date, ep_title, year_raw, director_raw, is_film in raw_rows:
        try:
            # Create staging episode
            staging_episode_id = str(uuid.uuid4())
            
            cursor.execute('''
                INSERT INTO staging_episodes 
                    (staging_episode_id, raw_episode_id, episode_number, episode_title, episode_date, validation_status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                staging_episode_id,
                raw_episode_id,
                ep,  # Assume 'ep' is episode number
                ep_title,
                date,
                'pending'
            ))
            
            staged_count += 1

            # Only films get a movie mention; non-film episodes (mailbags,
            # selection shows) are staged but not sent to the resolver.
            if str(is_film).strip() not in ('1', '1.0', 'True', 'true'):
                skipped_nonfilm += 1
                continue

            # Create staging movie mention
            staging_mention_id = str(uuid.uuid4())
            title_normalized = normalize_title(ep_title)  # Using episode title as movie title for now
            year_parsed = parse_year(year_raw)
            director_normalized = normalize_director(director_raw)

            cursor.execute('''
                INSERT INTO staging_movie_mentions
                    (staging_mention_id, staging_episode_id, raw_episode_id, mention_order,
                     title_raw, title_normalized, year_raw, year_parsed, director_raw, director_normalized,
                     resolution_method, confidence_score, requires_manual_review)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    db_path = os.getenv('DB_PATH', 'rewatchables.db')
    
    if not Path(db_path).exists():
        logger.error(f"{db_path} not found. Run 02_load_raw.py first.")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("Phase 3: Normalize and resolve movie keys")
    logger.info("=" * 60)
    
    process_raw_to_staging(db_path)
    
    logger.info("=" * 60)

if __name__ == '__main__':
    main()
