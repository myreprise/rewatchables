"""What every page exporter shares: JSON that the browser accepts, the
addresses pages link by, and the fields of a poster card."""

import dataclasses
import json
import math

import numpy as np
import pandas as pd

from rewatchables import images
from rewatchables.app.data import build_keyword_index
from views import ANCHOR, LINK_FLOOR, film_slugs, name_slugs, room_long

# The overview's spotlight blurb is cut to this many characters, as in the app.
BLURB_CHARS = 320


# ── Serialisation ─────────────────────────────────────────────────────────────

def plain_value(value):
    """A frame cell as something json.dumps writes as valid JSON.

    NaN and NaT become null rather than the bare NaN json.dumps would write,
    timestamps become ISO dates, and numpy scalars become Python ones.
    """
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.strftime("%Y-%m-%d")
    if value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return None if math.isnan(value) else float(value)
    if isinstance(value, (list, tuple)):
        return [plain_value(v) for v in value]
    return value


def figure(fig):
    """A Plotly figure as the JSON Plotly.js draws, or None for no figure."""
    return None if fig is None else json.loads(fig.to_json())


def blurb(text, limit=BLURB_CHARS):
    """A summary cut at a word boundary, as the overview spotlight cuts it."""
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


# ── Addresses ─────────────────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class Addresses:
    """Every page's address, so any page can link to any other.

    films: movie_id -> heat-1995. keywords: word -> writers-block, only for
    keywords on LINK_FLOOR films or more (the rest print as inert chips, as in
    the app). people: name -> chris-ryan, for everyone in the room but the
    anchor, who has no lookup in the app either. directors and actors: name ->
    address for everyone in the Directors and Actors tables (every director,
    and every actor on three or more films), each with a spotlight page.
    """
    films: dict
    keywords: dict
    people: dict
    directors: dict
    actors: dict

    def person(self, name):
        return self.people.get(name)

    def keyword(self, word):
        return self.keywords.get(word)

    def director(self, name):
        return self.directors.get(name)

    def actor(self, name):
        return self.actors.get(name)


def prepare(ctx):
    """(ctx, addresses): the context in a fixed order, and every address.

    Movies carry their address (`slug`) and are sorted by year and slug, so
    ties in every list built from them (a director's films in one year, say)
    fall the same way on every run: the frame's own order follows the
    database's insertion order, which step 06 does not promise to keep. The
    keyword index is rebuilt from that frame, for the same reason.
    """
    movies = ctx.movies.copy()
    if "slug" not in movies.columns:
        movies["slug"] = movies["movie_id"].map(film_slugs(movies))
    movies = movies.sort_values(["year", "slug"], kind="mergesort").reset_index(drop=True)
    keywords = build_keyword_index(movies)
    reach = {word: len(ids) for word, ids in keywords.items()}
    slugs = dict(zip(movies["movie_id"], movies["slug"]))

    # The episode frames too. The links query has no ORDER BY, so its rows
    # come back in whatever order step 06 inserted them, and a chart drawn
    # from them lists its points in that order. By airing, then the film's
    # address for the rare day with two.
    def by_airing(frame, date_col, number_col):
        key = frame["movie_id"].map(slugs).fillna("")
        return (frame.assign(_film=key)
                .sort_values([date_col, number_col, "_film"], kind="mergesort")
                .drop(columns="_film").reset_index(drop=True))

    ctx = dataclasses.replace(
        ctx, movies=movies, keywords=keywords, reach=reach,
        links=by_airing(ctx.links, "episode_date", "episode_number"),
        merged=by_airing(ctx.merged, "episode_date", "episode_number"),
        cruise_hanks=by_airing(ctx.cruise_hanks, "episode_date", "episode_number"),
        # `rated` is movies with their ratings joined; ranking ties (the
        # twentieth actor, say) fall by its order, so it takes the films' order.
        rated=(ctx.rated.assign(_film=ctx.rated["movie_id"].map(slugs))
               .sort_values(["year", "_film"], kind="mergesort")
               .drop(columns="_film").reset_index(drop=True)),
    )

    from rewatchables.app.sections.actors import actor_stats
    from rewatchables.app.sections.directors import director_stats

    room = room_long(ctx.merged, "raw_episode_id")
    people = set(room["person"]) - {ANCHOR}
    return ctx, Addresses(
        films=slugs,
        keywords=name_slugs(w for w, n in reach.items() if n >= LINK_FLOOR),
        people=name_slugs(people),
        directors=name_slugs(director_stats(ctx.rated)["director"]),
        actors=name_slugs(actor_stats(ctx.rated)["actor"]),
    )


def card(movie):
    """The fields a poster card needs: enough to draw it and link it."""
    return {
        "id": movie["slug"],
        "title": movie["title"],
        "year": plain_value(movie["year"]),
        "poster": images.file_name(movie["poster_url_tmdb"]),
    }
