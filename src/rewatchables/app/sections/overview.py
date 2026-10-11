"""Where the show is now, and a door into each part of the catalogue."""

import random

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from rewatchables import images
from rewatchables.app.analysis import explode_cast, explode_genres
from rewatchables.app.charts import plotly_defaults
from rewatchables.app.components import film_card, masthead, rings_svg, tape
from rewatchables.app.state import (
    NAV, SECTION_LABEL, SLUGS, go_section, open_dossier,
)
from rewatchables.app.theme import MINT_DEEP, MINT_DIM, TXT_3
from views import ANCHOR, html, room_long, stat_tile


# The numbers and the chart below are functions rather than lines in render()
# because the public site (pipeline step 15) prints the same ones. One
# definition keeps the two front pages from drifting apart.

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
        ("upcoming", f"{len(ctx.upcoming):,}", "in the queue",
         "Listener requests that have not aired yet, with the reason each is on the list."),
    ]


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
