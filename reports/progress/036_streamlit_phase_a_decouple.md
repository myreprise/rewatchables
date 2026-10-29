# 036 — Deprecating Streamlit, phase A: decouple

Date: 2026-10-29. Branch `streamlit-phase-a`.
Previous: [035 — proposal](035_streamlit_deprecation_proposal.md).

## TL;DR

The code the site export needs has moved out of `rewatchables.app` into
Streamlit-free modules. Step 15 now runs without importing Streamlit. The
exported `site.sql`, `synopses.json` and `theme.css` are **byte-identical** to
the baseline taken before the change. The app still works and still draws
everything.

The move turned up a bug on the **live site**. The Ratings page's "RT vs TMDB"
scatter draws its 16 genre traces in `#000001`–`#000010` on a `#101211`
background, so they are effectively invisible. Phase A keeps that output
exactly as it was, as a refactor should. The fix is the next decision (see
the end of this report).

## What moved

| New module | From | What it holds |
| --- | --- | --- |
| `presentation.py` | `views.py` (repo root, `git mv`) | labels, links, money, the room statistics |
| `analysis.py` | `app/analysis.py` (`git mv`) | frames in, numbers out |
| `data.py` | `app/data.py` (`git mv`) | the loaders, uncached |
| `context.py` | `app/context.py` (`git mv`) | `Ctx` and `build_context(db_stamp, loaders)` |
| `palette.py` | `app/theme.py` | the colours |
| `figures.py` | `app/charts.py`, `app/panels.py` | `plotly_defaults`, the folding helpers, figure builders |
| `sections/__init__.py` | `app/state.py` | `NAV`, `SLUGS`, `APP_ONLY`, `SITE_SLUGS`, labels |
| `sections/<name>.py` ×12 | `app/sections/<name>.py` | each section's numbers and figures: everything but `render` |
| `overlays/dossier.py`, `overlays/keyword.py` | `app/overlays/` | `same_director`, `shared_cast`, `cast_billing`, `keyword_profile` |

That is 164 top-level names and 174 import statements, moved by script and
reviewed by hand. The app's Python went from 6,009 lines to 3,643; the shared
modules are 3,249. Nothing outside `app/` imports Streamlit or
`rewatchables.app`.

Categories moved too (`sections/categories.py`: lifespans, people ranking,
lifespan figure, family labels). Phase B's local-only page will need them
outside the app. They stay `APP_ONLY`.

### How the app keeps its caches

- **Loaders.** `app/data.py` wraps each core loader in `st.cache_data(ttl=300)`
  keyed on the database stamp. Each core loader takes `db_stamp` and ignores
  it, so the two share one signature, and `build_context(..., loaders=)`
  takes either.
- **The unparsed-date canary.** Core `load_data` logs a warning; the app's
  wrapper still puts the `st.warning` banner on the page.
- **`room_leans`** (the ~1 s permutation test) was `st.cache_data`. It is now
  remembered in-process, keyed on a hash of its two frames' contents, at
  most eight entries. Step 15 benefits as well, since it asks twice.
- **`per_database` and `people_scatter`** (the figure cache) stay in
  `app/charts.py`; they are Streamlit-only.

### Other small changes

- `build_keyword_index` is now `data.keyword_index(movies, db_stamp=None)`.
- Step 15 no longer has to silence Streamlit's "no runtime" warnings.
- pytest's `pythonpath` drops the repo root, which only `views.py` needed.

## The gate, and the one thing it caught

The baseline was step 15's export into a scratch folder from master, run twice
to confirm the export is deterministic (it is). The first post-move export was
**not** identical: `site.sql` was 2,698,389 bytes against 2,595,221.

**Cause.** Importing `streamlit` sets `plotly.io.templates.default =
"streamlit"`, as a side effect. Step 15 imported Streamlit through the app's
modules, so every figure on the site has carried Streamlit's template. That
template is placeholders: `colorway` is `#000001`…`#000010`, the colour
scales `#000011`… Streamlit's front end swaps them for theme colours. Plotly.js
on the site draws them literally.

**Proof the move itself changed nothing.** I exported again with `import
streamlit` first, which put the old default back. That export was
byte-identical. With the template set aside, every figure's data and layout
matched, except `ratings/rt_vs_tmdb`. That chart is the only one that takes
its trace colours from the template (Plotly Express, `color="genre_primary"`,
no explicit sequence).

**What Phase A does about it.** It makes the template explicit.
`plotly_template.json` is Streamlit's template, captured as it was, and
`rewatchables.figures` sets it as the default with a comment saying what it is
and why. Result:

| Export | `site.sql` | `synopses.json` | `theme.css` |
| --- | --- | --- | --- |
| baseline (master) | 2,595,221 B | 2,025,321 B | 58,653 B |
| after phase A, no Streamlit in the process | identical | identical | identical |

## Tests

- **Lint.** Ruff reports the same 5 issues master has (3 unused locals in the
  overview's `render`, 2 in `test_site_db.py`), and no new ones.
- **Suite.** The full suite was run, `app`-marked tests included; the result is
  below.
- **Result: 968 passed, 3 failed, 1 deselected** (12 min 41 s).
- **The 3 failures fail identically on master** (run in a clean worktree of
  master against the same database), so they predate this branch:
  - `test_dossier.py::test_the_dossier_is_addressable`
  - `test_hosts.py::test_the_lookup_shows_every_episode_a_person_was_on`
  - `test_keywords.py::test_clicking_a_keyword_opens_it`

  All three are app tests that compare `AppTest.query_params` values with
  lists (`['neo-noir']`) and now get strings (`'neo-noir'`). This machine has
  Streamlit **1.65.0** installed, not the pinned 1.41.1; the environment has
  drifted from `pyproject.toml`.
- **Deselected:**
  `test_source_csv.py::TestRepoWorkbook::test_the_workbook_renders_to_exactly_the_tracked_csv`.
  It fails, rightly, because the workbook has two episodes that aren't
  published yet (*It Follows*, *A Nightmare on Elm Street*). Your next publish
  renders the CSV.

## Still coupled, for phase C

- `site/src/theme.css` is still copied by step 15 from
  `src/rewatchables/app/theme.css`. Before the app goes, the site's copy
  should become the source and `copy_theme` should go.
- `static/tmdb/` and step 14 serve only the app.
- `rewatchables.app.state.film_from_address` and `LEGACY_SECTIONS` are the
  app's URL contract. The site has its own (`404.md`).

## Decision: the template

The site's charts should not depend on Streamlit's placeholders. Two options:

1. **Project template (recommended).** Replace `plotly_template.json` with
   one built from the palette: `colorway = SERIES`, sequential scale `SEQ`.
   For the scatter, fold genres past `SERIES` into "Other", as the rest of the
   site does, instead of cycling 16 traces through 6 colours. This changes
   the site's output, so it lands as its own commit, checked in the
   `site-dev` preview.
2. **Fix only the scatter.** Give `rt_vs_tmdb` an explicit
   `color_discrete_sequence` and leave the template as it is. That is smaller,
   but every future chart that leans on the template repeats the bug.
