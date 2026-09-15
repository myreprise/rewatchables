#!/usr/bin/env python3
"""
Spreadsheets to tracked CSV: the rendering shared by steps 01 and 13.

  data/episodes.xlsx         -> data/episodes.csv    step 01, every run
  data/remaining films.xlsx  -> data/upcoming.csv    step 13, every run

This began as a one-off migration, data/master.xlsx -> data/episodes.csv, and
what follows is why a CSV sits beside each workbook at all. The episode
workbook and the checks it gets are described under "The episode workbook"
further down.

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
    python scripts/convert_xlsx_to_csv.py --init-episodes-workbook [--overwrite]
"""

import argparse
import logging
import re
import sys
from datetime import date, datetime
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.table import Table, TableStyleInfo

from _keys import episode_business_key

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
    # pd.Timestamp is a datetime, so this covers the pandas read path as well
    # as the plain datetimes openpyxl hands back.
    if isinstance(value, (datetime, date)):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, float):
        # Ten significant digits: an integer-valued float loses its '.0', and
        # the binary noise a computed cell can carry (0.8300000000000001) goes.
        return f'{value:.10g}'
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


# ── The episode workbook ──────────────────────────────────────────────────────
# Since 2026-09-15 the episode list is edited in data/episodes.xlsx. The Google
# Sheet step 01 used to download is retired, and episodes.csv is back to being
# what upcoming.csv already was: a rendering, tracked so a change reads as a
# diff, regenerated by step 01 on every run.
#
# Why a workbook and not the CSV: opening a CSV in Excel on this machine and
# saving it re-encodes the file as GBK, rewrites every ISO date in the local
# format and reads each Ebert rating like '3/4' as a date ('4-3月'). It happened
# twice on 2026-09-15. A workbook holds text as UTF-8 and dates as dates, so a
# save cannot do that.
#
# Why it is still checked cell by cell: Excel converts as you TYPE. A '3/4'
# typed into a General cell is the fourth of March before any file is written.
# So the workbook is built with every text column formatted as Text and the
# ratings offered as a list, and the render refuses any cell that is not what
# its column holds -- naming the row and the column -- rather than passing it
# downstream.

EPISODE_XLSX = Path('data/episodes.xlsx')

# The CSV's columns in the CSV's order. It is also the order 02_load_raw
# computes source_hash in, so reordering this would present every row as edited.
EPISODE_COLUMNS = [
    'ep', 'ep_ex_1999', 'title', 'date', 'host', 'guest1', 'guest2', 'guest3',
    'guest4', 'year', 'genre', 'director', 'ebert', 'tomatoes_score',
    'cruise_hanks', 'notes', 'rating', 'is_film', 'ebert_stars', 'revisited',
]
INT_COLUMNS = {'ep', 'ep_ex_1999', 'year', 'is_film', 'revisited'}
PERCENT_COLUMNS = ('tomatoes_score', 'rating')
STAR_COLUMNS = {'ebert_stars'}
DATE_COLUMNS = {'date'}

# Rows below the data that are formatted in advance, so a value typed into a
# new row lands in a cell that already has its column's format.
FORMAT_ROWS = 3000

EBERT_RATING = re.compile(r'(\d(?:\.5)?)/4')
EBERT_CHOICES = [f'{n / 2:g}/4' for n in range(1, 9)] + ['Not reviewed']
VERDICTS = ('Cruise', 'Hanks', 'Tie')

COLUMN_WIDTH = {
    'title': 38, 'notes': 60, 'genre': 26, 'director': 24, 'date': 12,
    'host': 16, 'guest1': 18, 'guest2': 18, 'guest3': 18, 'guest4': 18,
    'tomatoes_score': 14, 'cruise_hanks': 13,
}


def excel_lock_file(xlsx_path):
    """The owner file Excel keeps beside a workbook it has open, or None.

    Excel names it '~$' plus the file name, and some Office versions replace
    the name's first two characters instead ('~$isodes.xlsx'); both are
    checked. Its presence is the reliable signal: Excel does not always stop
    another process reading the file, and a read then sees the last SAVED
    version while the edits on screen wait.
    """
    xlsx_path = Path(xlsx_path)
    for name in ('~$' + xlsx_path.name, '~$' + xlsx_path.name[2:]):
        lock = xlsx_path.with_name(name)
        if lock.exists():
            return lock
    return None


