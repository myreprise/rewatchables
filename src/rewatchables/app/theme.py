"""The app's palette and stylesheet.

The CSS sits beside this module as theme.css rather than inside a Python
string. It is a stylesheet, not code, and Streamlit re-parses the whole script
on every rerun -- a thousand lines of CSS in app.py were a thousand lines of
that parse.

The palette is here too, because the Python side and the CSS custom properties
in theme.css are two spellings of one set of colours and have to move together.
"""

from functools import lru_cache
from pathlib import Path

import streamlit as st

CSS_PATH = Path(__file__).parent / "theme.css"

# Palette — derived from The Rewatchables artwork (mint field, ring black, tape white).
INK, INK_2, INK_3, INK_4 = "#0B0D0C", "#101211", "#171A18", "#1E221F"
LINE, LINE_2 = "#262B28", "#333934"
MINT, MINT_DEEP, MINT_DIM = "#2BE8A0", "#17A87C", "#0D6249"
TAPE, TAPE_2, CORAL = "#F2EFE6", "#D9D5C9", "#E2624F"
TXT_2, TXT_3 = "#9AA39D", "#6B736E"

# Categorical series, assigned in this fixed order and never cycled. The ordering
# was chosen by running candidates through a colour-vision validator: worst
# adjacent pair scores dE 10.2 under protanopia against the #101211 surface.
AMBER, BLUE, VIOLET, MAGENTA = "#C98500", "#4A8FE0", "#9085E9", "#D55181"
SERIES = [MINT_DEEP, AMBER, BLUE, CORAL, VIOLET, MAGENTA]

# Sequential ramp for magnitude — one hue, receding into the surface at the low end.
SEQ = ["#0D6249", "#14906C", "#1CBD8C", "#43D9A7", "#79E9C2", "#B6F5DC"]


@lru_cache(maxsize=1)
def css():
    """The stylesheet, read from disk once per process."""
    return CSS_PATH.read_text(encoding="utf-8")


def inject():
    """Put the stylesheet on the page. Called once, near the top of app.py."""
    st.markdown(f"<style>{css()}</style>", unsafe_allow_html=True)
