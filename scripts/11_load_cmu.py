#!/usr/bin/env python3
"""
Phase 2: Load the vendored CMU Movie Summary Corpus subset into the raw zone.

Reads the TSVs produced by vendor_cmu_subset.py:

    data/external/cmu/movies.tsv          -> raw_cmu_movies
    data/external/cmu/plot_summaries.tsv  -> raw_cmu_summaries
    data/external/cmu/characters.tsv      -> raw_cmu_characters

Each run is recorded in raw_cmu_loads with the vendored manifest, so a database
can always be traced back to the exact files it was built from.

Idempotent: the three tables are cleared and rebuilt on every run, exactly as
03_normalize rebuilds staging. Because the source is a static vendored snapshot
rather than a live feed, a reload is cheap and always yields the same result.

Deliberately NOT wired into raw_ingest_runs -- 03_normalize pins staging to the
newest row there, so a CMU load in that table would starve the episode rebuild.

Raw-zone fidelity: text is stored verbatim, including Wikipedia markup residue
and the handful of impossible Freebase values (two actor DOBs imply a negative
age at release). Blank strings become NULL; nothing else is corrected here.

Usage:
    python scripts/11_load_cmu.py [--source data/external/cmu]
"""

import argparse
import csv
import json
import logging
import os
import sqlite3
import sys
import uuid
from pathlib import Path

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

DEFAULT_SOURCE = Path("data/external/cmu")

MOVIE_FIELDS = ["wikipedia_page_id", "freebase_id", "name", "release_date",
                "box_office_revenue", "runtime", "languages", "countries", "genres"]
CHAR_FIELDS = ["fb_character_actor_map_id", "wikipedia_page_id", "freebase_id",
               "release_date", "character_name", "actor_dob", "actor_gender",
               "actor_height_m", "actor_ethnicity_fbid", "actor_name",
               "actor_age_at_release", "fb_character_id", "fb_actor_id"]


def _s(v):
    """Blank -> NULL; everything else verbatim."""
    v = (v or "").strip()
    return v or None


