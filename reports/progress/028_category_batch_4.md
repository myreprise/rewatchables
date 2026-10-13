# 028 — Category data: batch 4 (2023)

Date: 2026-10-13. Branch: none (uncommitted on `master`).
Previous: [027 — category data: batch 3](027_category_batch_3.md).

## TL;DR

**Batch 4 passed its checks first time**, the first batch to do so. There
were no code changes.
- **The fetch:** 1,666 new pages, **0 failures**, in 28 min 2 s (1.01 s a
  page). The other 18 of the batch's 1,684 were already stored by the pilot,
  from *American Pie*.
- **The check:**
  - all 1,684 pages parse;
  - every page's bullets match its own count;
  - all **4,509 of 4,509** workbook discussion cells are found on their pages;
  - no field disagrees with the workbooks;
  - no page lacks a category slug.
- **One source quirk, reported and not a failure:** "dates the film to the
  mid-2000s ." in `casino-royale-aged-worst-0097`. It's rewatchvault's own
  typo, which batch 3's source-text check now recognises.
- **The categories, rebuilt:** **6,526 entries across 326 of 473 episodes, 148
  categories**, 31,015 bullets, 23,290 links and 604 hosts' picks. Every entry
  has a category. Only *Dunkirk* and *Fast Five* are unmapped.
- **Read it:** `logs/categories/batch-4-entries.xlsx` (1,684 entries, 6,114
  bullets, 107 picks).

| | Pilot | 1 | 2 | 3 | 4 | Together |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Pages | 211 | 1,365 | 1,958 | 1,406 | 1,684 | 6,526 |
| Episodes | 10 | 97 | 119 | 54 | 53 | 326 of 473 |
| Bullets | 819 | 7,474 | 11,067 | 6,040 | 6,114 | 31,015 |
| Pages the workbooks lacked | 17 | 19 | 49 | 24 | 50 | |
| Person links the workbook rows had dropped | 65 | 962 | 1,100 | 685 | 441 | |

## Next

1. **Batch 5** (2024: 57 episodes, 1,851 pages, about 31 min), on your
   go-ahead.
2. Optional, from report 026: page the "Read the discussions" toggle.
3. Still open: *Dunkirk* and *Fast Five* dates, and the multi-id banners in
   report 025 (before phase 4).
