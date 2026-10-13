# 031 — Category data: batch 7, and the archive is complete

Date: 2026-10-13. Branch: none (uncommitted on `master`).
Previous: [030 — category data: batch 6](030_category_batch_6.md).

## TL;DR

**Batch 7 passed its checks first time, and the archive is complete:
11,530 entries across all 473 episodes**, every page in rewatchvault's
sitemap.
- **The fetch:** 1,483 new pages, **0 failures**, in 26 min 5 s. The other 39
  of the batch's 1,522 were already stored by the pilot, from *The Texas Chain
  Saw Massacre*.
- **The check:**
  - all 1,522 pages parse;
  - every page's bullets match its own count;
  - all **3,685 of 3,685** workbook discussion cells are found on their pages;
  - no field disagrees with the workbooks.
- **The 4 unclaimed pages are placed.** `c54`, `c56` and `c57` are *Heat*
  (2021) entries, and `c8` is *Aliens*. Each page names its own episode.
- **The categories, rebuilt:** **11,530 entries across 473 of 473 episodes,
  252 categories**, 46,927 bullets, 31,077 links and 887 hosts' picks.
  - 59 opaque-slug entries took their category from their banner.
  - **One entry is uncategorised:** *Aliens* `c8`, explained below.
  - Only *Dunkirk* and *Fast Five* are unmapped, while their dates are open.
- **Nothing new on the site since the scrape.** rewatchvault hasn't yet added
  *Friday the 13th* (aired 2026-10-12), or anything else.
- **The app's "Partial data" note is gone,** because coverage is complete. Its
  test now checks that the note shows exactly when coverage is incomplete.
- **Read it:** `logs/categories/batch-7-entries.xlsx`, `batch-1` to `batch-6`
  beside it, or the app.

## The whole run

| | Pilot | 1 | 2 | 3 | 4 | 5 | 6 | 7 | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Pages | 211 | 1,365 | 1,958 | 1,406 | 1,684 | 1,851 | 1,744 | 1,522 | **11,530** |
| Episodes | 10 | 97 | 119 | 54 | 53 | 57 | 51 | 43 | **473** |
| Bullets | 819 | 7,474 | 11,067 | 6,040 | 6,114 | 6,213 | 5,464 | 4,555 | **46,927** |
| Pages the workbooks lacked | 17 | 19 | 49 | 24 | 50 | 43 | 36 | 72 | **293**\* |
| Person links the workbook rows had dropped | 65 | 962 | 1,100 | 685 | 441 | 581 | 359 | 356 | **4,549**\* |
| First check | pass | fail | fail | fail | pass | pass | pass | pass | |

\*Pilot pages are counted again in their year's batch, so these columns
double-count the pilot. The 293 matches the gap report 021 found in the
sitemap.

**Fetching:** 11,319 requests over about 3 h 35 min of fetching, with **no
HTTP errors**. Every first-check failure came from the check being too
strict, never from a page or the parser losing text. Each was fixed with a
test: the empty-discussion entry, decimals, ellipses, the picks heading, and
gaps that are in the source itself.

**Database:** `rewatchables.db` is 84.4 MB, git-ignored and local only.

## Decisions before phase 4 (totals)

### 1. Banners filed under more than one id: the full list

Across all 11,530 pages, 14 banners appear under 2–3 category ids. Without
aliases, totals would split an award across ids. The full list is in
`logs/categories/multi-id-banners.txt`. Proposed handling:

**Fold (one or two stray pages, same award, same banner):**

| Alias | Into | Pages |
| --- | --- | ---: |
| `half-ass` | `research` (Half-Assed Internet Research, 469) | 1 |
| `joey-pants` | `that-guy` (432) | 1 |
| `netflix` | `remake` (410) | 2 |
| `quote` | `best-quote` (304) | 1 |
| `belated-quote` | `best-quote` | 4 |
| `best-pet` | `pet-performance` (25) | 1 |
| `improbable-hot-actress` | `cold-fusion` (5) | 1 |
| `different-movie` | `wrong-movie` (4) | 1 |
| `who-stole-movie` | `second-guy-steals-movie` (1) | 1 |

`belated-quote` pages are best lines "newly appreciated" or "grown funnier
over time". The banner is the same and so is the award, picked in hindsight.

**Keep separate: the five `-proposal` ids** (`remake-`, `hottest-take-`,
`weak-link-`, `pee-break-` and `movie-title-spoken-proposal`, 1 page each).
They're meta-discussion about the category itself, not an award. One example:
"a joking suggestion to rename the hottest-take award; no permanent rename is
established". Folding them would count a proposal as a winner.

**Your call: the two "Action Is the Juice" awards.**
- "The Action Is the Juice Award for Best Milking of the Moment"
  (`milking-moment`, 4 pages);
- "Tom Sizemore Action Is the Juice Award for Best Toe-to-Toe Moment"
  (`toe-to-toe`, 7 pages).

Each carries one page with the other's id. Reading those two pages, both are
toe-to-toe picks. One reads: "Sizemore wins the **newly named** Tom Sizemore
Action Is the Juice award". That suggests one award, renamed, with its
criterion changed. Two options:
- **(a) One award:** fold `milking-moment` into `toe-to-toe`. That gives 13
  entries, and the banners keep both names.
- **(b) Two awards:** keep them separate and file the two crossed pages under
  `toe-to-toe` by hand. That needs a small per-page override file, which
  doesn't exist yet.

I'd take (a), unless you think of them as different bits.

### 2. *Aliens* `c8`: a one-off with no id at all

`c8` is "Private Hudson Game Over Man category". Its page has an opaque slug,
and no other page carries its banner, so neither rule can place it. Two
options:
- **(a) A general rule:** an opaque page whose banner appears nowhere else
  gets its own category id, made from the banner
  (`private-hudson-game-over-man-category`), as a one-off award. That's what
  it is, and the rule would also cover any future case.
- **(b) Leave it in "Uncategorised"** in the app.

I'd take (a).

### 3. Still open from earlier

- ***Dunkirk* and *Fast Five* dates:** which of the episode list and
  rewatchvault is right? Until you say, their 29 entries show without a film
  link.
- **Paging "Read the discussions" (report 026):** now worth doing. Standing
  categories have about 470 entries, and the AppTest that opens the toggle
  takes 19.7 s, up from 10.6 s at batch 2.

## Future episodes (proposal 3 from report 021)

This already works, without new code. A page that isn't stored and that no
workbook episode claims falls into the last batch, and stored pages are
skipped. So once rewatchvault publishes a new episode:

```bash
python scripts/16_load_categories.py --batch 7
python scripts/orchestrate.py --stages categories
```

That fetches only the new pages (about 20–50 requests) and checks them. Two
refinements are worth making later:
- a `--new` alias that says what it does;
- a 2027 entry in `YEAR_BATCHES`, though 2027 already falls through to the
  last batch.

*Friday the 13th* is the first test: it isn't on rewatchvault yet.

## Verification

- `tests/test_categories.py` 39 and `tests/test_category_build.py` 32: **71
  pass** on the complete database.
- The coverage test now checks that the "Partial data" note shows exactly when
  coverage is incomplete.

## Next

1. Your decisions: the alias list (fold 9, keep the 5 proposals), the "Action
   Is the Juice" choice, `c8`, and *Dunkirk* and *Fast Five*.
2. Then **phase 4: totals**. The proposal in report 023 covers most-mentioned
   people and films, each host's picks, and category lifespans.
3. Optional now: page the discussions toggle.
