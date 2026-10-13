#!/usr/bin/env python3
"""
Step 17: build the curated category tables from stored rewatchvault pages.

Reads raw_category_pages (step 16 fills it, batch by batch) and rebuilds, from
nothing, every table in curated_zone.sql's "Category entries" block:

    category_episode_map       each rewatchvault episode -> its airing
    curated_categories         one row per category, after aliases
    curated_category_entries   one row per entry (page)
    curated_category_bullets   the discussion, names restored
    curated_category_mentions  every inline link, with offsets
    curated_category_picks     the hosts' picks, where a page has them

No network. With no pages stored it builds empty tables, so it is safe in every
orchestrated run -- and it must be in them: it copies movie_id from
curated_episode_movies, which a curated rebuild reissues.

Placing an episode. A rewatchvault episode maps to the airing within
WINDOW_DAYS of its date whose title agrees with its film's. rewatchvault often
dates an episode a day later (report 024), so an exact-date join misses a third
of them. Anything the rule can't place is in data/category_episode_overrides.csv
or stays unmapped and is logged -- never matched on title alone (report 012).

Placing a category. The category id comes from the page's slug
("<episode>-<category>-<n>"). 56 pages have opaque slugs (c2, c58, ...); those
take the id their banner carries everywhere else. data/category_aliases.csv
folds ids the site uses twice for one category.

Usage:
    python scripts/17_build_categories.py
"""

import argparse
import csv
import json
import logging
import re
import sqlite3
import unicodedata
import zlib
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from rewatchables import config
from rewatchables import rewatchvault as rv

logger = logging.getLogger(__name__)

OVERRIDES = config.DATA_DIR / "category_episode_overrides.csv"
ALIASES = config.DATA_DIR / "category_aliases.csv"
WINDOW_DAYS = 2

# Icon family -> category family. Every other icon is a standing category's own.
FAMILIES = {"flex-bicep-web": "one_off", "segments": "segment", "most-year": "most_year"}

TABLES = ["curated_category_picks", "curated_category_mentions",
          "curated_category_bullets", "curated_category_entries",
          "curated_categories", "category_episode_map"]


# ---------------------------------------------------------------------------
# Rules
# ---------------------------------------------------------------------------

def title_key(title):
    """'Ocean's 11' and "Oceans 11" alike: ASCII-folded, & as and, alphanumerics."""
    folded = unicodedata.normalize("NFKD", str(title or "")).lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]", "", folded)


def titles_agree(a, b):
    """Equal keys, or one containing the other once both are four characters
    or more ("Boogie Nights" in "Boogie Nights (Part 1 and 2)")."""
    a, b = title_key(a), title_key(b)
    if not a or not b:
        return False
    return a == b or (min(len(a), len(b)) >= 4 and (a in b or b in a))


def _days(later, earlier):
    return (date.fromisoformat(later) - date.fromisoformat(earlier)).days


def read_overrides(path=OVERRIDES):
    """{rv_episode_slug: (episode_number, episode_date, note)}."""
    if not Path(path).exists():
        return {}
    with open(path, encoding="utf-8", newline="") as f:
        return {r["rv_episode_slug"]: (int(r["episode_number"]), r["episode_date"], r["note"])
                for r in csv.DictReader(f)}


def read_aliases(path=ALIASES):
    """{alias slug: canonical slug}. Refuses a chain: a canonical id that is
    itself an alias would make the result depend on the order of the file."""
    if not Path(path).exists():
        return {}
    with open(path, encoding="utf-8", newline="") as f:
        aliases = {r["alias_slug"]: r["canonical_slug"] for r in csv.DictReader(f)}
    chained = set(aliases.values()) & set(aliases)
    if chained:
        raise SystemExit(f"{path}: these are both an alias and a target: {sorted(chained)}")
    return aliases


def map_episodes(rv_episodes, airings, overrides):
    """One category_episode_map row per rewatchvault episode.

    rv_episodes  {rv_episode_slug: (air_date, film_title)}
    airings      [{episode_movie_id, movie_id, episode_number, episode_date,
                   episode_title, movie_title}] from curated_episode_movies
    overrides    read_overrides()
    """
    by_key = {(a["episode_number"], a["episode_date"]): a for a in airings}
    rows = []
    for slug, (air_date, film) in sorted(rv_episodes.items()):
        row = {"rv_episode_slug": slug, "rv_air_date": air_date, "rv_film_title": film,
               "episode_movie_id": None, "movie_id": None, "episode_number": None,
               "episode_date": None, "match_rule": "unmapped", "day_offset": None, "note": None}
        hit = None
        if slug in overrides:
            number, when, note = overrides[slug]
            hit = by_key.get((number, when))
            # An override whose airing has gone -- the episode list was
            # corrected, say -- is reported and the rule gets its turn.
            stale = None if hit else f"override points at no airing: ep {number} on {when}"
        if hit is not None:
            found, rule = [hit], "override"
            row["note"] = note
        else:
            found = [a for a in airings
                     if air_date and a["episode_date"]
                     and abs(_days(a["episode_date"], air_date)) <= WINDOW_DAYS
                     and (titles_agree(film, a["episode_title"])
                          or titles_agree(film, a["movie_title"]))]
            rule = "date_title"
            if slug in overrides:
                row["note"] = stale
            if len(found) != 1:
                why = (f"no airing within {WINDOW_DAYS} days with a matching title"
                       if not found else
                       f"{len(found)} airings match: "
                       + ", ".join(f"ep {a['episode_number']}" for a in found))
                row["note"] = f"{row['note']}; {why}" if row["note"] else why
                rows.append(row)
                continue
        a = found[0]
        row.update(episode_movie_id=a["episode_movie_id"], movie_id=a["movie_id"],
                   episode_number=a["episode_number"], episode_date=a["episode_date"],
                   match_rule=rule,
                   day_offset=_days(a["episode_date"], air_date) if air_date else None)
        rows.append(row)
    return rows


