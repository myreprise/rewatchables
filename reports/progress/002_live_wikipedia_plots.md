# 002 — Plot summaries: live Wikipedia, best of both

Date: 2026-09-15. Follows [001](001_plot_summary_coverage.md).

## Decisions taken on 001's open questions

| Question | Decision | How it was applied |
| --- | --- | --- |
| Plot selection | Keep the better of the two | The longer plot wins; an exact tie goes to live |
| Themes/Analysis text | Keep it separate, with provenance | Stored in `themes_wiki`; never mixed into the plot |
| Theme taxonomy | Curated by the user | Part 2; not started |
| Budget | Spend nothing for now | Part 2 LLM extraction is on hold. Everything here used only the free Wikipedia API |

## What changed

- **Step 12 extended rather than a new step.** Step numbers must stay
  contiguous (`test_orchestrate`), and a fetch step placed before 12 would have
  meant renumbering 12 and 13. Steps 09 and 10 already combine fetch, cache and
  write in one script. Step 12 now:
  1. fetches each film's live article (TextExtracts, one request per film)
     into `raw_wiki_articles`;
  2. cleans the CMU text as before;
  3. writes the longer plot, its source and the revision id, plus any themes
     section.
- **Schema.**
  - New raw-zone table `raw_wiki_articles`. It holds the plot and themes
    sections and the revision id; `06_build_curated` never wipes it.
  - New columns on `curated_movies`: `plot_summary_wiki_source`,
    `wikipedia_revid`, `themes_wiki`, `themes_wiki_heading` and
    `themes_wiki_words`.
- **CMU cleaner**, two additions:
  - bare URLs removed (*Eyes Wide Shut*, *American Gangster*);
  - leading punctuation stripped (*The Godfather Part II* began ": In 1901";
    *Pulp Fiction* began "; Prologue").
- **Parser fixes found on real data.**
  - A plot now includes its subsections. *The Godfather Part II*'s plot is only
    the subsections "Vito" and "Michael", so it had read as empty.
  - Box-office headings no longer count as themes: *Titanic*'s "Commercial
    analysis", *Good Will Hunting*'s "Box office analysis", *Trading Places*'
    "Performance analysis".
- **Database backup** before the schema change:
  `rewatchables.db.pre-wikiplots-20260915_122358.bak`.

## Results

| Measure | Before (001) | After |
| --- | ---: | ---: |
| Films with a Wikipedia plot | 402 / 456 (88.2%) | **456 / 456 (100%)** |
| Under 300 words | 76 | **4** |
| Under 400 words | 95 | **7** |
| Plot words p10 / median / p90 | 392 / 676 / 1,017 (of 402) | 549 / 703 / 990 (of 456) |
| Plot source | CMU 402 | CMU 237, live 219 |
| URL residue in the chosen text | 3 films | 0 |
| Unclosed citation text in the chosen text | 5 films | 1 (*American Gangster*) |
| Themes/analysis section stored | — | 91 films (median 464 words) |

Live vs. CMU across the 402 films that have both:

| Live compared with CMU | Films | Kept |
| --- | ---: | --- |
| ≥ 1.5× longer | 34 | live |
| 1.1–1.5× | 78 | live |
| within 10% | 117 | live 53 / CMU 64 |
| 0.67–0.9× | 114 | CMU |
| < 0.67× | 59 | CMU |

## Verification

- `tests/test_plot_summaries.py`: 63 pass, up from 23. The new tests cover:
  - section parsing (subsections, headings, false-positive themes);
  - the selection rule;
  - API response parsing;
  - the fetch cache: fetched once, `--refresh`, a failed fetch left uncached,
    an outage stopping the fetches, a rebuild refilling with zero network
    calls, and migration of an older database.
- Schema-dependent suites (orchestrate, CMU load, curated build, metadata,
  external ids): 192 pass.
- `tests/test_dossier.py`: `test_films_without_a_wiki_synopsis_exist` asserted
  that some films lack a synopsis, to keep the dossier's hide-when-missing path
  exercised. None do now, so it has been replaced by
  `test_every_wiki_synopsis_records_its_source`: a synopsis is never blank and
  always records its source. Dossier and keyword suites: 97 pass on the final
  database.
