"""The public site's database, written as a sorted SQL dump: site/src/data/site.sql.

The site reads one SQLite file. It is committed as text rather than as the
binary database: a dump with one row per line, sorted by primary key, so a
publish changes only the lines for the rows that changed, where a binary
database would replace the whole file in git every time. A Framework data
loader (site/src/data/site.db.py) turns the dump into site.db at build time.

What goes in, and who computes it:

  * The catalogue as plain tables -- films, their genres, directors, cast and
    keywords, the episodes and who was in the room, the Upcoming requests.
    The browser filters, joins and counts these in SQL (site/src/queries/).
  * Anything with a ranking rule or a statistic, computed here by the app's
    own functions: keyword reach and chip bands, the related-film shelves,
    the bench, everyone's frequent company, the permutation-tested leans,
    director and actor statistics and their collaborators.
  * Each section's charts (`figures`, Plotly specs) and the numbers its tiles
    and captions print (`section_data`), from the section builders in this
    package, already checked against the app.

The full Wikipedia synopses, about 2 MB, go to synopses.json beside it,
loaded only when a reader expands one.

Everything is keyed by address (heat-1995), never by movie_id, which step 06
mints afresh on every rebuild.
"""

import json
import math
from collections import Counter

import numpy as np
import pandas as pd

from rewatchables import images
from rewatchables.pipeline.site_export.common import prepare

SHELF = 4          # films per related-film shelf, as on the app's dossier
COMPANY = 6        # names in a person's "Who they sit with", as in the app

# Tables whose rows carry long text. Every other table is WITHOUT ROWID: its
# rows live in the primary key's own b-tree, rather than in a table plus an
# index that stores the key columns a second time. For the link tables, whose
# key is most of the row, that is the difference between a 981 KB and a
# 700 KB database, gzipped. SQLite advises the ordinary layout for wide rows,
# so these keep it.
WIDE = {"films", "figures", "section_data", "requests"}

# section_data keys left out because a table already holds their rows: the
# page queries the table (site/src/queries/) instead of a second copy.
DERIVED = {
    "boxoffice": {"table"},           # films
    "directors": {"table", "spotlight"},   # directors
    "actors": {"table", "spotlight"},      # actors
    "verdicts": {"ledger"},           # episodes
    "hosts": {"bench", "all_comparisons", "regulars", "without"},  # people, leans, episodes
}

