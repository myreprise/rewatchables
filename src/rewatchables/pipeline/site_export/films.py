"""films.json, the browse index, and one file per film page."""

import pandas as pd

from rewatchables.pipeline.site_export.common import blurb, card, plain_value

SHELF = 4          # films per related-film shelf on a film page
CAST_SHOWN = 10    # top-billed names on a film page


# ── films.json ────────────────────────────────────────────────────────────────

def film_rows(ctx):
    """One row per film, with every field the All films page filters or sorts
    on: the Movie Explorer's, read from the same `rated` frame."""
    ratings = ctx.rated.set_index("movie_id")[["tomatoes_avg", "ebert_avg"]]
    movies = ctx.movies.join(ratings, on="movie_id")
    rows = []
    for _, m in movies.sort_values(["year", "sort_title"]).iterrows():
        rt = m["tomatoes_avg"]
        rows.append({
            **card(m),
            "sort": m["sort_title"],
            "decade": plain_value(m["decade"]),
            "genres": list(m["genres"]),
            "directors": list(m["directors"]),
            "director": m["director_primary"],
            "runtime": plain_value(m["runtime_minutes"]),
            "tmdb": plain_value(m["rating_tmdb"]),
            "rt": None if pd.isna(rt) else round(float(rt) * 100, 1),
            "ebert": plain_value(m["ebert_avg"]),
            "episodes": plain_value(m["total_episodes_featured"]),
            "first": plain_value(m["first_episode_date"]),
            "last": plain_value(m["last_episode_date"]),
            "blurb": blurb(m["plot_summary"]),
        })
    return rows


# ── films/<slug>.json ─────────────────────────────────────────────────────────

def episode_rows(episodes, addresses):
    """A film's episodes, oldest first, with the gap since the one before.

    Everyone in the room carries the address of their person page, or None
    for the anchor, who has none.
    """
    from views import ROOM, clean, human_gap, person_name

    def seat(value):
        name = clean(value)
        return None if name is None else {
            "name": name, "id": addresses.person(person_name(name))}

    rows, previous = [], None
    for _, ep in episodes.sort_values("episode_number").iterrows():
        gap = None
        if previous is not None and pd.notna(ep["episode_date"]):
            days = (ep["episode_date"] - previous).days
            gap = human_gap(days) if days > 0 else None
        previous = ep["episode_date"]

        kind = None
        if ep["is_revisit"]:
            kind = (clean(ep["revisit_type"]) or "revisit").replace("_", " ")
            kind = kind.replace(" revisit", "")
        verdict = clean(ep["cruise_hanks"])
        rows.append({
            "number": plain_value(ep["episode_number"]),
            "date": plain_value(ep["episode_date"]),
            "gap_before": gap,
            "is_revisit": bool(ep["is_revisit"]),
            "revisit_sequence": plain_value(ep["revisit_sequence"]),
            "revisit_kind": kind,
            "verdict": verdict,
            "verdict_tone": (None if not verdict else
                             "cruise" if verdict.lower().startswith("cruise")
                             else "hanks"),
            "host": seat(ep["host"]),
            "guests": [g for g in (seat(ep.get(c)) for c in ROOM[1:]) if g],
            "note": clean(ep["notes"]),
        })
    return rows


def film_page(movie, ctx, billing, addresses):
    """Everything one film's page shows, precomputed."""
    from rewatchables.app.overlays.dossier import same_director, shared_cast
    from views import CPI_BASE_YEAR, LINK_FLOOR, chip_band, clean, money, rank_by_reach

    episodes = ctx.links[ctx.links["movie_id"] == movie["movie_id"]]
    rt = episodes["tomatoes_num"].dropna()
    ebert = episodes["ebert_num"].dropna()
    box, mult = movie.get("revenue_real"), movie.get("multiple")
    cast = list(movie["cast_names"][:CAST_SHOWN]) if movie["cast_names"] else []

    return {
        **card(movie),
        "tmdb_id": plain_value(movie["tmdb_id"]),
        # Each name with its spotlight's address, or None for a co-director
        # who is nobody's primary director and so has no page.
        "directors": [{"name": n, "id": addresses.director(n)} for n in movie["directors"]],
        "director_primary": movie["director_primary"],
        "genres": list(movie["genres"]),
        "runtime": plain_value(movie["runtime_minutes"]),
        "revisited": bool(movie["revisited_flag"] == 1),
        "episodes_featured": plain_value(movie["total_episodes_featured"]),
        "first": plain_value(movie["first_episode_date"]),
        "last": plain_value(movie["last_episode_date"]),
        "scores": {
            "tmdb": plain_value(movie["rating_tmdb"]),
            "rt": plain_value(rt.iloc[0] * 100) if len(rt) else None,
            "ebert": plain_value(ebert.iloc[0]) if len(ebert) else None,
            "box_office": money(box) if pd.notna(box) else None,
            "multiple": plain_value(mult),
            "cpi_year": CPI_BASE_YEAR,
        },
        "plot": clean(movie["plot_summary"]),
        "synopsis": clean(movie["plot_summary_wiki"]),
        "synopsis_words": plain_value(movie["plot_summary_wiki_words"]),
        "episodes": episode_rows(episodes, addresses),
        "keywords": [
            {"word": w, "reach": ctx.reach.get(w, 0),
             "band": chip_band(ctx.reach.get(w, 0)),
             "live": ctx.reach.get(w, 0) >= LINK_FLOOR,
             "id": addresses.keyword(w)}
            for w in rank_by_reach(movie["keywords"] or [], ctx.reach)
        ],
        "cast": [{"name": n, "films": billing.get(n, 0), "id": addresses.actor(n)}
                 for n in cast],
        "by_director": [card(m) for _, m in
                        same_director(ctx.movies, movie).head(SHELF).iterrows()],
        "shared_cast": [card(m) for _, m in
                        shared_cast(ctx.movies, movie).head(SHELF).iterrows()],
        "provenance": {
            "confidence": plain_value(movie["canonical_key_confidence"]),
            "enriched": (str(movie["enriched_at"])[:10]
                         if clean(movie["enriched_at"]) else None),
            "wikipedia": clean(movie["wikipedia_url"]),
            "wikidata": clean(movie["wikidata_qid"]),
        },
    }


def film_pages(ctx, addresses):
    """address -> page, for every film."""
    from rewatchables.app.overlays.dossier import cast_billing

    billing = cast_billing(ctx.movies)
    return {m["slug"]: film_page(m, ctx, billing, addresses)
            for _, m in ctx.movies.iterrows()}
