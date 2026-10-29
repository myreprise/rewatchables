"""The keyword vocabulary, browsable."""

import streamlit as st

from rewatchables.app.components import keyword_row, masthead, tape
from rewatchables.app.state import keep
from rewatchables.presentation import BROWSE_FLOOR
from rewatchables.sections.keywords import (
    SIGNATURE_DECADES, reach_bands, search_vocabulary, signature_by_decade, vocabulary,
)

def render(ctx):
    REACH = ctx.reach
    movies_df = ctx.movies

    masthead(
        "Keywords",
        "What the films are about, in the words TMDB uses. "
        "Pick one to see every film that carries it.",
    )

    vocab = vocabulary(REACH, movies_df)
    browsable = vocab["browsable"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Browsable here", f"{len(browsable):,}")
    c2.metric("Searchable", f"{vocab['searchable']:,}")
    c3.metric("Median per film", vocab["median_per_film"])
    c4.metric("On one film only", f"{vocab['single_share']:.0f}%")

    st.markdown("---")

    tape("Find a keyword")
    query = keep(st.text_input, "Search the whole vocabulary",
                 placeholder="heist, brooklyn, writer's block…", key="kw_search")
    if query:
        hits = search_vocabulary(REACH, query)
        if hits:
            st.caption(f"{len(hits)} of the {len(REACH):,} keywords match")
            keyword_row(hits, "search", REACH)
        else:
            st.caption("Nothing in the vocabulary matches that.")

    st.markdown("---")

    tape("The common vocabulary")
    st.caption(
        f"The {len(browsable)} keywords carried by {BROWSE_FLOOR} films or more. "
        f"Every one leads somewhere."
    )
    for label, low, band in reach_bands(browsable, REACH):
        st.markdown(
            f'<div class="rw-kw-legend"><span>{label}</span>'
            f'<span style="color:var(--mint-deep);">{len(band)} keywords</span></div>',
            unsafe_allow_html=True,
        )
        keyword_row(band, f"band_{low}", REACH)

    st.markdown(
        f'<div class="rw-kw-tail">The other <b>{vocab["tail"]:,}</b> keywords — including '
        f'the <b>{vocab["singles"]:,}</b> that belong to a single film — are reachable '
        'through the search above. They are genuine concepts rather than untidy '
        'duplicates, so nothing is gained by merging them away; they are simply '
        'found rather than browsed.</div>',
        unsafe_allow_html=True,
    )

    st.markdown("---")

    tape("Signature by decade")
    decade_cols = st.columns(len(SIGNATURE_DECADES))
    by_decade = {d: (n, top) for d, n, top in signature_by_decade(movies_df)}
    for col, decade in zip(decade_cols, SIGNATURE_DECADES):
        if decade not in by_decade:
            continue
        n_films, top = by_decade[decade]
        rows = "".join(f"<li><span>{w}</span><b>{n}</b></li>" for w, n in top)
        with col:
            st.markdown(
                f'<div class="rw-kw-dec"><h5>{decade}s</h5>'
                f'<span class="n">{n_films} films</span><ol>{rows}</ol></div>',
                unsafe_allow_html=True,
            )
