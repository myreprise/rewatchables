"""Plotly figures, styled the way the app styles them.

plotly_defaults is the one place the chart furniture is decided -- grid, font,
hover, margins -- so a new chart looks like the others by passing through it
rather than by copying a dozen settings. The folding helpers keep a categorical
chart inside the fixed colour series: past its length, the tail becomes one
"other" band rather than cycling colours that then mean two things at once.
"""

import streamlit as st

from rewatchables.figures import (
    people_scatter_fig,
)


@st.cache_resource(max_entries=128, show_spinner=False)
def _built_once(key, db_stamp, _build):
    return _build()


def per_database(key, db_stamp, build):
    """build(), run once per database and then shared by every rerun.

    For chart work that depends on nothing but the database. A widget change
    reruns its whole section, and rebuilding the charts that widget does not
    affect was most of what the rerun cost. Two rules keep it honest:

      * `key` must name everything besides the database that the result
        depends on, or a stale result is served;
      * the result is one shared object, so nothing may change it once it is
        returned. st.plotly_chart only reads a figure.
    """
    return _built_once(key, db_stamp, build)


def people_scatter(stats, name_col, label, name_from=4, cache_key=None,
                   db_stamp=None):
    """people_scatter_fig, drawn.

    Pass `cache_key` and `db_stamp` when `stats` depends on nothing but the
    database, to build the figure once; see per_database.
    """
    def build():
        return people_scatter_fig(stats, name_col, name_from)

    fig = per_database(cache_key, db_stamp, build) if cache_key else build()
    st.plotly_chart(fig, use_container_width=True)


