"""
Tests for scripts/migrate_compact_raw_zone.py.

The migration collapses the pre-upsert raw zone — one full copy of the sheet per
ingest run — into version rows: one per (airing, distinct content).

Two properties matter more than the row count:

  * raw_episodes_current must return exactly the same airings afterwards. That
    set is what the app reads, so if it is unchanged nothing downstream moved.
  * staging's foreign keys must still resolve. staging_episodes.raw_episode_id
    points at rows from the newest run, and app.py joins raw_episodes through
    them, so the migration has to keep the NEWEST copy of each duplicate — the
    natural-looking choice of keeping the oldest breaks that join silently.

Re-running the migration is the sharp edge and is tested hardest. Once the
duplicates are gone each (key, hash) has a single occurrence, so the pass that
derives "last run this version was seen in" would find only the FIRST-seen run
and write it over last_seen — dropping every airing not first seen in the newest
run out of the view. The guard against that is an early exit, not a rollback.
"""

import importlib.util
import sqlite3
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "compact_raw",
    Path(__file__).parent.parent / "scripts" / "migrate_compact_raw_zone.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

compact = mod.compact
already_compacted = mod.already_compacted

SCHEMA_DIR = Path(__file__).parent.parent / "sql" / "schemas"

RUNS = [
    ("run-1", "2026-06-23T05:15:28"),
    ("run-2", "2026-06-30T07:44:04"),
    ("run-3", "2026-09-01T07:16:12"),
]

# The pre-upsert layout: every run re-inserted the whole sheet.
# (raw_episode_id, run, ep, title, date, tomatoes_score)
SNAPSHOTS = [
    # Unchanged across all three runs -> one surviving version row.
    ("h1", "run-1", "1", "Heat", "2015-12-22", "0.88"),
    ("h2", "run-2", "1", "Heat", "2015-12-22", "0.88"),
    ("h3", "run-3", "1", "Heat", "2015-12-22", "0.88"),
    # Edited in run-3 -> two surviving version rows, newest is current.
    ("t1", "run-1", "300", "Tombstone", "2022-03-04", "0.72"),
    ("t2", "run-2", "300", "Tombstone", "2022-03-04", "0.72"),
    ("t3", "run-3", "300", "Tombstone", "2022-03-04", "0.79"),
    # Added in run-3.
    ("n1", "run-3", "479", "Aliens", "2026-08-31", "0.93"),
    # Dropped from the sheet after run-2 -> survives as history, not current.
    ("w1", "run-1", "999", "Withdrawn", "2020-01-01", "0.10"),
    ("w2", "run-2", "999", "Withdrawn", "2020-01-01", "0.10"),
]

# What the OLD view returned: rows belonging to the newest ingest run.
BEFORE_CURRENT = {"h3", "t3", "n1"}


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "t.db"
    conn = sqlite3.connect(path)
    for name in ("raw_zone.sql", "staging_zone.sql", "curated_zone.sql"):
        conn.executescript((SCHEMA_DIR / name).read_text(encoding="utf-8"))

    # Reproduce the pre-migration table: no episode_key, no last_seen, and the
    # unique index the upsert relies on not yet creatable.
    conn.execute("DROP INDEX IF EXISTS idx_raw_episodes_version")
    conn.execute("DROP VIEW IF EXISTS raw_episodes_current")
    conn.execute("""
        CREATE VIEW raw_episodes_current AS
        SELECT * FROM raw_episodes WHERE ingest_run_id = (
            SELECT ingest_run_id FROM raw_ingest_runs
            ORDER BY sync_timestamp DESC LIMIT 1)
    """)

    conn.executemany(
        "INSERT INTO raw_ingest_runs (ingest_run_id, source_url, sync_timestamp, "
        "sync_status) VALUES (?, 'x', ?, 'success')", RUNS)
    conn.executemany(
        "INSERT INTO raw_episodes (raw_episode_id, ingest_run_id, ep, title, "
        "date, tomatoes_score, is_film, source_hash) VALUES (?, ?, ?, ?, ?, ?, '1', ?)",
        [(rid, run, ep, t, d, rt, f"{ep}|{d}|{t}|{rt}")
         for rid, run, ep, t, d, rt in SNAPSHOTS])

    # staging points at the newest run's ids, as 03_normalize leaves it.
    conn.executemany(
        "INSERT INTO staging_episodes (staging_episode_id, raw_episode_id, "
        "episode_number) VALUES (?, ?, ?)",
        [("s1", "h3", 1), ("s2", "t3", 300), ("s3", "n1", 479)])
    conn.commit()
    conn.close()
    return path


