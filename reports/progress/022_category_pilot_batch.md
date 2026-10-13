# 022 — Category data: the pilot batch

Date: 2026-10-12. Branch: none (uncommitted on `master`).
Previous: [021 — category data: profile and proposal](021_category_data_proposal.md).

## TL;DR

The pilot passed. **211 pages from 10 episodes, one per air year, were
fetched with no failures, and all 211 parsed.** Each page's bullets match the
page's own count. Every link points at its name, and no restored text still
reads as if a name was cut out. Every field the workbooks have agrees with
the page.

| Question | Answer |
| --- | --- |
| Did every page fetch and parse? | **211 of 211.** No HTTP errors, no retries, no page without a discussion block |
| Are names back in the prose? | **Yes: 504 person links and 30 film links**, each with offsets that point at the name. 0 bullets, answers or picks still read as if a name was cut out |
| Does the page agree with the workbook? | **On every field, yes.** All 623 workbook discussion cells are found on their page. That took two parser fixes, below |
| What did re-reading recover? | Across the 194 pages the workbooks have, 790 bullets against the workbook's 623 cells; 36 pages (19%) had more bullets than the workbook kept. Plus 17 pages (29 bullets) the workbooks lack entirely, and 65 person links the workbook rows had dropped |
| How fast? | 211 pages in 3 min 48 s, **1.08 s a page**. The remaining 11,319 pages would take about 3 h 25 min |
| How big? | **1.4 KB a page** compressed (3.6 KB raw), so about 16.5 MB for all 11,530 |

**Recommendation: go ahead with batch 1** (2017–2019: 97 episodes, 1,365
pages, about 25 minutes).

## What was built

- **`src/rewatchables/rewatchvault.py`** is the parser. It's pure: it makes
  no network calls and doesn't touch the database. `parse_article()` returns:
  - the film, episode, air date, icon family, category slug, banner and answer;
  - the bullet count, transcript time (in seconds) and transcript URL;
  - the bullets, each with its inline links (`kind` is person or movie, with
    slug, name and offsets) and its speakers;
  - the hosts' picks.

  `without_mentions()` produces the workbook scraper's view of the same
  prose, with links cut out, and every cross-check depends on it.
- **`src/rewatchables/pipeline/s16_load_categories.py`**, run as
  `scripts/16_load_categories.py`, has four sub-commands:
  - `--load-workbooks`: no network.
  - `--plan`: one sitemap request.
  - `--batch NAME`: one request a second; resumes and skips stored pages.
  - `--check NAME`: no network.

  Step 16 is deliberately **not in `orchestrate.py`'s steps**, so a `--all`
  run can't start a crawl. It's listed, with that reason, in a new
  `MANUAL_STEPS` set. `test_all_pipeline_steps_are_wired_in` still fails any
  numbered step that's in neither list, and a new test checks that each
  manual step exists and isn't also in `STEPS`.
- **`sql/schemas/raw_zone.sql`** adds three tables:
  - `raw_category_loads`, the ledger, which records each batch's planned
    slugs;
  - `raw_category_workbook_rows`;
  - `raw_category_pages`.

  Both row tables use the `raw_episodes` upsert: one row per
  `(discussion_slug, source_hash)`, plus `last_seen_*`.
- **`tests/test_categories.py`** has 34 tests. The fixture page is invented:
  it copies the site's markup but none of its writing.
- **`pyproject.toml`** adds `beautifulsoup4==4.13.4`.

User agent: `rewatchables-category-archive/1.0 (+https://github.com/myreprise/rewatchables)`.
Requests are spaced at least 1 s apart, start to start. The step stops after 5
transport failures in a row.

## The run

| Step | Result |
| --- | --- |
| Workbook load | 11,237 rows in 54 s, all new |
| Workbook load, again | 0 new, 11,237 unchanged: idempotent |
| Plan | Sitemap 11,530 pages; batches 1–7 are 1,365 / 1,958 / 1,406 / 1,684 / 1,851 / 1,744 / 1,522, matching report 021 exactly |
| Pilot fetch | 211 new, 0 failed, load `74a80e2e` `success`, 09:13:45–09:17:33 UTC |
| Pilot checks | PASS. Summary and disagreement CSV in `logs/categories/` |
| Test suite (`-m "not app"`) | 868 passed, 2 failed. One was the step-wiring guard, fixed as above (that file plus the category and wrapper tests: 80 pass). The other, `test_the_workbook_renders_to_exactly_the_tracked_csv`, comes from the uncommitted edit to `data/episodes.xlsx` (*Friday the 13th*) that predates this work. Step 01 hasn't rendered it to the CSV yet |

