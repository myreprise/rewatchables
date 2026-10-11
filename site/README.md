# Rewatchables Explorer: the public site

A static build of the explorer for GitHub Pages, made with
[Observable Framework](https://observablehq.com/framework/). It has every
section of the Streamlit app (progress reports 013 to 016) and these pages:

| Page | Source | What it shows |
| --- | --- | --- |
| Overview | `src/index.md` | The app's front page: tiles, latest episodes, regulars, revisits, the episodes-per-year chart, a door into every section, a random film |
| Movie Explorer | `src/films.md` | Every film, with the app's filters and its nine sort orders. The filters live in the address (`/films?genre=Crime&sort=rt`) |
| Genres | `src/genres.md` | The four genre charts and the "Browse by genre" shelf |
| Directors | `src/directors.md` | Tiles, leaderboard, volume against reception, every director ranked |
| Actors | `src/actors.md` | The same, plus the gender split |
| Keywords | `src/keywords.md` | The vocabulary: reach bands, search over all of it, each decade's signature |
| Ratings | `src/ratings.md` | RT, Ebert and TMDB distributions, RT against TMDB, the divergence tables |
| Box Office | `src/boxoffice.md` | Gross, budget and return in today's dollars, with the data table |
| Hosts & Guests | `src/hosts.md` | The bench, who's on when, who sits together, each regular's leans, the episodes without Bill |
| Timeline & Revisits | `src/timeline.md` | The show over time and the films it came back to |
| Cruise vs. Hanks | `src/verdicts.md` | The standing, running margin, genre lean, tale of the tape, streaks, guests and the full ledger |
| Upcoming Films | `src/upcoming.md` | Listener requests not yet aired, with the app's four filters, the reasons, the graduates and the unmatched |
| Film | `src/movie/[id].md` | One page per film at `/movie/<title>-<year>`, e.g. `/movie/heat-1995`: the app's dossier |
| Keyword | `src/keyword/[id].md` | One page per keyword on two or more films, e.g. `/keyword/heist`: the app's keyword overlay |
| Person | `src/person/[id].md` | One page per person in the room but Bill Simmons, e.g. `/person/chris-ryan`: the Hosts & Guests lookup |
| Director, Actor | `src/director/[id].md`, `src/actor/[id].md` | One spotlight per name in the app's pickers (the top twenty of each), e.g. `/director/michael-mann` |
| Requested film | `src/upcoming/[id].md` | One page per request on the Upcoming list, e.g. `/upcoming/alien-3-1992`: the app's prospect overlay |

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
site comes from the same function the Streamlit app calls. Every chart is the
app's own Plotly figure, built by the section's `figures()`, exported as JSON
and drawn by `components/plot.js` with Plotly.js; only the width is set here.

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

## Keeping it in step with the app

A new chart or number belongs in the app first, in a function its section's
`render()` calls. Step 15 then calls the same function (one module per kind
of page in `pipeline/site_export/`), and the page here lays out what it
wrote. `tests/test_export_site.py` checks the site's numbers against the
app's and that every link lands on a page.
