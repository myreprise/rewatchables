"""The show over time, and the films it came back to.

The section's numbers and figures, free of any front end. The app draws them
in rewatchables.app.sections.timeline; step 15 ships them to the public site.
"""

import plotly.express as px
import plotly.graph_objects as go

from rewatchables.analysis import explode_genres
from rewatchables.figures import fold_to_series, plotly_defaults
from rewatchables.palette import MINT, MINT_DEEP, SEQ, TAPE


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
