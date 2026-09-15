# 004 — The episode list moves to `data/episodes.xlsx`

Date: 2026-09-15.

## Decisions

| Question | Decision | How it was applied |
| --- | --- | --- |
| Source of truth | `data/episodes.xlsx`, edited in Excel | Step 01 checks it and renders `data/episodes.csv` on every run |
| Google Sheet | Retired | `01_sync_sheets.py` deleted; README no longer lists the sheet keys |
| The damaged working-tree CSV | Restore from the last commit | Restored with `git checkout`. Its one real edit (ep 320) went into the workbook |
| Keeping the app current | A banner, not automatic runs | Every page warns while the workbook is newer than the last load |

## Why the CSV kept breaking, and what xlsx changes

Of the file saved at 14:43, all 491 rows differed from the commit. Only one of
those changes was a real edit:

| Change | Cells | Cause |
| --- | ---: | --- |
| ISO date → `2015/12/22` | 491 | Excel's locale date format |
| Ebert `3/4` → `4-3月` | 269 | Excel parsing the rating as a date |
| Curly quotes, `…`, `á` garbled | 7 | Re-encoding as GBK |
| `Mallory Rubin*` → `Mallory Rubin` (ep 320) | 1 | **The user's edit** |

**The format isn't the cause; Excel saving a CSV is.** A workbook stores
UTF-8 text and real dates, so a save can't do this. Excel still converts
values as they are typed, though. The old `master.xlsx` showed that risk:
- 348 of its 489 Ebert cells were formatted `m/d` and 7 `d-mmm`;
- `rating` and `ebert_stars` were formulas.

**Two columns are copies, on all 491 rows:** `rating` equals
`tomatoes_score`, and `ebert_stars` equals the number in `ebert`.

## What was built

- **`data/episodes.xlsx`**, built by
  `convert_xlsx_to_csv.py --init-episodes-workbook` from the committed CSV:
  - 491 episodes in a table named `EpisodeList`, with the header, `ep` and
    `title` frozen;
  - text columns formatted as Text for 3,000 rows, dates as real `yyyy-mm-dd`
    dates, scores as percentages;
  - lists on `ebert` (eight ratings plus "Not reviewed") and `cruise_hanks`,
    and 0/1 limits on `is_film` and `revisited`;
  - 185,565 bytes.

  On building, it verified that it renders back to the CSV exactly.
- **Step 01, `scripts/01_render_source.py`**, replaces the Google Sheet
  download.
  - It checks every cell. A bad cell stops the run, names the row and column,
    and leaves the CSV untouched. Each mistake is reported once: a derived
    column is compared only when its source passed.
  - Blank `rating` and `ebert_stars` are filled from their source columns.
  - It refuses while Excel has the workbook open (the `~$` lock file) and
    falls back to the tracked CSV when there's no workbook.
  - It copies a CSV edited after the workbook to `logs/` before replacing it,
    and leaves an unchanged CSV alone so its timestamp stays meaningful.
- **`convert_xlsx_to_csv.py`** was extended rather than duplicated. Its
  `render()` is shared with step 13 and now handles plain datetimes and float
  noise (`0.8300000000000001` → `0.83`).
- **App.** The stale-data banner (`views.stale_notice`). The three data
  loaders are now keyed on the database file's modification time, so a
  pipeline run shows on the next reload instead of up to 5 minutes later.
- **Docs.** The orchestrator's add-an-episode instructions (now `--from 1`),
  step 02's docstring (which used to say "edit it in Excel ... Save As CSV"),
  `DATA_SOURCES.md` ("The episode workbook"), README, `.gitattributes`, and
  `.gitignore` (ignores `~$*`).

## Results

| Check | Result |
| --- | --- |
| Prototype on a scratch copy: workbook → CSV | 491/491 `source_hash` identical, byte-identical file |
| Real build: workbook renders back to the CSV | exact |
| Step 01 after the ep 320 edit | "0 new, 1 edited, 0 removed"; `git diff` shows exactly one line |
| `orchestrate.py --from 1` | 13/13 steps pass; zero TMDB calls (456 from cache at steps 9 and 10) |
| Database after | ep 320 guest3 = "Mallory Rubin"; 491 airings, 456 films, 483 episode links, as before |
| `upcoming.csv` after step 13 used the new `render()` | unchanged (214 rows unchanged) |
| Banner, workbook saved 15:33 vs load 15:30 | shown on every page |
| Banner, after restoring the workbook's real save time (15:28) | hidden |

Backup taken before the run: `rewatchables.db.pre-xlsx-20260915_152947.bak`.

## Verification

- **`tests/test_source_csv.py` gained 40 tests:**
  - the exact round trip;
  - pre-formatted blank rows aren't episodes;
  - Text formatting below the data;
  - a typed-in row renders like the rest, with the copies filled;
  - an Ebert date, text dates, out-of-range values, a formula with no saved
    result, a disagreeing copy, a duplicate airing and a renamed column are
    all refused;
  - one mistake produces one message;
  - a future date is a warning;
  - the builder never overwrites the workbook;
  - the step's outcomes: open in Excel, no workbook, bad cell, CSV edited
    later, unchanged CSV;
  - the banner;
  - the real workbook renders to the tracked CSV.
- **Timing and a fix:** with the orchestrator tests, 90 pass in 37 s. The
  first run took 5 min 45 s, because every test built a 3,000-row workbook;
  the builder now takes `format_rows`, and tests use 60. That first run also
  caught the duplicate derived-column message, which is now fixed.
- **Full suite:** still running when this was committed. By then these had
  passed: the source and orchestrator suites (90), the pipeline itself run end
  to end (13/13), and the banner checked in the browser both shown and hidden.
  The app-level suites (dossier, Hosts & Guests) are in that full run, and its
  result is reported separately.

## Open items

1. **Not tested in real Excel.** The Text formats and lists should make a
   typed `3/4` stay text, or be refused, but I checked that through openpyxl,
   not by typing in Excel. A one-minute check: open the workbook, type `3/4`
   into `ebert` on a new row, and confirm it's accepted as the rating and
   not turned into a date.
2. **Old keys in `config/.env`:** the `GOOGLE_SHEETS_*` entries are now
   unused. That file is local and untracked, so remove them at will.
3. **The Ebert list lives in the workbook.** A new kind of value (say `0/4`)
   would need adding to the list in Excel (Data → Data Validation) as well as
   to `EBERT_CHOICES`.
4. **Not committed:** `data/episodes.xlsx`, the regenerated CSV and the code.
   Commit the workbook and the CSV together.
5. **`PROJECT_PLAN.md` is untouched.** It still describes `master.xlsx` and
   the sheet; it's a historical plan.
