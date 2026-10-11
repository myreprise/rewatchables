# Rewatchables Explorer: the public site

A static site for GitHub Pages, made with
[Observable Framework](https://observablehq.com/framework/). Every page reads
one SQLite database, `site.db`, and queries it in the visitor's browser. It
has every section of the Streamlit app.

## Pages

One page per section, and one per kind of detail view. A detail page reads
what to show from its address, so the site is the same 20 pages however
many films there are.

| Page | Source | What it shows |
| --- | --- | --- |
| Overview | `src/index.md` | The app's front page: tiles, latest episodes, regulars, revisits, the episodes-per-year chart, a door into every section, a random film |
| Movie Explorer | `src/films.md` | Every film, with the app's filters and its nine sort orders. The filters live in the address (`films?genre=Crime&sort=rt`) |
| Genres, Directors, Actors, Keywords, Ratings, Box Office | `src/genres.md` … `src/boxoffice.md` | The app's "The films" sections |
| Hosts & Guests, Timeline & Revisits | `src/hosts.md`, `src/timeline.md` | The app's "The show" sections |
| Cruise vs. Hanks | `src/verdicts.md` | The standing, running margin, genre lean, tale of the tape, streaks, guests and the full ledger |
| Upcoming Films | `src/upcoming.md` | Listener requests not yet aired, with the app's four filters |
| Film | `src/movie.md` | `movie?id=heat-1995`: the app's dossier |
| Keyword | `src/keyword.md` | `keyword?id=heist`, for every keyword on two or more films: the app's keyword overlay |
| Person | `src/person.md` | `person?id=chris-ryan`, for everyone in the room but Bill Simmons: the Hosts & Guests lookup |
| Director, Actor | `src/director.md`, `src/actor.md` | `director?id=michael-mann`: a spotlight for every director, and every actor on three or more films |
| Requested film | `src/request.md` | `request?id=alien-3-1992`: the app's prospect overlay |
| Not found | `src/404.md` | Forwards an old address (`/movie/heat-1995`, from before October 2026) to its new one |

A film page opened from a list (the Explorer, a keyword, a person's episodes,
a spotlight) steps through that list with arrows, as the app's dossier does.
The list is kept in session storage, so a film reached any other way simply
has no arrows.

## Where the data comes from

```
pipeline step 15 ──> src/data/site.sql        the database as a sorted SQL dump (committed)
                     src/data/synopses.json   full Wikipedia synopses (committed)
data loaders     ──> site.db                  built from site.sql at build time (src/data/site.db.py)
                     queries.json             every query in src/queries/ (src/data/queries.json.py)
pages            ──> components/db.js         opens site.db once, runs named queries
```

- **Step 15** (`src/rewatchables/pipeline/s15_export_site.py`, with the
  database in `pipeline/site_export/site_db.py`) writes the dump and the
  synopses, and copies the app's stylesheet to `src/theme.css`. These are
  generated: edit the pipeline or `src/rewatchables/app/theme.css`, not the
  copies.
- **Why a dump:** the repository tracks `site.sql` rather than the binary
  database. It is sorted, one row per line, so a new episode is a diff of the
  rows it changed, not a whole new file.
- **The data loader** builds `site.db` from the dump when the site is built.
  A visitor downloads it once: about 650 KB, compressed by GitHub Pages.
- **Who computes what.** Python computes anything with a ranking rule or a
  statistic and stores it as a table: the related-film shelves, keyword
  reach, the bench, the permutation-tested leans, director and actor
  statistics. The browser only filters, joins and counts, in SQL. Every
  section chart is the app's own Plotly figure (the `figures` table), drawn
  by `components/plot.js`. The spotlights' two small charts are drawn in the
  browser from the films query.
- **The queries** live one per file in `src/queries/`. Each file's first
  comment names the app function it must agree with, and
  `tests/test_site_db.py` runs the same files against the same database and
  checks the answers against those functions.

## Working on it

```bash
npm install          # once
npm run dev          # live preview at http://127.0.0.1:3000
npm run build        # the static site, in dist/ (about 20 seconds)
```

Framework reruns a data loader only when the loader file changes, not when
the data it reads does. Step 15 touches `src/data/site.db.py` whenever it
writes the dump, so a preview picks up a pipeline run on reload. After
editing a query, touch `src/data/queries.json.py` the same way.

Two names are taken on every page: `view` (Framework's) and anything a page
imports. A page with a search box called `query` imports the database
helper as `dbQuery`.

## Publishing

Pushing a change under `site/` to `master` runs
`.github/workflows/deploy-site.yml`, which builds the site and deploys it to
GitHub Pages. It clears the loaders' cached output first, so `site.db` is
always rebuilt from the `site.sql` being deployed. A push to any other branch
runs `build-site-branch.yml`, which builds without deploying.

Links between pages are relative, so the site works at a project path
(`https://<user>.github.io/rewatchables/`) as well as at a domain root.

## Keeping it in step with the app

A new chart or number belongs in the app first, in a function its section's
`render()` calls. Then either step 15 stores what it computes (a ranking or a
statistic), or a query in `src/queries/` derives it (a filter or a count),
with a test in `tests/test_site_db.py` comparing it with the app's function.
The page lays out the result.