# table -> (column definitions, primary key columns). Rows are written sorted
# by the primary key, so the dump is the same bytes for the same data.
SCHEMA = {
    "films": ([
        ("slug", "TEXT"), ("title", "TEXT"), ("year", "INTEGER"), ("decade", "INTEGER"),
        ("sort_title", "TEXT"), ("runtime", "INTEGER"), ("tmdb", "REAL"),
        ("rt", "REAL"), ("ebert", "REAL"),
        ("revenue_real", "REAL"), ("budget_real", "REAL"), ("multiple", "REAL"),
        ("box_office", "TEXT"), ("budget", "TEXT"), ("money_provisional", "INTEGER"),
        ("poster", "TEXT"), ("director_primary", "TEXT"),
        ("first_episode", "TEXT"), ("last_episode", "TEXT"), ("episodes", "INTEGER"),
        ("revisited", "INTEGER"), ("plot", "TEXT"), ("synopsis_words", "INTEGER"),
        ("tmdb_id", "INTEGER"), ("confidence", "TEXT"), ("enriched", "TEXT"),
        ("wikipedia", "TEXT"), ("wikidata", "TEXT"),
    ], ("slug",)),
    "film_genres": ([("slug", "TEXT"), ("ord", "INTEGER"), ("genre", "TEXT")], ("slug", "ord")),
    "film_directors": ([("slug", "TEXT"), ("ord", "INTEGER"), ("name", "TEXT")], ("slug", "ord")),
    "film_cast": ([("slug", "TEXT"), ("billing", "INTEGER"), ("name", "TEXT")], ("slug", "billing")),
    "film_keywords": ([("slug", "TEXT"), ("word", "TEXT")], ("slug", "word")),
    "film_shelves": ([("slug", "TEXT"), ("kind", "TEXT"), ("rank", "INTEGER"), ("other", "TEXT")],
                     ("slug", "kind", "rank")),
    "keywords": ([("word", "TEXT"), ("slug", "TEXT"), ("reach", "INTEGER"), ("band", "TEXT")],
                 ("word",)),
    "episodes": ([
        ("id", "TEXT"), ("slug", "TEXT"), ("number", "INTEGER"), ("date", "TEXT"),
        ("is_revisit", "INTEGER"), ("revisit_sequence", "INTEGER"), ("revisit_type", "TEXT"),
        ("verdict", "TEXT"), ("rt", "REAL"), ("ebert", "REAL"), ("note", "TEXT"),
        ("gap_before", "TEXT"), ("revisit_kind", "TEXT"),
    ], ("id",)),
    "episode_room": ([("episode", "TEXT"), ("seat", "INTEGER"), ("person", "TEXT"),
                      ("chair", "TEXT")], ("episode", "seat")),
    "people": ([("name", "TEXT"), ("slug", "TEXT"), ("rank", "INTEGER"), ("episodes", "INTEGER"),
                ("hosted", "INTEGER"), ("first", "TEXT"), ("last", "TEXT"),
                ("regular", "INTEGER")], ("name",)),
    "person_company": ([("person", "TEXT"), ("ord", "INTEGER"), ("other", "TEXT"),
                        ("episodes", "INTEGER")], ("person", "ord")),
    "leans": ([("person", "TEXT"), ("metric", "TEXT"), ("measure", "TEXT"), ("n", "INTEGER"),
               ("mean_in", "REAL"), ("mean_out", "REAL"), ("diff", "REAL"), ("p", "REAL"),
               ("q", "REAL"), ("shown", "INTEGER"), ("phrase", "TEXT"), ("theirs", "TEXT"),
               ("others", "TEXT"), ("gap", "TEXT")], ("person", "metric")),
    "directors": ([("name", "TEXT"), ("slug", "TEXT"), ("top_rank", "INTEGER"),
                   ("films", "INTEGER"), ("avg_tmdb", "REAL"), ("avg_rt", "REAL"),
                   ("avg_runtime", "REAL"), ("first_year", "INTEGER"), ("last_year", "INTEGER")],
                  ("name",)),
    "actors": ([("name", "TEXT"), ("slug", "TEXT"), ("top_rank", "INTEGER"),
                ("films", "INTEGER"), ("avg_tmdb", "REAL"), ("avg_rt", "REAL"),
                ("avg_runtime", "REAL"), ("first_year", "INTEGER"), ("last_year", "INTEGER"),
                ("gender", "TEXT")], ("name",)),
    "collaborators": ([("kind", "TEXT"), ("name", "TEXT"), ("ord", "INTEGER"),
                       ("other", "TEXT"), ("films", "INTEGER")], ("kind", "name", "ord")),
    "requests": ([
        ("slug", "TEXT"), ("ord", "INTEGER"), ("title", "TEXT"), ("year_raw", "TEXT"),
        ("year", "INTEGER"), ("decade", "INTEGER"), ("sort_title", "TEXT"), ("poster", "TEXT"),
        ("tmdb", "REAL"), ("runtime", "INTEGER"), ("note", "TEXT"), ("contributor", "TEXT"),
        ("by_label", "TEXT"), ("by_href", "TEXT"), ("directors", "TEXT"), ("genres", "TEXT"),
        ("cast", "TEXT"), ("plot", "TEXT"), ("resolved", "INTEGER"),
        ("unresolved_note", "TEXT"), ("method", "TEXT"), ("tmdb_id", "INTEGER"),
    ], ("slug",)),
    "request_tags": ([("slug", "TEXT"), ("ord", "INTEGER"), ("tag", "TEXT")], ("slug", "ord")),
    "graduated": ([("ord", "INTEGER"), ("film", "TEXT"), ("requested_as", "TEXT"),
                   ("aired", "TEXT"), ("episodes", "INTEGER")], ("ord",)),
    "figures": ([("section", "TEXT"), ("name", "TEXT"), ("spec", "TEXT")], ("section", "name")),
    "section_data": ([("section", "TEXT"), ("key", "TEXT"), ("value", "TEXT")],
                     ("section", "key")),
}


# ── Values ────────────────────────────────────────────────────────────────────

def sql_value(value):
    """One value as an SQL literal. A newline inside text is written as
    char(10), so every row stays on one line of the dump."""
    if value is None or value is pd.NaT or value is pd.NA:
        return "NULL"
    if isinstance(value, pd.Timestamp):
        return "NULL" if pd.isna(value) else f"'{value:%Y-%m-%d}'"
    if isinstance(value, (bool, np.bool_)):
        return "1" if value else "0"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, (float, np.floating)):
        if math.isnan(value):
            return "NULL"
        return str(int(value)) if float(value).is_integer() else repr(float(value))
    text = str(value).replace("'", "''").replace("\r\n", "\n")
    return "'" + text.replace("\n", "' || char(10) || '") + "'"


