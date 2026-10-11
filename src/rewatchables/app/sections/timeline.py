"""The show over time, and the films it came back to."""

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from rewatchables.app.analysis import explode_genres
from rewatchables.app.charts import fold_to_series, plotly_defaults
from rewatchables.app.components import film_card, masthead, tape
from rewatchables.app.theme import MINT, MINT_DEEP, SEQ, TAPE

# Rows in the "Oldest films discussed" table, before duplicates are dropped.
OLDEST = 10
# Bars on the revisit-gap chart.
GAPS_SHOWN = 20


def aired_with_age(merged_df):
    """Airings with the year they aired and the film's age then, in years."""
    ep = merged_df.dropna(subset=["episode_date"]).copy()
    ep["ep_year"] = ep["episode_date"].dt.year
    ep["age_gap"] = ep["ep_year"] - ep["year"]
    return ep


def ages_at_airing(merged_df):
    """Film ages within 0-60 years: the population the histogram reads."""
    ep = aired_with_age(merged_df)
    return ep[ep["age_gap"].between(0, 60)]


def oldest_discussed(merged_df):
    """The films furthest from release when they aired, oldest first."""
    return (
        aired_with_age(merged_df)
        .nlargest(OLDEST, "age_gap")[["movie_id", "title", "year", "ep_year", "age_gap"]]
        .drop_duplicates("title")
    )


def revisited_films(movies_df):
    """The films the source sheet flags as revisited, most episodes first."""
    return movies_df[movies_df["revisited_flag"] == 1].sort_values(
        "total_episodes_featured", ascending=False
    )


def figures(episodes_df, merged_df, movies_df):
    """name -> figure, for every chart in the section. The revisit scatter is
    None when no revisit episode is linked."""
    figs = {}

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
    figs["per_year"] = plotly_defaults(fig)

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
    figs["decade_genre"] = plotly_defaults(fig, legend=True)

    age_valid = ages_at_airing(merged_df)
    fig = px.histogram(
        age_valid, x="age_gap", nbins=30,
        color_discrete_sequence=[MINT_DEEP],
        labels={"age_gap": "Years since release"},
    )
    fig.add_vline(x=float(age_valid["age_gap"].median()), line_dash="dash",
                  line_color=TAPE,
                  annotation_text=f"median {age_valid['age_gap'].median():.0f} yrs")
    figs["age"] = plotly_defaults(fig)

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
    figs["rating_by_decade"] = fig

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
    figs["genre_strip"] = plotly_defaults(fig, legend=True)

    revisited = revisited_films(movies_df)
    # Scoped to films the sheet flags as revisited, so the timeline agrees with
    # the count even if the derived is_revisit ever drifts from it.
    rev_links = merged_df[
        (merged_df["is_revisit"] == 1)
        & (merged_df["movie_id"].isin(revisited["movie_id"]))
    ].copy()
    figs["revisits"] = None
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
        figs["revisits"] = plotly_defaults(fig)

    revisited_gap = revisited.copy()
    revisited_gap["gap_days"] = (
        revisited_gap["last_episode_date"] - revisited_gap["first_episode_date"]
    ).dt.days
    revisited_gap = revisited_gap.dropna(subset=["gap_days"]).sort_values("gap_days", ascending=False)
    shown = revisited_gap.head(GAPS_SHOWN)
    fig = px.bar(
        shown,
        x="gap_days", y="title",
        orientation="h",
        color_discrete_sequence=[MINT_DEEP],
        text=shown["gap_days"].apply(lambda d: f"{d//365}y {(d%365)//30}m"),
        labels={"gap_days": "Days between episodes", "title": ""},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(yaxis=dict(autorange="reversed"))
    figs["revisit_gaps"] = plotly_defaults(fig)

    g_rev_counts = explode_genres(revisited)["genre"].value_counts().reset_index()
    g_rev_counts.columns = ["genre", "count"]
    fig = px.bar(
        g_rev_counts, x="genre", y="count",
        color_discrete_sequence=[MINT_DEEP],
        text="count",
    )
    fig.update_traces(textposition="outside")
    figs["revisit_genres"] = plotly_defaults(fig)
    return figs


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
