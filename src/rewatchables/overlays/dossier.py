"""A film's links to the rest of the catalogue: its cast and its director's
other films. The app's dossier is rewatchables.app.overlays.dossier.
"""

from collections import Counter


def cast_billing(movies_df):
    """How many films each name is top-five billed in, across the catalogue."""
    billing = Counter()
    for names in movies_df["cast_names"]:
        for name in (names[:5] if isinstance(names, list) else []):
            billing[name] += 1
    return billing


def same_director(movies_df, movie):
    """The other films by this film's primary director, oldest first."""
    return movies_df[
        (movies_df["director_primary"] == movie["director_primary"])
        & (movies_df["movie_id"] != movie["movie_id"])
    ].sort_values("year")


def shared_cast(movies_df, movie):
    """Films sharing a top-billed name with this one, most-shared first."""
    cast = set(movie["cast_names"][:5]) if movie["cast_names"] else set()
    if not cast:
        return movies_df.iloc[0:0]
    overlap = movies_df[movies_df["movie_id"] != movie["movie_id"]].copy()
    overlap["shared"] = overlap["cast_names"].apply(
        lambda names: len(cast & set(names[:5])) if isinstance(names, list) else 0
    )
    return overlap[overlap["shared"] > 0].sort_values(
        ["shared", "year"], ascending=[False, True])
