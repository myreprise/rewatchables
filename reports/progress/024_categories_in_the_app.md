# 024 — Categories in the app: phases 1–3

Date: 2026-10-12. Branch: none (uncommitted on `master`).
Previous: [023 — category data in the app: proposal](023_category_app_proposal.md).

## TL;DR

Decisions taken in review of report 023:
- Categories goes under **The Bits**.
- The Streamlit app is **local only**.
- **`dion` is folded into `heat-check`**, and **`casting` into
  `recasting`**.
- Build **phases 1–3 now**, on the pilot data.

All three phases are built and working on the pilot's 211 entries.

| Phase | What | State |
| --- | --- | --- |
| 1 | Step 17 builds six tables from the stored pages | 211 entries; **all 10 episodes linked**; 62 categories; 819 bullets; 534 links; 14 picks |
| 2 | **Categories** section under The Bits | Coverage note, tiles, episode view, category view; checked in the live app and by AppTest |
| 3 | "In the categories" block on each film's page | Renders for films with entries and draws nothing for the rest; checked by AppTest |

**One entry has no category:** `c58`, from *Heat* (2021). Its banner,
"Apex Mountain", is also used by `american-pie-apex-wrapper-006`, the only
`apex-wrapper` page on the whole site. That page is an Apex Mountain mention in
the *American Pie* episode's intro. The rule in report 023 is to report an
ambiguous banner, not guess, so `c58` sits under "Uncategorised" until you
decide whether **`apex-wrapper` folds into `apex`**. If it does, that's one
line in `data/category_aliases.csv` and one re-run of step 17.

## Phase 1 — step 17, `s17_build_categories`

- **What it does.** It reads `raw_category_pages`, takes the newest version of
  each page, and rebuilds these tables from scratch:
  - `category_episode_map`;
  - `curated_categories`;
  - `curated_category_entries`, `_bullets`, `_mentions` and `_picks`.

  The schema is in `curated_zone.sql`. The step makes no network calls. With
  no pages stored it builds empty tables.
- **In the orchestrator** as stage `categories`, which is safe in `--all`. It
  has to run there: it copies `movie_id`, and a curated rebuild reissues
  `movie_id`s. Step 16 stays manual, and the step-numbering test now counts
  manual steps so that the numbers still run 1..N.
- **Episode linking.** An episode links when the date is within ±2 days *and*
  the title agrees. Otherwise it uses an override, or stays unmapped and is
  logged. All 10 pilot episodes link by the rule:
  - The Godfather Part II, F1 and Texas Chain Saw are each dated a day
    *later* on rewatchvault.
  - *Rocky IV* correctly beats *The Exorcist*, which aired two days later.
- **`data/category_episode_overrides.csv`** has 8 rows: the five 2017-08-07
  placeholder dates and the three title aliases. They're unused by the pilot
  but tested. *Dunkirk* and *Fast Five* are deliberately left out of it, so
  they'll show as unmapped until you settle their dates.
- **`data/category_aliases.csv`** has 2 rows: `dion → heat-check` and
  `casting → recasting`. A chain of aliases is refused.
- **Categories for opaque slugs.** 3 of the 4 opaque-slug pages in the pilot
  took their category from their banner. `c58` couldn't, as above.
- **Both steering files are tracked:** two `!data/...` exceptions were added
  to `.gitignore`.

## Phase 2 — the Categories section

Its position in the menu is **The Bits → Categories**, after Cruise vs. Hanks.

- **Coverage note, before any number:** *"Partial data. 10 of 473 episodes,
  211 entries so far. Counts here cover only these episodes; more arrive batch
  by batch."* It disappears when the stored episodes reach every episode the
  workbooks know.
- **Tiles:** Entries 211 · Episodes 10 · Categories 62 · Names linked 504 ·
  Hosts' picks 14.
- **By episode**, the default view:
  - pick an airing ("EP 484 · The Texas Chain Saw Massacre · 5 Oct 2026") to
    see its poster card, which opens the film;
  - then a card per entry in on-air order: minute, category as aired, family
    badge, answer, and links to rewatchvault and the transcript;
  - each card has an expander with the discussion: people in bold, films in
    mint italic, a speaker on each bullet, and the hosts' picks.
