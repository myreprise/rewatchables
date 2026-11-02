# 038 — Proposal: rebuild the web app on FastAPI + HTMX

Status: proposal, Phase 0 approved 2026-11-02; later phases await the host
decisions below. Date: 2026-11-02.
Previous: [035 — deprecate Streamlit](035_streamlit_deprecation_proposal.md),
[036 — phase A](036_streamlit_phase_a_decouple.md),
[037 — Plotly template](037_plotly_template.md).

"The current web app" here means the Observable Framework site in `site/`.
Streamlit is already on its way out (035). This plan retires both, leaving one
front end.

## TL;DR

**Recommendation: go ahead with FastAPI + Jinja2 + HTMX, but stage it. Build
a small deployed slice first (Phase 1), then decide on measured numbers.** If
the slice disappoints, deleting one package gets you back to where you are now.

- **This is consolidation, not a rescue.** The current site works, reached
  parity and costs $0. The honest alternative is to finish 035 and stay static.
- **What you gain.** One language instead of about 2,200 lines of page
  JavaScript. First visits drop from about 1 MB to about 60 KB (estimated from
  measurements below). Every film gets real HTML, a real title and link
  previews. Node leaves the toolchain. The local-only Categories page gets much
  simpler.
- **What you pay.** Hosting goes from $0 to about $2–3 a month. You own uptime
  for the first time. The public address changes. Filtering stops being instant
  and becomes a network round trip.
- **The stack holds up.** Your choice fits this app. The one real addition is
  a rule: the server must stay free of pandas and Plotly, serving the
  pre-built `site.db`. That rule keeps it small enough for the cheapest host.

## What is there today

| Piece | Size | Fate |
| --- | --- | --- |
| Pipeline, steps 01–15 | unchanged | Stays. The workbook → publish routine is untouched |
| `site.sql` + `synopses.json` | 2.6 MB + 2.0 MB | Stay as the serving data |
| `site/src/queries/*.sql` | 38 files, 178 lines | **Reused as they are**, on the server |
| `tests/test_site_db.py` | 519 lines | Stays, with a new query path |
| `theme.css`, `site.css` | 1,285 lines, 97 `rw-*` classes | Reused, so the look carries over |
| 19 pages (`site/src/*.md`) | 1,688 lines | Rewritten as Jinja templates |
| 4 JS components | 490 lines | Mostly rewritten as Jinja macros and filters |
| Streamlit app | 3,643 lines, 16 test files using `AppTest` | Removed (035 Phase C) |

Phase A already did the hard part. The numbers live outside the Streamlit app,
and step 15 runs without it.

## What the measurements say

Taken today from `site/dist`, a scratch copy of `site.db`, and a throwaway
FastAPI route in the scratchpad (nothing added to the repo).

**First visit, gzipped, before posters** (level-6 gzip here; GitHub's own
compression will differ a little):

| Page | Today | Main parts today | Proposed (estimate) |
| --- | --- | --- | --- |
| Film | 1.02 MB | `site.db` 644 KB, SQLite WASM 323 KB | ~40 KB |
| Movie Explorer | 1.04 MB | the same | ~60 KB (the 460-card grid is 21.8 KB of it) |
| Chart page (Ratings) | 1.53 MB | the same + Plotly 508 KB | ~550 KB, as Plotly stays |

Later pages are cheap today because the browser has cached all of that. So the
gain is mostly for first-time visitors, who are probably most of the audience
of a site people reach through a shared link.

**What a crawler or link preview sees today.** The HTML for every film is the
same 684 characters of site furniture, titled "Film". The film only exists once
JavaScript has run.

**Server response, FastAPI + uvicorn over loopback, 300 requests each, 2 runs:**

