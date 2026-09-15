#!/usr/bin/env python3
"""
One-off migration: data/master.xlsx -> data/episodes.csv.

The xlsx was a binary blob in git. `git diff` reported it as
"Bin 71028 -> 76009 bytes, 0 insertions(+), 0 deletions(-)" -- you could not see
which episode was added, and two edits could not merge. A CSV makes the source
of truth reviewable: adding an episode becomes a one-line diff.

It also drops a layer of Excel dtype artifacts that were reaching the raw zone.
pandas infers a type per column when reading xlsx, and 02_load_raw then stringified
whatever came out, so the database stored:

    year         '1995.0'   (int column inferred as float because of blanks)
    ep_ex_1999   '1.0'
    guest2       'nan'      (the literal three-letter string, for an empty cell)
    title        'Heat '    (120 titles carried trailing whitespace)

None of that is in the source data -- it is an artifact of the xlsx read path.
The CSV carries the values themselves, and 02_load_raw now reads it with
dtype=str and keep_default_na=False, so nothing is inferred on the way back in.

WHAT THIS CHANGES DOWNSTREAM. Every row's source_hash changes, because the raw
values genuinely change ('nan' -> '', '1995.0' -> '1995'). The next load
therefore records one new version per episode -- an edit, not an insert. Business
keys are unaffected (they already strip the title and normalise the date), so
staging ids stay stable and the manual review decisions still replay.

Trailing whitespace is stripped deliberately, not incidentally. It is invisible
in a diff and would vanish the first time a cell was edited by hand, producing a
spurious version row; doing it once, now, is cheaper than having it decay.

THE SECOND SOURCE. `--source upcoming` converts data/remaining films.xlsx into
data/upcoming.csv -- the list of films expected in future episodes. Same
reasoning, same round-trip guarantee, plus a reshape the episode file does not
need; see upcoming_reshape for what it drops and why.

Usage:
    python scripts/convert_xlsx_to_csv.py [--dry-run]
    python scripts/convert_xlsx_to_csv.py --source upcoming [--dry-run]
"""

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

XLSX_PATH = Path('data/master.xlsx')
CSV_PATH = Path('data/episodes.csv')

UPCOMING_XLSX = Path('data/remaining films.xlsx')
UPCOMING_CSV = Path('data/upcoming.csv')


