"""What the show watches, by genre."""

import streamlit as st

from rewatchables.app.charts import per_database
from rewatchables.app.components import film_card, masthead, tape
from rewatchables.app.state import keep
from rewatchables.sections.genres import FIGURES, SHELF, genre_counts

def render(ctx):
    movies_df = ctx.movies

    def chart(name):
        fig = per_database(f"genres:{name}", ctx.stamp,
                           lambda: FIGURES[name](movies_df))
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)

    masthead("Genres", "How the mix shifts across the decades they cover.")

    # Row 1: distribution + pie
    col_a, col_b = st.columns([3, 2])
    with col_a:
        tape("Genre frequency")
        chart("frequency")
    with col_b:
        tape("Share of films with each genre")
        chart("share")

    st.markdown("---")

    tape("Genre popularity by decade")
    chart("by_decade")

    st.markdown("---")

    tape("Genre co-occurrence (films with both genres)")
    chart("co_occurrence")

    st.markdown("---")

    # Genre-specific poster shelf
    tape("Browse by genre")
    chosen_genre = keep(
        st.selectbox, "Pick a genre", sorted(genre_counts(movies_df)["genre"]),
        key="flt_genre_shelf")
    genre_movies = movies_df[movies_df["genres"].apply(lambda g: chosen_genre in g)].sort_values("rating_tmdb", ascending=False)
    st.caption(f"{len(genre_movies)} films tagged {chosen_genre}")

    cols = st.columns(10)
    for i, (_, m) in enumerate(genre_movies.head(SHELF).iterrows()):
        with cols[i % 10]:
            film_card(m, str(m["year"]), key="genre")