def banner_categories(pairs, aliases):
    """{banner: {canonical category slug}} from (slug, episode, banner) triples
    that carry a derivable slug."""
    seen = defaultdict(set)
    for slug, episode, banner in pairs:
        cat = rv.category_slug(slug, episode)
        if cat and banner:
            seen[banner].add(aliases.get(cat, cat))
    return seen


def banner_slug(banner):
    """'Private Hudson Game Over Man category' -> 'private-hudson-game-over-man-category'."""
    folded = unicodedata.normalize("NFKD", str(banner or "")).lower()
    return re.sub(r"[^a-z0-9]+", "-", folded).strip("-") or None


def resolve_category(page, aliases, by_banner):
    """(category slug or None, source) for one parsed page.

    The slug's own id; else the one id its banner carries everywhere else;
    else, for a banner that appears nowhere else (Aliens' "Private Hudson Game
    Over Man category"), an id made from the banner itself -- a one-off award
    by construction. A banner carried under two ids still resolves to None:
    that is ambiguity, which is reported, not guessed (report 031).
    """
    if page["category_slug"]:
        return aliases.get(page["category_slug"], page["category_slug"]), "slug"
    options = by_banner.get(page["banner"], set())
    if len(options) == 1:
        return next(iter(options)), "banner"
    if not options and banner_slug(page["banner"]):
        own = banner_slug(page["banner"])
        return aliases.get(own, own), "banner"
    return None, "none"


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def stored_pages(conn):
    """[(raw_id, slug, html)] for the newest stored version of every page."""
    if "raw_category_pages" not in _tables(conn):
        return []
    return [(raw_id, slug, zlib.decompress(blob).decode("utf-8")) for raw_id, slug, blob in
            conn.execute("""SELECT raw_id, discussion_slug, article_html FROM raw_category_pages p
                            WHERE raw_id = (SELECT MAX(raw_id) FROM raw_category_pages q
                                            WHERE q.discussion_slug = p.discussion_slug)
                            ORDER BY discussion_slug""")]


def workbook_banners(conn):
    """(slug, episode, banner) for every workbook row: the widest view of which
    banner goes with which category id."""
    if "raw_category_workbook_rows" not in _tables(conn):
        return []
    out = []
    for slug, episode, blob in conn.execute(
            "SELECT discussion_slug, episode_slug, payload FROM raw_category_workbook_rows"):
        cells = dict(json.loads(zlib.decompress(blob).decode("utf-8")))
        out.append((slug, episode, cells.get("archive-answer-banner")))
    return out


def airings(conn):
    return [dict(zip(["episode_movie_id", "movie_id", "episode_number", "episode_date",
                      "episode_title", "movie_title"], r)) for r in conn.execute(
        """SELECT e.episode_movie_id, e.movie_id, e.episode_number, e.episode_date,
                  e.episode_title, m.title
           FROM curated_episode_movies e LEFT JOIN curated_movies m USING (movie_id)""")]


def _insert(conn, table, rows):
    if not rows:
        return
    cols = list(rows[0])
    conn.executemany(
        f"INSERT INTO {table} ({', '.join(chr(34) + c + chr(34) for c in cols)}) "
        f"VALUES ({', '.join('?' * len(cols))})",
        [[r[c] for c in cols] for r in rows])


