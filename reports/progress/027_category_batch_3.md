# 027 — Category data: batch 3 (2022)

Date: 2026-10-13. Branch: none (uncommitted on `master`).
Previous: [026 — category data: batch 2](026_category_batch_2.md).

## TL;DR

**Batch 3 is in.**
- **The fetch:** 1,402 new pages, **0 failures**, in 24 min 23 s (1.04 s a
  page). The other 4 of the batch's 1,406 were already stored by the pilot,
  from *Boogie Nights* part 1.
- **The first check failed on 2 bullets** that "read excised". Both gaps are in
  rewatchvault's own prose, not dropped by the parser. The check now tests
  exactly that, so this class of false alarm is closed for good rather than
  one pattern at a time. With it, the pilot and batches 1–3 all **pass**.
  Batch 3:
  - all 1,406 pages parse;
  - every page's bullets match its own count;
  - all **4,398 of 4,398** workbook discussion cells are found on their pages;
  - no field disagrees with the workbooks.
- **The categories, rebuilt:** **4,860 entries across 274 of 473 episodes, 124
  categories**, 24,973 bullets, 20,646 links and 497 hosts' picks.
  - Every entry has a category, including the 6 opaque *Maverick* pages
    (`c43`–`c48`), which took theirs from their banners.
  - Only *Dunkirk* and *Fast Five* are unmapped.
- **Read it:** `logs/categories/batch-3-entries.xlsx` (1,406 entries, 6,040
  bullets, 95 picks).
- **Usage:** measured for this batch, as you asked. See the end of this
  report.

| | Pilot | 1 | 2 | 3 | Together |
| --- | ---: | ---: | ---: | ---: | ---: |
| Pages | 211 | 1,365 | 1,958 | 1,406 | 4,860 |
| Episodes | 10 | 97 | 119 | 54 | 274 of 473 |
| Bullets | 819 | 7,474 | 11,067 | 6,040 | 24,973 |
| Pages the workbooks lacked | 17 | 19 | 49 | 24 | |
| Person links the workbook rows had dropped | 65 | 962 | 1,100 | 685 | |

## The check, fixed properly this time

Batches 1 and 2 each turned up a pattern that looked like a cut-out name and
wasn't: decimals (".406"), then ellipses ("... of focus"). Each got its own
exception. Batch 3 found a third:
- "moving to the 1990s ." (*Grease*);
- "seasons through the 1960s ." (*School Ties*).

That's a space before the full stop, and it's there in **the page's own
HTML**, with no element removed. It's rewatchvault's typo.

Patching patterns can't keep up with prose. The question the check exists to
answer is narrower: **did the parser drop anything?** It now answers that
directly.
- `rewatchvault.source_bullet_texts()` reads each bullet's text as the page
  has it, with the speaker removed.
- When a parsed bullet that "reads excised" equals that text, the gap is the
  site's. It's counted as a **source quirk**, listed, and doesn't fail the
  gate.
- A gap the parser introduced still fails it.
- Two tests cover this: the parsed bullets equal the source text for the
  fixture, and an injected source-side gap passes as a quirk.

The decimal and ellipsis exceptions stay. They're cheap and they keep quirks
out of the problem list.

## Verification

- `tests/test_categories.py` 39 and `tests/test_category_build.py` 32 pass on
  the batch-3 database.
- Re-checked offline after the change: pilot, 1, 2 and 3 all PASS.

## Next

1. **Batch 4** (2023: 53 episodes, 1,684 pages, about 28 min), on your
   go-ahead.
2. Optional, from report 026: page the "Read the discussions" toggle.
3. Still open: *Dunkirk* and *Fast Five* dates, and the multi-id banners in
   report 025 (before phase 4).

## Usage for this batch

Measured as asked: readings just before the batch started and just after this
report was written. Both are in `logs/categories/usage-batch-3.md`.

| Limit (Max plan) | Before | After | Change |
| --- | ---: | ---: | ---: |
| 5-hour window | 12% | 15% | **+3 points** |
| Weekly, all models | 64% | 65% | **+1 point** |
| This session's context | 471,218 | 487,010 tokens | +15,792 |

**How to read it:**
- **These are upper bounds.** Three other sessions were active during the
  same 30 minutes, two NFL sessions and the audio one, and their usage lands
  in the same totals.
- **The plan reports whole percentages,** so "+1 weekly" means somewhere
  between about 0.5 and 1.5 points.
- **This was a middling batch.** It needed one fix cycle: investigate, change
  the check, add tests, re-check four batches, rebuild. Batches 1 and 2 needed
  more. A batch that passes first time would cost less.

**Per batch, in this session, about 1 point of the weekly limit, at most 2 if
it needs real debugging.** Batches 4–7 would then take about 4–8 points. The
weekly limit is at 65% with 3 days 4 hours to its reset, so that fits.

**Why it costs that:** about 25 steps, each re-reading this conversation's
roughly 480k tokens. The fetch itself costs nothing.

**To spend less:**
- **Run the batches yourself** (`--batch 4`, then `--stages categories`). The
  checks decide pass or fail without me, so that's zero usage unless one
  fails.
- **Bring failures to a fresh session.** Reports 021–027 and the memory note
  carry what's needed, so it starts from a small context.
