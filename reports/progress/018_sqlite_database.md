# 018 — SQLite site, phase 1: the database

Date: 2026-10-11. Branch: `sqlite-site` (not merged; the live site is unchanged).
Previous: [017 — phase 0, the spike](017_sqlite_spike.md).

## TL;DR

`site.db` now holds everything the site shows, in 21 tables. **2.04 MB, or
644 KB gzipped.** The full Wikipedia synopses sit beside it in
`synopses.json`, 2.03 MB (0.78 MB gzipped), loaded only when a reader expands
one.

The site's logic is 36 SQL query files (`site/src/queries/`). The pages will
run them in the browser, and `tests/test_site_db.py` runs the same files and
compares each answer with the Streamlit app function it must agree with. All
28 tests pass.

| | Phase 0 | Phase 1 |
| --- | ---: | ---: |
| Tables | 7 | 21 |
| `site.sql` (the committed dump) | 1.45 MB, 16k lines | 2.58 MB |
| `site.db`, raw | 1.68 MB | 2.04 MB |
| `site.db`, gzipped (what a visitor downloads) | 536 KB | **644 KB** |
| Queries | 5, inline | 36, in files, tested |

## The size, and how it came down

The first full build was **981 KB gzipped**, over the 1 MB line I'd set for
splitting the database (017). Measuring showed the excess was SQLite's
storage layout, not the data:

| Layout | Raw | Gzipped |
| --- | ---: | ---: |
| Ordinary tables | 3.10 MB | 981 KB |
| …plus `VACUUM` | 3.03 MB | 1,041 KB |
| Every table `WITHOUT ROWID` | 2.23 MB | 694 KB |
| **Hybrid**: `WITHOUT ROWID` except the 4 tables with long text | 2.25 MB | 700 KB |
| Hybrid, without duplicated section tables | **2.04 MB** | **644 KB** |

- **`WITHOUT ROWID`:** an ordinary table with a primary key also builds an
  index that stores the key columns a second time. For a link table such as
  `film_keywords`, where the key is the whole row, that doubles it. A
  `WITHOUT ROWID` table stores each row once, inside its key.
- **The hybrid:** SQLite's documentation advises the ordinary layout for
  tables with long rows, so `films`, `figures`, `section_data` and
  `requests` keep it. It costs 6 KB.
- **Duplicated section tables dropped:** the section builders produce some
  tables that repeat rows already in the catalogue: the Box Office data
  table, the director and actor tables, the Cruise vs. Hanks ledger, and the
  Hosts bench, lean comparisons, regulars and "Without Bill". They're no
  longer stored; each has a query over the catalogue tables instead
  (`DERIVED` in `site_db.py`).
- **No help from:** removing the Plotly template the 30 charts each repeat.
  Gzip already collapses the copies, so it saved about 4 KB.

## What's in the database

| Tables | Rows | Filled by |
| --- | ---: | --- |
| `films`, `film_genres`, `film_directors`, `film_cast`, `film_keywords` | 460 films; 1,102 genre, 460 director, 4,599 cast and 7,846 keyword links | the curated frames |
| `episodes`, `episode_room` | 487, 1,357 | the episode links, the room in chair order |
| `keywords` | 3,676 | reach, chip band, and an address for the 1,265 on two or more films |
| `film_shelves` | 2,321 | `dossier.same_director` / `shared_cast`, four each |
| `people`, `person_company`, `leans` | 62, 176, 90 | the bench, `hosts.sits_with`, `hosts.regular_leans` with p, q and phrases |
| `directors`, `actors`, `collaborators` | 260, 367, 267 | `director_stats`, `actor_stats`, the spotlights' recurring collaborators, top-20 rank |
| `requests`, `request_tags`, `graduated` | 210, 116, 4 | the Upcoming list |
| `figures` | 30 | each section's Plotly charts |
| `section_data` | 82 | each section's tile and caption numbers, one row per key |

**Who computes what:**
- **In the browser (SQL):** filters, joins and counts.
- **In Python, stored as tables:** anything with a ranking rule or a
  statistic, so the browser never re-derives a tie-break or a p-value.

## The queries and their tests

The 36 queries cover:
- each detail view: film, keyword, person, director or actor spotlight,
  request;
- each table: Explorer, bench, leans, directors, actors, money, ledger,
  requests;
- the section data.

Each file's first comment names the app function it must agree with.

`tests/test_site_db.py` builds the database from the live one, as the
loader does, and checks:

- **Values:** literals round-trip, and a newline in text keeps each row on
  one line of the dump.
- **Determinism:** the dump and synopses are byte-identical after a rebuild
  that reissues every `movie_id` and shuffles every frame, and no
  `movie_id` reaches either file.
- **The loader:** `site.db.py` builds a valid database.
- **Integrity:** row counts equal the app's frames, no reference points at a
  missing row, and every address is unique and URL-safe.
- **Contents:** keyword addresses follow the link floor, every section has
  its charts, and no duplicated table is stored.
- **Every query runs.**
- **Parity with the app, query by query:**
  - film keywords against `rank_by_reach`, and cast and billing against
    `cast_billing`;
  - film episodes and shelves against the dossier;
  - the Explorer's ratings against `ctx.rated`;
  - keyword films, partners and peak decade against `keyword_profile`;
  - every person's shelf, company, verdicts and leans against
    `person_shelf`, `sits_with`, `verdict_tally` and `lean_chips`;
  - the bench and "Without Bill" against the Hosts section;
  - the director and actor tables, pickers, films and collaborators against
    the section functions;
  - the money table, the ledger's verdict counts, the requests (with their
    tags) and the graduates against their frames.

They take 78 seconds. The old JSON export's tests still run too, until
phase 3 retires that export.

**Full suite:** 915 of 916 pass. The failure is
`test_the_workbook_renders_to_exactly_the_tracked_csv`, unrelated to this
work. `data/episodes.xlsx` has edits that haven't been published yet, so it
no longer matches the tracked CSV. It should pass once they are.

## Other changes

- **Step 15** writes `site.sql` and `synopses.json` beside the JSON (until
  phase 3).
- **`.gitattributes`** pins both files to LF line endings. This machine
  converts line endings in the working copy (`core.autocrlf` is true), which
  would otherwise make git read every row as changed.
- **`.github/workflows/build-site-branch.yml`** builds the site on any
  branch other than `master` that changes `site/`, without deploying. This
  is how the loader is checked on GitHub's Linux machines before the switch.
- **The two section builders the database reads from stay.** `sections.py`
  and `overview.py` produce the section payloads stored in `section_data`.
  So phase 3 deletes the per-page exporters (film, keyword, person,
  spotlight and request pages) and keeps these two, rather than the whole
  `site_export` package as the plan first said.

## Next: phase 2, the pages

Rewrite the six detail views as `?id=` pages, and point the section pages at
`figures`, `section_data` and the queries. Then remove `dynamicPaths`.
