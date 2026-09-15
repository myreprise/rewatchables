| Source                        | What you get                                                   |       Incident granularity |              Free? | My rating |
| ----------------------------- | -------------------------------------------------------------- | -------------------------: | -----------------: | --------: |
| **TMDb API**                  | Movie metadata + thousands of keywords                         |                Movie-level | Yes, noncommercial |     ★★★★★ |
| **Wikipedia / MediaWiki API** | Detailed plot summaries                                        | Plot-event level after NLP |                Yes |     ★★★★★ |
| **OpenSubtitles API**         | Timestamped dialogue                                           |      Scene-level after NLP |       Limited free |     ★★★★☆ |
| **OMDb API**                  | Plot + basic metadata                                          |           Movie-level text |          1,000/day |     ★★★☆☆ |
| **Wikidata SPARQL**           | Structured narrative metadata                                  |         Mostly movie-level |                Yes |     ★★☆☆☆ |
| **MovieGraphs dataset**       | Interactions, relationships, emotions, motivations, timestamps |            **Scene-level** |      Research/free |     ★★★★★ |
| **MovieNet dataset**          | Scripts, subtitles, scenes, action/place annotations           |            **Scene-level** |      Research/free |     ★★★★☆ |
| **CMU Movie Summary Corpus**  | 42,306 detailed plots                                          | Plot-event level after NLP |       Free dataset |     ★★★★☆ |

## Project source files

The table above is the menu of external sources. These two are the project's own
inputs — both hand-curated, both converted from xlsx to CSV so that a change to
either is a reviewable one-line diff rather than `Bin 71028 -> 76009 bytes`.

| Source of truth | Edited how | Derived CSV | Rows | Loaded by |
| --- | --- | --- | ---: | --- |
| Google Sheet | in the sheet | `data/episodes.csv` | 489 | `02_load_raw.py` (after `01_sync_sheets.py`) |
| `data/remaining films.xlsx` | in Excel | `data/upcoming.csv` | 214 | `13_build_upcoming.py` |

**Edit the source, never the CSV.** In both rows the CSV is a rendering, not a
copy: the pipeline rewrites it from the source at the start of every run, so an
edit made to the CSV is discarded silently. The CSVs are nonetheless tracked in
git, and that is the point of them — an xlsx diffs as `Bin 71028 -> 76009 bytes`
and cannot be merged, while the CSV beside it turns "one film was added" into a
one-line diff. The xlsx should be committed too, so the thing you actually edit
is not the one thing that only exists on one machine.

Step 13 refuses to fall back to the CSV when the xlsx is present but unreadable
— which on Windows means Excel is holding it open. Falling back there would
quietly build the previous version of the list while your edits are on screen.
Close the file and run it again.

The two do not mix. `upcoming.csv` rows are not airings — no episode number, no
date — so they get their own raw and curated tables and their own load ledger
(`raw_upcoming_loads`, never `raw_ingest_runs`; see the comment block in
`sql/schemas/raw_zone.sql` for why that separation is load-bearing).

**Where they overlap.** A film can be on both: a request that later becomes an
episode. Step 13 matches the two on **`tmdb_id`**, never on title, and marks the
request superseded so it leaves the app's upcoming list. Title matching is not a
shortcut here — against the current data it finds seven pairs and is wrong about
four of them (a 1996 *Crash* against a 2005 one, a 1987 *Heat* against a 1995
one, and *Miami Vice* the 1980s series and the 2027 film against the 2006 one).

## Actor gender

`curated_people` carries one row per credited person with the gender TMDB
records for them. It comes out of the `credits` sub-object of the movie detail
call `09_enrich_metadata.py` already makes, so it costs no extra request; TMDB's
integer enum maps `0 -> unknown`, `1 -> F`, `2 -> M`, `3 -> NB`.

Coverage on the current catalogue, over the 4,539 billed credits across 454
films:

| Gender | People | Credits | Share of credits |
| --- | ---: | ---: | ---: |
| M | 1,949 | 3,207 | 70.7% |
| F | 930 | 1,269 | 28.0% |
| NB | 4 | 4 | 0.1% |
| not recorded | 59 | 59 | 1.3% |

**`unknown` is stored, never guessed.** TMDB leaves gender unset on about 1% of
billed credits; assigning those to either side would overstate that side, so
they are their own category and are excluded from the Actors section's paired
leaderboards rather than folded into one.

