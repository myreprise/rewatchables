# 001 — Plot summary coverage, and a plan for LLM theme extraction

Date: 2026-09-15. Read-only profiling; no pipeline code or database rows changed.

## Current coverage (`curated_movies`, 456 films)

| Source | Column | Films | Share | Median words |
| --- | --- | ---: | ---: | ---: |
| TMDB overview | `plot_summary` | 456 | 100% | 46 (p10 23, p90 74) |
| CMU corpus (Wikipedia, Nov 2012 dump) | `plot_summary_wiki` | 402 | 88.2% | 676 (p10 392, p90 1,017) |

The TMDB overview is a logline, not a plot. At 46 words it is too thin for
extracting themes or events, so **the working corpus today is the 402 CMU plots.**

### The 54-film gap

| Cause | Films |
| --- | ---: |
| Released 2013+ (CMU froze in 2012, so this is structural) | 37 |
| Pre-2013, CMU has the film's metadata but no summary (e.g. *Pretty Woman*, *Skyfall*, *Jeremiah Johnson*) | 7 |
| Pre-2013, not in the vendored CMU metadata at all (e.g. *Aliens*, *Apollo 13*, *Ali*, *Hitch*) | 10 |

The 10 in the last group cannot be diagnosed further without the full CMU
tarball (only the matched subset is vendored). Either Wikidata's freebase_id for
them differs from CMU's, or CMU never had them. Live Wikipedia (below) makes the
question moot.

### Quality of the 402 CMU plots

- 12 are under 200 words and 41 are under 400 (*Hardball* 70, *Purple Rain* 76,
  *Night Shift* 89, *He Got Game* 96).
- Markup residue after `12_enrich_plot_summaries.py`: none for `{{`, `[[`,
  `<ref` or entities. 3 films still contain a URL, and 5 carry inline citation
  text (already flagged by step 12).

## Live Wikipedia, measured across all 456 films

This was fetched once via TextExtracts using `curated_movies.wikipedia_page_id`
(present on all 456). The per-film results are in the session scratchpad only;
nothing was persisted.

| Measure | Result |
| --- | ---: |
| Live article has a Plot/Synopsis section | 455 / 456 (the exception is *The Godfather Part II*, whose section heading didn't match; CMU covers it) |
| CMU gap filled by live | **54 / 54** |
| Films with a plot from CMU or live | **456 / 456** |
| Live plot words | median 642 (p10 490, p90 746) |
| Films with both sources: median live/CMU length ratio | 0.95 |
| Live ≥ 1.5× CMU | 34 films (32 of these are among the 41 CMU plots under 400 words) |
| Live ≤ 0.67× CMU | 60 films (e.g. *Eyes Wide Shut* 1,724 → 616; *Bloodsport* 504 → 218) |
| Films under 300 words: CMU today vs. best-of-both | 76 → **4** |

**Interpretation.** Live Wikipedia is not a strict upgrade. Editors have since
cut many overlong plots down to the 400–700-word WP:FILMPLOT norm, so for 60
films the 2012 text is substantially more detailed. The right policy is to
keep both sources and choose per film, not to replace one with the other.

**Themes/Analysis sections** (critics' interpretation rather than plot): about 76
of 456 films (78 heading matches, 2 of them "Theme park attraction" false
positives). Median 312 words. Useful as a separate, provenance-tagged input for
well-studied films; too sparse to be a primary source.

## TMDB keywords as a similarity baseline

3,658 distinct keywords over 456 films. 2,406 (66%) are used by only one film,
and only 331 are used by five or more. The top of the list mixes places and
source material with mood tags (`amused`, `intense`, `duringcreditsstinger`).
This is the existing "connections" signal, and it is the baseline any LLM
approach has to beat.

## Proposal summary (details in session notes)

1. **Summaries:** add a live-Wikipedia raw table pinned by `revid`, and pick a
   "best" plot per film (longer of CMU/live, with a large-shrink flag for review).
   Keep CMU verbatim. Optionally store Themes/Analysis sections separately.
2. **Extraction:** use structured-output extraction against a controlled,
   hand-reviewed taxonomy (discover → consolidate → tag). Every tag carries
   salience and a verbatim evidence quote. Film–film similarity is
   IDF-weighted shared tags, which keeps it explainable. Embeddings are a
   complement, not the core.
3. **Evaluation before building UI:** evidence-quote grounding rate, a
   hand-tagged gold set of about 25 films, run-to-run stability, and a blind
   "similar films" comparison against TMDB keywords, genre overlap and plot
   embeddings. If the LLM tags don't beat TMDB keywords, that result gets
   reported as such.

**Estimated one-time cost** for the extraction pass (Opus 5, $5/$25 per MTok):
about 1.9M input and 1.1M output tokens, roughly $38 standard or $19 via the
Batch API. A discovery pass plus taxonomy consolidation adds under $10. These
are estimates from assumed token counts; a 20-film pilot should measure the real
figures first.

## Open decisions

- Best-of-both plot selection vs. live-only vs. gap-fill-only.
- Whether critics' Themes/Analysis text is allowed to drive tags, or only
  plot text.
- Taxonomy governance: LLM-proposed and hand-curated (recommended) vs. open tags.
- Model and budget choice for the extraction pass.

*Resolved 2026-09-15; see [002](002_live_wikipedia_plots.md).*
