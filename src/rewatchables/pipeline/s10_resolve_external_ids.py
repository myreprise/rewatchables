#!/usr/bin/env python3
"""
Phase 1: Resolve external identifiers for each canonical movie.

Builds the bridge from our tmdb_id to the identifier space used by external
film datasets, in three hops:

  1. TMDB   GET /movie/{tmdb_id}/external_ids   -> wikidata_qid, imdb_id
  2. Wikidata  wbgetentities (50 ids/call)      -> freebase_id (P646),
                                                   enwiki sitelink title
  3. Wikipedia query&titles (50 titles/call)    -> wikipedia_page_id (curid)

Fills four previously-null columns on curated_movies:
  wikidata_qid       Q-number
  freebase_id        /m/xxxxx  -- primary join key for the CMU Movie Summary
                     Corpus; immutable, since Freebase froze in 2016
  wikipedia_page_id  enwiki curid -- CMU's other join key
  wikipedia_url      canonical article URL

Only hop 1 is per-film; hops 2 and 3 batch 50 at a time, so a full resolve of
~450 films costs ~450 TMDB calls and ~20 batched calls, not 1350.

Idempotent: skips movies whose four columns are already filled.

Persistent cache: results are written through to `external_id_cache` (keyed by
tmdb_id). 06_build_curated wipes and rebuilds curated_movies on every run --
clearing these columns -- so the cache lets us refill from local storage rather
than re-resolving. A film genuinely without a freebase_id (anything postdating
the 2016 Freebase freeze) caches with NULL and is not retried; the `resolved`
flag, not per-column nullness, marks a row as done.
"""

import logging
import os
import sqlite3
import sys
import time
from pathlib import Path
from urllib.parse import quote

import requests

from rewatchables import config

logger = logging.getLogger(__name__)

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_BASE_URL = "https://api.themoviedb.org/3"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_ARTICLE = "https://en.wikipedia.org/wiki/"

RATE_LIMIT_SLEEP = 0.26   # TMDB: ~3.8 req/sec, under the 40/10s ceiling
BATCH_SLEEP = 0.5         # courtesy delay between WMF batch calls
BATCH_SIZE = 50           # wbgetentities / query&titles both cap at 50

# WMF asks for a descriptive UA identifying the client.
USER_AGENT = os.getenv(
    "WIKIMEDIA_USER_AGENT",
    "rewatchables-pipeline/0.1 (https://github.com/myreprise/rewatchables)",
)
HEADERS = {"User-Agent": USER_AGENT}


def _redact(text):
    if text and TMDB_API_KEY:
        return str(text).replace(TMDB_API_KEY, "***")
    return text


# ---------------------------------------------------------------------------
# Hop 1: TMDB -> wikidata_qid / imdb_id
# ---------------------------------------------------------------------------

def fetch_external_ids(tmdb_id):
    """Return {'wikidata_qid':..., 'imdb_id':...} for a tmdb_id, or None."""
    url = f"{TMDB_BASE_URL}/movie/{tmdb_id}/external_ids"
    params = {"api_key": TMDB_API_KEY}

    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 200:
                d = r.json()
                return {"wikidata_qid": d.get("wikidata_id") or None,
                        "imdb_id": d.get("imdb_id") or None}
            if r.status_code == 404:
                logger.warning(f"tmdb_id {tmdb_id} returned 404 — skipping")
                return None
            logger.warning(f"tmdb_id {tmdb_id} HTTP {r.status_code} "
                           f"(attempt {attempt+1}/3)")
            time.sleep(2 * (attempt + 1))
        except (requests.Timeout, requests.ConnectionError) as e:
            logger.warning(f"tmdb_id {tmdb_id} transient error "
                           f"(attempt {attempt+1}/3): {_redact(str(e))}")
            time.sleep(2 * (attempt + 1))
        except Exception as e:
            logger.error(f"tmdb_id {tmdb_id} unexpected error: {_redact(str(e))}")
            return None

    logger.error(f"tmdb_id {tmdb_id} gave up after 3 attempts")
    return None


# ---------------------------------------------------------------------------
# Hop 2: Wikidata -> freebase_id (P646) + enwiki title
# ---------------------------------------------------------------------------

