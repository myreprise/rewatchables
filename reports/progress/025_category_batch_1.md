# 025 — Category data: batch 1 (2017–2019)

Date: 2026-10-12. Branch: none (uncommitted on `master`).
Previous: [024 — categories in the app](024_categories_in_the_app.md).

## TL;DR

**`apex-wrapper` is folded into `apex`** (approved). `c58`, *Heat* (2021),
now takes Apex Mountain from its banner, and the pilot has nothing left
uncategorised.

**Batch 1 is in.**
- **The fetch:** 1,315 new pages, **0 failures**, in 24 min 57 s (1.14 s a
  page). The other 50 of the batch's 1,365 pages were already stored by the
  pilot.
- **The first check failed, on two findings.** Neither was a broken page, and
  both are fixed. With the fixes, the batch and the pilot both **pass**:
  - all 1,365 pages parse;
  - every page's bullets match its own count;
  - all 6,524 workbook discussion cells are found on their pages;
  - no field disagrees with the workbooks.
- **The categories, rebuilt:** **1,526 entries across 104 episodes, 81
  categories**, 8,034 bullets, 9,839 links and 184 hosts' picks.
  - Episode linking: 2 unmapped, *Dunkirk* and *Fast Five*, as expected
    while their dates are open.
  - All five placeholder-date episodes and *Ocean's 11* linked through the
    overrides file.
- **Read it:** `logs/categories/batch-1-entries.xlsx` (1,365 entries, 7,474
  bullets, 179 picks), or the app's Categories section.

| | Pilot | Batch 1 | Together |
| --- | ---: | ---: | ---: |
| Pages | 211 | 1,365 (50 shared) | 1,526 |
| Episodes | 10 | 97 (3 shared) | 104 of 473 |
| Bullets | 819 | 7,474 | 8,034 |
| Hosts' picks | 14 | 179 | 184 |
| Pages the workbooks lacked | 17 | 19 | |
| Person links the workbook rows had dropped | 65 | 962 | |

## What the first check caught

1. **An entry with no discussion.** `the-natural-recasting-0202` ("Casting
   What-Ifs", answered "None found") has an answer and a transcript time but
   no discussion block.
   - The parser had treated a missing block as a broken page. It's a real
     entry with no discussion. Its bullets are now empty and its
     `bullet_count` is blank, matching the "(N)" label the page doesn't have.
     The transcript time is read from the card.
   - The check now **counts** such pages and lists each one, without failing
     the batch. A layout change that dropped the block site-wide would show as
     hundreds of them at once.
   - In the app, an entry with nothing to expand gets no expander.
2. **Batting averages read as cut-out names.** Two bullets matched the check's
   pattern: "hit .406 with a .553 on-base", and "a .350 to .370 average". A
   space before a full stop is also what a cut-out name leaves. Punctuation
   followed by a digit is now excluded, and a test covers both cases.

## Still uncategorised: 4 entries, one more alias to decide

The 22 opaque-slug pages in batch 1 (`c21`–`c53`, from *Jaws*, *Mean Girls*,
*Speed* (2017) and *Top Gun*) took their category from their banner. 18 did.
The 4 that didn't, `c21`, `c32`, `c37` and `c49`, all carry **"Who Won the
Movie?"**.

That banner also appears on `american-pie-winner-retrospective-009`, the only
`winner-retrospective` page there is: a "Who Won the Movie?" mention 3:47 into
the *American Pie* intro. It's the same pattern as `apex-wrapper`. **Folding
`winner-retrospective` into `winner`** would place all 4. It isn't done,
because a new alias is your call.

## For later: banners the site files under more than one id

Across the workbooks, 12 banners appear under two or three category ids.
Nothing in batch 1 depends on them, because no opaque page uses them. They
matter for phase 4: a total per category would otherwise split one award
across ids.

| Banner | Ids (pages) |
| --- | --- |
| Best Line from the Movie (Neil McCauley) | `best-quote` 298, `belated-quote` 4, `quote` 1 |
| Sequel, Prequel, Limited Series, or All-Black Remake | `remake` 398, `netflix` 1, `remake-proposal` 1 |
| Half-Assed Internet Research | `research` 468, `half-ass` 1 |
| The Joey Pants "That Guy" Award | `that-guy` 428, `joey-pants` 1 |
| The Stephen A. Smith Hottest Take Award | `hottest-take` 246, `hottest-take-proposal` 1 |
| The Butch's Girlfriend Award (Weakest Link) | `weak-link` 216, `weak-link-proposal` 1 |
| The Ron Burgundy Flute Award (Pee Break) | `pee-break` 73, `pee-break-proposal` 1 |
| Brandy Booth Award (Best Pet Performance) | `pet-performance` 22, `best-pet` 1 |
| Elisabeth Shue Inventing Cold Fusion Award | `cold-fusion` 5, `improbable-hot-actress` 1 |
| Judd Nelson New Jack City Award (Wrong Movie) | `wrong-movie` 4, `different-movie` 1 |
| The Action Is the Juice Award (Milking the Moment) | `milking-moment` 4, `toe-to-toe` 1 |
| Tom Sizemore Action Is the Juice Award (Toe-to-Toe) | `toe-to-toe` 7, `milking-moment` 1 |

Most of these look like one-page strays to fold, like `apex-wrapper`. Three
need a closer look first:
- the `-proposal` ids, which may be categories proposed on air rather than
  awarded;
- `belated-quote` (4 pages), which may be a real variant: a quote picked late;
- the two "Action Is the Juice" awards, which use each other's ids.

I'll bring a proposed alias list once batches 2–7 have shown the full set.

## Verification

- `tests/test_categories.py` 37 and `tests/test_category_build.py` 32 pass,
  run against the batch-1 database. That includes the AppTest section,
  category-view, discussions and dossier tests.
- New tests:
  - a page with no discussion block parses as an entry without one;
  - a page with no identity link is still an error;
  - decimals are not read as cut-out names;
  - the alias list includes `apex-wrapper`.
- The pilot was re-checked offline after the parser change: still PASS.

## Next

1. **Your call:** fold `winner-retrospective` into `winner`?
2. **Batch 2** (2020–2021: 119 episodes, 1,958 pages, about 33 min), on your
   go-ahead.
3. Still open: *Dunkirk* and *Fast Five* dates, and the multi-id banners above
   (before phase 4).
