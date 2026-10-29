"""Every frame the front ends read, loaded once.

One object holding the frames and the maps derived from them. The app builds
it once per rerun and hands it to each section; step 15 builds it once per
export. A section takes it and unpacks what it needs, so it cannot reach for a
frame nobody gave it, and the loaders stay in one place rather than being
called wherever a number is wanted.
"""

from dataclasses import dataclass

import pandas as pd

from rewatchables import data


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
    # Steps 16-17: the show's categories, and how many episodes they cover yet.
    categories: data.Categories
    # The database's modification time: the key for anything built once per
    # database, such as the charts a widget does not affect.
    stamp: float


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


def build_context(db_stamp=None, loaders=data):
    """Load everything once.

    `loaders` is any module with rewatchables.data's five loaders: that one by
    default, or the app's cached copies, which `db_stamp` keys.
    """
    movies, episodes, links, merged, cruise_hanks = loaders.load_data(db_stamp)
    upcoming, graduated = loaders.load_upcoming(db_stamp)
    keywords = loaders.keyword_index(movies, db_stamp)
    return Ctx(
        movies=movies,
        episodes=episodes,
        links=links,
        merged=merged,
        cruise_hanks=cruise_hanks,
        upcoming=upcoming,
        graduated=graduated,
        rated=_rated(movies, merged),
        gender_map=data.gender_from_people(loaders.load_people(db_stamp)),
        keywords=keywords,
        reach={word: len(ids) for word, ids in keywords.items()},
        categories=loaders.load_categories(db_stamp),
        stamp=db_stamp,
    )
