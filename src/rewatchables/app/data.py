"""Loading the database into the frames every section reads.

Each loader is cached and keyed on the database's modification time as well as
its ttl, so a pipeline run shows up on the next rerun rather than up to five
minutes later. They are separate functions, not one, so that a database built
before a table existed still loads: see load_people and load_upcoming.
"""

import json
import sqlite3

import pandas as pd
import streamlit as st

from rewatchables import config
from views import (
    CPI_PROVISIONAL_FROM, ROOM, multiple, parse_tags, person_name, real_usd,
    sort_title,
)

DB_PATH = config.db_path()


def stamp():
    """The database's modification time, as the loaders' cache key.

    Read on every rerun: it is one stat(), and it is what makes a rebuilt
    database a cache miss instead of a five-minute wait.
    """
    return DB_PATH.stat().st_mtime if DB_PATH.exists() else 0.0


@st.cache_data(ttl=300)
def load_data(db_stamp=None):
    # db_stamp is never read: it is part of the cache key, so a rebuilt
    # database is a cache miss. Callers pass DB_STAMP.
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Core movies
    movies = pd.read_sql("""
        SELECT movie_id, tmdb_id, title, year,
               directors, genres, keywords, runtime_minutes,
               rating_tmdb, popularity_tmdb, cast_names,
               budget_tmdb, revenue_tmdb,
               plot_summary, plot_summary_wiki, plot_summary_wiki_words,
               poster_url_tmdb,
               wikipedia_url, wikidata_qid, enriched_at,
               first_episode_date, last_episode_date,
               total_episodes_featured, revisit_count,
               canonical_key_confidence
        FROM curated_movies
        ORDER BY year
    """, conn, parse_dates=["first_episode_date", "last_episode_date"])

    # `revisited` is curated ground truth from the source sheet, carried through
    # raw -> staging -> curated. Prefer it over the derived revisit_count, which
    # is only a cross-check. Selected separately so a database built before the
    # column existed still loads, falling back to the derived value.
    movie_cols = {r[1] for r in conn.execute("PRAGMA table_info(curated_movies)")}
    if "revisited_flag" in movie_cols:
        flags = pd.read_sql(
            "SELECT movie_id, revisited_flag FROM curated_movies", conn)
        movies = movies.merge(flags, on="movie_id", how="left")
        # A film the sheet never flagged falls back to the derived count.
        movies["revisited_flag"] = (
            movies["revisited_flag"]
            .fillna((movies["revisit_count"] > 0).astype(int))
            .astype(int)
        )
    else:
        movies["revisited_flag"] = (movies["revisit_count"] > 0).astype(int)

    # Episodes. raw_episodes_current pins to the newest ingest snapshot — the
    # raw table keeps one full copy per run — and exposes episode_date with the
    # source sheet's M/D/YYYY values normalised to ISO. Both traps are documented
    # in sql/schemas/raw_zone.sql; read the view, not the table.
    episodes = pd.read_sql("""
        SELECT raw_episode_id, ep, title, episode_date AS date,
               host, guest1, guest2, guest3, guest4,
               ebert, tomatoes_score, cruise_hanks,
               rating, ebert_stars, notes
        FROM raw_episodes_current
        WHERE is_film = 1
        ORDER BY episode_date
    """, conn, parse_dates=["date"])

    # Canary: the view should leave nothing unparseable, but a new date format
    # appearing upstream must not silently vanish from the time series again.
    unparsed = int(episodes["date"].isna().sum())
    if unparsed:
        st.warning(
            f"{unparsed} episode dates could not be parsed and are excluded "
            "from the time-based charts."
        )

    # Episode-movie links (for join). guest4 and notes are carried for the film
    # dossier, which shows the full room and the sheet's episode annotations.
    # raw_episode_id is the only per-airing key: the sheet reuses an episode
    # number when a film is revisited, so Hosts & Guests counts rooms by this.
    links = pd.read_sql("""
        SELECT re.raw_episode_id,
               cem.movie_id, cem.episode_number, cem.episode_date,
               cem.is_revisit, cem.revisit_sequence, cem.revisit_type,
               re.host, re.guest1, re.guest2, re.guest3, re.guest4,
               re.ebert, re.tomatoes_score, re.cruise_hanks,
               re.rating, re.ebert_stars, re.notes
        FROM curated_episode_movies cem
        JOIN staging_episodes se ON se.staging_episode_id = cem.staging_episode_id
        JOIN raw_episodes re ON re.raw_episode_id = se.raw_episode_id
    """, conn, parse_dates=["episode_date"])

    # CMU box office, kept only as a cross-check against TMDB on the provenance
    # side. It is NOT what the app charts: CMU's Freebase snapshot froze in
    # 2012, so its coverage runs ~92% before 2010 and 0% after 2019, and a
    # decade trend drawn from it measures the snapshot date rather than the
    # films. TMDB covers 447 of 454 evenly across every decade. Where both know
    # a film they agree (median ratio 1.000, 341 of 376 within 10%); the
    # outliers are CMU recording a domestic gross against TMDB's worldwide one.
    box_office = pd.read_sql(
        "SELECT movie_id, box_office_revenue FROM v_movie_cmu", conn)

    # Cruise vs. Hanks verdicts. Episode-grained -- the verdict belongs to the
    # episode, not the film, so a revisit can carry a different verdict. The view
    # joins the film on episode_number rather than raw_episode_id; see the comment
    # block on v_cruise_hanks in sql/schemas/curated_zone.sql for why the id path
    # silently returns zero rows.
    ch = pd.read_sql("""
        SELECT episode_number, episode_date, verdict,
               host, guest1, guest2, guest3, guest4,
               tomatoes_score, ebert_stars,
               movie_id, movie_title, movie_year, movie_decade,
               genres, directors, runtime_minutes, rating_tmdb, poster_url_tmdb,
               is_revisit
        FROM v_cruise_hanks
        ORDER BY episode_number
    """, conn, parse_dates=["episode_date"])

    conn.close()

    # Parse JSON columns
    for col in ["directors", "genres", "keywords", "cast_names"]:
        movies[col] = movies[col].apply(
            lambda x: json.loads(x) if isinstance(x, str) and x.startswith("[") else []
        )

    # Derive director_primary / genre_primary
    movies["director_primary"] = movies["directors"].apply(
        lambda x: x[0] if x else "Unknown"
    )
    movies["genre_list"] = movies["genres"]  # alias
    movies["genre_primary"] = movies["genres"].apply(
        lambda x: x[0] if x else "Unknown"
    )

    # Alphabetical sort key: 'The Blind Side' -> 'Blind Side, The'. Derived here
    # rather than at the point of sorting so every frame downstream of movies_df
    # files a film in the same place.
    movies["sort_title"] = movies["title"].apply(sort_title)

    # Decade
    movies["decade"] = (movies["year"] // 10 * 10).astype("Int64")

    # Box office joins one-to-one; films missing from CMU keep NaN.
    movies = movies.merge(
        box_office.drop_duplicates("movie_id"), on="movie_id", how="left")

    # Money, in CPI_BASE_YEAR dollars. Derived once here rather than per chart:
    # every user-facing figure has to be the adjusted one, and a single
    # unadjusted series slipping into a decade comparison is exactly the bug
    # that makes inflation look like a change in taste.
    movies["revenue_real"] = [
        real_usd(r, y) for r, y in zip(movies["revenue_tmdb"], movies["year"])]
    movies["budget_real"] = [
        real_usd(b, y) for b, y in zip(movies["budget_tmdb"], movies["year"])]
    # The ratio is scale-free, so it takes the nominal pair — adjusting both
    # sides by the same year's CPI cancels out and only adds rounding.
    movies["multiple"] = [
        multiple(r, b)
        for r, b in zip(movies["revenue_tmdb"], movies["budget_tmdb"])]
    # A film still in release has neither a settled gross nor, often, a real
    # budget: TMDB carries a $750K placeholder for a 2026 title that has taken
    # $506M. Flagged rather than dropped, and kept out of the leaderboards.
    movies["money_provisional"] = movies["year"] >= CPI_PROVISIONAL_FROM

    # Parse numeric ratings in episodes
    episodes["tomatoes_num"] = pd.to_numeric(
        episodes["tomatoes_score"], errors="coerce"
    )
    episodes["ebert_num"] = pd.to_numeric(
        episodes["ebert_stars"], errors="coerce"
    )
    episodes["rating_num"] = pd.to_numeric(
        episodes["rating"], errors="coerce"
    )

    # Same for links
    links["tomatoes_num"] = pd.to_numeric(links["tomatoes_score"], errors="coerce")
    links["ebert_num"] = pd.to_numeric(links["ebert_stars"], errors="coerce")
    links["rating_num"] = pd.to_numeric(links["rating"], errors="coerce")

    # Merge movies + links for enriched table
    merged = links.merge(
        movies[[
            "movie_id", "title", "year", "decade", "directors",
            "director_primary", "genres", "genre_primary", "runtime_minutes",
            "rating_tmdb", "cast_names", "poster_url_tmdb",
            "total_episodes_featured", "revisit_count"
        ]],
        on="movie_id", how="left"
    )

    # Same JSON columns on the Cruise/Hanks frame, plus numeric ratings.
    for col in ["directors", "genres"]:
        ch[col] = ch[col].apply(
            lambda x: json.loads(x) if isinstance(x, str) and x.startswith("[") else []
        )
    ch["tomatoes_num"] = pd.to_numeric(ch["tomatoes_score"], errors="coerce")
    ch["ebert_num"] = pd.to_numeric(ch["ebert_stars"], errors="coerce")

    # Names are normalised once, here, so every section that reads the room --
    # the dossier, the overview, Cruise vs. Hanks, Hosts & Guests -- counts
    # the same people. The sheet is the source of truth and writes "Mallory
    # Rubin*" on one episode; see person_name().
    for frame in (episodes, links, merged, ch):
        for chair in ROOM:
            frame[chair] = frame[chair].map(person_name)

    return movies, episodes, links, merged, ch




@st.cache_data(ttl=300)
def load_people(db_stamp=None):
    """The people dimension: one row per credited person, with their gender.

    Cached separately from load_data() for the same reason load_upcoming() is:
    a database built before 09_enrich_metadata collected person ids has no
    curated_people table, and folding this query into load_data() would take
    every section down with it rather than just the gender split. An empty
    frame degrades the Actors section to the ungendered view it had before.
    """
    if not DB_PATH.exists():
        return pd.DataFrame(columns=["name", "gender"])

    conn = sqlite3.connect(DB_PATH)
    have = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "curated_people" not in have:
        conn.close()
        return pd.DataFrame(columns=["name", "gender"])
    people = pd.read_sql(
        "SELECT name, gender FROM curated_people WHERE name IS NOT NULL", conn)
    conn.close()
    return people


# The genders the app charts, in the order it charts them, plus their labels.
# 'unknown' is a real category and is never folded into either of the other
# two: TMDB leaves gender unset on about 1% of billed credits, and quietly
# assigning those would overstate whichever side received them.
GENDERS = ("M", "F", "NB", "unknown")
GENDER_LABEL = {"M": "Men", "F": "Women", "NB": "Non-binary",
                "unknown": "Not recorded"}


def gender_from_people(people):
    """name -> gender, for the names the app groups actor statistics by.

    Keyed on name rather than on tmdb_person_id because every actor statistic
    in the app groups by name -- one bar is one name. Where two different
    people share a name and TMDB records different genders for them, that bar
    is genuinely two people and the honest answer is 'unknown', not whichever
    row the lookup reached first. curated_movies.cast_ids exists so a future
    person-grained version of these panels can drop the name key entirely.
    """
    if people.empty:
        return {}
    rows = people.copy()
    rows["gender"] = rows["gender"].fillna("unknown")
    agreed = rows.groupby("name")["gender"].nunique()
    first = rows.drop_duplicates("name").set_index("name")["gender"]
    return {name: (first[name] if agreed[name] == 1 else "unknown")
            for name in agreed.index}




@st.cache_data(ttl=300)
def load_upcoming(db_stamp=None):
    """Films listeners have put forward for future episodes.

    Cached separately from load_data() rather than folded into it, for two
    reasons. It is a genuinely independent source — a different file, its own
    raw and curated tables, nothing joined to an episode — and a database built
    before step 13 existed has none of those tables. Returning empty frames
    there keeps every other section rendering; adding the query to load_data()
    would take the whole app down with it.

    Returns (pending, graduated). `pending` is the films still waiting: the
    v_upcoming_pending view already excludes anything that has become a real
    episode, so no caller has to remember to filter.
    """
    empty = (pd.DataFrame(), pd.DataFrame())
    if not DB_PATH.exists():
        return empty

    conn = sqlite3.connect(DB_PATH)
    have = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
    if not {"v_upcoming_pending", "v_upcoming_graduated"} <= have:
        conn.close()
        return empty

    pending = pd.read_sql("""
        SELECT upcoming_film_id, title, year_raw, year, contributor,
               mention_note, pitch_tags, tmdb_id, resolution_method,
               genres, keywords, runtime_minutes, cast_names, plot_summary,
               poster_url_tmdb, rating_tmdb, directors, source_row_number
        FROM v_upcoming_pending
        ORDER BY source_row_number
    """, conn)

    graduated = pd.read_sql("""
        SELECT upcoming_film_id, requested_title, year_raw, contributor,
               mention_note, pitch_tags, movie_id, movie_title, movie_year,
               poster_url_tmdb, first_episode_date, total_episodes_featured
        FROM v_upcoming_graduated
        ORDER BY first_episode_date
    """, conn, parse_dates=["first_episode_date"])
    conn.close()

    if pending.empty:
        return pending, graduated

    for col in ["genres", "keywords", "cast_names", "directors"]:
        pending[col] = pending[col].apply(
            lambda x: json.loads(x) if isinstance(x, str) and x.startswith("[") else []
        )
    pending["tags"] = pending["pitch_tags"].apply(parse_tags)
    pending["sort_title"] = pending["title"].apply(sort_title)
    # year_raw is the source text and holds two ranges and a blank; `year` is
    # the parsed value and is NULL for exactly those rows. Decade is derived
    # from the parsed one, so an unresolvable row lands in "Unknown" rather
    # than in 1984 because its range happened to start there.
    pending["decade"] = (pending["year"] // 10 * 10).astype("Int64")
    pending["resolved"] = pending["resolution_method"] == "auto_tmdb"
    return pending, graduated
