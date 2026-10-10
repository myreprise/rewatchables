# Rewatchables Explorer: the public site

A static build of the explorer for GitHub Pages, made with
[Observable Framework](https://observablehq.com/framework/). It is being brought
up to the Streamlit app section by section; see progress report 013 for the
plan. It has these pages:

| Page | Source | What it shows |
| --- | --- | --- |
| Overview | `src/index.md` | The app's front page: tiles, latest episodes, regulars, revisits, the episodes-per-year chart, a random film |
| Movie Explorer | `src/films.md` | Every film, with the app's filters and its nine sort orders. The filters live in the address (`/films?genre=Crime&sort=rt`) |
| Keywords | `src/keywords.md` | The vocabulary: reach bands, search over all of it, each decade's signature |
| Film | `src/movie/[id].md` | One page per film at `/movie/<title>-<year>`, e.g. `/movie/heat-1995`: the app's dossier |
| Keyword | `src/keyword/[id].md` | One page per keyword on two or more films, e.g. `/keyword/heist`: the app's keyword overlay |
| Person | `src/person/[id].md` | One page per person in the room but Bill Simmons, e.g. `/person/chris-ryan`: the Hosts & Guests lookup |

A film page opened from a list (the Explorer, a keyword, a person's
episodes) steps through that list with arrows, as the app's dossier does. The
list is kept in session storage, so a film reached any other way simply has
no arrows.

## Where the data comes from

Nothing here reads the database. Pipeline step 15
(`src/rewatchables/pipeline/s15_export_site.py`, with one module per kind of
page in `pipeline/site_export/`) writes `src/data/` and copies
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

The Streamlit app's Genres, Directors, Actors, Ratings, Box Office, Hosts &
Guests (beyond the lookup), Timeline, Cruise vs. Hanks and Upcoming sections.
