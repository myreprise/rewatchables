"""
The scripts/ wrappers: the step files people run by path.

The pipeline's code lives in src/rewatchables/pipeline, and each old path is a
wrapper so that `python scripts/04_enrich.py --refresh` -- and every doc, log
line and habit that says so -- still works. What can go wrong is a wrapper
aimed at the wrong module, or a step that has no wrapper at all.
"""

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from rewatchables.pipeline import orchestrate

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"


def _target(path):
    """The module a wrapper runs, read from its runpy.run_module call."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "run_module":
            return node.args[0].value
    return None


@pytest.mark.parametrize("step", orchestrate.STEPS, ids=lambda s: s[1])
def test_every_step_has_a_wrapper_that_runs_it(step):
    module = step[1]
    path = SCRIPTS / f"{module.removeprefix('s')}.py"
    assert path.exists(), f"no wrapper at scripts/{path.name}"
    assert _target(path) == f"{orchestrate.PACKAGE}.{module}"


@pytest.mark.parametrize("name", ["orchestrate", "convert_xlsx_to_csv"])
def test_the_tools_have_wrappers(name):
    assert _target(SCRIPTS / f"{name}.py") == f"{orchestrate.PACKAGE}.{name}"


def _run(*args):
    # PYTHONPATH so the check holds without the editable install too.
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=120)


def test_the_orchestrator_wrapper_runs():
    """End to end: the wrapper finds the package and its arguments arrive."""
    result = _run("scripts/orchestrate.py", "--list")
    assert result.returncode == 0, result.stderr
    assert "s13_build_upcoming" in result.stdout


def test_a_step_wrapper_passes_its_arguments_through():
    result = _run("scripts/04_enrich.py", "--help")
    assert result.returncode == 0, result.stderr
    assert "--refresh" in result.stdout


def test_a_step_wrapper_passes_its_exit_code_through(tmp_path):
    """A step that fails must fail the orchestrator's subprocess check."""
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src"),
           "DB_PATH": str(tmp_path / "absent.db")}
    result = subprocess.run([sys.executable, "scripts/05_validate.py"], cwd=ROOT,
                            env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 1
