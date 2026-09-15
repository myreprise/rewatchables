#!/usr/bin/env python3
"""
Vendor the slice of the CMU Movie Summary Corpus that covers our films.

The full corpus is a 46 MB tarball (130 MB extracted) describing 81,741 films.
Only the ~413 that appear in curated_movies are of any use here, so rather than
committing the whole thing we extract the matching rows -- a couple of MB that
fits comfortably in git and needs no special handling.

Rows are matched on `freebase_id` (CMU's primary key; immutable since Freebase
froze in 2016), falling back to `wikipedia_page_id`. Both come from
curated_movies and are populated by 10_resolve_external_ids.py, which must run
first.

Source text is copied VERBATIM -- Wikipedia markup residue ({{templates}},
[[wikilinks]], HTML entities) is left intact so the vendored files stay a
faithful subset. Cleaning belongs downstream, where it can be changed without
re-vendoring.

Usage:
    python scripts/vendor_cmu_subset.py --source path/to/MovieSummaries
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import sqlite3
import sys
from datetime import date
from pathlib import Path

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

DEFAULT_OUT = Path("data/external/cmu")

SOURCE_URL = "http://www.cs.cmu.edu/~ark/personas/data/MovieSummaries.tar.gz"
TARBALL_SHA256 = "6c3bd3d42046c4b87e2267f2e2599ba6f651b8ad23a8998237c3d2bb338ac559"

MOVIE_COLS = ["wikipedia_page_id", "freebase_id", "name", "release_date",
              "box_office_revenue", "runtime", "languages", "countries", "genres"]
CHAR_COLS = ["wikipedia_page_id", "freebase_id", "release_date", "character_name",
             "actor_dob", "actor_gender", "actor_height_m", "actor_ethnicity_fbid",
             "actor_name", "actor_age_at_release", "fb_character_actor_map_id",
             "fb_character_id", "fb_actor_id"]


def load_bridge(db_path):
    """Return the freebase ids and page ids of our curated films."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT tmdb_id, title, year, freebase_id, wikipedia_page_id "
        "FROM curated_movies").fetchall()
    conn.close()
    fb = {r[3] for r in rows if r[3]}
    pid = {str(r[4]) for r in rows if r[4]}
    logger.info(f"Bridge: {len(rows)} curated films — {len(fb)} freebase ids, "
                f"{len(pid)} page ids")
    if not fb and not pid:
        logger.error("No external ids on curated_movies. "
                     "Run 10_resolve_external_ids.py first.")
        sys.exit(1)
    return rows, fb, pid


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def vendor(source, out_dir, db_path):
    source, out_dir = Path(source), Path(out_dir)
    for required in ["movie.metadata.tsv", "plot_summaries.txt",
                     "character.metadata.tsv"]:
        if not (source / required).exists():
            logger.error(f"{source / required} not found")
            sys.exit(1)

    rows, fb_ids, page_ids = load_bridge(db_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- movies ------------------------------------------------------------
    kept_movies, kept_pids = [], set()
    with open(source / "movie.metadata.tsv", encoding="utf-8") as f:
        for r in csv.reader(f, delimiter="\t"):
            if len(r) >= 9 and (r[1] in fb_ids or r[0] in page_ids):
                kept_movies.append(r[:9])
                kept_pids.add(r[0])
    with open(out_dir / "movies.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(MOVIE_COLS)
        w.writerows(kept_movies)
    logger.info(f"movies.tsv          : {len(kept_movies)} rows")

    # --- plot summaries ----------------------------------------------------
    # One summary per line in the source; keep that shape so the text needs no
    # quoting, and drop any stray tab/newline defensively.
    kept_summaries = 0
    with open(source / "plot_summaries.txt", encoding="utf-8") as fin, \
         open(out_dir / "plot_summaries.tsv", "w", encoding="utf-8",
              newline="") as fout:
        fout.write("wikipedia_page_id\tsummary\n")
        for line in fin:
            pid, _, text = line.partition("\t")
            if pid in kept_pids:
                clean = text.strip().replace("\t", " ").replace("\n", " ")
                fout.write(f"{pid}\t{clean}\n")
                kept_summaries += 1
    logger.info(f"plot_summaries.tsv  : {kept_summaries} rows")

    # --- characters --------------------------------------------------------
    kept_chars = 0
    with open(source / "character.metadata.tsv", encoding="utf-8") as fin, \
         open(out_dir / "characters.tsv", "w", encoding="utf-8", newline="") as fout:
        w = csv.writer(fout, delimiter="\t", lineterminator="\n")
        w.writerow(CHAR_COLS)
        for r in csv.reader(fin, delimiter="\t"):
            if len(r) >= 13 and (r[1] in fb_ids or r[0] in page_ids):
                w.writerow(r[:13])
                kept_chars += 1
    logger.info(f"characters.tsv      : {kept_chars} rows")

    # --- provenance --------------------------------------------------------
    # CC BY-SA requires attribution; record it next to the data rather than
    # relying on anyone remembering where these files came from.
    (out_dir / "PROVENANCE.md").write_text(f"""# CMU Movie Summary Corpus — vendored subset

A subset of the CMU Movie Summary Corpus, filtered to the films in
`curated_movies`. **This is not the full corpus.**

## Source

- URL: {SOURCE_URL}
- Full tarball SHA-256: `{TARBALL_SHA256}`
- Plot summaries: November 2, 2012 dump of English-language Wikipedia
- Metadata: November 4, 2012 dump of Freebase
- Full corpus: 42,306 summaries / 81,741 films / 450,669 characters

## This subset

Extracted {date.today().isoformat()} by `scripts/vendor_cmu_subset.py`, matching on
`freebase_id` (primary) or `wikipedia_page_id` (fallback) from `curated_movies`.

| file | rows |
|---|---|
| `movies.tsv` | {len(kept_movies)} |
| `plot_summaries.tsv` | {kept_summaries} |
| `characters.tsv` | {kept_chars} |

Text is verbatim from the source, including Wikipedia markup residue
(`{{{{templates}}}}`, `[[wikilinks]]`, HTML entities). Clean downstream.

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
""", encoding="utf-8")

    # --- manifest ----------------------------------------------------------
    manifest = {
        "source_url": SOURCE_URL,
        "tarball_sha256": TARBALL_SHA256,
        "extracted_on": date.today().isoformat(),
        "curated_films": len(rows),
        "files": {},
    }
    for name in ["movies.tsv", "plot_summaries.tsv", "characters.tsv"]:
        p = out_dir / name
        manifest["files"][name] = {"bytes": p.stat().st_size,
                                   "sha256": _sha256(p)}
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    total = sum(v["bytes"] for v in manifest["files"].values())
    logger.info(f"✓ Vendored to {out_dir} ({total/1e6:.2f} MB)")
    return len(kept_movies), kept_summaries, kept_chars


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True,
                    help="path to the extracted MovieSummaries directory")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--db", default=os.getenv("DB_PATH", "rewatchables.db"))
    args = ap.parse_args()

    if not Path(args.db).exists():
        logger.error(f"{args.db} not found.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Vendor CMU Movie Summary Corpus subset")
    logger.info("=" * 60)
    vendor(args.source, args.out, args.db)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