`raw_cmu_characters.actor_gender` is the same fact from the CMU corpus and is
kept only as a cross-check. It covers 78% of these actors (85% credit-weighted)
against TMDB's 98.7%, and the gap is concentrated in recent films because the
Freebase snapshot behind CMU froze around 2012. The two are substantially
consistent where both know a person: across the 2,291 actors they share they
disagree on 2 (0.09%) -- `Harley Jane Kozak` and `Kazuyoshi Minamimagoe`, CMU
recording `M` against TMDB's `F` in both cases.

A CMU backfill is therefore worth little here and has not been run: it would
resolve 12 of the 59 credits TMDB leaves unset, leaving 47. If one is ever run,
`curated_people.gender_source` records which source a row is carrying, and a
`manual` row is never overwritten by a later TMDB refetch.

**Names are not keys.** `curated_movies.cast_ids` carries the TMDB person id for
each billed credit, positionally parallel to `cast_names`. The app still groups
actor statistics by name — one bar is one name — and where two people share a
name and TMDB disagrees on their gender, the app resolves that name to
`unknown` rather than picking a row. On the current catalogue no name is shared
by two person ids, so nothing is currently lost to this; `cast_ids` is what a
person-grained version of those panels would use.

## Plot summaries

`curated_movies.plot_summary_wiki` is the film's Wikipedia plot section, taken
from whichever of two vintages is longer for that film. Step 12 fetches the
live one and makes the choice. `plot_summary_wiki_source` records which won,
and `wikipedia_revid` records the exact revision read.

| Source | Stored in | Films | Words p10 / median / p90 |
| --- | --- | ---: | ---: |
| CMU corpus: Nov 2012 dump, markup cleaned | `raw_cmu_summaries` | 402 | 392 / 676 / 1,017 |
| Live Wikipedia: TextExtracts, read 2026-09-15 | `raw_wiki_articles` | 456 | 490 / 643 / 746 |
| **Chosen: the longer of the two** | `curated_movies.plot_summary_wiki` | **456** | **549 / 703 / 990** |
| TMDB overview, a logline | `curated_movies.plot_summary` | 456 | 23 / 46 / 74 |

**Why not simply use the live text.** It isn't a strict upgrade. Editors have
rewritten many thin 2012 plots and trimmed many overlong ones toward the
~700-word guideline. Across the 402 films that have both:

| Live plot compared with CMU | Films | Kept |
| --- | ---: | --- |
| 1.5× longer or more (*Hardball*: 70 → 689 words) | 34 | live |
| 10–50% longer | 78 | live |
| within 10% | 117 | live 53, CMU 64 |
| 10–33% shorter | 114 | CMU |
| a third shorter or more (*Eyes Wide Shut*: 1,724 → 616) | 59 | CMU |

The live text also covers the 54 films CMU never had: all 37 released after
2012, plus 17 older ones (*Aliens*, *Apollo 13*, *Pretty Woman*). The ratios
above use word counts before CMU cleaning, so a few near-ties sit on the other
side of the line from the rule that chose them.

**What is still thin.**
- Four films are under 300 words:
  - *Kicking and Screaming* (1995), 24 words. The article has only a one-line
    "Premise", and CMU has no summary.
  - *Singles*, 119 words.
  - *Someone to Watch Over Me*, 277 words.
  - *Vision Quest*, 292 words.
- *American Gangster* keeps its longer CMU plot, and with it an unclosed
  citation step 12 can't safely cut (see the step 12 docstring).
- The rule is strictly "longer wins", so 64 films keep 2012 text over a current
  plot within 10% of its length. A tie band would be a one-line change in
  `choose_plot`.

**Themes and analysis sections.** 91 films (median 464 words) have one:
"Themes", "Analysis", "Thematic analysis" and similar headings. The text is
stored in `themes_wiki`, apart from the plot, because it is critics'
interpretation rather than events in the film. Box-office sections that happen
to match ("Commercial analysis", "Box office analysis") are excluded. Coverage
leans toward well-studied films, so this text isn't a neutral basis for comparing
films across the catalogue.

**Refreshing.** Only the plot and themes sections are stored, not whole
articles, so a change to the section parser needs a re-fetch:

    python scripts/12_enrich_plot_summaries.py --refresh

That is 456 requests, about three minutes, and free. It also moves every film to
its current revision. A plain run fetches only films new to the catalogue.
