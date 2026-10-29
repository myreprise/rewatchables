"""Everyone who sits in with Bill Simmons."""

import pandas as pd
import streamlit as st

from rewatchables.analysis import (
    GENRE_FLOOR, LEAN_FLOOR, LEAN_Q, N_PERM, VERDICT_FLOOR, person_shelf,
)
from rewatchables.app.charts import per_database
from rewatchables.app.components import (
    film_card, masthead, ranked_list, stat_tiles, tape,
)
from rewatchables.app.panels import lean_chips
from rewatchables.app.state import keep
from rewatchables.presentation import MEASURE_LABEL, lean_value
from rewatchables.sections.hosts import (
    BENCH_FLOOR, RING_TOP, WHEN_TOP, anchor_share, quiet_regulars, regular_leans,
    sits_with, the_room, top_lineups, verdict_tally, who_is_on_when_figure,
    who_sits_together_figure, without_anchor,
)


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
