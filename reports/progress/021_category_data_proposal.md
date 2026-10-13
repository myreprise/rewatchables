# 021 — Category data: profile and proposal

Date: 2026-10-12. Branch: none. Nothing is built yet; this report is for review.
Previous: [020 — the switch, checked on the live site](020_sqlite_switch.md).

## TL;DR

The five workbooks in `data/raw/categories/` are browser-scraper exports of
rewatchvault.com's archive: **11,237 category entries across 473 episodes,
2017-08-07 to 2026-10-06**. The facts each row carries are clean:
- the episode;
- the category;
- the answer;
- the transcript timestamp.

**The discussion text is not clean.** The scraper split each discussion
into columns and pulled the person links out of the sentences. Their order
can't be rebuilt, and about 17% of rows lost bullets past the column cap.

| Question | Answer |
| --- | --- |
| Do the five files overlap? | No row is in two files. They are contiguous date slices, and each pair shares one boundary episode, split between them. **Union, don't dedupe** |
| Is there a stable key? | Yes. The discussion URL slug (e.g. `the-omen-great-shot-86`) is unique in all 11,237 rows. All 11,237 also appear in the site's sitemap |
| Is there a canonical category? | Yes. It's embedded in that slug: `<episode>-<category>-<n>`. It can be derived for 99.5% of rows, giving 165 slugs; 99.4% of rows match the site's own list of 154. The 196 banner strings are not a key: the umbrella icon `flex-bicep-web` alone covers 123 banners |
| Does it join to `episodes.csv`? | Yes, for all 473 episodes, but **not on date alone**. Only 318 match on exact date: rewatchvault dates are often one day earlier. Date ±2 days plus title matches 463. The other 10 are listed below |
| Is the scrape complete? | No. **The sitemap lists 293 discussions the scrape missed**, spread across many episodes. Moneyball and Contagion are on the site but missing from the scrape |
| Can the lost text be recovered? | Yes. Each discussion page is plain server-rendered HTML, and `robots.txt` allows crawling. The page has the bullets in order, the person links inline, and a speaker on each bullet |

**Recommendation:** use the workbooks as an index and a cross-check, not as
the source. Re-read each discussion page once, keep the raw HTML in the raw
zone, and parse it there. The same parser, run against a sitemap diff, is how
future episodes come in. Three decisions in the last section are yours.

## What's in the files

All five files have the same layout:
- one sheet;
- a header row of CSS class names (`archive-answer-banner`,
  `archive-discussion 4`, …);
- one row per category entry.

The column count differs by file (34–54). The scraper keeps a different set
of numbered slots each time.

| File | Rows | Episodes | Air dates | Columns |
| --- | ---: | ---: | --- | ---: |
| `(5)` | 1,385 | 100 | 2017-08-07 … 2020-01-24 | 51 |
| `(4)` | 228 | 16 | 2020-01-24 … 2020-04-16 | 50 |
| `(3)` | 1,356 | 84 | 2020-04-16 … 2021-08-09 | 54 |
| `(2)` | 3,084 | 118 | 2021-08-09 … 2023-10-31 | 41 |
| `(1)` | 5,184 | 159 | 2023-10-31 … 2026-10-06 | 34 |
| **All** | **11,237** | **473** | | |

Entries per episode run from 2 to 49, with a median of 18. The early years
are thinner:

| Year | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
| --- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |
| Episodes | 20 | 32 | 45 | 66 | 53 | 54 | 53 | 57 | 51 | 42 |

### Clean fields (present in every file, 97–100% filled)

| Field | Source column | Note |
| --- | --- | --- |
| Discussion slug | `archive-answer-banner href`, or `poster href` in files 3–5 | The two columns are equal wherever both exist |
| Episode slug | `?episode=` in `archive-answer-identity href` | One air date per episode, no conflicts |
| Air date | `archive-answer-date 2` | `October 6, 2026` format; parses 100% |
| Category slug | derived from the discussion slug | 165 distinct |
| Category family | `archive-icon src` | 22 icons: 19 standing categories with one banner each, plus `flex-bicep-web` (123 one-off awards), `segments` (21: Picking Nits, Half-Assed Internet Research, …) and `most-year` (43 "The most 19xx thing" banners) |
| Banner as aired | `archive-answer-banner` | Free text, 196 distinct |
| Answer | `archive-answer` | 81–89% filled. The blanks are categories that have no single answer: Best Double Feature 118, Roger Ebert's review 100, Who Won the Movie? 81, … |
| Bullet count | `archive-discussion 2`, e.g. `(4)` | The page's own count of bullets |
| Transcript time | `archive-transcript-time` | 100% match `Approx. transcript time · hh:mm:ss` |
| Transcript link | `archive-transcript-reference href` | podscripts.co 8,954 · megaphone mp3 1,133 · pod.wave.co 1,081 · YouTube 69 |

