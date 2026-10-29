"""The show over time, and the films it came back to."""

import streamlit as st

from rewatchables.app.components import film_card, masthead, tape
from rewatchables.sections.timeline import figures, oldest_discussed, revisited_films

def render(ctx):
    figs = figures(ctx.episodes, ctx.merged, ctx.movies)

    masthead(
        "Timeline &amp; Revisits",
        "When the episodes landed, how old the films were when they did, and "
        "the few they came back to.",
    )

    tape("Episodes per year")
    st.plotly_chart(figs["per_year"], use_container_width=True)

    st.markdown("---")

    tape("Films by release decade and genre")
    st.plotly_chart(figs["decade_genre"], use_container_width=True)

    st.markdown("---")

    tape("How old were films when featured? (episode year − release year)")
    col_e, col_f = st.columns(2)
    with col_e:
        st.plotly_chart(figs["age"], use_container_width=True)
    with col_f:
        tape("Oldest films discussed")
        st.dataframe(
            oldest_discussed(ctx.merged).drop(columns="movie_id")
            .rename(columns={"ep_year": "Episode year", "age_gap": "Age (yrs)"}),
            hide_index=True, use_container_width=True,
        )

    st.markdown("---")

    tape("Average TMDB rating by release decade")
    st.plotly_chart(figs["rating_by_decade"], use_container_width=True)

    st.markdown("---")

    tape("Episode timeline colored by primary genre")
    st.plotly_chart(figs["genre_strip"], use_container_width=True)

    # ── Revisits ──
    # Was its own section; the nine films the sheet flags read better as the
    # closing movement of the timeline than as a peer of Movie Explorer.
    st.markdown("---")
    tape("Films they came back to")

    revisited = revisited_films(ctx.movies)
    st.markdown(
        '<div class="rw-tile"><div class="k">Revisited films</div>'
        f'<div class="v">{len(revisited)}</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("---")

    tape("The Rewatchables hall of fame (revisited films)")
    cols = st.columns(10)
    for i, (_, m) in enumerate(revisited.iterrows()):
        with cols[i % 10]:
            film_card(
                m,
                f"{m['year']} · {m['total_episodes_featured']}×",
                key="revisit",
            )

    st.markdown("---")

    tape("When did revisits happen?")
    if figs["revisits"] is not None:
        st.plotly_chart(figs["revisits"], use_container_width=True)
    else:
        st.info("No revisit episode links found.")

    st.markdown("---")

    tape("Time between first and last episode")
    st.plotly_chart(figs["revisit_gaps"], use_container_width=True)

    st.markdown("---")

    tape("Genre breakdown of revisited films")
    st.plotly_chart(figs["revisit_genres"], use_container_width=True)
