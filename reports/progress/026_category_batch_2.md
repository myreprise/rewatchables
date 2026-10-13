# 026 — Category data: batch 2 (2020–2021)

Date: 2026-10-13. Branch: none (uncommitted on `master`).
Previous: [025 — category data: batch 1](025_category_batch_1.md).

## TL;DR

**`winner-retrospective` is folded into `winner`** (approved). The 4 *Jaws*,
*Speed* (2017), *Top Gun* and *Mean Girls* "Who Won the Movie?" entries now
take their category from their banner, and nothing is uncategorised.

**Batch 2 is in.**
- **The fetch:** 1,932 new pages, **0 failures**, in 34 min 53 s (1.08 s a
  page). The other 26 of the batch's 1,958 pages were already stored by the
  pilot (*Rocky IV* and *Heat* 2021).
- **The first check failed, again on two false alarms.** Neither was a page
  problem, and both are fixed. With the fixes, the pilot and batches 1 and 2
  all **pass**. Batch 2:
  - all 1,958 pages parse;
  - every page's bullets match its own count;
  - all **9,350 of 9,350** workbook discussion cells are found on their pages;
  - no field disagrees with the workbooks.
- **The categories, rebuilt:** **3,458 entries across 221 of 473 episodes, 98
  categories**, 18,941 bullets, 17,587 links and 402 hosts' picks. Every entry
  has a category. Only *Dunkirk* and *Fast Five* are unmapped.
- **Read it:** `logs/categories/batch-2-entries.xlsx` (1,958 entries, 11,067
  bullets, 218 picks), or the app.

| | Pilot | Batch 1 | Batch 2 | Together |
| --- | ---: | ---: | ---: | ---: |
| Pages | 211 | 1,365 | 1,958 | 3,458 |
| Episodes | 10 | 97 | 119 | 221 of 473 |
| Bullets | 819 | 7,474 | 11,067 | 18,941 |
| Hosts' picks | 14 | 179 | 218 | 402 |
| Pages the workbooks lacked | 17 | 19 | 49 | |
| Person links the workbook rows had dropped | 65 | 962 | 1,100 | |

## What the first check caught

1. **94 workbook cells read "Podcast choices"** and weren't found on their
   pages. That's the heading of the hosts' picks block (its `<summary>`),
   which the workbook scraper kept as a discussion cell. It was one per page
   with a picks block. The comparison already accepted the picks' speakers
   and texts. It now also accepts the heading, and only on pages that have a
   picks block.
2. **8 bullets "read excised", all ellipses.** Quoted dialogue ("this is a game
   ... of focus") and a title that opens with dots (*...And Justice for All*).
   A dot followed by a dot is now excluded, as a dot followed by a digit was
   after batch 1. There's a test for each.

Both were the check over-flagging, and no page needed a parser change. The
pattern across three batches is that each new slice of the archive shows some
variation in the prose, not in the markup.

## A cost that grows with the batches

The category view's **"Read the discussions"** toggle draws every entry in the
chosen category, each with its expander. The standing categories now have
about 220 entries each and will reach about 470. The AppTest that opens it
takes 10.6 s, the slowest in the file.

**Proposal:** show the newest 25 with a "Show 25 more" button, the way the
upcoming-films grid caps its reasons. It's a small change in
`sections/categories.py`, and I'll make it with your go-ahead. The table
above the toggle is unaffected.

## Verification

- `tests/test_categories.py` 37 and `tests/test_category_build.py` 32 pass on
  the batch-2 database, including the AppTest section and dossier tests.
- The test fixture's workbook row now includes a "Podcast choices" cell, and
  the excision test covers both ellipsis forms.
- Re-checked offline after the change: pilot PASS, batch 1 PASS, batch 2 PASS.
- `rewatchables.db` is 51.8 MB, as the 3,458 stored pages bring it up.

## Next

1. **Batch 3** (2022: 54 episodes, 1,406 pages, about 25 min), on your
   go-ahead.
2. Optional: page the "Read the discussions" toggle (above).
3. Still open: *Dunkirk* and *Fast Five* dates, and the multi-id banners in
   report 025 (before phase 4).