def _typed(column, text):
    """A CSV value as the cell Excel should hold for it.

    Only a value that fits its column's type is converted; anything else is
    written as text, so the workbook can always render back to the CSV.
    """
    if text == '':
        return None
    if column in DATE_COLUMNS and re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
        return datetime.strptime(text, '%Y-%m-%d')
    if column in INT_COLUMNS and re.fullmatch(r'\d+', text):
        return int(text)
    if (column in PERCENT_COLUMNS or column in STAR_COLUMNS) and \
            re.fullmatch(r'\d+(\.\d+)?', text):
        return float(text)
    return text


def _number_format(column):
    if column in DATE_COLUMNS:
        return 'yyyy-mm-dd'
    if column in PERCENT_COLUMNS:
        return '0%'
    if column in STAR_COLUMNS:
        return '0.0'
    if column in INT_COLUMNS:
        return '0'
    return '@'   # Text: what stops a typed '3/4' becoming a date


def _span(column, rows=FORMAT_ROWS):
    letter = get_column_letter(EPISODE_COLUMNS.index(column) + 1)
    return f'{letter}2:{letter}{rows}'


def build_episode_workbook(csv_path=CSV_PATH, xlsx_path=EPISODE_XLSX,
                           overwrite=False, format_rows=FORMAT_ROWS):
    """Build data/episodes.xlsx from the CSV, formatted for safe editing.

    A one-off: after this the workbook is the source and the CSV is rendered
    from it. It refuses to overwrite an existing workbook unless told to, since
    that is the file holding every edit. The result is read straight back and
    must render to exactly the CSV it was built from.

    `format_rows` is how far down the column formats reach. The real workbook
    takes the default; tests pass a few dozen, because formatting 3,000 rows
    makes every build and read of the file seconds slower.
    """
    csv_path, xlsx_path = Path(csv_path), Path(xlsx_path)
    if xlsx_path.exists() and not overwrite:
        logger.error(f"{xlsx_path} already exists and is the source of truth; "
                     f"not overwriting it. Pass --overwrite to rebuild it from "
                     f"{csv_path}.")
        return 1

    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding='utf-8')
    if list(df.columns) != EPISODE_COLUMNS:
        logger.error(f"{csv_path} does not have the expected columns: "
                     f"{list(df.columns)}")
        return 1

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'episodes'
    ws.append(EPISODE_COLUMNS)
    for row in df.itertuples(index=False):
        ws.append([_typed(c, v) for c, v in zip(EPISODE_COLUMNS, row)])

    for j, column in enumerate(EPISODE_COLUMNS, start=1):
        fmt = _number_format(column)
        for i in range(2, format_rows + 1):
            ws.cell(row=i, column=j).number_format = fmt
        ws.column_dimensions[get_column_letter(j)].width = COLUMN_WIDTH.get(column, 11)

    last = get_column_letter(len(EPISODE_COLUMNS))
    ws.add_table(Table(
        displayName='EpisodeList', ref=f'A1:{last}{len(df) + 1}',
        tableStyleInfo=TableStyleInfo(name='TableStyleLight9', showRowStripes=True)))
    ws.freeze_panes = 'D2'   # header row, and ep / ep_ex_1999 / title

    # The ratings as a list: picking one enters exactly the text the pipeline
    # expects, and typing anything else is refused before it is saved.
    choices = [
        ('ebert', ','.join(EBERT_CHOICES), 'Pick a rating from the list, or leave it blank.'),
        ('cruise_hanks', ','.join(VERDICTS), 'Cruise, Hanks, Tie, or blank.'),
    ]
    for column, options, message in choices:
        dv = DataValidation(type='list', formula1=f'"{options}"', allow_blank=True,
                            showErrorMessage=True, error=message)
        dv.add(_span(column, format_rows))
        ws.add_data_validation(dv)
    for column in ('is_film', 'revisited'):
        dv = DataValidation(type='whole', operator='between', formula1='0',
                            formula2='1', allow_blank=True, showErrorMessage=True,
                            error='0 or 1.')
        dv.add(_span(column, format_rows))
        ws.add_data_validation(dv)

    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(xlsx_path)

    back, errors, _ = render_episode_workbook(xlsx_path)
    if errors or not back.equals(df):
        logger.error(f"VERIFICATION FAILED — {xlsx_path} does not render back to "
                     f"{csv_path}.")
        for e in errors[:10]:
            logger.error(f"  {e}")
        return 1
    logger.info(f"✓ Built {xlsx_path}: {len(df)} episodes, renders back to "
                f"{csv_path} exactly")
    return 0


