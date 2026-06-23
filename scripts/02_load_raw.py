#!/usr/bin/env python3
"""
Phase 2: Load raw zone from master.xlsx
Ingests the xlsx file into the raw_zone tables with immutable snapshots and fingerprints.
"""

import os
import sys
import logging
import hashlib
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

# Load environment variables
load_dotenv('config/.env')

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

def init_database(db_path):
    """Initialize SQLite database with schema files."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    schema_dir = Path(__file__).parent.parent / 'sql' / 'schemas'
    
    # Load and execute schema files in order
    for schema_file in ['raw_zone.sql', 'staging_zone.sql', 'curated_zone.sql']:
        schema_path = schema_dir / schema_file
        if schema_path.exists():
            logger.info(f"Loading schema: {schema_file}")
            with open(schema_path, 'r') as f:
                cursor.executescript(f.read())
    
    conn.commit()
    conn.close()
    logger.info(f"Database initialized at {db_path}")

def load_xlsx_to_raw(xlsx_path, db_path):
    """Load master.xlsx into raw_episodes table."""
    # Initialize DB if needed
    if not Path(db_path).exists():
        logger.info(f"Creating database: {db_path}")
        init_database(db_path)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Read xlsx (use first sheet, whatever its name)
    logger.info(f"Reading {xlsx_path}")
    df = pd.read_excel(xlsx_path)
    
    # Sanitize column names (replace spaces with underscores)
    df.columns = [col.replace(' ', '_') for col in df.columns]
    
    # Convert all data to strings for raw zone (preserve everything as-is)
    df = df.astype(str)
    
    logger.info(f"Loaded {len(df)} rows, {len(df.columns)} columns")
    logger.info(f"Columns: {', '.join(df.columns[:10])}")
    
    # Create ingest run record
    ingest_run_id = str(uuid.uuid4())
    sync_timestamp = datetime.utcnow().isoformat()
    
    cursor.execute('''
        INSERT INTO raw_ingest_runs (ingest_run_id, source_url, sync_timestamp, rows_ingested, sync_status)
        VALUES (?, ?, ?, ?, ?)
    ''', (ingest_run_id, 'data/master.xlsx', sync_timestamp, len(df), 'success'))
    
    # Validate xlsx columns against schema before inserting anything
    schema_cols = {r[1] for r in cursor.execute('PRAGMA table_info(raw_episodes)')}
    unknown = [c for c in df.columns if c not in schema_cols]
    if unknown:
        logger.error(f"xlsx has columns not in raw_episodes schema: {unknown}")
        logger.error("Add them to sql/schemas/raw_zone.sql and run: "
                     "ALTER TABLE raw_episodes ADD COLUMN <name> TEXT")
        conn.close()
        sys.exit(1)

    # Only insert xlsx columns present in the schema (future-proof for partial adds)
    insert_cols = [c for c in df.columns if c in schema_cols]

    inserted = 0
    for idx, row in df.iterrows():
        raw_episode_id = str(uuid.uuid4())
        row_dict = row.to_dict()

        # Compute fingerprint over ALL source values (including any future cols)
        row_str = '|'.join([str(v) for v in row.values])
        source_hash = hashlib.md5(row_str.encode()).hexdigest()

        values = [raw_episode_id, ingest_run_id]
        for col in insert_cols:
            values.append(row_dict.get(col))
        values.extend([source_hash, idx, sync_timestamp])

        cols = ['raw_episode_id', 'ingest_run_id'] + insert_cols + ['source_hash', 'gs_row_number', 'ingested_at']
        placeholders = ', '.join(['?'] * len(values))

        try:
            cursor.execute(f'''
                INSERT INTO raw_episodes ({', '.join(cols)})
                VALUES ({placeholders})
            ''', values)
            inserted += 1
        except sqlite3.IntegrityError as e:
            logger.warning(f"Row {idx}: {e} (likely duplicate, skipping)")
            continue

    conn.commit()
    conn.close()
    logger.info(f"✓ Loaded {inserted}/{len(df)} rows into raw_episodes")

def main():
    xlsx_path = 'data/master.xlsx'
    db_path = os.getenv('DB_PATH', 'rewatchables.db')
    
    if not Path(xlsx_path).exists():
        logger.error(f"{xlsx_path} not found. Run 01_sync_sheets.py first.")
        sys.exit(1)
    
    logger.info("=" * 60)
    logger.info("Phase 2: Load raw zone from master.xlsx")
    logger.info("=" * 60)
    
    load_xlsx_to_raw(xlsx_path, db_path)
    
    logger.info("=" * 60)

if __name__ == '__main__':
    main()
