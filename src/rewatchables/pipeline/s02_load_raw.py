#!/usr/bin/env python3
"""
Phase 2: Load raw zone from data/episodes.csv

Ingests the episode list into raw_episodes as append-only version history.

THE FILE THIS READS IS A CSV, READ VERBATIM -- AND GENERATED.

Step 01 renders it from data/episodes.xlsx, the workbook that gets edited, and
checks every cell on the way. The CSV stays tracked (see the !data/episodes.csv
line in .gitignore) because git can diff it: a workbook diffs as "Bin 71028 ->
76009 bytes", the CSV beside it as the one row that changed. Do not edit it,
and never open it in Excel -- on this machine a save re-encodes it as GBK and
turns '3/4' into a date. Step 01 regenerates it on every run anyway.

It is read with dtype=str and keep_default_na=False, so pandas infers nothing.
pandas' xlsx path typed each column by guessing and then stringified the
result, which is how '1995.0' and the literal string 'nan' once reached the raw
zone. An empty field is '' and every value is the text the file holds.

THE LOAD IS AN UPSERT, NOT A SNAPSHOT.

Each source row is identified by its business key (ep|ISO date|title, see
scripts/_keys.py) and fingerprinted by source_hash over every column. On load a
row is one of three things:

  unchanged  key and hash both already present -> nothing inserted, the existing
             row's last_seen provenance advances to this run
  edited     key present, hash different       -> a NEW version row is inserted;
             the previous version stays as history but stops being current
  new        key absent                        -> inserted

Before this, every load re-inserted the entire sheet: six loads of ~489 rows
left 2,913 rows in the table for 489 real airings, and the count grew by the
full sheet size every time. The zone is still immutable in the sense that
matters -- no ingested VALUE is ever rewritten. Only the last_seen provenance
columns are updated in place, and only to record that a row is still there.

A row deleted from the sheet needs no special handling: nothing re-sees it, so
its last_seen stays behind and raw_episodes_current stops returning it.
"""

import sys
import logging
import hashlib
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
import pandas as pd

from rewatchables import config
from rewatchables.keys import episode_business_key

logger = logging.getLogger(__name__)

