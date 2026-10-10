"""
Tests for orchestrate.py — step selection and the destructive-path guard.

Nothing here spawns a subprocess; run_step is patched out. The behaviour that
matters is which steps get selected and whether the guard stops a run that
would discard manual work.
"""

import argparse
import importlib.util
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

from rewatchables.pipeline import orchestrate as mod

STEPS = mod.STEPS
STAGES = mod.STAGES
select_steps = mod.select_steps
count_manual_resolutions = mod.count_manual_resolutions


def _args(**kw):
    base = dict(all=False, from_step=None, to_step=None, only=None, stages=None)
    base.update(kw)
    return argparse.Namespace(**base)


def _nums(steps):
    return [s[0] for s in steps]


# Derived, not restated. These three assertions are about where a selection
# STOPS -- at the end of the pipeline -- and a hard-coded 12 turns "a step was
# added" into three unrelated-looking failures about ranges. Read the last step
# out of the table the code itself uses.
LAST = STEPS[-1][0]


# ---------------------------------------------------------------------------
# Step table integrity
# ---------------------------------------------------------------------------

class TestStepTable:
    def test_every_step_module_exists(self):
        missing = [s[1] for s in STEPS
                   if importlib.util.find_spec(f"{mod.PACKAGE}.{s[1]}") is None]
        assert missing == [], f"orchestrator references missing modules: {missing}"

    def test_numbers_are_contiguous_and_ordered(self):
        assert _nums(STEPS) == list(range(1, len(STEPS) + 1))

    def test_all_pipeline_steps_are_wired_in(self):
        """A numbered step that exists but is not orchestrated is exactly the
        bug this file is meant to prevent recurring."""
        pipeline_dir = Path(mod.__file__).parent
        on_disk = {p.stem for p in pipeline_dir.glob("s[0-9][0-9]_*.py")}
        wired = {s[1] for s in STEPS}
        assert on_disk - wired == set(), f"not wired into orchestrate: {on_disk - wired}"

    def test_stages_are_valid(self):
        assert {s[3] for s in STEPS} <= set(STAGES)

    def test_review_and_image_steps_are_optional(self):
        """07/08 fail by design when there is nothing queued or no CSV yet; 14
        is a download the app can do without."""
        optional = {s[0] for s in STEPS if s[4]}
        assert optional == {7, 8, 14}


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

class TestSelectSteps:
    def test_default_skips_the_destructive_steps(self):
        assert _nums(select_steps(_args())) == list(range(5, LAST + 1))

    def test_all_selects_everything(self):
        assert _nums(select_steps(_args(all=True))) == list(range(1, LAST + 1))

    def test_stage_selection(self):
        assert _nums(select_steps(_args(stages="enrich"))) == [9, 10, 11, 12]
        assert _nums(select_steps(_args(stages="source"))) == [1, 2]
        assert _nums(select_steps(_args(stages="resolve"))) == [3, 4]
        assert _nums(select_steps(_args(stages="upcoming"))) == [13]
        assert _nums(select_steps(_args(stages="images"))) == [14]
        assert _nums(select_steps(_args(stages="site"))) == [15]

    def test_multiple_stages(self):
        assert _nums(select_steps(_args(stages="source,resolve"))) == [1, 2, 3, 4]

    def test_range(self):
        assert _nums(select_steps(_args(from_step=6, to_step=9))) == [6, 7, 8, 9]

    def test_only(self):
        assert _nums(select_steps(_args(only="11,12"))) == [11, 12]

    def test_only_beats_stages(self):
        assert _nums(select_steps(_args(only="3", stages="enrich"))) == [3]

    def test_unknown_stage_exits(self):
        with pytest.raises(SystemExit):
            select_steps(_args(stages="bogus"))

    def test_from_alone_runs_to_the_end(self):
        assert _nums(select_steps(_args(from_step=10))) == list(range(10, LAST + 1))


# ---------------------------------------------------------------------------
# Destructive-path guard
# ---------------------------------------------------------------------------

