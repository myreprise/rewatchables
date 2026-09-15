"""
Tests for the raw_episodes_current view in sql/schemas/raw_zone.sql.

The view exists to stop two silent failures that both produced plausible-looking
but wrong numbers:

  * raw_episodes is version history, so an unfiltered read counts an airing once
    per stored version
  * the source sheet mixes M/D/YYYY strings in with ISO timestamps, and pandas
    coerced those to NaT, dropping the most recent episodes from every chart

"Current" means LAST SEEN BY THE MOST RECENT LOAD, not "belongs to the most
recent ingest run". The distinction is the whole point of the upsert: once loads
stop re-inserting the entire sheet, an unchanged row belongs to the run that
first saw it — possibly months ago — and the ingest-run selector would return
only the handful of rows edited in the last load.

The fixture below is built to exercise all four lifecycles at once: a row that
has sat unchanged for three loads, a row edited into a second version, a row
deleted from the sheet, and a revisit that shares an episode number with its
original.
"""

import importlib.util
import sqlite3
from pathlib import Path

import pytest

SCHEMA_DIR = Path(__file__).parent.parent / "sql" / "schemas"
SCHEMA = SCHEMA_DIR / "raw_zone.sql"

spec = importlib.util.spec_from_file_location(
    "normalize", Path(__file__).parent.parent / "scripts" / "03_normalize_and_resolve.py"
)
normalize = importlib.util.module_from_spec(spec)
spec.loader.exec_module(normalize)

# Three loads. run-3 is the most recent, so "current" means last seen by run-3.
RUNS = [
    ("run-1", "2026-06-23T05:15:28", 3, "success"),
    ("run-2", "2026-06-30T07:44:04", 4, "success"),
    ("run-3", "2026-09-01T07:16:12", 6, "success"),
]

# (raw_episode_id, first_seen_run, last_seen_run, ep, title, date, is_film)
EPISODES = [
    # Unchanged since the first load. Belongs to run-1 but is still current —
    # the case the old ingest-run selector got wrong.
    ("a1", "run-1", "run-3", "1", "Heat", "2015-12-22 00:00:00", "1"),
    # A revisit: same ep number, different airing. Both rows must survive.
    ("b1", "run-3", "run-3", "74", "The Insider", "2019-05-23 00:00:00", "1"),
    ("b2", "run-3", "run-3", "74", "The Insider", "1/30/2024", "1"),
    # Single-digit month and day, needing zero-padding.
    ("c1", "run-3", "run-3", "465", "Single White Female", "6/8/2026", "1"),
    # Double-digit month, and a non-film row that callers filter out themselves.
    ("d1", "run-3", "run-3", "470", "Mailbag", "11/28/2023", "0"),
    # Deleted from the sheet: last seen by run-2, never re-seen. Must not leak.
    ("e1", "run-2", "run-2", "999", "Withdrawn", "2020-01-01 00:00:00", "1"),
    # Edited in run-3. Same airing, two stored versions; only the newer one is
    # current, and the superseded one stays as history.
    ("f1", "run-1", "run-2", "300", "Tombstone", "2022-03-04 00:00:00", "1"),
    ("f2", "run-3", "run-3", "300", "Tombstone", "2022-03-04 00:00:00", "1"),
]

CURRENT = {"a1", "b1", "b2", "c1", "d1", "f2"}


def episode_key(ep, date, title):
    return normalize.episode_business_key(ep, date, title)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA.read_text(encoding="utf-8"))
    c.executemany(
        "INSERT INTO raw_ingest_runs "
        "(ingest_run_id, source_url, sync_timestamp, rows_ingested, sync_status) "
        "VALUES (?, 'http://example.test/sheet', ?, ?, ?)",
        RUNS,
    )
    c.executemany(
        "INSERT INTO raw_episodes "
        "(raw_episode_id, ingest_run_id, last_seen_ingest_run_id, ep, title, date, "
        " is_film, episode_key, source_hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(rid, first, last, ep, title, date, is_film,
          episode_key(ep, date, title), rid)
         for rid, first, last, ep, title, date, is_film in EPISODES],
    )
    c.commit()
    yield c
    c.close()


def rows(conn, sql, *args):
    return conn.execute(sql, args).fetchall()


def test_view_returns_one_row_per_current_airing(conn):
    got = {r[0] for r in rows(conn, "SELECT raw_episode_id FROM raw_episodes_current")}
    assert got == CURRENT


def test_an_unchanged_row_stays_current_across_loads(conn):
    """The case the ingest-run selector could not express.

    'Heat' was last written by run-1 and has sat untouched since. Selecting rows
    belonging to the newest run would drop it, and with it every episode that
    simply has not changed recently — which, after the upsert, is nearly all of
    them.
    """
    got = rows(conn, "SELECT raw_episode_id FROM raw_episodes_current WHERE ep = '1'")
    assert [r[0] for r in got] == ["a1"]


