"""The directors, ranked and profiled.

The section's numbers and figures, free of any front end. The app draws them
in rewatchables.app.sections.directors; step 15 ships them to the public site.
"""

from collections import Counter

import pandas as pd

from rewatchables.analysis import BILLED, PERSON_AGG
from rewatchables.figures import _leaderboard_fig, people_scatter_fig
from rewatchables.palette import MINT_DEEP


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
