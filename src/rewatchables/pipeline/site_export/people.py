"""people.json, the lookup's index, and one file per person page.

A person page is the Hosts & Guests section's "Look someone up" panel: their
numbers, every airing they were on, who they sit with, what they get booked
on and their Cruise vs. Hanks record. Everyone in the room has one except the
anchor, who has no lookup in the app either.
"""

from rewatchables.pipeline.site_export.common import card, plain_value

COMPANY = 6        # names in "Who they sit with", as in the app


def lookup(ctx):
    """The section's shared workings: (others, board, regulars, held leans)."""
    from rewatchables.app.analysis import LEAN_Q
    from rewatchables.app.sections.hosts import regular_leans, the_room

    _, others, board = the_room(ctx.merged)
    regulars, _, leans = regular_leans(ctx.merged, others, board)
    return others, board, regulars, leans[leans["q"] < LEAN_Q]


def people_index(board, addresses):
    """Everyone with a page, in the lookup's order: most episodes first."""
    return [{"name": name, "id": addresses.person(name), "episodes": int(row["episodes"])}
            for name, row in board.iterrows()]


def person_page(name, ctx, addresses, others, board, regulars, held):
    """Everything one person's page shows, precomputed."""
    from rewatchables.app.analysis import LEAN_FLOOR, VERDICT_FLOOR, person_shelf
    from rewatchables.app.sections.hosts import sits_with, verdict_tally
    from views import lean_phrase

    me = board.loc[name]
    n_eps = len(ctx.merged)
    movies = ctx.movies.set_index("movie_id")
    shelf = person_shelf(ctx.merged, name)
    ids = set(shelf["raw_episode_id"])
    company = sits_with(others, ids, name)
    tally = verdict_tally(ctx.merged, ids)
    # Ties on q break on the measure's name, as lean_chips breaks them.
    mine = held[held["person"] == name].sort_values(["q", "metric"], kind="mergesort")

    return {
        "name": name,
        "id": addresses.person(name),
        "episodes": int(me["episodes"]),
        "share": round(me["episodes"] / n_eps, 4),
        "hosted": int(me["hosted"]),
        "first": plain_value(me["first"]),
        "last": plain_value(me["last"]),
        "shelf": [
            {**card(movies.loc[ep["movie_id"]]),
             "episode": plain_value(ep["episode_number"]),
             "aired": plain_value(ep["episode_date"])}
            for _, ep in shelf.iterrows()
        ],
        "company": [{"name": other, "id": addresses.person(other), "episodes": int(n)}
                    for other, n in company.head(COMPANY).items()],
        "regular": name in regulars,
        "lean_floor": LEAN_FLOOR,
        "leans": [{"text": lean_phrase(r.metric, r.mean_in, r.mean_out, r.diff),
                   "up": bool(r.diff > 0)}
                  for r in mine.itertuples()],
        "verdict_floor": VERDICT_FLOOR,
        "verdicts": {
            "cruise": int(tally.get("Cruise", 0)),
            "hanks": int(tally.get("Hanks", 0)),
            "ties": int(tally.get("Tie", 0)),
            "n": int(tally.sum()),
        },
    }


def people_pages(ctx, addresses):
    """(index rows, address -> page) for everyone in the room but the anchor."""
    others, board, regulars, held = lookup(ctx)
    pages = {addresses.person(name): person_page(name, ctx, addresses, others,
                                                 board, regulars, held)
             for name in board.index}
    return people_index(board, addresses), pages
