"""Whole panels the people sections share.

Directors and Actors are the same report over two different populations, and
Hosts & Guests reuses the person panel again. Each of these renders one
complete block -- a leaderboard, a spotlight, a row of lean chips -- from
frames the caller hands in.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

from rewatchables.app.analysis import explode_cast, explode_genres, person_stats
from rewatchables.app.charts import (
    GENDER_COLOUR, _leaderboard_fig, fold_counts, per_database, plotly_defaults,
)
from rewatchables.app.components import film_card, ranked_list, stat_tiles, tape
from rewatchables.app.data import GENDER_LABEL
from rewatchables.app.theme import INK, INK_2, MINT_DEEP, TAPE
from views import lean_phrase


# ── Shared people-section components ──────────────────────────────────────────
# The Directors and Actors sections are the same report over two different
# populations, so every panel they share is rendered from here. Splitting them
# into two hand-maintained blocks is how the pair would drift apart.


def people_leaderboard(counts, name_col, title, colour=MINT_DEEP, cache_key=None,
                       db_stamp=None):
    """Ranked horizontal bars — who turns up most.

    Pass `cache_key` and `db_stamp` when `counts` depends on nothing but the
    database, to build the figure once; see per_database.
    """
    tape(title)

    def build():
        return _leaderboard_fig(counts, name_col, colour)

    fig = per_database(cache_key, db_stamp, build) if cache_key else build()
    st.plotly_chart(fig, use_container_width=True)


def gender_leaderboard_figs(df, gender_map, top_n=15, genders=("M", "F")):
    """{gender: (actors counted, figure)}, for the genders with anyone, every
    figure on one shared x-axis."""
    ranked = {g: explode_cast(df, top_n=top_n, gender=g, gender_map=gender_map).rename(
        columns={"count": "films"}) for g in genders}
    present = [g for g in genders if not ranked[g].empty]
    if not present:
        return {}
    xmax = max(ranked[g]["films"].max() for g in present)
    return {g: (len(explode_cast(df, top_n=100_000, gender=g,
                                 gender_map=gender_map)),
                _leaderboard_fig(ranked[g], "actor", GENDER_COLOUR[g], xmax=xmax))
            for g in present}


def gender_split_leaderboards(df, title, gender_map, top_n=15,
                              genders=("M", "F"), cache_key=None, db_stamp=None):
    """The same leaderboard once per gender, side by side on a shared axis.

    Why a pair and not one chart coloured by gender: the combined top 20 is 19
    men and one woman, so colouring a single ranking shows one stray bar and no
    women's ranking at all. Two columns give each population its own ranking;
    the shared axis is what keeps the comparison honest.

    `genders` defaults to the two TMDB records for nearly every credit here.
    Non-binary and unrecorded credits are counted in the tiles above rather
    than given a column of their own, which at these volumes would be a chart
    of two or three names.

    Pass `cache_key` and `db_stamp` to build the pair once per database; see
    per_database.
    """
    tape(title)

    def build():
        return gender_leaderboard_figs(df, gender_map, top_n, genders)

    columns = per_database(cache_key, db_stamp, build) if cache_key else build()
    if not columns:
        st.caption("No gender is recorded for any credited actor — run "
                   "scripts/09_enrich_metadata.py to fill curated_people.")
        return

    for col, (g, (counted, fig)) in zip(st.columns(len(columns)), columns.items()):
        with col:
            st.markdown(
                f'<p class="ch-note" style="margin:0 0 2px">'
                f'<b>{GENDER_LABEL[g]}</b> &middot; '
                f'{counted:,} actors'
                f'</p>', unsafe_allow_html=True)
            st.plotly_chart(fig, use_container_width=True, key=f"lb_gender_{g}")


def lean_chips(rows):
    """One person's leans that survived the correction, as badges.

    Mint marks a measure above the rest of the show and grey one below. The
    words carry the direction too, so colour is never the only cue.
    """
    if rows.empty:
        return '<span class="rw-lean-none">No detectable lean</span>'
    return "".join(
        f'<span class="badge{" badge-mint" if r.diff > 0 else ""}">'
        f"{lean_phrase(r.metric, r.mean_in, r.mean_out, r.diff)}</span>"
        for r in rows.sort_values(["q", "metric"], kind="mergesort").itertuples()
    )


def spotlight_figures(films):
    """The spotlight's two charts for one person's films: genre mix and decades."""
    ordered = films.sort_values("year")
    g = explode_genres(ordered)["genre"].value_counts().reset_index()
    g.columns = ["genre", "count"]
    g, cmap, order = fold_counts(g, "genre", "count")
    genres = px.pie(
        g, values="count", names="genre", color="genre",
        color_discrete_map=cmap, category_orders={"genre": order}, hole=0.45,
    )
    genres.update_layout(paper_bgcolor=INK, font_color=TAPE, legend_bgcolor=INK_2,
                         height=270, margin=dict(t=10, b=10, l=10, r=10),
                         showlegend=False)
    genres.update_traces(textinfo="label+percent", textfont_size=10)

    dec = (ordered["year"].dropna() // 10 * 10).astype(int).value_counts().sort_index()
    decades = px.bar(
        x=[f"{d}s" for d in dec.index], y=dec.to_numpy(),
        color_discrete_sequence=[MINT_DEEP], text=dec.to_numpy(),
    )
    decades.update_traces(textposition="outside", cliponaxis=False)
    decades.update_layout(height=270, margin=dict(t=10, b=10, l=10, r=10),
                          xaxis_title="", yaxis_title="", yaxis_visible=False)
    plotly_defaults(decades)
    return {"genres": genres, "decades": decades}


def person_spotlight(films, key, collab_title, collab_pairs, collab_empty,
                     collab_note=""):
    """Everything about one person: headline numbers, the posters, the shape of
    the work. Identical for a director and for an actor by design."""
    stat_tiles(person_stats(films))
    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    ordered = films.sort_values("year")
    COLS = 8
    for i in range(0, len(ordered), COLS):
        cols = st.columns(COLS)
        for col, (_, m) in zip(cols, ordered.iloc[i : i + COLS].iterrows()):
            with col:
                rt = (f"RT {m['tomatoes_avg']*100:.0f}%"
                      if pd.notna(m["tomatoes_avg"]) else "")
                film_card(m, f"{int(m['year'])} {rt}".strip(), key=key)

    # Genre and decade are always populated; the collaborator column often is
    # not, because recurring pairings are genuinely rare in this catalogue.
    figs = spotlight_figures(films)
    c_genre, c_decade, c_collab = st.columns(3)
    with c_genre:
        st.markdown("###### Genre mix")
        st.plotly_chart(figs["genres"], use_container_width=True)
    with c_decade:
        st.markdown("###### Films by decade")
        st.plotly_chart(figs["decades"], use_container_width=True)
    with c_collab:
        st.markdown(f"###### {collab_title}")
        ranked_list(collab_pairs, collab_empty, collab_note)