| Request | p50 (run 1 / run 2) | p95 (run 1 / run 2) | Response, gz |
| --- | --- | --- | --- |
| `/films`, all 460 cards | 79 / 25 ms | 229 / 48 ms | 21.8 KB |
| `/films?genre=Crime&rt=60` | 27 / 11 ms | 61 / 15 ms | 4.6 KB |
| `/films?q=heat` | 10 / 7 ms | 24 / 8 ms | 0.3 KB |
| one film row, as JSON | 8 / 6 ms | 20 / 8 ms | — |

The two runs differ by up to three times, because this machine is shared and
the first run overlapped other jobs. Read them as "tens of milliseconds". Add
network time on top. A full film page runs about ten queries, not one, and
none of these figures include real page chrome.

**Memory and start-up:**

| Process | Working set | Note |
| --- | --- | --- |
| `sqlite3` + `jinja2` | 57 MB | |
| FastAPI + uvicorn serving, under load | 86–91 MB | fits a 256 MB machine |
| with `pandas` + `plotly.express` | 133 MB, 13.5 s import | **before** FastAPI, so about 160+ MB in total |

Start-up took 10–12 s here, which says little about a Linux container: this is
a contended Windows machine reading from OneDrive. Phase 1 measures it properly.

**Interactivity is small.** 12 of the 19 pages have no filter at all. Across the
site there are 17 filter controls on 7 pages, 6 sortable tables, and 1 button.

## Recommended stack

| Layer | Choice | Why |
| --- | --- | --- |
| Web framework | **FastAPI** (pin 0.162.0, latest) | Your choice, and it fits. Typed query parameters suit the Explorer's filters. Plain `def` handlers are enough, since `sqlite3` is blocking and every query takes milliseconds |
| Templates | **Jinja2** 3.1.6 + macros | `ui.js` already emits `rw-*` markup, so it maps almost line for line to macros |
| Partial updates | **HTMX 2.0.11**, vendored | The npm `latest` tag. 4.0.1 sits under `next`. Avoid attribute inheritance and the later move to 4 stays small |
| Charts | **Plotly.js, same partial bundle** | Figures stay in the `figures` table, so charts come out identical. Loaded on chart pages only |
| Small client code | **One vanilla `app.js`** (target < 100 lines) | Chart start-up, film-list arrows, table sort. No Alpine, no build step |
| Styling | **Existing `theme.css` + `site.css`** | Same look. No Tailwind |
| Data | **stdlib `sqlite3`, read-only `site.db`** | No ORM and no writes. The 38 tested queries carry over |
| Server | **uvicorn**, one worker | A site this size needs no more |
| Packaging | **Docker image**, data baked in | A deploy is atomic and a rollback is the previous image |

### Alternatives considered

| Option | Verdict |
| --- | --- |
| **Stay static** (finish 035, keep Framework) | The real rival. $0 and days of work, but keeps two languages, the 1 MB first load and empty HTML. Right if cost and zero upkeep matter more than those |
| **Litestar** + HTMX (2.25.0) | Has built-in HTMX support, and is a fair choice. Smaller community, and it saves very little here. Not worth moving away from your preference |
| **Flask** + HTMX | Would work just as well. Gives up typed parameters and offers nothing back |
| **Django** | Its best parts (ORM, admin, auth, migrations) go unused on a read-only site |
| **FastHTML, Reflex, NiceGUI** | Python-only UI layers. After leaving Streamlit, another framework that owns the rendering is the wrong direction |
| **Pre-render to static HTML** | Keeps free hosting, but means thousands of generated pages, which you rejected on 2026-10-11, and filters would still need JavaScript |

## Architecture

```
TODAY
  workbook -> pipeline -> step 15 -> site.sql (committed)
                                       -> GitHub Actions builds site.db
                                       -> browser downloads site.db + SQLite WASM,
                                          runs SQL, builds the page in JavaScript

PROPOSED
  workbook -> pipeline -> step 15 -> site.sql (committed)
                                       -> GitHub Actions builds an image with site.db inside
                                       -> FastAPI runs the same SQL, renders HTML
                                       -> browser gets HTML; HTMX swaps filter results
```

