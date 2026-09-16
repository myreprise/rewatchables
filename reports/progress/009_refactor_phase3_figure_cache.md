# 009 — Phase 3, option A: charts a widget doesn't affect are built once

Date: 2026-09-16. Branch: `refactor/phase-3-performance`. Nothing is merged
into `master`.
Previous: [008 — phase 3, first pass](008_refactor_phase3_performance.md),
which set out options A–D. You chose A.

## TL;DR

Changing a picker used to rebuild every chart in its section, including the
ones the picker never touches. Those charts are now built once per database
and reused.

**Per widget change, measured interleaved** (the cache on and bypassed
alternately, each run a real widget change):

| Section | Cache off | Cache on | Change |
| --- | ---: | ---: | ---: |
| Genres | 289 ms | 59 ms | **−80%** |
| Actors | 451 ms | 191 ms | **−58%** |
| Directors | 259 ms | 150 ms | **−42%** |
| Cruise vs. Hanks | 218 ms | 145 ms | **−34%** |
| Hosts & Guests | 396 ms | 324 ms | **−18%** |

Hosts & Guests gains least because its picker still drives the person's poster
grid, which cannot be cached per database.

**Nothing a visitor sees changes.** Every plotly spec and markdown block in the
five sections matches the render from before the change. That holds on the
first render and on the render after a widget change, which is the one served
from the cache: 36 chart specs.

**778 passed.**

## What changed

- **`charts.per_database(key, db_stamp, build)`** runs `build()` once per key
  and database (`st.cache_resource`) and shares the result. Its two rules:
  - the key names every input besides the database;
  - nothing may change a result once it is returned. `st.plotly_chart` only
    reads a figure; that was checked in Streamlit's source.
- **`Ctx.stamp`** is the database's modification time. Rebuilding the
  database invalidates every cached chart.
- **13 figures opt in.** The widget column is what does *not* affect them:

| Section | Figures | Widget |
| --- | --- | --- |
| Genres | frequency, share, by decade, co-occurrence | picker below them |
| Directors | leaderboard, scatter | director picker |
| Actors | leaderboard, gender split (figures and counts), scatter | actor picker |
| Cruise vs. Hanks | running margin, genre lean | verdict filter below them |
| Hosts & Guests | who's on when, who sits together | the lookup, which these heatmaps never read |

  The person spotlights depend on the pick, so they do not opt in.
- **The shared helpers take an optional `cache_key`.** That covers
  `people_leaderboard`, `people_scatter` and `gender_split_leaderboards`.
  Genres, Cruise vs. Hanks and Hosts & Guests wrap their figure code in local
  builders. The figure-building statements are unchanged apart from
  indentation.
- **`tests/test_charts.py`** pins the contract: once per key and database, a
  rebuilt database builds again, and keys do not collide.

## How it was checked

1. **A parity baseline, taken before any edit.** For each section: render, then
   change its widget, and record every plotly spec and markdown block both
   times. The same capture after the change matched exactly.
2. **Gates:** parse under 3.11, import every module, ruff, the 46 app tests,
   and the full suite.
3. **Interleaved timing** (the table above).
4. **A live Streamlit server.** In the real server the cache is shared across
   threads and sessions, which AppTest does not reproduce.
   - Three Directors picker changes, served through the cache: 4 charts each
     time, no exceptions, no server errors.
   - Genres rendered its 4 charts and opened dossiers correctly.
   - Driving the Genres dropdown from the automated browser did not work (my
     clicks opened posters, and keyboard input did not reach the menu). That
     path is covered by the AppTest parity and timing above instead.

## Open: one stall I could not explain

The first capture after the change **timed out**: an AppTest run went past 300
seconds navigating from Genres to Directors, with the machine at 71% CPU.

It did not happen again in any of these:

- the exact same sequence, on its own;
- the full capture, re-run with a watchdog set to dump every thread's stack
  after 120 seconds (it never fired);
- the 46 app tests;
- the full suite, run alongside the interleaved timing;
- the live server checks.

**The cause is unknown**, and a shared cache is the kind of change that could
cause one. If it recurs, re-run under Python's `faulthandler` stack dump (the
watchdog above); the dump will show whether a thread is stuck inside
Streamlit's cache lock.

## Seen, not claimed

On this run, the 46 app tests took 33 s and the full suite 3:07, the fastest of
any run so far. They are single runs on a machine that had just gone quiet, so
they are not evidence of a speed-up.

## What remains

Options B and C from report 008 still stand for the cost option A cannot
reach, which is the poster grids in Movie Explorer and in Hosts & Guests'
lookup:

- **B.** `st.fragment` around widget-driven regions: the highest risk.
- **C.** Paginate the grids: a UX change.
- **D.** Stop here.

## Commits

```
Phase 3: build the charts a widget doesn't affect once per database
```
