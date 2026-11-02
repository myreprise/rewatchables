"""Everyone who sits in with Bill Simmons.

The section's numbers and figures, free of any front end. The app draws them
in rewatchables.app.sections.hosts; step 15 ships them to the public site.
"""

from collections import Counter

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from rewatchables.analysis import GENRE_FLOOR, LEAN_FLOOR, room_leans
from rewatchables.figures import plotly_defaults
from rewatchables.palette import INK, INK_3, MINT_DIM, SEQ, TAPE, TXT_2
from rewatchables.presentation import (
    ANCHOR, appearances_by_year, bench, clean, co_appearances, lineups, room_long,
)


# The bench table stops here. The one- and two-timers are most of the names
# and none of the pattern, and the lookup still has every one of them.
BENCH_FLOOR = 3

RING_TOP = 12

WHEN_TOP = 15


def the_room(merged_df):
    """(room, others, board): everyone in the room per airing, the same with
    Bill Simmons left out, and the bench of everyone else.

    merged_df is one row per airing, so a revisit is its own episode.
    """
    room = room_long(merged_df, "raw_episode_id",
                     keep=("episode_number", "episode_date", "movie_id"))
    others = room[room["person"] != ANCHOR]
    board = bench(others, "raw_episode_id", "episode_date")
    return room, others, board


def regular_leans(merged_df, others, board):
    """(regulars, tested, leans): the people on LEAN_FLOOR+ episodes, the
    genres common enough to test, and every regular against the rest of the
    show on RT, film age and each of those genres.

    Sorted by airing first, because the permutation test assigns its shuffles
    by row position: the same episodes in another order are another draw, which
    moves a p-value enough to carry a lean across LEAN_Q."""
    eps = merged_df.sort_values(["episode_date", "episode_number"], kind="mergesort")
    regulars = board.index[board["episodes"] >= LEAN_FLOOR].tolist()
    reach = Counter(g for gs in eps["genres"] if isinstance(gs, list) for g in gs)
    tested = [g for g, n in reach.most_common() if n >= GENRE_FLOOR]
    film_year = pd.to_numeric(eps["year"], errors="coerce")
    measures = pd.DataFrame({
        "rt": eps["tomatoes_num"].astype(float).to_numpy(),
        "age": (eps["episode_date"].dt.year - film_year).astype(float).to_numpy(),
    })
    for g in tested:
        measures[g] = eps["genres"].map(
            lambda gs, g=g: isinstance(gs, list) and g in gs).astype(float).to_numpy()
    on_ids = others.groupby("person")["raw_episode_id"].agg(set)
    members = pd.DataFrame({
        p: eps["raw_episode_id"].isin(on_ids[p]).to_numpy() for p in regulars})
    return regulars, tested, room_leans(measures, members)


def sits_with(others, ids, who):
    """Episodes shared with each other person across `ids`, most first."""
    return others.loc[others["raw_episode_id"].isin(ids)
                      & (others["person"] != who), "person"].value_counts()


def verdict_tally(merged_df, ids):
    """Cruise / Hanks / Tie counts over the airings in `ids`."""
    verdicts = merged_df.loc[merged_df["raw_episode_id"].isin(ids), "cruise_hanks"].map(clean)
    return verdicts.dropna().value_counts()


def anchor_share(room):
    """(airings with the anchor, of them in the host chair)."""
    is_anchor = room["person"] == ANCHOR
    with_anchor = set(room.loc[is_anchor, "raw_episode_id"])
    hosted = int((is_anchor & (room["chair"] == "host")).sum())
    return with_anchor, hosted


def without_anchor(merged_df):
    """[(host, airings)] for the airings without the anchor, busiest host
    first, oldest airing first within each."""
    room, _, _ = the_room(merged_df)
    with_anchor, _ = anchor_share(room)
    solo = merged_df[~merged_df["raw_episode_id"].isin(with_anchor)].sort_values("episode_date")
    solo_host = solo["host"].fillna("No host listed")
    return [(host, solo[solo_host == host]) for host in solo_host.value_counts().index]