```
src/rewatchables/web/
  main.py        create_app(): routers, static files, headers
  db.py          read-only site.db; query(name, *params), section(name)
  filters.py     Jinja filters: dates, stars, money
  routes/        one module per page kind, as sections/ is organised
  queries/       moved from site/src/queries/
  templates/     base.html, pages/, partials/, macros.html
  static/        theme.css, site.css, htmx, plotly, app.js
```

Four rules:

1. **The server never imports pandas or Plotly.** `rewatchables.web` cannot use
   `presentation`, `figures` or `sections`, because they pull in pandas.
   Anything statistical stays in step 15, as the site README already says. A
   test imports `rewatchables.web` in a clean process and fails if either
   library loaded. `pyproject.toml` splits into `web` and `pipeline` extras, so
   the image installs only `web`.
2. **`site.db` is the contract.** The server never reads the 84 MB pipeline
   database. The one exception is the Categories page in local mode.
3. **A route returns a whole page, or just the fragment when `HX-Request` is
   set.** It always sends `Vary: HX-Request`, so a cache never serves a fragment
   as a page. Every filter state has a real URL, as it does today.
4. **Jinja autoescaping stays on.** No `|safe` on data, because notes and plot
   text are third-party text. All SQL uses bound parameters.

## How each interaction moves

| Today | Proposed |
| --- | --- |
| Explorer: 7 controls, filtered in the browser | `<form hx-get="/films" hx-target="#results" hx-push-url="true">`, typing debounced at ~200 ms; the JavaScript filter chain becomes one Python function over the 460 films held in memory |
| Upcoming, Keywords, Genres, Hosts, Person, Verdicts | The same pattern, 10 controls in all |
| `Inputs.table`, 6 tables | Plain `<table>` with a small client-side sort, since the rows are already in the page |
| Synopsis fetched on open | `hx-get="/movie/heat-1995/synopsis"` triggered once on `toggle`. Synopses go in SQLite, so the server loads one, not 2 MB |
| Random film button | A link to `/random`, a no-cache redirect |
| Film-list arrows (session storage) | Kept as they are for now: about 25 lines of JS |
| Spotlight charts built in the browser | A small Python function returns the same Plotly JSON as a plain dict |
| `movie?id=heat-1995` | `/movie/heat-1995`, with the old form 301-redirected |

No `hx-boost` at first. Pages this small load quickly with plain navigation, and
it spares chart pages some start-up edge cases.

## Hosting

Your site has no server today, so this is the biggest new decision.

| Host | Cost | Behaviour | Verdict |
| --- | --- | --- | --- |
| **Fly.io**, shared 256 MB | $2.19/month always on, plus small disk and bandwidth; no free tier | No cold start, Docker deploy from Actions | **Recommended** |
| **Google Cloud Run** | Likely $0 within the free tier (2M requests/month) | Scales to zero, so idle visitors wait for a cold start; more setup | Best if $0 matters most |
| **Render free** | $0 | Sleeps after 15 minutes; 30–60 s reported wake-up | Rejected for a public site |
| **Hetzner VPS** | ~€5.49 + VAT | You patch the OS; one report says the cheap plans can't currently be ordered | Rejected: more upkeep |

Prices are from search results and change often, so confirm them before signing
up. Bandwidth should be small: HTML is light and posters still come from TMDB.

## What gets worse

These are real costs, not footnotes.

1. **Filtering is slower.** Today it needs no network. After this, each change
   costs the debounce plus a round trip. That's fine close to the server and
   noticeable far from it. It's the one thing a visitor could feel get worse.
2. **The site can now go down.** GitHub Pages had no process of yours to fail.
   You'd need a `/healthz` endpoint and a free uptime check.
3. **It costs money** and needs a card on file.
4. **The public address changes.** `myreprise.github.io` can't front a server.
   Pages can only forward old links by JavaScript, so a small stub stays
   deployed there.