def _sheet(wb):
    return wb['episodes'] if 'episodes' in wb.sheetnames else wb.worksheets[0]


def _is_iso_date(text):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
        return False
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _is_fraction(text):
    try:
        return 0 <= float(text) <= 1
    except ValueError:
        return False


def check_episode(out, bad=()):
    """Problems with one rendered row, as messages. Fills the derived columns.

    `rating` is a copy of `tomatoes_score` and `ebert_stars` the number in
    `ebert` -- true of every one of the 491 rows when the workbook was built.
    Left blank they are filled, so a new row needs neither; where they
    disagree, one of the two is wrong and the run stops.

    `bad` names columns the caller has already reported (a formula with no
    result, a date where text belongs). A derived column is only compared once
    both it and its source are sound: otherwise one mistake arrives as two
    messages, and the second -- "clear the copy" -- points at the wrong cell.
    """
    problems, failed = [], set(bad)

    def need(column, ok, expected):
        if not ok:
            failed.add(column)
            problems.append(f"{column} is {out[column]!r}; expected {expected}")

    need('ep', re.fullmatch(r'\d+', out['ep']), 'a whole episode number')
    need('ep_ex_1999', out['ep_ex_1999'] == '' or re.fullmatch(r'\d+', out['ep_ex_1999']),
         'a whole number or blank')
    need('title', out['title'] != '', 'a title')
    need('date', _is_iso_date(out['date']),
         'an air date, entered as a date (e.g. 2026-09-21)')
    need('year', out['year'] == '' or re.fullmatch(r'\d{4}', out['year']),
         'a four-digit year or blank')
    need('ebert', out['ebert'] in ('', 'Not reviewed') or EBERT_RATING.fullmatch(out['ebert']),
         "a rating like '3.5/4', 'Not reviewed', or blank")
    for column in PERCENT_COLUMNS:
        need(column, out[column] == '' or _is_fraction(out[column]),
             'a score from 0% to 100% (83% is 0.83), or blank')
    need('cruise_hanks', out['cruise_hanks'] in ('',) + VERDICTS,
         'Cruise, Hanks, Tie, or blank')
    for column in ('is_film', 'revisited'):
        need(column, out[column] in ('0', '1'), '0 or 1')

    if failed & {'tomatoes_score', 'rating'}:
        pass
    elif out['rating'] == '':
        out['rating'] = out['tomatoes_score']
    elif out['rating'] != out['tomatoes_score']:
        problems.append(f"rating {out['rating']} disagrees with tomatoes_score "
                        f"{out['tomatoes_score'] or '(blank)'}; rating is a copy of "
                        "it -- clear rating and it will be filled")

    if failed & {'ebert', 'ebert_stars'}:
        pass
    else:
        rated = EBERT_RATING.fullmatch(out['ebert'])
        stars = f"{float(rated.group(1)):g}" if rated else ''
        if out['ebert_stars'] == '':
            out['ebert_stars'] = stars
        elif out['ebert_stars'] != stars:
            problems.append(f"ebert_stars {out['ebert_stars']} disagrees with ebert "
                            f"{out['ebert']!r}; clear ebert_stars and it will be filled")
    return problems


