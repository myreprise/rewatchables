"""One file per section: data/sections/<name>.json.

Ratings, Box Office, Timeline & Revisits, Genres, Cruise vs. Hanks, Hosts &
Guests, Directors and Actors are mostly charts that depend on nothing but the database. Each section's
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


# ── Hosts & Guests ────────────────────────────────────────────────────────────

def hosts(ctx, addresses):
    """The section around the lookup; the lookup itself is the person pages."""
    from rewatchables.app.analysis import GENRE_FLOOR, LEAN_FLOOR, LEAN_Q, N_PERM
    from rewatchables.app.sections.hosts import (
        BENCH_FLOOR, RING_TOP, WHEN_TOP, anchor_share, figures, quiet_regulars,
        regular_leans, the_room, top_lineups, without_anchor,
    )
    from views import ANCHOR, MEASURE_LABEL, lean_phrase, lean_value

    eps = ctx.merged
    n_eps = len(eps)
    room, others, board = the_room(eps)
    with_anchor, anchor_hosted = anchor_share(room)
    regulars, tested, leans = regular_leans(eps, others, board)
    held = leans[leans["q"] < LEAN_Q]
    listed = board[board["episodes"] >= BENCH_FLOOR]

    def chips(person):
        mine = held[held["person"] == person].sort_values(["q", "metric"], kind="mergesort")
        return [{"text": lean_phrase(r.metric, r.mean_in, r.mean_out, r.diff),
                 "up": bool(r.diff > 0)} for r in mine.itertuples()]

    ordered = leans.sort_values(["p", "person", "metric"], kind="mergesort")
    movies = ctx.movies.set_index("movie_id")
    return {
        "anchor": ANCHOR,
        "episodes": n_eps,
        "with_anchor": len(with_anchor),
        "anchor_hosted": anchor_hosted,
        "without_anchor": n_eps - len(with_anchor),
        "everyone_else": len(board),
        "five_or_more": int((board["episodes"] >= 5).sum()),
        "bench_floor": BENCH_FLOOR,
        "bench": [{"name": name, "id": addresses.person(name),
                   "episodes": int(r["episodes"]),
                   "share": round(100 * r["episodes"] / n_eps, 1),
                   "hosted": int(r["hosted"]),
                   "first": plain_value(r["first"]), "last": plain_value(r["last"])}
                  for name, r in listed.iterrows()],
        "off_bench": int((board["episodes"] < BENCH_FLOOR).sum()),
        "once": int((board["episodes"] == 1).sum()),
        "most_episodes": int(board["episodes"].max()),
        "when_top": min(WHEN_TOP, len(board)),
        "ring_top": min(RING_TOP, len(board)),
        "figures": figures_json(figures(eps)),
        "lineups": [{"lineup": lineup, "episodes": n} for lineup, n in top_lineups(others)],
        "regulars": [{"name": p, "id": addresses.person(p),
                      "episodes": int(board.loc[p, "episodes"]), "leans": chips(p)}
                     for p in regulars],
        "quiet": quiet_regulars(regulars, held),
        "lean_floor": LEAN_FLOOR,
        "genre_floor": GENRE_FLOOR,
        "genres_tested": len(tested),
        "comparisons": len(leans),
        "held": len(held),
        "n_perm": N_PERM,
        "lean_q": LEAN_Q,
        "all_comparisons": [
            {"name": r.person, "id": addresses.person(r.person),
             "measure": MEASURE_LABEL.get(r.metric, f"{r.metric} share"),
             "episodes": int(r.n),
             "theirs": lean_value(r.metric, r.mean_in),
             "others": lean_value(r.metric, r.mean_out),
             "gap": lean_value(r.metric, r.diff, signed=True),
             "p": round(float(r.p), 4), "q": round(float(r.q), 4),
             "shown": bool(r.q < LEAN_Q)}
            for r in ordered.itertuples()],
        "without": [
            {"host": host, "id": addresses.person(host),
             "episodes": [{**card(movies.loc[m["movie_id"]]),
                           "episode": int(m["episode_number"]),
                           "aired": plain_value(m["episode_date"])}
                          for _, m in group.iterrows()]}
            for host, group in without_anchor(eps)],
    }


# ── Directors and Actors ──────────────────────────────────────────────────────

def person_rows(stats, name_col, link):
    """The "every director / actor" table, with a link where a spotlight exists."""
    return [{"name": r[name_col], "id": link(r[name_col]), "films": int(r["films"]),
             "tmdb": None if pd.isna(r["avg_tmdb"]) else round(float(r["avg_tmdb"]), 2),
             "rt": None if pd.isna(r["avg_rt"]) else round(float(r["avg_rt"]) * 100),
             "runtime": None if pd.isna(r["avg_runtime"]) else round(float(r["avg_runtime"])),
             "first": plain_value(r["first_year"]), "last": plain_value(r["last_year"]),
             **({"gender": r["gender"]} if "gender" in r else {})}
            for _, r in stats.iterrows()]


def directors(ctx, addresses):
    from rewatchables.app.sections.directors import (
        figures, director_counts, ranked_directors, top_directors,
    )

    counts = director_counts(ctx.rated)
    return {
        "tiles": {
            "directors": int(counts.size),
            "one": int((counts == 1).sum()),
            "two_plus": int((counts >= 2).sum()),
            "four_plus": int((counts >= 4).sum()),
            "films": len(ctx.rated),
        },
        "figures": figures_json(figures(ctx.rated)),
        "spotlight": [{"name": n, "id": addresses.director(n), "films": int(f)}
                      for n, f in top_directors(ctx.rated).itertuples(index=False)],
        "table": person_rows(ranked_directors(ctx.rated), "director", addresses.director),
    }


def actors(ctx, addresses):
    from rewatchables.app.data import GENDER_LABEL
    from rewatchables.app.panels import gender_leaderboard_figs
    from rewatchables.app.sections.actors import (
        GENDER_TOP, NAMED_FROM, cast_counts, figures, gender_credits, gender_peaks,
        has_genders, ranked_actors, top_actors,
    )

    rated, genders = ctx.rated, ctx.gender_map
    cast_all = cast_counts(rated)
    credits = gender_credits(rated, genders)
    gendered = has_genders(credits)
    men_top, women_top, first_woman = gender_peaks(rated, genders)
    return {
        "tiles": {
            "actors": len(cast_all),
            "one": int((cast_all["count"] == 1).sum()),
            "three_plus": int((cast_all["count"] >= 3).sum()),
            "five_plus": int((cast_all["count"] >= 5).sum()),
            "films": len(rated),
            "named": int((cast_all["count"] >= NAMED_FROM).sum()),
        },
        "gendered": gendered,
        "credits": [{"gender": g, "label": GENDER_LABEL[g], "credits": n}
                    for g, n in credits.items()],
        "credits_total": sum(credits.values()),
        "by_gender": ([{"label": GENDER_LABEL[g], "actors": counted, "figure": figure(fig)}
                       for g, (counted, fig) in gender_leaderboard_figs(
                           rated, genders, top_n=GENDER_TOP).items()]
                      if gendered else []),
        "men_top": men_top,
        "women_top": women_top,
        "first_woman": first_woman,
        "figures": figures_json(figures(rated)),
        "spotlight": [{"name": n, "id": addresses.actor(n), "films": int(f)}
                      for n, f in top_actors(rated).itertuples(index=False)],
        "table": person_rows(ranked_actors(rated, genders), "actor", addresses.actor),
    }


# name -> exporter, one per page.
SECTIONS = {
    "ratings": ratings,
    "boxoffice": boxoffice,
    "timeline": timeline,
    "genres": genres,
    "verdicts": verdicts,
    "hosts": hosts,
    "directors": directors,
    "actors": actors,
}


def section_pages(ctx, addresses):
    """name -> content, for every chart section."""
    return {name: build(ctx, addresses) for name, build in SECTIONS.items()}
