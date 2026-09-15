#!/usr/bin/env python3
"""
Phase U: Upcoming films — convert, load, resolve, build.

Films expected in future episodes, contributed by listeners. One script covers
every zone because there is nothing to interleave: no human-in-the-loop review
step, no second source to join, and the whole path is a few hundred rows.

  convert  "data/remaining films.xlsx" -> data/upcoming.csv
  load     data/upcoming.csv -> raw_upcoming_films   (upsert, versioned)
  resolve  each film -> tmdb_id                      (via tmdb_search_cache)
  build    -> curated_upcoming_films                 (rebuilt every run)

THE XLSX IS THE SOURCE OF TRUTH. It is the file that gets edited, so it is the
file the pipeline reads, and every run regenerates the CSV from it before doing
anything else.

THE CSV IS DERIVED, AND STILL TRACKED IN GIT. That is not a contradiction — it
is the whole point. An xlsx diffs as "Bin 71028 -> 76009 bytes", which tells you
nothing about which film was added; the CSV beside it turns the same change into
a one-line diff you can read and merge. It is a rendering of the source, not a
second copy of it.

WHICH MEANS EDITS TO THE CSV ARE DISCARDED. The same trap step 01 sets for
episodes.csv, and it fails just as silently: the conversion simply writes the
xlsx's version over the top and the load stores that. Edit the xlsx. If you have
genuinely hand-edited the CSV and want this run to keep it, pass --skip-convert.

IF THE XLSX IS ABSENT the run falls back to the CSV and says so. A fresh
checkout has the CSV (it is tracked) but need not have the xlsx, and the
pipeline has to build there.

NOTHING HERE IS A NEW IMPLEMENTATION OF ANYTHING. The title normalizer, the
candidate scorer and both TMDB caches are imported from 04_enrich and
09_enrich_metadata. Two copies of the scorer would drift, and the moment they
did, "is this upcoming film the same film as that episode?" would have two
answers.

THE LOAD DOES NOT TOUCH raw_ingest_runs. raw_episodes_current pins to the newest
row of that table, so a load recorded there would present itself as the newest
episode snapshot and empty the episode view. Loads go to raw_upcoming_loads, the
same separation the CMU corpus uses.

RESOLUTION IS STRICTER HERE THAN ON THE EPISODE PATH: a film with no parseable
year is never auto-resolved. 04's scorer awards year_score = 0.5 when it has no
year to compare, which is a sensible neutral for an episode list where every row
is a film the show actually covered. This list is not that. It contains two TV
series, and 'Miami Vice (TV series)' with its year range stripped scores
0.75*1.0 + 0.25*0.5 = 0.875 against the 2006 film — over the 0.85 threshold. It
would auto-match a film it is not, and then delete itself as a graduate of that
film. Requiring a year costs three rows a poster and buys back that whole class
of error.

THE OVERLAP RULE. A film that has become a real episode is marked superseded,
not deleted; see the comment block on curated_upcoming_films in
sql/schemas/curated_zone.sql for why, and for the four title collisions that are
the reason the match is made on tmdb_id.

COST. First run: one TMDB search and one detail call per unseen film (~211 of
214 at the time of writing, roughly three minutes at the shared rate limit).
Every run after that is free — both caches are keyed independently of this
script and survive the rebuild.

Usage:
    python scripts/13_build_upcoming.py                # convert, load, build
    python scripts/13_build_upcoming.py --refresh      # bypass the search cache
    python scripts/13_build_upcoming.py --skip-convert # trust the CSV as it is
    python scripts/13_build_upcoming.py --skip-load    # rebuild from raw only

Through the orchestrator the conversion always runs -- steps are invoked without
arguments -- which is the right default now that the xlsx is the source. Reach
for --skip-convert by running this script directly.
"""

import argparse
import hashlib
import importlib.util
import json
import logging
import os
import re
import sqlite3
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from _keys import make_upcoming_id, upcoming_business_key

load_dotenv('config/.env')

logging.basicConfig(level=os.getenv('LOG_LEVEL', 'INFO'))
logger = logging.getLogger(__name__)