def init_database(db_path):
    """Initialize SQLite database with schema files."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    schema_dir = config.SCHEMA_DIR
    
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

def _ensure_column(cursor, table, column, decl="TEXT"):
    """Add `column` to `table` if it is missing (no-op when already present).

    CREATE TABLE IF NOT EXISTS cannot widen an existing table, so databases
    created before a column was introduced need an explicit ALTER.
    """
    existing = {r[1] for r in cursor.execute(f"PRAGMA table_info({table})")}
    if existing and column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        logger.info(f"Migrated {table}: added {column} column")
        return True
    return False


def migrate_raw_columns(cursor):
    """Widen raw_episodes for columns added after the database was built.

    A new source column would otherwise trip the schema guard below and abort
    the load. Returns whether anything was added, so the caller can replay
    raw_zone.sql once it is safe to -- see replay_schema.
    """
    added = _ensure_column(cursor, 'raw_episodes', 'revisited')

    # Columns the upsert needs. A database built before it has none of them, and
    # every row reads as "never seen" until migrate_compact_raw_zone.py has run.
    for column in ('episode_key', 'last_seen_ingest_run_id', 'last_seen_at'):
        added = _ensure_column(cursor, 'raw_episodes', column) or added
    return added


def replay_schema(cursor):
    """Re-run raw_zone.sql so the view projects any newly added column.

    Idempotent by construction (CREATE ... IF NOT EXISTS, DROP/CREATE VIEW), so
    replaying it on an existing database is safe -- but only AFTER the
    compaction check. The schema creates a unique index on
    (episode_key, source_hash), which a pre-upsert zone cannot satisfy. Today
    that happens to succeed there anyway, because every episode_key is still
    NULL and SQLite treats NULLs as distinct in a unique index; a half-migrated
    zone with keys backfilled but duplicates still present would raise a bare
    IntegrityError instead of the actionable message assert_compacted gives.
    """
    schema = config.SCHEMA_DIR / 'raw_zone.sql'
    cursor.executescript(schema.read_text(encoding='utf-8'))


def assert_compacted(cursor):
    """Refuse to upsert into a raw zone that still holds per-run snapshots.

    The upsert recognises an existing row by (episode_key, source_hash). In a
    pre-upsert database that pair matches six rows at once -- one per historical
    load -- so "is this row already here?" has no single answer, and the unique
    index that would enforce one cannot be created until the duplicates are gone.

    Loading anyway would not corrupt anything, but it would silently keep
    appending full snapshots while reporting them as upserts, which is worse
    than stopping.
    """
    dupes = cursor.execute('''
        SELECT COUNT(*) FROM (
            SELECT episode_key, source_hash
            FROM raw_episodes
            WHERE episode_key IS NOT NULL
            GROUP BY episode_key, source_hash
            HAVING COUNT(*) > 1
        )
    ''').fetchone()[0]
    unkeyed = cursor.execute(
        "SELECT COUNT(*) FROM raw_episodes WHERE episode_key IS NULL"
    ).fetchone()[0]

    if dupes or unkeyed:
        logger.error("Raw zone is not compacted: "
                     f"{dupes} duplicated version(s), {unkeyed} row(s) with no "
                     f"episode_key.")
        logger.error("Run: python scripts/migrate_compact_raw_zone.py")
        return False
    return True


def read_source(csv_path):
    """Read the episode list exactly as written, with nothing inferred.

    dtype=str and keep_default_na=False together are what make this a raw read:
    pandas otherwise types each column by guessing, which is how the xlsx path
    used to put '1995.0' in the year column and the literal string 'nan' in
    every empty cell. An empty field here is '', and every value is the text the
    file contains.
    """
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    # Tolerated for hand-edited files and for anything exported back out of
    # Excel, which reintroduces the space in 'ep ex_1999'.
    df.columns = [col.replace(' ', '_') for col in df.columns]
    return df


def load_source_to_raw(csv_path, db_path):
    """Load data/episodes.csv into raw_episodes."""
    # Initialize DB if needed
    if not Path(db_path).exists():
        logger.info(f"Creating database: {db_path}")
        init_database(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    logger.info(f"Reading {csv_path}")
    df = read_source(csv_path)
    
    logger.info(f"Loaded {len(df)} rows, {len(df.columns)} columns")
    logger.info(f"Columns: {', '.join(df.columns[:10])}")
    
    # Create ingest run record
    ingest_run_id = str(uuid.uuid4())
    sync_timestamp = datetime.utcnow().isoformat()
    
    cursor.execute('''
        INSERT INTO raw_ingest_runs (ingest_run_id, source_url, sync_timestamp, rows_ingested, sync_status)
        VALUES (?, ?, ?, ?, ?)
    ''', (ingest_run_id, str(csv_path), sync_timestamp, len(df), 'success'))
    
    # Widen the table for any known new source columns before validating. The
    # schema replay that goes with it waits until after the compaction check.
    schema_changed = migrate_raw_columns(cursor)

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

    if not assert_compacted(cursor):
        conn.close()
        sys.exit(1)

    if schema_changed:
        replay_schema(cursor)

    added, edited, unchanged = 0, 0, 0
    seen_keys = set()

    for idx, row in df.iterrows():
        row_dict = row.to_dict()

        # Compute fingerprint over ALL source values (including any future cols)
        row_str = '|'.join([str(v) for v in row.values])
        source_hash = hashlib.md5(row_str.encode()).hexdigest()

        episode_key = episode_business_key(
            row_dict.get('ep'), row_dict.get('date'), row_dict.get('title'))

        # Two source rows sharing a business key would upsert onto each other,
        # so the second would vanish. That has never happened -- ep+date+title is
        # unique across all 489 rows -- but it must not fail silently if the
        # sheet ever gains a genuine duplicate.
        if episode_key in seen_keys:
            logger.warning(f"Row {idx}: duplicate business key {episode_key!r} "
                           f"in the source file — skipping the second copy")
            continue
        seen_keys.add(episode_key)

        existing = cursor.execute(
            "SELECT raw_episode_id FROM raw_episodes "
            "WHERE episode_key = ? AND source_hash = ?",
            (episode_key, source_hash)
        ).fetchone()

        if existing:
            # Unchanged. Touch only the provenance columns; the ingested values
            # are never rewritten.
            cursor.execute(
                "UPDATE raw_episodes SET last_seen_ingest_run_id = ?, "
                "last_seen_at = ? WHERE raw_episode_id = ?",
                (ingest_run_id, sync_timestamp, existing[0]))
            unchanged += 1
            continue

        # New key, or a new version of a key already present.
        is_edit = cursor.execute(
            "SELECT 1 FROM raw_episodes WHERE episode_key = ? LIMIT 1",
            (episode_key,)).fetchone() is not None

        raw_episode_id = str(uuid.uuid4())
        cols = (['raw_episode_id', 'ingest_run_id'] + insert_cols
                + ['episode_key', 'source_hash', 'gs_row_number', 'ingested_at',
                   'last_seen_ingest_run_id', 'last_seen_at'])
        values = ([raw_episode_id, ingest_run_id]
                  + [row_dict.get(c) for c in insert_cols]
                  + [episode_key, source_hash, idx, sync_timestamp,
                     ingest_run_id, sync_timestamp])
        placeholders = ', '.join(['?'] * len(values))

        try:
            cursor.execute(f'''
                INSERT INTO raw_episodes ({', '.join(cols)})
                VALUES ({placeholders})
            ''', values)
        except sqlite3.IntegrityError as e:
            logger.warning(f"Row {idx}: {e} (skipping)")
            continue

        if is_edit:
            edited += 1
        else:
            added += 1

    # An airing in the table that this load did not see has been deleted from
    # the sheet. Nothing to do -- it simply stops being current -- but say so,
    # since it silently removes episodes from every downstream count.
    #
    # Grouped rather than matched against the keys just read: an airing can have
    # several stored versions and is only withdrawn when NONE of them was
    # re-seen. It also keeps the query independent of sheet size, where an
    # IN (?, ?, ...) list would eventually hit SQLite's variable limit.
    withdrawn = cursor.execute('''
        SELECT COUNT(*) FROM (
            SELECT episode_key FROM raw_episodes
            GROUP BY episode_key
            HAVING MAX(CASE WHEN last_seen_ingest_run_id = ? THEN 1 ELSE 0 END) = 0
        )
    ''', (ingest_run_id,)).fetchone()[0]

    conn.commit()
    total = cursor.execute("SELECT COUNT(*) FROM raw_episodes").fetchone()[0]
    current = cursor.execute(
        "SELECT COUNT(*) FROM raw_episodes_current").fetchone()[0]
    conn.close()

    logger.info(f"✓ Upserted {len(df)} source rows: {added} new, {edited} edited, "
                f"{unchanged} unchanged")
    if withdrawn:
        logger.warning(f"⚠ {withdrawn} airing(s) in the raw zone are no longer in "
                       f"the source file — they drop out of raw_episodes_current")
    logger.info(f"  raw_episodes: {total} version rows, {current} current airings")

def main():
    csv_path = config.path_setting('SOURCE_CSV', 'data/episodes.csv')
    db_path = str(config.db_path())

    if not csv_path.exists():
        logger.error(f"{csv_path} not found. Run scripts/01_render_source.py "
                     "first: it writes this file from data/episodes.xlsx.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info(f"Phase 2: Load raw zone from {csv_path}")
    logger.info("=" * 60)

    load_source_to_raw(csv_path, db_path)

    logger.info("=" * 60)

if __name__ == '__main__':
    config.setup_logging()
    main()
