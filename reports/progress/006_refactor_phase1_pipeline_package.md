# 006 — Refactor phase 1: the pipeline becomes a package

Date: 2026-09-15. Branch: `refactor/phase-1-pipeline-package`, off
`refactor/phase-0-foundations`. Neither is merged into `master`.
Previous: [005 — Refactor phase 0: foundations](005_refactor_phase0_foundations.md).

## TL;DR

The pipeline now lives in `src/rewatchables/`. The move carried:

- the thirteen steps;
- the orchestrator;
- the workbook converter;
- the key functions.

Every file is recorded as a rename, so `git log --follow` still reaches the
first commit. Three pieces are now shared, where every script used to carry
its own copy:

| Shared piece | What it does |
| --- | --- |
| `config` module | Anchors every path to the repo root and loads `config/.env` once |
| Logging setup | Runs only when a step is run, not when one is imported |
| `http` module | One retry policy for every API call |

Every old command still works: the `scripts/` files are now thin wrappers.
The app reads `DB_PATH` the way the pipeline does. The tests import the
package rather than loading files by path.

**768 passed.** That is the 710 tests from the start of phase 0 plus 58 new
ones. Every app section renders once with no exceptions.

| Measure | Before | After |
| --- | ---: | ---: |
| `load_dotenv` calls | 13 | 1 (`config.py`) |
| Logging configured at import (`basicConfig`) | 18 | 1 (`vendor_cmu_subset.py`, untouched) |
| Hand-written retry loops | 4 | 1 (`http.call_with_retries`) |
| Tests loading a script by file path | 18 | 3 |
| `sys.path` edits in tests | 4 | 0 |
| Log files written by *importing* the orchestrator | 1 per import | 0 |
| Tests | 710 | 768 |

**About the three remaining file-path loads.** They are the one-off tools that
stay in `scripts/`. **About the `basicConfig` count.** `config.py` now holds
the only other call, inside `setup_logging()`, which runs only when a step is
started as a program. **About the retry loops.** My proposal said there were
five. There were four, plus three single-attempt calls: step 08's detail fetch
and step 10's two batch fetches.

## Decisions

| Question | Decision | Why |
| --- | --- | --- |
| Module names | `s04_enrich.py` and so on | A module name can't start with a digit; the number is how the steps are known |
| The old paths | Wrappers built on `runpy.run_module` | Keeps every doc, log message and habit working; arguments and exit codes pass through |
| How the orchestrator runs a step | `python -m rewatchables.pipeline.sNN_…` in a subprocess | Keeps each step isolated, as before |
| `requests.Session` or `requests.get` | `requests.get`, looked up per call | The suite patches `requests.get` 37 times. A shared session would slip past those patches and could reach the real API |
| One-off tools (`migrate_*`, `vendor_cmu_subset`) | Stay in `scripts/` | Tested by path and run rarely; the migrations now import from the package |
| Committing the move | The move first, the wrappers second | A new file at an old path in the same commit stops git seeing the rename |
| A shared database-connection helper | **Deferred to phase 4** | See below |

**A deviation from the approved plan.** The plan put a shared
database-connection context manager in phase 1. Swapping one in for the 25 or
so `sqlite3.connect` calls moves where each step commits. That is a change in
behaviour, and it belongs with the phase 4 hardening work, where it can be
tested one step at a time. Paths, environment and logging are shared now;
connections are not yet.

## Behaviour that changed on purpose

| Change | Where | Before |
| --- | --- | --- |
| A 4xx other than 429 is final | Steps 09, 10 | A rejected API key was asked three times, 2 s and 4 s apart |
| A 429 or 5xx is retried | Step 04 | The search failed at once; the film waited for the next run |
| A 429's `Retry-After` is honoured, up to 60 s | All API steps | Nothing honoured it |
| A dropped connection is retried | Step 08 details; step 10 batches | One attempt; a batch fell back to empty |
| The API key is masked in the warning | Step 08 | The raw exception was logged, key included |
| Relative paths are resolved from the repo root | Every step, and the app | Resolved from the current folder; the orchestrator always ran from the root, so its runs are unchanged |
| The app reads `DB_PATH` | `app.py` | Always `./rewatchables.db`. Your `config/.env` sets exactly that, so the file is the same |
| Log format of steps 01 and 13 | Steps 01, 13 | They inherited the converter's `LEVEL: message` format only because of import order |
| `response_time_ms` includes any retries | Step 04's `api_call_log` | It timed one attempt |

## Verification

- **Full suite:** 768 passed, and ruff is clean. The three test files cleaned
  up after that run started pass on their own: 138 tests.
- **App:** one AppTest pass over all 12 sections, with no exceptions, after
  `app.py` switched to the shared config.
- **Wrappers:** `scripts/orchestrate.py --list` and `scripts/04_enrich.py --help`
  run end to end through their wrappers. `scripts/05_validate.py` exits 1 on a
  missing database, which shows the exit code passes through.
- **No stray log file:** `--list` leaves `logs/` as it was (105 files before,
  105 after).

## Found, not changed

1. **Old empty logs.** `logs/` holds 105 `orchestrate_*.log` files, 81 of them
   empty. They were written by the old import-time logging, every time a test
   imported the orchestrator. Nothing writes them now, and they are safe to
   delete.
2. **`--refresh` is only reachable directly.** The orchestrator passes steps no
   arguments, so steps 04, 09, 10 and 12 can only be refreshed by running them
   on their own, for example `python scripts/04_enrich.py --refresh`. This was
   already the case; the README says so.
3. **Still open from 005.** `data/manual_review.csv` is untracked, and
   `WIKI_USER_AGENT` in `config/.env` should be `WIKIMEDIA_USER_AGENT`.

## Commits

```
Drop the last sys.path edits from the tests
Read the database path from the shared config in the app
Route every API call through the shared retry policy
Keep the old script paths working as wrappers
Move the pipeline into the rewatchables package
Add shared config and HTTP modules to the package
```

The docs commit, holding this report, the README and `config/.env.template`,
follows them.

## Next

Phase 2 splits `app.py`, currently 5,272 lines, into
`src/rewatchables/app/`:

- theme;
- data;
- state;
- components;
- the three overlays;
- one module per section.

The sidebar rail and the link format stay exactly as they are. Phase 2 starts
when you say so.
