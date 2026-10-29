"""The app's stylesheet.

The CSS sits beside this module as theme.css rather than inside a Python
string. It is a stylesheet, not code, and Streamlit re-parses the whole script
on every rerun -- a thousand lines of CSS in app.py were a thousand lines of
that parse.

The palette is rewatchables.palette. Its colours and the CSS custom properties
in theme.css are two spellings of one set of colours and have to move together.
"""

from functools import lru_cache
from pathlib import Path

import streamlit as st

CSS_PATH = Path(__file__).parent / "theme.css"

@lru_cache(maxsize=1)
def css():
    """The stylesheet, read from disk once per process."""
    return CSS_PATH.read_text(encoding="utf-8")


def inject():
    """Put the stylesheet on the page. Called once, near the top of app.py."""
    st.markdown(f"<style>{css()}</style>", unsafe_allow_html=True)
