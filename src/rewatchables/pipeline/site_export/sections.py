"""One file per chart section: data/sections/<name>.json.

Ratings, Box Office, Timeline & Revisits, Genres and Cruise vs. Hanks are
mostly charts that depend on nothing but the database. Each section's
figures() builds them, in the app and here alike, and they are shipped as
Plotly JSON. Alongside them go the numbers the section prints in its tiles
and captions, and the rows of its tables, so the page lays them out without
working anything out.

A film in a table or grid carries its address, so it links to its page.
"""

import pandas as pd

from rewatchables.pipeline.site_export.common import card, figure, plain_value


def film_link(movie_id, addresses, title, year):
    return {"id": addresses.films.get(movie_id), "title": title, "year": plain_value(year)}


def figures_json(figs):
    return {name: figure(fig) for name, fig in figs.items()}


# ── Ratings ───────────────────────────────────────────────────────────────────

def ratings(ctx, addresses):
    from rewatchables.app.sections.ratings import divergence, figures

    def rows(frame):
        return [{**film_link(r.movie_id, addresses, r.title, r.year),
                 "rt": round(float(r.rt_pct), 1), "tmdb": round(float(r.rating_tmdb), 2),
                 "diff": round(float(r.diff), 1)}
                for r in frame.itertuples()]

    critic, audience = divergence(ctx.merged)
    return {
        "figures": figures_json(figures(ctx.merged, ctx.movies)),
        "critics_love": rows(critic),
        "audiences_love": rows(audience),
    }


# ── Box Office ────────────────────────────────────────────────────────────────

def boxoffice(ctx, addresses):
    from rewatchables.app.sections.boxoffice import (
        figures, money_table, returns, summary,
    )
    from views import BREAK_EVEN_MULTIPLE, CPI_BASE_YEAR, CPI_PROVISIONAL_FROM, money

    s = summary(ctx.movies)

    def rows(frame, digits):
        return [{**film_link(r.movie_id, addresses, r.title, r.year),
                 "budget": money(r.budget_real), "gross": money(r.revenue_real),
                 "return": f"{r.multiple:,.{digits}f}×"}
                for r in frame.itertuples()]

    best, worst = returns(ctx.movies)
    table = money_table(ctx.movies)
    return {
        "cpi_year": CPI_BASE_YEAR,
        "provisional_from": CPI_PROVISIONAL_FROM,
        "break_even": BREAK_EVEN_MULTIPLE,
        "summary": {
            "films": s["films"],
            "with_gross": s["with_gross"],
            "median_gross": money(s["median_gross"]),
            "median_budget": money(s["median_budget"]),
            "median_return": round(float(s["median_return"]), 1),
            "with_return": s["with_return"],
            "under_break_even": s["under_break_even"],
            "no_gross": s["no_gross"],
            "no_budget": s["no_budget"],
            "thin_decades": [{"decade": d, "films": n} for d, n in s["thin_decades"]],
            "scatter_films": s["scatter_films"],
            "scatter_short": s["scatter_short"],
            "rho": round(float(s["rho"]), 2),
            "merit_films": s["merit_films"],
            "provisional": [{"title": t, "year": y} for t, y in s["provisional"]],
        },
        "figures": figures_json(figures(ctx.movies)),
        "best": rows(best, 0),
        "worst": rows(worst, 2),
        # The data table sorts in the browser, so it carries the raw figures
        # beside the printed ones.
        "table": [{**film_link(r.movie_id, addresses, r.title, r.year),
                   "budget": plain_value(r.budget_real), "budget_txt": money(r.budget_real),
                   "gross": plain_value(r.revenue_real), "gross_txt": money(r.revenue_real),
                   "return": None if pd.isna(r.multiple) else round(float(r.multiple), 1),
                   "tmdb": None if pd.isna(r.rating_tmdb) else round(float(r.rating_tmdb), 1),
                   "episodes": plain_value(r.total_episodes_featured)}
                  for r in table.itertuples()],
    }


