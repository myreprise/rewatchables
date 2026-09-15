"""
Paths and settings in rewatchables.config.

The point of the module is that nothing depends on the working directory, so
that is what these pin: every path lands under the repo root, and the settings
are read when asked for rather than frozen at import.
"""

from pathlib import Path

from rewatchables import config

REPO = Path(__file__).resolve().parent.parent


def test_root_is_the_repository():
    assert config.ROOT == REPO
    assert (config.ROOT / "pyproject.toml").exists()


def test_the_directories_sit_under_the_root():
    assert (config.SCHEMA_DIR / "raw_zone.sql").exists()
    assert config.DATA_DIR == REPO / "data"
    assert config.ENV_FILE == REPO / "config" / ".env"


def test_a_relative_setting_is_anchored_to_the_root(monkeypatch):
    monkeypatch.setenv("SOME_PATH", "data/x.csv")
    assert config.path_setting("SOME_PATH", "unused") == REPO / "data" / "x.csv"


def test_an_absolute_setting_is_kept(monkeypatch, tmp_path):
    monkeypatch.setenv("SOME_PATH", str(tmp_path / "x.db"))
    assert config.path_setting("SOME_PATH", "unused") == tmp_path / "x.db"


def test_an_unset_or_empty_setting_takes_the_default(monkeypatch):
    monkeypatch.delenv("SOME_PATH", raising=False)
    assert config.path_setting("SOME_PATH", "a/b") == REPO / "a" / "b"
    monkeypatch.setenv("SOME_PATH", "")
    assert config.path_setting("SOME_PATH", "a/b") == REPO / "a" / "b"


def test_db_path_is_read_when_asked_for(monkeypatch, tmp_path):
    monkeypatch.delenv("DB_PATH", raising=False)
    assert config.db_path() == REPO / "rewatchables.db"
    monkeypatch.setenv("DB_PATH", str(tmp_path / "other.db"))
    assert config.db_path() == tmp_path / "other.db"


def test_the_repos_own_setting_names_the_same_file(monkeypatch):
    """config/.env writes DB_PATH=./rewatchables.db; that must be the root file."""
    monkeypatch.setenv("DB_PATH", "./rewatchables.db")
    assert config.db_path().resolve() == (REPO / "rewatchables.db").resolve()
