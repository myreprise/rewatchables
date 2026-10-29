"""The loaders in rewatchables.data, cached for the app.

Each is keyed on the database's modification time as well as its ttl, so a
pipeline run shows up on the next rerun rather than up to five minutes later.
Callers pass rewatchables.data.stamp() as `db_stamp`.
"""

import streamlit as st

from rewatchables import data

_load_data = st.cache_data(ttl=300)(data.load_data)
load_people = st.cache_data(ttl=300)(data.load_people)
load_upcoming = st.cache_data(ttl=300)(data.load_upcoming)
load_categories = st.cache_data(ttl=300)(data.load_categories)


def load_data(db_stamp=None):
    """data.load_data, cached, with its unparsed-date canary on the page."""
    frames = _load_data(db_stamp)
    unparsed = data.unparsed_dates(frames[1])
    if unparsed:
        st.warning(data.UNPARSED_DATES.format(n=unparsed))
    return frames


@st.cache_data(ttl=300)
def keyword_index(_movies, db_stamp=None):
    """data.keyword_index, once per database.

    Keyed on the stamp alone (the frame is unhashed), so two different frames
    under one stamp would share an index. Step 15 calls the uncached one on the
    frame it was given instead.
    """
    return data.keyword_index(_movies)
