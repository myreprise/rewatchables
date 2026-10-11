# 017 — SQLite site, phase 0: the spike

Date: 2026-10-11. Branch: `sqlite-site` (not merged; the live site is unchanged).
Previous: [016 — site parity, phase 4](016_site_parity_phase4.md).

## TL;DR

The whole chain works end to end. Pipeline step 15 writes a sorted SQL dump.
A Framework data loader turns it into `site.db` at build time. One page,
`/movie?id=heat-1995`, draws any film by querying the database in the
browser.

| Question | Answer |
| --- | --- |
| How big is the database? | **1.68 MB, 536 KB as transferred** (gzipped), with the core tables. The dump is 1.45 MB and 16,321 lines |
| Does GitHub Pages compress a binary file? | **Yes.** A SQLite file on another Pages site came back as `application/octet-stream` with `Content-Encoding: gzip`: 10.5 MB transferred as 1.48 MB. No pre-compression needed |
| How fast is it? | Opening the database takes 80–350 ms, and a film's queries 2–28 ms, locally. Cold first visit: **2.5 s on fast 4G, 6.2 s on a slow 1.6 Mbps link** |
| Does the loader run on Windows? | Yes, once `interpreters` names `python` there (Framework defaults to `python3`) |
| Does the production build work under `/rewatchables/`? | Yes: the database ships as `site.909773d3.db`, with its contents' hash in the name, and the page draws correctly |
| Is the dump deterministic? | Yes: byte-identical across runs, and after a simulated rebuild that reissues every `movie_id` and shuffles every frame. No `movie_id` reaches it |

**Recommendation: go ahead with phase 1.** One cost to be aware of: a cold
first visit downloads 851 KB (the database plus the 315 KB SQLite engine)
before any data appears. On a fast connection that's under 3 seconds; on a
slow one, about 6. After that, both files are cached, and the next page
showed its data in about half a second.

## What was built

- **`pipeline/site_export/site_db.py`:**
  - `SCHEMA` defines 7 tables: `films`, `film_genres`, `film_directors`,
    `film_cast`, `film_keywords`, `episodes`, `episode_room`.
  - `tables()` fills them from the prepared context. Every key is an address
    (`heat-1995`), or for an episode, date, number and film
    (`2015-12-22-001-heat-1995`).
  - `dump()` writes `CREATE TABLE` statements, then one `INSERT` per line,
    sorted by primary key. A newline inside text becomes `char(10)` so each
    row stays on one line.
- **Step 15** writes `site/src/data/site.sql` beside the current JSON, which is
  left as it is until phase 3.
- **`site/src/data/site.db.py`**, the data loader, runs the dump in an
  in-memory SQLite, runs `ANALYZE`, and writes the database to stdout.
  Framework stores the result as `site.db`.
- **`observablehq.config.js`:** `interpreters` runs `.py` loaders with
  `python` on Windows and `python3` elsewhere.
- **`site/src/movie.md`** is the spike page. It reads `?id=` and runs 5
  queries (the film, directors, genres, episodes with the room, cast). It
  draws the hero, the episode spine and the cast with the existing
  components. Timings go to `window.__spike`.

## Measurements

Production build, served the way Pages serves it (under `/rewatchables/`,
gzipped), loaded in headless Chrome.

| Visit | Transferred | Data on screen |
| --- | --- | --- |
| Cold, local, first ever | `site.db` 536 KB, `sql-wasm.wasm` 315 KB, page code about 23 KB | 2.4 s, including Chrome compiling the engine the first time |
| Next film, local | the same files | 0.53 s |
| Cold, fast 4G (60 ms, 9 Mbps), cache off | 851 KB | 2.5 s |
| Cold, slow (150 ms, 1.6 Mbps), cache off | 851 KB | 6.2 s |

In the dev server, against 4 addresses, the film's queries took 1.7–28 ms
and opening the database 82–152 ms. The address of a missing film drew
"No film at this address." with no error.

**Compared with today's site:** a film page today downloads about 4 KB of
gzipped data. The Overview and the chart sections download Plotly, about
500 KB. The database is a larger first download than a film page has now,
but a single one: after it, every film, keyword and person comes from the
cache.

## Expected size after phase 1

Phase 1 adds the remaining tables: keywords, people, leans, shelves,
requests, the 33 section figures and the section numbers. From the current
JSON, my estimate is about 0.15–0.25 MB more, gzipped. That would put the
database near 0.7–0.8 MB as transferred. Plotly stays a separate, cached
download, loaded only by pages with a chart.

If the measured size comes out over 1 MB gzipped, the fallback is to split
off a second database for the section figures, which only the section pages
load. I don't expect to need it.

## Still to verify

- **The loader on GitHub's build machine** (`python3` on Ubuntu). It can only
  be checked when a build runs there. Phase 1 adds a build-only workflow
  for branch pushes, which builds without deploying, so this is checked
  before the switch.
- **Build time:** this build took 773 s, but it still builds all 2,049 old
  pages. Phase 3 removes them.

## Not changed

The live site and `master`. The spike is on the `sqlite-site` branch; your
weekly `publish` runs on `master` as before.
