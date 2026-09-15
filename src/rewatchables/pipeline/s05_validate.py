#!/usr/bin/env python3
"""
Phase 5: Validate data quality
Runs pre/post-enrichment checks and produces a data quality report.
"""

import sys
import logging
import sqlite3
import uuid
from pathlib import Path

from rewatchables import config

logger = logging.getLogger(__name__)

def validate_pre_enrichment(db_path):
    """Pre-enrichment validation checks."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    issues = []
    
    # Check 1: Title not null
    cursor.execute('SELECT COUNT(*) FROM staging_movie_mentions WHERE title_normalized IS NULL')
    null_titles = cursor.fetchone()[0]
    if null_titles > 0:
        issues.append(f"WARNING: {null_titles} mentions with null normalized titles")
    
    # Check 2: Year in plausible range
    cursor.execute('SELECT COUNT(*) FROM staging_movie_mentions WHERE year_parsed < 1850 OR year_parsed > 2100')
    bad_years = cursor.fetchone()[0]
    if bad_years > 0:
        issues.append(f"WARNING: {bad_years} mentions with implausible years")
    
    # Check 3: Duplicate mentions within episode
    cursor.execute('''
        SELECT staging_episode_id, COUNT(*)
        FROM staging_movie_mentions
        GROUP BY staging_episode_id
        HAVING COUNT(*) > 1
    ''')
    duplicates = len(cursor.fetchall())
    if duplicates > 0:
        issues.append(f"INFO: {duplicates} episodes have multiple movie mentions (expected)")
    
    conn.close()
    return issues

def validate_post_enrichment(db_path):
    """Post-enrichment validation checks."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    issues = []
    
    # Check: Unresolved rate
    cursor.execute('SELECT COUNT(*) FROM staging_movie_mentions')
    total_mentions = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM staging_movie_mentions WHERE requires_manual_review = 1')
    manual_review_count = cursor.fetchone()[0]
    
    manual_review_pct = (manual_review_count / total_mentions * 100) if total_mentions > 0 else 0
    
    if manual_review_pct > 50:
        issues.append(f"WARNING: {manual_review_pct:.1f}% of mentions require manual review (high)")
    else:
        logger.info(f"Manual review rate: {manual_review_pct:.1f}%")
    
    conn.close()
    return issues

def generate_quality_report(db_path):
    """Generate comprehensive data quality report."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Compute metrics
    cursor.execute('SELECT COUNT(*) FROM staging_episodes')
    total_episodes = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM staging_movie_mentions')
    total_mentions = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM staging_movie_mentions WHERE requires_manual_review = 1')
    manual_review = cursor.fetchone()[0]
    
    resolved = total_mentions - manual_review

    quality_run_id = str(uuid.uuid4())
    resolution_rate_pct = (resolved / total_mentions * 100) if total_mentions > 0 else 0

    # Curated-zone metrics (present once Phase 4 build has run)
    cursor.execute('SELECT COUNT(*) FROM curated_movies')
    curated_movies = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM curated_movies WHERE revisit_count > 0')
    revisited_movies = cursor.fetchone()[0]
    new_movies = curated_movies - revisited_movies

    # Store quality results
    cursor.execute('''
        INSERT INTO data_quality_results
            (quality_run_id, total_episodes_processed, total_movie_mentions, resolved_mentions,
             unresolved_mentions, resolution_rate_pct, new_movies, revisited_movies, run_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (quality_run_id, total_episodes, total_mentions, resolved, manual_review,
          resolution_rate_pct, new_movies, revisited_movies, 'success'))

    conn.commit()
    conn.close()

    logger.info("=" * 60)
    logger.info("Data Quality Report")
    logger.info("=" * 60)
    logger.info(f"Total episodes processed: {total_episodes}")
    logger.info(f"Total movie mentions: {total_mentions}")
    logger.info(f"Resolved mentions: {resolved}")
    logger.info(f"Manual review queue: {manual_review}")
    logger.info(f"Resolution rate: {resolution_rate_pct:.1f}%")
    logger.info(f"Curated movies: {curated_movies} ({revisited_movies} revisited, {new_movies} single-feature)")
    logger.info("=" * 60)

def main():
    db_path = str(config.db_path())
    
    if not Path(db_path).exists():
        logger.error(f"{db_path} not found.")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("Phase 5: Validate data quality")
    logger.info("=" * 60)
    
    # Pre-enrichment checks
    logger.info("\nPre-enrichment validation:")
    pre_issues = validate_pre_enrichment(db_path)
    for issue in pre_issues:
        logger.info(f"  {issue}")
    
    # Post-enrichment checks
    logger.info("\nPost-enrichment validation:")
    post_issues = validate_post_enrichment(db_path)
    for issue in post_issues:
        logger.info(f"  {issue}")
    
    # Generate report
    generate_quality_report(db_path)

if __name__ == '__main__':
    config.setup_logging()
    main()