5. **Repeat visits pay per page.** Today, once cached, pages need nothing
   from the network except posters. After this, every page is a request.

## Rollout

Each phase runs on its own branch and PR. The sizes are rough guesses.

### Phase 0 — Clear the deck (small)

- Merge `streamlit-phase-a` into `master`. This also fixes the invisible Ratings
  scatter on the live site, which has nothing to do with this plan and is worth
  doing either way. Local `master` is itself one commit ahead of `origin`
  (f63d763), and b72f165 isn't pushed.
- Publish the workbook edit in the working tree the normal way, which has to
  run on `master`.
- Freeze the Streamlit app (035 Phase B), but **do not build Categories on
  Framework**. That work moves to Phase 3.
- Settle the decisions below.

### Phase 1 — Deployed slice, then go/no-go (1–2 sessions)

`rewatchables.web`, the layout and sidebar, Overview, the film page and the
Explorer with HTMX, plus the Dockerfile and a deploy to a staging URL. The
current site stays live and untouched.

**Gate, measured on the deployed host from where you actually use it:**

| Check | Pass |
| --- | --- |
| Filter change to updated results, p95 | ≤ 300 ms |
| First response after idle | ≤ 3 s |
| Memory under load | ≤ 200 MB |
| First visit, non-chart page, gzipped, before posters | ≤ 100 KB |
| Monthly cost | ≤ $5 |

If it fails, or the site doesn't feel better, delete `src/rewatchables/web/` and
finish 035 on Framework. Cost: a session or two and a month of hosting at most.

### Phase 2 — Port the pages (3–5 sessions)

Detail pages (keyword, person, director, actor, request), then chart sections,
then Upcoming and the 404.

