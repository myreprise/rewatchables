"""Everyone who sits in with Bill Simmons."""

from collections import Counter

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from rewatchables.app.analysis import (
    GENRE_FLOOR, LEAN_FLOOR, LEAN_Q, N_PERM, VERDICT_FLOOR, person_shelf,
    room_leans,
)
from rewatchables.app.charts import per_database, plotly_defaults
from rewatchables.app.components import (
    film_card, masthead, ranked_list, stat_tiles, tape,
)
from rewatchables.app.panels import lean_chips
from rewatchables.app.state import keep
from rewatchables.app.theme import INK, INK_3, MINT_DIM, SEQ, TAPE, TXT_2
from views import (
    ANCHOR, MEASURE_LABEL, appearances_by_year, bench, clean, co_appearances,
    lean_value, lineups, room_long,
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
    show on RT, film age and each of those genres."""
    eps = merged_df
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


def render(ctx):
    merged_df = ctx.merged
    movies_df = ctx.movies

    masthead(
        "Hosts &amp; Guests",
        "Everyone who sits in with Bill Simmons: look anyone up, see when they "
        "were on, who they sit with, and which films they get booked on.",
    )

    # merged_df is one row per airing -- a revisit is its own row -- and it
    # carries the film, which the lookup's posters need.
    eps = merged_df
    n_eps = len(eps)
    room, others, board = the_room(eps)
    with_anchor, anchor_hosted = anchor_share(room)
    n_without = n_eps - len(with_anchor)

    # The leans feed the lookup as well as their own panel, so they are worked
    # out up front. Cached: the permutation tests take about a second.
    regulars, tested, leans = regular_leans(eps, others, board)
    held = leans[leans["q"] < LEAN_Q]

    stat_tiles([
        ("Film episodes", f"{n_eps}"),
        ("With Bill Simmons", f"{len(with_anchor) / n_eps:.0%}"),
        ("Without him", f"{n_without}"),
        ("Everyone else", f"{len(board)}"),
        ("On five or more", f"{int((board['episodes'] >= 5).sum())}"),
    ])
    st.markdown(
        f'<p class="ch-note">Bill Simmons is on <b>{len(with_anchor)} of {n_eps}</b> '
        f"film episodes and hosts {anchor_hosted} of them, so a chart that counts "
        "him is mostly a chart of him. Every panel below leaves him out. The host "
        f"chair only tells you something on the {n_without} episodes he is not on, "
        "which close the page.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── Look someone up ──
    tape("Look someone up")
    names = board.index.tolist()
    # A stored pick naming someone no longer in the room -- a guest renamed in
    # the sheet, say -- would make the picker raise. Drop it; the top name wins.
    for k in ("flt_person", "_keep_flt_person"):
        if k in st.session_state and st.session_state[k] not in names:
            del st.session_state[k]
    pick_col, _ = st.columns([2, 3])
    with pick_col:
        who = keep(
            st.selectbox, "Person", names, key="flt_person",
            format_func=lambda n: f"{n} ({int(board.loc[n, 'episodes'])})",
        )
    # Mirrored into the URL, as a dossier is, so a lookup can be shared.
    st.query_params["person"] = who

    me = board.loc[who]
    share = me["episodes"] / n_eps
    stat_tiles([
        ("Episodes", f"{int(me['episodes'])}"),
        ("Of all episodes", f"{share:.0%}" if share >= 0.005 else "<1%"),
        ("In the host chair", f"{int(me['hosted'])}"),
        ("First on", f"{me['first']:%b %Y}"),
        ("Latest", f"{me['last']:%b %Y}"),
    ])
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    mine = person_shelf(merged_df, who).merge(
        movies_df[["movie_id", "title", "poster_url_tmdb"]], on="movie_id", how="left")
    COLS = 8
    for start in range(0, len(mine), COLS):
        cols = st.columns(COLS)
        for offset, (col, (_, m)) in enumerate(
                zip(cols, mine.iloc[start:start + COLS].iterrows())):
            with col:
                # Keyed by position, not by film: a revisit can put one film on
                # a person's shelf twice.
                film_card(
                    m, f"Ep {int(m['episode_number'])} · {m['episode_date']:%b %Y}",
                    key=f"person{start + offset}")

    ids = set(mine["raw_episode_id"])
    c_company, c_record = st.columns(2)
    with c_company:
        st.markdown("###### Who they sit with")
        company = sits_with(others, ids, who)
        ranked_list(
            [(n, int(k)) for n, k in company.head(6).items()],
            f"{who} has only ever been on with Bill.",
            note="Episodes shared, Bill aside.",
        )
    with c_record:
        st.markdown("###### What they get booked on")
        if who in regulars:
            st.markdown(
                f'<div class="chip-row">{lean_chips(held[held["person"] == who])}</div>',
                unsafe_allow_html=True)
        else:
            st.caption(f"Fewer than {LEAN_FLOOR} episodes: too few to compare with "
                       "the rest of the show.")

        st.markdown("###### Cruise vs. Hanks")
        tally = verdict_tally(eps, ids)
        n_v = int(tally.sum())
        if n_v >= VERDICT_FLOOR:
            ties = int(tally.get("Tie", 0))
            tie_txt = f", {ties} tie{'s' if ties != 1 else ''}" if ties else ""
            st.markdown(
                f'<p class="ch-note"><b>Cruise {int(tally.get("Cruise", 0))} &ndash; '
                f'Hanks {int(tally.get("Hanks", 0))}</b>{tie_txt}, across {n_v} '
                "verdict episodes.</p>",
                unsafe_allow_html=True)
        else:
            st.caption(f"{n_v} verdict episode{'s' if n_v != 1 else ''}; a record "
                       f"is read from {VERDICT_FLOOR}.")

    st.markdown("---")

    # ── The bench ──
    tape("The bench")
    listed = board[board["episodes"] >= BENCH_FLOOR].reset_index()
    st.dataframe(
        pd.DataFrame({
            "Person": listed["person"],
            "Episodes": listed["episodes"],
            "Share": listed["episodes"] / n_eps * 100,
            "Hosted": listed["hosted"],
            "First on": listed["first"],
            "Latest": listed["last"],
        }),
        hide_index=True, use_container_width=True, height=420,
        column_config={
            "Episodes": st.column_config.ProgressColumn(
                format="%d", min_value=0, max_value=int(board["episodes"].max())),
            "Share": st.column_config.NumberColumn(format="%.1f%%"),
            "First on": st.column_config.DateColumn(format="MMM YYYY"),
            "Latest": st.column_config.DateColumn(format="MMM YYYY"),
        },
    )
    st.markdown(
        f'<p class="ch-note">Everyone on {BENCH_FLOOR} or more episodes. The other '
        f"{int((board['episodes'] < BENCH_FLOOR).sum())} have been on once or twice "
        f"&mdash; {int((board['episodes'] == 1).sum())} of them just once &mdash; and "
        "every one is in the lookup above.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── Who's on when ──
    tape("Who&rsquo;s on when")
    st.plotly_chart(per_database("hosts:who_is_on_when", ctx.stamp,
                                 lambda: who_is_on_when_figure(eps, others, board)),
                    use_container_width=True)
    st.markdown(
        f'<p class="ch-note">The {WHEN_TOP} people on the most episodes, in the order '
        "they first appeared. A cell is the share of that year&rsquo;s film episodes "
        "they were on, so a light year and a busy one read on the same scale; the "
        "count under each year is how many aired. The colour tops out at 80%.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── Who sits together ──
    tape("Who sits together")
    c_grid, c_lineup = st.columns([3, 2])
    with c_grid:
        st.plotly_chart(per_database("hosts:who_sits_together", ctx.stamp,
                                     lambda: who_sits_together_figure(others, board)),
                        use_container_width=True)
    with c_lineup:
        st.markdown("###### Most common lineups")
        ranked_list(top_lineups(others), "No lineup has repeated.", wide=True)
    st.markdown(
        f'<p class="ch-note">The {RING_TOP} people on the most episodes. A cell is the '
        "number of episodes a pair shared; an empty one is a pair who have never been "
        "in the room together. A lineup is everyone in the room except Bill, so a "
        "single name is that person with Bill.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── What each regular gets booked on ──
    tape("What each regular gets booked on")
    st.markdown(
        "".join(
            f'<div class="rw-lean"><div class="n">{p}'
            f'<span>{int(board.loc[p, "episodes"])} episodes</span></div>'
            f'<div class="l">{lean_chips(held[held["person"] == p])}</div></div>'
            for p in regulars),
        unsafe_allow_html=True,
    )
    quiet = quiet_regulars(regulars, held)
    if len(quiet) > 1:
        quiet_txt = f"{', '.join(quiet[:-1])} and {quiet[-1]} show none. "
    elif quiet:
        quiet_txt = f"{quiet[0]} shows none. "
    else:
        quiet_txt = ""
    st.markdown(
        '<p class="ch-note">The sheet doesn&rsquo;t record who picked a film, so this is '
        "what each person gets <b>booked on</b>, not what they like: a guest brought in "
        "for a month of rom-coms shows a romance lean whether or not they chose the "
        f"films. Each of the {len(regulars)} people on {LEAN_FLOOR}+ episodes is "
        "compared with every episode they were not on &mdash; on Rotten Tomatoes "
        "score, the film&rsquo;s age when it aired, and the share of episodes in each "
        f"of the {len(tested)} genres on {GENRE_FLOOR}+ episodes. That is "
        f"{len(leans)} comparisons, each a {N_PERM:,}-shuffle permutation test, and a "
        "lean is shown only if it survives a Benjamini&ndash;Hochberg correction at "
        f"q &lt; {LEAN_Q}: <b>{len(held)} of {len(leans)}</b> do. {quiet_txt}"
        "Films carry several genres, so the genre comparisons overlap. Mint is above "
        "the rest of the show, grey below.</p>",
        unsafe_allow_html=True,
    )
    with st.expander(f"All {len(leans)} comparisons"):
        ordered = leans.sort_values("p")
        st.dataframe(
            pd.DataFrame({
                "Person": ordered["person"],
                "Measure": ordered["metric"].map(
                    lambda m: MEASURE_LABEL.get(m, f"{m} share")),
                "Episodes": ordered["n"],
                "Their episodes": [lean_value(m, v) for m, v
                                   in zip(ordered["metric"], ordered["mean_in"])],
                "Everyone else": [lean_value(m, v) for m, v
                                  in zip(ordered["metric"], ordered["mean_out"])],
                "Gap": [lean_value(m, v, signed=True) for m, v
                        in zip(ordered["metric"], ordered["diff"])],
                "p": ordered["p"],
                "q": ordered["q"],
                "Shown": ordered["q"] < LEAN_Q,
            }),
            hide_index=True, use_container_width=True, height=420,
            column_config={
                "p": st.column_config.NumberColumn(format="%.4f"),
                "q": st.column_config.NumberColumn(format="%.4f"),
            },
        )

    st.markdown("---")

    # ── Without Bill ──
    groups = without_anchor(eps)
    tape(f"Without Bill &mdash; {sum(len(g) for _, g in groups)} episodes")
    st.markdown(
        '<p class="ch-note">The only episodes where the host chair says something. '
        "Grouped by who hosted, busiest first; oldest episode first within each.</p>",
        unsafe_allow_html=True,
    )
    for host, group in groups:
        count = len(group)
        st.markdown(
            f'<div class="rw-kw-gridnote"><span>{host} hosting &middot; {count} '
            f'episode{"s" if count != 1 else ""}</span></div>',
            unsafe_allow_html=True,
        )
        for start in range(0, len(group), COLS):
            cols = st.columns(COLS)
            for col, (_, m) in zip(cols, group.iloc[start:start + COLS].iterrows()):
                with col:
                    film_card(
                        m, f"Ep {int(m['episode_number'])} · {m['episode_date']:%b %Y}",
                        key=f"solo{m['raw_episode_id']}")
