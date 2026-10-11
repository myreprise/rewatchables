# Rewatchables Movie Database

A reproducible data pipeline and a Streamlit explorer for *The Rewatchables*
podcast. The pipeline takes the hand-kept episode list, resolves each film
against TMDB, enriches it from TMDB, Wikipedia, Wikidata and the CMU Movie
Summary Corpus, and builds a SQLite database, `rewatchables.db`. The explorer
(`app.py`) reads that database.

Revisited films are handled as one film with several airings, and every
resolution decision is logged.

## Quick start

Requires Python 3.11 or later.

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
```

Dependencies are pinned in `pyproject.toml`. The `dev` extra adds pytest and
ruff. The install is required, not a convenience: the pipeline and the app
both import the `rewatchables` package from `src/`.

Copy the config template and add a TMDB API key (free at
<https://www.themoviedb.org/settings/api>):

```bash
cp config/.env.template config/.env
```

Build the database, then open the explorer:

```bash
python scripts/orchestrate.py --all
streamlit run app.py
```

`rewatchables.db` is gitignored, so a fresh clone has none. The API caches live
inside it, so the first full build makes one TMDB search per film; after that a
rebuild reaches the network only for new titles.

## Everyday workflow

### Adding or editing an episode

1. Edit `data/episodes.xlsx` in Excel, save, and close it.
2. Run `python scripts/publish.py`, or double-click `publish.bat`.

That is the whole routine, including updating the public site. `publish` runs
the pipeline from step 01, checks the result, shows what changed ("Added: Ep
484, ...") and asks before it commits and pushes. See
[Publishing](#publishing) below for what it checks. To update the local
database without publishing, run `python scripts/orchestrate.py --from 1`
instead.

Step 01 checks every cell and regenerates `data/episodes.csv` from the
workbook. It stops with the row and column named if a cell is wrong, and
refuses to read the workbook while Excel has it open. Step 02 upserts, so only
changed rows are stored. Expect one TMDB search per new film. Until this runs,
the app shows a banner saying the workbook is newer than its data.

Edit the workbook, never the CSV: step 01 regenerates the CSV on every run. The
CSV is tracked so that git can show which episode changed. See
[DATA_SOURCES.md](DATA_SOURCES.md) for the workbook's columns and rules.

### Adding an upcoming film

Add the row to `data/remaining films.xlsx`, save, close it, then:

```bash
python scripts/orchestrate.py --stages upcoming
```

Step 13 regenerates `data/upcoming.csv` from the workbook itself.

### Posters

The app serves movie posters from the local drive, not from TMDB. Step 14
downloads each poster at the two widths the app draws (`w185`, `w342`) into
`static/tmdb/`, named for the film: `Heat (1995).jpg`. `static/tmdb/manifest.json`
records which TMDB image each file is, and Streamlit serves the folder at
`app/static/`. The step runs at the end of every default pipeline run and
fetches only images not already on disk, so a new film costs two downloads; a
retitled film's files are renamed. A poster not yet downloaded is shown from
TMDB. To fetch on its own:

```bash
python scripts/orchestrate.py --stages images
```

`static/tmdb/` is gitignored; a fresh clone gets it from that command.

### Publishing

The public site lives in `site/`, built with
[Observable Framework](https://observablehq.com/framework/) and deployed to
GitHub Pages by `.github/workflows/deploy-site.yml`. It has every section of
the app, and every page reads one SQLite database, `site.db`, queried in the
visitor's browser. See `site/README.md`.

Step 15 writes that database as `site/src/data/site.sql`, a sorted SQL dump
(one row per line, so a new episode is a small diff), plus the synopses, using
the app's own functions, so the two front ends print the same numbers. It runs
at the end of every default pipeline run. Those files are committed, so GitHub
needs neither this machine's database nor a TMDB key; the build turns the dump
into `site.db`.

`python scripts/publish.py` (or `publish.bat`) does the whole publish:

1. Runs the pipeline from step 01. It stops if Excel has a workbook open or a
   cell is invalid.
2. Stops if TMDB queued a film it was unsure of, and names it. Decide it in
   `data/manual_review.csv` (see below) and run publish again.
   `--allow-pending` publishes without that film for now.
3. Runs the quick checks on the published data: the workbook renders to the
   tracked CSV, and the site's database is complete and agrees with the app
   (`tests/test_site_db.py`, about half a minute).
4. Prints what changed and asks `Publish this? [y/N]`.
5. Commits only the published data: both workbooks, both CSVs,
   `manual_review.csv`, `site/src/data/` and `site/src/theme.css`. Other work in
   progress is never swept in. The commit message names the episodes.
6. Pushes to `master`. GitHub Actions deploys the site in a few minutes, and
   publish prints the link.

Any stop happens before the commit, so a failed run leaves git as it was.
`--dry-run` does steps 1-4 and commits nothing; `--skip-pipeline` uses the data
as it is. Without a GitHub remote, publish commits and says so, and the next
run pushes what is waiting.

Publish commits data, not code. A change to the pipeline, the app or the site's
pages is committed by hand as usual.

To preview locally, `cd site`, `npm install` once, then `npm run dev`. See
[site/README.md](site/README.md).

### Reviewing uncertain matches

A mention that does not match TMDB with enough confidence is queued for review
instead of being accepted.

1. Step 07 writes the queue to `data/manual_review.csv`. It merges new items
   into the file and never overwrites earlier decisions.
2. Fill in `action` (`approve`, `reject` or `skip`) and `chosen_tmdb_id`.
3. Step 08 applies the decisions.

`data/manual_review.csv` is the durable record of those decisions: step 08
replays it after staging is rebuilt. It is tracked, and `publish` commits it,
so the decisions are backed up with the repository. An item left as `skip`
stays pending, and `publish` stops on it until it is decided or you pass
`--allow-pending`.

## The pipeline

`scripts/orchestrate.py` runs fifteen steps in seven stages. Each step is a
module in `src/rewatchables/pipeline/`, such as `s04_enrich.py` for step 04. A
step can also be run on its own, with its own options, as
`python scripts/04_enrich.py` or `python -m rewatchables.pipeline.s04_enrich`.

| Step | Stage | What it does |
| ---: | --- | --- |
| 01 | source | Render `episodes.xlsx` to `episodes.csv` |
| 02 | source | Load the raw zone from `episodes.csv` |
| 03 | resolve | Normalize episodes and stage movie mentions (clears staging) |
| 04 | resolve | Resolve mentions against TMDB |
| 05 | curated | Validate data quality |
| 06 | curated | Build the curated zone and detect revisits |
| 07 | curated | Export the manual-review queue (optional) |
| 08 | curated | Apply manual-review decisions (optional) |
| 09 | enrich | Enrich metadata from TMDB |
| 10 | enrich | Resolve external identifiers (Wikidata, Wikipedia, Freebase) |
| 11 | enrich | Load the vendored CMU corpus subset |
| 12 | enrich | Plot summaries: CMU plus live Wikipedia |
| 13 | upcoming | Build the upcoming-films list |
| 14 | images | Download posters to `static/tmdb/` (optional) |
| 15 | site | Export the public site's data to `site/src/data/` |

The optional steps fail by design when there is nothing to review, and the run
continues past them.

```bash
python scripts/orchestrate.py                    # safe refresh (05-15)
python scripts/orchestrate.py --from 1           # after editing the episode list
python scripts/orchestrate.py --all              # everything
python scripts/orchestrate.py --stages enrich    # just 09-12
python scripts/orchestrate.py --from 6 --to 9
python scripts/orchestrate.py --list
python scripts/orchestrate.py --dry-run
```

**Rebuilds are guarded.** Step 03 clears staging and step 04 re-resolves every
mention from scratch, which can reintroduce a match that was corrected by hand.
Step 08 puts those corrections back, which works because staging ids are
deterministic. A run that includes 03 but not 08 is refused while any
hand-made resolutions exist, unless you pass `--rebuild-from-source`.

**Every network step caches.** Step 04 caches in `tmdb_search_cache`, 09 in
`tmdb_metadata_cache`, 10 in `external_id_cache` and 12 in `raw_wiki_articles`;
step 11 reads vendored files. Pass `--refresh` to 04, 09, 10 or 12 individually
to force a re-fetch.

Each run writes a log to `logs/`.

## The database

Three zones, defined in `sql/schemas/`:

- **Raw**: a versioned history of each source. `raw_episodes` keeps one row
  per version of each airing, `raw_ingest_runs` records each load, and
  `raw_upcoming_films`, `raw_cmu_*` and `raw_wiki_articles` hold the other
  sources.
- **Staging**: parsed and normalized. `staging_episodes` and
  `staging_movie_mentions` hold normalized titles, parsed years, confidence
  scores and TMDB candidates.
- **Curated**: canonical, and what the app reads. `curated_movies` (one row
  per film), `curated_episode_movies` (one row per airing of a film),
  `curated_people`, `curated_upcoming_films`, `curated_audits`,
  `manual_review_queue` and `data_quality_results`.

The API caches (`tmdb_search_cache`, `tmdb_metadata_cache`,
`external_id_cache`) and `api_call_log` sit alongside them.

Read through the views where they exist. `raw_episodes_current` pins the
newest snapshot and normalizes dates, which the underlying table does not; see
the comments in `sql/schemas/raw_zone.sql`. The others are
`raw_upcoming_films_current`, `v_cruise_hanks`, `v_movie_cmu`,
`v_upcoming_pending` and `v_upcoming_graduated`.

### Revisited films

Each film has exactly one row in `curated_movies`. `curated_episode_movies`
has one row per airing, so a revisited film has several, marked by
`is_revisit`, `revisit_sequence` (1 for the first airing) and `revisit_type`.
`UNIQUE(staging_episode_id, movie_id)` prevents a duplicate within one episode
while allowing the same film across episodes.

For example, *A Few Good Men* (1992, TMDB 881):

| episode_number | episode_date | is_revisit | revisit_sequence |
| ---: | --- | ---: | ---: |
| 7 | 2017-08-10 | 0 | 1 |
| 320 | 2023-07-31 | 1 | 2 |

The workbook's hand-curated `revisited` column is carried through to
`curated_movies.revisited_flag`, and the app prefers it to the derived
`revisit_count`.

### Queries

Every revisit:

```sql
SELECT e.episode_number, e.episode_date, m.title, em.revisit_sequence
FROM curated_episode_movies em
JOIN curated_movies m ON em.movie_id = m.movie_id
JOIN staging_episodes e ON em.staging_episode_id = e.staging_episode_id
WHERE em.is_revisit = 1
ORDER BY m.title, em.revisit_sequence;
```

Most-revisited films:

```sql
SELECT m.title,
       COUNT(DISTINCT em.staging_episode_id) AS times_discussed,
       SUM(CASE WHEN em.is_revisit THEN 1 ELSE 0 END) AS revisit_count
