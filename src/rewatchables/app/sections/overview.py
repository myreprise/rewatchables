"""Where the show is now, and a door into each part of the catalogue."""

import random

import pandas as pd
import streamlit as st

from rewatchables import images
from rewatchables.app.components import film_card, masthead, rings_svg, tape
from rewatchables.app.state import go_section, open_dossier
from rewatchables.sections import NAV, SECTION_LABEL, SLUGS
from rewatchables.presentation import html, stat_tile
from rewatchables.sections.overview import (
    came_back_to, doors, episodes_per_year, regulars, show_now,
)


def render(ctx):
    KEYWORDS = ctx.keywords
    ch_df = ctx.cruise_hanks
    episodes_df = ctx.episodes
    links_df = ctx.links
    merged_df = ctx.merged
    movies_df = ctx.movies
    upcoming_df = ctx.upcoming

    masthead(
        "Every film they&rsquo;ve rewatched",
        f"{len(episodes_df):,} film episodes joined to TMDB metadata, "
        "Rotten Tomatoes scores and Ebert stars. Where the show is now, who is "
        "in the room, and a door into each part of the catalogue.",
    )

    # ── Where the show is now ──
    # The tiles carry what characterises the show rather than what sizes the
    # database. A director count says nothing a visitor can picture; "the
    # median film is 27 years old" is the whole premise in one number. The
    # catalogue's own counts sit on the doors at the bottom.
    now = show_now(episodes_df, merged_df, movies_df)
    latest_air = now["latest_air"]

    st.markdown(
        '<div class="rw-dt-rail">'
        + stat_tile("Episodes", f"{len(episodes_df):,}")
        + stat_tile("Films", f"{len(movies_df):,}")
        + stat_tile("Last 12 months", now["n_last_year"])
        + stat_tile("Median film age", f"{now['median_film_age']:.0f}", " yrs")
        + stat_tile("From the 1990s", f"{now['share_90s']:.0f}", "%")
        + stat_tile("Between episodes", f"{now['median_gap']:.0f}", " days")
        + "</div>",
        unsafe_allow_html=True,
    )

    # ── Latest episodes ──
    # The one block with a reason to change from week to week. Newest first,
    # one card per film: a film that has aired twice recently appears once,
    # under its most recent episode.
    tape("Latest episodes")
    recent = (
        links_df.sort_values("episode_date", ascending=False)
        .drop_duplicates("movie_id")
        .head(8)
        .merge(movies_df[["movie_id", "title", "year", "poster_url_tmdb"]], on="movie_id")
    )
    st.markdown(
        f'<div class="rw-kw-gridnote"><span>as of {latest_air:%B} {latest_air.day}, '
        f'{latest_air.year}</span><span>click a poster for its episodes</span></div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(8)
    for col, (_, row) in zip(cols, recent.iterrows()):
        with col:
            aired = row["episode_date"]
            film_card(
                row,
                f"Ep {int(row['episode_number'])} · {aired:%b} {aired.day}",
                key="latest",
            )

    st.markdown("---")

    # ── The regulars ──
    # Everyone but Bill Simmons, counted across all five chairs so a guest who
    # sometimes hosts is credited for every episode they were in. He is on
    # nine episodes in ten; a row led by him would say only that.
    tape("The regulars")
    n_eps = len(episodes_df)
    in_room, hosted, n_anchor = regulars(episodes_df)

    reg_cards = []
    for name, n in in_room.head(6).items():
        h = int(hosted.get(name, 0))
        hosted_txt = f" &middot; hosted {h}" if h else ""
        initials = "".join(w[0] for w in name.split()[:2]).upper()
        reg_cards.append(html(f'''
            <div class="rw-reg">
              <span class="d">{initials}</span>
              <div class="b">
                <span class="n">{name}</span>
                <span class="m"><b>{n}</b> of {n_eps}{hosted_txt}</span>
                <div class="bar"><i style="width:{100 * n / n_eps:.0f}%"></i></div>
              </div>
            </div>'''))
    st.markdown('<div class="rw-reg-row">' + "".join(reg_cards) + "</div>",
                unsafe_allow_html=True)

    note_col, go_col = st.columns([4, 1], vertical_alignment="center")
    with note_col:
        st.markdown(
            f'<p class="rw-ov-note"><b>{len(in_room)}</b> people besides Bill '
            f"Simmons have been in the room. He is on {n_anchor} of {n_eps} "
            "episodes, so he is left out of the ranking. The bar is the share of "
            "episodes each was in.</p>",
            unsafe_allow_html=True,
        )
    with go_col:
        st.button("Full room →", key="btn_ov_hosts", use_container_width=True,
                  on_click=go_section, args=("hosts",))

    st.markdown("---")

    # ── The ones they came back to ──
    # Every film with more than one episode, and nothing else. The grid used to
    # show a top twenty, but only sixteen films have ever had a second episode
    # and the maximum is three, so rows two and three were single-episode films
    # in arbitrary order dressed as a ranking.
    tape("The ones they came back to")
    again = came_back_to(movies_df)
    n_flagged = int((movies_df["revisited_flag"] == 1).sum())
    st.markdown(
        f'<p class="rw-ov-note"><b>{len(again)}</b> films have more than one '
        f'episode. The source sheet marks <b>{n_flagged}</b> films as revisits '
        'by hand; the episode count is derived from the feed, and the two are '
        'deliberately not reconciled &mdash; a second episode is not always a '
        'revisit.</p>',
        unsafe_allow_html=True,
    )
    per_row = 8
    again_rows = list(again.iterrows())
    for start in range(0, len(again_rows), per_row):
        cols = st.columns(per_row)
        for col, (_, row) in zip(cols, again_rows[start:start + per_row]):
            with col:
                last = row["last_episode_date"]
                # Eight across leaves ~100px per strip: "2× · 2026" holds one
                # line, anything carrying a month wraps on half the cards.
                when = f"{last:%Y}" if pd.notna(last) else "—"
                film_card(
                    row,
                    f"{int(row['total_episodes_featured'])}× · {when}",
                    key="again",
                )

    st.markdown("---")

    # ── Episodes per year ──
    # One chart, the one that tells the show's history at a glance. Genre and
    # decade bars used to sit here too; they are the first two charts on
    # Genres and Timeline, and a front page that repeats its own sections is a
    # front page nobody scrolls.
    tape("Episodes per year")
    fig, ep_year = episodes_per_year(episodes_df)
    first_full = ep_year[ep_year["count"] >= 50]["year"].min()

    chart_col, read_col = st.columns([3, 1.15])
    with chart_col:
        st.plotly_chart(fig, use_container_width=True)
    with read_col:
        first_air = now["first_air"]
        st.markdown(
            html(f'''
            <div class="rw-dt-panel" style="margin-top:8px">
              <p class="rw-dt-loose">Reading the chart</p>
              <ul class="rw-ov-read">
                <li><b>{first_air:%b %Y}</b>first film episode</li>
                <li><b>{int(first_full) if pd.notna(first_full) else "&mdash;"}</b>first year at fifty or more</li>
                <li><b>{now['median_gap']:.0f} days</b>median gap between episodes</li>
                <li><b>{int(ep_year["count"].iloc[-1])}</b>so far in {int(ep_year["year"].iloc[-1])}</li>
              </ul>
            </div>'''),
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── Go deeper ──
    # One door per section of the rail, in rail order and with the rail's
    # numbering, each carrying the one number that says what is behind it.
    tape("Go deeper")
    group_of = {slug: group for group, items in NAV for slug, _ in items}
    all_doors = doors(ctx)
    # Four across: eleven doors over rows of five left a single door stranded.
    per_row = 4
    for start in range(0, len(all_doors), per_row):
        cols = st.columns(per_row)
        for col, (slug, number, unit, blurb) in zip(cols, all_doors[start:start + per_row]):
            with col:
                unit_html = f"<small>{unit}</small>" if unit else ""
                st.markdown(
                    html(f'''
                    <div class="rw-door"><span class="rw-doormark"></span>
                      <span class="k">{group_of[slug]} &middot; {SLUGS.index(slug) + 1:02d}</span>
                      <span class="v">{number}{unit_html}</span>
                      <span class="t">{SECTION_LABEL[slug]}</span>
                      <p>{blurb}</p>
                    </div>'''),
                    unsafe_allow_html=True,
                )
                st.button("Open →", key=f"btn_door_{slug}", use_container_width=True,
                          on_click=go_section, args=(slug,))

    st.markdown("---")

    # ── Random spotlight ──
    # Rerolled through a seed in session state. The button used to clear
    # st.cache_data, which threw away the whole database load to pick one
    # random row.
    tape("Random spotlight")
    if "spot_seed" not in st.session_state:
        st.session_state.spot_seed = random.randrange(1 << 30)

    def _reroll():
        st.session_state.spot_seed = random.randrange(1 << 30)

    spotlight = movies_df.sample(1, random_state=st.session_state.spot_seed).iloc[0]

    def _esc(text):
        return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    art = images.src(spotlight["poster_url_tmdb"], "w342")
    poster = (
        f'<img src="{art}" alt="">' if art else
        f'<div class="poster-plate" style="height:225px;width:150px">{rings_svg("")}'
        f'<b>{_esc(spotlight["title"])}</b></div>'
    )
    meta = [m for m in [
        " &middot; ".join(spotlight["directors"]) if spotlight["directors"] else "",
        " &middot; ".join(spotlight["genres"]) if spotlight["genres"] else "",
        f"{int(spotlight['runtime_minutes'])} min" if pd.notna(spotlight["runtime_minutes"]) else "",
    ] if m]
    scores = []
    if pd.notna(spotlight["rating_tmdb"]):
        scores.append(f"TMDB <b>{spotlight['rating_tmdb']:.1f}</b>/10")
    scores.append(f"featured <b>{int(spotlight['total_episodes_featured'])}&times;</b>")
    summary = spotlight["plot_summary"] or ""
    if len(summary) > 320:
        summary = summary[:320].rsplit(" ", 1)[0] + "…"
    st.markdown(
        html(f'''
        <div class="rw-dt-panel"><div class="rw-spot">{poster}
          <div>
            <p class="h">{_esc(spotlight["title"])}<small>{spotlight["year"]}</small></p>
            <span class="m">{" &middot; ".join(meta)}</span>
            <span class="m">{" &middot; ".join(scores)}</span>
            <p>{_esc(summary) if summary else "No plot summary on file."}</p>
          </div>
        </div></div>'''),
        unsafe_allow_html=True,
    )
    b1, b2, _ = st.columns([1.2, 1.2, 4])
    with b1:
        st.button("🎲 Surprise me", key="btn_spot_reroll", use_container_width=True,
                  on_click=_reroll)
    with b2:
        if st.button("Open dossier →", key="btn_spotlight", use_container_width=True):
            open_dossier(spotlight["movie_id"])
