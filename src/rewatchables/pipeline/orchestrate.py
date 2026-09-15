#!/usr/bin/env python3
"""
Orchestrate the rewatchables pipeline.

Thirteen steps in five stages:

  source   01 render episodes.xlsx, 02 load raw
  resolve  03 normalize + stage mentions, 04 resolve against TMDB
  curated  05 validate, 06 build curated zone, 07 export review queue,
           08 apply review decisions
  enrich   09 TMDB metadata, 10 external ids, 11 CMU corpus,
           12 plot summaries (CMU + live Wikipedia)
  upcoming 13 build the upcoming-films list

Step 13 is a stage of its own because it is a second, independent source. It
reads "data/remaining films.xlsx" rather than the episode list, writes only its
own tables, and depends on steps 01-12 for exactly one thing: curated_movies has
to be current before it can tell which requested films have become real
episodes. That is why it runs last and not why it runs at all -- `--stages
upcoming` on its own is a legitimate way to refresh the list.

ADDING AN UPCOMING FILM. Add the row to "data/remaining films.xlsx", save, close
it in Excel, then:

    python scripts/orchestrate.py --stages upcoming

Unlike the episode path there is no --from to remember. Step 13 regenerates
data/upcoming.csv from the xlsx itself, so the xlsx is the only file to edit --
and edits made to the CSV instead are overwritten without warning. (Step 01
does the same for episodes.csv, but keeps a copy of a hand-edited CSV in logs/
first.) Expect one TMDB search for the new film.

REBUILDING FROM SOURCE -- read before running the whole thing.

Step 03 clears staging and step 04 re-resolves every mention from scratch, so a
hand-made correction is undone mid-run. 'Crash' (2004) is the standing example:
it auto-matches a 5-minute Australian short sharing its title and release year,
at 1.0 confidence.

Those corrections come back, but only because staging ids are now deterministic
(uuid5 over episode number + air date + title). Step 08 replays
data/manual_review.csv against the rebuilt rows and the ids still line up. When
the ids were uuid4 they changed on every rebuild and the decisions were simply
lost.

That recovery depends on step 08 actually running. A run that includes 03 but
stops before 08 leaves the wrong matches in place, so that combination is
refused unless --rebuild-from-source says it is intended.

A REBUILD IS CHEAP NOW, but it is still not free of consequence -- the guard
above is about correctness, not cost. Every network step caches: 04 in
tmdb_search_cache, 09 in tmdb_metadata_cache, 10 in external_id_cache, 12 in
raw_wiki_articles, and 11 reads vendored files. A full rebuild of every layer
therefore costs no API calls and runs in seconds; only a genuinely new title
reaches the network. Pass --refresh to 04, 09, 10 or 12 individually to force a
re-fetch.

ADDING OR EDITING AN EPISODE. Edit data/episodes.xlsx, save, close it in Excel,
then:

    python scripts/orchestrate.py --from 1

Step 01 checks every cell and regenerates data/episodes.csv from the workbook;
it stops with the row and column named if a cell is wrong, and refuses to read
the workbook while Excel has it open. 02 upserts, so only changed rows are
stored; 03 and 04 rebuild from the cache; 08 replays the review decisions.
Expect one TMDB search per new film. Until this runs, the app shows a banner
saying the workbook is newer than the data.

Edit the workbook, never the CSV: step 01 regenerates the CSV on every run. If
it finds the CSV was changed after the workbook was saved, it copies the
replaced file to logs/ and says so rather than discarding it silently. (The
Google Sheet step 01 used to download is retired; see DATA_SOURCES.md.)

Usage:
    python scripts/orchestrate.py                    # safe refresh (05-12)
    python scripts/orchestrate.py --all              # everything, guarded
    python scripts/orchestrate.py --all --rebuild-from-source
    python scripts/orchestrate.py --stages enrich    # just 09-12
    python scripts/orchestrate.py --stages upcoming  # just 13
    python scripts/orchestrate.py --from 6 --to 9
    python scripts/orchestrate.py --list
"""

import argparse
import importlib.util
import logging
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from rewatchables import config

logger = logging.getLogger(__name__)

PACKAGE = "rewatchables.pipeline"
DB_PATH = str(config.db_path())

