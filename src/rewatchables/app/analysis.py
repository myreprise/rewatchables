"""Turning the frames into the numbers the sections report.

Everything here takes frames and returns frames or counts: no Streamlit
elements, no module-level data. The one call that touches Streamlit is
room_leans, and only to cache a permutation test that costs about a second.

The population a statistic is computed over is always passed in, never reached
for, so a section cannot quietly report one population under another's label.
"""

from collections import Counter

import pandas as pd
import streamlit as st

from views import bh_adjust, permutation_diffs, room_long


def explode_genres(df):
    """Return long-form DataFrame with one genre per row."""
    rows = []
    for _, row in df.iterrows():
        for g in (row["genres"] if isinstance(row["genres"], list) else []):
            rows.append({**row.to_dict(), "genre": g})
    return pd.DataFrame(rows)


# "In this film" counts the whole cast list curated_movies stores, which TMDB
# caps at ten (453 of 454 films carry exactly ten; one carries nine). The slice
# is kept rather than dropped so a future deeper cast list cannot silently
# redefine every actor statistic in the app.
BILLED = 10


def explode_cast(df, top_n=50, gender=None, gender_map=None):
    """Ranked (actor, count) over the stored cast lists.

    `gender` narrows the population to one of GENDERS before ranking, using
    the map it is handed. A name with no person row counts as
    'unknown', so the four genders partition the credits exactly -- any
    headline share is then computed over the population it claims.
    """
    lookup = gender_map or {}
    counts = Counter()
    for cast in df["cast_names"]:
        if isinstance(cast, list):
            for name in cast[:BILLED]:  # the full stored cast
                if gender is not None and lookup.get(name, "unknown") != gender:
                    continue
                counts[name] += 1
    return pd.DataFrame(counts.most_common(top_n), columns=["actor", "count"])


def films_by_director(films, name):
    return films[films["director_primary"] == name]


def films_by_actor(films, name):
    return films[films["cast_names"].apply(
        lambda c: isinstance(c, list) and name in c[:BILLED])]


def billed_long(df):
    """One row per (film, credited actor).

    The actor-side analogue of director_primary: it turns cast into a plain
    column so actor statistics are a single groupby, the same shape as the
    director ones. Scanning the frame once per actor instead cost ~0.3s on
    every rerun, which Streamlit pays on every widget change.
    """
    out = df.copy()
    out["actor"] = out["cast_names"].apply(
        lambda c: c[:BILLED] if isinstance(c, list) else [])
    return out.explode("actor").dropna(subset=["actor"])


PERSON_AGG = dict(
    films=("movie_id", "count"),
    avg_tmdb=("rating_tmdb", "mean"),
    avg_runtime=("runtime_minutes", "mean"),
    avg_rt=("tomatoes_avg", "mean"),
    first_year=("year", "min"),
    last_year=("year", "max"),
)


def person_stats(films):
    """The headline numbers for one person's body of covered work.

    First and latest are separate tiles rather than one "1983-2022" range: a
    metric value that long is truncated to an ellipsis at a sixth of the width.
    """
    years = films["year"].dropna()
    rt = films["tomatoes_avg"].dropna()
    tmdb = films["rating_tmdb"].dropna()
    return [
        ("Films covered", len(films)),
        ("Episodes", int(films["total_episodes_featured"].fillna(0).sum())),
        ("First film", int(years.min()) if len(years) else "—"),
        ("Latest film", int(years.max()) if len(years) else "—"),
        ("Avg RT", f"{rt.mean()*100:.0f}%" if len(rt) else "—"),
        ("Avg TMDB", f"{tmdb.mean():.2f}" if len(tmdb) else "—"),
    ]


def person_shelf(merged, name):
    """Every airing a person was on, newest first.

    One definition for two readers: the lookup draws its poster grid in this
    order, and the dossier's step arrows walk it in the same order. Computed
    from merged_df rather than read off the grid because the dossier gate runs
    before the section, on a run where the grid is never drawn.
    """
    room = room_long(merged, "raw_episode_id",
                     keep=("episode_number", "episode_date", "movie_id"))
    return (room[room["person"] == name]
            .sort_values(["episode_date", "episode_number"], ascending=False))


# A regular, for the lean tests: anyone on at least this many episodes. Ten
# people clear it; below it a person's episodes are too few for anything short
# of a landslide to be told from chance.
LEAN_FLOOR = 15
# Genres tested for a lean: those on at least this many episodes (seven do).
# Every extra test raises the bar the correction sets for all the others, and
# a genre on a handful of episodes cannot move far enough to clear it.
GENRE_FLOOR = 40
LEAN_Q = 0.05
N_PERM = 4000


@st.cache_data(ttl=300)
def room_leans(measures, members):
    """Every regular against everyone else, on every measure, with q-values.

    `measures` is one column per metric and `members` one boolean column per
    regular, both one row per airing.
    """
    out = permutation_diffs(
        {c: measures[c].to_numpy() for c in measures.columns},
        {p: members[p].to_numpy() for p in members.columns},
        n_perm=N_PERM,
    )
    out["q"] = bh_adjust(out["p"])
    return out
