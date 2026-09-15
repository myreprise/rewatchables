"""
Tests for poster card geometry and the card's click target.

Every poster plate is 2:3 at its column's width (.poster-img in app.py), so the
cards in a grid share one size and every card in the app shares one shape.
Nothing hands a plate a height any more: a fixed pixel height against a fluid
column width is what made plates whatever shape the viewport produced, with
object-fit:cover cropping the poster to match.

A poster card is two sibling elements: an st.markdown plate and the st.button
that carries the title strip and the click handler. The whole card is one target
only because CSS reaches the button's hit area up over the plate. That distance
is one plate height, written as a percentage margin -- percentages resolve
against width, and the button is as wide as the plate -- so it holds at every
column count with no per-grid rule. What is left to drift is the pairing of
that percentage with the aspect ratio, and that is what is pinned here.
"""

import ast
import re
from fractions import Fraction
from pathlib import Path

import pytest

APP = Path(__file__).parent.parent / "app.py"
SOURCE = APP.read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)

# The rules that stretch the strip's hit area, base and toned.
_OVERLAY = re.compile(
    r'\.rw-cardmark(\.toned)?\) div\[data-testid="stButton"\] button::after \{'
    r'[^}]*margin-top:calc\(-(\d+)% \+ (\d+)px\)'
)


def _called(name):
    """Every Call node for a plain function named `name`."""
    return [n for n in ast.walk(TREE)
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == name]


def _defined(name):
    return next(n for n in ast.walk(TREE)
                if isinstance(n, ast.FunctionDef) and n.name == name)


def _plate_ratio():
    """Height over width of a plate, from .poster-img's aspect-ratio."""
    m = re.search(r"\.poster-img \{[^}]*aspect-ratio:(\d+)/(\d+)", SOURCE)
    assert m, ".poster-img no longer declares an aspect-ratio"
    w, h = map(int, m.groups())
    return Fraction(h, w)


def _overlays():
    """{toned: (percent, px)} for the two hit-area rules."""
    found = {bool(t): (int(pct), int(px)) for t, pct, px in _OVERLAY.findall(SOURCE)}
    assert set(found) == {False, True}, (
        "expected a base and a toned button::after rule with "
        "margin-top:calc(-N% + Mpx)"
    )
    return found


def test_plates_are_poster_shaped():
    assert _plate_ratio() == Fraction(3, 2)


def test_overlay_reaches_one_plate_height():
    """-N% of the button's width is one plate up only if N matches the ratio.

    Change the aspect ratio without the overlay and the top of every poster
    stops being clickable (or the overlay reaches into the row above).
    """
    pct, px = _overlays()[False]
    assert Fraction(pct, 100) == _plate_ratio()
    assert px == 12


def test_toned_overlay_reaches_past_the_band():
    band = int(re.search(r"\.poster-rule \{ height:(\d+)px; \}", SOURCE).group(1))
    base_pct, base_px = _overlays()[False]
    toned_pct, toned_px = _overlays()[True]
    assert toned_pct == base_pct
    assert toned_px == base_px - band


@pytest.mark.parametrize(
    "name", ["poster_art", "poster_html", "film_card", "prospect_card", "shelf"])
def test_no_plate_takes_a_height(name):
    """A height parameter or argument would bring back per-grid plate shapes."""
    params = [a.arg for a in _defined(name).args.args]
    assert "height" not in params
    passing = [c.lineno for c in _called(name)
               if any(kw.arg == "height" for kw in c.keywords)]
    assert not passing, f"{name}() called with height= at lines {passing}"


def test_shelf_column_count_is_fixed():
    """One column per film made a one-film shelf a panel-wide poster."""
    cols = [n for n in ast.walk(_defined("shelf"))
            if isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "columns"]
    assert len(cols) == 1
    assert isinstance(cols[0].args[0], ast.Constant)


def test_card_is_held_to_its_column():
    """Streamlit can leave a column's contents at a stale measured width.

    It sets that width at three levels -- the inner block and each element
    container by class, the element inside by inline style -- so a clamp on the
    block alone still leaves the plate at 740x1111 in a 103px column (seen after
    switching sections). All three have to be in the rule.
    """
    block = (r'div\[data-testid="stVerticalBlock"\]:has\(> div > div > div > div > '
             r'\.rw-cardmark\)')
    container = block + r' > div\[data-testid="stElementContainer"\]'
    assert re.search(
        rf'{block},\s*{container},\s*{container} > div \{{\s*'
        r'width:100% !important; max-width:100%;',
        SOURCE,
    ), "the column clamp must cover the block, its containers and their elements"


def test_marker_carries_the_band():
    """poster_html must stamp .toned, or a banded card's top 5px go dead."""
    source = ast.get_source_segment(SOURCE, _defined("poster_html"))
    assert "rw-cardmark" in source
    assert "toned" in source
