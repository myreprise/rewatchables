# 023 — Category data in the app: proposal

Date: 2026-10-12. Branch: none. Nothing in the app is built yet; this report
is for review.
Previous: [022 — category data: the pilot batch](022_category_pilot_batch.md).

## TL;DR

**To read the pilot data today**, open
`logs/categories/batch-pilot-entries.xlsx`. The new `--export` sub-command
writes it from the stored pages, without touching the network, and it has
three sheets:
- **Entries:** 211 rows, one per category entry.
- **Discussion:** 819 bullets, with names restored and the speaker on each.
- **Hosts' picks:** 14 rows.

Each later batch can be read the same way:
`python scripts/16_load_categories.py --export 1`.

**For the app, the proposal has two layers.**
- **A curated build, step 17.** It makes no network calls, so it can run in
  the orchestrator. It rebuilds the category tables from whatever pages are
  stored and links each entry to its airing.
- **A Categories section** under "The bits", next to Cruise vs. Hanks, plus
  an "In the categories" block on each film's page. The section has an
  episode view and a category view. Every number on it states how many
  episodes it covers, because until batches 1–7 are in it covers 10 of 473.

## Why build the curated layer now

Report 022 said the curated tables should wait for all batches. The app needs
them, and there's a way to do it that removes the reason for waiting.
**Step 17 drops and rebuilds its tables from the raw pages on every run**, the
way step 03 rebuilds staging. A design change, or a new batch, then costs one
re-run and nothing has to be migrated. The pilot already shows every structure
I know of: film links, links inside answers, the hosts' picks and opaque slugs.

## A. The data: step 17, `s17_build_categories`

Step 17 is a new `categories` stage in `orchestrate.py`. It makes no network
calls and reads only `raw_category_pages`, so `--all` runs it safely. With no
pages stored, it builds empty tables.

| Table | One row per | Main columns |
| --- | --- | --- |
| `category_episode_map` | rewatchvault episode | `rv_episode_slug`, `episode_movie_id`, `match_rule` (`date_title` / `override`), `day_offset` |
| `curated_categories` | category | `category_slug`, `family` (`standing` / `one_off` / `segment` / `most_year`), `display_name`, `first_aired`, `last_aired`, `entries` |
| `curated_category_entries` | entry (page) | `discussion_slug`, `rv_episode_slug`, `episode_movie_id`, `movie_id`, `category_slug`, `banner`, `answer`, `transcript_seconds`, `transcript_url`, `bullet_count`, `source_url` |
| `curated_category_bullets` | bullet | `discussion_slug`, `position`, `text`, `speaker_slug`, `speaker_name` |
| `curated_category_mentions` | link | `discussion_slug`, `where` (`answer` / bullet n / `pick`), `kind` (person / movie), `slug`, `name`, `start`, `end` |
| `curated_category_picks` | host's pick | `discussion_slug`, `speaker_slug` (NULL if unidentified), `speaker_name`, `text` |

**How the episode link works**, checked against the pilot, where all 10
episodes link:
- **The rule:** air date within ±2 days, and the title must agree. *Rocky IV*
  has *The Exorcist* two days away, and the title rule picks the right one.
- **Several to one:** rewatchvault splits *Boogie Nights* into
  `boogie-nights-part-1` and `-part-2`, and the episode list has one row,
  "Boogie Nights (Part 1 and 2)". Both map to it.
- **Overrides:** the exceptions from report 021 go in a tracked
  `data/category_episode_overrides.csv`. These are the five 2017-08-07
  placeholder dates and the three title aliases. *Dunkirk* and *Fast Five* stay
  unmapped and are flagged, not guessed, until you settle which date is right.
- **Revisits:** *Heat* has three airings on rewatchvault (`heat-2017`,
  `the-re-heat`, `heat`). Each date picks out a different airing, so each maps
  to its own episode.

**Categories without a slug.** The 56 opaque-slug pages (`c58` and the like)
take their category from the banner. All 56 banners also appear on pages that
do have a slug, but two of them appear under two slugs each, so the site
itself has duplicate category ids:
- "The Dion Waiters Award for Best Heat Check Performance" is used under both
  `dion` and `heat-check`;