def quiet_regulars(regulars, held):
    """The regulars with no lean that survives the correction."""
    return [p for p in regulars if p not in set(held["person"])]


def who_is_on_when_figure(merged_df, others, board):
    """The WHEN_TOP busiest people by year, as a share of that year's episodes."""
    on, aired = appearances_by_year(others, merged_df, "raw_episode_id", "episode_date")
    cast = board.head(WHEN_TOP).sort_values("first").index.tolist()
    counts = on.reindex(cast).fillna(0)
    years = [str(int(y)) for y in aired.index]
    fig = go.Figure(go.Heatmap(
        z=counts.to_numpy() / aired.to_numpy() * 100,
        x=years, y=cast,
        customdata=np.dstack([counts.to_numpy(),
                              np.tile(aired.to_numpy(), (len(cast), 1))]),
        hovertemplate="%{y}, %{x}<br>%{customdata[0]:.0f} of %{customdata[1]:.0f} "
                      "episodes (%{z:.0f}%)<extra></extra>",
        # Zero gets the surface colour and anything above it the first step,
        # so "never on that year" and "on once" do not blur together.
        colorscale=[[0, INK_3], [0.001, SEQ[0]], [0.2, SEQ[1]], [0.4, SEQ[2]],
                    [0.6, SEQ[3]], [0.8, SEQ[4]], [1, SEQ[5]]],
        zmin=0, zmax=80, xgap=2, ygap=2,
        colorbar=dict(ticksuffix="%", outlinewidth=0, thickness=10,
                      tickfont=dict(color=TXT_2)),
    ))
    plotly_defaults(fig)
    fig.update_layout(
        height=30 * len(cast) + 120,
        yaxis=dict(autorange="reversed", gridcolor=INK, title=""),
        xaxis=dict(tickvals=years, gridcolor=INK, title="",
                   ticktext=[f"{y}<br>{int(n)} eps" for y, n in zip(years, aired)]),
    )
    return fig


def who_sits_together_figure(others, board):
    """Episodes shared by each pair of the RING_TOP busiest people."""
    ring = board.head(RING_TOP).index.tolist()
    pairs = co_appearances(others, "raw_episode_id")
    shared = np.array([[np.nan if a == b else pairs.get(tuple(sorted((a, b))), 0)
                        for b in ring] for a in ring], dtype=float)
    fig = go.Figure(go.Heatmap(
        # Square-root colour: the top pair shares three times the episodes
        # of the next, so a linear ramp lights one cell and leaves the rest
        # near black.
        z=np.sqrt(shared), x=ring, y=ring, customdata=shared,
        text=[["" if not v or np.isnan(v) else f"{v:.0f}" for v in row]
              for row in shared],
        texttemplate="%{text}", textfont=dict(color=TAPE, size=11),
        hovertemplate="%{y} + %{x}<br>%{customdata:.0f} episodes together"
                      "<extra></extra>",
        hoverongaps=False,
        colorscale=[[0, INK_3], [0.001, MINT_DIM], [1, SEQ[1]]],
        showscale=False, xgap=2, ygap=2,
    ))
    plotly_defaults(fig)
    fig.update_layout(
        height=34 * len(ring) + 130,
        yaxis=dict(autorange="reversed", gridcolor=INK, title=""),
        xaxis=dict(tickangle=-40, gridcolor=INK, title=""),
    )
    return fig


def top_lineups(others, n=10):
    """(lineup, episodes) for the n commonest panels, Bill aside."""
    return [(lineup, int(k)) for lineup, k in lineups(others, "raw_episode_id").head(n).items()]


def figures(merged_df):
    """name -> figure, for the section's two heatmaps."""
    _, others, board = the_room(merged_df)
    return {"who_is_on_when": who_is_on_when_figure(merged_df, others, board),
            "who_sits_together": who_sits_together_figure(others, board)}