### Lossy fields: the discussion

On the page, a discussion is a `<ul>` of bullets. Each bullet is a sentence
with `<a class="archive-person-mention">` links inline and an optional
`<span class="archive-speaker">`. The scraper flattened that into numbered
columns, and three things broke:

1. **Names were cut out of the sentences.** In *The Texas Chain Saw Massacre*,
   `John Dugan` moved to its own column. The text left behind reads `After
   getting the grandfather's old-age makeup,  would not repeat…`, and the next
   bullet starts with `, who played the hitchhiker…`. 18–42% of text cells
   show a gap like this, rising in the older files. Which name goes in which
   gap is not recoverable: the mention slots are numbered by position in the
   DOM, not by bullet.
2. **Slots were dropped, sometimes from the middle.** File 1 keeps mention
   slots 1, 2 and 4 and has no slot 3. File 4 keeps 1, 2, 3, 4, 7 and 9.
   Whatever was in the missing slots is gone.
3. **Long discussions were cut short.** Each file keeps only 5–9 discussion
   columns, but the page count runs up to 53. About 17% of rows (1,918) have
   fewer bullets than their count. In 0.1–6% of rows, depending on the file,
   the reverse is true: more bullets than the count. That suggests columns
   have also shifted.

Speakers have the same slot problem. The `—` column is a separator; the
name is in the column after it.

## Joining to the episode list

There are no shared IDs, so episodes join on air date plus title, checked
against `episodes.csv`.

| Rule | Episodes | Note |
| --- | ---: | --- |
| Exact date, title agrees | 315 | |
| Exact date, title alias | 3 | *Beverly Hills Cop II*/*2*, *Ocean's Eleven*/*11*, *Ocean's Twelve*/*12* |
| Date −2 … +1 days, title agrees | 148 | Of these, 144 are −1 (the list's date minus rewatchvault's): rewatchvault runs a day **later**. *Corrected in report 024; this first said "earlier", misreading the sign.* Mostly 2019 (29) and 2024–26 (103). This looks like a time-zone or feed-date convention, not an error |
| Placeholder date | 5 | *Heat*, *Jerry Maguire*, *Blue Chips*, *Any Given Sunday*, *White Men Can't Jump* are all dated 2017-08-07, which looks like the feed relaunch. The episode list has their original 2015–17 dates. These need a title-only match |
| **Real conflict** | **2** | ***Dunkirk***: rewatchvault 2019-12-30, the list 2019-12-20. ***Fast Five***: rewatchvault 2019-04-01, the list 2019-05-31. One source is wrong in each case |
| Ambiguous (more than one candidate) | 0 | |

No join falls back on title alone: report 012 showed how that breaks with
*Heat* and *Crash*. The year in the rewatchvault film slug
(`the-texas-chain-saw-massacre-1974`) can serve as a second check against
`curated_movies.year`.

**Episodes on the list but not on rewatchvault: 25.**
- 8 aren't films: mailbags, the categories selection show, the Top 50, the
  *Miami Vice* two-parter.
- *Friday the 13th* aired today.
- 4 are absent from the site entirely: *Office Space*, *The Matrix*,
  *Election* and *Never Been Kissed*, all 1999-month episodes from 2019.
- The rest are films the site has but the scrape missed, such as *Moneyball*
  and *Contagion*. These are part of the 293.

## Proposal 1 — Clean and consolidate

Two parts.

**A. The workbooks, kept exactly as they are.** They stay in `data/raw/`,
which is already git-ignored. A loader reads all five sheets and stores each
row verbatim as JSON, keyed by discussion slug, with a hash of its contents.
That keeps the workbooks as an auditable record of what was collected on
2026-10-12, and as a fallback.

**B. The site, read once.** Every discussion slug in the sitemap is fetched
once: 11,530 pages, including the 293 the scrape missed. The fetch:
- runs at 1 request a second, about 3¼ hours in one background job;
- sends a named user agent;
- resumes where it stopped.

The `<article>` fragment of each page goes to the raw zone. It's about 3–5
KB, and compressed it should come to roughly 10–15 MB in total. Everything is
then parsed out of the stored HTML, never out of the scraper's columns:

