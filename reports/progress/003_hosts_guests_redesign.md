# 003 — Hosts & Guests: rebuilt around everyone but Bill

Date: 2026-09-15.

## Decisions taken on the proposal's open questions

| Question | Decision | How it was applied |
| --- | --- | --- |
| "Mallory Rubin*" | Merge | `person_name()` drops a trailing `*`; applied once in `load_data()`, so every section counts the same people |
| "Booked on" leans panel | Keep | Framed as booking, not taste; only leans that survive a Benjamini–Hochberg correction are shown |
| Without-Bill panel | Keep | Closes the page, grouped by who hosted |
| Bill Simmons in the lookup | Left out (the proposal's default; not objected to) | The Without-Bill panel answers the inverse question |

## Data findings

| Measure | Value |
| --- | ---: |
| Film episodes | 483 (Dec 2015 – Sep 2026) |
| Bill Simmons in the room | **438 (90.7%)**; hosts 437, guest on 1 (*Die Hard*, ep 42, Chris Ryan hosting) |
| Episodes without him | **45** |
| Other people | 62 |
| … on once / 3+ / 5+ / 15+ episodes | 27 / 31 / 18 / 10 |
| Distinct episode numbers | 473 over 483 airings |
| Film episodes per year | 1 (2015) to 67 (2020) |

- **The proposal's figures were off by one.** It said 439 and 44. Those came
  from matching on the substring "Simmons", which also counted Kari Simmons on
  *The Holiday* (ep 107). The code matches the full name, and
  `test_leaving_out_the_anchor_is_an_exact_match` pins that.
- **The episode number is not a per-airing key.** Revisits reuse it (*Notting
  Hill* is ep 73 in 2019 and in 2024), so rooms are keyed on `raw_episode_id`.
  `links_df` now carries that column.
- **Nothing in the pipeline normalises guest names.** The only variant in the
  data is "Mallory Rubin*" on ep 320 (*A Few Good Men*). Merging it takes her
  from 41 episodes to 42. A test fails if two spellings of one name ever
  survive normalisation.

## Results: what each regular gets booked on

Each regular (15+ episodes) was compared with every episode they weren't on,
on nine measures:
- Rotten Tomatoes score;
- the film's age when the episode aired;
- the share of episodes in each of the 7 genres that appear on 40+ episodes.

That makes 90 comparisons. Each is a two-sided permutation test with 4,000
shuffles and a fixed seed, so a reload never moves a p-value.

- **42 of 90 are significant at p < 0.05. 35 survive the BH correction at
  q < 0.05.**
- About 4.5 of the 90 would clear p < 0.05 by chance alone, so the correction
  matters. Van Lathan's RT dip (−5.6 points, p ≈ 0.02 in profiling) is the
  clearest casualty.

| Person | Episodes | Leans that survive (q < 0.05) |
| --- | ---: | --- |
| Chris Ryan | 285 | RT +7 pts; Thriller 44% vs 26%; Crime 32% vs 19%; Comedy 27% vs 45%; Romance 12% vs 31% |
| Sean Fennessey | 180 | RT +11 pts; Action 16% vs 31%; Romance 12% vs 24% |
| Van Lathan | 76 | **none** |
| Amanda Dobbins | 44 | Romance 59% vs 16%; Comedy 61% vs 31%; Action 7% vs 27%; Thriller 18% vs 38%; Crime 9% vs 28%; films 5 yr newer |
| Mallory Rubin | 42 | Drama 79% vs 53%; Action 7% vs 27%; Crime 10% vs 28% |
| Shea Serrano | 34 | Action 71% vs 22%; Thriller 56% vs 35%; Drama 29% vs 57%; Comedy 15% vs 36%; Romance 3% vs 21%; films 6 yr newer |
| Kyle Brandt | 31 | RT −20 pts; films 8 yr older; Action 58% vs 23%; Adventure 29% vs 8% |
| Juliet Litman | 29 | Romance 79% vs 16%; Comedy 76% vs 31%; Thriller 3% vs 39%; Action 0% vs 27%; Crime 3% vs 28%; films 5 yr newer |
| Wesley Morris | 25 | **none** |
| Jason Concepcion | 19 | Action 74% vs 23%; Adventure 32% vs 8% |

**Reading it.**
- The sheet doesn't record who picked a film, so this is booking, not taste.
- Two groups separate clearly:
  - Juliet Litman and Amanda Dobbins are the rom-com bench.
  - Kyle Brandt is booked on older, lower-rated action.
- Chris Ryan's and Sean Fennessey's +7 and +11 RT points say the
  best-reviewed films go to the core crew.
- Van Lathan and Wesley Morris are booked across the catalogue with no
  detectable lean. That is a result, not a gap, and the page says so.

**Caveats.**
- The comparisons aren't independent:
  - a film carries several genres;
  - Ryan and Fennessey share 136 episodes;
  - "everyone else" includes the Bill-only episodes.
- BH is robust to the positive dependence this produces, but the q-values
  should be read as a screen, not as exact error rates.

## Room structure worth knowing

- **Most common pairs** (Bill aside): Ryan + Fennessey 136, Ryan + Lathan 40,
  Dobbins + Litman 22.
- **Most common lineups:**
  - Ryan + Fennessey is the whole panel beside Bill 95 times;
  - Ryan alone with Bill 50;
  - Ryan + Lathan 31;
  - Kyle Brandt alone with Bill 21.
- **Eras**, as each person's share of that year's episodes:
  - Fennessey falls from 69% (2018) to 22–28% (2025–26);
  - Van Lathan rises from 12% (2020) to 28–30%;
  - Shea Serrano's last episode is Sep 2024;
  - Joanna Robinson starts in 2025.
- **Without Bill (45 episodes):** Chris Ryan hosts 20, Juliet Litman 12, Sean
  Fennessey 7, Craig Horlbeck 3, and Donnie Kwak, Jason Concepcion and Van
  Lathan 1 each.

## What changed

- **`views.py`, a new Hosts & guests block** (pure, Streamlit-free):
  - `ROOM`, `ANCHOR`, `person_name`;
  - `room_long`, `bench`, `co_appearances`, `lineups`, `appearances_by_year`;
  - `permutation_diffs`, `bh_adjust`;
  - `lean_phrase`, `lean_value`, `MEASURE_LABEL`.
- **`app.py`:**
  - `load_data()`: links carry `raw_episode_id`, and room names are
    normalised once across `episodes`, `links`, `merged` and `ch`.
  - **Hosts & Guests rebuilt as seven panels:**
    1. context tiles;
    2. person lookup: a poster per episode that opens its dossier, "who they
       sit with", their leans and their Cruise/Hanks record, plus a
       `?person=` deep link;
    3. the bench table;
    4. "who's on when": a heatmap of share of each year's episodes;
    5. "who sits together": a co-appearance matrix and the most common
       lineups;
    6. leans, with a table of all 90 comparisons;
    7. without Bill.
  - **Removed:** the episodes-by-host bar, the top-guests bar, genre share by
    host, guest appearances over time (raw counts), the host × guest heatmap
    and decade by host.
  - **The dossier** gains "Look up who was in the room" buttons, which hand
    the name to the lookup through `open_person()`. They are buttons, not
    links, so the session and filters survive.
  - **Overview:** the regulars row leaves Bill out, the note states his
    share, and the Hosts & Guests door reads "62 besides Bill".
  - **Cruise vs. Hanks** reads its guest floor from the shared
    `VERDICT_FLOOR` (still 8).
  - **Presentation:** `ranked_list(wide=)`; CSS `.rw-lean` and
    `.rw-rank.wide`; the unused `.rw-reg.is-host` rule is removed.
- **`tests/test_hosts.py`, new.** It covers:
  - the helpers, on hand-built frames;
  - three premises read from the live database: the anchor's share, the
    episode number not being a key, and no two spellings of one name;
  - the section through AppTest: Bill isn't offered, the lookup shows every
    episode (Mallory Rubin, 42), a `?person=` cold load works, and the
    dossier hands off to the lookup.

## Verification

- `tests/test_hosts.py` unit and data tests: 30 pass on the first run.
- Full suite: **673 pass, 0 fail** (7 min 57 s). That includes the four
  AppTest tests in `test_hosts.py` and the existing dossier and Cruise/Hanks
  suites, which now read normalised names.
- Browser preview (port 8502):
  - `?person=Juliet+Litman` cold-loads onto the section with her 29
    episodes.
  - All seven panels render, with no server or console errors.
  - The heatmap puts the earliest arrival (Chris Ryan) at the top.
  - The Overview regulars row starts with Chris Ryan, "285 of 483 · hosted
    21".

## Open items

1. **The sheet itself still says "Mallory Rubin\*".** The app normalises it.
   Fix it at the source when convenient.
2. ~~**The dossier's ‹ › arrows don't walk the lookup's shelf.**~~ Done in a
   follow-up. The arrows now step through the selected person's films in grid
   order, newest first. A revisited film is visited once, at its newest
   airing. `person_shelf()` defines that order for both the grid and the
   arrows. A film opened from the Without Bill grid is usually not on the
   picked person's shelf, so it still gets no arrows.
3. **The default pick is heavy.** It is the busiest person, Chris Ryan, which
   draws 285 poster cards. Movie Explorer already draws 456, so this is within
   what the app does, but it is the slowest first view on this page.
