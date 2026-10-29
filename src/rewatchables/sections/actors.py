"""The actors, ranked and profiled, and the gender split.

The section's numbers and figures, free of any front end. The app draws them
in rewatchables.app.sections.actors; step 15 ships them to the public site.
"""

from collections import Counter

from rewatchables.analysis import PERSON_AGG, billed_long, explode_cast
from rewatchables.figures import _leaderboard_fig, people_scatter_fig
from rewatchables.data import GENDERS, GENDER_LABEL
from rewatchables.palette import AMBER


# Actors on the leaderboard and in the spotlight picker.
TOP = 20
# Actors on the scatter and in the table need this many films.
SCATTER_FROM = 3
# Actors named on the scatter.
NAMED_FROM = 8
# Names per column of the gender-split leaderboards.
GENDER_TOP = 15
# Recurring directors listed in a spotlight.
COLLABORATORS = 6


def cast_counts(rated):
    """(actor, count) for every credited name, most films first.

    Counts every name in the stored cast list, so supporting and minor roles
    land in an actor's filmography alongside the leads.
    """
    return explode_cast(rated, top_n=100_000)


def top_actors(rated, n=TOP):
    return cast_counts(rated).head(n).rename(columns={"count": "films"})


def gender_credits(rated, gender_map):
    """{gender: billed credits}. Counted in credits, not people: a film's billed
    cast is ten slots, and "who gets cast" is a question about slots."""
    return {g: int(explode_cast(rated, top_n=100_000, gender=g,
                                gender_map=gender_map)["count"].sum())
            for g in GENDERS}


def gender_peaks(rated, gender_map):
    """(films of the most-featured man, of the most-featured woman, the first
    woman's place in the combined ranking or None)."""
    by = {g: explode_cast(rated, top_n=100_000, gender=g, gender_map=gender_map)
          for g in ("M", "F")}
    first_woman = next(
        (i + 1 for i, n in enumerate(cast_counts(rated)["actor"])
         if gender_map.get(n) == "F"), None)
    men_top = by["M"]["count"].max() if len(by["M"]) else 0
    women_top = by["F"]["count"].max() if len(by["F"]) else 0
    return int(men_top), int(women_top), first_woman


def has_genders(credits):
    """Whether the gender dimension is populated at all. A database that has
    not been through the cast_ids pass keeps the ungendered section."""
    total = sum(credits.values())
    return bool(total) and credits["unknown"] < total


def actor_stats(rated):
    """Per actor on SCATTER_FROM+ films: films, averages, first and last year."""
    stats = billed_long(rated).groupby("actor").agg(**PERSON_AGG).reset_index()
    return stats[stats["films"] >= SCATTER_FROM]


def volume_reception(rated):
    """(Pearson r of films covered against average TMDB, actors counted),
    over the actors on the scatter."""
    stats = actor_stats(rated)
    return float(stats["films"].corr(stats["avg_tmdb"])), len(stats)


def ranked_actors(rated, gender_map):
    """actor_stats in the table's order, with each actor's gender label."""
    return (actor_stats(rated)
            .sort_values(["films", "avg_tmdb"], ascending=[False, False])
            .assign(gender=lambda d: d["actor"].map(
                lambda n: GENDER_LABEL.get(gender_map.get(n, "unknown")))))


def directors_returned_to(actor_films):
    """(director, films) for directors of two or more of these films.

    Same "two or more" rule as the Directors spotlight. Listing the one-film
    pairings too would fill the panel with rows that say nothing -- recurring
    director/actor pairs are rare here, and that is the finding.
    """
    worked_with = Counter(actor_films["director_primary"])
    worked_with.pop("Unknown", None)
    return [(n, k) for n, k in worked_with.most_common(COLLABORATORS) if k >= 2]


def leaderboard_figure(rated):
    return _leaderboard_fig(top_actors(rated), "actor", AMBER)


def scatter_figure(rated):
    return people_scatter_fig(actor_stats(rated), "actor", name_from=NAMED_FROM)


FIGURES = {"leaderboard": leaderboard_figure, "scatter": scatter_figure}


def figures(rated):
    """name -> figure, for every chart in the section but the gender pair's
    and the spotlight's."""
    return {name: build(rated) for name, build in FIGURES.items()}
