#!/usr/bin/env python3
"""
One-time migration: rewrite uuid4 staging ids to the deterministic uuid5 scheme
introduced in 03_normalize_and_resolve.py.

Before this, staging ids were random and regenerated on every rebuild, so
anything keyed to them detached the moment step 03 ran: manual resolutions,
data/manual_review.csv, and approved rows in manual_review_queue.

Rewriting the existing ids in place means the current database already matches
what 03 will generate, so no rebuild is needed and manual work survives the
next one.

Tables updated (all references, in FK-safe order):
    staging_episodes.staging_episode_id
    staging_movie_mentions.staging_mention_id, .staging_episode_id
    curated_episode_movies.staging_episode_id
    manual_review_queue.staging_mention_id
Plus data/manual_review.csv, which is keyed on staging_mention_id.

Rows whose source episode is no longer in the latest ingest run keep their old
id -- they are already orphaned and inventing an id for them would be wrong.

Idempotent: ids already in the deterministic form are left alone.

Usage:
    python scripts/migrate_deterministic_ids.py --dry-run
    python scripts/migrate_deterministic_ids.py
"""

import argparse
import csv
import importlib.util
import logging
import os
import shutil
import sqlite3
import sys
from pathlib import Path

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

CSV_PATH = Path("data/manual_review.csv")

