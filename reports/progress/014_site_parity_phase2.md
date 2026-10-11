# 014 — Site parity, phase 2: the chart sections

Date: 2026-10-11. Branch: `master`.
Previous: [013 — phase 1, the Explorer, keywords and people](013_site_parity_phase1.md).

## TL;DR

Five more of the app's sections are on the public site: **Genres, Ratings,
Box Office, Timeline & Revisits and Cruise vs. Hanks**. Between them that is
23 charts, 7 tables, the Genres shelf and the Cruise vs. Hanks ledger. The
sidebar is now grouped as the app's is (Find / The films / The show / The
bits).

| | Before | After |
| --- | ---: | ---: |
| App sections on the site | 3 of 12 | 8 of 12 |
| Charts on the site | 1 | 24 |
| Tests | 881 | 883 |

Still to come: Directors, Actors, Hosts & Guests in full (phase 3), and
Upcoming (phase 4).

**Every chart is the app's own figure.** The section's `figures()` builds it,
in the app and in step 15 alike, and the site draws the exported JSON with
Plotly.js.

**Checked against the app:**
- **Cruise vs. Hanks ledger:** filtered to Cruise and "top", the site shows
  *Over the Top*, ep 374, the one row the app's frame gives.
- **Box Office data table:** opens on Titanic ($4.4B, 11.3×), then Star Wars,
  the app's order.
- **Tests** pin the tiles, the divergence tables, the ledger and the running
  margin to the app's functions.

## What changed

### The app: each section's charts and numbers are named functions

The same pattern as phase 1. Each `render()` now calls functions that step 15
calls too. Nothing the app shows changed.

| Section | New functions |
| --- | --- |
| `ratings.py` | `figures()` (5 charts), `divergence()`, `rated_episodes()`, `scored_films()` |
| `boxoffice.py` | `figures()` (4), `summary()` (every tile and caption number), `returns()`, `money_table()`, `money_frames()` |
| `timeline.py` | `figures()` (8), `oldest_discussed()`, `revisited_films()`, `ages_at_airing()` |
| `genres.py` | `figures()` (4) over a `FIGURES` map. `render()` still caches each chart once per database, as before |
| `verdicts.py` | `figures()` (2), `standing()`, `running_margin()`, `tale_of_the_tape()`, `streaks()`, `guest_split()`, `rail_films()`, `films_with()` |

**One small app change:** lean chips tied on q-value now sort by the measure's
name. Before, their order followed the database's row order, so a rebuild
could swap two chips, and the export showed it (Kyle Brandt's "Action" and
"films 8 yr older" traded places).

### Step 15: the episode frames are put in a fixed order too

The links query (`app/data.py`) has no `ORDER BY`, so its rows, and `merged`'s,
come back in whatever order step 06 inserted them. A chart lists its points in
frame order. A permutation test with a fixed seed also gives slightly
different p-values when its rows arrive in a different order.

`prepare()` now sorts `links`, `merged` and `cruise_hanks` by airing date,
episode number and film address. The rebuild test now shuffles all three as
well as the films, and the export still comes out byte for byte the same.

The app itself still reads the frames in database order. In the app, that
means a lean's p-value can move in its third decimal after a rebuild. The
site's cannot.

### Step 15: `site_export/sections.py`

One file per section, `data/sections/<name>.json`. Each holds:
- the section's figures, as Plotly JSON;
- the numbers its tiles and captions print;
- its table rows, with each film's address so titles link.

Money is formatted by `views.money` in Python, so the site prints `$4.4B` the
way the app does. The Box Office data table also carries the raw figures, so
it sorts by value rather than by text.

| File | Raw | Gzipped |
| --- | ---: | ---: |
| `boxoffice.json` | 227 KB | 61 KB |
| `timeline.json` | 145 KB | 14 KB |
| `ratings.json` | 128 KB | 21 KB |
| `verdicts.json` | 61 KB | 13 KB |
| `genres.json` | 42 KB | 3 KB |

Plotly itself is the larger cost: about 500 KB gzipped, once per visitor, and
cached across pages after that. This was decided in the parity plan.

### The site

- **`components/plot.js`** draws a figure at the page's width. The Overview
  uses it now too, so only pages with a chart load Plotly.
- **Five pages:** `genres.md`, `ratings.md`, `boxoffice.md`, `timeline.md`,
  `verdicts.md`. Each follows the app's section top to bottom, with the same
  headings and captions.
  - **Filtering in the browser:** the Genres shelf (from `films.json`, best
    rated first, top 30) and the Cruise vs. Hanks ledger (verdict and title
    filters, with the verdict band on each card).
  - **Arrows on film pages:** posters on the Genres shelf, in the revisited
    films, and in the ledger set the "Back to …" and ‹ › arrows.
  - **Links:** film titles in tables link to their pages, and guest names in
    "Who's in the room" link to their person pages.
- **The sidebar** is grouped as in the app's `state.NAV`. Sections the site
  does not have yet are left out rather than shown empty.

## Checked

- **Tests:** 883 pass. The 2 new tests check that every section ships every
  chart it should, and that the section numbers match the app's
  (`summary()`, `divergence()`, `standing()`, `running_margin()`, the ledger).
  The link test now also covers every table and grid in the sections.
- **Headless Chrome against the dev server:**
  - Each of the five pages renders every chart (5, 4, 8, 4 and 2), with no
    errors.
  - The Box Office table sorts and links.
  - The ledger filters to the right rows.
  - The Genres shelf switches genre (Western: 6 films).

## Not done, and why

- **Each chart is drawn at full width or in the app's columns, with Plotly's
  default height**, as `st.plotly_chart` draws it. The Ebert stars' tick
  labels crowd at a third of the page width. They do in the app too, so I
  left it as it is.