def as_json(value):
    """A value stored as JSON text: no spaces, no NaN. Keys keep the order the
    section builder gave them, which is fixed, and which a page can rely on:
    the tale-of-the-tape table takes its column order from its keys."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def dump(tables):
    """{table: rows} -> the dump: schema first, then each table's rows sorted
    by primary key, one INSERT per line."""
    out = ["PRAGMA foreign_keys=OFF;", "BEGIN TRANSACTION;"]
    for name, (columns, key) in SCHEMA.items():
        cols = ", ".join(f"{c} {t}" for c, t in columns)
        layout = "" if name in WIDE else " WITHOUT ROWID"
        out.append(f"CREATE TABLE {name} ({cols}, PRIMARY KEY ({', '.join(key)})){layout};")
        names = [c for c, _ in columns]
        index = [names.index(k) for k in key]
        rows = sorted(tables.get(name, []), key=lambda r: tuple(
            (r[i] is None, r[i] if r[i] is not None else "") for i in index))
        for row in rows:
            out.append(f"INSERT INTO {name} VALUES({','.join(sql_value(v) for v in row)});")
    out.append("COMMIT;")
    return "\n".join(out) + "\n"


def num(value, places=None):
    """A number for a REAL column: None for NaN, rounded when asked."""
    if value is None or pd.isna(value):
        return None
    return round(float(value), places) if places is not None else float(value)


# ── The catalogue ─────────────────────────────────────────────────────────────

def episode_ids(links, films):
    """Each airing's id: date, episode number and film, e.g.
    2015-12-22-001-heat-1995. The sheet reuses a number when a film is
    revisited, so the number alone is not an id; raw_episode_id is minted
    afresh by the pipeline and is not one either."""
    return {
        rid: f"{d:%Y-%m-%d}-{int(n):03d}-{films[m]}"
        for rid, d, n, m in zip(links["raw_episode_id"], links["episode_date"],
                                links["episode_number"], links["movie_id"])
    }


def film_tables(ctx, out):
    from rewatchables.app.overlays.dossier import same_director, shared_cast
    from views import clean, money

    rated = ctx.rated.set_index("movie_id")
    for _, m in ctx.movies.iterrows():
        r = rated.loc[m["movie_id"]]
        s = m["slug"]
        box = m.get("revenue_real")
        out["films"].append([
            s, m["title"], m["year"], m["decade"], m["sort_title"], m["runtime_minutes"],
            num(m["rating_tmdb"]),
            num(r["tomatoes_avg"] * 100, 1) if pd.notna(r["tomatoes_avg"]) else None,
            num(r["ebert_avg"]),
            num(box), num(m.get("budget_real")), num(m.get("multiple")),
            money(box) if pd.notna(box) else None,
            money(m.get("budget_real")) if pd.notna(m.get("budget_real")) else None,
            int(bool(m.get("money_provisional"))),
            images.file_name(m["poster_url_tmdb"]), m["director_primary"],
            m["first_episode_date"], m["last_episode_date"], m["total_episodes_featured"],
            int(m["revisited_flag"] == 1), clean(m["plot_summary"]),
            m["plot_summary_wiki_words"], m["tmdb_id"],
            clean(m["canonical_key_confidence"]),
            str(m["enriched_at"])[:10] if clean(m["enriched_at"]) else None,
            clean(m["wikipedia_url"]), clean(m["wikidata_qid"]),
        ])
        out["film_genres"] += [[s, i, g] for i, g in enumerate(m["genres"] or [])]
        out["film_directors"] += [[s, i, d] for i, d in enumerate(m["directors"] or [])]
        out["film_cast"] += [[s, i, n] for i, n in enumerate(m["cast_names"] or [])]
        out["film_keywords"] += [[s, w] for w in sorted(set(m["keywords"] or []))]
        for kind, shelf in (("director", same_director(ctx.movies, m)),
                            ("cast", shared_cast(ctx.movies, m))):
            out["film_shelves"] += [[s, kind, i, other]
                                    for i, other in enumerate(shelf["slug"].head(SHELF))]


def keyword_table(ctx, addresses, out):
    from views import chip_band

    out["keywords"] = [[w, addresses.keyword(w), n, chip_band(n)] for w, n in ctx.reach.items()]


def episode_labels(links):
    """raw_episode_id -> (gap since the film's previous airing, revisit kind),
    in the words the dossier's spine prints them: "4 yr 1 mo later",
    "regular". The first airing of a film has no gap; a first watch no kind."""
    from views import clean, human_gap

    out = {}
    for _, eps in links.groupby("movie_id", sort=False):
        previous = None
        for _, ep in eps.sort_values("episode_number", kind="mergesort").iterrows():
            gap = None
            if previous is not None and pd.notna(ep["episode_date"]):
                days = (ep["episode_date"] - previous).days
                gap = human_gap(days) if days > 0 else None
            previous = ep["episode_date"]
            kind = None
            if ep["is_revisit"]:
                kind = (clean(ep["revisit_type"]) or "revisit").replace("_", " ")
                kind = kind.replace(" revisit", "")
            out[ep["raw_episode_id"]] = (gap, kind)
    return out


def episode_tables(ctx, addresses, out):
    from views import ROOM, clean, person_name

    films = addresses.films
    ids = episode_ids(ctx.links, films)
    labels = episode_labels(ctx.links)
    for _, e in ctx.links.iterrows():
        eid = ids[e["raw_episode_id"]]
        out["episodes"].append([
            eid, films[e["movie_id"]], e["episode_number"], e["episode_date"],
            int(bool(e["is_revisit"])), e["revisit_sequence"], clean(e["revisit_type"]),
            clean(e["cruise_hanks"]), num(e["tomatoes_num"]), num(e["ebert_num"]),
            clean(e["notes"]), *labels[e["raw_episode_id"]],
        ])
        # Every chair in order, as the sheet has it. A name in two chairs of
        # one episode is one appearance, in the earlier chair, as room_long()
        # counts it.
        seen = set()
        for seat, chair in enumerate(ROOM):
            name = person_name(e.get(chair))
            if name and name not in seen:
                seen.add(name)
                out["episode_room"].append([eid, seat, name, chair])
    return ids


# ── People, and the statistics about them ─────────────────────────────────────

def people_tables(ctx, addresses, out):
    from rewatchables.app.analysis import LEAN_Q, person_shelf
    from rewatchables.app.sections.hosts import regular_leans, sits_with, the_room
    from views import MEASURE_LABEL, lean_phrase, lean_value

    _, others, board = the_room(ctx.merged)
    regulars, _, leans = regular_leans(ctx.merged, others, board)
    for rank, (name, r) in enumerate(board.iterrows(), start=1):
        out["people"].append([name, addresses.person(name), rank, int(r["episodes"]),
                              int(r["hosted"]), r["first"], r["last"], int(name in regulars)])
        ids = set(person_shelf(ctx.merged, name)["raw_episode_id"])
        company = sits_with(others, ids, name).head(COMPANY)
        out["person_company"] += [[name, i, other, int(n)]
                                  for i, (other, n) in enumerate(company.items())]
    for r in leans.itertuples():
        out["leans"].append([
            r.person, r.metric, MEASURE_LABEL.get(r.metric, f"{r.metric} share"), int(r.n),
            num(r.mean_in), num(r.mean_out), num(r.diff), num(r.p), num(r.q),
            int(r.q < LEAN_Q), lean_phrase(r.metric, r.mean_in, r.mean_out, r.diff),
            lean_value(r.metric, r.mean_in), lean_value(r.metric, r.mean_out),
            lean_value(r.metric, r.diff, signed=True),
        ])


def spotlight_tables(ctx, addresses, out):
    from rewatchables.app.analysis import films_by_actor, films_by_director
    from rewatchables.app.data import GENDER_LABEL
    from rewatchables.app.sections.actors import (
        actor_stats, directors_returned_to, top_actors,
    )
    from rewatchables.app.sections.directors import (
        actors_brought_back, director_stats, top_directors,
    )

    rated = ctx.rated
    top_d = {n: i for i, n in enumerate(top_directors(rated)["director"], start=1)}
    top_a = {n: i for i, n in enumerate(top_actors(rated)["actor"], start=1)}

    def stat_row(r):
        return [num(r["avg_tmdb"]), num(r["avg_rt"]), num(r["avg_runtime"]),
                r["first_year"], r["last_year"]]

    for _, r in director_stats(rated).iterrows():
        name = r["director"]
        out["directors"].append([name, addresses.director(name), top_d.get(name),
                                 int(r["films"]), *stat_row(r)])
        pairs = actors_brought_back(films_by_director(rated, name))
        out["collaborators"] += [["director", name, i, other, int(k)]
                                 for i, (other, k) in enumerate(pairs)]
    for _, r in actor_stats(rated).iterrows():
        name = r["actor"]
        gender = GENDER_LABEL.get(ctx.gender_map.get(name, "unknown"))
        out["actors"].append([name, addresses.actor(name), top_a.get(name),
                              int(r["films"]), *stat_row(r), gender])
        pairs = directors_returned_to(films_by_actor(rated, name))
        out["collaborators"] += [["actor", name, i, other, int(k)]
                                 for i, (other, k) in enumerate(pairs)]


# ── Upcoming ──────────────────────────────────────────────────────────────────

def request_tables(ctx, addresses, out):
    from rewatchables.pipeline.site_export.upcoming import requested_page, requested_slugs

    pending, graduated = ctx.upcoming, ctx.graduated
    if len(pending):
        slugs = requested_slugs(pending)
        for _, r in pending.iterrows():
            p = requested_page(r, slugs[r["upcoming_film_id"]])
            by = p["by"] or {}
            out["requests"].append([
                p["id"], p["order"], p["title"], p["year_raw"], p["year"], p["decade"],
                p["sort"], p["poster"], p["tmdb"], p["runtime"], p["note"], p["contributor"],
                by.get("label"), by.get("href"), as_json(p["directors"]), as_json(p["genres"]),
                as_json(p["cast"]), p["plot"], int(p["resolved"]), p["unresolved_note"],
                p["method"], p["tmdb_id"],
            ])
            out["request_tags"] += [[p["id"], i, t] for i, t in enumerate(p["tags"])]
    if len(graduated):
        graduated = graduated.sort_values(["first_episode_date", "movie_title"], kind="mergesort")
        for i, (_, g) in enumerate(graduated.iterrows()):
            out["graduated"].append([i, addresses.films.get(g["movie_id"]),
                                     g["requested_title"], g["first_episode_date"],
                                     g["total_episodes_featured"]])


# ── Sections: their charts and the numbers their captions print ───────────────

def section_tables(ctx, addresses, out):
    """figures and section_data, from the section builders in this package.

    Each builder returns the section's payload: its figures go to `figures`,
    one row per chart, and every other top-level value to `section_data`, one
    row per key. The overview's chart is a figure of the overview's.
    """
    from rewatchables.pipeline.site_export.keywords import keywords_index
    from rewatchables.pipeline.site_export.overview import charts, overview
    from rewatchables.pipeline.site_export.sections import SECTIONS
    from rewatchables.pipeline.site_export.upcoming import upcoming

    payloads = {name: build(ctx, addresses) for name, build in SECTIONS.items()}
    payloads["overview"] = {**overview(ctx, addresses), "figures": charts(ctx)}
    keywords = keywords_index(ctx, addresses)
    keywords.pop("vocabulary")          # the keywords table holds it
    payloads["keywords"] = keywords
    queue = upcoming(ctx, addresses)
    for key in ("requests", "graduated", "unmatched"):
        queue.pop(key, None)           # the requests tables hold these
    payloads["upcoming"] = queue

    for section, payload in payloads.items():
        for name, spec in (payload.pop("figures", None) or {}).items():
            if spec is not None:
                out["figures"].append([section, name, as_json(spec)])
        for key, value in payload.items():
            if key not in DERIVED.get(section, ()):
                out["section_data"].append([section, key, as_json(value)])


# ── The step ──────────────────────────────────────────────────────────────────

def tables(ctx, addresses):
    """{table: rows} for every table in SCHEMA. ctx must have been through
    prepare(), so movies carry their address."""
    out = {name: [] for name in SCHEMA}
    film_tables(ctx, out)
    keyword_table(ctx, addresses, out)
    episode_tables(ctx, addresses, out)
    people_tables(ctx, addresses, out)
    spotlight_tables(ctx, addresses, out)
    request_tables(ctx, addresses, out)
    section_tables(ctx, addresses, out)
    return out


def synopses(ctx):
    """{address: full Wikipedia synopsis}, one film per line, sorted."""
    from views import clean

    rows = {m["slug"]: clean(m["plot_summary_wiki"]) for _, m in ctx.movies.iterrows()}
    rows = {k: v for k, v in sorted(rows.items()) if v}
    body = ",\n".join(f"{json.dumps(k)}:{json.dumps(v, ensure_ascii=False)}"
                      for k, v in rows.items())
    return "{\n" + body + "\n}\n"


def site_files(ctx):
    """(site.sql, synopses.json) for this context."""
    ctx, addresses = prepare(ctx)
    return dump(tables(ctx, addresses)), synopses(ctx)


def site_sql(ctx):
    """The dump alone."""
    return site_files(ctx)[0]