def _chunks(seq, size=BATCH_SIZE):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def fetch_wikidata(qids):
    """Map each Q-number to {'freebase_id':..., 'enwiki_title':...}.

    Batched 50 per request. A failed batch degrades to empty entries for that
    batch rather than aborting the run.
    """
    out = {}
    for batch in _chunks(list(qids)):
        try:
            r = requests.get(WIKIDATA_API, headers=HEADERS, timeout=30, params={
                "action": "wbgetentities", "ids": "|".join(batch),
                "props": "sitelinks|claims", "sitefilter": "enwiki",
                "format": "json",
            })
            entities = r.json().get("entities") or {}
        except Exception as e:
            logger.warning(f"Wikidata batch failed ({len(batch)} ids): {e}")
            entities = {}

        for qid, ent in entities.items():
            claims = (ent.get("claims") or {}).get("P646") or []
            fb = [c["mainsnak"]["datavalue"]["value"] for c in claims
                  if c.get("mainsnak", {}).get("datavalue")]
            title = ((ent.get("sitelinks") or {}).get("enwiki") or {}).get("title")
            out[qid] = {"freebase_id": fb[0] if fb else None,
                        "enwiki_title": title}
        time.sleep(BATCH_SLEEP)
    return out


# ---------------------------------------------------------------------------
# Hop 3: Wikipedia title -> page id
# ---------------------------------------------------------------------------

def fetch_page_ids(titles):
    """Map each enwiki title to its current page id, following redirects."""
    out = {}
    for batch in _chunks(sorted(titles)):
        try:
            r = requests.get(WIKIPEDIA_API, headers=HEADERS, timeout=30, params={
                "action": "query", "titles": "|".join(batch),
                "format": "json", "redirects": 1,
            })
            q = r.json().get("query") or {}
        except Exception as e:
            logger.warning(f"Wikipedia batch failed ({len(batch)} titles): {e}")
            continue

        # The API normalizes and follows redirects, so walk both maps back to
        # the title we asked for.
        norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
        redir = {n["from"]: n["to"] for n in q.get("redirects", [])}
        by_title = {p["title"]: int(pid) for pid, p in (q.get("pages") or {}).items()
                    if int(pid) > 0}
        for t in batch:
            resolved = norm.get(t, t)
            resolved = redir.get(resolved, resolved)
            if resolved in by_title:
                out[t] = by_title[resolved]
        time.sleep(BATCH_SLEEP)
    return out


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _ensure_column(cursor, table, column, decl="TEXT"):
    """Add `column` to `table` if missing (no-op when already present)."""
    existing = {r[1] for r in cursor.execute(f"PRAGMA table_info({table})")}
    if existing and column not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        logger.info(f"Migrated {table}: added {column} column")


