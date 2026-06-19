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

def normalize_title(title):
    """
    Normalize movie title for matching.
    - Convert to lowercase
    - Remove leading "The"
    - Remove special characters except &, -, '
    """
    if not title:
        return None
    
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
    
    # Fetch raw episodes that haven't been staged yet
    query = 'SELECT raw_episode_id, ep, date, title, year, director FROM raw_episodes'
    if limit:
        query += f' LIMIT {limit}'
    
    cursor.execute(query)
    raw_rows = cursor.fetchall()
    logger.info(f"Processing {len(raw_rows)} raw episodes into staging")
    
    staged_count = 0
    for raw_episode_id, ep, date, ep_title, year_raw, director_raw in raw_rows:
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
            
            staged_count += 1
        except Exception as e:
            logger.warning(f"Failed to process raw_episode_id {raw_episode_id}: {e}")
            continue
    
    conn.commit()
    conn.close()
    
    logger.info(f"✓ Staged {staged_count} episodes into staging zone")
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
