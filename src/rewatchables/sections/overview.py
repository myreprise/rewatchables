"""Where the show is now, and a door into each part of the catalogue.

The section's numbers and figures, free of any front end. The app draws them
in rewatchables.app.sections.overview; step 15 ships them to the public site.
"""

import pandas as pd
import plotly.graph_objects as go

from rewatchables.analysis import explode_cast, explode_genres
from rewatchables.figures import plotly_defaults
from rewatchables.palette import MINT_DEEP, MINT_DIM, TXT_3
from rewatchables.presentation import ANCHOR, room_long


def show_now(episodes_df, merged_df, movies_df):
    """The headline numbers: where the show is now, and the chart's reading."""
    latest_air = episodes_df["date"].max()
    gaps = episodes_df["date"].sort_values().diff().dt.days.dropna()
    film_age = (merged_df["episode_date"].dt.year - merged_df["year"]).dropna()
    return {
        "latest_air": latest_air,
        "first_air": episodes_df["date"].min(),
        "n_last_year": int(
            (episodes_df["date"] > latest_air - pd.Timedelta(days=365)).sum()),
        "median_film_age": float(film_age.median()),
        "share_90s": 100 * float((movies_df["decade"] == 1990).mean()),
        "median_gap": float(gaps.median()),
    }


def regulars(episodes_df):
    """Everyone but Bill Simmons, counted across all five chairs.

    Returns (in_room, hosted, n_anchor): episodes per person, episodes each
    hosted, and how many Bill was on.
    """
    seats = room_long(episodes_df, "raw_episode_id")
    n_anchor = int((seats["person"] == ANCHOR).sum())
    seats = seats[seats["person"] != ANCHOR]
    in_room = seats["person"].value_counts()
    hosted = seats.loc[seats["chair"] == "host", "person"].value_counts()
    return in_room, hosted, n_anchor


def came_back_to(movies_df):
    """Every film with more than one episode, most episodes then latest first."""
    return movies_df[movies_df["total_episodes_featured"] > 1].sort_values(
        ["total_episodes_featured", "last_episode_date"], ascending=[False, False])


def episodes_per_year(episodes_df):
    """The episodes-per-year bar chart, and the counts it draws.

    Returns (fig, ep_year). The current year is a partial count, drawn dim so
    the drop at the right edge reads as "so far" rather than as a decline.
    """
    ep_year = (
        episodes_df.set_index("date").resample("YE").size().reset_index(name="count")
    )
    ep_year["year"] = ep_year["date"].dt.year
    bar_colors = [MINT_DEEP] * (len(ep_year) - 1) + [MINT_DIM]
    fig = go.Figure(go.Bar(
        x=ep_year["year"], y=ep_year["count"],
        marker_color=bar_colors, marker_line_width=0,
        text=ep_year["count"], textposition="outside",
        textfont=dict(family="IBM Plex Mono, ui-monospace, monospace", size=11),
        hovertemplate="%{x}: %{y} episodes<extra></extra>",
    ))
    fig.update_layout(
        height=280, xaxis=dict(dtick=1, title=None),
        # Headroom for the outside labels; autorange clips the tallest one.
        yaxis=dict(title="Episodes", range=[0, ep_year["count"].max() * 1.18]),
        margin=dict(t=36, r=10, b=30, l=50),
    )
    fig.add_annotation(
        x=ep_year["year"].iloc[-1], y=ep_year["count"].iloc[-1],
        text="to date", showarrow=False, yshift=26,
        font=dict(family="IBM Plex Mono, ui-monospace, monospace", size=10, color=TXT_3),
    )
    plotly_defaults(fig)
    return fig, ep_year


def doors(ctx):
    """[(section slug, number, unit, blurb)]: one door per section of the rail
    but this one, in rail order, each carrying the one number that says what
    is behind it."""
    movies_df, episodes_df = ctx.movies, ctx.episodes
    in_room, _, _ = regulars(episodes_df)
    n_genres = explode_genres(movies_df)["genre"].nunique()
    yr_min = int(episodes_df["date"].dt.year.min())
    yr_max = int(episodes_df["date"].dt.year.max())
    rt_median = episodes_df["tomatoes_num"].median()
    return [
        ("explorer", f"{len(movies_df):,}", "films",
         "Filter the whole catalogue by decade, genre, director, rating and runtime."),
        ("genres", f"{n_genres}", "genres",
         "How the mix shifts across the decades they cover, and which genres travel together."),
        ("directors", f"{movies_df['director_primary'].nunique()}", "directors",
         "Who gets called back to the chair, their genre range and each one's run on the show."),
        ("actors", f"{len(explode_cast(movies_df, top_n=100_000)):,}", "actors",
         "Who keeps turning up on screen, the films they carry and the directors they work with."),
        ("keywords", f"{len(ctx.keywords):,}", "terms",
         "TMDB's keyword tags across every film: the themes, settings and tropes that recur."),
        ("ratings", f"{rt_median * 100:.0f}", "% median RT",
         "Tomatometer, Ebert stars and TMDB scores, and where the critics and the audience split."),
        ("boxoffice", f"{int(movies_df['revenue_real'].notna().sum())}", "with a gross",
         "Budgets and grosses in today's dollars, and which films made their money back."),
        ("hosts", f"{len(in_room)}", "besides Bill",
         "Look anyone up, see who sits together, and what each regular gets booked on."),
        ("timeline", f"{yr_min}–{yr_max}", "",
         "The show year by year, how old the films were when featured, and the revisits."),
        ("verdicts", f"{len(ctx.cruise_hanks)}", "verdicts",
         "The recurring bit: which of the two is the bigger star, episode by episode."),
        ("categories", f"{ctx.categories.coverage['entries']:,}", "entries",
         "Every award and segment the show hands out, and how the room argued about it."),
        ("upcoming", f"{len(ctx.upcoming):,}", "in the queue",
         "Listener requests that have not aired yet, with the reason each is on the list."),
    ]
