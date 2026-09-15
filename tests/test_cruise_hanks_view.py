"""
Tests for the v_cruise_hanks view in sql/schemas/curated_zone.sql.

The view backs the Cruise vs. Hanks section of the Streamlit app. Two failure
modes are worth pinning down, because both produce a plausible-looking result
rather than an error:

  * The film must be joined on curated_episode_movies.episode_number, NOT via
    staging_episodes.raw_episode_id. raw_episodes is version history and
    raw_episodes_current returns only the version last seen in the source, while
    staging still points at the raw_episode_ids it was built from. An airing
    edited since then has a newer version row, and the raw_episode_id path joins
    to nothing at all.

  * The grain is one row per verdict EPISODE. A film can be revisited, so a
    fan-out here would silently double-count verdicts on the scoreboard.
"""

import sqlite3
from pathlib import Path

import pytest

SCHEMAS = Path(__file__).parent.parent / "sql" / "schemas"
RAW_SCHEMA = SCHEMAS / "raw_zone.sql"
STAGING_SCHEMA = SCHEMAS / "staging_zone.sql"
CURATED_SCHEMA = SCHEMAS / "curated_zone.sql"

# Two loads. The o* rows are versions that have been superseded — the sheet was
# edited between loads — and the n* rows are what the source holds now. staging
# deliberately still references the o* ids, reproducing the drift between
# raw_episodes_current and staging that the view has to route around.
RUNS = [
    ("run-old", "2026-09-01T07:16:12", 5, "success"),
    ("run-new", "2026-09-01T12:34:06", 5, "success"),
]

# (raw_episode_id, first_seen, last_seen, ep, title, date, cruise_hanks)
# last_seen = run-new is what makes a row current; the o* rows stopped being
# re-seen when their newer versions replaced them.
EPISODES = [
    ("o1", "run-old", "run-old", "350", "Manchester By The Sea", "3/26/2024", "Hanks"),
    ("o2", "run-old", "run-old", "351", "Shot Caller", "4/2/2024", "Cruise"),
    ("o3", "run-old", "run-old", "352", "Domestic Disturbance", "6/22/2026", "Tie"),
    ("o4", "run-old", "run-old", "353", "Mailbag", "7/1/2026", None),
    ("o5", "run-old", "run-old", "354", "The Insider", "7/8/2026", "Cruise"),
    # Current versions: same episodes, and one verdict revised from Cruise.
    ("n1", "run-new", "run-new", "350", "Manchester By The Sea", "3/26/2024", "Hanks"),
    ("n2", "run-new", "run-new", "351", "Shot Caller", "4/2/2024", "Cruise"),
    ("n3", "run-new", "run-new", "352", "Domestic Disturbance", "6/22/2026", "Tie"),
    ("n4", "run-new", "run-new", "353", "Mailbag", "7/1/2026", None),
    ("n5", "run-new", "run-new", "354", "The Insider", "7/8/2026", "Hanks"),
]

MOVIES = [
    ("m-manchester", 1, "Manchester by the Sea", 2016, '["Drama"]', 137),
    ("m-shotcaller", 2, "Shot Caller", 2017, '["Crime", "Thriller"]', 121),
    ("m-domestic", 3, "Domestic Disturbance", 2001, '["Thriller"]', 89),
    ("m-insider", 4, "The Insider", 1999, '["Drama", "Thriller"]', 157),
]

