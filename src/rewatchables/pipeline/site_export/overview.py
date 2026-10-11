"""overview.json, the front page, and the Plotly figures it draws."""

import json

from rewatchables.pipeline.site_export.common import card, plain_value

LATEST = 8         # cards in "Latest episodes"
REGULARS = 6       # people in "The regulars"
# A section's page on the site, where it is not the app's slug.
SITE_PATH = {"explorer": "films"}


def overview(ctx, addresses):
    """The front page: the headline tiles, the lists and the chart's reading."""
    from rewatchables.app.sections.overview import (
        came_back_to, doors, episodes_per_year, regulars, show_now,
    )
    from rewatchables.app.state import NAV, SECTION_LABEL, SLUGS
    from views import ANCHOR

    group_of = {slug: group for group, items in NAV for slug, _ in items}

    episodes, movies, links = ctx.episodes, ctx.movies, ctx.links
    now = show_now(episodes, ctx.merged, movies)
    in_room, hosted, n_anchor = regulars(episodes)
    _, ep_year = episodes_per_year(episodes)
    first_full = ep_year[ep_year["count"] >= 50]["year"].min()

    recent = (
        links.sort_values("episode_date", ascending=False)
        .drop_duplicates("movie_id")
        .head(LATEST)
        .merge(movies[["movie_id", "slug", "title", "year", "poster_url_tmdb"]],
               on="movie_id")
    )
    again = came_back_to(movies)

    return {
        "as_of": plain_value(now["latest_air"]),
        "tiles": {
            "episodes": len(episodes),
            "films": len(movies),
            "last_12_months": now["n_last_year"],
            "median_film_age": round(now["median_film_age"]),
            "share_90s": round(now["share_90s"]),
            "median_gap": round(now["median_gap"]),
        },
        "latest": [
            {**card(r), "episode": plain_value(r["episode_number"]),
             "aired": plain_value(r["episode_date"])}
            for _, r in recent.iterrows()
        ],
        "regulars": [
            {"name": name, "id": addresses.person(name), "episodes": int(n),
             "hosted": int(hosted.get(name, 0))}
            for name, n in in_room.head(REGULARS).items()
        ],
        "anchor": ANCHOR,
        "people_besides_anchor": len(in_room),
        "anchor_episodes": n_anchor,
        "came_back_to": [
            {**card(m), "episodes": plain_value(m["total_episodes_featured"]),
             "last": plain_value(m["last_episode_date"])}
            for _, m in again.iterrows()
        ],
        "flagged_revisits": int((movies["revisited_flag"] == 1).sum()),
        # One door per section, as in the app. The site's address for a
        # section is its slug, but for the Explorer's, which is /films.
        "doors": [
            {"path": SITE_PATH.get(slug, slug), "group": group_of[slug],
             "number_in_rail": SLUGS.index(slug) + 1, "label": SECTION_LABEL[slug],
             "value": number, "unit": unit, "blurb": blurb}
            for slug, number, unit, blurb in doors(ctx)
        ],
        "reading": {
            "first_air": plain_value(now["first_air"]),
            "first_full_year": plain_value(first_full),
            "median_gap": round(now["median_gap"]),
            "so_far": int(ep_year["count"].iloc[-1]),
            "so_far_year": int(ep_year["year"].iloc[-1]),
        },
    }


def charts(ctx):
    """name -> Plotly figure as JSON, built by the app's own chart code."""
    from rewatchables.app.sections.overview import episodes_per_year

    fig, _ = episodes_per_year(ctx.episodes)
    return {"episodes-per-year": json.loads(fig.to_json())}