def ensure_cache_table(cursor):
    """Create the external-id cache if absent, and migrate curated_movies."""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS external_id_cache (
            tmdb_id INTEGER PRIMARY KEY,
            wikidata_qid TEXT,
            freebase_id TEXT,
            wikipedia_page_id INTEGER,
            wikipedia_url TEXT,
            imdb_id TEXT,
            resolved INTEGER DEFAULT 1,
            cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    _ensure_column(cursor, "curated_movies", "wikipedia_page_id", "INTEGER")
    _ensure_column(cursor, "curated_movies", "freebase_id", "TEXT")


def cache_get(cursor, tmdb_id):
    """Return the cached bridge for tmdb_id, or None if never resolved."""
    return cursor.execute(
        "SELECT wikidata_qid, freebase_id, wikipedia_page_id, wikipedia_url "
        "FROM external_id_cache WHERE tmdb_id = ? AND resolved = 1", (tmdb_id,)
    ).fetchone()


def cache_put(cursor, tmdb_id, qid, freebase_id, page_id, url, imdb_id):
    cursor.execute(
        "INSERT OR REPLACE INTO external_id_cache "
        "(tmdb_id, wikidata_qid, freebase_id, wikipedia_page_id, wikipedia_url, "
        " imdb_id, resolved, cached_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)",
        (tmdb_id, qid, freebase_id, page_id, url, imdb_id))


def _write(cursor, movie_id, qid, freebase_id, page_id, url):
    cursor.execute("""
        UPDATE curated_movies
        SET wikidata_qid      = ?,
            freebase_id       = ?,
            wikipedia_page_id = ?,
            wikipedia_url     = ?,
            updated_at        = CURRENT_TIMESTAMP
        WHERE movie_id = ?
    """, (qid, freebase_id, page_id, url, movie_id))


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def resolve_external_ids(db_path):
    if not TMDB_API_KEY:
        logger.error("TMDB_API_KEY not set in config/.env")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    ensure_cache_table(cursor)
    conn.commit()

    cursor.execute("""
        SELECT movie_id, tmdb_id, title
        FROM curated_movies
        WHERE wikidata_qid IS NULL
           OR freebase_id IS NULL
           OR wikipedia_page_id IS NULL
           OR wikipedia_url IS NULL
        ORDER BY title
    """)
    pending = cursor.fetchall()
    total = cursor.execute("SELECT COUNT(*) FROM curated_movies").fetchone()[0]
    logger.info(f"Resolving external ids for {len(pending)}/{total} movies "
                f"({total - len(pending)} already complete)")

    from_cache = needs_api = 0
    to_resolve = []                      # (movie_id, tmdb_id, title)
    for movie_id, tmdb_id, title in pending:
        cached = cache_get(cursor, tmdb_id)
        if cached is not None:
            _write(cursor, movie_id, *cached)
            from_cache += 1
        else:
            to_resolve.append((movie_id, tmdb_id, title))
            needs_api += 1
    conn.commit()
    if from_cache:
        logger.info(f"  {from_cache} refilled from cache")

    if not to_resolve:
        conn.close()
        logger.info(f"✓ External ids complete: {from_cache} from cache, 0 resolved")
        return from_cache, 0, 0

    # --- hop 1 (per film, rate-limited) ------------------------------------
    logger.info(f"Hop 1/3: TMDB external_ids for {len(to_resolve)} movies")
    rows, errors = [], 0
    for i, (movie_id, tmdb_id, title) in enumerate(to_resolve, 1):
        ext = fetch_external_ids(tmdb_id)
        if ext is None:
            errors += 1
        rows.append({"movie_id": movie_id, "tmdb_id": tmdb_id, "title": title,
                     "wikidata_qid": (ext or {}).get("wikidata_qid"),
                     "imdb_id": (ext or {}).get("imdb_id")})
        if i % 100 == 0:
            logger.info(f"  hop 1: {i}/{len(to_resolve)}")
        time.sleep(RATE_LIMIT_SLEEP)

    qids = [r["wikidata_qid"] for r in rows if r["wikidata_qid"]]
    logger.info(f"  {len(qids)}/{len(rows)} resolved to a wikidata_qid")

    # --- hop 2 (batched) ---------------------------------------------------
    logger.info(f"Hop 2/3: Wikidata for {len(qids)} qids "
                f"({(len(qids) + BATCH_SIZE - 1)//BATCH_SIZE} batches)")
    wd = fetch_wikidata(qids)
    logger.info(f"  {sum(1 for v in wd.values() if v['freebase_id'])} freebase ids, "
                f"{sum(1 for v in wd.values() if v['enwiki_title'])} enwiki titles")

    # --- hop 3 (batched) ---------------------------------------------------
    titles = {v["enwiki_title"] for v in wd.values() if v["enwiki_title"]}
    logger.info(f"Hop 3/3: Wikipedia page ids for {len(titles)} titles")
    page_ids = fetch_page_ids(titles)
    logger.info(f"  {len(page_ids)}/{len(titles)} page ids resolved")

    # --- persist -----------------------------------------------------------
    resolved = 0
    for r in rows:
        ent = wd.get(r["wikidata_qid"] or "", {})
        title = ent.get("enwiki_title")
        page_id = page_ids.get(title) if title else None
        url = f"{WIKIPEDIA_ARTICLE}{quote(title.replace(' ', '_'))}" if title else None
        cache_put(cursor, r["tmdb_id"], r["wikidata_qid"], ent.get("freebase_id"),
                  page_id, url, r["imdb_id"])
        _write(cursor, r["movie_id"], r["wikidata_qid"], ent.get("freebase_id"),
               page_id, url)
        resolved += 1
    conn.commit()
    conn.close()

    logger.info(f"✓ External ids complete: {from_cache} from cache, "
                f"{resolved} resolved, {errors} errors")
    return from_cache, resolved, errors


def main():
    db_path = str(config.db_path())
    if not Path(db_path).exists():
        logger.error(f"{db_path} not found.")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Phase 1: Resolve external identifiers")
    logger.info("=" * 60)
    resolve_external_ids(db_path)
    logger.info("=" * 60)


if __name__ == "__main__":
    config.setup_logging()
    main()
