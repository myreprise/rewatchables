"""Paths and settings shared by the pipeline, the app and the tests.

Every path here is anchored to the repository root rather than the working
directory, so a step behaves the same whether the orchestrator runs it, its
scripts/ wrapper does, or it is started from somewhere else entirely.

Importing this module loads config/.env, as each pipeline script used to do
for itself. A variable already set in the environment wins over the file.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / "config" / ".env"
DATA_DIR = ROOT / "data"
SCHEMA_DIR = ROOT / "sql" / "schemas"
LOG_DIR = ROOT / "logs"

load_dotenv(ENV_FILE)


def path_setting(name, default):
    """The path in environment variable `name`, else `default`, anchored to ROOT.

    Read at call time rather than import time, so a caller or a test can set
    the variable after this module has been imported.
    """
    path = Path(os.getenv(name) or default)
    return path if path.is_absolute() else ROOT / path


def db_path():
    """The SQLite database: DB_PATH, else rewatchables.db at the repo root."""
    return path_setting("DB_PATH", "rewatchables.db")


def setup_logging(**kwargs):
    """Configure the root logger for a command-line run.

    Called from each step's `__main__` block rather than at import, so that
    importing a step -- as the tests and step 13 do -- configures nothing.
    LOG_LEVEL sets the level unless `level` is passed; every other keyword goes
    to logging.basicConfig.
    """
    kwargs.setdefault("level", os.getenv("LOG_LEVEL", "INFO"))
    logging.basicConfig(**kwargs)
