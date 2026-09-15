#!/usr/bin/env python3
"""
Phase 1: Render data/episodes.xlsx into data/episodes.csv.

THE WORKBOOK IS THE SOURCE OF TRUTH. It is the file that gets edited, so it is
the file this step reads. The CSV it writes is a rendering, tracked in git
because it diffs: the workbook shows up as "Bin 71028 -> 76009 bytes", the CSV
beside it as the one row that changed. 02_load_raw reads the CSV, verbatim, and
nothing downstream knows the workbook exists.

This step used to download a Google Sheet over the CSV. The sheet was retired
on 2026-09-15: it had drifted from the local file in 59 places and lacked four
of its 20 columns, so keeping both meant two masters that disagreed.

EVERY CELL IS CHECKED ON THE WAY. A row that breaks its column's rules -- a
rating Excel has turned into a date, a date typed as text, a score of 83 where
0.83 was meant, two rows for the same airing -- stops the run with the row and
the column named, and the CSV is left as it was. `rating` and `ebert_stars`
copy `tomatoes_score` and the number in `ebert`: left blank they are filled,
and where they disagree the run stops. The rules are check_episode() and
render_episode_workbook() in convert_xlsx_to_csv.py.

FOUR OTHER OUTCOMES, each chosen over its silent alternative:

  open in Excel    refuse. Reading it would build the last SAVED version while
                   the edits on screen wait -- the same reasoning as step 13.
  no workbook      fall back to the tracked CSV and say so. A fresh checkout
                   has the CSV but need not have the workbook.
  CSV edited after the workbook -- by hand, or by opening it in Excel -- is
                   still replaced, since the workbook is the source, but a copy
                   goes to logs/ first and the run says so.
  nothing new      the CSV is not rewritten, so its timestamp stays meaningful.

Usage:
    python scripts/01_render_source.py
    python scripts/orchestrate.py --from 1     # render, load and rebuild

The workbook was built once from the committed CSV, formatted so that Excel
keeps each column's type as you type:
    python scripts/convert_xlsx_to_csv.py --init-episodes-workbook
"""

import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from rewatchables import config
from rewatchables.keys import episode_business_key
from rewatchables.pipeline.convert_xlsx_to_csv import (
    CSV_PATH, EPISODE_XLSX, excel_lock_file, render_episode_workbook,
    write_episode_csv,
)

logger = logging.getLogger(__name__)

# Problems printed before the rest are summarised as a count.
SHOW = 25


def read_previous(csv_path):
    """The CSV as it stands, or None when it is absent or no longer UTF-8."""
    if not csv_path.exists():
        return None
    try:
        return pd.read_csv(csv_path, dtype=str, keep_default_na=False,
                           encoding='utf-8')
    except (UnicodeDecodeError, pd.errors.ParserError):
        return None


def changes(before, after):
    """(new, edited, removed) business keys between two renderings."""
    def rows(df):
        return {episode_business_key(r.ep, r.date, r.title): tuple(r)
                for r in df.itertuples(index=False)}
    b, a = rows(before), rows(after)
    return ([k for k in a if k not in b],
            [k for k in a if k in b and a[k] != b[k]],
            [k for k in b if k not in a])


def render_source(xlsx_path=EPISODE_XLSX, csv_path=CSV_PATH,
                  backup_dir=config.LOG_DIR):
    """Render the workbook into the CSV. Returns 0 when the run may continue."""
    xlsx_path, csv_path = Path(xlsx_path), Path(csv_path)
    backup_dir = Path(backup_dir)

    if not xlsx_path.exists():
        if csv_path.exists():
            logger.info(f"No {xlsx_path} — loading {csv_path} as it stands.")
            return 0
        logger.error(f"Neither {xlsx_path} nor {csv_path} exists; nothing to load.")
        return 1

    lock = excel_lock_file(xlsx_path)
    if lock:
        logger.error(f"{xlsx_path} is open in Excel ({lock.name} is beside it).")
        logger.error("Save it, close it and run this again. If Excel is not "
                     f"running, the lock file is left from a crash: delete {lock}.")
        return 1

    try:
        rendered, errors, warnings = render_episode_workbook(xlsx_path)
    except PermissionError:
        logger.error(f"Cannot read {xlsx_path} — it is open in another program. "
                     "Close it and run this again.")
        return 1

    for w in warnings:
        logger.warning(f"⚠ {w}")
    if errors:
        logger.error(f"{xlsx_path} has {len(errors)} problem(s); {csv_path} was "
                     "not touched. Fix these in the workbook:")
        for e in errors[:SHOW]:
            logger.error(f"  {e}")
        if len(errors) > SHOW:
            logger.error(f"  ... and {len(errors) - SHOW} more")
        return 1

    previous = read_previous(csv_path)
    if previous is not None and previous.equals(rendered):
        logger.info(f"✓ {csv_path} already matches {xlsx_path} "
                    f"({len(rendered)} rows); not rewritten.")
        return 0

    if csv_path.exists():
        edited_later = csv_path.stat().st_mtime > xlsx_path.stat().st_mtime
        if previous is None or edited_later:
            backup_dir.mkdir(parents=True, exist_ok=True)
            kept = backup_dir / f"{csv_path.name}.replaced-{datetime.now():%Y%m%d_%H%M%S}"
            shutil.copy2(csv_path, kept)
            why = ("is no longer UTF-8" if previous is None
                   else "was changed after the workbook was last saved")
            logger.warning(f"⚠ {csv_path} {why}. Edits belong in {xlsx_path}; the "
                           f"CSV is regenerated from it. The replaced file is "
                           f"kept at {kept}.")

    if previous is not None:
        new, edited, removed = changes(previous, rendered)
        logger.info(f"Changes: {len(new)} new, {len(edited)} edited, "
                    f"{len(removed)} removed")
        for label, keys in (("new", new), ("edited", edited), ("removed", removed)):
            for k in keys[:10]:
                logger.info(f"  {label:8s}{k}")

    if not write_episode_csv(rendered, csv_path):
        logger.error(f"VERIFICATION FAILED — {csv_path} does not read back "
                     "identically.")
        return 1
    logger.info(f"✓ Wrote {len(rendered)} rows to {csv_path}")
    return 0


def main():
    xlsx_path = config.path_setting('SOURCE_XLSX', EPISODE_XLSX)
    csv_path = config.path_setting('SOURCE_CSV', CSV_PATH)

    logger.info("=" * 60)
    logger.info(f"Phase 1: Render {xlsx_path} → {csv_path}")
    logger.info("=" * 60)
    return render_source(xlsx_path, csv_path)


if __name__ == '__main__':
    config.setup_logging()
    sys.exit(main())