@pytest.fixture
def db_with_manual(tmp_path):
    p = str(tmp_path / "m.db")
    conn = sqlite3.connect(p)
    schema_dir = Path(__file__).parent.parent / "sql" / "schemas"
    for fname in ["raw_zone.sql", "staging_zone.sql"]:
        conn.executescript((schema_dir / fname).read_text())
    ep, raw_ep = str(uuid.uuid4()), str(uuid.uuid4())
    conn.execute(
        "INSERT INTO staging_episodes (staging_episode_id, raw_episode_id, "
        "episode_title) VALUES (?, ?, 'ep')", (ep, raw_ep))
    # UNIQUE(staging_episode_id, mention_order) -- give each its own order
    for order, (title, method) in enumerate(
            [("Crash", "manual_approved"), ("Heat", "exact_tmdb")], start=1):
        conn.execute(
            "INSERT INTO staging_movie_mentions (staging_mention_id, "
            "staging_episode_id, raw_episode_id, mention_order, title_raw, "
            "resolution_method) VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), ep, raw_ep, order, title, method))
    conn.commit()
    conn.close()
    return p


class TestGuard:
    def test_counts_only_manual_resolutions(self, db_with_manual):
        assert count_manual_resolutions(db_with_manual) == 1

    def test_missing_db_counts_zero(self, tmp_path):
        assert count_manual_resolutions(str(tmp_path / "nope.db")) == 0

    def test_db_without_staging_table_counts_zero(self, tmp_path):
        p = str(tmp_path / "bare.db")
        sqlite3.connect(p).close()
        assert count_manual_resolutions(p) == 0

    def test_blocks_rebuild_that_skips_the_replay(self, db_with_manual,
                                                  monkeypatch):
        """03 without 08 leaves the wrong matches 04 re-derived in place."""
        monkeypatch.setattr(mod, "DB_PATH", db_with_manual)
        with patch.object(mod.sys, "argv",
                          ["orchestrate.py", "--from", "3", "--to", "6",
                           "--dry-run"]),              patch.object(mod, "run_step") as rs:
            rc = mod.main()
        assert rc == 3
        rs.assert_not_called()

    def test_allows_rebuild_that_includes_the_replay(self, db_with_manual,
                                                     monkeypatch):
        """--all runs step 08, which replays decisions onto the deterministic
        ids, so a full rebuild no longer loses manual work."""
        monkeypatch.setattr(mod, "DB_PATH", db_with_manual)
        with patch.object(mod.sys, "argv",
                          ["orchestrate.py", "--all", "--dry-run"]):
            assert mod.main() == 0

    def test_allows_unreplayed_rebuild_when_acknowledged(self, db_with_manual,
                                                         monkeypatch):
        monkeypatch.setattr(mod, "DB_PATH", db_with_manual)
        with patch.object(mod.sys, "argv",
                          ["orchestrate.py", "--from", "3", "--to", "6",
                           "--rebuild-from-source", "--dry-run"]):
            assert mod.main() == 0

    def test_allows_safe_refresh_without_flag(self, db_with_manual, monkeypatch):
        monkeypatch.setattr(mod, "DB_PATH", db_with_manual)
        with patch.object(mod.sys, "argv", ["orchestrate.py", "--dry-run"]):
            assert mod.main() == 0

    def test_no_manual_work_means_no_block(self, tmp_path, monkeypatch):
        p = str(tmp_path / "clean.db")
        conn = sqlite3.connect(p)
        schema_dir = Path(__file__).parent.parent / "sql" / "schemas"
        for fname in ["raw_zone.sql", "staging_zone.sql"]:
            conn.executescript((schema_dir / fname).read_text())
        conn.commit()
        conn.close()
        monkeypatch.setattr(mod, "DB_PATH", p)
        with patch.object(mod.sys, "argv",
                          ["orchestrate.py", "--from", "3", "--to", "6",
                           "--dry-run"]):
            assert mod.main() == 0


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------

class TestFailureHandling:
    def test_optional_failure_does_not_halt(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mod, "DB_PATH", str(tmp_path / "none.db"))
        # steps 7 and 8 are optional; fail 7 and confirm 8 still runs
        calls = []

        def fake(num, script, desc, position, total, optional):
            calls.append(num)
            return num != 7

        with patch.object(mod, "run_step", side_effect=fake), \
             patch.object(mod.sys, "argv", ["orchestrate.py", "--only", "7,8"]):
            rc = mod.main()
        assert calls == [7, 8]
        assert rc == 0, "an optional failure must not fail the pipeline"

    def test_required_failure_halts(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mod, "DB_PATH", str(tmp_path / "none.db"))
        calls = []

        def fake(num, script, desc, position, total, optional):
            calls.append(num)
            return num != 9

        with patch.object(mod, "run_step", side_effect=fake), \
             patch.object(mod.sys, "argv", ["orchestrate.py", "--only", "9,10,11"]):
            rc = mod.main()
        assert calls == [9], "must stop at the first required failure"
        assert rc == 1

    def test_continue_on_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mod, "DB_PATH", str(tmp_path / "none.db"))
        calls = []

        def fake(num, script, desc, position, total, optional):
            calls.append(num)
            return num != 9

        with patch.object(mod, "run_step", side_effect=fake), \
             patch.object(mod.sys, "argv",
                          ["orchestrate.py", "--only", "9,10,11",
                           "--continue-on-error"]):
            rc = mod.main()
        assert calls == [9, 10, 11]
        assert rc == 1, "still reports failure even though it continued"
