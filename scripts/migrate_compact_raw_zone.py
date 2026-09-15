#!/usr/bin/env python3
"""
One-off migration: compact the raw zone from per-run snapshots to version rows.

Before the upsert (see 02_load_raw.py), every load re-inserted the entire sheet.
Six loads left 2,913 rows in raw_episodes for 489 real airings, and the count
grew by the full sheet size on every run. This collapses that history: one row
per (airing, distinct content), which is what raw_episodes was always trying to
express.

What it does, in one transaction:

  1. adds episode_key / last_seen_ingest_run_id / last_seen_at
  2. backfills episode_key for every row from ep+date+title
  3. sets last_seen to the newest run each (key, hash) pair appeared in
  4. deletes the duplicate copies, keeping ONE row per (key, hash)
  5. creates the unique index the upsert relies on
  6. replays raw_zone.sql so the rebuilt view is in place

WHICH DUPLICATE SURVIVES MATTERS. The surviving row keeps the raw_episode_id of
the copy from the MOST RECENT run it appeared in, because staging_episodes and
staging_movie_mentions hold foreign keys to exactly those ids, and app.py joins
raw_episodes through them. Keeping the oldest copy instead would be more natural
-- it is the one that was genuinely "first seen" -- and would silently break that
join. The survivor's ingest_run_id is then relabelled to the run that first saw
the version, so the column keeps meaning "the load that introduced this row".

Safety: refuses to run unless raw_episodes_current returns exactly the same set
of raw_episode_ids afterwards as it did before. That set is what the whole app
reads, so if it is unchanged, nothing downstream can have moved.

Idempotent -- a second run finds nothing to compact and exits cleanly.

Usage:
    python scripts/migrate_compact_raw_zone.py [--dry-run]
"""

import argparse
import logging
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv

from _keys import episode_business_key

load_dotenv('config/.env')

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'),
                    format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

SCHEMA = Path(__file__).parent.parent / 'sql' / 'schemas' / 'raw_zone.sql'


def _ensure_column(cursor, table, column, decl="TEXT"):
    existing = {r[1] for r in cursor.execute(f"PRAGMA table_info({table})")}
    if existing and column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        logger.info(f"  added {table}.{column}")
        return True
    return False


def current_ids(cursor):
    """The raw_episode_ids raw_episodes_current returns right now.

    This is the migration's whole safety property: it is the set app.py reads,
    and the set staging's foreign keys point into.
    """
    return {r[0] for r in cursor.execute(
        "SELECT raw_episode_id FROM raw_episodes_current")}


def already_compacted(cursor):
    """True when the raw zone is already in the post-migration shape.

    Checked before anything is written, because re-running the migration on a
    compacted zone is actively destructive rather than merely redundant: with the
    duplicates gone, each (key, hash) has exactly one occurrence, so the pass
    that derives "last run this version was seen in" would find only the
    first-seen run and overwrite last_seen with it. Every airing not first seen
    in the newest run would then drop out of raw_episodes_current.
    """
    columns = {r[1] for r in cursor.execute("PRAGMA table_info(raw_episodes)")}
    if not {'episode_key', 'last_seen_ingest_run_id'} <= columns:
        return False

    unkeyed = cursor.execute(
        "SELECT COUNT(*) FROM raw_episodes "
        "WHERE episode_key IS NULL OR last_seen_ingest_run_id IS NULL"
    ).fetchone()[0]
    dupes = cursor.execute('''
        SELECT COUNT(*) FROM (
            SELECT 1 FROM raw_episodes GROUP BY episode_key, source_hash
            HAVING COUNT(*) > 1
        )
    ''').fetchone()[0]
    return not unkeyed and not dupes


