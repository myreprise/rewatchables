# Rewatchables Explorer: the public site

A static build of the explorer for GitHub Pages, made with
[Observable Framework](https://observablehq.com/framework/). It is a prototype
with three kinds of page:

| Page | Source | What it shows |
| --- | --- | --- |
| Overview | `src/index.md` | The app's front page: tiles, latest episodes, regulars, revisits, the episodes-per-year chart, a random film |
| All films | `src/films.md` | Every film, searchable and filtered by decade and genre in the browser |
| Film | `src/movie/[id].md` | One page per film at `/movie/<movie_id>`: the app's dossier |

## Where the data comes from

Nothing here reads the database. Pipeline step 15
(`src/rewatchables/pipeline/s15_export_site.py`) writes `src/data/` and copies
the app's stylesheet to `src/theme.css`. Both are generated: edit the pipeline
or `src/rewatchables/app/theme.css`, not these copies. They are committed, so
the deploy workflow builds from the repository alone.

The rule is to compute in Python and filter in the browser. A number on the
site comes from the same function the Streamlit app calls. The Overview's
chart is the app's own Plotly figure, exported as JSON and drawn with
Plotly.js.

## Working on it

```bash
npm install          # once
npm run dev          # live preview at http://127.0.0.1:3000
npm run build        # the static site, in dist/
```

After a pipeline run, `npm run dev` picks up the new data on reload.

## Publishing

Pushing a change under `site/` to `master` runs
`.github/workflows/deploy-site.yml`, which builds the site and deploys it to
GitHub Pages. Before the first deploy, in the repository's settings, set
**Pages → Build and deployment → Source** to **GitHub Actions**.

Links between pages are relative, so the site works at a project path
(`https://<user>.github.io/rewatchables/`) as well as at a domain root.

## Not here yet

The Streamlit app's other sections (Genres, Directors, Actors, Keywords,
Ratings, Box Office, Hosts & Guests, Timeline, Cruise vs. Hanks, Upcoming) and
its keyword and person pages. Keyword chips on a film page show their reach but
do not link anywhere yet.
