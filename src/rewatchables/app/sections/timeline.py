"""The show over time, and the films it came back to."""

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from rewatchables.app.analysis import explode_genres
from rewatchables.app.charts import fold_to_series, plotly_defaults
from rewatchables.app.components import film_card, masthead, tape
from rewatchables.app.theme import MINT, MINT_DEEP, SEQ, TAPE


def render(ctx):
    episodes_df = ctx.episodes
    merged_df = ctx.merged
    movies_df = ctx.movies

    masthead(
        "Timeline &amp; Revisits",
        "When the episodes landed, how old the films were when they did, and "
        "the few they came back to.",
    )

    # Episode cadence by year (line)
    tape("Episodes per year")
    ep_year = (
        episodes_df.set_index("date").resample("YE").size().reset_index(name="count")
    )
    ep_year["year"] = ep_year["date"].dt.year
    fig = px.line(
        ep_year, x="year", y="count",
        markers=True, color_discrete_sequence=[MINT],
        labels={"year": "Year", "count": "Episodes"},
    )
    fig.update_traces(marker_size=8)
    plotly_defaults(fig)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Movie release decade stacked by genre
    tape("Films by release decade and genre")
    g_long_d = explode_genres(movies_df[movies_df["decade"].notna()].copy())
    g_long_d["genre_cat"], cmap, order = fold_to_series(g_long_d["genre"])
    decade_genre = (
        g_long_d.groupby(["decade", "genre_cat"]).size().reset_index(name="count")
    )
    decade_genre["decade_label"] = decade_genre["decade"].apply(lambda x: f"{int(x)}s")
    fig = px.bar(
        decade_genre, x="decade_label", y="count", color="genre_cat",
        color_discrete_map=cmap, category_orders={"genre_cat": order},
        labels={"decade_label": "Decade", "count": "Films", "genre_cat": "Genre"},
    )
    plotly_defaults(fig, legend=True)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Gap between film release year and episode year
    tape("How old were films when featured? (episode year − release year)")
    ep_with_year = merged_df.dropna(subset=["episode_date"]).copy()
    ep_with_year["ep_year"] = ep_with_year["episode_date"].dt.year
    ep_with_year["age_gap"] = ep_with_year["ep_year"] - ep_with_year["year"]
    age_valid = ep_with_year[ep_with_year["age_gap"].between(0, 60)]

    col_e, col_f = st.columns(2)
    with col_e:
        fig = px.histogram(
            age_valid, x="age_gap", nbins=30,
            color_discrete_sequence=[MINT_DEEP],
            labels={"age_gap": "Years since release"},
        )
        fig.add_vline(x=float(age_valid["age_gap"].median()), line_dash="dash",
                      line_color=TAPE,
                      annotation_text=f"median {age_valid['age_gap'].median():.0f} yrs")
        plotly_defaults(fig)
        st.plotly_chart(fig, use_container_width=True)
    with col_f:
        tape("Oldest films discussed")
        oldest = (
            ep_with_year
            .nlargest(10, "age_gap")[["title", "year", "ep_year", "age_gap"]]
            .drop_duplicates("title")
        )
        st.dataframe(
            oldest.rename(columns={"ep_year": "Episode year", "age_gap": "Age (yrs)"}),
            hide_index=True, use_container_width=True,
        )

    st.markdown("---")

    # TMDB rating over decades
    tape("Average TMDB rating by release decade")
    dec_rating = (
        movies_df.groupby("decade")["rating_tmdb"]
        .agg(["mean", "std", "count"])
        .reset_index()
    )
    dec_rating.columns = ["decade", "mean", "std", "count"]
    dec_rating["decade_label"] = dec_rating["decade"].apply(lambda x: f"{int(x)}s")
    dec_rating["lower"] = dec_rating["mean"] - dec_rating["std"]
    dec_rating["upper"] = dec_rating["mean"] + dec_rating["std"]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dec_rating["decade_label"], y=dec_rating["upper"],
        fill=None, mode="lines", line_color="rgba(43,232,160,0.12)", name="",
    ))
    fig.add_trace(go.Scatter(
        x=dec_rating["decade_label"], y=dec_rating["lower"],
        fill="tonexty", fillcolor="rgba(245,197,24,0.15)",
        mode="lines", line_color="rgba(43,232,160,0.12)", name="±1 std",
    ))
    fig.add_trace(go.Scatter(
        x=dec_rating["decade_label"], y=dec_rating["mean"],
        mode="lines+markers", line_color=MINT,
        marker_size=10, name="Mean TMDB",
    ))
    plotly_defaults(fig)
    fig.update_layout(showlegend=True)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # New episodes over calendar time with genre colouring
    tape("Episode timeline colored by primary genre")
    ep_genre = merged_df.dropna(subset=["episode_date", "genre_primary"]).drop_duplicates("episode_date").copy()
    ep_genre["genre_cat"], cmap, order = fold_to_series(ep_genre["genre_primary"])
    fig = px.strip(
        ep_genre.sort_values("episode_date"),
        x="episode_date", y="genre_cat",
        color="genre_cat",
        color_discrete_map=cmap, category_orders={"genre_cat": order},
        hover_data=["title"],
        labels={"episode_date": "", "genre_cat": ""},
    )
    fig.update_traces(marker_size=6, opacity=0.75)
    plotly_defaults(fig, legend=True)
    st.plotly_chart(fig, use_container_width=True)

    # ── Revisits ──
    # Was its own section; the nine films the sheet flags read better as the
    # closing movement of the timeline than as a peer of Movie Explorer.
    st.markdown("---")
    tape("Films they came back to")

    revisited = movies_df[movies_df["revisited_flag"] == 1].sort_values(
        "total_episodes_featured", ascending=False
    )
    st.markdown(
        '<div class="rw-tile"><div class="k">Revisited films</div>'
        f'<div class="v">{len(revisited)}</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # Poster grid of revisited movies
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

    # Revisits over time
    tape("When did revisits happen?")
    # Scope to films the sheet flags as revisited, so the timeline agrees with
    # the count above even if the derived is_revisit ever drifts from it.
    rev_links = merged_df[
        (merged_df["is_revisit"] == 1)
        & (merged_df["movie_id"].isin(revisited["movie_id"]))
    ].copy()
    if len(rev_links) > 0:
        rev_links["ep_year"] = rev_links["episode_date"].dt.year
        fig = px.scatter(
            rev_links,
            x="episode_date", y="title",
            color="revisit_sequence",
            color_continuous_scale=SEQ,
            size_max=12,
            hover_data=["year", "episode_date"],
            labels={"episode_date": "Episode date", "title": "", "revisit_sequence": "Revisit #"},
        )
        plotly_defaults(fig)
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No revisit episode links found.")

    st.markdown("---")

    # Time between first and last episode for revisited films
    tape("Time between first and last episode")
    revisited_gap = revisited.copy()
    revisited_gap["gap_days"] = (
        revisited_gap["last_episode_date"] - revisited_gap["first_episode_date"]
    ).dt.days
    revisited_gap = revisited_gap.dropna(subset=["gap_days"]).sort_values("gap_days", ascending=False)

    fig = px.bar(
        revisited_gap.head(20),
        x="gap_days", y="title",
        orientation="h",
        color_discrete_sequence=[MINT_DEEP],
        text=revisited_gap.head(20)["gap_days"].apply(lambda d: f"{d//365}y {(d%365)//30}m"),
        labels={"gap_days": "Days between episodes", "title": ""},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(yaxis=dict(autorange="reversed"))
    plotly_defaults(fig)
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Revisit genres
    tape("Genre breakdown of revisited films")
    rev_g = explode_genres(revisited)
    g_rev_counts = rev_g["genre"].value_counts().reset_index()
    g_rev_counts.columns = ["genre", "count"]
    fig = px.bar(
        g_rev_counts, x="genre", y="count",
        color_discrete_sequence=[MINT_DEEP],
        text="count",
    )
    fig.update_traces(textposition="outside")
    plotly_defaults(fig)
    st.plotly_chart(fig, use_container_width=True)
