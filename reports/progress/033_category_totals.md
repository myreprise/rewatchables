# 033 — Category data: phase 4, totals

Date: 2026-10-13. Branch: none (uncommitted on `master`).
Previous: [032 — report 031's decisions, applied](032_category_decisions_applied.md).

## TL;DR

The Categories section has a third view, **Totals**, with two parts:
- **How long each category has run:** a lifespan chart of the 31 recurring
  categories. 28 still run and 3 have been retired.
- **Who the categories name:** two rankings of film people, by the episodes
  they're named in. One counts names in the answer, the other names anywhere
  in the discussion. A category picker narrows both.

**Two of report 023's proposed totals are not built**, because the data can't
support them:
- **hosts' agreement on picks**, where the likeliest pair shares 7 pages;
- **films brought up in discussion**, where the top film comes up in 3
  episodes.

Both are explained below and named on the page.

**Verified:**
- 153 tests pass across the category, orchestrator and site test files. That
  includes 7 new ones and an AppTest of the Totals view.
- The view rendered in the live app on :8502. The screenshot showed the
  timeline squeezed by long category names, so the axis labels are now cut to
  30 characters, with the full name in the hover. I couldn't see the fix
  before the browser pane went hidden again. It's covered by a test.
- The chart's three family colours are the app's first three series colours.
  The dataviz palette validator passes them against the app's own plot surface
  (`#101211`): worst adjacent colour-blind ΔE is 10.2 (protan), and the
  normal-vision floor is 19.9.

## How long each category has run

There's one row per recurring category, a line from first to last aired, and a
dot at each end, coloured by family:
- **Recurring** means standing, segment or "the most…", with 3 or more
  entries.
- **`-proposal` ids are excluded:** they're talk about a category, not a
  category.
- **Still running** means it aired within 60 days of the latest episode, 5 Oct
  2026.

What it shows:
- **28 of 31 recurring categories are still running.** The core set has aired
  since the first episodes: Apex Mountain, Picking Nits and Recasting Couch
  since December 2016, and Probably Unanswerable Questions and the Remake
  category since December 2015.
- **3 are retired:**

  | Category | Entries | Ran |
  | --- | ---: | --- |
  | What Would Tony Romo's Director's Commentary for This Movie Sound Like? | 46 | Feb 2024 – Jan 2025 |
  | Really Fun Deleted Scenes | 7 | Sep 2022 – Jul 2025 |
  | How Long Do They Stay Together? | 4 | Mar 2019 – Jun 2022 |

- **Four categories began together on 2 June 2022:** Best Double Feature, the
  Great Shot Gordo Award, Just One Oscar, and the Butch's Girlfriend (Weakest
  Link) Award. That's the episode after "The New Categories Selection Show"
  (31 May 2022) in your episode list. The chart doesn't mark that episode,
  because the app's episode table holds film episodes only.

## Who the categories name

These are ranked lists, top 15, of the episodes in which a person is named:
- **"Named in the answer":** a link in the answer itself.
- **"Named anywhere":** a link in the answer, a discussion point or a host's
  pick.

The picker covers "All categories but Cruise or Hanks?" (the default), "All
categories", or any one recurring category. "Cruise or Hanks?" is left out by
default because its answer is one of two people by design. Even without it,
Tom Cruise leads.

| Named in the answer (default) | Episodes | | Named anywhere (default) | Episodes |
| --- | ---: | --- | --- | ---: |
| Tom Cruise | 39 | | Tom Cruise | 61 |
| Samuel L. Jackson | 39 | | Samuel L. Jackson | 53 |
| Danny Trejo | 37 | | Brad Pitt | 49 |
| Al Pacino | 34 | | Danny Trejo | 49 |
| Brad Pitt | 31 | | Harrison Ford | 48 |
| Matt Damon | 30 | | Al Pacino | 45 |

**Danny Trejo is real, and a running bit:** 33 of his 37 answer episodes are
"Is This Movie Better With…?". It isn't excluded, because unlike "Cruise or
Hanks?" the category doesn't dictate the answer. Narrowed to **"Who Won the
Movie?"**, the list is Cruise 14, Pacino 9, DiCaprio 8, then Denzel
Washington, Eddie Murphy and Robert Redford on 7 each.

**What the rankings don't count**, each found by looking at the first version
of the list:
1. **The show's own people.** Hosts and guests (Bill, Chris, Craig) have
   rewatchvault person pages, while film people have `film-person:` ids. Before
   this filter, three hosts were in the top six.
2. **A category's namesake inside it.** 79 of Roger Ebert's 85 links are in
   "Roger Ebert's review", and 76 of Dion Waiters' 105 are in his own award.
   Both topped the list for being in the name. They still count anywhere else,
   for example Dion Waiters under That Guy.
3. **Links on uncapitalised words.** rewatchvault's own linker turned "more
   common modern depictions" into the actor Common 49 times, and did the same
   with "usher", "flea", "prince" and "50": 69 links in all. A real name in
   this prose is capitalised. The rule also drops one genuine lowercase
   "mark ruffalo". The stored data is unchanged; only the ranking skips them.

**Names:** the site links "Pacino" and "Al Pacino" to one person, and 469
person ids appear under more than one name. The ranking shows the fullest:
most words, then the commonest.

## Not built, and why

- **Hosts' agreement on "Who Won the Movie?"** The picks block appears only on
  "Who Won the Movie?" pages: 430 pages and 887 picks.
  - **537 picks (61%) have no identified speaker.**
  - **The likeliest pair, Bill and Chris, both picked on just 7 pages**, and
    agreed on 1. Every other pair is smaller.

  An agreement rate on 7 observations would be noise presented as a finding.
- **Films brought up in the discussion.** **1,781 of the 2,094 film links are
  the episode's own film.** The remaining 313 spread thinly, and the
  most-mentioned other film, *Alien*, comes up in 3 episodes. A ranking would
  be ties at 2 and 3.

## Code

- **`app/sections/categories.py`:**
  - the "Totals" option on the view radio;
  - `lifespans()`, `display_names()`, `people_ranking()`, `short_label()`,
    `lifespan_figure()` and `_totals()`;
  - the figure is cached per database (`per_database("categories:lifespans")`).
- **`tests/test_category_build.py`:** 7 new tests:
  - recurring-only lifespans and the running flag;
  - fullest names;
  - the three ranking exclusions;
  - excluded categories;
  - short, distinct axis labels;
  - the AppTest of the Totals view, including the "Who Won the Movie?" filter.

## Next

- The paging and search question for "Read the discussions" (report 032) is
  still yours.
- The episode-list dates for *Dunkirk* and *Fast Five*, at your convenience.
- Nothing is committed. Everything from report 021 onwards is in the working
  tree on `master`.
