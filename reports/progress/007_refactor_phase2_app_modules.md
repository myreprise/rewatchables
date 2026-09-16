# 007 — Refactor phase 2: app.py becomes an entry point

Date: 2026-09-16. Branch: `refactor/phase-2-app-modules`, off
`refactor/phase-1-pipeline-package`. None of the refactor branches is merged
into `master`.
Previous: [006 — Refactor phase 1](006_refactor_phase1_pipeline_package.md).

## TL;DR

`app.py` went from **5,275 lines to 173**. It now does six things: page config,
theme, building the context, the nav rail, the freshness banner, and handing
off to an overlay or a section. Everything else lives in
`src/rewatchables/app/`: 27 files, with the largest module (the Hosts &
Guests section) at 373 lines.

**768 passed at every commit.** One commit briefly sat on a failing suite
before being amended; see "What went wrong" below.

The split was aimed at test cost, and it delivered:

| Per AppTest run, CPU time | Phase 1 | Phase 2 |
| --- | ---: | ---: |
| Script transform Streamlit re-applies to `app.py` | 1,047 ms | 16 ms |
| Fresh AppTest + first run (what each test fixture pays) | 1.84 s | 0.55 s |
| Rerun after switching section (what each interaction pays) | 2.96 s | 1.47 s |

**These are test-harness numbers, not user-facing ones.** The Streamlit server
caches the compiled script, so a visitor already paid the transform once,
not per click. Phase 2 is not expected to change how the app feels.
The ~1.5 s per interaction that remains is the sections' own work, which is
phase 3's starting point.

## How it was measured

The phase 1 `app.py` and the phase 2 `app.py` ran against the same database
and the same package. Runs alternated old and new, with medians over 4–8 runs.

CPU time was used, not wall clock. While this phase ran, another project's
test suite was running on the machine (`tests/strategy_hub` and others,
started 16:10). The full suite's wall-clock time here ranged from 4:20 to 10:08
for identical code, so **no suite-level speed claim is made**. CPU time and
wall time agreed in the benchmark itself.

## What was built

| Commit | Module | What moved |
| --- | --- | --- |
| 1 | `theme.py`, `theme.css` | 1,053 lines of CSS from a Python string, and the palette |
| 2 | `data.py` | The three cached loaders and the gender map |
| 3 | `state.py` | The rail, the overlay callbacks, `keep`/`kept`, URL seeding |
| 4 | `components.py` | Cards, plates, tiles, ranked lists, keyword chip rows |
| 5 | `analysis.py` | Genre and cast explosions, per-person lookups, room leans |
| 6 | `charts.py`, `panels.py` | Plotly primitives; the people panels |
| 7 | `context.py`, `overlays/` | The `Ctx` object; dossier, keyword and prospect views |
| 8 | `sections/` | The twelve sections, one module each, with `render(ctx)` |

### Decisions

| Question | Decision | Why |
| --- | --- | --- |
| How sections get data | A frozen `Ctx`, built once per rerun and passed in | A section can't reach for a frame nobody gave it |
| Section bodies | Moved unchanged, with a preamble binding the names they use | A mechanical move is reviewable; renaming inside 2,400 lines at the same time is not |
| Section imports | Generated from what each body actually reads (free-variable analysis) | Hand-written import lists are where a missed name hides |
| Helpers that read globals | Now take what they need | See the list below |
| Nav rail and link format | Unchanged | The standing decision; the 46 app tests pin it |

The helpers that used to read module globals now take arguments:

- `keyword_row` takes `reach`;
- `films_by_director`, `films_by_actor` and `person_shelf` take the frame;
- `explode_cast` and `gender_split_leaderboards` take the gender map;
- `keyword_index` takes the films.

The gender-map change matters beyond tidiness. `explode_cast` used to fall back
silently to a global map, which is exactly how a population count could end up
labelled with the wrong population.

### Tests

- **`conftest.py`** imports `NAV` instead of parsing it out of `app.py`.
- **`test_people_gender.py`** imports `gender_from_people` and `explode_cast`.
  Nothing in it reads `app.py`'s source any more.
- **`test_card_hit_area.py`** reads the geometry rules from `theme.css` and
  searches the whole app package for card functions. It now covers all 18
  card call sites, including any section added later.

## What went wrong

The code is right, but the process slipped several times, and the slips belong
in the record.

1. **A commit landed on a failing suite.** The components commit was chained
   after a command that printed the suite's result instead of checking it.
   Five tests had failed: two Keywords call sites still used the old
   `keyword_row` signature. It was fixed and the commit amended before anything
   was built on it. Every later commit was gated on the log's `exit=0` line.
2. **App tests caught four mistakes before they reached a commit:**
   - one of two `explode_cast` calls in the gender split was missing the map,
     so a column heading would have counted the wrong population;
   - Movie Explorer's own dossier gate was missed when the overlay signature
     changed;
   - `stat_tile` was imported from the wrong module;
   - `VERDICT_FLOOR` was mapped to `analysis.py` but never moved there.
3. **Ruff accepted code that Python 3.11 rejects.** Ruff parses with a newer
   grammar, and accepted an f-string expression split across lines that 3.11
   refuses. Test collection caught it.
4. **One slice skipped the app tests.** For the components slice I ran only
   the two source-reading tests before the full suite, which is how item 1 got
   as far as it did.

The gates used from then on, in order:

1. parse every file under 3.11;
2. import every module;
3. ruff;
4. the 46 app tests;
5. the full suite;
6. commit only on `exit=0`.

## Found, not changed

1. **Section bodies still use the old variable names** (`movies_df`,
   `merged_df`, …), bound from `ctx` in each preamble. Renaming them to `ctx.*`
   would be a pure readability change. It was kept out of this phase so the
   move stayed mechanical.
2. **The freshness banner's query** (`last_load_utc`) still lives in `app.py`.
   It is 13 lines and has only the one caller.
3. **Still open from 005 and 006:**
   - `data/manual_review.csv` is untracked;
   - `WIKI_USER_AGENT` in `config/.env` should be `WIKIMEDIA_USER_AGENT`;
   - `logs/` holds 105 stale files.

## Commits

```
Phase 2: one module per section, and app.py becomes the entry point
Phase 2: give the app a context object and move the overlays
Phase 2: split the chart primitives and the people panels out
Phase 2: move the analysis helpers into the app package
Phase 2: move the card and layout components into the app package
Phase 2: move the nav rail and session state into the app package
Phase 2: move the data loaders into the app package
Phase 2: move the stylesheet and palette out of app.py
```

This docs commit, holding the README layout, the "Adding a section" guide and
this report, follows them.

## Next

Phase 3 is performance. It starts from what this phase measured:

- **Harness baseline:** about 1.5 s of CPU per interaction.
- **Production:** the Streamlit server should be measured directly, per
  section, before anything is changed.
- **Candidates from the original profile:**
  - poster-grid rendering;
  - per-figure chart styling (`plotly_defaults`);
  - `build_context` redoing the rated-films merge, the gender map and the
    reach map on every rerun, uncached.

Phase 3 starts when you say so.
