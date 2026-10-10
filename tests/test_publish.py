"""
Tests for scripts/publish.py (src/rewatchables/publish.py).

What matters most is what publish refuses to do: commit anything outside the
published data, commit on a run that was declined or dry, or call a revisit a
new episode. The git checks run in a throwaway repository, never in this one.
"""

import sqlite3
import subprocess

import pytest

from rewatchables import config, publish

HEADER = "ep,title,date,host\n"


# ── What changed ──────────────────────────────────────────────────────────────

def test_a_new_row_is_added():
    before = HEADER + "1,Heat,2015-12-01,Bill\n"
    after = before + "2,Speed,2015-12-08,Bill\n"
    changes = publish.episode_changes(before, after)
    assert [r["title"] for r in changes["added"]] == ["Speed"]
    assert changes["changed"] == changes["removed"] == []


def test_a_revisit_reusing_the_number_is_added_not_changed():
    """The sheet reuses an episode number when a film comes back."""
    before = HEADER + "73,Notting Hill,2019-05-01,Bill\n"
    after = before + "73,Notting Hill,2024-05-01,Bill\n"
    changes = publish.episode_changes(before, after)
    assert [r["date"] for r in changes["added"]] == ["2024-05-01"]
    assert changes["changed"] == []


def test_an_edited_cell_is_changed():
    before = HEADER + "1,Heat,2015-12-01,Bill\n"
    after = HEADER + "1,Heat,2015-12-01,Chris\n"
    changes = publish.episode_changes(before, after)
    assert [r["host"] for r in changes["changed"]] == ["Chris"]
    assert changes["added"] == changes["removed"] == []


def test_no_previous_csv_means_everything_is_added():
    changes = publish.episode_changes("", HEADER + "1,Heat,2015-12-01,Bill\n")
    assert len(changes["added"]) == 1


@pytest.mark.parametrize("added,changed,subject", [
    ([{"ep": "484", "title": "The Texas Chain Saw Massacre"}], [],
     "Add episode 484: The Texas Chain Saw Massacre"),
    ([{"ep": "9", "title": "a"}, {"ep": "10", "title": "b"}], [],
     "Add episodes 9-10"),
    ([], [{"ep": "1", "title": "Heat"}], "Update 1 episode"),
    ([], [], "Refresh the published data"),
])
def test_commit_subject(added, changed, subject):
    message = publish.commit_message(
        {"added": added, "changed": changed, "removed": []}, [])
    assert message.split("\n\n")[0] == subject


def test_commit_body_counts_site_files_and_names_the_rest():
    files = [("M", "data/episodes.csv"), ("M", "data/upcoming.csv"),
             ("??", "site/src/data/films/a.json"), ("M", "site/src/data/films.json")]
    body = publish.commit_message(
        {"added": [], "changed": [], "removed": []}, files).split("\n\n", 1)[1]
    assert "Also: data/upcoming.csv" in body
    assert "Site data: 2 files" in body
    assert "episodes.csv" not in body.split("Also:")[1].split("\n")[0]


@pytest.mark.parametrize("remote,site", [
    ("https://github.com/myreprise/rewatchables.git", "https://myreprise.github.io/rewatchables/"),
    ("https://github.com/myreprise/rewatchables", "https://myreprise.github.io/rewatchables/"),
    ("git@github.com:myreprise/rewatchables.git", "https://myreprise.github.io/rewatchables/"),
    ("https://github.com/myreprise/myreprise.github.io.git", "https://myreprise.github.io/"),
    ("https://gitlab.com/x/y.git", None),
    (None, None),
])
def test_pages_url(remote, site):
    assert publish.pages_url(remote) == site


@pytest.mark.parametrize("answer,expected", [("y", True), ("YES", True), ("", False), ("n", False)])
def test_confirm_needs_an_explicit_yes(answer, expected):
    assert publish.confirm("Publish?", ask=lambda _: answer) is expected


def test_confirm_treats_no_input_as_no():
    def eof(_):
        raise EOFError
    assert publish.confirm("Publish?", ask=eof) is False


def test_pending_reviews(tmp_path):
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE manual_review_queue "
                 "(movie_title_raw TEXT, year_parsed INTEGER, queue_status TEXT)")
    conn.executemany("INSERT INTO manual_review_queue VALUES (?, ?, ?)", [
        ("Crash", 2004, "approved"), ("Heat", 1995, "pending"), ("Speed", None, "pending")])
    conn.commit()
    conn.close()
    assert publish.pending_reviews(db) == ["Heat (1995)", "Speed"]


def test_pending_reviews_without_the_table_is_empty(tmp_path):
    assert publish.pending_reviews(tmp_path / "missing.db") == []


# ── In a throwaway repository ─────────────────────────────────────────────────