# (episode_movie_id, staging_episode_id, movie_id, ep_number, date, is_revisit, seq)
LINKS = [
    ("em1", "s1", "m-manchester", 350, "2024-03-26", 0, 1),
    ("em2", "s2", "m-shotcaller", 351, "2024-04-02", 0, 1),
    ("em3", "s3", "m-domestic", 352, "2026-06-22", 0, 1),
    # ep 354 is a revisit of a film first covered long before the segment began.
    ("em4", "s5", "m-insider", 354, "2026-07-08", 1, 2),
]


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(RAW_SCHEMA.read_text(encoding="utf-8"))
    c.executescript(STAGING_SCHEMA.read_text(encoding="utf-8"))
    c.executescript(CURATED_SCHEMA.read_text(encoding="utf-8"))

    c.executemany(
        "INSERT INTO raw_ingest_runs "
        "(ingest_run_id, source_url, sync_timestamp, rows_ingested, sync_status) "
        "VALUES (?, 'http://example.test/sheet', ?, ?, ?)",
        RUNS,
    )
    c.executemany(
        "INSERT INTO raw_episodes "
        "(raw_episode_id, ingest_run_id, last_seen_ingest_run_id, ep, title, date, "
        " cruise_hanks, is_film, source_hash) VALUES (?, ?, ?, ?, ?, ?, ?, '1', ?)",
        [(rid, first, last, ep, t, d, ch, rid)
         for rid, first, last, ep, t, d, ch in EPISODES],
    )
    # staging points at the OLDER run -- this is the drift the view routes around.
    c.executemany(
        "INSERT INTO staging_episodes "
        "(staging_episode_id, raw_episode_id, episode_number, episode_date) "
        "VALUES (?, ?, ?, ?)",
        [("s1", "o1", 350, "2024-03-26"), ("s2", "o2", 351, "2024-04-02"),
         ("s3", "o3", 352, "2026-06-22"), ("s4", "o4", 353, "2026-07-01"),
         ("s5", "o5", 354, "2026-07-08")],
    )
    c.executemany(
        "INSERT INTO curated_movies "
        "(movie_id, tmdb_id, title, year, genres, runtime_minutes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        MOVIES,
    )
    c.executemany(
        "INSERT INTO curated_episode_movies "
        "(episode_movie_id, staging_episode_id, movie_id, episode_number, "
        " episode_date, mention_order, is_revisit, revisit_sequence) "
        "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
        LINKS,
    )
    c.commit()
    yield c
    c.close()


def rows(conn, sql, *args):
    return conn.execute(sql, args).fetchall()


def test_only_verdict_episodes_are_returned(conn):
    got = {r[0] for r in rows(conn, "SELECT episode_number FROM v_cruise_hanks")}
    assert got == {350, 351, 352, 354}


def test_episode_without_a_verdict_is_excluded(conn):
    assert rows(conn, "SELECT 1 FROM v_cruise_hanks WHERE episode_number = 353") == []


def test_verdict_comes_from_the_newest_snapshot(conn):
    """ep 354 was revised from Cruise to Hanks in run-new.

    Reading the raw table unfiltered would return both, and reading the older
    run would return the superseded verdict.
    """
    got = rows(conn, "SELECT verdict FROM v_cruise_hanks WHERE episode_number = 354")
    assert got == [("Hanks",)]


def test_grain_is_one_row_per_episode(conn):
    """A fan-out here would double-count verdicts on the scoreboard."""
    total, distinct = rows(
        conn,
        "SELECT COUNT(*), COUNT(DISTINCT episode_number) FROM v_cruise_hanks",
    )[0]
    assert total == distinct == 4


def test_film_is_joined_despite_staging_pointing_at_the_older_run(conn):
    """The regression this view exists to prevent.

    staging_episodes references run-old's raw_episode_ids while
    raw_episodes_current serves run-new's, so joining the two on
    raw_episode_id yields zero rows. episode_number is snapshot-stable.
    """
    got = rows(
        conn,
        "SELECT episode_number, movie_title, movie_year FROM v_cruise_hanks "
        "ORDER BY episode_number",
    )
    assert got == [
        (350, "Manchester by the Sea", 2016),
        (351, "Shot Caller", 2017),
        (352, "Domestic Disturbance", 2001),
        (354, "The Insider", 1999),
    ]
    assert all(r[1] is not None for r in got)


def test_revisit_flag_is_carried_through(conn):
    got = rows(
        conn,
        "SELECT is_revisit, revisit_sequence FROM v_cruise_hanks "
        "WHERE episode_number = 354",
    )
    assert got == [(1, 2)]


def test_decade_is_derived_from_the_film_not_the_episode(conn):
    """Domestic Disturbance aired in 2026 but is a 2001 film."""
    got = rows(
        conn, "SELECT movie_decade FROM v_cruise_hanks WHERE episode_number = 352"
    )
    assert got == [(2000,)]


@pytest.mark.parametrize("verdict", ["Cruise", "Hanks", "Tie"])
def test_each_verdict_value_survives(conn, verdict):
    got = rows(
        conn, "SELECT COUNT(*) FROM v_cruise_hanks WHERE verdict = ?", verdict
    )
    assert got[0][0] >= 1


def test_film_metadata_is_exposed_for_the_genre_cut(conn):
    """The genre lean is the section's one real finding, so the JSON must arrive."""
    got = rows(
        conn, "SELECT genres, runtime_minutes FROM v_cruise_hanks "
        "WHERE episode_number = 351"
    )
    assert got == [('["Crime", "Thriller"]', 121)]
