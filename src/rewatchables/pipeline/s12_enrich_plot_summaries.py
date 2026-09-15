#!/usr/bin/env python3
"""
Phase 3: Plot summaries -- the CMU corpus and live Wikipedia, best of both.

Both sources are Wikipedia's plot section, a dozen years apart:

  CMU corpus  raw_cmu_summaries, loaded by 11_load_cmu.py from a Nov 2012
              dump. Carries Wikipedia markup residue, cleaned here.
  live        raw_wiki_articles, fetched here from the MediaWiki TextExtracts
              API as plain text. Covers the films CMU never had -- everything
              released after 2012, plus a handful it simply lacks (Aliens,
              Apollo 13, Pretty Woman).

Neither is a strict upgrade. Across the ~400 films that have both, the live
plot is about the same length at the median, but a few dozen thin 2012 plots
have since been rewritten (Hardball: 70 words -> 689) and about sixty overlong
ones trimmed toward Wikipedia's ~700-word guideline (Eyes Wide Shut: 1,724 ->
616). So the choice is made per film:

  BEST OF BOTH  the longer plot wins -- detail is what the downstream uses
                need. An exact tie goes to live (clean text, current revision).

Columns written to curated_movies:

  plot_summary_wiki          the chosen plot
  plot_summary_wiki_words    its word count
  plot_summary_wiki_source   'cmu_2012' | 'wikipedia_live'
  wikipedia_revid            the live revision read, for plot and themes
  themes_wiki, _heading,     the article's themes/analysis section(s), when it
  themes_wiki_words          has one. Critics' reading, not plot -- kept apart
                             so it never passes for events in the film.

The TMDB `plot_summary` (~46 words) is left untouched.

FETCHING. One TextExtracts request per film (full-article extracts cannot be
batched), written through to raw_wiki_articles. 06_build_curated wipes
curated_movies but never that table, so a rebuild re-derives every column here
from local storage without the network: only a film new to the catalogue is
fetched. --refresh re-fetches them all (~456 requests, a couple of minutes).
A failed request is not cached, so it is retried on the next run; after
MAX_CONSECUTIVE_FAILURES films fail in a row the run stops fetching and
finishes with what it has, rather than spend minutes timing out offline.

Only the plot and themes sections are stored, not the article (which would
roughly double the database). The cost: a change to the section parser takes
--refresh to apply, and that also moves every film to its current revision.

Sections are read from the extract's "== Heading ==" lines. A plot is its
section plus every subsection under it -- The Godfather Part II's plot is two
subsections, "Vito" and "Michael", and no text of its own.

CMU CLEANING is deliberately conservative and fully reversible:
raw_cmu_summaries keeps the verbatim text, so the cleaner can be changed and
re-run at any time. What the corpus actually contains, and how each case is
handled:

  {{Plot}}, {{cite web}}   stray templates            -> removed
  {{'s}}, {{'}}            possessive templates       -> restored to 's / '
                           ("Titanic{{'s}} final moments")
  [[Kevin Gage             UNCLOSED link openers      -> brackets removed,
                           (90 "[[" and zero "]]" in   text kept
                           the corpus, so deleting to
                           a closing "]]" would eat
                           the rest of the sentence)
  &mdash; &nbsp; &ndash;   HTML entities              -> unescaped
  <ref name ... | ...      unclosed citation debris   -> tag token removed;
                           (5 films)                    the citation TEXT has no
                                                        reliable terminator, so it
                                                        stays inline and the films
                                                        are reported for review
                                                        rather than claimed clean
  double spacing           left by upstream link      -> collapsed
                           stripping (86% of films)
  http://...               bare URLs from citations   -> removed
  ": In 1901 ..."          leading punctuation        -> stripped

Idempotent: a re-run rewrites only the films whose chosen values changed.

Usage:
    python scripts/12_enrich_plot_summaries.py [--force] [--refresh]
"""

