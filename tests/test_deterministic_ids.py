"""
Tests for the deterministic staging-id scheme in 03_normalize_and_resolve.py,
its migration, and the 07 export that must not clobber decisions.

The property under test: rebuilding staging must not detach manual review work.
"""

import csv
import importlib.util
import sqlite3
import uuid
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "scripts"
SCHEMAS = Path(__file__).parent.parent / "sql" / "schemas"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


norm = _load("normalize_and_resolve", SCRIPTS / "03_normalize_and_resolve.py")
migrate_mod = _load("migrate_ids", SCRIPTS / "migrate_deterministic_ids.py")
export_mod = _load("export_queue", SCRIPTS / "07_export_review_queue.py")

make_episode_id = norm.make_episode_id
make_mention_id = norm.make_mention_id


class TestDeterministicIds:
    def test_same_input_gives_same_id(self):
        a = make_mention_id("68", "2019-04-23", "American Pie", 1)
        b = make_mention_id("68", "2019-04-23", "American Pie", 1)
        assert a == b

    def test_ids_are_valid_uuids(self):
        """Columns are TEXT holding uuid strings; the format must not change."""
        mid = make_mention_id("1", "2019-01-01", "Heat", 1)
        assert str(uuid.UUID(mid)) == mid
        assert uuid.UUID(mid).version == 5

    def test_date_format_does_not_change_the_id(self):
        """raw_episodes stores '2019-04-23 00:00:00'; normalising first means a
        format change upstream does not detach decisions."""
        assert make_mention_id("68", "2019-04-23 00:00:00", "American Pie", 1) == \
               make_mention_id("68", "2019-04-23", "American Pie", 1)

    def test_rewatches_get_distinct_ids(self):
        """The podcast reuses episode numbers when revisiting a film, so `ep`
        alone is not unique — American Pie is ep 68 in 2019 and again in 2023."""
        assert make_mention_id("68", "2019-04-23", "American Pie", 1) != \
               make_mention_id("68", "2023-11-28", "American Pie", 1)

    def test_mention_order_separates_mentions(self):
        assert make_mention_id("1", "2019-01-01", "Heat", 1) != \
               make_mention_id("1", "2019-01-01", "Heat", 2)

    def test_episode_and_mention_ids_differ(self):
        assert make_episode_id("1", "2019-01-01", "Heat") != \
               make_mention_id("1", "2019-01-01", "Heat", 1)

    def test_title_change_changes_the_id(self):
        """Accepted trade-off: retitling a row detaches its decision, which is
        arguably correct — but it must be a deliberate, documented property."""
        assert make_mention_id("1", "2019-01-01", "Heat") != \
               make_mention_id("1", "2019-01-01", "Heat 2")

    def test_whitespace_is_insignificant(self):
        assert make_mention_id(" 1 ", "2019-01-01", " Heat ", 1) == \
               make_mention_id("1", "2019-01-01", "Heat", 1)

    def test_namespace_is_pinned(self):
        """Changing this renames every id and detaches all manual work."""
        assert str(norm.STAGING_NAMESPACE) == \
            "6f2a1d4c-9b3e-5a77-8c14-2de0f7b6a913"


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

@pytest.fixture
def legacy_db(tmp_path):
    """A database with random uuid4 staging ids and one manual resolution."""
    p = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(p)
    for f in ["raw_zone.sql", "staging_zone.sql", "curated_zone.sql"]:
        conn.executescript((SCHEMAS / f).read_text())

    run = str(uuid.uuid4())
    conn.execute("INSERT INTO raw_ingest_runs (ingest_run_id, source_url, "
                 "sync_timestamp) VALUES (?, 'test://sheet', "
                 "'2026-01-01T00:00:00')", (run,))
    raw_ids = {}
    for i, (ep, date, title) in enumerate([
            ("68", "2019-04-23 00:00:00", "American Pie"),
            ("68", "2023-11-28 00:00:00", "American Pie")], start=1):
        rid = str(uuid.uuid4())
        raw_ids[ep + date] = (rid, ep, date, title)
        conn.execute(
            "INSERT INTO raw_episodes (raw_episode_id, ingest_run_id, ep, date, "
            "title, is_film, source_hash, gs_row_number) "
            "VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
            (rid, run, ep, date, title, f"hash{i}", i))

    for order, (rid, ep, date, title) in enumerate(raw_ids.values(), start=1):
        sid, mid = str(uuid.uuid4()), str(uuid.uuid4())
        conn.execute("INSERT INTO staging_episodes (staging_episode_id, "
                     "raw_episode_id, episode_title) VALUES (?, ?, ?)",
                     (sid, rid, title))
        conn.execute(
            "INSERT INTO staging_movie_mentions (staging_mention_id, "
            "staging_episode_id, raw_episode_id, mention_order, title_raw, "
            "resolution_method) VALUES (?, ?, ?, 1, ?, ?)",
            (mid, sid, rid, title,
             "manual_approved" if order == 1 else "exact_tmdb"))
        conn.execute(
            "INSERT INTO manual_review_queue (review_id, staging_mention_id, "
            "movie_title_raw, candidates, queue_status) "
            "VALUES (?, ?, ?, '[]', 'approved')",
            (str(uuid.uuid4()), mid, title))
        conn.execute(
            "INSERT INTO curated_episode_movies (episode_movie_id, "
            "staging_episode_id, movie_id, episode_number, episode_date, "
            "mention_order) VALUES (?, ?, ?, ?, ?, 1)",
            (str(uuid.uuid4()), sid, str(uuid.uuid4()), order, date[:10]))
    conn.commit()
    conn.close()
    return p


