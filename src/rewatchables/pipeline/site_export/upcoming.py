"""The Upcoming section: its numbers, and each request as site.db rows.

A requested film's page (request?id=<slug>) is the app's prospect overlay.
Its address is made from its title and year as a film's is; upcoming_film_id
is not used, for the same reason movie_id is not: the list is rebuilt on every
pipeline run. The filters run in the browser, over the requests table.
"""

import pandas as pd

from rewatchables.pipeline.site_export.common import plain_value


def requested_slugs(upcoming_df):
    """upcoming_film_id -> address, unique within the list.

    Title and year where there is a year, the title alone where the source
    gives none or a range. Should two rows fold to one address, the later in
    source order takes -2, then -3.
    """
    from collections import Counter

    from views import slugify

    out, taken = {}, Counter()
    for r in upcoming_df.sort_values("source_row_number", kind="mergesort").itertuples():
        base = slugify(r.title, r.year if pd.notna(r.year) else None)
        taken[base] += 1
        out[r.upcoming_film_id] = base if taken[base] == 1 else f"{base}-{taken[base]}"
    return out


def why(row):
    """The reason a film is on the list, and who put it there, as fields:
    views.contributor_link decides the label and the link, as in the app."""
    from views import clean, contributor_link

    label, href = contributor_link(row.get("contributor"))
    return {
        "note": clean(row.get("mention_note")),
        "tags": list(row.get("tags") or []),
        "by": {"label": label, "href": href} if label else None,
    }


def request_row(row, slug):
    """One request, as the grid, its filters and "Why these films" need it."""
    from rewatchables import images

    return {
        "id": slug,
        "title": row["title"],
        "year_raw": row["year_raw"] or None,
        "year": plain_value(row["year"]),
        "decade": plain_value(row["decade"]),
        "sort": row["sort_title"],
        "order": int(row["source_row_number"]),
        "poster": images.file_name(row["poster_url_tmdb"]),
        "tmdb": plain_value(row["rating_tmdb"]),
        "contributor": row["contributor"] if isinstance(row["contributor"], str) else None,
        **why(row),
    }


def requested_page(row, slug):
    """Everything one requested film's page shows."""
    from views import RESOLUTION_NOTE, clean

    return {
        **request_row(row, slug),
        "directors": list(row["directors"]),
        "genres": list(row["genres"]),
        "runtime": plain_value(row["runtime_minutes"]),
        "plot": clean(row.get("plot_summary")),
        "cast": list(row["cast_names"][:10]) if row["cast_names"] else [],
        "resolved": bool(row["resolved"]),
        "unresolved_note": (None if row["resolved"] else
                            RESOLUTION_NOTE.get(row["resolution_method"], "not matched")),
        "method": row["resolution_method"],
        "tmdb_id": plain_value(row["tmdb_id"]),
    }


def upcoming(ctx, addresses):
    """The section's numbers, with every request, graduate and unmatched one."""
    from rewatchables import images
    from rewatchables.app.sections.upcoming import (
        TOP_TAGS, WHY_SHOWN, queue_summary, shared_tags, tag_counts, unmatched,
    )
    from views import RESOLUTION_NOTE

    pending, graduated = ctx.upcoming, ctx.graduated
    if not len(pending) and not len(graduated):
        return {"empty": True}

    slugs = requested_slugs(pending)
    rows = pending.sort_values("source_row_number", kind="mergesort")
    graduated = graduated.sort_values(["first_episode_date", "movie_title"], kind="mergesort")
    section = {
        "empty": False,
        "summary": queue_summary(pending, graduated),
        "why_shown": WHY_SHOWN,
        "offered_tags": shared_tags(pending),
        "top_tags": [{"tag": t, "n": n} for t, n in tag_counts(pending).most_common(TOP_TAGS)],
        "requests": [request_row(r, slugs[r["upcoming_film_id"]]) for _, r in rows.iterrows()],
        "graduated": [
            {"id": addresses.films.get(g["movie_id"]), "title": g["movie_title"],
             "year": plain_value(g["movie_year"]), "requested_as": g["requested_title"],
             "aired": plain_value(g["first_episode_date"]),
             "episodes": plain_value(g["total_episodes_featured"]),
             "poster": images.file_name(g["poster_url_tmdb"])}
            for _, g in graduated.iterrows()],
        "unmatched": [
            {"id": slugs[r["upcoming_film_id"]], "title": r["title"],
             "year_raw": r["year_raw"] or None,
             "note": RESOLUTION_NOTE.get(r["resolution_method"], "not matched")}
            for _, r in unmatched(rows).iterrows()],
    }
    return section