import argparse
import html
import logging
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

import requests

from rewatchables import config, http

logger = logging.getLogger(__name__)

WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
# WMF asks for a descriptive UA identifying the client -- the same one step 10
# sends.
USER_AGENT = os.getenv(
    "WIKIMEDIA_USER_AGENT",
    "rewatchables-pipeline/0.1 (https://github.com/myreprise/rewatchables)",
)
FETCH_SLEEP = 0.15             # courtesy delay between article requests
RETRY_SLEEP = 2                # backoff base between attempts on one article
FETCH_ATTEMPTS = 3
MAX_CONSECUTIVE_FAILURES = 5   # films failing in a row before we assume offline

SOURCE_CMU = "cmu_2012"
SOURCE_LIVE = "wikipedia_live"

# CMU markup. Order matters; see clean_wiki_markup.
RE_POSSESSIVE_S = re.compile(r"\{\{'s\}\}")
RE_POSSESSIVE = re.compile(r"\{\{'\}\}")
RE_SPACED_DASH = re.compile(r"\{\{\s*spaced\s+n?dash\s*\}\}", re.I)
RE_REF = re.compile(r"</?ref[^>]{0,80}>|</?ref\b", re.I)
RE_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
RE_STRAY_BRACES = re.compile(r"\{\{|\}\}")
RE_LINK_OPEN = re.compile(r"\[\[")
RE_TAG = re.compile(r"</?[a-z][^>]{0,40}>", re.I)
RE_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:!?])")
RE_SPACE_IN_PAREN = re.compile(r"\(\s+|\s+\)")
RE_WS = re.compile(r"\s+")
RE_URL = re.compile(r"https?://\S+")
RE_LEADING_PUNCT = re.compile(r"^[\s:;,.]+")

# Tokens that should not survive cleaning; used for the residue report.
RESIDUE = {"{{": "template", "}}": "template", "[[": "wikilink",
           "]]": "wikilink", "<ref": "ref tag", "&nbsp;": "entity",
           "&mdash;": "entity", "&ndash;": "entity"}

# Live sections, as TextExtracts writes them with exsectionformat=wiki.
RE_HEADING = re.compile(r"^(={2,6})\s*(.+?)\s*\1\s*$", re.M)
RE_PLOT_HEADING = re.compile(
    r"^(plot|plot summary|plot synopsis|synopsis|summary|storyline|story|"
    r"premise)$", re.I)
RE_THEMES_HEADING = re.compile(
    r"\b(themes?|thematic|analysis|interpretations?|symbolism|motifs?|"
    r"allegory)\b", re.I)
# Headings that match but are not about what the film means. "Theme park
# attraction" (two films), "Box office analysis" and "Commercial analysis" are
# real headings in this catalogue; the song/music forms are the same trap on
# the soundtrack side.
RE_NOT_THEMES = re.compile(
    r"\btheme\s+(park|song|music|tune)s?\b"
    r"|\b(commercial|box[ -]office|financial|performance)\s+analysis\b", re.I)