- "Casting What-Ifs" is used under both `casting` and `recasting`.

Proposed handling:
- A small tracked alias list folds the duplicates together (`dion` into
  `heat-check`, and `casting` into `recasting`, if you agree they're the same
  category).
- Every banner then resolves to exactly one category.
- A banner that resolves to none, or to more than one, is reported, not
  guessed.

The alias list also affects totals. Without it, Heat Check counts would be
split across two ids.

## B. The app

### Loading

`load_categories()` goes in `app/data.py`. Like `load_upcoming()`, it has its
own cache and returns empty frames when the tables are missing, so a database
built before step 17 still renders every other section. It also returns a
coverage record: episodes covered and entries stored, against the sitemap's
11,530.

### A "Categories" section under "The bits"

"The bits" exists for recurring segments, and Cruise vs. Hanks is already
there. Categories is the same kind of thing at a larger scale.

1. **Coverage strip at the top.** For example: *"Pilot data: 10 of 473
   episodes, 211 of 11,530 entries. Totals below count only these."* It
   disappears once coverage is complete. Without it, a leaderboard built from
   ten episodes would read as the show's history.
2. **Episode view (the default).**
   - Pick an episode, and its entries appear as cards in the order they aired
     (by transcript time).
   - Each card shows the category as aired, the answer, the minute, and links
     to the transcript and the rewatchvault page.
   - Expanding a card shows the discussion, with names in bold, a speaker on
     each bullet, and the hosts' picks.
3. **Category view.**
   - Pick a category. Standing ones are listed first (Apex Mountain, Who Won
     the Movie?, Hottest Take…), then the one-off awards and segments.
   - The result is a table of every episode's answer: date, film poster,
     answer and minute.
   - This is the view that becomes useful as batches arrive.
4. **Totals (switched on per batch, as coverage allows).**
   - Most-mentioned people and films.
   - Each host's picks, e.g. how often Bill and Chris agree on "Who Won the
     Movie?".
   - A lifespan chart of categories: first and last aired, which shows when
     each one was introduced and retired.

   These are not built until batches 1–7 are in. Built on ten episodes they
   would mislead, and with this little data they can't be tested meaningfully.

### On each film's page

The dossier gets an **"In the categories"** block. It lists the film's
entries, grouped by airing so revisits stay separate, with answers shown and
discussions collapsed. It appears only when the film has entries.

### Attribution and the text

Every card and row links to its rewatchvault page. The section footer reads:
*"From rewatchvault.com, an independent archive of The Rewatchables."*

Showing the discussion text in the app is fine as long as the app runs
locally. Putting it on the public site is the separate decision still open
from report 021.

### Tests

- Step 17 rebuilds from the fixture page, and building twice gives the same
  tables.
- The episode link, including the *Boogie Nights* several-to-one case and an
  override.
- The loader returns empty frames on a database without the tables.
- An AppTest renders the section with no data and with the fixture, and checks
  that the coverage strip shows.

## Phasing

| Phase | What | Needs |
| --- | --- | --- |
| 1 | Step 17, the overrides CSV and tests | nothing new; runs on the pilot |
| 2 | The Categories section: coverage strip, episode view, category view | phase 1 |
| 3 | The dossier block | phase 1 |
| 4 | Totals | batches 1–7 |

## Your decisions

1. **Where it goes:** under "The bits" (my recommendation), or a nav group of
   its own?
2. **Does the Streamlit app only ever run locally?** If it's deployed
   anywhere public, the discussion text should stay out of it until
   rewatchvault has answered, the same as for the site.
3. **Category aliases.** Should `dion` fold into `heat-check`, and `casting`
   into `recasting`? Batches 1–7 will probably turn up more pairs like these,
   and each one goes on the same list for you to approve.
4. **Build phases 1–3 now, on the pilot data?** The alternative is to run
   batches 1–7 first, which gives the first look at real totals sooner but
   takes longer to show you anything in the app.