def test_episode_deleted_from_the_sheet_does_not_leak_through(conn):
    assert rows(conn, "SELECT 1 FROM raw_episodes_current WHERE ep = '999'") == []


def test_an_edited_airing_shows_only_its_newest_version(conn):
    got = rows(conn, "SELECT raw_episode_id FROM raw_episodes_current WHERE ep = '300'")
    assert [r[0] for r in got] == ["f2"]


def test_the_superseded_version_is_kept_as_history(conn):
    """The view hides the old version; the table still has it."""
    got = rows(conn, "SELECT raw_episode_id FROM raw_episodes WHERE ep = '300'")
    assert {r[0] for r in got} == {"f1", "f2"}


def test_revisits_survive_deduplication(conn):
    """A revisit reuses the episode number, so `ep` is not a unique key.

    Collapsing on `ep` is the obvious-looking fix and would delete exactly the
    rows the Revisits analysis is built on.
    """
    got = rows(
        conn,
        "SELECT episode_date FROM raw_episodes_current WHERE ep = '74' "
        "ORDER BY episode_date",
    )
    assert [r[0] for r in got] == ["2019-05-23", "2024-01-30"]


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2015-12-22 00:00:00", "2015-12-22"),  # ISO timestamp, truncated
        ("1/30/2024", "2024-01-30"),            # single-digit month
        ("6/8/2026", "2026-06-08"),             # single-digit month and day
        ("11/28/2023", "2023-11-28"),           # double-digit both
    ],
)
def test_episode_date_normalises_the_source_formats(conn, raw, expected):
    got = rows(
        conn, "SELECT episode_date FROM raw_episodes_current WHERE date = ?", raw
    )
    assert got and got[0][0] == expected


def test_every_episode_date_is_a_valid_date(conn):
    """date() returns NULL for anything SQLite cannot read as a date."""
    bad = rows(
        conn,
        "SELECT raw_episode_id, date, episode_date FROM raw_episodes_current "
        "WHERE date IS NOT NULL AND date(episode_date) IS NULL",
    )
    assert bad == []


def test_raw_date_column_is_passed_through_untouched(conn):
    """Raw-zone fidelity: the view adds a column, it does not rewrite one."""
    got = rows(conn, "SELECT date FROM raw_episodes_current WHERE raw_episode_id = 'c1'")
    assert got[0][0] == "6/8/2026"


def test_null_date_does_not_break_the_view(conn):
    conn.execute(
        "INSERT INTO raw_episodes "
        "(raw_episode_id, ingest_run_id, last_seen_ingest_run_id, ep, title, date, "
        " is_film, source_hash) "
        "VALUES ('g1', 'run-3', 'run-3', '500', 'No date', NULL, '1', 'g1')"
    )
    got = rows(
        conn, "SELECT episode_date FROM raw_episodes_current WHERE raw_episode_id = 'g1'"
    )
    assert got[0][0] is None


def test_staging_is_built_from_exactly_the_view(conn, tmp_path):
    """03_normalize must stage the same airings the view calls current.

    This used to be enforced by comparing two hand-written copies of the same
    selector, one in the view and one in 03, with a comment on each warning that
    they had to be changed together. 03 now reads the view, so the check is that
    it actually does: run it and compare what landed in staging.
    """
    db = tmp_path / "t.db"
    disk = sqlite3.connect(db)
    for name in ("raw_zone.sql", "staging_zone.sql", "curated_zone.sql"):
        disk.executescript((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    disk.executemany(
        "INSERT INTO raw_ingest_runs "
        "(ingest_run_id, source_url, sync_timestamp, rows_ingested, sync_status) "
        "VALUES (?, 'x', ?, ?, ?)", RUNS)
    disk.executemany(
        "INSERT INTO raw_episodes "
        "(raw_episode_id, ingest_run_id, last_seen_ingest_run_id, ep, title, date, "
        " is_film, episode_key, source_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(rid, first, last, ep, title, date, is_film,
          episode_key(ep, date, title), rid)
         for rid, first, last, ep, title, date, is_film in EPISODES])
    disk.commit()
    disk.close()

    normalize.process_raw_to_staging(str(db))

    disk = sqlite3.connect(db)
    staged = {r[0] for r in disk.execute(
        "SELECT raw_episode_id FROM staging_episodes")}
    viewed = {r[0] for r in disk.execute(
        "SELECT raw_episode_id FROM raw_episodes_current")}
    disk.close()

    assert staged == viewed == CURRENT