def compact(db_path, dry_run=False):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    before_total = cursor.execute("SELECT COUNT(*) FROM raw_episodes").fetchone()[0]
    before_current = current_ids(cursor)
    logger.info(f"Before: {before_total} rows, {len(before_current)} current airings")

    if already_compacted(cursor):
        conn.close()
        logger.info(f"✓ Already compacted: {before_total} version rows, "
                    f"{len(before_current)} current airings. Nothing to do.")
        return 0

    # --- 1. columns ---------------------------------------------------------
    for column in ('episode_key', 'last_seen_ingest_run_id', 'last_seen_at'):
        _ensure_column(cursor, 'raw_episodes', column)

    # --- 2. backfill episode_key -------------------------------------------
    rows = cursor.execute(
        "SELECT raw_episode_id, ep, date, title FROM raw_episodes").fetchall()
    for raw_id, ep, date, title in rows:
        cursor.execute("UPDATE raw_episodes SET episode_key = ? "
                       "WHERE raw_episode_id = ?",
                       (episode_business_key(ep, date, title), raw_id))
    logger.info(f"  backfilled episode_key on {len(rows)} rows")

    # --- 3+4. pick a survivor per (key, hash), record its lifespan ----------
    # Ordering by the run's sync_timestamp, so "first" and "last" mean when the
    # load actually happened rather than whatever order rows were inserted in.
    versions = {}
    for raw_id, key, shash, run_id, ts in cursor.execute('''
        SELECT re.raw_episode_id, re.episode_key, re.source_hash,
               re.ingest_run_id, r.sync_timestamp
        FROM raw_episodes re
        JOIN raw_ingest_runs r ON r.ingest_run_id = re.ingest_run_id
        ORDER BY r.sync_timestamp ASC
    '''):
        versions.setdefault((key, shash), []).append((raw_id, run_id, ts))

    keep, drop = [], []
    for (key, shash), occurrences in versions.items():
        first_run = occurrences[0][1]
        last_id, last_run, last_ts = occurrences[-1]
        # Keep the NEWEST copy: staging's foreign keys point at that id.
        keep.append((last_id, first_run, last_run, last_ts))
        drop.extend(o[0] for o in occurrences[:-1])

    logger.info(f"  {len(keep)} distinct (airing, version) pairs, "
                f"{len(drop)} duplicate rows to remove")

    if dry_run:
        conn.close()
        logger.info("Dry run — nothing written.")
        return 0

    # Delete BEFORE relabelling. The survivor's ingest_run_id is rewritten to
    # the run that first saw it, and the row that originally belonged to that
    # run is one of the duplicates -- it still holds (that run, that hash), which
    # the pre-existing UNIQUE(ingest_run_id, source_hash) forbids duplicating.
    # Clearing the duplicates first vacates the slot.
    if drop:
        cursor.executemany("DELETE FROM raw_episodes WHERE raw_episode_id = ?",
                           [(i,) for i in drop])

    for raw_id, first_run, last_run, last_ts in keep:
        cursor.execute(
            "UPDATE raw_episodes SET ingest_run_id = ?, "
            "last_seen_ingest_run_id = ?, last_seen_at = ? "
            "WHERE raw_episode_id = ?",
            (first_run, last_run, last_ts, raw_id))

    # --- verify, while a rollback is still possible -------------------------
    # sqlite3.executescript() issues an implicit COMMIT before it runs, so the
    # schema replay below is a point of no return. Everything that could go
    # wrong is checked first, against a query that spells out the new view's
    # selector by hand -- the view itself is still the old definition here.
    after_total = cursor.execute("SELECT COUNT(*) FROM raw_episodes").fetchone()[0]
    after_current = {r[0] for r in cursor.execute('''
        SELECT raw_episode_id FROM raw_episodes
        WHERE last_seen_ingest_run_id = (
            SELECT ingest_run_id FROM raw_ingest_runs
            ORDER BY sync_timestamp DESC LIMIT 1
        )
    ''')}

    if after_current != before_current:
        missing = before_current - after_current
        extra = after_current - before_current
        logger.error("VERIFICATION FAILED — raw_episodes_current changed.")
        logger.error(f"  {len(missing)} airing(s) lost, {len(extra)} gained")
        if missing:
            logger.error(f"  e.g. missing: {sorted(missing)[:3]}")
        conn.rollback()
        conn.close()
        return 1

    # Staging's foreign keys must still resolve, or app.py's episode join dies.
    orphans = cursor.execute('''
        SELECT COUNT(*) FROM staging_episodes se
        WHERE NOT EXISTS (SELECT 1 FROM raw_episodes re
                          WHERE re.raw_episode_id = se.raw_episode_id)
    ''').fetchone()[0]
    if orphans:
        logger.error(f"VERIFICATION FAILED — {orphans} staging episode(s) now "
                     f"point at a deleted raw row.")
        conn.rollback()
        conn.close()
        return 1

    conn.commit()

    # --- 5+6. index and view ------------------------------------------------
    # Replaying the schema creates the unique index the upsert relies on and
    # rebuilds the view on the new selector. Idempotent by construction
    # (CREATE ... IF NOT EXISTS, DROP/CREATE VIEW), so it is safe to replay on an
    # already-migrated database. The unique index can only be created now that
    # the duplicates are gone.
    cursor.executescript(SCHEMA.read_text(encoding='utf-8'))
    conn.commit()

    # The real view, now that it is the new definition, must agree with the
    # hand-written selector the verification above used.
    if current_ids(cursor) != before_current:
        logger.error("VERIFICATION FAILED — the rebuilt view disagrees with the "
                     "selector used to verify the compaction.")
        conn.close()
        return 1

    conn.close()

    logger.info(f"After:  {after_total} rows, {len(after_current)} current airings")
    logger.info(f"✓ Compacted {before_total} → {after_total} rows "
                f"({before_total - after_total} removed); "
                f"current airings unchanged, no orphaned staging rows")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dry-run', action='store_true',
                    help='report what would change without writing')
    args = ap.parse_args()

    db_path = os.getenv('DB_PATH', 'rewatchables.db')
    if not Path(db_path).exists():
        logger.error(f"{db_path} not found.")
        return 1

    logger.info("=" * 60)
    logger.info("Compacting raw zone: per-run snapshots → version rows")
    logger.info("=" * 60)
    return compact(db_path, dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
