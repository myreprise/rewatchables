# CMU Movie Summary Corpus — vendored subset

A subset of the CMU Movie Summary Corpus, filtered to the films in
`curated_movies`. **This is not the full corpus.**

## Source

- URL: http://www.cs.cmu.edu/~ark/personas/data/MovieSummaries.tar.gz
- Full tarball SHA-256: `6c3bd3d42046c4b87e2267f2e2599ba6f651b8ad23a8998237c3d2bb338ac559`
- Plot summaries: November 2, 2012 dump of English-language Wikipedia
- Metadata: November 4, 2012 dump of Freebase
- Full corpus: 42,306 summaries / 81,741 films / 450,669 characters

## This subset

Extracted 2026-09-01 by `scripts/vendor_cmu_subset.py`, matching on
`freebase_id` (primary) or `wikipedia_page_id` (fallback) from `curated_movies`.

| file | rows |
|---|---|
| `movies.tsv` | 413 |
| `plot_summaries.tsv` | 402 |
| `characters.tsv` | 6496 |

Text is verbatim from the source, including Wikipedia markup residue
(`{{templates}}`, `[[wikilinks]]`, HTML entities). Clean downstream.

Column names are added as a header row; the source files have none. Column
order and values are otherwise unchanged.

## License

All data is released under a Creative Commons Attribution-ShareAlike License
(CC BY-SA): <http://creativecommons.org/licenses/by-sa/3.0/us/legalcode>

**Share-alike applies to derived work you distribute.**

## Citation

David Bamman, Brendan O'Connor and Noah A. Smith, "Learning Latent Personas of
Film Characters," Proceedings of the Annual Meeting of the Association for
Computational Linguistics (ACL 2013), Sofia, Bulgaria, August 2013.
