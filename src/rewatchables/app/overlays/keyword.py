"""Every film carrying one keyword, and where to go next."""

from collections import Counter

import pandas as pd
import streamlit as st

from rewatchables.app.components import (
    film_card, keyword_row, rings_svg, tape,
)
from rewatchables.app.state import (
    DEFAULT_SECTION, SECTION_LABEL, close_dossier, resolve_section,
)
from views import decade_bars, html, region_of, stat_tile

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

    movie_ids = KEYWORDS.get(keyword, [])
    films = movies_df[movies_df["movie_id"].isin(movie_ids)].sort_values("year")
    origin = SECTION_LABEL[
        resolve_section(st.session_state.get("nav_section", DEFAULT_SECTION))]

    if st.button(f"← Back to {origin}", key="btn_kw_back"):
        close_dossier()
        st.rerun()

    # ── Header ──
    share = 100 * len(films) / len(movies_df)
    rail = [
        stat_tile("Films", len(films)),
        stat_tile("Of the catalogue", f"{share:.1f}", "%"),
    ]
    thin = len(films) < 3
    if thin:
        # No decade shape and no meaningful average from one or two films, so
        # the rail says how rare the keyword is instead of inventing precision.
        rail.append(stat_tile("Rarity", len(films), f" of {len(movies_df)}", coral=True))
    else:
        decades = Counter(int(y) // 10 * 10 for y in films["year"].dropna())
        peak = max(decades, key=lambda d: decades[d])
        ratings = films["rating_tmdb"].dropna()
        corpus = movies_df["rating_tmdb"].dropna().mean()
        rail.append(stat_tile("Peak decade", peak, "s"))
        rail.append(stat_tile("Avg TMDB", f"{ratings.mean():.1f}" if len(ratings) else None, "/10"))
        if len(ratings):
            rail.append(stat_tile("vs. catalogue", f"{ratings.mean() - corpus:+.1f}", coral=True))

    st.markdown(html(f"""
    <div class="rw-kw-head">
      {rings_svg()}
      <p class="rw-kw-eyebrow">Keyword</p>
      <h1>{keyword}</h1>
      <div class="rw-kw-rail">{''.join(rail)}</div>
    </div>"""), unsafe_allow_html=True)

    # The one mechanical hierarchy in the vocabulary: TMDB writes locations as
    # "city, region". It earns a line, not a browse axis of its own — "usa" is a
    # bucket and some regions have a single child.
    region = region_of(keyword)
    if region:
        siblings = [w for w in KEYWORDS if region_of(w) == region]
        if len(siblings) > 1:
            total = len({m for w in siblings for m in KEYWORDS[w]})
            st.markdown(
                f'<div class="rw-kw-tail">Part of <b>{region.title()}</b>: '
                f'{total} films across {len(siblings)} places.</div>',
                unsafe_allow_html=True,
            )

    # ── Decade signature ──
    if not thin:
        tape("When these films were made")
        spread = Counter(int(y) // 10 * 10 for y in films["year"].dropna())
        full = {d: spread.get(d, 0) for d in range(min(spread), max(spread) + 10, 10)}
        st.markdown(decade_bars(full), unsafe_allow_html=True)
        catalogue = Counter(int(y) // 10 * 10 for y in movies_df["year"].dropna())
        here = 100 * full.get(peak, 0) / len(films)
        house = 100 * catalogue.get(peak, 0) / len(movies_df)
        st.markdown(
            f'<p class="rw-kw-caption">The {peak}s hold <b>{here:.0f}%</b> of these '
            f'films, against <b>{house:.0f}%</b> of the catalogue as a whole. '
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
    partners = Counter()
    for movie_id in movie_ids:
        row = movies_df[movies_df["movie_id"] == movie_id].iloc[0]
        for word in (row["keywords"] if isinstance(row["keywords"], list) else []):
            if word != keyword:
                partners[word] += 1
    if partners:
        tape("Travels with" if not thin else "Where to go from here")
        top = [w for w, _ in partners.most_common(14)]
        keyword_row(top, "partners", REACH, current=keyword)

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
