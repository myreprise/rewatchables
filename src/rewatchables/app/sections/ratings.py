"""Critic scores: Rotten Tomatoes, Ebert stars, TMDB."""

import streamlit as st

from rewatchables.app.components import masthead, tape
from rewatchables.sections.ratings import divergence, figures

def render(ctx):
    masthead(
        "Ratings",
        "Rotten Tomatoes, Ebert stars and TMDB audience scores, side by side.",
    )
    figs = figures(ctx.merged, ctx.movies)

    # Row 1: distribution histograms
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        tape("Rotten Tomatoes scores")
        st.plotly_chart(figs["rt"], use_container_width=True)
    with col_b:
        tape("Ebert star ratings")
        st.plotly_chart(figs["ebert"], use_container_width=True)
    with col_c:
        tape("TMDB audience rating")
        st.plotly_chart(figs["tmdb"], use_container_width=True)

    st.markdown("---")

    tape("Rotten Tomatoes vs TMDB rating")
    st.plotly_chart(figs["rt_vs_tmdb"], use_container_width=True)

    st.markdown("---")

    tape("RT score distribution by genre")
    st.plotly_chart(figs["rt_by_genre"], use_container_width=True)

    st.markdown("---")

    # Outlier table — high RT + low TMDB or vice versa
    tape("Ratings divergence — critics vs audience")
    top_critic, top_audience = divergence(ctx.merged)
    shown = {"rt_pct": "RT %", "rating_tmdb": "TMDB", "diff": "Δ"}

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        st.markdown("**Critics love, audiences cooler on**")
        st.dataframe(
            top_critic.drop(columns="movie_id").rename(columns=shown),
            hide_index=True, use_container_width=True,
        )
    with col_d2:
        st.markdown("**Audiences love, critics cooler on**")
        st.dataframe(
            top_audience.drop(columns="movie_id").rename(columns=shown),
            hide_index=True, use_container_width=True,
        )
