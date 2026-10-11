# 015 — Site parity, phase 3: the people sections

Date: 2026-10-11. Branch: `master`.
Previous: [014 — phase 2, the chart sections](014_site_parity_phase2.md).

## TL;DR

Hosts & Guests (in full), Directors and Actors are on the public site, along
with one spotlight page for each of the 20 directors and 20 actors in the
app's spotlight pickers.

| | Before | After |
| --- | ---: | ---: |
| App sections on the site | 8 of 12 | 11 of 12 |
| Charts on the site | 24 | 32, plus 2 on each of 40 spotlights |
| Pages | 1,789 | about 1,840 |
| Tests | 883 | 885 |

Only Upcoming is left (phase 4).

**The numbers on all three pages come from the app's own functions.** For
example, Hosts & Guests gives Bill Simmons on 442 of 487 airings, the bench,
both heatmaps, all 90 lean comparisons (36 survive the correction) and the
episodes without him, grouped by host. Tests check them against the app.

## What changed

### The app: more named functions, nothing visible changed

| Module | New functions |
| --- | --- |
| `sections/hosts.py` | `figures()` (`who_is_on_when_figure`, `who_sits_together_figure`), `anchor_share()`, `without_anchor()`, `quiet_regulars()`, `top_lineups()` |
| `sections/directors.py` | `figures()` (leaderboard, scatter), `director_counts()`, `top_directors()`, `director_stats()`, `ranked_directors()`, `actors_brought_back()` |
| `sections/actors.py` | `figures()`, `cast_counts()`, `top_actors()`, `gender_credits()`, `gender_peaks()`, `has_genders()`, `actor_stats()`, `ranked_actors()`, `directors_returned_to()` |
| `panels.py` | `spotlight_figures()` (the spotlight's genre pie and decade bars), `gender_leaderboard_figs()` |
| `charts.py` | `people_scatter_fig()`, split from `people_scatter()` |

### Step 15

- **`sections.py` gains `hosts`, `directors` and `actors`.** Lean comparisons
  are formatted by `views.lean_value`, and lean chips by `lean_phrase`, as in
  the app.
- **New `spotlights.py`** writes `data/directors/<slug>.json` and
  `data/actors/<slug>.json`. Each holds:
  - the spotlight's tiles (`person_stats`);
  - its films;
  - its two charts;
  - its collaborators, each linked to their own spotlight when they have one.
- **`Addresses` now has `directors` and `actors`**, the top 20 of each.
- **`prepare()` now orders `rated` by the films' order.** Rank ties decide
  who is twentieth in the actor picker, and those depended on row order.
  No existing page changed.

### The site

- **Pages:** `hosts.md`, `directors.md`, `actors.md`, `director/[id].md`,
  `actor/[id].md`.
- **`components/spotlight.js`** is the spotlight panel, one for both, as
  `person_spotlight` is in the app.
- **The app's pickers are linked chips here:**
  - Hosts & Guests: "Look someone up" opens the person page.
  - Directors and Actors: "Director spotlight" and "Actor spotlight" open the
    spotlight pages.
- **Tables:** names in the bench and the leaderboards link to their pages, and
  the bench's episode column is drawn as a bar, as the app's ProgressColumn
  is.
- **Film page arrows:** a spotlight's posters and each "Without Bill" host's
  episodes set them.
- **Sidebar:** Directors and Actors join The films, and Hosts & Guests joins
  The show, in the app's order.

## Checked

- **Tests:** 885 pass.
  - **2 new.** One checks there is exactly one spotlight page for each name in
    the app's pickers, with that person's films and both charts. The other
    pins the Hosts, Directors and Actors numbers to the app's functions: the
    anchor share, the bench, the regulars, the 90 comparisons, the director
    and actor counts, and the gender credits.
  - **The link test now covers** the bench, the leans, "Without Bill", both
    tables and every spotlight's films and collaborators.
- **Headless Chrome against the dev server:**
  - Every chart is drawn: Hosts 2, Directors 2, Actors 4, and 2 on each
    spotlight.
  - Michael Mann's spotlight shows 9 films, and opening one gives
    "Back to Michael Mann · Film 1 of 9".

## Not done, and why

- **Spotlights only for the app's top 20 of each.** That matches the app. The
  site could give every director with two or more films (99 of them) and
  every actor with three or more a page. It would make every row of the two
  tables a link, at about 22 KB a page. Not done because it goes beyond
  parity.
- **The scatter captions quote fixed figures** ("r = 0.30 across these 97",
  "r = 0.08"), word for word from the app, and the first has already gone
  stale: 99 directors now have two or more films. They are stale in the app
  too. Computing them is a small change to make in the app first, and then
  here.
