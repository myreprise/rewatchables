"""The actors, ranked and profiled, and the gender split."""

import streamlit as st

from rewatchables.analysis import films_by_actor
from rewatchables.app.charts import per_database
from rewatchables.app.components import masthead, stat_tiles, tape
from rewatchables.data import GENDER_LABEL
from rewatchables.app.panels import gender_split_leaderboards, person_spotlight
from rewatchables.app.state import keep
from rewatchables.sections.actors import (
    GENDER_TOP, NAMED_FROM, cast_counts, directors_returned_to, gender_credits,
    gender_peaks, has_genders, leaderboard_figure, ranked_actors, scatter_figure,
    top_actors, volume_reception,
)

def render(ctx):
    GENDER_MAP = ctx.gender_map
    movies_rated = ctx.rated

    masthead(
        "Actors",
        "Who keeps turning up on screen, and the films they turn up in.",
    )

    cast_all = cast_counts(movies_rated)

    stat_tiles([
        ("Actors", f"{len(cast_all):,}"),
        ("Just one film", f"{int((cast_all['count'] == 1).sum()):,}"),
        ("Three or more", f"{int((cast_all['count'] >= 3).sum()):,}"),
        ("Five or more", f"{int((cast_all['count'] >= 5).sum()):,}"),
        ("Films covered", f"{len(movies_rated):,}"),
    ])

    # The gender row, rendered only when the dimension is populated.
    credits_by_gender = gender_credits(movies_rated, GENDER_MAP)
    credits_total = sum(credits_by_gender.values())
    gendered = has_genders(credits_by_gender)
    if gendered:
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

    tape("Most-featured actors")
    st.plotly_chart(per_database("actors:leaderboard", ctx.stamp,
                                 lambda: leaderboard_figure(movies_rated)),
                    use_container_width=True)
    st.markdown(
        '<p class="ch-note">Every credited name TMDB lists, so a supporting turn '
        "counts the same as a lead. That widens the field considerably: "
        f"{int((cast_all['count'] == 1).sum()):,} of these "
        f"{len(cast_all):,} appear in a single film.</p>",
        unsafe_allow_html=True,
    )

    if gendered:
        st.markdown("---")

        gender_split_leaderboards(
            movies_rated, "Most-featured actors, by gender", GENDER_MAP,
            top_n=GENDER_TOP, cache_key="actors:by_gender", db_stamp=ctx.stamp)

        # The two figures the pair is for: where the first woman lands in the
        # combined ranking, and how far apart the two peaks are.
        men_top, women_top, first_woman = gender_peaks(movies_rated, GENDER_MAP)
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
        st.selectbox, "Actor", top_actors(movies_rated)["actor"].tolist(),
        key="flt_actor_pick")
    actor_films = films_by_actor(movies_rated, sel_actor)
    person_spotlight(
        actor_films,
        key="actor",
        collab_title="Directors they return to",
        collab_pairs=directors_returned_to(actor_films),
        collab_empty=f"{sel_actor} has one film with each of these directors — "
                     "no repeat pairing in the catalogue.",
        collab_note="Directors of two or more of their covered films.",
    )

    st.markdown("---")

    tape("Volume against reception")
    st.plotly_chart(per_database("actors:scatter", ctx.stamp,
                                 lambda: scatter_figure(movies_rated)),
                    use_container_width=True)
    r, _ = volume_reception(movies_rated)
    st.markdown(
        '<p class="ch-note">Actors with three or more covered films; bubble size '
        "is average runtime. Only those with eight or more are named &mdash; the "
        "rest are on hover. For actors the link between being cast often and being "
        f"in well-rated films is <b>absent &mdash; r = {r:.2f}</b>. Of "
        f"{len(cast_all):,} actors, {int((cast_all['count'] >= NAMED_FROM).sum())} clear "
        "eight films.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    tape("Every actor with 3+ films")
    # Gender comes in as a column here rather than as a filter: the table is
    # already sortable and searchable, so a column lets the reader slice it
    # without another widget to keep in session state.
    st.dataframe(
        ranked_actors(movies_rated, GENDER_MAP)
        .assign(avg_rt=lambda d: d["avg_rt"] * 100)   # see note in Directors
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
