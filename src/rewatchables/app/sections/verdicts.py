"""Cruise vs. Hanks: the segment, tallied."""

import pandas as pd
import streamlit as st

from rewatchables import images
from rewatchables.analysis import VERDICT_FLOOR
from rewatchables.app.charts import per_database
from rewatchables.app.components import film_card, tape
from rewatchables.app.state import keep
from rewatchables.palette import AMBER, BLUE, TXT_3
from rewatchables.sections.verdicts import (
    RUN_START, STREAKS_SHOWN, films_with, genre_lean_figure, guest_split, margin_figure,
    rail_films, running_margin, standing, streaks, tale_of_the_tape,
)

def render(ctx):
    ch_df = ctx.cruise_hanks
    movies_df = ctx.movies

    st_ = standing(ch_df)
    n_ch, n_cruise, n_hanks, n_tie = (
        st_["verdicts"], st_["cruise"], st_["hanks"], st_["ties"])
    marg, lead_changes = running_margin(ch_df)
    n_early = n_ch - len(marg)

    # ── Fight-card header ─────────────────────────────────────────────────────
    def _rail(actor, side):
        posters = "".join(
            f'<img src="{images.src(r.poster_url_tmdb, "w342")}" '
            f'alt="" loading="lazy">'
            for r in rail_films(movies_df, actor).itertuples()
        )
        return f'<div class="ch-rail {side}">{posters}</div>'

    n_cruise_films = len(films_with(movies_df, "Tom Cruise"))
    n_hanks_films = len(films_with(movies_df, "Tom Hanks"))

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
          f'<div class="bolt">EP {st_["first_ep"]} &ndash; {st_["last_ep"]}</div>'
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
    tape(f"Running margin, ep {RUN_START} &rarr; {int(marg['episode_number'].max())}")
    st.plotly_chart(per_database("verdicts:running_margin", ctx.stamp,
                                 lambda: margin_figure(ch_df)),
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

    # ── Genre lean ────────────────────────────────────────────────────────────
    tape("What actually decides it: genre")
    st.plotly_chart(per_database("verdicts:genre_lean", ctx.stamp,
                                 lambda: genre_lean_figure(ch_df)),
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
    tot, ratios = tale_of_the_tape(ch_df)
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
    cols = st.columns(STREAKS_SHOWN)
    for col, (verdict, length, ep_a, ep_b, titles) in zip(cols, streaks(ch_df)):
        colour = "#E8A21F" if verdict == "Cruise" else "#7BB0EE"
        with col:
            st.markdown(
                f'<div class="ch-streak"><div class="n" style="color:{colour}">'
                f"{length}</div>"
                f'<div class="lbl">{verdict.upper()} &middot; EP '
                f"{ep_a}&ndash;{ep_b}</div>"
                f'<div class="films">{" &middot; ".join(titles)}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ── Who's in the room ─────────────────────────────────────────────────────
    tape("Who&rsquo;s in the room")
    for name, r in guest_split(ch_df).iterrows():
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
