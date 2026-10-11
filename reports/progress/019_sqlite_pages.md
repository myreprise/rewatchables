# 019 — SQLite site, phase 2: the pages

Date: 2026-10-12. Branch: `sqlite-site` (not merged; the live site is unchanged).
Previous: [018 — phase 1, the database](018_sqlite_database.md).

## TL;DR

(The live site's page count is about 2,637 since the spotlight expansion of
2026-10-11; earlier reports quote 2,049, from before it. Its `dist/` was 43 MB
before that expansion.)

Every page now reads `site.db` and queries it in the browser. The per-film
pages are gone: each kind of detail view is one page that reads what to show
from its address.

| | Live site (JSON) | This branch (SQLite) |
| --- | ---: | ---: |
| HTML pages built | about 2,637 | **20** |
| Build time (this machine) | 773 s | **18 s** |
| `dist/` | over 43 MB | **6.6 MB** |
| Data files deployed | 2,638 | **3** (`site.db`, `queries.json`, `synopses.json`) |
| Film address | `/movie/heat-1995` | `movie?id=heat-1995` (old links forward) |

**Checked against the live site:** 19 pages compared line by line, each
against the same page on the live site, whose numbers were tested against
the app. 15 match exactly, including all 672 lines of Chris Ryan's person
page, the whole Hosts & Guests section, Keywords, Upcoming, Box Office,
Ratings and Timeline. The remaining four differences:

- **Overview:** the random film, as it should.
- **One keyword's "vs. catalogue" tile** reads −0.0 where the live site says
  +0.0. The new page agrees with the app (Python formats −0.02 as "−0.0").
  The old export had rounded the sign away.
- **Two bugs**, both found by this comparison and fixed (below).

## What changed

### Data access: `components/db.js`

- **One module opens `site.db`** once per page and runs named queries.
  `query(name, …params)` and `row(…)` run any query from `src/queries/`.
- **The queries arrive in one file.** A second data loader,
  `queries.json.py`, bundles them into `queries.json`, so a page makes one
  request for its SQL.
- **Section pages:** `section(name)` returns a section's stored numbers and
  charts in the same shape the old JSON had, so their layout code didn't
  change. The tables now drawn from queries (the Box Office data table, the
  ledger, the bench, the lean comparisons, "Without Bill", the director and
  actor tables) are mapped back into that shape.
- **Synopses:** `synopsis(slug)` fetches `synopses.json` only when a reader
  opens one.
- **Rounding:** `roundEven()` rounds half to even, as Python does.

### Pages

- **Six detail pages:** `movie.md`, `keyword.md`, `person.md`,
  `director.md`, `actor.md` and `request.md` replace the `[id]` templates
  and their 2,624 generated pages (460 films, 1,265 keywords, 62 people,
  260 directors, 367 actors, 210 requests).
- **The keyword page** computes its rail (share, peak decade, average TMDB
  against the catalogue, the region line) from queries. The arithmetic is
  the overlay's `keyword_profile`, line for line.
- **The spotlights' two small charts** (genre mix, films by decade) are drawn
  in the browser from the films, in the app's colours. Storing a pair for
  each of 627 people was what bloated the old export. Their tiles come from
  the Python-computed `directors` and `actors` tables.
- **Links:** `pageHref(kind, id)` in `ui.js` builds every link
  (`movie?id=…`, `keyword?id=…`, and so on). All pages sit at the top of the
  site, so every link is `./`.
- **`404.md`** forwards an old address (`/movie/heat-1995`, `/keyword/…`,
  `/person/…`, `/director/…`, `/actor/…`, `/upcoming/<request>`) to its new
  one. It uses a plain script, so it runs even though the page is served at
  the old, deeper path.
- **The config** no longer reads any data or lists `dynamicPaths`.

### Database additions

- **`episodes` gains `gap_before` and `revisit_kind`**, the spine's "4 yr 1
  mo later" and "regular", computed exactly as the film pages compute them
  (tested against the old export's `episode_rows`).
- **Two new queries:** `catalogue` (films, average TMDB, airings) and
  `region_films`, the films under a place keyword's region. Both are tested
  against `keyword_profile`. That makes 38 queries and 30 tests in
  `test_site_db.py`, all passing.

## Bugs found and fixed

1. **A stale database, which would also have hit production.** Framework
   caches a data loader's output and reruns the loader only when the loader
   file changes, not when the `site.sql` it reads changes. After a publish,
   a cached `site.db` could have been served.
   - Step 15 now touches `site.db.py` whenever it writes the dump.
   - `deploy-site.yml` deletes the loaders' cached output before every build.
     Rebuilding the database takes seconds.
2. **The tale-of-the-tape columns came out alphabetical.** I had stored
   section values with sorted JSON keys, and that table takes its column order
   from its keys. Keys now keep the order the section builders give them,
   which is fixed, so the dump stays deterministic.
3. **Half-way rounding.** Two directors' average runtimes showed 97 instead
   of 96, because JavaScript rounds half up and the app rounds half to even.
   `roundEven()` fixes it in the director, actor and bench tables.
4. **Name clashes:** on Keywords and Upcoming, a search box called `query`
   clashed with the database helper, so they import it as `dbQuery`. The
   README notes this.

## Checked

- **All 19 kinds of page**, on the dev server and on the production build
  served gzipped under `/rewatchables/` (headless Chrome):
  - every chart drawn: Ratings 5, Box Office 4, Timeline 8, Genres 4,
    Cruise vs. Hanks 2, Hosts 2, Directors 2, Actors 4, each spotlight 2;
  - every grid full: Explorer 460, Upcoming 210, Chris Ryan 287;
  - no errors.
- **Interactions:**
  - Explorer filtered to Crime, RT ≥ 90 shows 32 films. Opening the second
    gives "Film 2 of 32", and ‹ › step through the list.
  - Back returns to the same filters.
  - From a film page: keyword chip → keyword page, room name → person
    page, director → spotlight.
  - Upcoming poster → request page.
  - The full synopsis loads when opened.
- **Old links:** `movie/heat-1995`, `keyword/heist`, `person/chris-ryan`,
  `director/michael-mann`, `actor/tom-hanks` and `upcoming/alien-3-1992` all
  arrive at their new pages. An unknown address shows "Page not found".

## Next: phase 3, the switch

- Delete the per-page JSON exporters and the 2,638 JSON files.
- Point `publish.py`'s quick tests at `test_site_db.py`.
- Merge to `master` and deploy, then check the live site.
