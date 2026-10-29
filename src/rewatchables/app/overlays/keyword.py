"""Every film carrying one keyword, and where to go next."""

import pandas as pd
import streamlit as st

from rewatchables.app.components import film_card, keyword_row, rings_svg, tape
from rewatchables.app.state import close_dossier, resolve_section
from rewatchables.sections import DEFAULT_SECTION, SECTION_LABEL
from rewatchables.presentation import decade_bars, html, stat_tile
from rewatchables.overlays.keyword import (
    keyword_profile,
)

# ── Keyword index ─────────────────────────────────────────────────────────────

def render_keyword(ctx, keyword):
    """Every film carrying one keyword, plus where to go next.

    A keyword page must hold up even when the keyword has a single film, since
    search and shared links reach the thin ones too. The partner panel is what
    guarantees that: no keyword in the catalogue has an empty one, because the
    median film carries 17 keywords and every one of them is an exit.
    """
    movies_df, KEYWORDS = ctx.movies, ctx.keywords
    REACH = ctx.reach

    prof = keyword_profile(movies_df, KEYWORDS, keyword)
    films, thin, peak = prof["films"], prof["thin"], prof["peak"]
    origin = SECTION_LABEL[
        resolve_section(st.session_state.get("nav_section", DEFAULT_SECTION))]

    if st.button(f"← Back to {origin}", key="btn_kw_back"):
        close_dossier()
        st.rerun()

    # ── Header ──
    rail = [
        stat_tile("Films", len(films)),
        stat_tile("Of the catalogue", f"{prof['share']:.1f}", "%"),
    ]
    if thin:
        # No decade shape and no meaningful average from one or two films, so
        # the rail says how rare the keyword is instead of inventing precision.
        rail.append(stat_tile("Rarity", len(films), f" of {len(movies_df)}", coral=True))
    else:
        avg = prof["avg_tmdb"]
        rail.append(stat_tile("Peak decade", peak, "s"))
        rail.append(stat_tile("Avg TMDB", f"{avg:.1f}" if avg is not None else None, "/10"))
        if avg is not None:
            rail.append(stat_tile("vs. catalogue", f"{prof['vs_catalogue']:+.1f}", coral=True))

    st.markdown(html(f"""
    <div class="rw-kw-head">
      {rings_svg()}
      <p class="rw-kw-eyebrow">Keyword</p>
      <h1>{keyword}</h1>
      <div class="rw-kw-rail">{''.join(rail)}</div>
    </div>"""), unsafe_allow_html=True)

    if prof["region"]:
        st.markdown(
            f'<div class="rw-kw-tail">Part of <b>{prof["region"].title()}</b>: '
            f'{prof["region_films"]} films across {prof["region_places"]} places.</div>',
            unsafe_allow_html=True,
        )

    # ── Decade signature ──
    if not thin:
        tape("When these films were made")
        st.markdown(decade_bars(prof["decades"]), unsafe_allow_html=True)
        st.markdown(
            f'<p class="rw-kw-caption">The {peak}s hold <b>{prof["peak_share"]:.0f}%</b> of these '
            f'films, against <b>{prof["catalogue_peak_share"]:.0f}%</b> of the catalogue as a whole. '
            'Read the gap between those two numbers, not the shape on its own '
            '— the show covers some decades far more than others.</p>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="rw-kw-tail">Only {len(films)} film'
            f'{"s" if len(films) != 1 else ""} carries this keyword, so there is no '
            'decade shape and no average worth printing. Below is the film, and '
            'the keywords it shares with the rest of the catalogue.</div>',
            unsafe_allow_html=True,
        )

    # ── Travels with ──
    if prof["partners"]:
        tape("Travels with" if not thin else "Where to go from here")
        keyword_row(prof["partners"], "partners", REACH, current=keyword)

    # ── The films ──
    tape(f"The {len(films)} film{'s' if len(films) != 1 else ''}")
    st.markdown(
        '<div class="rw-kw-gridnote"><span>Ordered by year · oldest first</span>'
        "<span>Every poster opens that film's dossier</span></div>",
        unsafe_allow_html=True,
    )
    COLS = 8
    for start in range(0, len(films), COLS):
        cols = st.columns(COLS)
        for col, (_, film) in zip(cols, films.iloc[start:start + COLS].iterrows()):
            with col:
                rating = f"{film['rating_tmdb']:.1f}" if pd.notna(film["rating_tmdb"]) else ""
                film_card(film, f"{film['year']} {rating}", key="kw")