def build(conn, overrides_path=OVERRIDES, aliases_path=ALIASES):
    """Rebuild every category table. Returns a summary dict."""
    for name in ["raw_zone.sql", "curated_zone.sql"]:
        conn.executescript((config.SCHEMA_DIR / name).read_text(encoding="utf-8"))
    overrides, aliases = read_overrides(overrides_path), read_aliases(aliases_path)

    parsed, failed = [], []
    for raw_id, slug, html in stored_pages(conn):
        try:
            parsed.append((raw_id, slug, rv.parse_article(html)))
        except rv.ParseError as e:
            failed.append((slug, str(e)))

    rv_episodes = {}
    for _, _, p in parsed:
        rv_episodes.setdefault(p["episode_slug"], (p["air_date"], p["film_title"]))
    episode_map = map_episodes(rv_episodes, airings(conn), overrides)
    placed = {r["rv_episode_slug"]: r for r in episode_map}

    by_banner = banner_categories(
        workbook_banners(conn) + [(s, p["episode_slug"], p["banner"]) for _, s, p in parsed],
        aliases)

    entries, bullets, mentions, picks = [], [], [], []
    for raw_id, slug, p in parsed:
        where = placed[p["episode_slug"]]
        category, source = resolve_category(p, aliases, by_banner)
        entries.append({
            "discussion_slug": slug, "rv_episode_slug": p["episode_slug"],
            "episode_movie_id": where["episode_movie_id"], "movie_id": where["movie_id"],
            "episode_number": where["episode_number"],
            "air_date": where["episode_date"] or p["air_date"], "film_title": p["film_title"],
            "category_slug": category, "category_source": source, "banner": p["banner"],
            "answer": p["answer"], "transcript_seconds": p["transcript_seconds"],
            "transcript_url": p["transcript_url"], "bullet_count": p["bullet_count"],
            "pick_count": len(p["choices"]), "source_url": rv.discussion_url(slug),
            "raw_id": raw_id,
        })
        inlines = [("answer", 0, {"mentions": p["answer_mentions"]})]
        for n, b in enumerate(p["bullets"], 1):
            bullets.append({
                "discussion_slug": slug, "position": n, "text": b["text"],
                "speaker_slugs": "; ".join(s["person_slug"] or "" for s in b["speakers"]) or None,
                "speaker_names": "; ".join(s["name"] for s in b["speakers"]) or None,
            })
            inlines.append(("bullet", n, b))
        for n, c in enumerate(p["choices"], 1):
            picks.append({"discussion_slug": slug, "position": n,
                          "speaker_slug": c["speaker"]["person_slug"],
                          "speaker_name": c["speaker"]["name"], "text": c["text"]})
            inlines.append(("pick", n, c))
        for location, n, inline in inlines:
            for m in inline["mentions"]:
                mentions.append({"discussion_slug": slug, "location": location, "position": n,
                                 "start": m["start"], "end": m["end"], "kind": m["kind"],
                                 "slug": m["slug"], "name": m["name"]})

    categories = []
    grouped = defaultdict(list)
    for e, (_, _, p) in zip(entries, parsed):
        if e["category_slug"]:
            grouped[e["category_slug"]].append((e, p))
    for cat, members in sorted(grouped.items()):
        # A page with no icon says nothing about its family; a category with
        # no icon at all is a one-off (Aliens' c8 is the only such page).
        families = Counter(FAMILIES.get(p["icon_family"], "standing")
                           for _, p in members if p["icon_family"]) or Counter(one_off=1)
        banners = Counter(e["banner"] for e, _ in members)
        dates = sorted(e["air_date"] for e, _ in members if e["air_date"])
        categories.append({
            "category_slug": cat, "family": families.most_common(1)[0][0],
            "display_name": banners.most_common(1)[0][0], "banners": len(banners),
            "entries": len(members), "episodes": len({e["rv_episode_slug"] for e, _ in members}),
            "first_aired": dates[0] if dates else None, "last_aired": dates[-1] if dates else None,
        })

    with conn:
        for table in TABLES:
            conn.execute(f"DELETE FROM {table}")
        _insert(conn, "category_episode_map", episode_map)
        _insert(conn, "curated_categories", categories)
        _insert(conn, "curated_category_entries", entries)
        _insert(conn, "curated_category_bullets", bullets)
        _insert(conn, "curated_category_mentions", mentions)
        _insert(conn, "curated_category_picks", picks)

    unmapped = [r for r in episode_map if r["match_rule"] == "unmapped"]
    unresolved = [e["discussion_slug"] for e in entries if e["category_slug"] is None]
    summary = {
        "pages": len(parsed), "parse_failures": failed, "episodes": len(episode_map),
        "unmapped": unmapped, "categories": len(categories), "entries": len(entries),
        "bullets": len(bullets), "mentions": len(mentions), "picks": len(picks),
        "by_banner": sum(e["category_source"] == "banner" for e in entries),
        "unresolved": unresolved,
    }
    logger.info(f"Categories: {len(entries)} entries from {len(parsed)} pages, "
                f"{len(episode_map)} episodes ({len(unmapped)} unmapped), "
                f"{len(categories)} categories, {len(bullets)} bullets, "
                f"{len(mentions)} links, {len(picks)} picks")
    for r in unmapped:
        logger.warning(f"  unmapped episode {r['rv_episode_slug']} ({r['rv_air_date']}): {r['note']}")
    if summary["by_banner"]:
        logger.info(f"  {summary['by_banner']} entries placed in a category by their banner")
    for slug in unresolved:
        logger.warning(f"  no category for {slug}")
    for slug, why in failed:
        logger.warning(f"  could not parse {slug}: {why}")
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(config.db_path()))
    args = ap.parse_args()
    if not Path(args.db).exists():
        raise SystemExit(f"{args.db} not found.")
    conn = sqlite3.connect(args.db)
    try:
        build(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    config.setup_logging()
    main()
