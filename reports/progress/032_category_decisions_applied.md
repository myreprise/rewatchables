# 032 — Category data: report 031's decisions, applied

Date: 2026-10-13. Branch: none (uncommitted on `master`).
Previous: [031 — batch 7, and the archive is complete](031_category_batch_7_complete.md).

## TL;DR

All four decisions are applied. **Every one of the 11,530 entries now has a
category and a linked episode**: 0 uncategorised, 0 unmapped, and 243
categories, down from 252.

| Decision | Applied as | Result |
| --- | --- | --- |
| 1. Fold the 9 stray ids, keep the 5 `-proposal` ids | 9 rows in `data/category_aliases.csv` | Best line 309 (was 304), Research 470, Remake 412, That Guy 433. The proposals stay separate |
| 2. "Action Is the Juice": one award, renamed | `milking-moment → toe-to-toe` | **Toe-to-Toe, 13 entries under its 2 banners** |
| 3. A banner seen nowhere else gets its own id | `resolve_category` in step 17 | *Aliens* `c8` becomes `private-hudson-game-over-man-category`, a one-off |
| 4. *Dunkirk* and *Fast Five* | checked against the podcast feed, then 2 override rows | Both linked, so the 29 entries now open their film |

## 4 — Dunkirk and Fast Five: the feed says rewatchvault is right

Report 031 asked which source was right. I didn't have a recommendation, so I
found evidence instead, with one request to the show's RSS feed
(`feeds.megaphone.fm/the-rewatchables`, 485 items):

| Episode | Episode list | rewatchvault | **Podcast feed** |
| --- | --- | --- | --- |
| *Dunkirk* | 2019-12-20 (ep 112, before *Ripley*) | 2019-12-30 | **Mon 30 Dec 2019**, after *Ripley* (24 Dec) |
| *Fast Five* | 2019-05-31 (ep 77, after *Austin Powers*) | 2019-04-01 | **Mon 1 Apr 2019**, between *Pretty Woman* (26 Mar) and *Major League* (10 Apr) |

**The episode list has both dates wrong.** Two things follow.
- **Linked now, without touching the list.** There is one *Dunkirk* and one
  *Fast Five* in each source, so `data/category_episode_overrides.csv` maps
  rewatchvault's episode to the list's airing: 112 and 77. Each row says
  "remove once the list is corrected".
- **Correcting the list is yours.** `data/episodes.xlsx` is your source of
  truth, and it has an uncommitted edit of yours in progress, so I haven't
  touched it. If you correct the dates, note that *Fast Five*'s position
  bears on the numbering too: it's numbered 77 but aired between your 65 and
  66.
- **Step 17 copes with that fix on its own.** An override whose airing has
  disappeared is reported and the date-and-title rule takes over. Once the
  dates match the feed, the rule links both episodes and the two override
  rows become dead weight to delete. A test covers exactly this.

## 3 — c8, and a correction to the category families

`c8` ("Private Hudson Game Over Man category") has an opaque slug, a banner no
other page carries, and **no icon**. Applying the own-banner rule showed that
step 17 had been calling every icon-less category **standing**, because an
unknown icon defaulted to standing. That was wrong for more than `c8`:
- **108 pages have no icon.** They make up **67 categories**, and no category
  mixes icon and no-icon pages.
- **They're one-offs:** "Blake Lively Story Time", "Crazier Game to Attend",
  "Weightlifting Scouting Report", "Best Memory Hole".
- **The pilot showed the symptom:** "Peter North Effort Award — STANDING" in
  the app.

Pages with no icon now say nothing about the family, and a category with no
icon at all is `one_off`.

| Family | Before | After |
| --- | ---: | ---: |
| Standing (has its own icon on rewatchvault) | 90 | **21** |
| One-off | 129 | **190** |
| Segment | 32 | 31 |
| The most… | 1 | 1 |

**Known looseness:** a few icon-less categories recur, for example "The Dennis
Peck Relationship Test" (8 entries) and "Best Former That Guy" (3). The app
labels them "One-off award". If that bothers you, a fifth family ("Occasional")
for icon-less categories with several entries is a small change. Say if you
want it.

## Verification

- `tests/test_category_build.py`, `tests/test_categories.py` and
  `tests/test_orchestrate.py`: **101 pass**. New tests:
  - a stale override falls back to the rule;
  - the feed-dated overrides are present;
  - the alias list folds the strays and holds no `-proposal` id;
  - a banner seen nowhere else becomes its own category;
  - a category with no icon is a one-off.
- Rebuilt with `--stages categories`: 11,530 entries, 473 episodes, 0
  unmapped, 0 uncategorised, 243 categories.

## Next

1. Paging the discussions toggle: **on hold** until you've decided whether it's
   worth it (see the reply that accompanies this report).
2. **Phase 4, totals**, on your go-ahead.
3. The episode-list dates for *Dunkirk* and *Fast Five*, at your convenience.

## Addendum, 2026-10-13: the episode list corrected

You corrected `data/episodes.xlsx` to the feed's dates, in the list's own
convention of the US release day (the feed's publish time in UTC is the
evening before in the US):
- **_Dunkirk_ is 2019-12-30.**
- **_Fast Five_ is 2019-03-31.** Its episode number stays 77.

You re-ran `orchestrate.py --from 1`, and both episodes then linked by the date
and title rule. That's the fallback the stale overrides were built to trigger.
The two override rows are now removed, and the test that pinned them now
checks that they're gone. Step 17 rebuilds with 473 episodes and **0 unmapped,
both via `date_title`**.
