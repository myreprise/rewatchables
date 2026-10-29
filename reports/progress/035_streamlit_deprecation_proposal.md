# 035 — Proposal: deprecate the Streamlit app

Status: proposal, nothing changed yet. Date: 2026-10-29.

## Why now

The public site (`site/`, Observable Framework + SQLite) reached parity with
the app on 2026-10-11 (report 016) and has run on one `site.db` since
2026-10-12 (reports 017–020). Two front ends now print the same numbers from
the same functions, and every new feature has to be built twice or decided
"app-only". The app is the more expensive one to keep: it pins `streamlit`
(and its pyarrow/tornado tree), it has its own image cache (step 14), launch
configs, a desktop shortcut, and 16 test files that drive it through
`AppTest`, the slow half of the suite.

## What the audit found

**You can't just delete the app, because the site's data is built from it.**

| Coupling | Size | Where |
| --- | --- | --- |
| Site export imports app modules | ~30 imports across 7 files | `pipeline/s15_export_site.py`, `pipeline/site_export/*.py` |
| What it imports | stats, constants and **Plotly figure builders** (`figures()`, `actor_stats`, `the_room`, `money_table`, `divergence`, `LEAN_Q`, …) that sit inside the Streamlit section modules | `app/sections/*.py`, `app/analysis.py`, `app/panels.py` |
| Data loaders | `@st.cache_data`-decorated; step 15 silences Streamlit's "no runtime" warnings to call them | `app/data.py`, `app/context.py` |
| Root-level `views.py` | imported by the pipeline (17 imports) and tests; only reachable because pytest puts `.` on the path | `views.py` |
| Parity tests | `tests/test_site_db.py` checks the site DB against the app's functions | stays useful after the move |

Sizes: `app.py` + `views.py` + `src/rewatchables/app/` = 6,638 lines.

Things that are **app-only** and need a decision rather than a deletion:

1. **Categories** (`APP_ONLY = {"categories"}`) and the categories block
   on the film dossier. They stay local because the rewatchvault text isn't
   cleared for republishing (reports 021–024).
2. **"Workbook is newer than its data" banner.** The app checks this; the
   site can't see the workbook.
3. **Poster cache (step 14, `static/tmdb/`).** Only the app uses it. The
   site loads from `image.tmdb.org`, and the export uses only
   `images.file_name()`.
4. **Desktop shortcut** (`scripts/launch_app.pyw`, `install_shortcut.ps1`,
   both uncommitted) and the Start Menu entry it installs.

## Recommended approach: decouple, freeze, remove

The usual way to retire a front end is a strangler migration. First move
everything that still depends on the old system out of it, then prove
nothing changed, then delete it in one commit you can revert. Long
deprecation windows and shims are for libraries with outside users; this
repo has one user, so the soak period can be short.

### Phase A — Decouple (no visible change)

Move the logic the site needs into Streamlit-free modules. Extend the
package rather than adding a parallel `app2`:

- `rewatchables/analysis/`: pure frame→frame statistics, taken from
  `app/analysis.py` and the non-`render` functions in each
  `app/sections/*.py` (one module per section, same names, so the
  `site_export` imports change only their path).
- `rewatchables/figures.py` (+ `palette.py`): the Plotly figure builders and
  the colour constants from `app/theme.py`. These are now *site* assets that
  ship as Plotly JSON.
- `rewatchables/data.py`: the loaders without `@st.cache_data`. Wrap them
  with `functools.cache` if a run needs caching.
- Fold `views.py` into the package (`rewatchables/presentation.py`, or split
  it between `analysis` and `figures`). Drop `"."` from pytest's
  `pythonpath`.
- Step 15 then drops its `streamlit_logger` workaround.

During this phase `rewatchables.app` imports from the new modules, so the app
keeps working. No UI is removed yet.

**Gate:** `site/src/data/site.sql` and `synopses.json` come out
**byte-identical** before and after (the dump is sorted, so this is a strict
check), and the full test suite passes, `app`-marked tests included.
Afterwards, `grep -r "rewatchables.app\|from views" src/rewatchables/pipeline`
returns nothing.

### Phase B — Freeze

- Put an `st.info` banner in `app.py` pointing to the public site, and
  label the app deprecated in `pyproject.toml` and the README.
- Feature freeze: no new app sections.
- Settle the app-only items (below).
- Use the site alone for a week or two. Anything you reach for the app to do
  becomes a site ticket or an explicit "won't carry over".