- Rendering, checked headlessly through Streamlit's AppTest:
  - *Hardball* (live, 689 words) shows as 8 paragraphs, with its `$` amounts
    still escaped.
  - *Heat* (CMU, 736 words) and *Kicking and Screaming* (live, 24 words) render
    too.
  - No exceptions.

  The browser preview was skipped because port 8501 is held by another app.
- Full suite, run on the final database before the dossier test was replaced:
  622 pass, 5 fail.
  - 1 is the replaced dossier test above, which passes now.
  - 4 are in `tests/test_source_csv.py` and are unrelated to this change.
    `data/episodes.csv` was re-saved at 12:32 today, mid-run, by something
    outside the pipeline:
    - 274 of its 493 lines are now GBK rather than UTF-8;
    - Ebert ratings like `3/4` became `4-3月`;
    - ISO dates became `2016/12/23`.

    That is the signature of Excel on a Chinese-locale machine. The database
    was built from the good file at 11:34 and is unaffected. The file has never
    been committed to git, so git cannot restore it.
- On the real database:
  - The first run fetched 456/456 articles with 0 failures.
  - An immediate re-run fetched 0 and wrote 0.
  - `--refresh` re-fetched 456/456 with 0 failures.

## Findings worth attention

1. **64 near-ties go to the 2012 text.** Strict longer-wins keeps CMU where the
   current plot is within 10% of its length. That's defensible (more words),
   but the current text is cleaner and maintained. A tie band, keeping live
   unless CMU is at least 10% longer, is a one-line change.
2. **Four films stay thin.** *Kicking and Screaming* (1995) has 24 words: its
   article has only a one-line "Premise" and CMU has nothing. *Singles* has 119.
   No free source here can do better. OMDb's "full" plot is typically 100–200
   words.
3. **Themes coverage is skewed.** 91 of 456 films have a themes section, and
   they're the well-studied ones: *The Shawshank Redemption*, *The Shining*,
   *Get Out*. Tags derived from this text would pull similarity toward canonical
   films. That's another reason to keep it as provenance-tagged, secondary
   input.
4. **Design trade-off.** Only the plot and themes sections are stored; whole
   articles would roughly double the 11 MB database. So a parser change
   requires `--refresh`, which also advances every film to its current revision.

## Part 2 (LLM theme extraction): no-cost options

Held on budget. The paths that cost no money:

- **TMDB-keyword baseline.** Similarity weighted toward rarer shared keywords,
  from data already stored. It's needed anyway as the baseline any tagging
  approach must beat. No downloads.
- **Gold-set template.** About 25 films for the user to hand-tag. It seeds the
  curated taxonomy and becomes the evaluation set.
- **Local embeddings** (sentence-transformers). Free and CPU-feasible for 456
  documents, but it needs a new dependency and a one-off model download of
  roughly 100–400 MB.
- **Local LLM** (e.g. via Ollama). Free, but it needs an install and a
  multi-GB model, and extraction quality will be below a frontier model's.
- **Claude in a Claude Code session.** Tagging done in-conversation uses the
  user's plan allowance, not API billing. Whether that counts as spending is
  the user's call.

## Follow-up: `data/episodes.csv` restored

- **The first fix was wrong.** A re-sync from the Google Sheet (step 01) was
  tried first, on my recommendation. Step 01 writes the sheet's own 16 columns
  in the sheet's formats. The pipeline's file has 20 schema columns, and the
  sheet lacks four of them: `rating`, `is_film`, `ebert_stars` and
  `revisited`. Step 02 would have refused the file.
- **The file was rebuilt from `raw_episodes_current` instead.** All 491 rows
  reproduce their stored `source_hash` (an MD5 over the 20 values in header
  order), both straight from the database and after the CSV round trip. So the
  content is identical to what the database was built from at 11:34.
  `tests/test_source_csv.py`: 29 pass.
- Copies of both bad versions, the Excel-garbled file and the sheet download,
  are in the session scratchpad.
- **The sheet and the file have drifted apart.** After normalizing formats
  there are 59 differences, listed in `reports/sheet_vs_episodes_20260915.csv`
  for review. They run both ways:
  - The file corrects the sheet in places: *A Bronx Tale* is 1993, and titles
    are plain film titles rather than "Heat ("The Re-Heat")".
  - The sheet has edits the file lacks: an "Erotic" genre tag on 15 rows,
    "Naughty November" notes, and guests for *Borat* and *The Good Son*.
- **Still open.** `data/episodes.csv` has never been committed to git, although
  `DATA_SOURCES.md` says it is tracked.
