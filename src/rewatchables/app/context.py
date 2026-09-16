"""What a section or an overlay is handed to render itself.

One object, built once per rerun, holding every frame the app reads and the
maps derived from them. A section takes it and unpacks what it needs, so it
cannot reach for a frame nobody gave it, and the loaders stay in one place
rather than being called wherever a number is wanted.
"""

from dataclasses import dataclass

import pandas as pd

from rewatchables.app import data


@dataclass(frozen=True)
class Ctx:
    """The frames and maps one render pass reads."""

    movies: pd.DataFrame
    episodes: pd.DataFrame
    links: pd.DataFrame
    merged: pd.DataFrame
    cruise_hanks: pd.DataFrame
    upcoming: pd.DataFrame
    graduated: pd.DataFrame
    rated: pd.DataFrame
    gender_map: dict
    keywords: dict
    reach: dict


def _rated(movies, merged):
    """Films with their per-film critic scores joined on.

    Averaged over a film's airings and built once: the Movie Explorer,
    Directors and Actors sections all need the same numbers, and recomputing
    the groupby per section drifted the moment one of them changed.
    """
    ep_ratings = (
        merged.groupby("movie_id")
        .agg(tomatoes_avg=("tomatoes_num", "mean"), ebert_avg=("ebert_num", "mean"))
        .reset_index()
    )
    return movies.merge(ep_ratings, on="movie_id", how="left")


def build_context(db_stamp):
    """Load everything once for this rerun. `db_stamp` keys the caches."""
    movies, episodes, links, merged, cruise_hanks = data.load_data(db_stamp)
    upcoming, graduated = data.load_upcoming(db_stamp)
    keywords = data.keyword_index(movies, db_stamp)
    return Ctx(
        movies=movies,
        episodes=episodes,
        links=links,
        merged=merged,
        cruise_hanks=cruise_hanks,
        upcoming=upcoming,
        graduated=graduated,
        rated=_rated(movies, merged),
        gender_map=data.gender_from_people(data.load_people(db_stamp)),
        keywords=keywords,
        reach={word: len(ids) for word, ids in keywords.items()},
    )
