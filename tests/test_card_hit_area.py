"""
Tests for the poster card's click target.

A poster card is two sibling elements: an st.markdown plate and the st.button
that carries the title strip and the click handler. The whole card is one target
only because CSS reaches the button's hit area up over the plate — and CSS has
no way to work out how far up that is, so poster_html() stamps the plate height
onto the marker as a class and app.py generates one rule per height listed in
_CARD_HEIGHTS.

That makes _CARD_HEIGHTS a hand-kept list of something the call sites decide,
which is exactly the shape of thing that drifts. When it does, the failure is
silent and easy to miss: the card still works, the plate just stops being
clickable above the title strip. So the list is checked against the call sites
here rather than trusted, in the same spirit as NAV_GROUPS in conftest.
"""

import ast
from pathlib import Path

import pytest

APP = Path(__file__).parent.parent / "app.py"
TREE = ast.parse(APP.read_text(encoding="utf-8"))


def _called(name):
    """Every Call node for a plain function named `name`."""
    return [n for n in ast.walk(TREE)
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == name]


def _defined(name):
    return next(n for n in ast.walk(TREE)
                if isinstance(n, ast.FunctionDef) and n.name == name)


def _kwarg(call, name):
    return next((kw.value for kw in call.keywords if kw.arg == name), None)


def _default(func, name):
    """The default of `func`'s keyword parameter `name`."""
    args = func.args.args
    offset = len(args) - len(func.args.defaults)
    return next(ast.literal_eval(func.args.defaults[i - offset])
                for i, a in enumerate(args) if a.arg == name)


def _card_heights():
    node = next(n for n in ast.walk(TREE)
                if isinstance(n, ast.Assign)
                and any(getattr(t, "id", None) == "_CARD_HEIGHTS"
                        for t in n.targets))
    return set(ast.literal_eval(node.value))


def _rendered_heights():
    """Every plate height that reaches a .rw-cardmark, read off the call sites.

    film_card() and shelf() forward their own `height` parameter, so a call that
    passes one through non-literally falls back to that function's default —
    which is the value it would render. prospect_card() hands poster_html a
    literal of its own, so poster_html's label=False call sites are read too.
    """
    heights = set()
    for name in ("film_card", "shelf"):
        func = _defined(name)
        default = _default(func, "height")
        for call in _called(name):
            given = _kwarg(call, "height")
            if isinstance(given, ast.Constant):
                heights.add(given.value)
            else:
                # height=height (shelf forwarding) or omitted: both render the
                # default unless a caller of *that* function overrode it, which
                # this loop picks up on its own pass.
                heights.add(default)
    for call in _called("poster_html"):
        label = _kwarg(call, "label")
        if isinstance(label, ast.Constant) and label.value is False:
            given = _kwarg(call, "height")
            if isinstance(given, ast.Constant):
                heights.add(given.value)
    return heights


def test_every_rendered_plate_height_has_an_overlay_rule():
    missing = sorted(_rendered_heights() - _card_heights())
    assert not missing, (
        f"plate heights {missing} are rendered but absent from _CARD_HEIGHTS, "
        "so those cards fall back to the shortest overlay and the top of the "
        "poster stops being clickable. Add them to _CARD_HEIGHTS in app.py."
    )


def test_no_stale_overlay_rules():
    """The reverse: a height nothing renders any more is dead CSS."""
    stale = sorted(_card_heights() - _rendered_heights())
    assert not stale, (
        f"_CARD_HEIGHTS lists {stale}, which no poster grid renders. "
        "Drop them so the list keeps describing the app."
    )


@pytest.mark.parametrize("name", ["film_card", "shelf"])
def test_forwarding_defaults_are_covered(name):
    """A default that isn't in the list breaks every call that omits height."""
    assert _default(_defined(name), "height") in _card_heights()


def test_marker_carries_the_height_and_the_band():
    """poster_html must stamp both, or the generated rules match nothing.

    The verdict band is 5px of card the height class does not account for, so a
    toned card needs the extra modifier to stay clickable to its top edge.
    """
    func = _defined("poster_html")
    source = ast.get_source_segment(APP.read_text(encoding="utf-8"), func)
    assert "rw-cardmark " in source
    assert "h{height}" in source
    assert "toned" in source
