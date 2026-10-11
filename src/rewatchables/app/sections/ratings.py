"""Critic scores: Rotten Tomatoes, Ebert stars, TMDB."""

import plotly.express as px
import streamlit as st

from rewatchables.app.analysis import explode_genres
from rewatchables.app.charts import plotly_defaults
from rewatchables.app.components import masthead, tape
from rewatchables.app.theme import AMBER, INK, INK_2, LINE, MINT_DEEP, TAPE

# Films in each of the two divergence tables.
DIVERGENT = 5


def rated_episodes(merged_df):
    """One row per airing with a film: the population every chart here reads."""
    return merged_df.dropna(subset=["movie_id"]).copy()


def scored_films(merged_df):
    """One row per film carrying both an RT score and a TMDB rating."""
    rated = rated_episodes(merged_df)
    return rated.dropna(subset=["tomatoes_num", "rating_tmdb"]).drop_duplicates("movie_id").copy()


def figures(merged_df, movies_df):
    """name -> figure, for every chart in the section."""
    rated = rated_episodes(merged_df)
    figs = {}

    rt_vals = rated["tomatoes_num"].dropna()
    fig = px.histogram(
        rt_vals * 100, nbins=20,
        color_discrete_sequence=[MINT_DEEP],
        labels={"value": "RT Score %"},
    )
    fig.add_vline(x=float(rt_vals.mean() * 100), line_dash="dash", line_color=TAPE,
                  annotation_text=f"avg {rt_vals.mean()*100:.1f}%")
    figs["rt"] = plotly_defaults(fig)

    ebert_vals = rated["ebert_num"].dropna()
    counts = ebert_vals.value_counts().sort_index().reset_index()
    counts.columns = ["stars", "count"]
    counts["stars"] = counts["stars"].apply(lambda x: f"{'★' * int(x)}{'½' if x % 1 else ''}")
    fig = px.bar(counts, x="stars", y="count", color_discrete_sequence=[MINT_DEEP])
    figs["ebert"] = plotly_defaults(fig)

    tmdb_vals = movies_df["rating_tmdb"].dropna()
    fig = px.histogram(
        tmdb_vals, nbins=20,
        color_discrete_sequence=[AMBER],
        labels={"value": "TMDB Rating"},
    )
    fig.add_vline(x=float(tmdb_vals.mean()), line_dash="dash", line_color=TAPE,
                  annotation_text=f"avg {tmdb_vals.mean():.2f}")
    figs["tmdb"] = plotly_defaults(fig)

    fig = px.scatter(
        scored_films(merged_df),
        x="tomatoes_num", y="rating_tmdb",
        color="genre_primary",
        hover_name="title",
        hover_data={"year": True, "tomatoes_num": ":.0%", "rating_tmdb": ":.1f"},
        labels={"tomatoes_num": "RT Score", "rating_tmdb": "TMDB Rating"},
        opacity=0.8,
        size_max=10,
    )
    fig.update_layout(
        paper_bgcolor=INK,
        plot_bgcolor=INK_2,
        font_color=TAPE,
        legend_bgcolor=INK_2,
        xaxis=dict(gridcolor=LINE, tickformat=".0%"),
        yaxis=dict(gridcolor=LINE),
    )
    figs["rt_vs_tmdb"] = fig

    g_rated = explode_genres(rated.dropna(subset=["tomatoes_num"]))
    top10_genres = g_rated["genre"].value_counts().head(10).index
    g_rated_f = g_rated[g_rated["genre"].isin(top10_genres)]
    fig = px.box(
        g_rated_f.sort_values("genre"),
        x="genre", y="tomatoes_num",
        color_discrete_sequence=[MINT_DEEP],
        labels={"tomatoes_num": "RT Score", "genre": ""},
        points="outliers",
    )
    fig.update_layout(showlegend=False, yaxis_tickformat=".0%")
    figs["rt_by_genre"] = plotly_defaults(fig)
    return figs


def divergence(merged_df):
    """(critics' favourites, audiences' favourites): the films where RT and
    TMDB (scaled to 100) disagree most, each way."""
    div = scored_films(merged_df)
    div["rt_pct"] = div["tomatoes_num"] * 100
    div["diff"] = div["rt_pct"] - (div["rating_tmdb"] * 10)
    cols = ["movie_id", "title", "year", "rt_pct", "rating_tmdb", "diff"]
    return div.nlargest(DIVERGENT, "diff")[cols], div.nsmallest(DIVERGENT, "diff")[cols]


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
