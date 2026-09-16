"""
Rewatchables Explorer — Streamlit EDA app.

The entry point Streamlit runs. It loads the data once, draws the nav rail,
and hands off to an overlay or a section. Everything it calls lives in
rewatchables.app: the theme, the loaders, the session state, the components,
the analysis helpers, the three overlays and one module per section.
"""

import sqlite3
from datetime import datetime, timezone

import streamlit as st

from rewatchables import config
from rewatchables.app import theme
from rewatchables.app.analysis import person_shelf
from rewatchables.app.components import rings_svg
from rewatchables.app.context import build_context
from rewatchables.app.data import DB_PATH, stamp
from rewatchables.app.overlays.dossier import render_dossier
from rewatchables.app.overlays.keyword import render_keyword
from rewatchables.app.overlays.prospect import render_prospect
from rewatchables.app.sections import RENDERERS
from rewatchables.app.state import (
    DEFAULT_SECTION, NAV, kept, pick_section, seed_from_url,
)
from views import ANCHOR, room_long, stale_notice

# ── Config ────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Rewatchables Explorer",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# The episode list's source of truth, for the banner that says the data is
# behind it. Read through the setting step 01 uses, so the banner watches the
# workbook the pipeline actually renders. The database path comes from
# config/.env the same way; see rewatchables.app.data.
SOURCE_XLSX = config.path_setting("SOURCE_XLSX", "data/episodes.xlsx")

# ── Theme ───────────────────────────────────────────────────────────────
# The palette and the stylesheet live in rewatchables.app.theme; the CSS
# itself is theme.css beside it.

theme.inject()

# ── Data ─────────────────────────────────────────────────────────────────────
# The loaders live in rewatchables.app.data. They are called here, once, so
# every section reads the same frames.

ctx = build_context(stamp())


# ── Sidebar nav ───────────────────────────────────────────────────────────────

# A dossier is addressed by ?movie=<movie_id>, so a film can be linked directly
# and the browser Back button steps out of it. On a cold load the URL wins; from
# then on the click handler keeps the two in step.
_VALID_IDS = set(ctx.movies["movie_id"])
_VALID_UPCOMING = (set(ctx.upcoming["upcoming_film_id"])
                   if len(ctx.upcoming) else set())
_VALID_PEOPLE = (set(room_long(ctx.merged, "raw_episode_id")["person"])
                 - {ANCHOR})
seed_from_url(_VALID_IDS, ctx.keywords, _VALID_UPCOMING, _VALID_PEOPLE)
with st.sidebar:
    st.markdown(
        '<div class="rw-brand">'
        + rings_svg("")
        + "<div><b>THE<br>REWATCHABLES</b>"
        + f"<span>{len(ctx.movies)} FILMS &middot; {len(ctx.episodes)} EPS"
        + "</span></div></div>",
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # Seed the per-group widget state from the selected slug once. After this
    # the callbacks own it; re-deriving it every run would fight the click.
    st.session_state.setdefault("nav_section", DEFAULT_SECTION)
    for _gi, (_, _items) in enumerate(NAV):
        if f"nav_g{_gi}" not in st.session_state:
            st.session_state[f"nav_g{_gi}"] = next(
                (lbl for slug, lbl in _items if slug == st.session_state.nav_section),
                None,
            )

    for _gi, (_group, _items) in enumerate(NAV):
        st.markdown(
            '<div class="rw-navgroup"'
            + (' style="margin-top:0"' if _gi == 0 else "")
            + f">{_group}</div>",
            unsafe_allow_html=True,
        )
        st.radio(
            _group, [lbl for _, lbl in _items], key=f"nav_g{_gi}", index=None,
            on_change=pick_section(_gi), label_visibility="collapsed",
        )

    section = st.session_state.nav_section
    st.markdown("---")
    st.markdown(
        '<div class="rw-foot">SQLite &middot; TMDB</div>', unsafe_allow_html=True
    )


# ── Source freshness ──────────────────────────────────────────────────────────
# data/episodes.xlsx is the file that gets edited, but the app reads the
# database, which only moves when the pipeline runs. Until it does, every page
# says so, with the command that closes the gap. Read on every run rather than
# cached: it is one stat() and one indexed MAX().

def last_load_utc():
    """When step 02 last loaded the episode list, as naive UTC, or None."""
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    try:
        stamp = conn.execute(
            "SELECT MAX(sync_timestamp) FROM raw_ingest_runs").fetchone()[0]
    except sqlite3.Error:
        stamp = None
    finally:
        conn.close()
    return datetime.fromisoformat(stamp) if stamp else None


_saved = (datetime.fromtimestamp(SOURCE_XLSX.stat().st_mtime, tz=timezone.utc)
          .replace(tzinfo=None) if SOURCE_XLSX.exists() else None)
_notice = stale_notice(_saved, last_load_utc())
if _notice:
    st.markdown(_notice, unsafe_allow_html=True)


# ── Dossier overlay ───────────────────────────────────────────────────────────
# A selected film replaces the section body while the nav rail stays put, so
# Back lands you where you were. Movie Explorer handles its own gate further
# down: its filters live in the sidebar and have to keep rendering, and its
# result set is what the dossier's step arrows walk.

selected_film = st.session_state.get("dt_movie")
selected_keyword = st.session_state.get("kw_word")

# A keyword overlay covers every section, Movie Explorer included: it has no
# result set of its own to preserve, so there is nothing to keep rendering.
if selected_keyword:
    render_keyword(ctx, selected_keyword)
    st.stop()

if selected_film and section != "explorer":
    # A film opened from the Hosts & Guests lookup steps through that person's
    # films. A revisit puts one film on a shelf twice; the arrows visit it
    # once, at its newest airing. A film opened from elsewhere on the page --
    # the Without Bill grid -- is usually not on the shelf and gets no arrows.
    siblings = None
    if section == "hosts" and kept("flt_person") in _VALID_PEOPLE:
        siblings = list(dict.fromkeys(
            person_shelf(ctx.merged, kept("flt_person"))["movie_id"]))
    render_dossier(ctx, selected_film, siblings=siblings)
    st.stop()

selected_prospect = st.session_state.get("up_film")
if selected_prospect:
    render_prospect(ctx, selected_prospect)
    st.stop()


# ── Sections ────────────────────────────────────────────────────────────────
# Each section is a module with a render(ctx); the rail's slug picks one.

RENDERERS[section](ctx)
