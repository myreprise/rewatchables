# 008 — Refactor phase 3: performance, first pass

Date: 2026-09-16. Branch: `refactor/phase-3-performance`, off
`refactor/phase-2-app-modules`. None of the refactor branches is merged into
`master`.
Previous: [007 — Refactor phase 2](007_refactor_phase2_app_modules.md).

## TL;DR

Three changes, each measured interleaved against the code it replaced, and
each committed only on a green suite:

| Change | Measured, interleaved | Where it is felt |
| --- | --- | --- |
| Gender map built in one aligned pass | 54.6 → 22.2 ms (2.5×) | Every rerun of every page |
| Streamlit usage statistics off | Movie Explorer −25%, Hosts & Guests −18%, Overview −7%, Timeline −4% | Every rerun, in proportion to element count |
| `explode_genres` vectorised | 172.6 → 14.1 ms a call (12.3×) | Genres and Timeline (twice each), Ratings, Overview, the spotlight |

**The whole app, phase 2 against phase 3.** Each version ran from its own
checkout, alternating over three rounds; figures are the median render time in
ms.

| Component | Phase 2 | Phase 3 | Change |
| --- | ---: | ---: | ---: |
| Overview | 500 | 198 | −60% |
| Upcoming Films | 531 | 351 | −34% |
| Movie Explorer | 1,216 | 839 | −31% |
| Genres | 865 | 607 | −30% |
| Keywords | 255 | 189 | −26% |
| Timeline & Revisits | 1,304 | 1,082 | −17% |
| Ratings | 1,006 | 841 | −16% |
| Hosts & Guests | 1,672 | 1,414 | −15% |
| Directors | 724 | 635 | −12% |
| Actors | 967 | 881 | −9% |
| Box Office | 1,952 | 1,817 | −7% |
| Cruise vs. Hanks | 550 | 512 | −7% |
| `build_context` (every rerun) | 101 | 73 | −28% |
| Dossier / keyword overlays | 81 / 85 | 68 / 74 | −16% / −12% |

Phase 3 was faster in every round for every section checked. Movie Explorer,
for example, ran 839, 904 and 660 ms against 1,216, 1,410 and 1,034.
**The absolute numbers are inflated, because the machine was shared.** Box
Office measured 484 ms on an idle machine this morning. Read the change
column, not the milliseconds.

**One negative result.** Styling plotly figures more cheaply did not work: a
prebuilt `go.Layout` gives an identical spec but is slower (153 → 181 ms).

## Method

**The instrument.** Timers wrap `build_context`, each section's `render` and
the three overlays. They run on the thread doing the work, driven through
AppTest, with `cProfile` for hotspots.

**Why interleaved.** The machine was not quiet: another Claude Code session
was running pytest from 16:54, and Jupyter Lab kernels had been started at
16:55. A plain before-and-after run of the first change showed every section
30–95% *slower*, after a change that touches no section. CPU time did not
rescue it; on this laptop CPU time inflates under load as well. So every claim
here comes from running the old and new code alternately, in the same process
where possible, so that any load falls on both.

**Parity.** Each change was checked against real output, not only its unit
tests:

- **Gender map:** identical for all 2,948 names, order included.
- **`explode_genres`:** the old and new implementations were swapped into the
  running app.
  - All 22 plotly specs and every markdown block in Genres, Timeline, Ratings,
    Overview and Directors came out identical.
  - The one differing block is Overview's random film spotlight. A control run
    showed it also differs between two renders of identical code.

## The baseline, and where the time went

On an idle machine at the phase 2 tip, in CPU ms per render:

| Section | Cost | Where the time went |
| --- | ---: | --- |
| Timeline & Revisits | 1,234 | ~60% plotly figure construction: ~110 ms a figure to build, ~40 ms to style |
| Hosts & Guests | 969 | ~40% poster cards (330) |
| Movie Explorer | 906 | ~65% poster cards (456): Streamlit's per-element cost, including telemetry |
| Ratings | 859 | Plotly figure construction |
| Actors | 844 | Plotly figure construction |
| Genres | 734 | ~45% `explode_genres`, the rest plotly |
| `build_context` | 94 | ~60% `gender_from_people` |

The shares come from `cProfile` and are indicative; the profiler inflates pure
Python.

## The changes

1. **`gender_from_people`.** It looked up each name twice with pandas scalar
   indexing. It now reindexes and masks in one step.
2. **`browser.gatherUsageStats = false`.** With it on, Streamlit builds a
   telemetry record for every element call, including an `inspect` of the
   caller's signature. That was about a thousand inspections per poster-grid
   render. It also stops a private app reporting usage to Streamlit. Streamlit's
   source was read to confirm the setting is read on every script run.
3. **`explode_genres`.** A filter plus `DataFrame.explode` replaces a dict per
   row. `tests/test_analysis.py` is new, since nothing pinned this function
   before:
   - five tests were written against the old version and pass on both;
   - two record deliberate differences: an empty input still has a `genre`
     column, and input dtypes are kept (`decade` stays `Int64`).

## What is left, and why it is your call

The remaining cost falls in two places:

- **Widget-driven reruns.** Changing a filter or a picker redraws the whole
  section, including charts and grids the widget does not affect.
- **Poster grids.** Streamlit's per-element cost does not shrink much further
  while every card is a plate, a button and a column.

Every way to cut these further trades something:

| Option | What it buys | What it costs |
| --- | --- | --- |
| **A. Cache widget-independent figures** per database stamp: Directors/Actors leaderboard and scatter, the Genres charts above its picker, the Cruise vs. Hanks charts | About 110–150 ms per figure off every picker change. No visible change | Moderate edits inside those sections. Figures are shared across sessions, so nothing may mutate them after building; that needs a test |
| **B. `st.fragment` around widget-driven regions** | Only the region reruns. The largest latency cut, for Explorer and Hosts & Guests especially | Interacts with the dossier gate, `keep`/`kept` and the callbacks that phase 2 kept exactly. The highest risk |
| **C. Paginate the poster grids** (e.g. 48 cards, then "Show more") | Removes most of Explorer's and Hosts & Guests' render | A UX change. The tests currently assert that every poster renders |
| **D. Stop here** | — | — |

**Recommendation: A first.** It is measurable, invisible to a visitor, and
contained. Decide B or C afterwards, with A's numbers in hand.

## Commits

```
Phase 3: vectorise explode_genres
Phase 3: turn off Streamlit's usage statistics
Phase 3: build the gender map in one aligned pass
```

775 passed at the last of them.