def render(value):
    """One source cell as the text the CSV should carry.

    Missing becomes empty rather than 'nan'; a float that is really an integer
    loses its '.0'; everything else is stripped text. This is the whole of the
    cleanup -- no value is reinterpreted, only rendered without the artifacts
    the xlsx read path added.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
        return ''
    if isinstance(value, pd.Timestamp):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value).strip()


JUSTIFICATION_COLS = ['justification_1', 'justification_2', 'justification_3']


def upcoming_reshape(df):
    """Reduce the upcoming sheet to the columns that carry a distinct fact.

    Three changes, each because the source column is not what it looks like.

    `index` and `entry_name` go. `index` is a row number. `entry_name` is a sort
    key, not a name: it differs from `title` on 39 of 214 rows and every
    difference is the same transform ('The Blind Side' -> 'Blind Side, The'),
    so it is regenerated for display rather than stored.

    The three justification columns become two. Exactly one of them is populated
    per row -- they are alternatives, not fields -- but they are not three kinds
    of thing either. Measured over the 211 rows that have one:

        justification_1  93 rows, median 13 words, 99% cite an episode
        justification_3  70 rows, median 17 words, 83% cite an episode
        justification_2  48 rows, median  5 words,  2% cite an episode,
                                                   94% comma-separated

    _1 and _3 are the same thing said in two columns -- prose evidence that the
    film was mentioned on air ("mentioned during The Big Chill ep"). Which of
    the two a row uses tracks the contributor, not the meaning. _2 is genuinely
    different: a comma-separated pitch ("1980s, John Carpenter, Kurt Russell").

    So _1 and _3 merge into `mention_note` (safe -- they never co-occur) and _2
    becomes `pitch_tags`, which the app splits into filter chips. Collapsing all
    three into one column instead would put a tag list and a paragraph in the
    same field and lose the tags as an axis.

    `contributor` is stripped of its "contributed by " prefix, which is on every
    row and says nothing.
    """
    df = df.copy()

    for col in JUSTIFICATION_COLS:
        if col not in df.columns:
            df[col] = pd.NA

    both = df[['justification_1', 'justification_3']].notna().all(axis=1)
    if both.any():
        # Never seen, but a merge that silently discarded one of two populated
        # cells would be invisible in the output.
        logger.warning(f"{int(both.sum())} row(s) have BOTH justification_1 and "
                       f"justification_3; keeping _1 and dropping _3")

    df['mention_note'] = df['justification_1'].fillna(df['justification_3'])
    df['pitch_tags'] = df['justification_2']

    df['contributor'] = (df['contributor'].astype('string').str.strip()
                         .str.replace(r'^contributed by\s+', '', regex=True))

    keep = ['title', 'year', 'contributor', 'mention_note', 'pitch_tags']
    missing = [c for c in keep if c not in df.columns]
    if missing:
        logger.error(f"upcoming sheet is missing expected column(s): {missing}")
        raise SystemExit(1)
    return df[keep]


def convert(xlsx_path=XLSX_PATH, csv_path=CSV_PATH, dry_run=False,
            reshape=None):
    if not xlsx_path.exists():
        logger.error(f"{xlsx_path} not found.")
        return 1

    df = pd.read_excel(xlsx_path)
    # The sheet's 'ep ex_1999' has a space; the schema column does not. 02 has
    # always done this rename on the way in, so do it once here instead.
    df.columns = [c.replace(' ', '_') for c in df.columns]
    logger.info(f"Read {len(df)} rows, {len(df.columns)} columns from {xlsx_path}")

    if reshape is not None:
        df = reshape(df)
        logger.info(f"Reshaped to {len(df.columns)} columns: "
                    f"{', '.join(df.columns)}")

    out = df.map(render)

    # Report what the rendering actually changed, per column, so the diff in the
    # raw zone afterwards is expected rather than surprising.
    before = df.astype(str)
    logger.info("Columns whose stored text changes:")
    for col in out.columns:
        changed = (before[col] != out[col]).sum()
        if changed:
            example = next(
                (f"{b!r} -> {a!r}" for b, a in zip(before[col], out[col]) if b != a),
                "")
            logger.info(f"  {col:16s} {changed:4d} row(s)   {example}")

    if dry_run:
        logger.info("Dry run — nothing written.")
        return 0

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    # newline='' + lineterminator so the file is identical on every platform;
    # otherwise Windows writes CRLF and every line reads as changed in git.
    out.to_csv(csv_path, index=False, lineterminator='\n')
    logger.info(f"✓ Wrote {len(out)} rows to {csv_path}")

    # Read it straight back the way 02_load_raw will, and confirm the round trip
    # is lossless. A quoting or encoding problem has to surface here, not as a
    # silently mangled episode three steps downstream.
    back = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    if not back.equals(out):
        logger.error("VERIFICATION FAILED — the CSV does not read back identically.")
        diff = (back != out)
        for col in out.columns:
            if diff[col].any():
                i = diff[col].idxmax()
                logger.error(f"  {col}: wrote {out[col][i]!r}, read {back[col][i]!r}")
        return 1
    logger.info("✓ Round-trips losslessly under dtype=str, keep_default_na=False")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dry-run', action='store_true',
                    help='report what would change without writing')
    ap.add_argument('--source', choices=('episodes', 'upcoming'),
                    default='episodes',
                    help='which sheet to convert (default: episodes)')
    args = ap.parse_args()

    if args.source == 'upcoming':
        return convert(UPCOMING_XLSX, UPCOMING_CSV, dry_run=args.dry_run,
                       reshape=upcoming_reshape)
    return convert(dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