FROM curated_episode_movies em
JOIN curated_movies m ON em.movie_id = m.movie_id
GROUP BY m.title
ORDER BY revisit_count DESC
LIMIT 10;
```

Data quality by run:

```sql
SELECT run_timestamp, total_episodes_processed, resolution_rate_pct,
       unresolved_mentions
FROM data_quality_results
ORDER BY run_timestamp DESC
LIMIT 10;
```

More are in `sql/queries/analytics.sql`.

## Configuration

Settings live in `config/.env`, copied from
[`config/.env.template`](config/.env.template), which lists every variable and
its default. Only `TMDB_API_KEY` is required.

The pipeline and the app both read `config/.env`, through
`src/rewatchables/config.py`. A relative path in it is taken from the
repository root, not from wherever a command happens to be run.

## Tests and linting

```bash
pytest                  # everything, a few minutes
pytest -m "not app"     # skip the tests that drive app.py through AppTest
ruff check .
```

Tests that run the app through Streamlit's AppTest are marked `app`
automatically (see `tests/conftest.py`). Most tests need a built
`rewatchables.db` and skip without one.

## Layout

```
rewatchables/
├── app.py                  Streamlit entry point: rail, overlays, dispatch
├── publish.bat             Double-click to run scripts/publish.py
├── views.py                Streamlit-free presentation and statistics helpers
├── src/rewatchables/
│   ├── config.py           Paths and settings, anchored to the repo root
│   ├── http.py             The API steps' shared retry policy
│   ├── keys.py             Business keys and deterministic ids
│   ├── images.py           Local poster copies, and the <img> URL for one
│   ├── publish.py          Pipeline, checks, commit and push in one command
│   ├── pipeline/           orchestrate.py, s01_…s15_*.py, convert_xlsx_to_csv.py
│   └── app/                The explorer, in parts
│       ├── theme.py, theme.css      Palette and stylesheet
│       ├── data.py, context.py      Loaders, and the Ctx every renderer is handed
│       ├── state.py                 Nav rail, overlay callbacks, URL seeding, keep/kept
│       ├── components.py, charts.py, panels.py   Cards, figures, shared panels
│       ├── analysis.py              Frames in, numbers out
│       ├── overlays/                dossier.py, keyword.py, prospect.py
│       └── sections/                One module per rail section, each with render(ctx)
├── scripts/
│   ├── orchestrate.py, 01_…15_*.py, convert_xlsx_to_csv.py   wrappers for the modules above
│   └── migrate_*.py, vendor_cmu_subset.py   one-off tools
├── sql/
│   ├── schemas/            raw_zone.sql, staging_zone.sql, curated_zone.sql
│   └── queries/            analytics.sql
├── data/
│   ├── episodes.xlsx       The episode list: the file you edit
│   ├── episodes.csv        Rendered from it by step 01; tracked for diffs
│   ├── remaining films.xlsx, upcoming.csv   The upcoming-films list
│   └── external/cmu/       Vendored CMU corpus subset, with PROVENANCE.md
├── static/tmdb/            Posters downloaded by step 14; served by Streamlit
├── site/                   The public site (Observable Framework); data from step 15
├── .github/workflows/      deploy-site.yml: build site/ and publish to GitHub Pages
├── tests/
├── reports/progress/       Numbered progress reports
├── config/.env.template
└── pyproject.toml
```

### Adding a section

1. Add its slug and label to `NAV` in `src/rewatchables/app/state.py`.
2. Write `src/rewatchables/app/sections/<slug>.py` with a `render(ctx)`.
3. Register it in `RENDERERS` in `sections/__init__.py`.

`ctx` carries every frame the app reads; see `context.py`. The tests pick the
new rail entry up from `NAV` on their own.

## API sources

| Source | Used for | Rate |
| --- | --- | --- |
| TMDB | Film identity and metadata | About 4 requests a second, under TMDB's 40 per 10 seconds |
| Wikipedia | Plot summaries, page ids | Courtesy delay between requests, with a descriptive User-Agent |
| Wikidata | Identifier reconciliation | Batched 50 ids per call, with a courtesy delay |

All API calls share one retry policy, in `src/rewatchables/http.py`:

- **Retried:** a timeout, a dropped connection, a 429 or a 5xx.
- **Attempts:** up to three in all.
- **Wait:** 2 s, then 4 s. After a 429, as long as its `Retry-After` asks, up
  to a minute.
- **Final:** any other status, so a rejected API key fails at once.

Step 12 also retries an error that the Wikipedia API reports inside a
successful response. Step 04's searches are recorded in `api_call_log`.

## Troubleshooting

- **A film matched the wrong TMDB entry.** Correct it through the review queue
  (above) so the correction survives rebuilds.
- **Step 01 refuses to run.** Close `data/episodes.xlsx` in Excel; the step
  won't read a workbook that is open.
- **"Database is locked".** Run one pipeline at a time, and close anything else
  holding `rewatchables.db` open.

## Security

- API keys go in `config/.env`, which is gitignored. Never commit them.
- Only public film metadata is stored.

## Further reading

- [DATA_SOURCES.md](DATA_SOURCES.md): where each source comes from and how it
  is handled.
- [reports/progress/](reports/progress/): what changed and why, with numbers.
- `PROJECT_PLAN.md`: the original plan from June 2026, kept as history.