**Gate: a parity harness.** It crawls the old and new sites side by side in
headless Chrome, compares visible text, and prints each difference. It covers
every list page and a sample of each detail kind, plus all 460 films once before
cutover. Chart specs must match byte for byte, since both come from `figures`.
Watch for: sort order (the browser's `localeCompare` isn't Python's default),
number rounding and date formats.

### Phase 3 — Categories and the launcher (1 session)

Categories stays local-only, with the 035 rule unchanged: **rewatchvault text
never enters anything tracked or deployed.** The server makes it simpler:

1. The data never goes through step 15.
2. The route is mounted only when `REWATCHABLES_LOCAL=1` *and* the pipeline
   database exists. The image has neither.
3. The image is built from an allow-list, so the pipeline database cannot get
   in. A CI step boots the image and fails unless `/categories` returns 404 and
   a known marker appears nowhere in it.

`launch_app.pyw` then starts uvicorn on 8577 in local mode, and no longer needs
Node. After this phase Streamlit has nothing left to do.

### Phase 4 — Cut over (1 session)

- Step 15 writes to `data/site/`; update `PUBLISHED` and `QUICK_TESTS` in
  `publish.py`. The routine stays: edit the workbook, run publish.
- Actions deploys the image on pushes to the data or `web/` paths. It runs the
  web tests first, but not `test_site_db.py`, which needs the local database;
  `publish.py` keeps running that one.
- Go live on the new address, and replace the Pages deployment with the
  forwarding stub. It handles both older address styles, `/movie/heat-1995` and
  `movie?id=heat-1995`.
- Add `/healthz` and the uptime check.

**Gate:** a publish runs end to end, with a real episode, onto the new site.
Keep the last Framework build deployable until the soak ends. One or two weeks
is plenty for a site with one maintainer.

### Phase 5 — Remove both old front ends (1 session)

Two commits, two tags, so each can be restored alone.

- **`app-final`, then remove Streamlit:** exactly 035 Phase C, including
  `streamlit` from `pyproject.toml`, `.streamlit/`, step 14 and `static/tmdb/`
  if nothing needs them, and the AppTest-only tests (moving any that check
  `analysis` or `figures`).
- **`framework-final`, then remove Framework:** `site/`, the `site-dev` launch
  configs, `build-site-branch.yml`, `copy_theme`, and the Node requirement.
- Rewrite the README and the project description around pipeline → server.

**Gate:** full test suite passes, `pip install -e .[web,pipeline]` works in a
fresh venv with no Node, and `site.sql` is byte-identical to before.

## Risks

| Risk | Mitigation |
| --- | --- |
| Port drifts from today's site | The Phase 2 harness compares every difference rather than relying on inspection |
| Framework supplies more than it looks like | `site.css` names Framework in only 5 places, but the sidebar, page layout and form styling are Framework's and must be rebuilt. Phase 1 proves this early |
| Rewatchvault text reaches the public server | Three layers in Phase 3, one of them run against the built image |
| Sharing `queries/` with two front ends during the port | Queries stay in `site/src/queries/` until Phase 4, with both sides reading them |
| Abuse of a public server | Read-only with no accounts, so it's mostly nuisance. A concurrency limit plus response caching (ETag from the `site.db` hash) should cover it |
| Fly.io changes terms | The app is one plain Docker image, so moving should be quick. A custom domain makes that move invisible |

## Decisions that are yours

Defaults in bold. Phase 0 needs 1–3; the rest can wait for Phase 1.

1. **Go ahead with Phase 1** (recommended), or stay static and finish 035?
2. **Hosting:** **Fly.io at about $2–3/month**, or Cloud Run at about $0 with
   cold starts?
3. **Where are your readers, and you?** This decides the server region and
   whether filtering feels fine. This PC is a China-region Windows install, and
   I have not tested whether `fly.dev` or `run.app` are reachable from networks
   there. If that matters, test it first; it could change the host choice.
4. **Address:** **a custom domain (roughly $10–15/year)**, or the host's free
   subdomain? I'd pay for it. Links have already moved once, and a domain means
   they never have to move again, even if the host does.
5. **Film-list arrows:** **keep session storage**, or carry the list in the URL
   later?

## Not verified

- **Nothing here was tested on a real host.** Latency, cold start and memory on
  Linux are what Phase 1 is for.
- **Proposed page sizes are estimates.** Only the 460-card grid (21.8 KB) was
  measured, and the rest assumes CSS at most 12.8 KB and HTMX around 16 KB.
- **The spike used FastAPI 0.143.0 and uvicorn 0.30.6**, as installed here, not
  the versions proposed.
- **Effort is a judgement**, not derived from anything measured.
- **The HTMX 4 timeline comes from secondary sources.** The `latest`/`next` tags
  themselves were read from npm today.
- **Observable Framework's health isn't an argument either way.** You're on its
  latest npm release (1.13.4) and its registry entry last changed in April 2026.
  I found no announcement about its future, so this plan doesn't assume it is
  going away.

## Sources

- HTMX 4 coverage: [flaviocopes.com](https://flaviocopes.com/htmx-4.md),
  [OpenReplay](https://blog.openreplay.com/htmx-4-0-release/)
- [FastAPI templates documentation](https://fastapi.tiangolo.com/advanced/templates/)
- [Fly.io resource pricing](https://docs.fly.io/about/pricing),
  [Fly.io pricing](https://fly.io/pricing/)
- [Cloud Run pricing](https://cloud.google.com/run/pricing),
  [Google Cloud free features](https://docs.cloud.google.com/free/docs/free-cloud-features)
- Render sleep behaviour: [free FastAPI stack](https://agentdeals.dev/free-fastapi-stack),
  [Pandastack](https://pandastack.io/blog/best-fastapi-hosting-2026)
- Hetzner: [Bitdoze 2026 pricing](https://www.bitdoze.com/es/hetzner-cloud-precios-2026/),
  [cost-optimized plans](https://www.bitdoze.com/md/hetzner-cloud-cost-optimized-plans.md)
- Observable Framework: [issue #2045](https://github.com/observablehq/framework/issues/2045),
  [GitHub organisation page](https://github.com/observablehq)
