#!/usr/bin/env python3
"""
Phase J: Export the data the public site reads.

The site in site/ is an Observable Framework project, built and deployed to
GitHub Pages by .github/workflows/deploy-site.yml. It cannot run Python or read
the database, so this step writes everything it shows as JSON into
site/src/data/, and those files are committed. CI then needs neither the
database nor a TMDB key: it builds the site from what is in the repository.

The numbers come from the Streamlit app's own loaders and helpers --
build_context, the overview's show_now / regulars / came_back_to /
episodes_per_year, the dossier's shelves -- so the two front ends print the
same figures. The rule is to compute here and only filter in the browser.

Writes:
  site/src/data/films.json            one row per film, for grids and search
  site/src/data/overview.json         the front page's numbers and lists
  site/src/data/charts/*.json         Plotly figures, built by the app's code
  site/src/data/films/<movie_id>.json one file per film page
  site/src/theme.css                  a copy of the app's stylesheet

Output is deterministic -- no timestamps, stable ordering, one film per line in
films.json -- so a commit shows only what changed. Per-film files for films no
longer in the catalogue are removed.

Posters are not exported. The site loads them from TMDB's image CDN, the same
fallback the app uses; static/tmdb/ stays unpublished.
"""

import json
import logging
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from rewatchables import config, images

logger = logging.getLogger(__name__)

SITE_SRC = config.ROOT / "site" / "src"
DATA_OUT = SITE_SRC / "data"
THEME_SRC = config.ROOT / "src" / "rewatchables" / "app" / "theme.css"

# The overview's spotlight blurb is cut to this many characters, as in the app.
BLURB_CHARS = 320
SHELF = 4          # films per related-films shelf on a film page
CAST_SHOWN = 10    # top-billed names on a film page
LATEST = 8         # cards in "Latest episodes"
REGULARS = 6       # people in "The regulars"


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


def _dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1) + "\n"


def write_rows(path, rows):
    """A JSON array with one row per line, so a diff names the films changed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = ",\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
    path.write_text(f"[\n{body}\n]\n", encoding="utf-8")


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_dump(obj), encoding="utf-8")


def blurb(text, limit=BLURB_CHARS):
    """A summary cut at a word boundary, as the overview spotlight cuts it."""
    text = text or ""
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def card(movie):
    """The fields a poster card needs: enough to draw it and link it."""
    return {
        "id": movie["movie_id"],
        "title": movie["title"],
        "year": plain_value(movie["year"]),
        "poster": images.file_name(movie["poster_url_tmdb"]),
    }


# ── films.json ────────────────────────────────────────────────────────────────

def film_rows(movies):
    """One row per film for the grids and the browse page's filters."""
    rows = []
    for _, m in movies.sort_values(["year", "sort_title"]).iterrows():
        rows.append({
            **card(m),
            "sort": m["sort_title"],
            "decade": plain_value(m["decade"]),
            "genres": list(m["genres"]),
            "directors": list(m["directors"]),
            "runtime": plain_value(m["runtime_minutes"]),
            "tmdb": plain_value(m["rating_tmdb"]),
            "episodes": plain_value(m["total_episodes_featured"]),
            "last": plain_value(m["last_episode_date"]),
            "blurb": blurb(m["plot_summary"]),
        })
    return rows


# ── overview.json ─────────────────────────────────────────────────────────────

def overview(ctx):
    """The front page: the headline tiles, the lists and the chart's reading."""
    from rewatchables.app.sections.overview import (
        came_back_to, episodes_per_year, regulars, show_now,
    )

    from views import ANCHOR

    episodes, movies, links = ctx.episodes, ctx.movies, ctx.links
    now = show_now(episodes, ctx.merged, movies)
    in_room, hosted, n_anchor = regulars(episodes)
    _, ep_year = episodes_per_year(episodes)
    first_full = ep_year[ep_year["count"] >= 50]["year"].min()

    recent = (
        links.sort_values("episode_date", ascending=False)
        .drop_duplicates("movie_id")
        .head(LATEST)
        .merge(movies[["movie_id", "title", "year", "poster_url_tmdb"]],
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
            {"name": name, "episodes": int(n), "hosted": int(hosted.get(name, 0))}
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


# ── films/<movie_id>.json ─────────────────────────────────────────────────────

def episode_rows(episodes):
    """A film's episodes, oldest first, with the gap since the one before."""
    from views import ROOM, clean, human_gap

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
            "host": clean(ep["host"]),
            "guests": [g for g in (clean(ep.get(c)) for c in ROOM[1:]) if g],
            "note": clean(ep["notes"]),
        })
    return rows


