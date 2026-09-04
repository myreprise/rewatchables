"""
Shared pytest configuration.
Adds the scripts directory to sys.path so test files can import directly from
the pipeline scripts without requiring a package restructure.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# The nav rail is one radio per group (keys nav_g0..nav_gN), so a test cannot
# address it by a single widget any more. Drive it by label.
#
# NAV_GROUPS is read out of app.py rather than restated here. A hand-kept copy
# drifts the moment a section is added -- which it did, the first time one was
# -- and the failure is an unhelpful StopIteration inside the helper rather
# than anything about the section under test.

import ast as _ast
import re as _re
from pathlib import Path as _Path


def _nav_groups():
    tree = _ast.parse(
        (_Path(__file__).parent.parent / "app.py").read_text(encoding="utf-8"))
    for node in _ast.walk(tree):
        if not isinstance(node, _ast.Assign):
            continue
        if not any(getattr(t, "id", None) == "NAV" for t in node.targets):
            continue
        return [[label for _slug, label in
                 (_ast.literal_eval(item) for item in group.elts[1].elts)]
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
            f"{[l for g in NAV_GROUPS for l in g]}") from None
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
    return _re.search(r"<span>(.*?)</span>", block).group(1)