def _git(repo, *args):
    return subprocess.run(["git", *args], cwd=repo, check=True,
                          capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A repo on master holding one episode, with ROOT and the db pointed at it."""
    _git(tmp_path, "init", "-q", "-b", "master")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "core.autocrlf", "false")
    (tmp_path / "data").mkdir()
    (tmp_path / "site" / "src" / "data").mkdir(parents=True)
    (tmp_path / "data" / "episodes.csv").write_text(
        HEADER + "1,Heat,2015-12-01,Bill\n", encoding="utf-8")
    (tmp_path / "site" / "src" / "data" / "films.json").write_text("[]\n", encoding="utf-8")
    (tmp_path / "code.py").write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-q", "-m", "start")
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "none.db"))
    return tmp_path


def _add_episode(repo):
    with open(repo / "data" / "episodes.csv", "a", encoding="utf-8") as f:
        f.write("2,Speed,2015-12-08,Bill\n")
    (repo / "site" / "src" / "data" / "films").mkdir()
    (repo / "site" / "src" / "data" / "films" / "speed.json").write_text("{}\n", encoding="utf-8")


def test_changed_files_reads_a_path_with_a_space(repo):
    (repo / "data" / "remaining films.xlsx").write_bytes(b"x")
    files = publish.changed_files(["data/remaining films.xlsx"], cwd=repo)
    assert files == [("??", "data/remaining films.xlsx")]


def test_publishable_paths_drops_what_never_existed(repo):
    paths = publish.publishable_paths(cwd=repo)
    assert "data/episodes.csv" in paths
    assert "data/manual_review.csv" not in paths


def test_commit_takes_only_the_published_paths(repo):
    _add_episode(repo)
    (repo / "code.py").write_text("x = 2\n", encoding="utf-8")       # unstaged work
    (repo / "notes.txt").write_text("draft\n", encoding="utf-8")
    _git(repo, "add", "notes.txt")                                    # staged work
    publish.commit_published("Add episode 2: Speed\n\nbody",
                             publish.publishable_paths(cwd=repo), cwd=repo)
    committed = _git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert sorted(committed) == ["data/episodes.csv", "site/src/data/films/speed.json"]
    status = _git(repo, "status", "--porcelain")
    assert " M code.py" in status and "A  notes.txt" in status


def test_a_deleted_page_is_committed_as_deleted(repo):
    (repo / "site" / "src" / "data" / "films.json").unlink()
    publish.commit_published("Refresh\n\nbody", publish.publishable_paths(cwd=repo), cwd=repo)
    assert _git(repo, "show", "--name-status", "--format=", "HEAD").split() == [
        "D", "site/src/data/films.json"]


def test_unpushed_counts_everything_before_a_first_push(repo):
    assert publish.unpushed(cwd=repo) == 1


def test_main_commits_the_episode_with_its_message(repo):
    _add_episode(repo)
    (repo / "code.py").write_text("x = 2\n", encoding="utf-8")
    assert publish.main(["--skip-pipeline", "--skip-tests", "--yes"]) == 0
    assert _git(repo, "log", "-1", "--format=%s") .strip() == "Add episode 2: Speed"
    assert "Added: Ep 2, Speed (2015-12-08)" in _git(repo, "log", "-1", "--format=%b")
    assert _git(repo, "status", "--porcelain").strip() == "M code.py"


def test_main_dry_run_commits_nothing(repo):
    _add_episode(repo)
    assert publish.main(["--skip-pipeline", "--skip-tests", "--dry-run"]) == 0
    assert _git(repo, "rev-list", "--count", "HEAD").strip() == "1"


def test_main_declined_commits_nothing(repo, monkeypatch):
    _add_episode(repo)
    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert publish.main(["--skip-pipeline", "--skip-tests"]) == 2
    assert _git(repo, "rev-list", "--count", "HEAD").strip() == "1"


def test_main_refuses_another_branch(repo):
    _git(repo, "switch", "-q", "-c", "elsewhere")
    _add_episode(repo)
    assert publish.main(["--skip-pipeline", "--skip-tests", "--yes"]) == 1
    assert _git(repo, "rev-list", "--count", "HEAD").strip() == "1"


def test_main_stops_for_a_pending_review(repo, monkeypatch, tmp_path):
    db = tmp_path / "q.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE manual_review_queue "
                 "(movie_title_raw TEXT, year_parsed INTEGER, queue_status TEXT)")
    conn.execute("INSERT INTO manual_review_queue VALUES ('Crash', 2004, 'pending')")
    conn.commit()
    conn.close()
    monkeypatch.setenv("DB_PATH", str(db))
    _add_episode(repo)
    assert publish.main(["--skip-pipeline", "--skip-tests", "--yes"]) == 2
    assert _git(repo, "rev-list", "--count", "HEAD").strip() == "1"
    assert publish.main(["--skip-pipeline", "--skip-tests", "--yes",
                         "--allow-pending"]) == 0


def test_main_with_nothing_changed_does_nothing(repo):
    assert publish.main(["--skip-pipeline", "--skip-tests", "--yes"]) == 0
    assert _git(repo, "rev-list", "--count", "HEAD").strip() == "1"