def film_page(movie, ctx, billing):
    """Everything one film's page shows, precomputed."""
    from rewatchables.app.overlays.dossier import same_director, shared_cast
    from views import (
        CPI_BASE_YEAR, LINK_FLOOR, chip_band, clean, money, rank_by_reach,
    )

    episodes = ctx.links[ctx.links["movie_id"] == movie["movie_id"]]
    rt = episodes["tomatoes_num"].dropna()
    ebert = episodes["ebert_num"].dropna()
    box, mult = movie.get("revenue_real"), movie.get("multiple")
    cast = list(movie["cast_names"][:CAST_SHOWN]) if movie["cast_names"] else []

    return {
        **card(movie),
        "tmdb_id": plain_value(movie["tmdb_id"]),
        "directors": list(movie["directors"]),
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
        "episodes": episode_rows(episodes),
        "keywords": [
            {"word": w, "reach": ctx.reach.get(w, 0),
             "band": chip_band(ctx.reach.get(w, 0)),
             "live": ctx.reach.get(w, 0) >= LINK_FLOOR}
            for w in rank_by_reach(movie["keywords"] or [], ctx.reach)
        ],
        "cast": [{"name": n, "films": billing.get(n, 0)} for n in cast],
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


# ── The step ──────────────────────────────────────────────────────────────────

def copy_theme(dest):
    """The app's stylesheet, copied so the site draws with the same classes."""
    text = THEME_SRC.read_text(encoding="utf-8")
    note = ("/* Generated by pipeline step 15 from "
            "src/rewatchables/app/theme.css. Edit that file, not this one. */\n")
    dest.write_text(note + text, encoding="utf-8")


def export(ctx, out=DATA_OUT, theme_dest=SITE_SRC / "theme.css"):
    """Write the site's data. Returns the number of film pages written."""
    from rewatchables.app.overlays.dossier import cast_billing

    write_rows(out / "films.json", film_rows(ctx.movies))
    write_json(out / "overview.json", overview(ctx))
    for name, fig in charts(ctx).items():
        write_json(out / "charts" / f"{name}.json", fig)

    pages = out / "films"
    pages.mkdir(parents=True, exist_ok=True)
    billing = cast_billing(ctx.movies)
    keep = set()
    for _, movie in ctx.movies.iterrows():
        name = f"{movie['movie_id']}.json"
        write_json(pages / name, film_page(movie, ctx, billing))
        keep.add(name)
    for stale in pages.glob("*.json"):
        if stale.name not in keep:
            stale.unlink()
            logger.info(f"  removed {stale.name}: no longer in the catalogue")

    if theme_dest is not None:
        copy_theme(theme_dest)
    return len(keep)


def main():
    db_path = config.db_path()
    if not Path(db_path).exists():
        logger.error(f"{db_path} not found.")
        sys.exit(1)

    # The loaders are the app's, decorated with st.cache_data. Outside a
    # Streamlit server they run uncached and Streamlit warns that it has no
    # runtime, once per call; that is expected here and says nothing useful.
    # Streamlit sets a level on each of its loggers, so the parent's is not
    # enough: its own setter reaches them all.
    from streamlit import logger as streamlit_logger
    streamlit_logger.set_log_level("error")
    from rewatchables.app.context import build_context
    from rewatchables.app.data import stamp

    logger.info("=" * 60)
    logger.info("Phase J: Export the public site's data")
    logger.info("=" * 60)
    ctx = build_context(stamp())
    n = export(ctx)
    size = sum(p.stat().st_size for p in DATA_OUT.rglob("*.json"))
    logger.info(f"Wrote {n} film pages and the overview to "
                f"{DATA_OUT.relative_to(config.ROOT)} ({size / 1e6:.1f} MB)")
    logger.info("Commit site/ and push to publish.")
    logger.info("=" * 60)


if __name__ == "__main__":
    config.setup_logging()
    main()