- the bullets, in order, with names restored to the sentences;
- for each mention: the person slug, display name and character offsets
  within its bullet;
- the speaker for each bullet;
- the answer, the category slug and banner, the transcript time (stored as
  seconds) and the transcript URL.

**Cleaning rules**, each covered by a test:
- normalise the text to NFC;
- straighten smart quotes only in matching keys, never in the stored text;
- trim whitespace;
- store the answer as null when it is empty, never as `''`.

**Cross-check:** the parsed page has to agree with the workbook row on
episode, category, answer and transcript time wherever the row has them.
Anything that disagrees goes in a review CSV; nothing is fixed silently.

**Category taxonomy:** keyed by the site's category slug. Each category also
gets:
- a family taken from the icon: `standing`, `one_off`, `segment` or
  `most_year`;
- a display name: the most common banner;
- its first and last air dates.

Banners stay on each entry as aired, so *The most 1999 thing* stays
distinguishable from *The most 1985 thing*. This is a starting taxonomy you
can edit, in the same way as the theme taxonomy. It is not a fixed list.

## Proposal 2 — Archive in SQLite

This extends `rewatchables.db` and the existing raw → staging → curated zones.
It does not create a second database. The tables:

```
raw_category_loads        load_id PK, source ('xlsx'|'web'), source_ref, loaded_at,
                          rows_ingested, load_status
raw_category_rows         raw_id PK, load_id FK, discussion_slug, payload (xlsx row JSON
                          or zlib'd article HTML), http_status, source_hash,
                          last_seen_load_id, last_seen_at, UNIQUE(load_id, source_hash)

category_episode_map      rv_episode_slug PK, staging_episode_id FK, match_rule
                          ('exact'|'date_window'|'alias'|'title_only'|'manual'), day_offset
                          -- manual rows seeded from a tracked CSV for the 7 exceptions

curated_categories        category_slug PK, family, display_name, first_aired, last_aired
curated_category_entries  discussion_slug PK, episode_movie_id FK, category_slug FK,
                          banner, answer, transcript_seconds, transcript_url,
                          bullet_count, raw_id FK
curated_category_bullets  (discussion_slug, position) PK, text, speaker_slug
curated_category_mentions (discussion_slug, position, char_start) PK, person_slug,
                          person_name, tmdb_person_id NULL
```

Notes:
- **Loads get their own ledger table** (`raw_category_loads`), as the upcoming
  films and CMU loads already do, so the `raw_episodes_current` pin can't be
  disturbed (`raw_zone.sql`, line 282).
- **Same upsert pattern as `raw_episodes`:** a business key, a `source_hash`
  and `last_seen_*` fields. Re-running against unchanged pages inserts
  nothing, and an edited page is stored as a new version.
- **`tmdb_person_id` starts empty.** rewatchvault person slugs are opaque
  hashes (`film-person:c359d8a0…`). Linking them to `curated_people` takes a
  name match with a review queue. The workbooks hold 2,504 distinct
  `film-person` slugs, a lower bound because of the dropped slots. That's a
  later step and not part of this proposal.
- **This is pipeline stage `categories`** (`s16_categories`), run through
  `orchestrate.py --stages categories`. It does not feed the public site yet.
  Whether it should is decision 2 below.

**Checks:**
- after the backfill, entries = 11,530;
- every entry maps to an episode;
- every category slug is in `curated_categories`;
- `bullet_count` equals the number of stored bullets for 100% of entries;
- no restored bullet contains a double space or starts with a comma.

## Proposal 3 — Future episodes (to work out together)

**Recommended: a sitemap diff.** The site lists every discussion page in one
sitemap. The 2.3 MB file has no `lastmod`, but slugs never change. The
weekly run:
1. fetches the sitemap;
2. selects slugs not in `raw_category_rows`;
3. fetches and parses only those;
4. re-fetches the last 3 episodes' pages, to pick up late corrections.

A normal week is one episode, about 20–50 requests. The run either sits in
`orchestrate.py` or runs on a schedule.

Two things decide whether this is good enough:
- **Latency.** *Friday the 13th* aired today and isn't on the site yet.
  Watching how many days it takes to appear tells us how far behind a release
  this method runs.
- **Dependence on an independent site.** If rewatchvault stops updating or
  changes its markup, this stops. The parser should fail loudly, not quietly
  load nothing: a fetched page with no `archive-discussion` block is an error.

**Alternatives:**
- **Extract the categories from the transcripts ourselves.** podscripts.co
  publishes transcripts. Turning a transcript into category entries is an
  LLM job, and the current rule is no paid API spend on extraction (see the
  theme-extraction decision). It stays parked until that rule changes.
