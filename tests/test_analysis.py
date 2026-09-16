"""
Pure helpers in rewatchables.app.analysis that had no tests of their own.

explode_genres feeds five views (Overview, Genres, Ratings, Timeline and the
person spotlight). Its shape was never pinned, so these were written against
the implementation before it was vectorised, and the two tests at the end
record where the vectorised one deliberately differs.
"""

import pandas as pd

from rewatchables.app.analysis import explode_genres


def _films():
    return pd.DataFrame({
        "movie_id": ["heat", "big", "blank", "odd"],
        "title": ["Heat", "Big", "No Genres", "Not A List"],
        "genres": [["Crime", "Drama"], ["Comedy"], [], None],
        "decade": pd.array([1990, 1980, 2000, pd.NA], dtype="Int64"),
    })


def test_one_row_per_film_and_genre():
    out = explode_genres(_films())
    assert list(zip(out["movie_id"], out["genre"])) == [
        ("heat", "Crime"), ("heat", "Drama"), ("big", "Comedy")]


def test_the_genre_column_is_added_last():
    out = explode_genres(_films())
    assert list(out.columns) == ["movie_id", "title", "genres", "decade", "genre"]


def test_each_row_carries_its_films_values():
    out = explode_genres(_films())
    drama = out[out["genre"] == "Drama"].iloc[0]
    assert drama["title"] == "Heat"
    assert drama["genres"] == ["Crime", "Drama"]


def test_films_without_a_genre_list_contribute_nothing():
    out = explode_genres(_films())
    assert "blank" not in set(out["movie_id"])
    assert "odd" not in set(out["movie_id"])


def test_the_index_is_fresh():
    out = explode_genres(_films())
    assert list(out.index) == list(range(len(out)))


# Where the vectorised implementation differs from the row-by-row one, on
# purpose. Both were checked against the rendered app: every chart and every
# markdown block in Overview, Genres, Ratings, Timeline and Directors came out
# identical (report 008).

def test_an_empty_input_still_has_a_genre_column():
    """The row-by-row version returned a frame with no columns at all, so
    explode_genres(nothing)["genre"] raised."""
    out = explode_genres(_films().iloc[0:0])
    assert "genre" in out.columns and out.empty


def test_input_dtypes_are_kept():
    """decade is declared Int64 by load_data. Rebuilding rows from dicts
    silently re-inferred it as int64."""
    out = explode_genres(_films())
    assert str(out["decade"].dtype) == "Int64"