# ── Timeline & Revisits ───────────────────────────────────────────────────────

def timeline(ctx, addresses):
    from rewatchables.app.sections.timeline import (
        figures, oldest_discussed, revisited_films,
    )

    revisited = revisited_films(ctx.movies)
    return {
        "figures": figures_json(figures(ctx.episodes, ctx.merged, ctx.movies)),
        "oldest": [{**film_link(r.movie_id, addresses, r.title, r.year),
                    "aired": int(r.ep_year), "age": int(r.age_gap)}
                   for r in oldest_discussed(ctx.merged).itertuples()],
        "revisited": [{**card(m), "episodes": plain_value(m["total_episodes_featured"])}
                      for _, m in revisited.iterrows()],
    }


# ── Genres ────────────────────────────────────────────────────────────────────

def genres(ctx, addresses):
    from rewatchables.app.sections.genres import SHELF, figures

    # The "Browse by genre" shelf filters films.json in the browser; only its
    # length is set here.
    return {"figures": figures_json(figures(ctx.movies)), "shelf": SHELF}


# ── Cruise vs. Hanks ──────────────────────────────────────────────────────────

def verdicts(ctx, addresses):
    from rewatchables import images
    from rewatchables.app.analysis import VERDICT_FLOOR
    from rewatchables.app.sections.verdicts import (
        GENRE_VERDICTS, RUN_START, STREAKS_SHOWN, figures, films_with, guest_split,
        rail_films, running_margin, standing, streaks, tale_of_the_tape,
    )

    movies = ctx.movies
    marg, lead_changes = running_margin(ctx.cruise_hanks)
    rows, ratios = tale_of_the_tape(ctx.cruise_hanks)
    slugs = addresses.films
    posters = dict(zip(movies["movie_id"], movies["poster_url_tmdb"]))

    def fighter(actor):
        return {
            "films": len(films_with(movies, actor)),
            "portrait": images.file_name(images.PORTRAITS[actor]),
            "rail": [card(m) for _, m in rail_films(movies, actor).iterrows()],
        }

    ledger = ctx.cruise_hanks.sort_values("episode_number", ascending=False, kind="mergesort")
    return {
        "standing": standing(ctx.cruise_hanks),
        "cruise": fighter("Tom Cruise"),
        "hanks": fighter("Tom Hanks"),
        "run_start": RUN_START,
        "run_end": int(marg["episode_number"].max()),
        "early": len(ctx.cruise_hanks) - len(marg),
        "lead_changes": lead_changes,
        "widest": int(marg["margin"].abs().max()),
        "genre_floor": GENRE_VERDICTS,
        "figures": figures_json(figures(ctx.cruise_hanks)),
        "tape": rows,
        "largest_ratio": round(max(ratios), 2),
        "streaks": [{"verdict": v, "length": n, "from": a, "to": b, "films": titles}
                    for v, n, a, b, titles in streaks(ctx.cruise_hanks)[:STREAKS_SHOWN]],
        "verdict_floor": VERDICT_FLOOR,
        "guests": [{"name": name, "id": addresses.person(name),
                    "cruise": int(r["Cruise"]), "hanks": int(r["Hanks"]),
                    "ties": int(r["Tie"]), "n": int(r["n"])}
                   for name, r in guest_split(ctx.cruise_hanks).iterrows()],
        "ledger": [{"id": slugs.get(r.movie_id), "title": r.movie_title,
                    "year": plain_value(r.movie_year),
                    "poster": images.file_name(posters.get(r.movie_id) or r.poster_url_tmdb),
                    "episode": int(r.episode_number), "verdict": r.verdict}
                   for r in ledger.itertuples()],
    }


# name -> exporter, one per page.
SECTIONS = {
    "ratings": ratings,
    "boxoffice": boxoffice,
    "timeline": timeline,
    "genres": genres,
    "verdicts": verdicts,
}


def section_pages(ctx, addresses):
    """name -> content, for every chart section."""
    return {name: build(ctx, addresses) for name, build in SECTIONS.items()}
