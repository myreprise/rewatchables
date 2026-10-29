"""Cruise vs. Hanks: the segment, tallied.

The section's numbers and figures, free of any front end. The app draws them
in rewatchables.app.sections.verdicts; step 15 ships them to the public site.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from rewatchables.analysis import VERDICT_FLOOR
from rewatchables.figures import plotly_defaults
from rewatchables.palette import AMBER, BLUE, LINE_2, TAPE


# The bit is a modern-era feature: all but one verdict falls in a contiguous
# run from ep 350 (Mar 2024). The lone earlier one -- ep 105 -- stays in the
# ledger but is kept out of the time series, which would otherwise draw a
# five-year flat line to a single stray point.
RUN_START = 350
# A genre needs this many verdicts to appear on the genre-lean chart.
GENRE_VERDICTS = 8
# Posters in each actor's rail on the header.
RAIL = 7
STREAKS_SHOWN = 4

TAPE_ROWS = [
    ("Release year", "movie_year", "{:.1f}"),
    ("Runtime (min)", "runtime_minutes", "{:.1f}"),
    ("TMDB rating", "rating_tmdb", "{:.2f}"),
    ("Rotten Tomatoes", "tomatoes_num", "{:.1%}"),
    ("Ebert stars", "ebert_num", "{:.2f}"),
]


def standing(ch_df):
    """Verdicts in all and for each side, and the episodes they span."""
    return {
        "verdicts": len(ch_df),
        "cruise": int((ch_df["verdict"] == "Cruise").sum()),
        "hanks": int((ch_df["verdict"] == "Hanks").sum()),
        "ties": int((ch_df["verdict"] == "Tie").sum()),
        "first_ep": int(ch_df["episode_number"].min()),
        "last_ep": int(ch_df["episode_number"].max()),
    }


def the_run(ch_df):
    """The contiguous run of verdicts from RUN_START, in episode order."""
    return ch_df[ch_df["episode_number"] >= RUN_START].sort_values("episode_number")


def running_margin(ch_df):
    """(the run with a cumulative Cruise-minus-Hanks `margin`, lead changes)."""
    marg = the_run(ch_df).copy()
    marg["step"] = marg["verdict"].map({"Cruise": 1, "Hanks": -1, "Tie": 0})
    marg["margin"] = marg["step"].cumsum()
    lead_changes = int((np.sign(marg["margin"]).diff().fillna(0) != 0).sum())
    return marg, lead_changes


def films_with(movies_df, actor):
    """The covered films an actor is credited in."""
    return movies_df[movies_df["cast_names"].apply(lambda c: actor in c)]


def rail_films(movies_df, actor, limit=RAIL):
    """An actor's covered films by TMDB popularity, so "most iconic" is read
    off the data rather than hand-picked. Both men are well represented."""
    hits = films_with(movies_df, actor).dropna(subset=["poster_url_tmdb"])
    return hits.nlargest(limit, "popularity_tmdb")


def margin_figure(ch_df):
    """Cumulative Cruise-minus-Hanks. A donut can only ever show the final
    total; this is the chart that shows the lead changing hands."""
    marg, _ = running_margin(ch_df)
    # Expand to explicit step vertices so the fill can be split at zero. The
    # series only ever crosses zero on a vertical segment (x is constant there),
    # so clipping with maximum/minimum is exact -- no interpolation needed, and
    # the area above the line reads amber for Cruise, below it blue for Hanks.
    xs = np.repeat(marg["episode_number"].to_numpy(), 2)[1:]
    ys = np.repeat(marg["margin"].to_numpy(), 2)[:-1]

    fig = go.Figure()
    for clip, colour in ((np.maximum(ys, 0), "rgba(201,133,0,.28)"),
                         (np.minimum(ys, 0), "rgba(74,143,224,.28)")):
        fig.add_trace(go.Scatter(
            x=xs, y=clip, mode="lines", line=dict(width=0),
            fill="tozeroy", fillcolor=colour, hoverinfo="skip", showlegend=False,
        ))
    fig.add_trace(go.Scatter(
        x=marg["episode_number"], y=marg["margin"],
        line_shape="hv", mode="lines", line=dict(color=TAPE, width=1.6),
        customdata=np.stack([marg["movie_title"], marg["verdict"]], axis=-1),
        hovertemplate="<b>%{customdata[0]}</b><br>ep %{x} · %{customdata[1]}"
                      "<br>margin %{y:+d}<extra></extra>",
        showlegend=False, name="",
    ))
    fig.add_hline(y=0, line_color=LINE_2, line_width=1.4)
    fig.update_yaxes(title_text="← Hanks     Cruise →", zeroline=False)
    fig.update_xaxes(title_text="Episode")
    return plotly_defaults(fig)


def genre_lean_figure(ch_df):
    """The one dimension that actually separates the camps."""
    g_ch = ch_df.explode("genres").dropna(subset=["genres"])
    g_tab = (
        g_ch.pivot_table(index="genres", columns="verdict",
                         aggfunc="size", fill_value=0)
        .reindex(columns=["Cruise", "Hanks", "Tie"], fill_value=0)
    )
    g_tab["n"] = g_tab.sum(axis=1)
    g_tab = g_tab[g_tab["n"] >= GENRE_VERDICTS].copy()
    g_tab["lean"] = (g_tab["Cruise"] - g_tab["Hanks"]) / g_tab["n"]
    # Ascending lean puts the most Hanks-leaning genre first, and Plotly draws
    # the first horizontal category at the BOTTOM -- so the chart runs Cruise at
    # the top down to Hanks at the bottom.
    g_tab = g_tab.sort_values("lean")

    # Cruise reads left, Hanks right, matching the header portraits and the
    # standing bar. Cruise therefore takes the negative half of the axis.
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=g_tab.index, x=-g_tab["Cruise"], orientation="h",
        marker_color=AMBER, name="Cruise",
        text=g_tab["Cruise"], textposition="inside", insidetextanchor="start",
        hovertemplate="%{y} · Cruise %{text}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=g_tab.index, x=g_tab["Hanks"], orientation="h",
        marker_color=BLUE, name="Hanks",
        text=g_tab["Hanks"], textposition="inside", insidetextanchor="end",
        hovertemplate="%{y} · Hanks %{text}<extra></extra>",
    ))
    fig.update_layout(barmode="relative", bargap=0.3, height=34 * len(g_tab) + 120)
    fig.update_xaxes(
        title_text="← CRUISE          HANKS →",
        tickvals=[-30, -20, -10, 0, 10, 20, 30],
        ticktext=["30", "20", "10", "0", "10", "20", "30"],
    )
    fig.update_yaxes(title_text="")
    return plotly_defaults(fig, legend=True)


# name -> builder, in the order the section draws them.
FIGURES = {"running_margin": margin_figure, "genre_lean": genre_lean_figure}


def figures(ch_df):
    """name -> figure, for every chart in the section."""
    return {name: build(ch_df) for name, build in FIGURES.items()}


def tale_of_the_tape(ch_df):
    """(rows, ratios): each camp's average film, and each gap over the spread.

    Every gap here is small against the spread *within* each camp, which is the
    honest way to show a null without pulling in a hypothesis-test dependency.
    Ratios are quoted rather than asserted so this stays true as data changes.
    """
    rows, ratios = [], []
    for label, col, fmt in TAPE_ROWS:
        cv = ch_df.loc[ch_df["verdict"] == "Cruise", col].dropna()
        hv = ch_df.loc[ch_df["verdict"] == "Hanks", col].dropna()
        gap = abs(cv.mean() - hv.mean())
        spread = float(pd.concat([cv, hv]).std())
        ratios.append(gap / spread if spread else 0.0)
        rows.append({
            "Average film in each camp": label,
            "Cruise": fmt.format(cv.mean()),
            "Hanks": fmt.format(hv.mean()),
            "Gap": fmt.format(gap),
            "Spread (SD)": fmt.format(spread),
            "Gap ÷ SD": f"{ratios[-1]:.2f}",
            "Films rated": f"{len(cv)} / {len(hv)}",
        })
    return rows, ratios


def streaks(ch_df):
    """Unbroken runs of one side's verdicts in the run, longest first, as
    (verdict, length, first episode, last episode, film titles). A tie breaks
    a streak and is not one itself."""
    seq = the_run(ch_df).reset_index(drop=True)
    out, start = [], 0
    for i in range(1, len(seq) + 1):
        if i == len(seq) or seq.loc[i, "verdict"] != seq.loc[start, "verdict"]:
            out.append((seq.loc[start, "verdict"], i - start,
                        int(seq.loc[start, "episode_number"]),
                        int(seq.loc[i - 1, "episode_number"]),
                        list(seq.loc[start:i - 1, "movie_title"])))
            start = i
    out = [s for s in out if s[0] != "Tie"]
    out.sort(key=lambda t: -t[1])
    return out


def guest_split(ch_df):
    """Cruise, Hanks, Tie and n per guest on VERDICT_FLOOR+ verdict episodes."""
    guests = (
        ch_df.melt(
            id_vars=["episode_number", "verdict"],
            value_vars=["guest1", "guest2", "guest3", "guest4"],
            value_name="guest",
        )
        .dropna(subset=["guest"])
    )
    guests = guests[~guests["guest"].isin(["nan", ""])]
    tab = (
        guests.pivot_table(index="guest", columns="verdict",
                           aggfunc="size", fill_value=0)
        .reindex(columns=["Cruise", "Hanks", "Tie"], fill_value=0)
    )
    tab["n"] = tab.sum(axis=1)
    return tab[tab["n"] >= VERDICT_FLOOR].sort_values("n", ascending=False)
