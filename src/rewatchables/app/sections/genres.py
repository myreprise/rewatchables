"""What the show watches, by genre."""

from collections import Counter
from itertools import combinations

import pandas as pd
import plotly.express as px
import streamlit as st

from rewatchables.app.analysis import explode_genres
from rewatchables.app.charts import fold_counts, per_database, plotly_defaults
from rewatchables.app.components import film_card, masthead, tape
from rewatchables.app.state import keep
from rewatchables.app.theme import INK, INK_2, MINT_DEEP, SEQ, TAPE

# Films on the "Browse by genre" shelf, best rated first.
SHELF = 30


def genre_counts(movies_df):
    """Films per genre, commonest first."""
    counts = explode_genres(movies_df)["genre"].value_counts().reset_index()
    counts.columns = ["genre", "count"]
    return counts


def frequency(movies_df):
    fig = px.bar(
        genre_counts(movies_df), x="genre", y="count",
        color_discrete_sequence=[MINT_DEEP],
        text="count",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(xaxis_tickangle=-35)
    return plotly_defaults(fig)


def share_of_films(movies_df):
    share, cmap, order = fold_counts(genre_counts(movies_df), "genre", "count")
    fig = px.pie(
        share, values="count", names="genre",
        color="genre", color_discrete_map=cmap,
        category_orders={"genre": order},
        hole=0.4,
    )
    fig.update_layout(paper_bgcolor=INK, font_color=TAPE, legend_bgcolor=INK_2)
    return fig


def by_decade(movies_df):
    g_decade = (
        explode_genres(movies_df)
        .groupby(["decade", "genre"])
        .size()
        .reset_index(name="count")
    )
    top = genre_counts(movies_df).head(10)["genre"].tolist()
    g_decade_f = g_decade[g_decade["genre"].isin(top)]
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
    return fig


def co_occurrence(movies_df):
    """The twenty commonest genre pairs, or None if no film has two genres."""
    genre_pairs = Counter()
    for genres in movies_df["genres"]:
        for pair in combinations(sorted(genres), 2):
            genre_pairs[pair] += 1
    if not genre_pairs:
        return None
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
    return plotly_defaults(fig)


# name -> builder, in the order the section draws them.
FIGURES = {
    "frequency": frequency,
    "share": share_of_films,
    "by_decade": by_decade,
    "co_occurrence": co_occurrence,
}


def figures(movies_df):
    """name -> figure, for every chart in the section (None for one with no data)."""
    return {name: build(movies_df) for name, build in FIGURES.items()}


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