def render_episode_workbook(xlsx_path=EPISODE_XLSX):
    """Read the workbook into the CSV's text, checking every cell.

    Returns (frame, errors, warnings). The frame is only safe to write when
    errors is empty. A row with nothing in it is not an episode -- the rows
    below the data are pre-formatted, and to openpyxl a formatted cell is a
    cell. Formulas are read by their saved result; one with no saved result
    (a file last written by something other than Excel) is an error, not a
    blank.
    """
    values_ws = _sheet(openpyxl.load_workbook(xlsx_path, data_only=True))
    formula_ws = _sheet(openpyxl.load_workbook(xlsx_path, data_only=False))
    errors, warnings = [], []

    header = [str(c.value).strip().replace(' ', '_') if c.value is not None else ''
              for c in values_ws[1]]
    missing = [c for c in EPISODE_COLUMNS if c not in header]
    unknown = [c for c in header if c and c not in EPISODE_COLUMNS]
    if missing:
        errors.append(f"missing column(s): {', '.join(missing)}")
    if unknown:
        errors.append(f"column(s) the pipeline has no place for: {', '.join(unknown)} "
                      "(add them to sql/schemas/raw_zone.sql first)")
    if errors:
        return pd.DataFrame(columns=EPISODE_COLUMNS), errors, warnings

    where = {c: header.index(c) for c in EPISODE_COLUMNS}
    rows, seen, today = [], {}, date.today()
    pairs = zip(values_ws.iter_rows(min_row=2, values_only=True),
                formula_ws.iter_rows(min_row=2, values_only=True))
    for excel_row, (values, formulas) in enumerate(pairs, start=2):
        if all(v is None or (isinstance(v, str) and not v.strip()) for v in values):
            continue

        out, problems, bad = {}, [], set()
        for column in EPISODE_COLUMNS:
            value, formula = values[where[column]], formulas[where[column]]
            is_formula = (isinstance(formula, str) and formula.startswith('=')) \
                or hasattr(formula, 'text')
            if value is None and is_formula:
                problems.append(f"{column} is a formula with no saved result; open "
                                "the workbook in Excel and save it")
                out[column] = ''
                bad.add(column)
                continue
            if isinstance(value, (datetime, date)) and column not in DATE_COLUMNS:
                if column == 'ebert':
                    problems.append(f"ebert holds a date ({value:%d %b}): Excel turned "
                                    "a rating like '3/4' into a date. Pick the rating "
                                    "from the cell's list instead")
                else:
                    problems.append(f"{column} holds a date ({value:%Y-%m-%d})")
                out[column] = ''
                bad.add(column)
                continue
            out[column] = render(value)

        problems += check_episode(out, bad)
        label = f"row {excel_row} (ep {out['ep'] or '?'}, {out['title'] or 'untitled'})"
        errors.extend(f"{label}: {p}" for p in problems)

        key = episode_business_key(out['ep'], out['date'], out['title'])
        if key in seen:
            errors.append(f"{label}: same episode number, date and title as row "
                          f"{seen[key]}; the load would keep only one of them")
        else:
            seen[key] = excel_row
        if _is_iso_date(out['date']) and date.fromisoformat(out['date']) > today:
            warnings.append(f"{label}: air date {out['date']} is in the future")
        rows.append(out)

    return pd.DataFrame(rows, columns=EPISODE_COLUMNS), errors, warnings


def write_episode_csv(frame, csv_path=CSV_PATH):
    """Write the rendered episodes as UTF-8 with LF endings, and read it back.

    Returns whether the round trip under 02_load_raw's read (dtype=str,
    keep_default_na=False) is exact. LF because .gitattributes pins the file to
    it; UTF-8 explicitly, because the platform default here is GBK.
    """
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(csv_path, index=False, lineterminator='\n', encoding='utf-8')
    back = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding='utf-8')
    return back.equals(frame)


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dry-run', action='store_true',
                    help='report what would change without writing')
    ap.add_argument('--source', choices=('episodes', 'upcoming'),
                    default='episodes',
                    help='which sheet to convert (default: episodes)')
    ap.add_argument('--init-episodes-workbook', action='store_true',
                    help='build data/episodes.xlsx from data/episodes.csv (one-off)')
    ap.add_argument('--overwrite', action='store_true',
                    help='with --init-episodes-workbook: replace an existing workbook')
    args = ap.parse_args()

    if args.init_episodes_workbook:
        return build_episode_workbook(overwrite=args.overwrite)
    if args.source == 'upcoming':
        return convert(UPCOMING_XLSX, UPCOMING_CSV, dry_run=args.dry_run,
                       reshape=upcoming_reshape)
    return convert(dry_run=args.dry_run)


if __name__ == '__main__':
    sys.exit(main())