- **Enter the standing categories by hand** as new columns in
  `episodes.xlsx`: Apex Mountain, Who Won the Movie?, and so on. This doesn't
  depend on anyone else, but it covers only answers, with no discussion, and
  it's ongoing manual work. It's the fallback if rewatchvault goes away.

## Batch plan (added after review: re-read the site, in batches)

**Decision:** re-read the site in batches. Proposed: **8 batches**, a pilot
plus seven grouped by air year.

Each batch is designed to:
- take 30 minutes or less at 1 request a second;
- run as one `raw_category_loads` row, so a batch is one load you can audit or
  roll back;
- resume where it stopped;
- skip any page already stored.

Pages per year come from the workbooks plus the sitemap. 289 of the 293
missing pages match a known episode slug. The other 4 have slugs that match
no known episode (`c54-…`, `c56-…`, `c57-…`, `c8-…`) and go in the last batch.

| Batch | Air years | Episodes | Pages | Missing from workbooks | Time at 1/s |
| --- | --- | ---: | ---: | ---: | ---: |
| **0 — pilot** | 1 episode per year, 2017–2026 | 10 | about 240 | — | about 4 min |
| 1 | 2017–2019 | 97 | 1,365 | 19 | 23 min |
| 2 | 2020–2021 | 119 | 1,958 | 49 | 33 min |
| 3 | 2022 | 54 | 1,406 | 24 | 23 min |
| 4 | 2023 | 53 | 1,684 | 50 | 28 min |
| 5 | 2024 | 57 | 1,851 | 43 | 31 min |
| 6 | 2025 | 51 | 1,744 | 36 | 29 min |
| 7 | 2026, plus the 4 unmatched pages | 42+ | 1,522 | 72 | 25 min |
| **Total** | | **473+** | **11,530** | **293** | **about 3¼ h** |

**Why a pilot first.** Ten episodes, one from each year, cover every
transcript host (podscripts.co, megaphone, wave, YouTube) and both poster
sources. That surfaces any change in the page markup over the years before
11,000 pages depend on the parser. The pilot also measures real page size,
response times and whether the site slows us down. The pilot's pages count
toward their own years and aren't fetched again.

**Why by air year, not by workbook file.** The files split boundary episodes
between them, and range from 228 to 5,184 rows. Years keep every episode
whole and every batch under about 30 minutes.

**The check between batches.** Each batch ends with a summary:
- pages fetched;
- HTTP errors;
- pages with no `archive-discussion` block;
- bullet count against the page's own `(N)`;
- disagreements with the workbook.

The next batch runs only after you've looked at it. The pilot must show 100%
of bullet counts matching and no text with a gap where a name was cut out.

**Cadence.** This is your call. Back to back, it's one afternoon. One or two
batches a day spreads the load on the site over a week.

## On publishing rewatchvault text

The site states no terms of use or licence. `/terms`, `/terms-of-use` and
`/about` all return 404. `/resources` has guides only, with no reuse
statement. No stated licence means the default: the writing is theirs.

Facts are fine to publish with a link: the category, who won it, the answer,
and the minute. For the discussion prose, **I'd ask first.** The site gives a
contact address, `hello@rewatchvault.com`. Until you've heard back, the site
export would carry facts and a link to each discussion only.

Two consequences for the build:
- every entry keeps its source URL, so attribution can be added anywhere;
- step 15 adds text to `site.sql` only through an explicit list of allowed
  fields, so prose can't reach the public site by accident.

## Your decisions

1. ~~Re-read the site, or clean the workbooks only?~~ **Decided:** re-read it,
   in batches. See the batch plan.
2. **What, if anything, goes on the public site?** rewatchvault's discussion
   text is their writing. My suggestion is to keep it in the local archive
   only, and publish the facts with a link back to the discussion page: who
   won which category, with what answer, at what minute. It's your site and
   your call.
3. **The two date conflicts.** Which is right, the list or rewatchvault, for
   *Dunkirk* (2019-12-20 vs 2019-12-30) and *Fast Five* (2019-05-31 vs
   2019-04-01)? If the list is wrong, the fix goes in `episodes.xlsx`.

## Reproduce

The profile scripts were one-offs in the session scratchpad. Four requests
went to rewatchvault.com for this report: `robots.txt`, `sitemap.xml` and two
discussion pages. The numbers above can be rebuilt from the
workbooks and the sitemap. If the proposal goes ahead, the profiling becomes
`tests/test_categories_profile.py`.