def clean_wiki_markup(text):
    """Strip Wikipedia markup residue from a CMU plot summary.

    Conservative by design: when a construct is ambiguous the text is kept and
    only the markup characters are dropped. Returns '' for empty input.
    """
    if not text:
        return ""

    s = text

    # 1. Possessives FIRST -- a generic template strip would delete these and
    #    silently mangle the word ("Titanic{{'s}}" -> "Titanic").
    s = RE_POSSESSIVE_S.sub("'s", s)
    s = RE_POSSESSIVE.sub("'", s)
    s = RE_SPACED_DASH.sub(" - ", s)

    # 2. Citation debris. Only the <ref> token itself is removed: the corpus
    #    fragments are unclosed and run straight into prose ("...Le Spleen de
    #    Paris], 1864. This is followed by..."), so there is no safe place to
    #    stop. Consuming to the next brace ate real narrative in testing.
    #    Leaving the citation text inline is ugly but never destructive.
    s = RE_REF.sub(" ", s)

    # 3. Balanced templates, innermost-first so shallow nesting unwinds.
    for _ in range(3):
        s, changed = RE_TEMPLATE.subn(" ", s)
        if not changed:
            break
    s = RE_STRAY_BRACES.sub(" ", s)

    # 4. Link openers: drop the brackets, keep the text (see module docstring).
    s = RE_LINK_OPEN.sub("", s)
    s = s.replace("]]", "")

    # 5. Entities and any real tags.
    s = html.unescape(s)
    s = RE_TAG.sub(" ", s)

    # 6. Bare URLs: citation debris that outlived its <ref>. Unlike the
    #    citation text around them they have an unambiguous end, and a URL is
    #    never narrative, so these can go.
    s = RE_URL.sub(" ", s)

    # 7. Whitespace left behind by upstream link stripping, and punctuation
    #    stranded at the very start (The Godfather Part II began ": In 1901").
    s = RE_WS.sub(" ", s)
    s = RE_SPACE_BEFORE_PUNCT.sub(r"\1", s)
    s = RE_SPACE_IN_PAREN.sub(lambda m: m.group(0).strip(), s)
    return RE_LEADING_PUNCT.sub("", s).strip()


# ---------------------------------------------------------------------------
# Live Wikipedia: reading sections out of an article extract
# ---------------------------------------------------------------------------

def split_sections(extract):
    """Split a plain-text extract into (level, heading, body) triples.

    The lead -- everything before the first heading -- is level 1 with an
    empty heading.
    """
    extract = extract or ""
    sections, pos, level, heading = [], 0, 1, ""
    for m in RE_HEADING.finditer(extract):
        sections.append((level, heading, extract[pos:m.start()]))
        level, heading, pos = len(m.group(1)), m.group(2), m.end()
    sections.append((level, heading, extract[pos:]))
    return sections


def _paragraphs(text):
    """One paragraph per non-empty line, separated by a blank line.

    The app renders the synopsis as markdown, where a single newline is not a
    break at all.
    """
    return "\n\n".join(line.strip() for line in text.splitlines()
                       if line.strip())


def _with_subsections(sections, i):
    """Text of sections[i] plus every deeper section under it, and the index
    just past them. Subsection headings stay, as their own paragraph."""
    level = sections[i][0]
    parts = [sections[i][2]]
    j = i + 1
    while j < len(sections) and sections[j][0] > level:
        parts += [sections[j][1], sections[j][2]]
        j += 1
    return _paragraphs("\n".join(parts)), j


def extract_sections(extract):
    """Pick the plot and the themes/analysis text out of an article extract.

    Returns a dict of plot_heading, plot_text, themes_heading and themes_text;
    a section the article lacks is None throughout.
    """
    sections = split_sections(extract)
    out = dict(plot_heading=None, plot_text=None,
               themes_heading=None, themes_text=None)

    for i, (level, heading, _) in enumerate(sections):
        if level == 2 and RE_PLOT_HEADING.match(heading):
            text, _ = _with_subsections(sections, i)
            if text:
                out["plot_heading"], out["plot_text"] = heading, text
                break

    # Themes can sit at any level ("=== Themes ===" under Reception). A match
    # takes its subsections with it, so a nested match is never counted twice.
    headings, texts, i = [], [], 0
    while i < len(sections):
        level, heading, _ = sections[i]
        if (level >= 2 and RE_THEMES_HEADING.search(heading)
                and not RE_NOT_THEMES.search(heading)):
            text, i = _with_subsections(sections, i)
            if text:
                headings.append(heading)
                texts.append(text)
            continue
        i += 1
    if texts:
        out["themes_heading"] = "; ".join(headings)
        out["themes_text"] = "\n\n".join(texts)
    return out