SCRIPTS_DIR = Path(__file__).parent
SOURCE_XLSX = Path(os.getenv('UPCOMING_XLSX', 'data/remaining films.xlsx'))
SOURCE_CSV = Path(os.getenv('UPCOMING_CSV', 'data/upcoming.csv'))


def _sibling(name, module_name):
    """Import a numerically-named pipeline script as a module.

    'from 04_enrich import ...' is not valid Python — the module name starts
    with a digit — so the reuse has to go through the loader directly. This is
    the same mechanism the test suite already uses to reach these functions.
    """
    spec = importlib.util.spec_from_file_location(
        module_name, SCRIPTS_DIR / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_enrich = _sibling('04_enrich.py', 'enrich_04')
_meta = _sibling('09_enrich_metadata.py', 'enrich_09')
_convert = _sibling('convert_xlsx_to_csv.py', 'convert_xlsx')

# Resolution — 04_enrich's scorer and search cache, unchanged.
strip_annotations = _enrich.strip_annotations
score_candidate = _enrich.score_candidate
search_tmdb_cached = _enrich.search_tmdb_cached
CONFIDENCE_THRESHOLD = _enrich.CONFIDENCE_THRESHOLD
TITLE_SIMILARITY_FLOOR = 0.6      # matches 04: a good year cannot rescue a bad title

# Metadata — 09_enrich_metadata's fetch, parse and cache, unchanged.
fetch_details = _meta.fetch_details
parse_details = _meta._parse
meta_cache_get = _meta.cache_get
meta_cache_put = _meta.cache_put
meta_people_put = _meta.people_put
RATE_LIMIT_SLEEP = _meta.RATE_LIMIT_SLEEP

YEAR_RE = re.compile(r'^\s*(\d{4})\s*$')


def parse_year(year_raw):
    """A four-digit year, or None.

    Deliberately strict. The source carries two ranges ('1984-1990',
    '1997-2003') and one blank, and every one of those is a row that should NOT
    auto-resolve — the ranges because they are TV series and the blank because
    there is nothing to disambiguate a title with. Taking the first year of a
    range would hand exactly those rows a confident wrong match.
    """
    if year_raw is None:
        return None
    match = YEAR_RE.match(str(year_raw))
    return int(match.group(1)) if match else None


def ensure_schema(cursor):
    """Create the upcoming tables and views if they are not there yet.

    Existing databases were built by an 02_load_raw run that executed the schema
    files once, at creation, so they have none of this. Both files are idempotent
    (CREATE ... IF NOT EXISTS, DROP/CREATE VIEW), but replaying raw_zone.sql
    whole would also recreate the episode unique index on a zone that may not be
    compacted — 02 guards that with assert_compacted and this script has no
    business making that call. So only the four upcoming objects are created.
    """
    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS raw_upcoming_loads (
            load_id TEXT PRIMARY KEY,
            source_file TEXT NOT NULL,
            loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            rows_ingested INTEGER,
            load_status TEXT CHECK(load_status IN ('success', 'partial', 'failed'))
        );

        CREATE TABLE IF NOT EXISTS raw_upcoming_films (
            raw_upcoming_id TEXT PRIMARY KEY,
            load_id TEXT NOT NULL,
            title TEXT,
            year TEXT,
            contributor TEXT,
            mention_note TEXT,
            pitch_tags TEXT,
            upcoming_key TEXT,
            source_hash TEXT NOT NULL,
            source_row_number INTEGER,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen_load_id TEXT,
            last_seen_at TIMESTAMP,
            FOREIGN KEY (load_id) REFERENCES raw_upcoming_loads(load_id)
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_upcoming_version
            ON raw_upcoming_films(upcoming_key, source_hash);
        CREATE INDEX IF NOT EXISTS idx_raw_upcoming_last_seen
            ON raw_upcoming_films(last_seen_load_id);

        DROP VIEW IF EXISTS raw_upcoming_films_current;
        CREATE VIEW raw_upcoming_films_current AS
        SELECT *
        FROM raw_upcoming_films
        WHERE last_seen_load_id = (
            SELECT load_id FROM raw_upcoming_loads
            WHERE load_status = 'success'
            ORDER BY loaded_at DESC LIMIT 1
        );

        CREATE TABLE IF NOT EXISTS curated_upcoming_films (
            upcoming_film_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            year_raw TEXT,
            year INTEGER,
            contributor TEXT,
            mention_note TEXT,
            pitch_tags TEXT,
            tmdb_id INTEGER,
            resolution_method TEXT CHECK(resolution_method IN (
                'auto_tmdb', 'unresolved_no_year', 'unresolved_no_match',
                'unresolved_low_confidence', 'unresolved_error')),
            confidence_score REAL,
            candidate_json TEXT,
            genres TEXT,
            keywords TEXT,
            runtime_minutes INTEGER,
            cast_names TEXT,
            plot_summary TEXT,
            poster_url_tmdb TEXT,
            rating_tmdb REAL,
            directors TEXT,
            superseded_by_movie_id TEXT,
            superseded_at TIMESTAMP,
            source_row_number INTEGER,
            built_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (superseded_by_movie_id) REFERENCES curated_movies(movie_id)
        );

        CREATE INDEX IF NOT EXISTS idx_upcoming_tmdb
            ON curated_upcoming_films(tmdb_id);
        CREATE INDEX IF NOT EXISTS idx_upcoming_superseded
            ON curated_upcoming_films(superseded_by_movie_id);

        DROP VIEW IF EXISTS v_upcoming_pending;
        CREATE VIEW v_upcoming_pending AS
        SELECT * FROM curated_upcoming_films
        WHERE superseded_by_movie_id IS NULL;

        DROP VIEW IF EXISTS v_upcoming_graduated;
        CREATE VIEW v_upcoming_graduated AS
        SELECT
            u.upcoming_film_id,
            u.title              AS requested_title,
            u.year_raw,
            u.contributor,
            u.mention_note,
            u.pitch_tags,
            u.superseded_at,
            m.movie_id,
            m.title              AS movie_title,
            m.year               AS movie_year,
            m.poster_url_tmdb,
            m.first_episode_date,
            m.total_episodes_featured
        FROM curated_upcoming_films u
        JOIN curated_movies m ON m.movie_id = u.superseded_by_movie_id;
    ''')
    _enrich.ensure_cache_table(cursor)
    _meta.ensure_cache_table(cursor)   # also creates curated_people


SOURCE_COLUMNS = ['title', 'year', 'contributor', 'mention_note', 'pitch_tags']


# ── Load ──────────────────────────────────────────────────────────────────────

def refresh_csv_from_xlsx(xlsx_path=None, csv_path=None):
    """Regenerate the CSV from the xlsx. Returns True if the run may continue.

    Three outcomes, and the middle one is the reason this is not just a call to
    convert():

      converted  the xlsx was read and the CSV rewritten
      skipped    no xlsx present -- fall back to the tracked CSV and say so
      failed     the xlsx is there but unreadable -- stop, do NOT fall back

    The failure that matters is Excel holding the file open, which raises
    PermissionError on Windows. Falling back to the CSV there would be the worst
    possible behaviour: the run would quietly build from the PREVIOUS version of
    the list while the user is looking at their edits on screen. Better to stop
    and say which file to close.
    """
    xlsx_path = Path(xlsx_path or SOURCE_XLSX)
    csv_path = Path(csv_path or SOURCE_CSV)

    if not xlsx_path.exists():
        if csv_path.exists():
            logger.info(f"No {xlsx_path} — building from {csv_path} as it stands.")
            return True
        logger.error(f"Neither {xlsx_path} nor {csv_path} exists; nothing to load.")
        return False

    logger.info(f"Converting {xlsx_path} -> {csv_path}")
    try:
        rc = _convert.convert(xlsx_path, csv_path,
                              reshape=_convert.upcoming_reshape)
    except PermissionError:
        logger.error(f"Cannot read {xlsx_path} — it is open in another program.")
        logger.error("Close it in Excel and run this again. Refusing to fall "
                     "back to the CSV, which would silently build the previous "
                     "version of the list.")
        return False
    except Exception as e:
        logger.error(f"Could not convert {xlsx_path}: {e}")
        return False

    if rc != 0:
        logger.error("Conversion reported a problem; not loading.")
        return False
    return True


def load_source(conn, csv_path):
    """Upsert data/upcoming.csv into raw_upcoming_films.

    Same three outcomes per row as the episode load: unchanged (provenance
    advances), edited (a new version row beside the old one), new (inserted).
    No ingested value is ever rewritten.
    """
    cursor = conn.cursor()

    # dtype=str, keep_default_na=False for the same reason 02_load_raw uses
    # them: nothing about the source should be inferred on the way in. An empty
    # cell is '', not the float nan that becomes the string 'nan' downstream.
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    missing = [c for c in SOURCE_COLUMNS if c not in df.columns]
    if missing:
        logger.error(f"{csv_path} is missing column(s): {missing}")
        logger.error("Regenerate it: python scripts/convert_xlsx_to_csv.py "
                     "--source upcoming")
        return None

    load_id = str(uuid.uuid4())
    loaded_at = datetime.utcnow().isoformat()
    cursor.execute(
        "INSERT INTO raw_upcoming_loads "
        "(load_id, source_file, loaded_at, rows_ingested, load_status) "
        "VALUES (?, ?, ?, ?, ?)",
        (load_id, str(csv_path), loaded_at, len(df), 'success'))

    added = edited = unchanged = 0
    seen = set()

    for idx, row in df.iterrows():
        values = [row[c] for c in SOURCE_COLUMNS]
        source_hash = hashlib.md5('|'.join(map(str, values)).encode()).hexdigest()
        key = upcoming_business_key(row['title'], row['year'])

        if key in seen:
            logger.warning(f"Row {idx}: duplicate business key {key!r} in the "
                           f"source file — skipping the second copy")
            continue
        seen.add(key)

        existing = cursor.execute(
            "SELECT raw_upcoming_id FROM raw_upcoming_films "
            "WHERE upcoming_key = ? AND source_hash = ?",
            (key, source_hash)).fetchone()

        if existing:
            cursor.execute(
                "UPDATE raw_upcoming_films SET last_seen_load_id = ?, "
                "last_seen_at = ? WHERE raw_upcoming_id = ?",
                (load_id, loaded_at, existing[0]))
            unchanged += 1
            continue

        is_edit = cursor.execute(
            "SELECT 1 FROM raw_upcoming_films WHERE upcoming_key = ? LIMIT 1",
            (key,)).fetchone() is not None

        cursor.execute(
            "INSERT INTO raw_upcoming_films "
            "(raw_upcoming_id, load_id, title, year, contributor, mention_note, "
            " pitch_tags, upcoming_key, source_hash, source_row_number, "
            " ingested_at, last_seen_load_id, last_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [str(uuid.uuid4()), load_id] + values
            + [key, source_hash, idx, loaded_at, load_id, loaded_at])

        edited += 1 if is_edit else 0
        added += 0 if is_edit else 1

    withdrawn = cursor.execute('''
        SELECT COUNT(*) FROM (
            SELECT upcoming_key FROM raw_upcoming_films
            GROUP BY upcoming_key
            HAVING MAX(CASE WHEN last_seen_load_id = ? THEN 1 ELSE 0 END) = 0
        )
    ''', (load_id,)).fetchone()[0]

    conn.commit()
    logger.info(f"✓ Upserted {len(df)} source rows: {added} new, {edited} edited, "
                f"{unchanged} unchanged")
    if withdrawn:
        logger.info(f"  {withdrawn} film(s) are no longer in the source list — "
                    f"they drop out of raw_upcoming_films_current")
    return load_id


# ── Resolve ───────────────────────────────────────────────────────────────────

def resolve_film(cursor, db_path, title, year, refresh=False):
    """Match one upcoming film to a tmdb_id.

    Returns (tmdb_id, method, confidence, candidates, hit_network). tmdb_id is
    None for every method that starts 'unresolved_'; hit_network tells the caller
    whether to pay the rate-limit sleep, so a fully cached rebuild does not idle
    for a minute doing nothing.
    """
    if year is None:
        # See the module docstring: without a year the scorer's neutral 0.5 is
        # enough to clear the threshold on a title alone, which is how a TV
        # series matches a film that merely shares its name.
        return None, 'unresolved_no_year', None, None, False

    query = strip_annotations(title)
    candidates, hit_network = search_tmdb_cached(
        cursor, db_path, query, year, refresh=refresh)

    if candidates is None:
        return None, 'unresolved_error', None, None, hit_network
    if not candidates:
        return None, 'unresolved_no_match', None, json.dumps([]), hit_network

    scored = []
    for cand in candidates:
        # 04 stores its candidates already flattened: the release year lives on
        # 'year', not on TMDB's raw 'release_date'. Reading the raw key here
        # would hand every candidate a None year and collapse the whole scale
        # onto the neutral 0.5.
        confidence, title_sim, year_score = score_candidate(
            query, year, cand.get('title'), cand.get('year'))
        scored.append({**cand, 'confidence': confidence,
                       'title_similarity': title_sim, 'year_score': year_score})
    # Same tie-break as 04: equal confidence goes to the more popular film.
    scored.sort(key=lambda c: (c['confidence'], c.get('popularity', 0)),
                reverse=True)
    best = scored[0]

    if (best['confidence'] >= CONFIDENCE_THRESHOLD
            and best['title_similarity'] >= TITLE_SIMILARITY_FLOOR):
        method = 'auto_tmdb'
        tmdb_id = best['id']
    else:
        method = 'unresolved_low_confidence'
        tmdb_id = None

    return tmdb_id, method, best['confidence'], json.dumps(scored[:5]), hit_network


def matched_rating(candidates_json, tmdb_id):
    """The winning candidate's TMDB audience score, or None.

    Read back out of the stored candidate list rather than passed down from the
    scorer, so a row rebuilt from an existing candidate_json gets the same value
    a freshly resolved one does.
    """
    if not candidates_json or tmdb_id is None:
        return None
    try:
        candidates = json.loads(candidates_json)
    except (ValueError, TypeError):
        return None
    for cand in candidates:
        if cand.get('id') == tmdb_id:
            return cand.get('vote_average') or None
    return None


def metadata_for(cursor, tmdb_id):
    """The cached TMDB payload for a film, fetching it once if never seen.

    Reads and writes tmdb_metadata_cache — the same rows 09_enrich_metadata
    fills for the episode catalogue — so a film that is both an upcoming request
    and an aired episode is fetched once, by whichever script gets there first.

    Returns (metadata_dict, hit_network).
    """
    # Staleness is still judged on keywords alone, deliberately: an upcoming
    # film shows a cast list but feeds no actor statistic, so refetching the
    # 200-odd of them for cast ids would buy nothing. A film that graduates to
    # a real episode acquires a NULL curated_movies.cast_ids, which puts it in
    # 09's pending set and fills the ids and people rows there.
    cached = meta_cache_get(cursor, tmdb_id)
    if cached is None or cached[5] is None:   # [5] = keywords; see 09's cache_get
        data = fetch_details(tmdb_id)
        if data is None:
            return {}, True
        (genres, runtime, cast_names, cast_ids, plot_summary, poster_url,
         keywords, budget, revenue, people) = parse_details(data)
        # `people` is not a cache column -- it goes to the person dimension, so
        # an upcoming film's cast lands there on the same terms as an aired
        # one's rather than waiting for the film to graduate.
        meta_cache_put(cursor, tmdb_id, genres, runtime, cast_names, cast_ids,
                       plot_summary, poster_url, keywords, budget, revenue)
        if people:
            meta_people_put(cursor, people)
        return {
            'genres': genres, 'runtime_minutes': runtime,
            'cast_names': cast_names, 'plot_summary': plot_summary,
            'poster_url_tmdb': poster_url, 'keywords': keywords,
        }, True

    genres, runtime, cast_names, plot_summary, poster_url, keywords = cached[:6]
    return {
        'genres': genres, 'runtime_minutes': runtime, 'cast_names': cast_names,
        'plot_summary': plot_summary, 'poster_url_tmdb': poster_url,
        'keywords': keywords,
    }, False


# ── Build ─────────────────────────────────────────────────────────────────────

def build(db_path, refresh=False, skip_load=False, skip_convert=False):
    """Load, resolve and rebuild, in that order and in that transaction shape.

    The network pass and the rebuild are deliberately separate phases rather
    than one loop. Two reasons, and the first is not optional:

    04's log_api_call opens its OWN connection to the same file for every TMDB
    call. Holding an open write transaction across the loop -- which is what
    building rows as they resolve does -- means that second connection cannot
    get the lock and the whole run dies with "database is locked" on the first
    search. 04 gets away with the same structure only because it commits after
    every mention.

    The second reason is that it makes the rebuild atomic. DELETE plus 214
    INSERTs in one short transaction at the end means a run interrupted during
    the three-minute network phase leaves the previous list intact, instead of
    emptying the table and then failing to refill it.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    ensure_schema(cursor)
    conn.commit()

    if not skip_load:
        # --skip-load implies skipping the conversion too: there is no point
        # rewriting the CSV for a run that is not going to read it.
        if not skip_convert and not refresh_csv_from_xlsx():
            conn.close()
            return 1
        if not SOURCE_CSV.exists():
            logger.error(f"{SOURCE_CSV} not found.")
            conn.close()
            return 1
        if load_source(conn, SOURCE_CSV) is None:
            conn.close()
            return 1

    rows = cursor.execute(
        "SELECT title, year, contributor, mention_note, pitch_tags, "
        "       source_row_number "
        "FROM raw_upcoming_films_current ORDER BY source_row_number"
    ).fetchall()

    if not rows:
        logger.error("raw_upcoming_films_current is empty — nothing to build.")
        conn.close()
        return 1

    # The catalogue side of the overlap rule, read once. Keyed on tmdb_id and
    # nothing else — see the schema comment for the four title collisions this
    # avoids.
    #
    # `directors` rides along because the catalogue is the ONLY place it exists:
    # it comes from the source sheet's director column, which the upcoming list
    # has no equivalent of, and tmdb_metadata_cache does not carry crew. So it
    # is filled for a film already in the catalogue and NULL for the rest, and
    # the card simply shows its genres without a director rather than a blank
    # slot. Getting it for the other 205 would mean teaching 09's shared cache
    # to store credits.crew, which is a change to the episode path and not
    # worth making for a secondary line.
    aired, catalogue = {}, {}
    for tmdb_id, movie_id, directors in cursor.execute(
            "SELECT tmdb_id, movie_id, directors FROM curated_movies "
            "WHERE tmdb_id IS NOT NULL"):
        aired[tmdb_id] = movie_id
        catalogue[tmdb_id] = directors

    now = datetime.utcnow().isoformat()
    counts = {'auto_tmdb': 0, 'unresolved_no_year': 0, 'unresolved_no_match': 0,
              'unresolved_low_confidence': 0, 'unresolved_error': 0}
    graduated, searches, fetches = [], 0, 0
    built = []

    # ── Phase 1: resolve and enrich. Commits as it goes, so the cache writes
    # land and log_api_call's connection can take the lock between calls.
    for i, (title, year_raw, contributor, mention_note, pitch_tags,
            row_no) in enumerate(rows, 1):
        year = parse_year(year_raw)
        tmdb_id, method, confidence, candidates, hit_network = resolve_film(
            cursor, db_path, title, year, refresh=refresh)
        counts[method] += 1
        if hit_network:
            searches += 1

        meta = {}
        directors = rating = None
        fetched = False
        if tmdb_id is not None:
            meta, fetched = metadata_for(cursor, tmdb_id)
            if fetched:
                fetches += 1
            directors = catalogue.get(tmdb_id)
            # The audience score is already in the search candidate that won —
            # TMDB returns vote_average on /search/movie — so it costs nothing.
            # This is the same field, from the same place, that 06_build_curated
            # writes to curated_movies.rating_tmdb, so the two agree by
            # construction rather than by coincidence.
            rating = matched_rating(candidates, tmdb_id)

        superseded_by = aired.get(tmdb_id) if tmdb_id is not None else None
        if superseded_by:
            graduated.append((title, year_raw))

        built.append(
            (make_upcoming_id(title, year_raw), title, year_raw or None, year,
             contributor or None, mention_note or None, pitch_tags or None,
             tmdb_id, method, confidence, candidates,
             meta.get('genres'), meta.get('keywords'),
             meta.get('runtime_minutes'), meta.get('cast_names'),
             meta.get('plot_summary'), meta.get('poster_url_tmdb'),
             rating, directors,
             superseded_by, now if superseded_by else None,
             row_no, now))

        # Release the lock before sleeping, not after: the sleep is the window
        # log_api_call needs, and holding the transaction through it is exactly
        # the deadlock this phase split exists to avoid.
        conn.commit()
        if hit_network or fetched:
            time.sleep(RATE_LIMIT_SLEEP)
            if searches % 25 == 0 and hit_network:
                logger.info(f"  ... {i}/{len(rows)} ({searches} searches)")

    # ── Phase 2: rebuild, atomically.
    cursor.execute("DELETE FROM curated_upcoming_films")
    cursor.executemany(
        "INSERT INTO curated_upcoming_films "
        "(upcoming_film_id, title, year_raw, year, contributor, "
        " mention_note, pitch_tags, tmdb_id, resolution_method, "
        " confidence_score, candidate_json, genres, keywords, "
        " runtime_minutes, cast_names, plot_summary, poster_url_tmdb, "
        " rating_tmdb, directors, superseded_by_movie_id, superseded_at, "
        " source_row_number, built_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
        "        ?, ?, ?, ?)",
        built)
    conn.commit()

    pending = cursor.execute(
        "SELECT COUNT(*) FROM v_upcoming_pending").fetchone()[0]
    total = cursor.execute(
        "SELECT COUNT(*) FROM curated_upcoming_films").fetchone()[0]
    conn.close()

    logger.info("=" * 60)
    logger.info(f"✓ Built {total} upcoming film(s): {pending} pending, "
                f"{len(graduated)} already made")
    logger.info(f"  resolved: {counts['auto_tmdb']}  "
                f"unresolved: no year {counts['unresolved_no_year']}, "
                f"no match {counts['unresolved_no_match']}, "
                f"low confidence {counts['unresolved_low_confidence']}, "
                f"error {counts['unresolved_error']}")
    logger.info(f"  TMDB calls this run: {searches} search, {fetches} detail")
    if graduated:
        logger.info("  Graduated to real episodes:")
        for title, year_raw in graduated:
            logger.info(f"    · {title} ({year_raw or 'no year'})")
    unresolved = total - counts['auto_tmdb']
    if unresolved:
        logger.info(f"  {unresolved} film(s) carry no tmdb_id and render without "
                    f"metadata; they can never be marked superseded.")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--refresh', action='store_true',
                    help='bypass tmdb_search_cache and re-query TMDB')
    ap.add_argument('--skip-load', action='store_true',
                    help='rebuild the curated table from the raw zone only')
    ap.add_argument('--skip-convert', action='store_true',
                    help='load data/upcoming.csv as it stands, without '
                         'regenerating it from the xlsx')
    args = ap.parse_args()

    db_path = os.getenv('DB_PATH', 'rewatchables.db')
    if not Path(db_path).exists():
        logger.error(f"{db_path} not found — run the main pipeline first.")
        return 1

    return build(db_path, refresh=args.refresh, skip_load=args.skip_load,
                 skip_convert=args.skip_convert)


if __name__ == '__main__':
    sys.exit(main())
