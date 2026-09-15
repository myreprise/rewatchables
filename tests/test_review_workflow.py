"""
Integration tests for the manual-review workflow:
  07_export_review_queue.py  →  CSV  →  08_apply_review.py

Uses a temp SQLite file + temp CSV — no real API calls.
The apply script calls get_movie_details() when the chosen id isn't in the
stored candidates; we patch requests.get to avoid real network calls.
"""

import csv
import json
import sqlite3
import uuid
import pytest
from pathlib import Path
from unittest.mock import patch


from rewatchables.pipeline import s07_export_review_queue as export_mod
from rewatchables.pipeline import s08_apply_review as apply_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    schema_dir = Path(__file__).parent.parent / "sql" / "schemas"
    for fname in ["raw_zone.sql", "staging_zone.sql", "curated_zone.sql"]:
        conn.executescript((schema_dir / fname).read_text())
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def tmp_csv(tmp_path):
    return str(tmp_path / "review.csv")


def _seed_pending(db_path, items):
    """
    items = list of (title_raw, year, tmdb_id_of_best_candidate)
    Inserts staging rows marked requires_manual_review=1.
    """
    conn = sqlite3.connect(db_path)
    run_id = "test-run"
    conn.execute(
        "INSERT OR IGNORE INTO raw_ingest_runs (ingest_run_id, source_url, sync_status) "
        "VALUES (?, 'test', 'success')", (run_id,)
    )
    for title, year, best_tmdb_id in items:
        raw_id = str(uuid.uuid4())
        ep_id  = str(uuid.uuid4())
        men_id = str(uuid.uuid4())
        conn.execute(
            "INSERT OR IGNORE INTO raw_episodes (raw_episode_id, ingest_run_id, source_hash) "
            "VALUES (?, ?, ?)", (raw_id, run_id, raw_id)
        )
        conn.execute(
            "INSERT INTO staging_episodes "
            "(staging_episode_id, raw_episode_id, episode_number, episode_date, "
            " episode_title, validation_status) "
            "VALUES (?, ?, 1, '2020-01-01', ?, 'pending')",
            (ep_id, raw_id, title)
        )
        cand = json.dumps([{
            "id": best_tmdb_id, "title": title + " (full title)", "year": str(year),
            "popularity": 5, "vote_average": 6.0, "confidence": 0.75
        }])
        conn.execute(
            "INSERT INTO staging_movie_mentions "
            "(staging_mention_id, staging_episode_id, raw_episode_id, mention_order, "
            " title_raw, title_normalized, year_parsed, resolution_method, "
            " confidence_score, tmdb_id, candidate_json, requires_manual_review) "
            "VALUES (?, ?, ?, 1, ?, ?, ?, 'unresolved', 0.75, ?, ?, 1)",
            (men_id, ep_id, raw_id, title, title.lower(), year, best_tmdb_id, cand)
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Export tests
# ---------------------------------------------------------------------------

class TestExportQueue:
    def test_exports_csv_with_correct_row_count(self, tmp_db, tmp_csv):
        _seed_pending(tmp_db, [("Terminator 2", 1991, 280), ("Victory", 1981, 17360)])
        n = export_mod.export_queue(tmp_db, tmp_csv)
        assert n == 2
        rows = list(csv.DictReader(open(tmp_csv, encoding="utf-8")))
        assert len(rows) == 2

    def test_csv_has_required_columns(self, tmp_db, tmp_csv):
        _seed_pending(tmp_db, [("Terminator 2", 1991, 280)])
        export_mod.export_queue(tmp_db, tmp_csv)
        rows = list(csv.DictReader(open(tmp_csv, encoding="utf-8")))
        required = {"review_id", "staging_mention_id", "title_raw", "action",
                    "chosen_tmdb_id", "candidates"}
        assert required.issubset(set(rows[0].keys()))

    def test_action_and_chosen_id_blank_initially(self, tmp_db, tmp_csv):
        _seed_pending(tmp_db, [("Terminator 2", 1991, 280)])
        export_mod.export_queue(tmp_db, tmp_csv)
        row = list(csv.DictReader(open(tmp_csv, encoding="utf-8")))[0]
        assert row["action"] == ""
        assert row["chosen_tmdb_id"] == ""

    def test_queue_table_populated(self, tmp_db, tmp_csv):
        _seed_pending(tmp_db, [("Terminator 2", 1991, 280), ("Victory", 1981, 17360)])
        export_mod.export_queue(tmp_db, tmp_csv)
        conn = sqlite3.connect(tmp_db)
        count = conn.execute(
            "SELECT COUNT(*) FROM manual_review_queue WHERE queue_status='pending'"
        ).fetchone()[0]
        conn.close()
        assert count == 2

    def test_idempotent_refresh(self, tmp_db, tmp_csv):
        """Re-exporting replaces pending rows; count stays the same."""
        _seed_pending(tmp_db, [("Terminator 2", 1991, 280)])
        export_mod.export_queue(tmp_db, tmp_csv)
        export_mod.export_queue(tmp_db, tmp_csv)
        conn = sqlite3.connect(tmp_db)
        count = conn.execute(
            "SELECT COUNT(*) FROM manual_review_queue WHERE queue_status='pending'"
        ).fetchone()[0]
        conn.close()
        assert count == 1

    def test_candidates_rendered_in_csv(self, tmp_db, tmp_csv):
        _seed_pending(tmp_db, [("Terminator 2", 1991, 280)])
        export_mod.export_queue(tmp_db, tmp_csv)
        row = list(csv.DictReader(open(tmp_csv, encoding="utf-8")))[0]
        assert "280" in row["candidates"]


# ---------------------------------------------------------------------------
# Apply tests
# ---------------------------------------------------------------------------

def _write_csv(csv_path, rows):
    fieldnames = ["review_id", "staging_mention_id", "title_raw", "year_parsed",
                  "best_confidence", "candidates", "action", "chosen_tmdb_id",
                  "reviewer", "notes"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


class TestApplyReview:
    def _export_and_get_rows(self, db_path, csv_path):
        export_mod.export_queue(db_path, csv_path)
        return list(csv.DictReader(open(csv_path, encoding="utf-8")))

    def test_approve_sets_resolution_method(self, tmp_db, tmp_csv):
        _seed_pending(tmp_db, [("Terminator 2", 1991, 280)])
        rows = self._export_and_get_rows(tmp_db, tmp_csv)
        rows[0]["action"] = "approve"
        rows[0]["chosen_tmdb_id"] = "280"
        _write_csv(tmp_csv, rows)

        with patch.object(apply_mod, "get_movie_details", return_value=None), \
             patch("subprocess.run"):
            apply_mod.apply_decisions(tmp_db, tmp_csv)

        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT resolution_method, tmdb_id, requires_manual_review, confidence_score "
            "FROM staging_movie_mentions"
        ).fetchone()
        conn.close()
        assert row[0] == "manual_approved"
        assert row[1] == 280
        assert row[2] == 0
        assert row[3] == 1.0

    def test_approve_marks_queue_approved(self, tmp_db, tmp_csv):
        _seed_pending(tmp_db, [("Terminator 2", 1991, 280)])
        rows = self._export_and_get_rows(tmp_db, tmp_csv)
        rows[0]["action"] = "approve"
        rows[0]["chosen_tmdb_id"] = "280"
        _write_csv(tmp_csv, rows)

        with patch.object(apply_mod, "get_movie_details", return_value=None), \
             patch("subprocess.run"):
            apply_mod.apply_decisions(tmp_db, tmp_csv)

        conn = sqlite3.connect(tmp_db)
        status = conn.execute(
            "SELECT queue_status FROM manual_review_queue"
        ).fetchone()[0]
        conn.close()
        assert status == "approved"

    def test_reject_marks_queue_rejected(self, tmp_db, tmp_csv):
        _seed_pending(tmp_db, [("Victory", 1981, 17360)])
        rows = self._export_and_get_rows(tmp_db, tmp_csv)
        rows[0]["action"] = "reject"
        _write_csv(tmp_csv, rows)

        with patch("subprocess.run"):
            apply_mod.apply_decisions(tmp_db, tmp_csv)

        conn = sqlite3.connect(tmp_db)
        status = conn.execute(
            "SELECT queue_status FROM manual_review_queue"
        ).fetchone()[0]
        conn.close()
        assert status == "rejected"

    def test_reject_leaves_mention_unresolved(self, tmp_db, tmp_csv):
        _seed_pending(tmp_db, [("Victory", 1981, 17360)])
        rows = self._export_and_get_rows(tmp_db, tmp_csv)
        rows[0]["action"] = "reject"
        _write_csv(tmp_csv, rows)

        with patch("subprocess.run"):
            apply_mod.apply_decisions(tmp_db, tmp_csv)

        conn = sqlite3.connect(tmp_db)
        row = conn.execute(
            "SELECT requires_manual_review FROM staging_movie_mentions"
        ).fetchone()
        conn.close()
        assert row[0] == 1  # still flagged

    def test_skip_leaves_queue_pending(self, tmp_db, tmp_csv):
        _seed_pending(tmp_db, [("Victory", 1981, 17360)])
        rows = self._export_and_get_rows(tmp_db, tmp_csv)
        rows[0]["action"] = ""  # blank = skip
        _write_csv(tmp_csv, rows)

        with patch("subprocess.run"):
            apply_mod.apply_decisions(tmp_db, tmp_csv)

        conn = sqlite3.connect(tmp_db)
        status = conn.execute(
            "SELECT queue_status FROM manual_review_queue"
        ).fetchone()[0]
        conn.close()
        assert status == "pending"

    def test_approve_non_top_candidate_fetches_details(self, tmp_db, tmp_csv):
        """Chosen id not in stored candidates → get_movie_details called."""
        _seed_pending(tmp_db, [("Terminator 2", 1991, 280)])
        rows = self._export_and_get_rows(tmp_db, tmp_csv)
        rows[0]["action"] = "approve"
        rows[0]["chosen_tmdb_id"] = "99999"  # not in candidates
        _write_csv(tmp_csv, rows)

        mock_details = {
            "id": 99999, "title": "Custom Film", "year": "1991",
            "popularity": 5, "vote_average": 7.0, "confidence": 1.0,
            "title_similarity": None, "year_score": None,
        }
        with patch.object(apply_mod, "get_movie_details", return_value=mock_details) as mock_fn, \
             patch("subprocess.run"):
            apply_mod.apply_decisions(tmp_db, tmp_csv)

        mock_fn.assert_called_once_with(99999)

    def test_invalid_chosen_id_skips_row(self, tmp_db, tmp_csv):
        """Non-numeric chosen_tmdb_id should not crash — just skip the row."""
        _seed_pending(tmp_db, [("Terminator 2", 1991, 280)])
        rows = self._export_and_get_rows(tmp_db, tmp_csv)
        rows[0]["action"] = "approve"
        rows[0]["chosen_tmdb_id"] = "not-a-number"
        _write_csv(tmp_csv, rows)

        with patch.object(apply_mod, "get_movie_details", return_value=None), \
             patch("subprocess.run"):
            approved, _, _ = apply_mod.apply_decisions(tmp_db, tmp_csv)

        assert approved == 0

    def test_returns_correct_counts(self, tmp_db, tmp_csv):
        _seed_pending(tmp_db, [
            ("Terminator 2", 1991, 280),
            ("Victory",      1981, 17360),
            ("Dodgeball",    2004, 9472),
        ])
        rows = self._export_and_get_rows(tmp_db, tmp_csv)
        rows[0]["action"] = "approve"
        rows[0]["chosen_tmdb_id"] = "280"
        rows[1]["action"] = "reject"
        rows[2]["action"] = ""  # skip
        _write_csv(tmp_csv, rows)

        with patch.object(apply_mod, "get_movie_details", return_value=None), \
             patch("subprocess.run"):
            approved, rejected, skipped = apply_mod.apply_decisions(tmp_db, tmp_csv)

        assert approved == 1
        assert rejected == 1
        assert skipped == 1
