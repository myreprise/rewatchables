# 010 — A public site prototype on Observable Framework

Date: 2026-10-10. Branch: `master`, uncommitted. Nothing is pushed: the repo
has no GitHub remote yet.
Previous: [009 — phase 3, option A](009_refactor_phase3_figure_cache.md).

## TL;DR

The explorer can be published as a static site on GitHub Pages without losing
what the Streamlit app computes. A new pipeline step writes the site's data;
an Observable Framework project in `site/` draws it; a GitHub Actions workflow
builds and deploys it on push.

The prototype has three kinds of page: the **Overview**, an **All films** list
with search and filters, and **one page per film** (458, at
`/movie/<movie_id>`). Built and checked locally under a GitHub Pages project
path (`/rewatchables/`). Not deployed, because there is no remote.

| What a visitor downloads | Raw | Gzipped |
| --- | ---: | ---: |
| Film page: HTML + its JSON (median) | 11 KB + 8.7 KB | ~3.5 KB of data |
| All films: the index of 458 films | 264 KB | 97 KB |
| Overview: Plotly (cartesian bundle) | 1.54 MB | 507 KB |
| Overview: everything else in its data | 15 KB | 3.5 KB |

**Reusing the app's Plotly figures works, but costs 507 KB gzipped on any page
with a chart.** The full Plotly bundle would cost 1.48 MB; the cartesian
partial bundle covers every trace type the app draws (bar, box, heatmap,
histogram, image, pie, scatter) at a third of that.

**Tests.** 821 passed. The one other test fails because of two new rows in
the workbook, not because of this change; see "Tests" below.

## What changed

### Pipeline step 15: `s15_export_site.py`

Writes `site/src/data/` (4.3 MB of JSON) and copies `theme.css` to
`site/src/theme.css`. It runs at the end of every default pipeline run and is
required, not optional: a failed export would leave the site silently stale.

- **It uses the app's loaders and helpers**: `build_context`, and the new
  functions below, so the site and the app print the same numbers. A test
  checks that the overview's tiles equal `show_now()`.
- **The output is deterministic**: no timestamps, stable ordering, one film per
  line in `films.json`. A test runs the export twice and compares bytes, so a
  commit after a pipeline run shows only the films that changed.
- **A film that leaves the catalogue loses its page.** Stale per-film files are
  deleted (tested).
- **It writes no NaN.** Every file is parsed with NaN and Infinity refused
  (tested), because the browser's `JSON.parse` rejects them and the page would
  fail without saying why.
- **Posters are not exported.** The site loads them from TMDB's CDN, the same
  fallback the app uses. `static/tmdb/` stays unpublished.

Runtime is about 20–30 s: 5 s of imports, 3 s for `build_context`, about 9 s
for the 458 film pages, and the rest writing 460 files into OneDrive.

### Small extractions in the app, so both front ends share one definition

- `sections/overview.py`: `show_now()`, `regulars()`, `came_back_to()` and
  `episodes_per_year()` are taken out of `render()`. `render()` calls them, and
  the Overview is unchanged.
- `overlays/dossier.py`: `cast_billing()`, `same_director()` and
  `shared_cast()` are taken out of `render_dossier()` the same way.

### `site/`: the Observable Framework project

- `src/index.md`, `src/films.md` and `src/movie/[id].md` are the pages.
  `components/ui.js` emits the same `rw-*` markup as `components.py`, so the
  copied stylesheet styles both. `site.css` adds only the layout that
  `st.columns` used to provide.
- **The Overview's chart is the app's own figure**: built by
  `episodes_per_year()` in Python, exported with `fig.to_json()`, and drawn by
  Plotly.js. Only the width is set in the browser.
- **The filters are Framework's built-in inputs**: search, a decade select, a
  genre select and a sort. They filter 458 rows in the browser with no
  noticeable delay.
- Links are relative, so the same build works at `user.github.io/rewatchables/`
  and at a domain root. Checked with a local server that mimics Pages' path and
  clean-URL rules.

### `.github/workflows/deploy-site.yml`

On a push touching `site/`: `npm ci`, `npm run build`, upload, deploy to Pages.
No Python and no secrets. The one-time manual step is setting Pages' source to
"GitHub Actions" in the repository settings.

## Findings

1. **The stylesheet carries one Streamlit-only escape.** The gap marker is
   written as a doubled-backslash `2304` escape because Streamlit's markdown
   step strips one backslash. Served as plain CSS, it printed the literal
   escape. `site.css` restates the rule. Every other rule in `theme.css` worked
   unchanged.
2. **`htl` wraps a multi-node template in a `<span>`**, which picked up the
   cast-chip styling and nested a chip inside every chip. Fixed with
   `html.fragment` wherever a template has more than one top-level node.
3. **Framework's dark theme name is not `theme-dark`.** The build failed until
   it used `near-midnight` plus `wide`.
4. **The film pages' `<title>` is "Film" until JavaScript runs.** It is fixed
   on load, but a link preview in Slack or iMessage reads the static title.
   Generating real titles needs either per-film `.md` files written by step 15,
   or a static heading built from the route parameter.
5. **Build time.** `observable build` took 82–132 s locally, mostly writing
   458 pages into OneDrive. CI on Linux should be faster; not yet measured.

## Tests

- `tests/test_export_site.py`: 15 cases. The pure helpers, plus checks against
  the live database: every film has exactly one page, the index matches the
  pages, no file holds NaN, the overview's numbers equal the app's, the
  episodes match the links, shelves never contain the film itself, and the
  export is deterministic.
- `tests/test_orchestrate.py`: `--stages site` selects step 15.
- Full suite: 736 passed, then stopped (`-x`) at
  `test_the_workbook_renders_to_exactly_the_tracked_csv`. That failure predates
  this work: two rows newly added to `data/episodes.xlsx` have air dates typed
  as text (row 495, ep 484, *The Texas Chain Saw Massacre*: `'10/5/2026'`).
  Step 01 would reject them the same way. With that one test deselected:
  **821 passed**.

## Not done

- Not committed, and not deployed: there is no GitHub remote, and creating a
  repository is your call.
- The other ten sections and the keyword and person pages. On a film page,
  keyword chips show their reach but do not link anywhere yet.

## Next

1. Create the GitHub repo, set Pages' source to Actions, push. The first CI
   build gives the real build time.
2. Fix the static film-page titles (finding 4).
3. Port sections in order of reuse. Sections whose charts don't depend on a
   widget can export their figures directly, as the Overview does. Charts that
   respond to a picker need either a figure per option, which is cheap when
   the options are few, or a JavaScript rewrite.