def fetch_extract(session, page_id):
    """One article as (revid, title, plain-text extract), or None when the
    page no longer exists. Raises on a transport or API failure, so the caller
    can leave the film uncached and retry it next run."""
    r = session.get(WIKIPEDIA_API, timeout=30, params={
        "action": "query", "prop": "extracts|revisions",
        "explaintext": 1, "exsectionformat": "wiki", "rvprop": "ids",
        "pageids": page_id, "format": "json", "formatversion": 2,
    })
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"{data['error'].get('code')}: "
                           f"{data['error'].get('info')}")
    pages = (data.get("query") or {}).get("pages") or []
    if not pages or pages[0].get("missing") or pages[0].get("invalid"):
        return None
    page = pages[0]
    revid = (page.get("revisions") or [{}])[0].get("revid")
    return revid, page.get("title"), page.get("extract") or ""


def _default_fetcher():
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    return lambda page_id: fetch_extract(session, page_id)


def _fetch_with_retries(fetch, page_id):
    # Any failure is retried, not only a transport one: fetch_extract raises on
    # an error the API reports inside a 200. The settings are read per call, so
    # a test can shorten them.
    return http.call_with_retries(
        lambda: fetch(page_id), retry_on=(Exception,),
        attempts=FETCH_ATTEMPTS, backoff=RETRY_SLEEP,
        what=f"Wikipedia page {page_id}")


def _words(text):
    return len(text.split()) if text else None


