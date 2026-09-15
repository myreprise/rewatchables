"""
Tests for the raw-zone upsert in 02_load_raw.py and the rebuilt
raw_episodes_current view.

Before the upsert, every load re-inserted the whole sheet: six loads left 2,913
rows for 489 real airings. The load now recognises a row it has already stored
and only appends when the content actually changed.

Three cases carry the design, and the view has to get all three right:

  unchanged  re-seen, provenance advances, still current
  edited     new version row appended, old version stops being current
  deleted    never re-seen, falls out of the view on its own

The deletion case is the one that constrains the design. \"Current\" cannot mean
\"belongs to the newest ingest run\" any more -- once loads are upserts, an
unchanged row belongs to the run that first saw it, possibly months ago.
"""

import importlib.util
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

spec = importlib.util.spec_from_file_location(
    "load_raw", Path(__file__).parent.parent / "scripts" / "02_load_raw.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

load_source_to_raw = mod.load_source_to_raw
read_source        = mod.read_source
assert_compacted = mod.assert_compacted

SCHEMA_DIR = Path(__file__).parent.parent / "sql" / "schemas"

COLUMNS = ["ep", "title", "date", "host", "year", "director", "is_film",
           "tomatoes_score", "revisited"]


def sheet(*rows):
    """Build a source frame from (ep, title, date, tomatoes_score) tuples."""
    return pd.DataFrame(
        [{"ep": ep, "title": title, "date": date, "host": "Bill Simmons",
          "year": 1995, "director": "Michael Mann", "is_film": 1,
          "tomatoes_score": rt, "revisited": 0}
         for ep, title, date, rt in rows],
        columns=COLUMNS)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "t.db"
    conn = sqlite3.connect(path)
    for name in ("raw_zone.sql", "staging_zone.sql", "curated_zone.sql"):
        conn.executescript((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    conn.close()
    return path


def load(db, frame, tmp_path):
    csv = tmp_path / "episodes.csv"
    frame.to_csv(csv, index=False, lineterminator="\n")
    load_source_to_raw(str(csv), str(db))


def rows(db, sql, *args):
    conn = sqlite3.connect(db)
    out = conn.execute(sql, args).fetchall()
    conn.close()
    return out


def current(db):
    """(ep, title, tomatoes_score) of every airing the view calls current."""
    return sorted(rows(db, "SELECT ep, title, tomatoes_score "
                          "FROM raw_episodes_current"))


def stored(db):
    return rows(db, "SELECT COUNT(*) FROM raw_episodes")[0][0]


HEAT = ("1", "Heat", "2015-12-22", "0.88")
INSIDER = ("74", "The Insider", "2019-05-23", "0.96")


class TestUnchangedReload:
    def test_reloading_the_same_sheet_inserts_nothing(self, db, tmp_path):
        s = sheet(HEAT, INSIDER)
        load(db, s, tmp_path)
        assert stored(db) == 2

        for _ in range(4):
            load(db, s, tmp_path)

        # The old behaviour would leave 10 rows here, one snapshot per load.
        assert stored(db) == 2
        assert len(current(db)) == 2

    def test_last_seen_advances_on_an_unchanged_row(self, db, tmp_path):
        s = sheet(HEAT)
        load(db, s, tmp_path)
        first = rows(db, "SELECT ingest_run_id, last_seen_ingest_run_id "
                         "FROM raw_episodes")[0]
        assert first[0] == first[1]

        load(db, s, tmp_path)
        second = rows(db, "SELECT ingest_run_id, last_seen_ingest_run_id "
                          "FROM raw_episodes")[0]
        # First-seen is pinned to the original load; last-seen moved on.
        assert second[0] == first[0]
        assert second[1] != first[1]

    def test_the_row_stays_current_across_loads(self, db, tmp_path):
        s = sheet(HEAT)
        load(db, s, tmp_path)
        load(db, s, tmp_path)
        # The point of the last_seen selector: a row nobody touched is still
        # current even though it belongs to an older ingest run.
        assert current(db) == [("1", "Heat", "0.88")]


class TestNewRow:
    def test_appending_an_episode_stores_only_that_episode(self, db, tmp_path):
        load(db, sheet(HEAT), tmp_path)
        load(db, sheet(HEAT, INSIDER), tmp_path)
        assert stored(db) == 2
        assert len(current(db)) == 2

    def test_a_revisit_reusing_an_episode_number_is_a_separate_airing(
            self, db, tmp_path):
        # The podcast reuses the episode number when it revisits a film, so the
        # business key has to be more than `ep` or the revisit overwrites the
        # original -- the exact rows the Revisits analysis depends on.
        original = ("68", "American Pie", "2019-08-01", "0.61")
        revisit = ("68", "American Pie", "2023-07-14", "0.61")
        load(db, sheet(original, revisit), tmp_path)
        assert stored(db) == 2
        assert len(current(db)) == 2


class TestEditedRow:
    def test_an_edit_appends_a_version_and_supersedes_the_old_one(
            self, db, tmp_path):
        load(db, sheet(HEAT), tmp_path)
        load(db, sheet(("1", "Heat", "2015-12-22", "0.94")), tmp_path)

        # History kept...
        assert stored(db) == 2
        # ...but only the new version is current.
        assert current(db) == [("1", "Heat", "0.94")]

    def test_editing_the_business_key_reads_as_a_different_airing(
            self, db, tmp_path):
        # Correcting a typo'd air date is indistinguishable from a new airing,
        # since the date is part of the identity. Both rows persist; only the
        # one in the current sheet is current.
        load(db, sheet(HEAT), tmp_path)
        load(db, sheet(("1", "Heat", "2015-12-23", "0.88")), tmp_path)
        assert stored(db) == 2
        assert len(current(db)) == 1

    def test_date_format_change_alone_is_not_an_edit_of_the_key(
            self, db, tmp_path):
        # The sheet mixes M/D/YYYY with ISO. Both must reduce to the same key,
        # or reformatting a cell would fork the airing in two.
        load(db, sheet(("1", "Heat", "2015-12-22", "0.88")), tmp_path)
        keys_before = rows(db, "SELECT episode_key FROM raw_episodes")
        load(db, sheet(("1", "Heat", "12/22/2015", "0.88")), tmp_path)
        keys_after = {r[0] for r in rows(db, "SELECT episode_key FROM raw_episodes")}
        assert len(keys_after) == 1
        assert keys_before[0][0] in keys_after


class TestDeletedRow:
    def test_a_row_removed_from_the_sheet_drops_out_of_current(
            self, db, tmp_path):
        load(db, sheet(HEAT, INSIDER), tmp_path)
        assert len(current(db)) == 2

        load(db, sheet(HEAT), tmp_path)
        # History keeps it; the view does not.
        assert stored(db) == 2
        assert current(db) == [("1", "Heat", "0.88")]

    def test_a_restored_row_becomes_current_again_without_a_new_version(
            self, db, tmp_path):
        load(db, sheet(HEAT, INSIDER), tmp_path)
        load(db, sheet(HEAT), tmp_path)
        load(db, sheet(HEAT, INSIDER), tmp_path)
        # Re-seen, not re-inserted: the stored row is unchanged, so it is
        # recognised rather than duplicated.
        assert stored(db) == 2
        assert len(current(db)) == 2


class TestGuards:
    def test_duplicate_business_keys_in_one_sheet_are_reported_not_merged(
            self, db, tmp_path, caplog):
        dupe = sheet(HEAT, ("1", "Heat", "2015-12-22", "0.99"))
        with caplog.at_level("WARNING"):
            load(db, dupe, tmp_path)
        # Second copy skipped rather than silently upserted over the first.
        assert stored(db) == 1
        assert any("duplicate business key" in r.message for r in caplog.records)

    def test_assert_compacted_rejects_a_pre_upsert_database(self, db, tmp_path):
        load(db, sheet(HEAT), tmp_path)
        conn = sqlite3.connect(db)
        # Simulate the old snapshot layout: the same row stored once per ingest
        # run. The pre-existing UNIQUE(ingest_run_id, source_hash) permitted
        # exactly this — it only ever stopped duplicates WITHIN a run — which is
        # how 2,913 rows accumulated for 489 airings.
        conn.execute("DROP INDEX idx_raw_episodes_version")
        conn.execute(
            "INSERT INTO raw_ingest_runs (ingest_run_id, source_url, "
            "sync_timestamp, sync_status) "
            "VALUES ('run-2', 'x', '2026-09-02T00:00:00', 'success')")
        conn.execute(
            "INSERT INTO raw_episodes (raw_episode_id, ingest_run_id, ep, title, "
            "date, episode_key, source_hash) "
            "SELECT 'dupe', 'run-2', ep, title, date, episode_key, "
            "source_hash FROM raw_episodes")
        conn.commit()
        assert assert_compacted(conn.cursor()) is False
        conn.close()

    def test_assert_compacted_rejects_rows_with_no_key(self, db, tmp_path):
        load(db, sheet(HEAT), tmp_path)
        conn = sqlite3.connect(db)
        conn.execute("UPDATE raw_episodes SET episode_key = NULL")
        conn.commit()
        assert assert_compacted(conn.cursor()) is False
        conn.close()

    def test_uncompacted_database_gets_the_actionable_message_not_a_crash(
            self, db, tmp_path, capsys):
        """The guard must fire before the schema replay, not after.

        Replaying raw_zone.sql creates the unique index on
        (episode_key, source_hash), which an un-compacted zone cannot satisfy.
        If that ran first the user would get a bare IntegrityError instead of
        being told which script to run.
        """
        load(db, sheet(HEAT), tmp_path)
        conn = sqlite3.connect(db)
        conn.execute("DROP INDEX idx_raw_episodes_version")
        # Half-migrated: keys backfilled, duplicates not yet removed. This is
        # the state where the index would raise, since NULL keys no longer
        # mask the collision.
        conn.execute(
            "INSERT INTO raw_ingest_runs (ingest_run_id, source_url, "
            "sync_timestamp, sync_status) VALUES ('run-2', 'x', "
            "'2026-09-02T00:00:00', 'success')")
        conn.execute(
            "INSERT INTO raw_episodes (raw_episode_id, ingest_run_id, ep, title, "
            "date, episode_key, source_hash) "
            "SELECT 'dupe', 'run-2', ep, title, date, episode_key, source_hash "
            "FROM raw_episodes")
        # Force the schema replay path by removing a column it will re-add.
        conn.commit()
        conn.close()

        with pytest.raises(SystemExit) as exc:
            load(db, sheet(HEAT), tmp_path)
        assert exc.value.code == 1

    def test_unique_index_forbids_storing_a_version_twice(self, db, tmp_path):
        load(db, sheet(HEAT), tmp_path)
        conn = sqlite3.connect(db)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO raw_episodes (raw_episode_id, ingest_run_id, "
                "episode_key, source_hash) "
                "SELECT 'dupe', ingest_run_id, episode_key, source_hash "
                "FROM raw_episodes")
        conn.close()
