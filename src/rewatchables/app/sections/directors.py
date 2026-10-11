"""The directors, ranked and profiled."""

from collections import Counter

import pandas as pd
import streamlit as st

from rewatchables.app.analysis import BILLED, PERSON_AGG, films_by_director
from rewatchables.app.charts import (
    _leaderboard_fig, people_scatter_fig, per_database,
)
from rewatchables.app.components import masthead, stat_tiles, tape
from rewatchables.app.panels import person_spotlight
from rewatchables.app.state import keep
from rewatchables.app.theme import MINT_DEEP

# Directors on the leaderboard and in the spotlight picker.
TOP = 20
# Directors on the scatter and in the table need this many films.
SCATTER_FROM = 2
# Recurring actors listed in a spotlight.
COLLABORATORS = 6


def director_counts(rated):
    """Films per director, most first. Every curated film carries exactly one
    director, so director_primary is the director -- no credit-splitting."""
    counts = rated["director_primary"].value_counts()
    return counts[counts.index != "Unknown"]


def top_directors(rated, n=TOP):
    top = director_counts(rated).head(n)
    return pd.DataFrame({"director": top.index, "films": top.to_numpy()})


def director_stats(rated):
    """Per director: films, average TMDB, RT and runtime, first and last year."""
    return (
        rated[rated["director_primary"] != "Unknown"]
        .groupby("director_primary").agg(**PERSON_AGG).reset_index()
        .rename(columns={"director_primary": "director"})
    )


def ranked_directors(rated):
    """director_stats in the table's order: most films, then best rated."""
    return director_stats(rated).sort_values(["films", "avg_tmdb"], ascending=[False, False])


def volume_reception(rated):
    """(Pearson r of films covered against average TMDB, directors counted),
    over the directors on the scatter."""
    stats = director_stats(rated)
    stats = stats[stats["films"] >= SCATTER_FROM]
    return float(stats["films"].corr(stats["avg_tmdb"])), len(stats)


def actors_brought_back(dir_films):
    """(actor, films) for actors credited on two or more of these films."""
    regulars = Counter(
        name
        for cast in dir_films["cast_names"]
        for name in (cast[:BILLED] if isinstance(cast, list) else [])
    )
    return [(n, k) for n, k in regulars.most_common(COLLABORATORS) if k >= 2]


def leaderboard_figure(rated):
    return _leaderboard_fig(top_directors(rated), "director", MINT_DEEP)


def scatter_figure(rated):
    stats = director_stats(rated)
    return people_scatter_fig(stats[stats["films"] >= SCATTER_FROM], "director")


FIGURES = {"leaderboard": leaderboard_figure, "scatter": scatter_figure}


def figures(rated):
    """name -> figure, for every chart in the section but the spotlight's."""
    return {name: build(rated) for name, build in FIGURES.items()}


def render(ctx):
    movies_rated = ctx.rated

    masthead(
        "Directors",
        "Who gets called back to the chair, and what their covered work looks like.",
    )

    dir_counts = director_counts(movies_rated)

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

    tape("Most-featured directors")
    st.plotly_chart(per_database("directors:leaderboard", ctx.stamp,
                                 lambda: leaderboard_figure(movies_rated)),
                    use_container_width=True)
    st.markdown(
        f'<p class="ch-note">{int((dir_counts >= 2).sum())} directors have more '
        f"than one film covered, out of {dir_counts.size:,}. The long tail is "
        "most of the catalogue &mdash; the show ranges wider than it repeats.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    tape("Director spotlight")
    sel_dir = keep(
        st.selectbox, "Director", top_directors(movies_rated)["director"].tolist(),
        key="flt_dir_pick")
    dir_films = films_by_director(movies_rated, sel_dir)
    person_spotlight(
        dir_films,
        key="director",
        collab_title="Actors they bring back",
        collab_pairs=actors_brought_back(dir_films),
        collab_empty=f"No actor is credited on more than one {sel_dir} film here.",
        collab_note="Credited on two or more of their covered films.",
    )

    st.markdown("---")

    tape("Volume against reception")
    st.plotly_chart(per_database("directors:scatter", ctx.stamp,
                                 lambda: scatter_figure(movies_rated)),
                    use_container_width=True)
    r, n = volume_reception(movies_rated)
    st.markdown(
        '<p class="ch-note">Directors with two or more covered films; bubble size '
        "is average runtime. Only those with four or more are named &mdash; the rest "
        "are on hover. Being covered often and being rated well are weakly related "
        f"for directors &mdash; <b>r = {r:.2f}</b> across these {n} &mdash; so the show "
        "does lean slightly toward the better-reviewed, but it explains little of "
        "the spread.</p>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    tape("Every director, ranked")
    st.dataframe(
        ranked_directors(movies_rated)
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
