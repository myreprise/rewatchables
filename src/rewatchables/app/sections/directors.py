"""The directors, ranked and profiled."""

from collections import Counter

import pandas as pd
import streamlit as st

from rewatchables.app.analysis import BILLED, PERSON_AGG, films_by_director
from rewatchables.app.charts import people_scatter
from rewatchables.app.components import masthead, stat_tiles, tape
from rewatchables.app.panels import people_leaderboard, person_spotlight
from rewatchables.app.state import keep


def render(ctx):
    movies_rated = ctx.rated

    masthead(
        "Directors",
        "Who gets called back to the chair, and what their covered work looks like.",
    )

    # Every curated film carries exactly one director, so director_primary is
    # the director -- no credit-splitting to reconcile.
    dir_counts = movies_rated["director_primary"].value_counts()
    dir_counts = dir_counts[dir_counts.index != "Unknown"]

    # Numbers only: the leaderboard immediately below already names who leads,
    # and a name set in the tile's display face wraps and breaks the row.
    stat_tiles([
        ("Directors", f"{dir_counts.size:,}"),
        ("Just one film", f"{int((dir_counts == 1).sum()):,}"),
        ("Two or more", f"{int((dir_counts >= 2).sum()):,}"),
        ("Four or more", f"{int((dir_counts >= 4).sum()):,}"),
        ("Films covered", f"{len(movies_rated):,}"),
    ])

    st.markdown("---")

    top_dirs = dir_counts.head(20)
    top_dirs = pd.DataFrame(
        {"director": top_dirs.index, "films": top_dirs.to_numpy()})
    people_leaderboard(top_dirs, "director", "Most-featured directors")
    st.markdown(
        f'<p class="ch-note">{int((dir_counts >= 2).sum())} directors have more '
        f"than one film covered, out of {dir_counts.size:,}. The long tail is "
        "most of the catalogue &mdash; the show ranges wider than it repeats.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    tape("Director spotlight")
    sel_dir = keep(
        st.selectbox, "Director", top_dirs["director"].tolist(), key="flt_dir_pick")
    dir_films = films_by_director(movies_rated, sel_dir)

    regulars = Counter(
        name
        for cast in dir_films["cast_names"]
        for name in (cast[:BILLED] if isinstance(cast, list) else [])
    )
    person_spotlight(
        dir_films,
        key="director",
        collab_title="Actors they bring back",
        collab_pairs=[(n, k) for n, k in regulars.most_common(6) if k >= 2],
        collab_empty=f"No actor is credited on more than one {sel_dir} film here.",
        collab_note="Credited on two or more of their covered films.",
    )

    st.markdown("---")

    tape("Volume against reception")
    dir_stats = (
        movies_rated[movies_rated["director_primary"] != "Unknown"]
        .groupby("director_primary").agg(**PERSON_AGG).reset_index()
        .rename(columns={"director_primary": "director"})
    )
    people_scatter(dir_stats[dir_stats["films"] >= 2], "director", "director")
    st.markdown(
        '<p class="ch-note">Directors with two or more covered films; bubble size '
        "is average runtime. Only those with four or more are named &mdash; the rest "
        "are on hover. Being covered often and being rated well are weakly related "
        "for directors &mdash; <b>r = 0.30</b> across these 97 &mdash; so the show "
        "does lean slightly toward the better-reviewed, but it explains little of "
        "the spread.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    tape("Every director, ranked")
    st.dataframe(
        dir_stats.sort_values(["films", "avg_tmdb"], ascending=[False, False])
        # tomatoes_avg is a 0-1 fraction; the column format appends the sign but
        # does not scale, so 0.75 would print as "1%".
        .assign(avg_rt=lambda d: d["avg_rt"] * 100)
        .rename(columns={
            "director": "Director", "films": "Films", "avg_tmdb": "Avg TMDB",
            "avg_rt": "Avg RT", "avg_runtime": "Avg runtime",
            "first_year": "First", "last_year": "Last",
        }),
        hide_index=True, use_container_width=True, height=420,
        column_config={
            "Avg TMDB": st.column_config.NumberColumn(format="%.2f"),
            "Avg RT": st.column_config.NumberColumn(format="%.0f%%"),
            "Avg runtime": st.column_config.NumberColumn(format="%.0f"),
            "First": st.column_config.NumberColumn(format="%d"),
            "Last": st.column_config.NumberColumn(format="%d"),
        },
    )