# (number, module, description, stage, optional)
# optional=True -> a failure is logged and the pipeline continues. Used for the
# human-in-the-loop review steps, which fail by design when there is nothing
# queued or no decisions CSV yet.
STEPS = [
    (1,  "s01_render_source",         "Render episodes.xlsx → episodes.csv",   "source",  False),
    (2,  "s02_load_raw",              "Load raw zone from episodes.csv",       "source",  False),
    (3,  "s03_normalize_and_resolve", "Normalize + stage movie mentions",      "resolve", False),
    (4,  "s04_enrich",                "Resolve mentions against TMDB",         "resolve", False),
    (5,  "s05_validate",              "Validate data quality",                 "curated", False),
    (6,  "s06_build_curated",         "Build curated zone + revisit detection", "curated", False),
    (7,  "s07_export_review_queue",   "Export manual-review queue",            "curated", True),
    (8,  "s08_apply_review",          "Apply manual-review decisions",         "curated", True),
    (9,  "s09_enrich_metadata",       "Enrich metadata from TMDB",             "enrich",  False),
    (10, "s10_resolve_external_ids",  "Resolve external identifiers",          "enrich",  False),
    (11, "s11_load_cmu",              "Load CMU corpus subset",                "enrich",  False),
    (12, "s12_enrich_plot_summaries", "Plot summaries: CMU + live Wikipedia",  "enrich",  False),
    (13, "s13_build_upcoming",        "Build upcoming-films list",             "upcoming", False),
]

STAGES = ["source", "resolve", "curated", "enrich", "upcoming"]
DESTRUCTIVE_STEP = 3   # clears staging
REPLAY_STEP = 8        # replays manual_review.csv onto the rebuilt rows
SAFE_DEFAULT_FROM = 5   # everything from validation down is re-runnable


def start_log():
    """Log to the console and to a new file in logs/; return the file.

    Called when a run starts from the command line, not at import, so that
    importing this module -- as its tests do -- writes no log file.
    """
    config.LOG_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    log_file = config.LOG_DIR / f"orchestrate_{stamp}.log"
    config.setup_logging(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"),
                  logging.StreamHandler()],
    )
    return log_file


def run_step(step_num, module, description, position, total, optional):
    name = f"{PACKAGE}.{module}"
    if importlib.util.find_spec(name) is None:
        logger.error(f"✗ Step {step_num}: {name} not found")
        return False

    logger.info("=" * 70)
    logger.info(f"[{position}/{total}] Step {step_num}: {description}")
    logger.info("=" * 70)

    try:
        result = subprocess.run([sys.executable, "-m", name],
                                cwd=str(config.ROOT), capture_output=False)
    except Exception as e:
        logger.error(f"✗ Step {step_num} error: {e}")
        return False

    if result.returncode != 0:
        level = logger.warning if optional else logger.error
        level(f"{'⚠' if optional else '✗'} Step {step_num} exited "
              f"{result.returncode}{' (optional, continuing)' if optional else ''}")
        return False

    logger.info(f"✓ Step {step_num} completed")
    return True


def count_manual_resolutions(db_path):
    """How many hand-made resolutions step 03 would discard."""
    if not Path(db_path).exists():
        return 0
    try:
        conn = sqlite3.connect(db_path)
        n = conn.execute(
            "SELECT COUNT(*) FROM staging_movie_mentions "
            "WHERE resolution_method = 'manual_approved'").fetchone()[0]
        conn.close()
        return n
    except sqlite3.Error:
        return 0


def select_steps(args):
    steps = STEPS
    if args.only:
        wanted = {int(x) for x in args.only.split(",")}
        return [s for s in steps if s[0] in wanted]
    if args.stages:
        wanted = {x.strip() for x in args.stages.split(",")}
        unknown = wanted - set(STAGES)
        if unknown:
            logger.error(f"Unknown stage(s): {', '.join(sorted(unknown))}. "
                         f"Valid: {', '.join(STAGES)}")
            sys.exit(2)
        return [s for s in steps if s[3] in wanted]

    lo = args.from_step if args.from_step is not None else (
        1 if args.all else SAFE_DEFAULT_FROM)
    hi = args.to_step if args.to_step is not None else len(STEPS)
    return [s for s in steps if lo <= s[0] <= hi]


