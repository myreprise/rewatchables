# 005 — Refactor phase 0: foundations

Date: 2026-09-15. Branch: `refactor/phase-0-foundations`.
Previous: [004 — The episode list moves to `data/episodes.xlsx`](004_episode_workbook_source.md).

## TL;DR

Phase 0 of five in the approved refactor plan. The phases are foundations, an
importable pipeline package, splitting `app.py`, performance, and hardening.
Nothing the app or the pipeline does has changed. What changed:

- the project installs from one correct dependency list;
- plain `pytest` works;
- there is a quicker test loop that skips the app tests;
- lint is clean;
- the README describes the project as it is now.

All 710 tests pass.

| Measure | Before | After |
| --- | --- | --- |
| Dependency list | `requirements.txt`: 1 version that doesn't exist, 3 packages missing | `pyproject.toml`: pins equal to what is installed |
| `pytest` (plain) | Stops at collection: `views` can't be imported | 710 collected, 710 passed |
| Full suite | 710 passed, 6m 46s | 710 passed, 5m 15s (see note) |
| `pytest -m "not app"` | — | 664 passed, 46 deselected, 2m 24s |
| `ruff check .` | 18 errors | 0 |

**Note on the full-suite time:** nothing in phase 0 should change it. The
6m 46s baseline was the session's first run. Treat the gap as run-to-run
variance, not a gain.

## Decisions

| Question | Decision | How it was applied |
| --- | --- | --- |
| Dependency source | `pyproject.toml` only | `requirements.txt` removed; `pip install -e ".[dev]"` |
| Pin style | Exact (`==`), equal to the installed versions | `pip install --dry-run` showed nothing to change; the real install only added `rewatchables` itself |
| Streamlit | Stay on 1.41.1 | Upgrade later as its own step |
| Package | Empty `src/rewatchables/` created now | So the editable install has a target; filled from phase 1 |
| Test import path | `pythonpath = [".", "scripts"]` in the pytest config | Replaces the `sys.path.insert` in `conftest.py` |
| Marking app tests | Derived from the test source, not applied by hand | A test is marked `app` if it, or a fixture it uses, mentions `AppTest` |
| Lint rules | Ruff defaults | The complexity rules (41 hits) wait for the `app.py` split |
| Branching | One branch per phase | There is no remote and no `main`, so each phase is a local branch to merge |

## What was built

- **`pyproject.toml`**: dependencies, the `dev` extra (pytest, ruff), the
  pytest config (`testpaths`, `pythonpath`, `--strict-markers`, the `app`
  marker) and the ruff config. `.claude/` is excluded from ruff because it
  holds full copies of the repo in agent worktrees.
- **`tests/conftest.py`**: the `sys.path` hack is gone. A collection hook marks
  the app tests. `NAV_GROUPS`, `goto` and `film_count` are unchanged.
- **`config/.env.template`**: every variable the code actually reads, with its
  default. The README had pointed at this file, but it didn't exist.
- **README**: rewritten to the current state. It now covers:
  - all 13 steps and the orchestrator's options;
  - the review workflow and the rebuild guard;
  - the actual tables and views.

  Every SQL query in it was run against `rewatchables.db`. The made-up
  *Fight Club* revisit example is replaced with a real one, *A Few Good Men*
  (episodes 7 and 320).
- **The 18 lint fixes**:
  - unused imports in four scripts and one test;
  - an unused variable in step 07;
  - an f-string without placeholders in `app.py`;
  - imports moved to the top of `03_normalize_and_resolve.py` and three test
    files;
  - a lambda turned into a `def`;
  - a line with two statements split in two.

  None changes behaviour.

The app tests, per file:

| File | `app` tests |
| --- | ---: |
| `test_dossier.py` | 17 |
| `test_keywords.py` | 10 |
| `test_box_office.py` | 6 |
| `test_hosts.py` | 5 |
| `test_people_gender.py` (`TestActorsSectionSplit`) | 4 |
| `test_upcoming.py` (`TestSection`) | 4 |

## What the fast loop shows

Skipping the 46 app tests takes the suite to 2m 24s, about half the full run.
That is not fast. The remaining time is spread thinly: no single test takes
more than 1.7 s. It clusters in the pipeline tests:

| File | Time |
| --- | ---: |
| `test_curated_build.py` | 19.2 s |
| `test_plot_summaries.py` | 18.9 s |
| `test_metadata_enrich.py` | 14.3 s |
| `test_cmu_load.py` | 14.3 s |
| `test_compact_raw_zone.py` | 9.8 s |

These probably build a fresh SQLite database from the schema files for each
test. That is **not verified**. If it holds, the fix is to build a template
database once per session and copy it per test; that belongs in phase 3.

The app tests are slow for a different, measured reason. AppTest re-applies
Streamlit's script transform to all of `app.py` on every run: 0.6–0.8 s,
against 0.03 s for `views.py`. The production server caches this; AppTest
does not. Splitting `app.py` in phase 2 is what fixes it.

## Found, not changed

1. **Review decisions aren't in version control.** `data/manual_review.csv`
   holds 10 hand-made decisions. It is the file step 08 replays after a
   rebuild, but the `data/*.csv` rule in `.gitignore` excludes it.
   `manual_review.prior.csv` is likewise untracked. Tracking the file is one
   line in `.gitignore`, but the choice is yours.
2. **The Wikimedia User-Agent setting is ignored.** Local `config/.env` sets
   `WIKI_USER_AGENT`, but steps 10 and 12 read `WIKIMEDIA_USER_AGENT`, so the
   built-in default is sent. Rename the key in `config/.env` to use your own.
   The same file also carries four keys nothing reads:
   - `GOOGLE_SHEETS_WORKSHEET_ID`
   - `GOOGLE_SHEET_GID`
   - `LOG_FILE`
   - `API_RATE_LIMIT_BACKOFF_SECONDS`
3. **The app ignores `DB_PATH`.** It always reads `./rewatchables.db`. The
   template and README say so; phase 1's shared config fixes it.
4. **Left alone:** `PROJECT_PLAN.md` (historical), the untracked 14 MB
   `rewatchables.db.pre-xlsx-20260915_152947.bak`, and `.claude/`.

## Next

Phase 1 moves the pipeline into `src/rewatchables/`:

- shared config, connection and logging setup;
- one HTTP client with a single retry and backoff policy, replacing five loops;
- importable step modules, with `git mv` so history is kept.

Tests then drop their 18 `importlib` loads. `python scripts/orchestrate.py`
keeps working through a thin wrapper.
