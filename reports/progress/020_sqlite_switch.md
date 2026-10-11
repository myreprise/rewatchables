# 020 — SQLite site, phase 3: the switch

Date: 2026-10-12. Branch: `sqlite-site`, merged to `master`.
Previous: [019 — phase 2, the pages](019_sqlite_pages.md).

## TL;DR

The public site now runs on one SQLite database. The JSON export and its
2,638 files are gone. Step 15 writes two data files, `publish` checks them
with the database tests, and the site builds 19 pages.

| | Before (JSON) | After (SQLite) |
| --- | ---: | ---: |
| Data files committed under `site/src/data/` | 2,638 JSON | 2 (`site.sql`, `synopses.json`) |
| HTML pages built | about 2,637 | 19 |
| Local build | 773 s | 19 s |
| `dist/` | over 43 MB | 6.5 MB |
| `publish` quick checks | `test_export_site.py`, 2.5–8 min | `test_site_db.py`, about 20 s |

## What changed

### Step 15

`s15_export_site.py` now writes only:
- `site.sql`, the database dump;
- `synopses.json`;
- the copy of the app's stylesheet.

It also touches the data loader so a preview picks up new data.

The 13 legacy JSON paths are listed in `LEGACY` and removed if found, so an
old checkout cleans itself up. If Windows or OneDrive holds one of them, the
step logs a warning and carries on: tidying up never stops a publish. This
happened on the first run, when the `charts` folder refused to delete
partway through. The one-time removal went through git instead.

### `site_export`, down to what the database needs

| Module | Change |
| --- | --- |
| `films.py`, `people.py`, `spotlights.py` | Deleted: they wrote per-film, per-person and per-spotlight pages |
| `keywords.py` | Keeps `keywords_index` (the section's numbers); the per-keyword pages are gone |
| `upcoming.py` | `upcoming()` returns the section alone; each request is a `requests` row |
| `common.py` | The JSON file writers are gone; `prepare()`, `Addresses`, `card()`, `figure()` and `plain_value()` remain |
| `sections.py`, `overview.py` | Unchanged: they build the numbers and charts stored in `section_data` and `figures` |

### Tests

- **`test_export_site.py` is deleted** with the export it tested. What still
  applies moved to `test_site_db.py`:
  - the address tests (`slugify`, `film_slugs`, `name_slugs`);
  - the Overview's numbers and doors;
  - every section's stored numbers against the app: Box Office summary,
    Ratings divergence, Timeline revisits, Cruise vs. Hanks standing and
    lead changes, Hosts anchor share and comparisons, Directors and Actors
    tiles and correlations, the Upcoming summary.
- **The episode-label test** now computes its expected gaps with
  `views.human_gap` directly, instead of from the deleted exporter.
- **`test_site_db.py` now has 46 tests**, taking about 20 seconds.

### `publish`

- **Quick checks:** `QUICK_TESTS` is `test_source_csv.py` plus
  `test_site_db.py`.
- **What it commits:** still all of `site/src/data/`, which now holds the
  dump, the synopses and the two data loaders.
- **The weekly routine is unchanged:** edit the workbook, run `publish`.

### Docs

- `README.md`'s publishing section describes the database and the shorter
  checks.
- `site/README.md` describes the SQLite site (phase 2).

## Checked

- **Full suite:** 882 of 883 pass, in 4 min (13 min before: the JSON export
  tests ran the export three times). The failure is the usual workbook
  check: `data/episodes.xlsx` has edits that haven't been published yet.
  `publish` renders the CSV before it runs that check, so it will pass there.
- **Production build:** 19 pages, 19 s, 6.5 MB. Served under
  `/rewatchables/`, every page type renders with its charts and no errors,
  and an old link forwards to its new address.
- **Live site after the merge:** see below.