def main(log_to_file=False):
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--all", action="store_true",
                    help="run every step from 01 (implies the destructive path)")
    ap.add_argument("--from", dest="from_step", type=int, metavar="N")
    ap.add_argument("--to", dest="to_step", type=int, metavar="N")
    ap.add_argument("--only", metavar="N[,N...]", help="run just these steps")
    ap.add_argument("--stages", metavar="S[,S...]",
                    help=f"run whole stages: {', '.join(STAGES)}")
    ap.add_argument("--rebuild-from-source", action="store_true",
                    help="allow a rebuild that does not replay review decisions")
    ap.add_argument("--continue-on-error", action="store_true",
                    help="keep going after a required step fails")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--list", action="store_true", help="list steps and exit")
    args = ap.parse_args()

    if args.list:
        print(f"{'#':>3}  {'stage':8s}  module")
        for num, script, desc, stage, optional in STEPS:
            print(f"{num:>3}  {stage:8s}  {script:32s} {desc}"
                  f"{'  [optional]' if optional else ''}")
        return 0

    # --list only prints, so only a run -- dry or real -- gets a log file.
    log_file = start_log() if log_to_file else None

    selected = select_steps(args)
    if not selected:
        logger.error("No steps selected.")
        return 2

    # --- guard an unreplayed rebuild --------------------------------------
    # A rebuild is fine as long as step 08 replays the review decisions against
    # the regenerated (deterministic) ids. Stopping in between is not.
    nums = {s[0] for s in selected}
    if DESTRUCTIVE_STEP in nums and REPLAY_STEP not in nums             and not args.rebuild_from_source:
        manual = count_manual_resolutions(DB_PATH)
        if manual:
            logger.error("=" * 70)
            logger.error("REFUSING TO RUN: rebuild without replaying review")
            logger.error("=" * 70)
            logger.error(
                f"{manual} mention(s) are resolved as 'manual_approved'. Step 03 "
                f"clears staging and step 04 re-resolves from scratch, which can "
                f"re-introduce a wrong match that was corrected by hand. Step 08 "
                f"replays data/manual_review.csv and puts those corrections back, "
                f"but it is not in this run.")
            logger.error("")
            logger.error("  Include the replay:             "
                         "orchestrate.py --all")
            logger.error("  Refresh derived layers instead: orchestrate.py")
            logger.error("  Or proceed unreplayed:          "
                         "... --rebuild-from-source")
            return 3

    total = len(selected)
    logger.info("=" * 70)
    logger.info("REWATCHABLES PIPELINE")
    logger.info(f"Started: {datetime.now(timezone.utc).isoformat()}")
    logger.info(f"Steps: {', '.join(str(s[0]) for s in selected)}")
    logger.info("=" * 70)

    if args.dry_run:
        for num, script, desc, stage, optional in selected:
            logger.info(f"  [{stage}] {num:>2} {script:32s} {desc}"
                        f"{'  [optional]' if optional else ''}")
        logger.info("Dry run — nothing executed.")
        return 0

    results, halted = [], False
    for position, (num, script, desc, stage, optional) in enumerate(selected, 1):
        ok = run_step(num, script, desc, position, total, optional)
        results.append((num, desc, ok, optional))
        if not ok and not optional and not args.continue_on_error:
            logger.error(f"Pipeline halted at step {num}")
            halted = True
            break

    logger.info("\n" + "=" * 70)
    logger.info("PIPELINE SUMMARY")
    logger.info("=" * 70)
    for num, desc, ok, optional in results:
        status = "✓ PASS" if ok else ("⚠ SKIP" if optional else "✗ FAIL")
        logger.info(f"Step {num:>2}: {status} - {desc}")

    failed = [r for r in results if not r[2] and not r[3]]
    if failed or halted:
        logger.error(f"\n✗ PIPELINE FAILED ({len(failed)} required step(s))")
        if log_file:
            logger.info(f"Log file: {log_file}")
        return 1

    skipped = [r for r in results if not r[2]]
    logger.info(f"\n✓ PIPELINE COMPLETED"
                f"{f' ({len(skipped)} optional step(s) skipped)' if skipped else ''}")
    if log_file:
        logger.info(f"Log file: {log_file}")
    return 0


if __name__ == "__main__":
    sys.exit(main(log_to_file=True))
