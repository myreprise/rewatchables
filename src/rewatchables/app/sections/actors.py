"""The actors, ranked and profiled, and the gender split."""

from collections import Counter

import streamlit as st

from rewatchables.app.analysis import (
    PERSON_AGG, billed_long, explode_cast, films_by_actor,
)
from rewatchables.app.charts import people_scatter
from rewatchables.app.components import masthead, stat_tiles, tape
from rewatchables.app.data import GENDERS, GENDER_LABEL
from rewatchables.app.panels import (
    gender_split_leaderboards, people_leaderboard, person_spotlight,
)
from rewatchables.app.state import keep
from rewatchables.app.theme import AMBER


def render(ctx):
    GENDER_MAP = ctx.gender_map
    movies_rated = ctx.rated

    masthead(
        "Actors",
        "Who keeps turning up on screen, and the films they turn up in.",
    )

    # Counts every name in the stored cast list, so supporting and minor roles
    # land in an actor's filmography alongside the leads.
    cast_all = explode_cast(movies_rated, top_n=100_000)

    stat_tiles([
        ("Actors", f"{len(cast_all):,}"),
        ("Just one film", f"{int((cast_all['count'] == 1).sum()):,}"),
        ("Three or more", f"{int((cast_all['count'] >= 3).sum()):,}"),
        ("Five or more", f"{int((cast_all['count'] >= 5).sum()):,}"),
        ("Films covered", f"{len(movies_rated):,}"),
    ])

    # The gender row. Counted in credits, not people: a film's billed cast is
    # ten slots, and "who gets cast" is a question about slots. Rendered only
    # when the dimension is populated, so a database that has not been through
    # the cast_ids pass keeps the ungendered section it had before.
    by_gender = {g: explode_cast(movies_rated, top_n=100_000, gender=g,
                             gender_map=GENDER_MAP)
                 for g in GENDERS}
    credits_by_gender = {g: int(by_gender[g]["count"].sum()) for g in GENDERS}
    credits_total = sum(credits_by_gender.values())
    if credits_total and credits_by_gender["unknown"] < credits_total:
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        # Every gender with a credit gets a tile, including the two the split
        # below has no column for. Four non-binary credits is a small number to
        # print, and printing it is the difference between a split that omits
        # them and one that pretends they are not there. Actor counts are not
        # repeated here -- they head the two columns below.
        tiles = [(GENDER_LABEL[g],
                  f"{credits_by_gender[g]:,} · {credits_by_gender[g]/credits_total:.0%}")
                 for g in ("M", "F")]
        if credits_by_gender["NB"]:
            tiles.append((GENDER_LABEL["NB"], f"{credits_by_gender['NB']:,}"))
        tiles.append((GENDER_LABEL["unknown"], f"{credits_by_gender['unknown']:,}"))
        stat_tiles(tiles)
        st.markdown(
            '<p class="ch-note">Billed credits, not people: a film contributes '
            "ten cast slots, and who gets cast is a question about slots. One "
            "actor in five films is five credits.</p>",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    top_actors = cast_all.head(20).rename(columns={"count": "films"})
    people_leaderboard(top_actors, "actor", "Most-featured actors", colour=AMBER,
                       cache_key="actors:leaderboard", db_stamp=ctx.stamp)
    st.markdown(
        '<p class="ch-note">Every credited name TMDB lists, so a supporting turn '
        "counts the same as a lead. That widens the field considerably: "
        f"{int((cast_all['count'] == 1).sum()):,} of these "
        f"{len(cast_all):,} appear in a single film.</p>",
        unsafe_allow_html=True,
    )

    if credits_total and credits_by_gender["unknown"] < credits_total:
        st.markdown("---")

        gender_split_leaderboards(
            movies_rated, "Most-featured actors, by gender", GENDER_MAP,
            top_n=15, cache_key="actors:by_gender", db_stamp=ctx.stamp)

        # The two figures the pair is for: where the first woman lands in the
        # combined ranking, and how far apart the two peaks are.
        ranked_names = list(cast_all["actor"])
        first_woman = next(
            (i + 1 for i, n in enumerate(ranked_names)
             if GENDER_MAP.get(n) == "F"), None)
        men_top = by_gender["M"]["count"].max() if len(by_gender["M"]) else 0
        women_top = by_gender["F"]["count"].max() if len(by_gender["F"]) else 0
        st.markdown(
            '<p class="ch-note">Both columns share one x-axis, so the gap is '
            "the finding rather than a rendering accident: the most-featured "
            f"man has <b>{men_top}</b> covered films against "
            f"<b>{women_top}</b> for the most-featured woman. "
            + (f"The first woman in the combined ranking above is at "
               f"<b>#{first_woman}</b>. " if first_woman else "")
            + "Gender is what TMDB records for the credited performer; "
            f"{credits_by_gender['unknown']:,} of {credits_total:,} credits "
            "have none recorded and are counted in neither column.</p>",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    tape("Actor spotlight")
    sel_actor = keep(
        st.selectbox, "Actor", top_actors["actor"].tolist(), key="flt_actor_pick")
    actor_films = films_by_actor(movies_rated, sel_actor)

    worked_with = Counter(actor_films["director_primary"])
    worked_with.pop("Unknown", None)
    # Same "two or more" rule as the Directors spotlight. Listing the one-film
    # pairings too would fill the panel with rows that say nothing -- recurring
    # director/actor pairs are rare here, and that is the finding.
    person_spotlight(
        actor_films,
        key="actor",
        collab_title="Directors they return to",
        collab_pairs=[(n, k) for n, k in worked_with.most_common(6) if k >= 2],
        collab_empty=f"{sel_actor} has one film with each of these directors — "
                     "no repeat pairing in the catalogue.",
        collab_note="Directors of two or more of their covered films.",
    )

    st.markdown("---")

    tape("Volume against reception")
    actor_stats = (
        billed_long(movies_rated).groupby("actor").agg(**PERSON_AGG).reset_index()
    )
    actor_stats = actor_stats[actor_stats["films"] >= 3]
    people_scatter(actor_stats, "actor", "actor", name_from=8,
                   cache_key="actors:scatter", db_stamp=ctx.stamp)
    st.markdown(
        '<p class="ch-note">Actors with three or more covered films; bubble size '
        "is average runtime. Only those with eight or more are named &mdash; the "
        "rest are on hover. For actors the link between being cast often and being "
        "in well-rated films is <b>absent &mdash; r = 0.08</b>. Of "
        f"{len(cast_all):,} actors, {int((cast_all['count'] >= 8).sum())} clear "
        "eight films.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    tape("Every actor with 3+ films")
    # Gender comes in as a column here rather than as a filter: the table is
    # already sortable and searchable, so a column lets the reader slice it
    # without another widget to keep in session state.
    st.dataframe(
        actor_stats.sort_values(["films", "avg_tmdb"], ascending=[False, False])
        .assign(avg_rt=lambda d: d["avg_rt"] * 100,   # see note in Directors
                gender=lambda d: d["actor"].map(
                    lambda n: GENDER_LABEL.get(GENDER_MAP.get(n, "unknown"))))
        .rename(columns={
            "actor": "Actor", "gender": "Gender", "films": "Films",
            "avg_tmdb": "Avg TMDB",
            "avg_rt": "Avg RT", "avg_runtime": "Avg runtime",
            "first_year": "First", "last_year": "Last",
        })[["Actor", "Gender", "Films", "Avg TMDB", "Avg RT", "Avg runtime",
            "First", "Last"]],
        hide_index=True, use_container_width=True, height=420,
        column_config={
            "Avg TMDB": st.column_config.NumberColumn(format="%.2f"),
            "Avg RT": st.column_config.NumberColumn(format="%.0f%%"),
            "Avg runtime": st.column_config.NumberColumn(format="%.0f"),
            "First": st.column_config.NumberColumn(format="%d"),
            "Last": st.column_config.NumberColumn(format="%d"),
        },
    )