def fetch_live_sections(conn, fetch, refresh=False):
    """Write through to raw_wiki_articles for every curated film not fetched
    yet -- every film at all with refresh. Returns (fetched, failed).

    Keyed on the CURRENT page id. CMU's 2012 ids are the wrong key here: some
    articles have been recreated since (Big, The Firm).
    """
    pending = "" if refresh else "AND w.wikipedia_page_id IS NULL"
    todo = conn.execute(f"""
        SELECT DISTINCT m.wikipedia_page_id, m.title
        FROM curated_movies m
        LEFT JOIN raw_wiki_articles w
          ON w.wikipedia_page_id = m.wikipedia_page_id
        WHERE m.wikipedia_page_id IS NOT NULL {pending}
        ORDER BY m.title
    """).fetchall()
    if not todo:
        logger.info("Live Wikipedia: every film already fetched "
                    "(--refresh to re-read)")
        return 0, 0

    logger.info(f"Live Wikipedia: fetching {len(todo)} articles")
    fetched = failed = streak = 0
    for n, (page_id, title) in enumerate(todo, 1):
        try:
            article = _fetch_with_retries(fetch, page_id)
        except Exception as e:
            failed += 1
            streak += 1
            logger.warning(f"  {title}: fetch failed, left for next run ({e})")
            if streak >= MAX_CONSECUTIVE_FAILURES:
                logger.warning(
                    f"  {streak} failures in a row -- stopping fetches for "
                    f"this run; {len(todo) - n} films not attempted")
                break
            continue
        streak = 0

        revid, wiki_title, extract = article or (None, None, "")
        s = extract_sections(extract)
        conn.execute("""
            INSERT OR REPLACE INTO raw_wiki_articles
                (wikipedia_page_id, revid, title, plot_heading, plot_text,
                 plot_words, themes_heading, themes_text, themes_words,
                 fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (page_id, revid, wiki_title, s["plot_heading"], s["plot_text"],
              _words(s["plot_text"]), s["themes_heading"], s["themes_text"],
              _words(s["themes_text"])))
        fetched += 1
        if article is None:
            logger.warning(f"  {title}: page {page_id} not found on Wikipedia")
        elif not s["plot_text"]:
            logger.warning(f"  {title}: live article has no plot section")
        if n % 50 == 0:
            conn.commit()
            logger.info(f"  {n}/{len(todo)}")
        time.sleep(FETCH_SLEEP)

    conn.commit()
    logger.info(f"Live Wikipedia: {fetched} fetched, {failed} failed")
    return fetched, failed


# ---------------------------------------------------------------------------
# Best of both
# ---------------------------------------------------------------------------

def choose_plot(cmu_text, live_text):
    """(text, source) for the longer plot by word count; a tie goes to live.
    (None, None) when neither exists."""
    cmu_n = _words(cmu_text) or 0
    live_n = _words(live_text) or 0
    if not cmu_n and not live_n:
        return None, None
    if live_n >= cmu_n:
        return live_text, SOURCE_LIVE
    return cmu_text, SOURCE_CMU


def _tally_key(cmu, live, source):
    if cmu and live:
        return "live_over_cmu" if source == SOURCE_LIVE else "cmu_over_live"
    if live:
        return "live_only"
    return "cmu_only" if cmu else "neither"


def _ensure_column(cursor, table, column, decl="TEXT"):
    existing = {r[1] for r in cursor.execute(f"PRAGMA table_info({table})")}
    if existing and column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        logger.info(f"Migrated {table}: added {column} column")


def ensure_schema(cursor):
    for column, decl in [("plot_summary_wiki", "TEXT"),
                         ("plot_summary_wiki_words", "INTEGER"),
                         ("plot_summary_wiki_source", "TEXT"),
                         ("wikipedia_revid", "INTEGER"),
                         ("themes_wiki", "TEXT"),
                         ("themes_wiki_heading", "TEXT"),
                         ("themes_wiki_words", "INTEGER")]:
        _ensure_column(cursor, "curated_movies", column, decl)
    # raw_zone.sql creates raw_wiki_articles on databases that predate it.
    # curated_zone.sql is re-applied so v_movie_cmu picks up its current
    # definition: the view is DROP/CREATE (views are derived, so recreating is
    # free) -- without this, a database created before the raw/cleaned column
    # rename keeps serving the old column names. Both files are otherwise
    # CREATE ... IF NOT EXISTS, so re-applying them is a no-op.
    schema_dir = config.SCHEMA_DIR
    for fname in ["raw_zone.sql", "curated_zone.sql"]:
        cursor.executescript((schema_dir / fname).read_text(encoding="utf-8"))


def residue_report(rows):
    """Count cleaned summaries still carrying markup tokens."""
    found = {}
    for title, text in rows:
        for token, kind in RESIDUE.items():
            if token in text:
                found.setdefault(f"{token} ({kind})", []).append(title)
    return found


def enrich_plot_summaries(db_path, force=False, refresh=False, fetch=None):
    """Fetch what is missing, then promote the better plot for every film.

    `fetch` maps a page id to (revid, title, extract) or None; it defaults to
    the live API. Returns (films written, films with a plot).
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if not cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='raw_cmu_summaries'").fetchone():
        logger.error("raw_cmu_summaries not found. Run 11_load_cmu.py first.")
        conn.close()
        sys.exit(1)

    ensure_schema(cursor)
    conn.commit()

    fetch_live_sections(conn, fetch or _default_fetcher(), refresh)

    # CMU joins via freebase_id, never directly on wikipedia_page_id: CMU's
    # page ids are from a Nov 2012 dump and some articles have been recreated
    # since. Live joins on the current id, which is what it was fetched by.
    rows = cursor.execute("""
        SELECT m.movie_id, m.title, s.summary,
               w.plot_text, w.revid, w.themes_text, w.themes_heading,
               m.plot_summary_wiki, m.plot_summary_wiki_source,
               m.wikipedia_revid, m.themes_wiki, m.themes_wiki_heading
        FROM curated_movies m
        LEFT JOIN raw_cmu_movies cm ON cm.freebase_id = m.freebase_id
        LEFT JOIN raw_cmu_summaries s
          ON s.wikipedia_page_id = cm.wikipedia_page_id
        LEFT JOIN raw_wiki_articles w
          ON w.wikipedia_page_id = m.wikipedia_page_id
        ORDER BY m.title
    """).fetchall()
    logger.info(f"Choosing plots for {len(rows)} films")

    tally = dict.fromkeys(
        ["live_over_cmu", "cmu_over_live", "live_only", "cmu_only", "neither"], 0)
    updated, cmu_written, citation_debris, dropped_chars = 0, [], [], 0
    for (movie_id, title, raw_cmu, live, revid, themes, themes_heading,
         *current) in rows:
        cmu = clean_wiki_markup(raw_cmu) or None
        if raw_cmu and not cmu:
            logger.warning(f"{title}: CMU summary cleaned to empty, ignoring it")
        text, source = choose_plot(cmu, live)
        tally[_tally_key(cmu, live, source)] += 1

        chosen = (text, source, revid, themes, themes_heading)
        if not force and chosen == tuple(current):
            continue
        cursor.execute("""
            UPDATE curated_movies
            SET plot_summary_wiki        = ?,
                plot_summary_wiki_words  = ?,
                plot_summary_wiki_source = ?,
                wikipedia_revid          = ?,
                themes_wiki              = ?,
                themes_wiki_heading      = ?,
                themes_wiki_words        = ?,
                updated_at               = CURRENT_TIMESTAMP
            WHERE movie_id = ?
        """, (text, _words(text), source, revid, themes, themes_heading,
              _words(themes), movie_id))
        updated += 1
        if source == SOURCE_CMU:
            cmu_written.append((title, text))
            dropped_chars += len(raw_cmu) - len(text)
            if "<ref" in raw_cmu.lower():
                citation_debris.append(title)

    conn.commit()

    filled = len(rows) - tally["neither"]
    words = cursor.execute(
        "SELECT AVG(plot_summary_wiki_words) FROM curated_movies "
        "WHERE plot_summary_wiki_words IS NOT NULL").fetchone()[0]
    themed = cursor.execute(
        "SELECT COUNT(*) FROM curated_movies WHERE themes_wiki IS NOT NULL"
    ).fetchone()[0]
    conn.close()

    avg = f" (avg {words:.0f} words)" if words else ""
    logger.info(f"✓ Plot summaries complete: {updated} written, "
                f"{filled}/{len(rows)} films now have one{avg}")
    logger.info(f"  both sources: live longer for {tally['live_over_cmu']}, "
                f"CMU longer for {tally['cmu_over_live']}")
    logger.info(f"  one source:   live only {tally['live_only']}, "
                f"CMU only {tally['cmu_only']}; neither {tally['neither']}")
    logger.info(f"  themes/analysis section: {themed} films")

    if cmu_written:
        logger.info(f"  CMU markup removed: {dropped_chars:,} chars")
        residue = residue_report(cmu_written)
        if residue:
            logger.warning("  residual markup still present:")
            for token, titles in sorted(residue.items()):
                sample = ", ".join(titles[:3])
                more = f" (+{len(titles)-3} more)" if len(titles) > 3 else ""
                logger.warning(f"    {token}: {len(titles)} films — {sample}{more}")
        else:
            logger.info("  no residual markup tokens detected")

        if citation_debris:
            logger.warning(
                f"  citation text left inline (unclosed <ref> in source, no safe "
                f"terminator) — {len(citation_debris)} films for manual review: "
                f"{', '.join(citation_debris)}")

    return updated, filled


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true",
                    help="rewrite every film's plot columns, not just changed ones")
    ap.add_argument("--refresh", action="store_true",
                    help="re-fetch every live Wikipedia article")
    ap.add_argument("--db", default=str(config.db_path()))
    args = ap.parse_args()

    if not Path(args.db).exists():
        logger.error(f"{args.db} not found.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Phase 3: Plot summaries -- CMU + live Wikipedia, best of both")
    logger.info("=" * 60)
    enrich_plot_summaries(args.db, force=args.force, refresh=args.refresh)
    logger.info("=" * 60)


if __name__ == "__main__":
    config.setup_logging()
    main()
