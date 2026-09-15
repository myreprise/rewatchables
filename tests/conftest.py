"""
Shared pytest configuration.

The repo root and scripts/ are put on the import path by `pythonpath` in
pyproject.toml, so test files import views and the pipeline modules directly,
under plain `pytest` as well as `python -m pytest`.
"""

import ast
import functools
import inspect
import re
from pathlib import Path

import pytest

# ── The `app` marker ──────────────────────────────────────────────────────────
# A test that drives app.py through Streamlit's AppTest costs seconds rather
# than milliseconds: AppTest re-parses the whole script on every run. Those
# tests are marked `app`, so `pytest -m "not app"` is a fast loop.
#
# The mark is derived rather than applied by hand, for the same reason
# NAV_GROUPS is below: a new app test is covered the moment it is written. A
# test counts if it, or any fixture it uses, mentions AppTest.


@functools.cache
def _mentions_apptest(obj):
    try:
        return "AppTest" in inspect.getsource(obj)
    except (OSError, TypeError):
        return False


def _drives_the_app(item):
    candidates = [getattr(item, "function", None)]
    # _fixtureinfo is pytest-internal; pytest is pinned in pyproject.toml.
    info = getattr(item, "_fixtureinfo", None)
    if info is not None:
        for name in item.fixturenames:
            candidates += [d.func for d in info.name2fixturedefs.get(name, ())]
    return any(c is not None and _mentions_apptest(c) for c in candidates)


def pytest_collection_modifyitems(items):
    for item in items:
        if _drives_the_app(item):
            item.add_marker(pytest.mark.app)


# ── Driving the nav rail ──────────────────────────────────────────────────────
# The nav rail is one radio per group (keys nav_g0..nav_gN), so a test cannot
# address it by a single widget any more. Drive it by label.
#
# NAV_GROUPS is read out of app.py rather than restated here. A hand-kept copy
# drifts the moment a section is added -- which it did, the first time one was
# -- and the failure is an unhelpful StopIteration inside the helper rather
# than anything about the section under test.


def _nav_groups():
    tree = ast.parse(
        (Path(__file__).parent.parent / "app.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(getattr(t, "id", None) == "NAV" for t in node.targets):
            continue
        return [[label for _slug, label in
                 (ast.literal_eval(item) for item in group.elts[1].elts)]
                for group in node.value.elts]
    raise RuntimeError("no NAV assignment found in app.py")


NAV_GROUPS = _nav_groups()


def goto(at, label):
    """Select a section by its rail label and rerun."""
    try:
        group = next(i for i, labels in enumerate(NAV_GROUPS) if label in labels)
    except StopIteration:
        raise AssertionError(
            f"{label!r} is not on the rail; it has "
            f"{[name for grp in NAV_GROUPS for name in grp]}") from None
    return at.radio(key=f"nav_g{group}").set_value(label).run()


def film_count(at):
    """The Movie Explorer's result-count line, as rendered text.

    It left st.caption for the .rw-kw-gridnote header row when the sort picker
    joined it there, so it arrives as markdown carrying a span. Read through
    the span rather than by substring: "3 films match your filters" is itself a
    substring of "13 films match your filters".
    """
    block = next(m.value for m in at.markdown
                 if "films match your filters" in m.value)
    return re.search(r"<span>(.*?)</span>", block).group(1)