- **By category:**
  - categories are ordered standing, segments, "the most…", one-offs, busiest
    first, with "Uncategorised" last when it has anything;
  - a fact line shows entries, episodes, first and last aired, and how many
    names the category aired under;
  - a table gives date, episode, film, category as aired, answer, minute,
    points and a rewatchvault link;
  - a toggle opens every discussion below the table. It's a toggle because
    Streamlit can't nest expanders, which the first AppTest run caught.
- **Source line:** *"From rewatchvault.com, an independent archive of The
  Rewatchables. Every entry links to its page there."*

The card and discussion renderers live in `app/category_cards.py`, outside
`app/sections/`. The first version put them in the section module, and the
dossier importing it caused a circular import (sections → explorer → dossier).
The live app caught that on its first start.

## Phase 3 — the film page

`render_film_block()` sits between the episode list and "The film":
- a heading, *"In the categories — 39 entries"*;
- the coverage note;
- then each airing's entries, headed "EP 484 · … · 39 entries", with the same
  cards and discussions.

Revisits stay separate because it groups by airing. A film with no entries
draws nothing.

## A correction to report 021

Report 021 said rewatchvault dates run a day **earlier** than the episode list.
They run a day **later**. Its offset was the list's date minus rewatchvault's,
and −1 means rewatchvault's date is the later one. The pilot shows it plainly:
*The Godfather Part II* is 2019-12-16 in the list and 2019-12-17 on
rewatchvault. The linking rule is a symmetric ±2-day window, so nothing it
decided changes. Report 021, step 17's docstring and the tests now say
"later".

## Two things the test suite caught

1. **The orchestrator dropped step 17 from every default run.**
   `select_steps` took the last step number to be `len(STEPS)`. That held
   while the steps ran 1..15 with no gaps. With step 16 manual, `len(STEPS)` is
   16, so `--all`, `--from N` and the default run all stopped short of 17,
   silently. It now uses `STEPS[-1][0]`. The dry run shows
   `Steps: 5, …, 15, 17`, and a test checks that `--all` never selects a
   manual step.
2. **The public site would have renumbered itself.** The site's section cards
   take their number from the app's rail. Adding Categories to the rail would
   have made the site's Upcoming "13", with no 12 on the site. Categories is
   now explicitly app-only:
   - `APP_ONLY` and `SITE_SLUGS` are new in `app/state.py`, with the reason
     written there;
   - the site export skips app-only sections and numbers by `SITE_SLUGS`, so
     the site is unchanged;
   - the app's own Overview gains a **Categories** card ("211 entries");
   - `test_site_db` checks that no door leads to an app-only section and that
     the site's numbering runs without gaps.

## Verification

- **Tests.**
  - `tests/test_category_build.py`, 32 tests:
    - episode rules: the window, neighbours, several-to-one, overrides,
      unmapped;
    - titles;
    - aliases, including a refused chain;
    - banner placement, including the ambiguous case;
    - the end-to-end build, its links and offsets, and an identical rebuild;
    - the loader on an old database and its coverage counting;
    - the coverage note's wording;
    - AppTest on the real database: section, category view, discussions
      toggle, one category from each family plus Uncategorised, and the
      dossier block.
  - `tests/test_categories.py`: 35.
  - Orchestrator and site tests updated, as above.
  - **Full suite, app tests included: 951 passed, 1 failed.** The failure is
    `test_the_workbook_renders_to_exactly_the_tracked_csv`, the uncommitted
    *Friday the 13th* edit to `data/episodes.xlsx`. It predates this work and
    clears when step 01 renders the workbook (`orchestrate.py --from 1`).
- **Live app on :8502.** The section rendered with the expected tiles and
  cards. The live view caught one bug that AppTest didn't: the coverage note
  read "473episodes", because `html()` joins lines without a space. It's fixed
  and has a regression test.

  The browser pane was hidden for most of the session, which stalls Streamlit
  reruns, so the dossier was verified by AppTest rather than in the browser.

## Next

1. **Your call:** fold `apex-wrapper` into `apex`?
2. **Batch 1** (2017–2019, about 25 min), on your go-ahead. Then rebuild with
   `--stages categories`, and the app picks it up on reload.
3. **Phase 4 (totals)** waits for batches 1–7, as planned.
