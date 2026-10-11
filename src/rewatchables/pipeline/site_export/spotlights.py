"""One page per director and actor in the app's spotlight pickers.

data/directors/<slug>.json and data/actors/<slug>.json: the Directors and
Actors sections' spotlight, the same panel for both. Its numbers come from
analysis.person_stats, its two charts from panels.spotlight_figures, and its
collaborators from the section's own function, as in the app.
"""

import pandas as pd

from rewatchables.pipeline.site_export.common import card, figure


def spotlight(name, films, collaborators, link):
    from rewatchables.app.analysis import person_stats
    from rewatchables.app.panels import spotlight_figures

    ordered = films.sort_values(["year", "slug"], kind="mergesort")
    return {
        "name": name,
        "tiles": [{"label": label, "value": value} for label, value in person_stats(films)],
        "films": [{**card(m),
                   "rt": None if pd.isna(m["tomatoes_avg"]) else round(float(m["tomatoes_avg"]) * 100)}
                  for _, m in ordered.iterrows()],
        "figures": {k: figure(f) for k, f in spotlight_figures(films).items()},
        "collaborators": [{"name": n, "id": link(n), "films": int(k)} for n, k in collaborators],
    }


def director_pages(ctx, addresses):
    """address -> page, for every director in the spotlight picker."""
    from rewatchables.app.analysis import films_by_director
    from rewatchables.app.sections.directors import actors_brought_back

    rated = ctx.rated.assign(slug=ctx.rated["movie_id"].map(addresses.films))
    out = {}
    for name, slug in addresses.directors.items():
        films = films_by_director(rated, name)
        out[slug] = {**spotlight(name, films, actors_brought_back(films), addresses.actor),
                     "id": slug, "kind": "director"}
    return out


def actor_pages(ctx, addresses):
    """address -> page, for every actor in the spotlight picker."""
    from rewatchables.app.analysis import films_by_actor
    from rewatchables.app.sections.actors import directors_returned_to

    rated = ctx.rated.assign(slug=ctx.rated["movie_id"].map(addresses.films))
    out = {}
    for name, slug in addresses.actors.items():
        films = films_by_actor(rated, name)
        out[slug] = {**spotlight(name, films, directors_returned_to(films), addresses.director),
                     "id": slug, "kind": "actor"}
    return out