class TestMigration:
    def test_rewrites_ids_to_deterministic_form(self, legacy_db):
        migrate_mod.migrate(legacy_db)
        conn = sqlite3.connect(legacy_db)
        raw = {r[0]: (r[1], r[2], r[3]) for r in conn.execute(
            "SELECT raw_episode_id, ep, date, title FROM raw_episodes")}
        bad = [mid for mid, rid, o in conn.execute(
            "SELECT staging_mention_id, raw_episode_id, mention_order "
            "FROM staging_movie_mentions")
            if make_mention_id(*raw[rid], o or 1) != mid]
        conn.close()
        assert bad == []

    def test_preserves_manual_resolutions(self, legacy_db):
        migrate_mod.migrate(legacy_db)
        conn = sqlite3.connect(legacy_db)
        n = conn.execute("SELECT COUNT(*) FROM staging_movie_mentions "
                         "WHERE resolution_method = 'manual_approved'").fetchone()[0]
        conn.close()
        assert n == 1

    def test_updates_all_referencing_tables(self, legacy_db):
        migrate_mod.migrate(legacy_db)
        conn = sqlite3.connect(legacy_db)
        orphan_curated = conn.execute("""
            SELECT COUNT(*) FROM curated_episode_movies c
            LEFT JOIN staging_episodes e
              ON e.staging_episode_id = c.staging_episode_id
            WHERE e.staging_episode_id IS NULL""").fetchone()[0]
        orphan_queue = conn.execute("""
            SELECT COUNT(*) FROM manual_review_queue q
            LEFT JOIN staging_movie_mentions m
              ON m.staging_mention_id = q.staging_mention_id
            WHERE m.staging_mention_id IS NULL""").fetchone()[0]
        conn.close()
        assert (orphan_curated, orphan_queue) == (0, 0)

    def test_is_idempotent(self, legacy_db):
        migrate_mod.migrate(legacy_db)
        ep2, men2 = migrate_mod.migrate(legacy_db)
        assert (ep2, men2) == (0, 0), "second run must find nothing to do"

    def test_dry_run_changes_nothing(self, legacy_db):
        conn = sqlite3.connect(legacy_db)
        before = {r[0] for r in conn.execute(
            "SELECT staging_mention_id FROM staging_movie_mentions")}
        conn.close()
        migrate_mod.migrate(legacy_db, dry_run=True)
        conn = sqlite3.connect(legacy_db)
        after = {r[0] for r in conn.execute(
            "SELECT staging_mention_id FROM staging_movie_mentions")}
        conn.close()
        assert before == after


# ---------------------------------------------------------------------------
# 07 must not destroy the decisions file
# ---------------------------------------------------------------------------

FIELDS = ['review_id', 'staging_mention_id', 'title_raw', 'year_parsed',
          'best_confidence', 'candidates', 'action', 'chosen_tmdb_id',
          'reviewer', 'notes']


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


class TestExportPreservesDecisions:
    def test_existing_decisions_are_read_back(self, tmp_path):
        p = tmp_path / "review.csv"
        _write_csv(p, [
            {**{k: "" for k in FIELDS}, "staging_mention_id": "a",
             "action": "approve", "chosen_tmdb_id": "1640"},
            {**{k: "" for k in FIELDS}, "staging_mention_id": "b",
             "action": ""},   # untouched -> not a decision
        ])
        kept = export_mod._existing_decisions(p)
        assert [k["staging_mention_id"] for k in kept] == ["a"]

    def test_missing_file_is_not_an_error(self, tmp_path):
        assert export_mod._existing_decisions(tmp_path / "nope.csv") == []

    def test_export_with_nothing_pending_keeps_decisions(self, tmp_path):
        """Regression: exporting when the queue was empty truncated the file to
        a bare header, erasing every recorded decision."""
        db = str(tmp_path / "e.db")
        conn = sqlite3.connect(db)
        for f in ["raw_zone.sql", "staging_zone.sql", "curated_zone.sql"]:
            conn.executescript((SCHEMAS / f).read_text())
        conn.commit()
        conn.close()

        p = tmp_path / "review.csv"
        _write_csv(p, [{**{k: "" for k in FIELDS}, "staging_mention_id": "a",
                        "title_raw": "Crash", "action": "approve",
                        "chosen_tmdb_id": "1640"}])

        export_mod.export_queue(db, csv_path=str(p))

        rows = list(csv.DictReader(open(p, encoding="utf-8")))
        assert len(rows) == 1
        assert rows[0]["chosen_tmdb_id"] == "1640"