### Phase C — Remove (one commit, tagged)

- `git tag app-final` on the last commit that has the app, so it can be
  restored with `git checkout app-final -- app.py src/rewatchables/app`.
- Delete `app.py`, `src/rewatchables/app/`, `.streamlit/`, the
  `rewatchables` and `rewatchables-8502` launch configs, the `app` pytest
  marker and the AppTest-only tests. Move any test that checks a function
  now in `analysis`/`figures` instead of deleting it.
- Remove `streamlit` from `pyproject.toml` and the `app/*.css`
  package-data line, and fix the project description.
- Retire step 14 and `static/tmdb/` (keep `images.file_name`) if nothing
  else needs the local posters.
- Rewrite the README around pipeline → site, and update `site/README.md`'s
  "every section of the Streamlit app" framing.
- Run the uninstaller for the shortcut, then delete the two scripts.

**Gate:** the test suite and a clean `npm --prefix site run build` both
pass, `pip install -e .` works in a fresh venv without Streamlit, and the
site export is still byte-identical.

## Decisions that are yours

1. **Categories** — decided: (a). See the next section.
   - **(a) Local-only site page (recommended).** Add a `categories.md`
     page whose data loader reads the curated category tables from the local
     DB, with `observablehq.config.js` leaving it out of `pages` when
     `process.env.CI` is set. The text never reaches the deployed site, and
     you keep one front end. The catch is that a local build is needed to
     see it (the `site-dev` preview).
   - **(b) Drop the view.** The tables stay in the curated DB for SQL or a
     notebook.
   - **(c) Ask rewatchvault for permission**, then ship it publicly. This
     can follow (a).
2. **Workbook-staleness banner.** Default: move the check to a warning in
   `scripts/publish.py` and `orchestrate.py`, which is where it matters.
3. **Desktop shortcut.** Default: retire it and bookmark
   `myreprise.github.io/rewatchables`. Alternatively, point it at the
   local `site-dev` server if you go with (a).

## Decision taken: Categories becomes a local-only site page

Chosen 2026-10-29 (option a). This part of the work belongs in Phase B, once
Phase A has moved the category logic out of `rewatchables.app`.

The rule: **rewatchvault text never enters anything the repository tracks
or CI builds.** Three layers enforce it, because a single gate that fails
silently would publish the text.

1. **The data never goes through step 15.** A new loader,
   `site/src/data/categories.json.py`, reads the curated category tables
   straight from the local pipeline DB (`config.db_path()`, the tables
   `load_categories` reads today). Nothing goes into `site.sql`, which is
   committed. The loader's output lands in
   `site/src/.observablehq/cache/`, which is gitignored.
2. **In CI the loader emits nothing.** When `CI` is set, or the local DB is
   missing, it prints an empty payload marked `{"local_only": true}`, and the
   page shows "Categories are available in local builds only". The CI runner
   has no DB anyway; checking `CI` as well covers a future workflow that has
   one.
3. **The deploy fails if the text gets in anyway.** `deploy-site.yml` gets
   a step after `npm run build` that fails if `dist/` contains a
   category-only marker, such as a known field name from the loader. A test
   in `tests/` runs the loader with `CI=1` and asserts the empty payload.

How it looks: `categories.md` goes under "The bits" in the sidebar only when
`process.env.CI` is unset (`observablehq.config.js` already runs in Node,
so this is a one-line conditional). Framework still *builds* the page in CI
because it builds every `.md` under `src/`; layers 2 and 3 are what keep
its contents empty there. The film-page categories block (`movie.md`) reads
the same loader and renders nothing when the payload is empty.

The cost: you see Categories only through the local `site-dev` preview
(port 3200). The desktop shortcut can point there instead of being retired.
If rewatchvault gives permission later (option c), the gate is removed and
the data moves into step 15 like every other section.

To verify during implementation: whether Framework 1.13.4 leaves
`_`-prefixed pages out of the build, which would allow a fourth layer.
Don't rely on it until it's tested.

## Sequencing

- Land the in-flight category work first (`s16_load_categories.py`,
  `tests/test_category_build.py`, report 034 and the workbook edit), so it
  doesn't mix with a large move.
- Phase A is the only large step: a mechanical move of about 2–3k lines,
  checked by the byte-identical gate. B and C are small.
- Run each phase on its own branch and PR, as with PR #1.
