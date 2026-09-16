"""Critic scores: Rotten Tomatoes, Ebert stars, TMDB."""

import plotly.express as px
import streamlit as st

from rewatchables.app.analysis import explode_genres
from rewatchables.app.charts import plotly_defaults
from rewatchables.app.components import masthead, tape
from rewatchables.app.theme import AMBER, INK, INK_2, LINE, MINT_DEEP, TAPE


def render(ctx):
    merged_df = ctx.merged
    movies_df = ctx.movies

    masthead(
        "Ratings",
        "Rotten Tomatoes, Ebert stars and TMDB audience scores, side by side.",
    )

    # Build per-episode ratings merged with movie data
    rated = merged_df.dropna(subset=["movie_id"]).copy()

    # Row 1: distribution histograms
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        tape("Rotten Tomatoes scores")
        rt_vals = rated["tomatoes_num"].dropna()
        fig = px.histogram(
            rt_vals * 100, nbins=20,
            color_discrete_sequence=[MINT_DEEP],
            labels={"value": "RT Score %"},
        )
        fig.add_vline(x=float(rt_vals.mean() * 100), line_dash="dash", line_color=TAPE,
                      annotation_text=f"avg {rt_vals.mean()*100:.1f}%")
        plotly_defaults(fig)
        st.plotly_chart(fig, use_container_width=True)

    with col_b:
        tape("Ebert star ratings")
        ebert_vals = rated["ebert_num"].dropna()
        counts = ebert_vals.value_counts().sort_index().reset_index()
        counts.columns = ["stars", "count"]
        counts["stars"] = counts["stars"].apply(lambda x: f"{'★' * int(x)}{'½' if x % 1 else ''}")
        fig = px.bar(counts, x="stars", y="count", color_discrete_sequence=[MINT_DEEP])
        plotly_defaults(fig)
        st.plotly_chart(fig, use_container_width=True)

    with col_c:
        tape("TMDB audience rating")
        tmdb_vals = movies_df["rating_tmdb"].dropna()
        fig = px.histogram(
            tmdb_vals, nbins=20,
            color_discrete_sequence=[AMBER],
            labels={"value": "TMDB Rating"},
        )
        fig.add_vline(x=float(tmdb_vals.mean()), line_dash="dash", line_color=TAPE,
                      annotation_text=f"avg {tmdb_vals.mean():.2f}")
        plotly_defaults(fig)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # RT vs TMDB scatter
    tape("Rotten Tomatoes vs TMDB rating")
    scatter_data = rated.dropna(subset=["tomatoes_num", "rating_tmdb"]).drop_duplicates("movie_id").copy()
    fig = px.scatter(
        scatter_data,
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
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Genre vs ratings box plots
    tape("RT score distribution by genre")
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
    plotly_defaults(fig)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Outlier table — high RT + low TMDB or vice versa
    tape("Ratings divergence — critics vs audience")
    div = scatter_data.copy()
    div["rt_pct"] = div["tomatoes_num"] * 100
    div["diff"] = div["rt_pct"] - (div["rating_tmdb"] * 10)
    top_critic = div.nlargest(5, "diff")[["title", "year", "rt_pct", "rating_tmdb", "diff"]]
    top_audience = div.nsmallest(5, "diff")[["title", "year", "rt_pct", "rating_tmdb", "diff"]]

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        st.markdown("**Critics love, audiences cooler on**")
        st.dataframe(
            top_critic.rename(columns={"rt_pct": "RT %", "rating_tmdb": "TMDB", "diff": "Δ"}),
            hide_index=True, use_container_width=True,
        )
    with col_d2:
        st.markdown("**Audiences love, critics cooler on**")
        st.dataframe(
            top_audience.rename(columns={"rt_pct": "RT %", "rating_tmdb": "TMDB", "diff": "Δ"}),
            hide_index=True, use_container_width=True,
        )
