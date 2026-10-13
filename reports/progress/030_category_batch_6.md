# 030 — Category data: batch 6 (2025)

Date: 2026-10-13. Branch: none (uncommitted on `master`).
Previous: [029 — category data: batch 5](029_category_batch_5.md).

## TL;DR

**Batch 6 passed its checks first time**, the third clean batch in a row,
with no code changes.
- **The fetch:** 1,711 new pages, **0 failures**, in 28 min 50 s (1.01 s a
  page). The other 33 of the batch's 1,744 were already stored by the pilot,
  from *F1*.
- **The check:**
  - all 1,744 pages parse;
  - every page's bullets match its own count;
  - all **4,274 of 4,274** workbook discussion cells are found on their pages;
  - no field disagrees with the workbooks;
  - every page has a derivable category slug.
- **One source quirk, reported and not a failure:** "returned $219 million ."
  in `its-complicated-research-86`, rewatchvault's own typo.
- **The categories, rebuilt:** **10,047 entries across 432 of 473 episodes, 214
  categories**, 42,490 bullets, 28,668 links and 799 hosts' picks. Every entry
  has a category. Only *Dunkirk* and *Fast Five* are unmapped.
- **Read it:** `logs/categories/batch-6-entries.xlsx` (1,744 entries, 5,464
  bullets, 95 picks).

| | Pilot | 1 | 2 | 3 | 4 | 5 | 6 | Together |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Pages | 211 | 1,365 | 1,958 | 1,406 | 1,684 | 1,851 | 1,744 | 10,047 |
| Episodes | 10 | 97 | 119 | 54 | 53 | 57 | 51 | 432 of 473 |
| Bullets | 819 | 7,474 | 11,067 | 6,040 | 6,114 | 6,213 | 5,464 | 42,490 |
| Pages the workbooks lacked | 17 | 19 | 49 | 24 | 50 | 43 | 36 | |
| Person links the workbook rows had dropped | 65 | 962 | 1,100 | 685 | 441 | 581 | 359 | |

## Next

1. **Batch 7, the last** (2026: 43 episodes and the 4 pages no workbook
   episode claims, 1,522 pages, about 26 min), on your go-ahead. It also picks
   up anything that has aired since the workbooks were scraped, *Friday the
   13th* among them, if rewatchvault has added it.
2. After batch 7: the alias list for the multi-id banners (report 025), then
   phase 4.
3. Optional, from report 026: page the "Read the discussions" toggle.
4. Still open: *Dunkirk* and *Fast Five* dates.