The pilot, by episode:

| Episode | Year | Pages | Not in workbooks | Bullets | Workbook cells found | Person links the workbook lacked |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| friday | 2017 | 14 | 1 | 64 | 61 of 61 | 5 |
| get-out | 2018 | 19 | 1 | 52 | 54 of 54 | 0 |
| the-godfather-part-ii | 2019 | 17 | 1 | 143 | 91 of 91 | 1 |
| rocky-iv | 2020 | 17 | 2 | 101 | 79 of 79 | 2 |
| heat | 2021 | 9 | 0 | 59 | 46 of 46 | 25 |
| boogie-nights-part-1 | 2022 | 4 | 2 | 8 | 4 of 4 | 0 |
| american-pie | 2023 | 18 | 4 | 72 | 49 of 49 | 3 |
| road-house | 2024 | 41 | 1 | 120 | 80 of 80 | 15 |
| f1 | 2025 | 33 | 1 | 82 | 69 of 69 | 2 |
| the-texas-chain-saw-massacre | 2026 | 39 | 4 | 118 | 90 of 90 | 12 |

The "workbook cells found" counts include cells that came from the hosts'
picks block (below), so for get-out they exceed the episode's bullet count.

## What the pilot caught

The first check also passed its gate. Its cross-check, though, showed 69
answer and 26 bullet disagreements with the workbooks. Each one came from page
structure the parser didn't yet handle. All four fixes are in, and the same
stored pages were checked again offline, with no refetch.

1. **Answers contain links too.** 71 of 211 answers link a person or film,
   e.g. a recasting answer that is a list of five actors. The parser had read
   answers as flat text with a space between elements, giving
   `Jeff Bridges ; Rob Reiner`. Answers now go through the same parser as
   bullets, links are kept, and answers are covered by the check for cut-out
   names.
2. **Films are linked as well as people.** There are 30
   `a.archive-movie-mention` links, e.g. "ages implausibly across *Rocky IV*
   and *Rocky V*". The workbook scraper cut these out too. Their text was
   always kept on the page; now they're also recorded as links (`kind`
   `movie`).
3. **A second block: the hosts' picks.** 6 pages carry
   `details.archive-discussion archive-podcast-choices`, "Podcast choices": a
   list pairing each speaker with their pick, 14 picks in all. 5 of the 14
   speakers are labelled "Speaker not identified". One pick is credited to
   Patrick Swayze, presumably a clip played on the show. The picks are stored
   as the site gives them. This block shares the
   discussion's class, so the parser picks the right block explicitly, and a
   test proves it with the order swapped. The workbook's discussion columns had
   swallowed this block; that's where the stray "Wesley Morris" and "Speaker
   not identified" cells came from. **This is new structured data, who picked
   what, that the workbooks only had as loose cells.**
4. **Opaque slugs.** 56 workbook pages have slugs like `c2` and `c58` that
   start with no episode slug. They span 10 episodes, including *Aliens*,
   *Apollo 13*, both *Speed* episodes and *Heat*. Planning by prefix had pushed
   37 of them into batch 7. A page the workbooks list now belongs to the
   episode its row names, and the prefix is used only for pages the workbooks
   lack.
   - The 4 sitemap-only pages (`c54`, `c56`, `c57`, `c8`) can't be placed until
     they're fetched. They stay in batch 7, and the page itself will say which
     episode it belongs to.
   - These pages also have **no category slug**: 4 in the pilot, all *Heat*
     (2021). Their banners are ordinary ("Apex Mountain", "Casting What-Ifs"),
     so the curated step will assign them by banner. This is a known
     exception, not a failure.

## Costs to know about

- **Database size.** `rewatchables.db` went from 14.8 MB to 31.9 MB. Almost
  all of that is the workbook rows: about 1.5 KB each compressed, because
  each row is compressed alone. Once every page is in, expect about 48 MB. The
  file is git-ignored and is not what the public site reads (`site.sql` is),
  so this costs disk space only. A backup from before step 16 is in the
  session scratchpad.
- **Nothing is curated yet.** The pages are in the raw zone and parse
  cleanly, but `curated_category_*` tables and the episode map (report 021,
  proposal 2) aren't built. They should wait until all batches are in, so
  they're designed against every variation and not just ten episodes.

## Next

1. Batch 1, when you say so:
   `python scripts/16_load_categories.py --batch 1`. About 25 minutes, with a
   summary in `logs/categories/`.
2. Still open from report 021:
   - what goes on the public site (my advice: facts plus a link, and ask
     rewatchvault before using prose);
   - the two date conflicts, *Dunkirk* and *Fast Five*.
