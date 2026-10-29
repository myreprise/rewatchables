# 034 — Category data for new episodes: proposal

Date: 2026-10-13. Nothing is built yet; this report is for review.
Previous: [033 — category data: phase 4, totals](033_category_totals.md).

## TL;DR

One command picks up the categories of any episode rewatchvault has added
since the last run, checks them, rebuilds the tables the app reads, and says
what it found:

```bash
python scripts/16_load_categories.py --update
```

It extends step 16 with a new mode; there's no new script. It reuses
everything the batches proved:
- the sitemap diff;
- the polite fetch, one request a second;
- the raw-zone upsert;
- the batch checks;
- step 17's build.

**What it costs to run:** with nothing new, one 2.3 MB sitemap request and
about 10 seconds. With a new episode, about 25–50 page requests, under a
minute, plus the rebuild. It uses no Claude usage unless a run needs
attention.

**State today:** all 11,530 pages in rewatchvault's sitemap are stored. *Friday
the 13th* (aired 12 Oct) isn't on the site yet, so a run now would fetch
nothing.

## What `--update` does

1. **Find new pages.** Fetch the sitemap and take every discussion slug not in
   `raw_category_pages`. Unlike the year batches, this needs no workbook and
   no year table. A page's own HTML says which episode it belongs to,
   including opaque slugs like `c58`.
2. **Optionally re-read the newest episode's pages.** If you approve (decision
   2), the most recently stored episode's pages are fetched again, about 30
   requests, to pick up corrections rewatchvault makes after publishing. The
   upsert stores only pages whose content changed, so the run reports exactly
   how many did.
3. **Check what was fetched**, with the same gate as every batch:
   - every page parses;
   - bullets match each page's own count;
   - restored names, with source quirks reported rather than failed;
   - offsets.

   The workbook cross-check is skipped, because the workbooks predate every
   new page.
4. **Rebuild** with step 17, so the app shows the new entries on its next
   load.
5. **Report** to the console and to `logs/categories/update-<date>.md`:
   - new episodes and their entry counts;
   - new categories, ids the archive has never seen, flagged as possible
     aliases for you to approve or not;
   - episodes that didn't link to the episode list. A new episode that isn't
     in `episodes.xlsx` yet shows up here, with the date to add.
6. **Exit code**, so a scheduler or you can tell at a glance:

   | Code | Meaning |
   | --- | --- |
   | 0 | Up to date, or new entries added cleanly |
   | 1 | A check failed. Nothing is wrong in the app, but the new pages need a look |
   | 2 | Added, but something needs you: an unmapped episode or a new category |

Each run is one `raw_category_loads` row (`batch = 'update'`), so every run is
auditable, like the batches.

## What it won't do

- **Edit `episodes.xlsx`.** If rewatchvault has an episode your list doesn't,
  the report says so and you add it, as now.
- **Add aliases on its own.** New category ids are listed, and folding one
  into another stays your call.
- **Touch the public site.** Categories remains app-only.

## Decisions for you

1. **One command or two?** I'd make `--update` fetch, check *and* rebuild, so
   one command leaves the app current. The alternative keeps it to fetch and
   check, and you run `--stages categories` yourself, as with the batches.
2. **Re-read the newest episode each run?** It's about 30 extra requests. It
   catches corrections, if rewatchvault makes any. We don't know whether it
   does: no batch ever re-fetched a page. I'd turn it on and look at the
   "changed" counts after a few runs. If they're always 0, turn it off.
3. **How it runs:**
   - **By hand** after an episode drops (recommended to start).
   - **Windows Task Scheduler**, weekly. That uses no Claude usage, and you
     look at the log when the exit code isn't 0. I can set that up after a
     few clean manual runs.
   - **A Claude scheduled task:** not recommended. It would spend usage on
     something a plain script does for free.

## Work involved

Small, because it reuses step 16's code:
- `--update` and a short summary writer;
- tests: the sitemap diff, refetch selection, the summary's flags and the exit
  codes, all on the invented fixture page;
- a README line.

The batch plan (`--batch 1..7`) stays as it is for any future rebuild from
scratch.

## Built, 2026-10-13

You approved the recommendations: one command, re-read the newest episode,
and run it by hand for now.
- **Code:** step 16 gains `--update` and `--no-refetch-latest`. The fetch loop
  moved into `fetch_pages()`, now shared by the batches and updates, and it
  reports which pages changed. Also new: `plan_update()`,
  `latest_episode_pages()`, `run_update()` and `write_update_summary()`.
- **Tests:** 7 new in `tests/test_category_build.py`, with the network faked,
  covering:
  - the plan;
  - nothing new: OK, no rebuild;
  - a new entry for a known episode: OK, rebuilt;
  - an episode missing from the list: needs you;
  - a correction caught by the re-read;
  - a page that fails its checks: failed.
- **First live run** (19:02): 0 new pages, because *Friday the 13th* still
  isn't on rewatchvault.
  - The 39 *Texas Chain Saw Massacre* pages were re-read, **0 changed** since
    they were fetched on 2026-10-12.
  - Checks PASS, no rebuild needed, exit 0.

  That's one data point towards decision 2. Keep watching the "changed" count
  over the next few episodes.