def rows(db, sql, *args):
    conn = sqlite3.connect(db)
    out = conn.execute(sql, args).fetchall()
    conn.close()
    return out


def current(db):
    return {r[0] for r in rows(db, "SELECT raw_episode_id FROM raw_episodes_current")}


class TestCompaction:
    def test_removes_the_duplicate_snapshots(self, db):
        assert rows(db, "SELECT COUNT(*) FROM raw_episodes")[0][0] == 9
        assert compact(str(db)) == 0
        # 9 snapshot rows -> 4 versions: Heat, Tombstone x2, Aliens, Withdrawn.
        assert rows(db, "SELECT COUNT(*) FROM raw_episodes")[0][0] == 5

    def test_current_airings_are_unchanged(self, db):
        assert current(db) == BEFORE_CURRENT
        compact(str(db))
        assert current(db) == BEFORE_CURRENT

    def test_keeps_the_newest_copy_so_staging_still_resolves(self, db):
        compact(str(db))
        orphans = rows(db, """
            SELECT COUNT(*) FROM staging_episodes se
            WHERE NOT EXISTS (SELECT 1 FROM raw_episodes re
                              WHERE re.raw_episode_id = se.raw_episode_id)
        """)[0][0]
        assert orphans == 0
        # Specifically the newest ids, not the oldest.
        assert {"h3", "t3", "n1"} <= {
            r[0] for r in rows(db, "SELECT raw_episode_id FROM raw_episodes")}

    def test_survivor_is_relabelled_to_the_run_that_first_saw_it(self, db):
        compact(str(db))
        first, last = rows(
            db, "SELECT ingest_run_id, last_seen_ingest_run_id FROM raw_episodes "
                "WHERE raw_episode_id = 'h3'")[0]
        # Heat was introduced by run-1 and still present in run-3.
        assert (first, last) == ("run-1", "run-3")

    def test_an_edit_keeps_both_versions(self, db):
        compact(str(db))
        got = rows(db, "SELECT raw_episode_id, tomatoes_score FROM raw_episodes "
                       "WHERE ep = '300' ORDER BY tomatoes_score")
        assert [r[1] for r in got] == ["0.72", "0.79"]
        assert current(db) & {"t1", "t2", "t3"} == {"t3"}

    def test_a_withdrawn_airing_survives_as_history_but_is_not_current(self, db):
        compact(str(db))
        stored = {r[0] for r in rows(
            db, "SELECT raw_episode_id FROM raw_episodes WHERE ep = '999'")}
        assert len(stored) == 1
        assert not (stored & current(db))

    def test_creates_the_unique_index_the_upsert_needs(self, db):
        compact(str(db))
        conn = sqlite3.connect(db)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO raw_episodes (raw_episode_id, ingest_run_id, "
                "episode_key, source_hash) "
                "SELECT 'x', ingest_run_id, episode_key, source_hash "
                "FROM raw_episodes LIMIT 1")
        conn.close()

    def test_dry_run_writes_nothing(self, db):
        before = rows(db, "SELECT COUNT(*) FROM raw_episodes")[0][0]
        compact(str(db), dry_run=True)
        assert rows(db, "SELECT COUNT(*) FROM raw_episodes")[0][0] == before


class TestReRun:
    """Re-running must be a no-op, not a second compaction pass."""

    def test_second_run_reports_already_compacted(self, db):
        compact(str(db))
        assert already_compacted(sqlite3.connect(db).cursor()) is True
        assert compact(str(db)) == 0

    def test_second_run_does_not_lose_airings(self, db):
        compact(str(db))
        after_first = current(db)
        compact(str(db))
        # The regression this guards: the derive-last_seen pass would find only
        # the first-seen run for each surviving version and overwrite last_seen
        # with it, dropping every airing not first seen in the newest run.
        assert current(db) == after_first == BEFORE_CURRENT

    def test_second_run_does_not_change_row_count(self, db):
        compact(str(db))
        n = rows(db, "SELECT COUNT(*) FROM raw_episodes")[0][0]
        compact(str(db))
        assert rows(db, "SELECT COUNT(*) FROM raw_episodes")[0][0] == n

    def test_a_partially_migrated_zone_is_not_treated_as_done(self, db):
        compact(str(db))
        conn = sqlite3.connect(db)
        conn.execute("UPDATE raw_episodes SET last_seen_ingest_run_id = NULL "
                     "WHERE raw_episode_id = 'h3'")
        conn.commit()
        assert already_compacted(conn.cursor()) is False
        conn.close()
