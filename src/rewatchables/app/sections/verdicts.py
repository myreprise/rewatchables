"""Cruise vs. Hanks: the segment, tallied."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from rewatchables import images
from rewatchables.app.analysis import VERDICT_FLOOR
from rewatchables.app.charts import per_database, plotly_defaults
from rewatchables.app.components import film_card, tape
from rewatchables.app.state import keep
from rewatchables.app.theme import AMBER, BLUE, LINE_2, TAPE, TXT_3


def render(ctx):
    ch_df = ctx.cruise_hanks
    movies_df = ctx.movies

    n_ch = len(ch_df)
    n_cruise = int((ch_df["verdict"] == "Cruise").sum())
    n_hanks = int((ch_df["verdict"] == "Hanks").sum())
    n_tie = int((ch_df["verdict"] == "Tie").sum())

    # The bit is a modern-era feature: all but one verdict falls in a contiguous
    # run from ep 350 (Mar 2024). The lone earlier one -- ep 105 -- stays in the
    # ledger but is kept out of the time series, which would otherwise draw a
    # five-year flat line to a single stray point.
    RUN_START = 350
    run = ch_df[ch_df["episode_number"] >= RUN_START].sort_values("episode_number")
    n_early = n_ch - len(run)

    # ── Fight-card header ─────────────────────────────────────────────────────
    # The poster rails are each actor's own films as covered by the podcast,
    # ranked by TMDB popularity so "most iconic" is read off the data rather
    # than hand-picked. Both men are well represented: 18 films and 11.
    def _films_with(actor, limit=7):
        hits = movies_df[movies_df["cast_names"].apply(lambda c: actor in c)]
        hits = hits.dropna(subset=["poster_url_tmdb"])
        return hits.nlargest(limit, "popularity_tmdb")

    def _rail(actor, side):
        posters = "".join(
            f'<img src="{images.src(r.poster_url_tmdb, "w342")}" '
            f'alt="" loading="lazy">'
            for r in _films_with(actor).itertuples()
        )
        return f'<div class="ch-rail {side}">{posters}</div>'

    n_cruise_films = int(movies_df["cast_names"].apply(lambda c: "Tom Cruise" in c).sum())
    n_hanks_films = int(movies_df["cast_names"].apply(lambda c: "Tom Hanks" in c).sum())

    st.markdown(
        '<div class="ch-hero">'
        + _rail("Tom Cruise", "l")
        + _rail("Tom Hanks", "r")
        + '<div class="ch-hero-inner">'
        + '<div class="ch-fighter">'
        + f'<div class="ch-face c"><img src="{images.src(images.PORTRAITS["Tom Cruise"], "w342")}" '
          'alt="Tom Cruise"></div>'
        + f'<div><div class="ch-name c">TOM<br>CRUISE</div>'
          f'<div class="ch-tally">{n_cruise}</div>'
          f'<div class="ch-sub">{n_cruise_films} films covered</div></div>'
        + "</div>"
        + '<div class="ch-vs">'
          f'<div class="bolt">EP {int(ch_df["episode_number"].min())} &ndash; '
          f'{int(ch_df["episode_number"].max())}</div>'
          '<div class="q">Who ya got?</div>'
          f'<div class="blurb">{n_tie} ties</div></div>'
        + '<div class="ch-fighter r">'
        + f'<div class="ch-face h"><img src="{images.src(images.PORTRAITS["Tom Hanks"], "w342")}" '
          'alt="Tom Hanks"></div>'
        + f'<div><div class="ch-name h">TOM<br>HANKS</div>'
          f'<div class="ch-tally">{n_hanks}</div>'
          f'<div class="ch-sub">{n_hanks_films} films covered</div></div>'
        + "</div></div></div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="ch-note" style="margin-top:14px">At the end of an episode the '
        "room picks which of the two would have been better in the film. "
        f"<b>{n_ch} verdicts</b> on the board, and it is very nearly a tie.</p>",
        unsafe_allow_html=True,
    )

    # ── Scoreboard ────────────────────────────────────────────────────────────
    # The header carries the two totals, so this is just the proportion.
    tape("The standing")
    pc, ph, pt = (100 * n / n_ch for n in (n_cruise, n_hanks, n_tie))
    st.markdown(
        f'<div class="ch-tug">'
        f'<div class="c" style="width:{pc}%">{n_cruise} &nbsp;CRUISE</div>'
        f'<div class="t" style="width:{pt}%">{n_tie}</div>'
        f'<div class="h" style="width:{ph}%">HANKS&nbsp; {n_hanks}</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<p class="ch-note">A {abs(n_cruise - n_hanks)}-verdict margin across '
        f"{n_ch} episodes. <b>Nothing here is a landslide</b> &mdash; which is why "
        "the running margin below is the more interesting picture.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── Running margin ────────────────────────────────────────────────────────
    # Cumulative Cruise-minus-Hanks. A donut can only ever show the final total;
    # this is the chart that shows the lead changing hands.
    tape(f"Running margin, ep {RUN_START} &rarr; {int(run['episode_number'].max())}")
    marg = run.copy()
    marg["step"] = marg["verdict"].map({"Cruise": 1, "Hanks": -1, "Tie": 0})
    marg["margin"] = marg["step"].cumsum()
    lead_changes = int((np.sign(marg["margin"]).diff().fillna(0) != 0).sum())

    def running_margin():
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

    st.plotly_chart(per_database("verdicts:running_margin", ctx.stamp, running_margin),
                    use_container_width=True)
    excluded = (
        f" Excludes {n_early} earlier verdict"
        f"{'' if n_early == 1 else 's'} before ep {RUN_START}."
        if n_early else ""
    )
    st.markdown(
        f'<p class="ch-note">Cumulative Cruise wins minus Hanks wins. The lead '
        f"changed hands <b>{lead_changes} times</b>; neither man was ever more than "
        f"<b>{int(marg['margin'].abs().max())} verdicts</b> clear.{excluded}</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── Genre lean — the one dimension that actually separates the camps ──────
    tape("What actually decides it: genre")
    def genre_lean():
        g_ch = ch_df.explode("genres").dropna(subset=["genres"])
        g_tab = (
            g_ch.pivot_table(index="genres", columns="verdict",
                             aggfunc="size", fill_value=0)
            .reindex(columns=["Cruise", "Hanks", "Tie"], fill_value=0)
        )
        g_tab["n"] = g_tab.sum(axis=1)
        g_tab = g_tab[g_tab["n"] >= 8].copy()
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

    st.plotly_chart(per_database("verdicts:genre_lean", ctx.stamp, genre_lean),
                    use_container_width=True)
    st.markdown(
        '<p class="ch-note">Genres with 8+ verdicts. <b>The pattern is '
        "typecasting:</b> Cruise takes the action and thriller slots, Hanks takes "
        "comedy, and everything else is close to even. Films carry multiple genres, "
        "so these buckets overlap &mdash; read it as one pattern, not one finding "
        "per row.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── Tale of the tape — reported as the null result it is ──────────────────
    tape("Tale of the tape")
    tape_rows = [
        ("Release year", "movie_year", "{:.1f}"),
        ("Runtime (min)", "runtime_minutes", "{:.1f}"),
        ("TMDB rating", "rating_tmdb", "{:.2f}"),
        ("Rotten Tomatoes", "tomatoes_num", "{:.1%}"),
        ("Ebert stars", "ebert_num", "{:.2f}"),
    ]
    # Every gap here is small against the spread *within* each camp, which is the
    # honest way to show a null without pulling in a hypothesis-test dependency.
    # Ratios are quoted rather than asserted so this stays true as data changes.
    tot, ratios = [], []
    for label, col, fmt in tape_rows:
        cv = ch_df.loc[ch_df["verdict"] == "Cruise", col].dropna()
        hv = ch_df.loc[ch_df["verdict"] == "Hanks", col].dropna()
        gap = abs(cv.mean() - hv.mean())
        spread = float(pd.concat([cv, hv]).std())
        ratios.append(gap / spread if spread else 0.0)
        tot.append({
            "Average film in each camp": label,
            "Cruise": fmt.format(cv.mean()),
            "Hanks": fmt.format(hv.mean()),
            "Gap": fmt.format(gap),
            "Spread (SD)": fmt.format(spread),
            "Gap ÷ SD": f"{ratios[-1]:.2f}",
            "Films rated": f"{len(cv)} / {len(hv)}",
        })
    st.dataframe(pd.DataFrame(tot), hide_index=True, use_container_width=True)
    st.markdown(
        '<div class="ch-null"><b>Reported as a null result.</b> Era, length and '
        "quality do not separate the two camps: the largest gap is "
        f"<b>{max(ratios):.2f} standard deviations</b>, and the rest are smaller. "
        "Differences this size are what you would expect from two random halves of "
        "the same pile. Genre is the only dimension that moves the verdict.</div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── Longest runs ──────────────────────────────────────────────────────────
    tape("Longest runs")
    seq = run.reset_index(drop=True)
    streaks, start = [], 0
    for i in range(1, len(seq) + 1):
        if i == len(seq) or seq.loc[i, "verdict"] != seq.loc[start, "verdict"]:
            streaks.append((seq.loc[start, "verdict"], i - start, start, i - 1))
            start = i
    streaks = [s for s in streaks if s[0] != "Tie"]
    streaks.sort(key=lambda t: -t[1])

    cols = st.columns(4)
    for col, (verdict, length, a, b) in zip(cols, streaks[:4]):
        colour = "#E8A21F" if verdict == "Cruise" else "#7BB0EE"
        films = " &middot; ".join(seq.loc[a:b, "movie_title"])
        with col:
            st.markdown(
                f'<div class="ch-streak"><div class="n" style="color:{colour}">'
                f"{length}</div>"
                f'<div class="lbl">{verdict.upper()} &middot; EP '
                f'{int(seq.loc[a, "episode_number"])}&ndash;'
                f'{int(seq.loc[b, "episode_number"])}</div>'
                f'<div class="films">{films}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ── Who's in the room ─────────────────────────────────────────────────────
    tape("Who&rsquo;s in the room")
    guests = (
        ch_df.melt(
            id_vars=["episode_number", "verdict"],
            value_vars=["guest1", "guest2", "guest3", "guest4"],
            value_name="guest",
        )
        .dropna(subset=["guest"])
    )
    guests = guests[~guests["guest"].isin(["nan", ""])]
    g_tab2 = (
        guests.pivot_table(index="guest", columns="verdict",
                           aggfunc="size", fill_value=0)
        .reindex(columns=["Cruise", "Hanks", "Tie"], fill_value=0)
    )
    g_tab2["n"] = g_tab2.sum(axis=1)
    g_tab2 = g_tab2[g_tab2["n"] >= VERDICT_FLOOR].sort_values("n", ascending=False)

    for name, r in g_tab2.iterrows():
        c, h, t, n = int(r["Cruise"]), int(r["Hanks"]), int(r["Tie"]), int(r["n"])
        st.markdown(
            f'<div class="ch-guest"><div class="gn">{name}</div>'
            f'<div class="bar">'
            f'<i style="width:{100*c/n}%;background:{AMBER}"></i>'
            f'<i style="width:{100*t/n}%;background:{TXT_3}"></i>'
            f'<i style="width:{100*h/n}%;background:{BLUE}"></i></div>'
            f'<div class="num">{c}&ndash;{h} &middot; n={n}</div></div>',
            unsafe_allow_html=True,
        )
    st.markdown(
        f'<p class="ch-note">Guests in {VERDICT_FLOOR}+ verdict episodes. The leans are '
        "<b>suggestive, not established</b> &mdash; at these sample sizes a couple "
        "of episodes moves any of these bars noticeably.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ── The full ledger ───────────────────────────────────────────────────────
    tape("The full ledger")
    f1, f2 = st.columns([1, 2])
    with f1:
        pick = keep(st.selectbox, "Verdict", ["All", "Cruise", "Hanks", "Tie"], key="flt_verdict")
    with f2:
        term = st.text_input("Filter by title", "")

    led = ch_df.sort_values("episode_number", ascending=False)
    if pick != "All":
        led = led[led["verdict"] == pick]
    if term:
        led = led[led["movie_title"].str.contains(term, case=False, na=False)]

    st.caption(f"{len(led)} of {n_ch} verdicts &middot; newest first")

    if led.empty:
        st.info("No verdicts match those filters.")
    else:
        # film_card wants the curated column names, and the ledger carries the
        # movie_ prefixed ones from the view.
        grid = led.rename(columns={"movie_title": "title", "movie_year": "year"})
        # Six, not the eight the other grids use: this caption carries an episode
        # number as well as a year, and at eight the titles wrap to three lines
        # and the rows go ragged.
        COLS = 6
        for i in range(0, len(grid), COLS):
            cols = st.columns(COLS)
            for col, (_, m) in zip(cols, grid.iloc[i : i + COLS].iterrows()):
                with col:
                    ep = int(m["episode_number"])
                    # The verdict rides in the caption rather than on a
                    # tooltip: the whole card is a click target now, so a
                    # title= on the plate would never surface -- and hover is
                    # not a carrier that exists on touch anyway. The band still
                    # does the scanning work; this is the text form of it, so
                    # the tag is not left to colour vision alone.
                    stamp = (f"ep {ep} · {int(m['year'])}"
                             if pd.notna(m["year"]) else f"ep {ep}")
                    film_card(
                        m, f"{stamp} · {m['verdict']}",
                        # Episode-grained: two airings of one film would collide
                        # on movie_id alone, so the episode number owns the key.
                        key=f"ledger{ep}",
                        tone=m["verdict"].lower(),
                    )