def _i(v):
    """Integer, or NULL when blank/unparseable. Negatives pass through: the
    corpus contains a couple of impossible ages and the raw zone keeps them."""
    v = (v or "").strip()
    if not v:
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def _f(v):
    v = (v or "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _require(source):
    missing = [n for n in ["movies.tsv", "plot_summaries.tsv", "characters.tsv"]
               if not (source / n).exists()]
    if missing:
        logger.error(f"Missing in {source}: {', '.join(missing)}. "
                     f"Run scripts/vendor_cmu_subset.py first.")
        sys.exit(1)


def _read_tsv(path, expected):
    """Read a vendored TSV, verifying its header matches what we expect."""
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        header = reader.fieldnames or []
        if set(expected) - set(header):
            logger.error(f"{path.name} header mismatch. "
                         f"Missing: {sorted(set(expected) - set(header))}")
            sys.exit(1)
        return list(reader)


def load_cmu(db_path, source=DEFAULT_SOURCE):
    source = Path(source)
    _require(source)

    manifest_path = source / "manifest.json"
    manifest = (json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.exists() else {})

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # The schema is only applied to a fresh db by 02_load_raw, so create the
    # CMU tables (raw_zone) and the v_movie_cmu join view (curated_zone)
    # defensively for databases that predate them. Both files are entirely
    # CREATE ... IF NOT EXISTS, so re-applying them is a no-op. Note this does
    # not add columns to existing tables -- that is 10_resolve_external_ids's
    # _ensure_column job, and this loader depends on it having run.
    schema_dir = Path(__file__).parent.parent / "sql" / "schemas"
    for fname in ["raw_zone.sql", "curated_zone.sql"]:
        cursor.executescript((schema_dir / fname).read_text(encoding="utf-8"))

    load_id = str(uuid.uuid4())

    # Idempotent rebuild — children first, so the load_id FKs never dangle.
    for table in ["raw_cmu_characters", "raw_cmu_summaries", "raw_cmu_movies"]:
        cursor.execute(f"DELETE FROM {table}")

    # --- movies ------------------------------------------------------------
    movies = _read_tsv(source / "movies.tsv", MOVIE_FIELDS)
    cursor.executemany("""
        INSERT INTO raw_cmu_movies
            (wikipedia_page_id, freebase_id, name, release_date,
             box_office_revenue, runtime, languages, countries, genres, load_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [(_i(r["wikipedia_page_id"]), _s(r["freebase_id"]), _s(r["name"]),
           _s(r["release_date"]), _i(r["box_office_revenue"]), _f(r["runtime"]),
           _s(r["languages"]), _s(r["countries"]), _s(r["genres"]), load_id)
          for r in movies])
    logger.info(f"raw_cmu_movies     : {len(movies)} rows")

    # --- summaries ---------------------------------------------------------
    # One summary per line; split on the first tab so tabs inside the text
    # (there should be none) can never shift columns.
    summaries = []
    with open(source / "plot_summaries.tsv", encoding="utf-8") as f:
        header = f.readline().rstrip("\n").split("\t")
        if header[:2] != ["wikipedia_page_id", "summary"]:
            logger.error(f"plot_summaries.tsv header mismatch: {header[:2]}")
            sys.exit(1)
        for line in f:
            pid, _, text = line.rstrip("\n").partition("\t")
            text = text.strip()
            if pid.strip() and text:
                summaries.append((_i(pid), text, len(text.split()), load_id))
    cursor.executemany(
        "INSERT INTO raw_cmu_summaries "
        "(wikipedia_page_id, summary, word_count, load_id) VALUES (?, ?, ?, ?)",
        summaries)
    logger.info(f"raw_cmu_summaries  : {len(summaries)} rows")

    # --- characters --------------------------------------------------------
    chars = _read_tsv(source / "characters.tsv", CHAR_FIELDS)
    cursor.executemany("""
        INSERT INTO raw_cmu_characters
            (fb_character_actor_map_id, wikipedia_page_id, freebase_id,
             release_date, character_name, actor_dob, actor_gender,
             actor_height_m, actor_ethnicity_fbid, actor_name,
             actor_age_at_release, fb_character_id, fb_actor_id, load_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [(_s(r["fb_character_actor_map_id"]), _i(r["wikipedia_page_id"]),
           _s(r["freebase_id"]), _s(r["release_date"]), _s(r["character_name"]),
           _s(r["actor_dob"]), _s(r["actor_gender"]), _f(r["actor_height_m"]),
           _s(r["actor_ethnicity_fbid"]), _s(r["actor_name"]),
           _i(r["actor_age_at_release"]), _s(r["fb_character_id"]),
           _s(r["fb_actor_id"]), load_id)
          for r in chars])
    logger.info(f"raw_cmu_characters : {len(chars)} rows")

    cursor.execute("""
        INSERT INTO raw_cmu_loads
            (load_id, source_url, tarball_sha256, manifest_json,
             movies_loaded, summaries_loaded, characters_loaded)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (load_id, manifest.get("source_url"), manifest.get("tarball_sha256"),
          json.dumps(manifest) if manifest else None,
          len(movies), len(summaries), len(chars)))

    conn.commit()

    linked = cursor.execute("SELECT COUNT(*) FROM v_movie_cmu").fetchone()[0]
    with_summary = cursor.execute(
        "SELECT COUNT(*) FROM v_movie_cmu WHERE plot_summary_wiki_raw IS NOT NULL"
    ).fetchone()[0]
    total = cursor.execute("SELECT COUNT(*) FROM curated_movies").fetchone()[0]
    conn.close()

    logger.info(f"✓ CMU load complete (load_id={load_id[:8]}…): "
                f"{linked}/{total} curated films linked, "
                f"{with_summary} with a plot summary")
    return len(movies), len(summaries), len(chars), linked


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=str(DEFAULT_SOURCE))
    ap.add_argument("--db", default=os.getenv("DB_PATH", "rewatchables.db"))
    args = ap.parse_args()

    if not Path(args.db).exists():
        logger.error(f"{args.db} not found.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Phase 2: Load CMU Movie Summary Corpus into the raw zone")
    logger.info("=" * 60)
    load_cmu(args.db, args.source)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