# Reuse the id functions from 03 so the two can never drift apart.
_spec = importlib.util.spec_from_file_location(
    "normalize_and_resolve",
    Path(__file__).parent / "03_normalize_and_resolve.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
make_episode_id = _mod.make_episode_id
make_mention_id = _mod.make_mention_id


def build_maps(conn):
    """Return (episode_map, mention_map) of old id -> new deterministic id."""
    cur = conn.cursor()

    # Source rows keyed by raw_episode_id, restricted to the latest ingest run
    # (the same snapshot 03 rebuilds staging from).
    raw = {r[0]: (r[1], r[2], r[3]) for r in cur.execute("""
        SELECT raw_episode_id, ep, date, title FROM raw_episodes
        WHERE ingest_run_id = (
            SELECT ingest_run_id FROM raw_ingest_runs
            ORDER BY sync_timestamp DESC LIMIT 1)
    """)}

    ep_map, orphan_eps = {}, 0
    for sid, raw_id in cur.execute(
            "SELECT staging_episode_id, raw_episode_id FROM staging_episodes"):
        src = raw.get(raw_id)
        if not src:
            orphan_eps += 1
            continue
        new = make_episode_id(*src)
        if new != sid:
            ep_map[sid] = new

    men_map, orphan_mentions = {}, 0
    for mid, raw_id, order in cur.execute(
            "SELECT staging_mention_id, raw_episode_id, mention_order "
            "FROM staging_movie_mentions"):
        src = raw.get(raw_id)
        if not src:
            orphan_mentions += 1
            continue
        new = make_mention_id(*src, order or 1)
        if new != mid:
            men_map[mid] = new

    if orphan_eps or orphan_mentions:
        logger.warning(f"Left untouched (source row not in latest ingest run): "
                       f"{orphan_eps} episodes, {orphan_mentions} mentions")
    return ep_map, men_map


def _collisions(conn, table, column, mapping):
    """New ids that already exist on a DIFFERENT row would corrupt the table."""
    cur = conn.cursor()
    existing = {r[0] for r in cur.execute(f"SELECT {column} FROM {table}")}
    return {new for old, new in mapping.items()
            if new in existing and new != old}


def migrate(db_path, dry_run=False):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    ep_map, men_map = build_maps(conn)
    logger.info(f"Episode ids to rewrite: {len(ep_map)}")
    logger.info(f"Mention ids to rewrite: {len(men_map)}")
    if not ep_map and not men_map:
        logger.info("✓ Already migrated — nothing to do.")
        conn.close()
        return 0, 0

    for table, column, mapping in [
            ("staging_episodes", "staging_episode_id", ep_map),
            ("staging_movie_mentions", "staging_mention_id", men_map)]:
        clash = _collisions(conn, table, column, mapping)
        if clash:
            logger.error(f"{table}.{column}: {len(clash)} new id(s) already in "
                         f"use. Aborting rather than corrupting rows.")
            conn.close()
            sys.exit(1)

    manual = cur.execute(
        "SELECT COUNT(*) FROM staging_movie_mentions "
        "WHERE resolution_method = 'manual_approved'").fetchone()[0]
    logger.info(f"Manual resolutions being preserved: {manual}")

    if dry_run:
        logger.info("Dry run — no changes written.")
        for old, new in list(men_map.items())[:3]:
            logger.info(f"  {old} -> {new}")
        conn.close()
        return len(ep_map), len(men_map)

    # Order matters only for readability -- sqlite has FK enforcement off by
    # default -- but children are updated alongside their parents regardless.
    for old, new in ep_map.items():
        cur.execute("UPDATE staging_episodes SET staging_episode_id = ? "
                    "WHERE staging_episode_id = ?", (new, old))
        cur.execute("UPDATE staging_movie_mentions SET staging_episode_id = ? "
                    "WHERE staging_episode_id = ?", (new, old))
        cur.execute("UPDATE curated_episode_movies SET staging_episode_id = ? "
                    "WHERE staging_episode_id = ?", (new, old))

    for old, new in men_map.items():
        cur.execute("UPDATE staging_movie_mentions SET staging_mention_id = ? "
                    "WHERE staging_mention_id = ?", (new, old))
        cur.execute("UPDATE manual_review_queue SET staging_mention_id = ? "
                    "WHERE staging_mention_id = ?", (new, old))

    conn.commit()

    after = cur.execute(
        "SELECT COUNT(*) FROM staging_movie_mentions "
        "WHERE resolution_method = 'manual_approved'").fetchone()[0]
    if after != manual:
        logger.error(f"Manual resolutions changed during migration "
                     f"({manual} -> {after}). Rolling back.")
        conn.rollback()
        conn.close()
        sys.exit(1)

    orphaned = cur.execute("""
        SELECT COUNT(*) FROM curated_episode_movies c
        LEFT JOIN staging_episodes e ON e.staging_episode_id = c.staging_episode_id
        WHERE e.staging_episode_id IS NULL""").fetchone()[0]
    if orphaned:
        logger.error(f"{orphaned} curated_episode_movies rows lost their "
                     f"staging_episodes parent. Rolling back.")
        conn.rollback()
        conn.close()
        sys.exit(1)

    conn.close()
    logger.info(f"✓ Rewrote {len(ep_map)} episode and {len(men_map)} mention ids")
    return len(ep_map), len(men_map)


def migrate_csv(men_map, dry_run=False, csv_path=CSV_PATH):
    """Rewrite manual_review.csv, which is keyed on staging_mention_id."""
    csv_path = Path(csv_path)
    if not csv_path.exists():
        logger.info(f"{csv_path} not present — skipping")
        return 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)

    remapped = 0
    for row in rows:
        old = row.get("staging_mention_id")
        if old in men_map:
            row["staging_mention_id"] = men_map[old]
            remapped += 1

    logger.info(f"{csv_path}: {remapped}/{len(rows)} rows remapped")
    if dry_run or not remapped:
        return remapped

    shutil.copy(csv_path, csv_path.with_suffix(".csv.pre-deterministic.bak"))
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return remapped


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=os.getenv("DB_PATH", "rewatchables.db"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not Path(args.db).exists():
        logger.error(f"{args.db} not found.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Migrate staging ids to the deterministic scheme")
    logger.info("=" * 60)

    conn = sqlite3.connect(args.db)
    _, men_map = build_maps(conn)
    conn.close()

    migrate(args.db, dry_run=args.dry_run)
    migrate_csv(men_map, dry_run=args.dry_run)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
