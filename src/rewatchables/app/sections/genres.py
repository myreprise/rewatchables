"""What the show watches, by genre."""

from collections import Counter
from itertools import combinations

import pandas as pd
import plotly.express as px
import streamlit as st

from rewatchables.app.analysis import explode_genres
from rewatchables.app.charts import fold_counts, plotly_defaults
from rewatchables.app.components import film_card, masthead, tape
from rewatchables.app.state import keep
from rewatchables.app.theme import INK, INK_2, MINT_DEEP, SEQ, TAPE


def render(ctx):
    movies_df = ctx.movies

    masthead("Genres", "How the mix shifts across the decades they cover.")

    g_long = explode_genres(movies_df)

    # Row 1: distribution + pie
    col_a, col_b = st.columns([3, 2])

    with col_a:
        tape("Genre frequency")
        g_counts = g_long["genre"].value_counts().reset_index()
        g_counts.columns = ["genre", "count"]
        fig = px.bar(
            g_counts, x="genre", y="count",
            color_discrete_sequence=[MINT_DEEP],
            text="count",
        )
        fig.update_traces(textposition="outside")
        fig.update_layout(xaxis_tickangle=-35)
        plotly_defaults(fig)
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        tape("Share of films with each genre")
        share, cmap, order = fold_counts(g_counts, "genre", "count")
        fig = px.pie(
            share, values="count", names="genre",
            color="genre", color_discrete_map=cmap,
            category_orders={"genre": order},
            hole=0.4,
        )
        fig.update_layout(paper_bgcolor=INK, font_color=TAPE, legend_bgcolor=INK_2)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Genre by decade heatmap
    tape("Genre popularity by decade")
    g_decade = (
        explode_genres(movies_df)
        .groupby(["decade", "genre"])
        .size()
        .reset_index(name="count")
    )
    top8 = g_counts.head(10)["genre"].tolist()
    g_decade_f = g_decade[g_decade["genre"].isin(top8)]
    pivot = g_decade_f.pivot_table(index="genre", columns="decade", values="count", fill_value=0)
    pivot.columns = [f"{int(c)}s" for c in pivot.columns]

    fig = px.imshow(
        pivot,
        color_continuous_scale=SEQ,
        text_auto=True,
        aspect="auto",
    )
    fig.update_layout(
        paper_bgcolor=INK,
        font_color=TAPE,
        coloraxis_showscale=False,
        margin=dict(t=30, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Genre co-occurrence
    tape("Genre co-occurrence (films with both genres)")
    genre_pairs = Counter()
    for genres in movies_df["genres"]:
        for pair in combinations(sorted(genres), 2):
            genre_pairs[pair] += 1

    if genre_pairs:
        pair_df = pd.DataFrame(
            [(a, b, n) for (a, b), n in genre_pairs.most_common(20)],
            columns=["genre_a", "genre_b", "count"],
        )
        fig = px.bar(
            pair_df,
            x="count", y=pair_df["genre_a"] + " + " + pair_df["genre_b"],
            orientation="h",
            color_discrete_sequence=[MINT_DEEP],
            text="count",
        )
        fig.update_layout(yaxis_title="")
        fig.update_traces(textposition="outside")
        plotly_defaults(fig)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Genre-specific poster shelf
    tape("Browse by genre")
    chosen_genre = keep(
        st.selectbox, "Pick a genre", sorted(set(g_long["genre"])), key="flt_genre_shelf")
    genre_movies = movies_df[movies_df["genres"].apply(lambda g: chosen_genre in g)].sort_values("rating_tmdb", ascending=False)
    st.caption(f"{len(genre_movies)} films tagged {chosen_genre}")

    cols = st.columns(10)
    for i, (_, m) in enumerate(genre_movies.head(30).iterrows()):
        with cols[i % 10]:
            film_card(m, str(m["year"]), key="genre")
