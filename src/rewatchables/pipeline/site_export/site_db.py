"""The public site's database, written as a sorted SQL dump: site/src/data/site.sql.

The site reads one SQLite file. It is committed as text rather than as the
binary database: a dump with one row per line, sorted by primary key, so a
publish changes only the lines for the rows that changed, where a binary
database would replace the whole file in git every time. A Framework data
loader (site/src/data/site.db.py) turns the dump into site.db at build time.

Phase 0 of the SQLite plan: the film tables and the episodes, enough to draw
a film page and to measure the database. The rest of the schema follows in
phase 1.

Everything is keyed by address (heat-1995), never by movie_id, which step 06
mints afresh on every rebuild.
"""

import math

import numpy as np
import pandas as pd

from rewatchables.pipeline.site_export.common import prepare

# table -> (column definitions, primary key columns). Rows are written sorted
# by the primary key, so the dump is the same bytes for the same data.
SCHEMA = {
    "films": ([
        ("slug", "TEXT"), ("title", "TEXT"), ("year", "INTEGER"), ("decade", "INTEGER"),
        ("sort_title", "TEXT"), ("runtime", "INTEGER"), ("tmdb", "REAL"), ("rt", "REAL"),
        ("ebert", "REAL"), ("revenue_real", "REAL"), ("budget_real", "REAL"),
        ("multiple", "REAL"), ("poster", "TEXT"), ("director_primary", "TEXT"),
        ("first_episode", "TEXT"), ("last_episode", "TEXT"), ("episodes", "INTEGER"),
        ("revisited", "INTEGER"), ("plot", "TEXT"), ("tmdb_id", "INTEGER"),
    ], ("slug",)),
    "film_genres": ([("slug", "TEXT"), ("ord", "INTEGER"), ("genre", "TEXT")], ("slug", "ord")),
    "film_directors": ([("slug", "TEXT"), ("ord", "INTEGER"), ("name", "TEXT")], ("slug", "ord")),
    "film_cast": ([("slug", "TEXT"), ("billing", "INTEGER"), ("name", "TEXT")], ("slug", "billing")),
    "film_keywords": ([("slug", "TEXT"), ("word", "TEXT")], ("slug", "word")),
    "episodes": ([
        ("id", "TEXT"), ("slug", "TEXT"), ("number", "INTEGER"), ("date", "TEXT"),
        ("is_revisit", "INTEGER"), ("revisit_sequence", "INTEGER"), ("revisit_type", "TEXT"),
        ("verdict", "TEXT"), ("rt", "REAL"), ("ebert", "REAL"), ("note", "TEXT"),
    ], ("id",)),
    "episode_room": ([("episode", "TEXT"), ("person", "TEXT"), ("chair", "TEXT")],
                     ("episode", "person")),
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


def dump(tables):
    """{table: rows} -> the dump: schema first, then each table's rows sorted
    by primary key, one INSERT per line."""
    out = ["PRAGMA foreign_keys=OFF;", "BEGIN TRANSACTION;"]
    for name, (columns, key) in SCHEMA.items():
        cols = ", ".join(f"{c} {t}" for c, t in columns)
        out.append(f"CREATE TABLE {name} ({cols}, PRIMARY KEY ({', '.join(key)}));")
        names = [c for c, _ in columns]
        index = [names.index(k) for k in key]
        rows = sorted(tables.get(name, []), key=lambda r: tuple(
            (r[i] is None, r[i] if r[i] is not None else "") for i in index))
        for row in rows:
            out.append(f"INSERT INTO {name} VALUES({','.join(sql_value(v) for v in row)});")
    out.append("COMMIT;")
    return "\n".join(out) + "\n"


# ── Tables ────────────────────────────────────────────────────────────────────

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


def tables(ctx):
    """{table: rows} for every table in SCHEMA. ctx must have been through
    prepare(), so movies carry their address."""
    from views import clean, room_long

    films = dict(zip(ctx.movies["movie_id"], ctx.movies["slug"]))
    rated = ctx.rated.set_index("movie_id")
    out = {name: [] for name in SCHEMA}

    for _, m in ctx.movies.iterrows():
        r = rated.loc[m["movie_id"]]
        s = m["slug"]
        out["films"].append([
            s, m["title"], m["year"], m["decade"], m["sort_title"], m["runtime_minutes"],
            m["rating_tmdb"], None if pd.isna(r["tomatoes_avg"]) else r["tomatoes_avg"] * 100,
            r["ebert_avg"], m.get("revenue_real"), m.get("budget_real"), m.get("multiple"),
            m["poster_url_tmdb"], m["director_primary"], m["first_episode_date"],
            m["last_episode_date"], m["total_episodes_featured"], int(m["revisited_flag"] == 1),
            clean(m["plot_summary"]), m["tmdb_id"],
        ])
        out["film_genres"] += [[s, i, g] for i, g in enumerate(m["genres"] or [])]
        out["film_directors"] += [[s, i, d] for i, d in enumerate(m["directors"] or [])]
        out["film_cast"] += [[s, i, n] for i, n in enumerate(m["cast_names"] or [])]
        out["film_keywords"] += [[s, w] for w in sorted(set(m["keywords"] or []))]

    ids = episode_ids(ctx.links, films)
    for _, e in ctx.links.iterrows():
        out["episodes"].append([
            ids[e["raw_episode_id"]], films[e["movie_id"]], e["episode_number"],
            e["episode_date"], int(bool(e["is_revisit"])), e["revisit_sequence"],
            clean(e["revisit_type"]), clean(e["cruise_hanks"]), e["tomatoes_num"],
            e["ebert_num"], clean(e["notes"]),
        ])
    room = room_long(ctx.links, "raw_episode_id")
    out["episode_room"] = [[ids[r.raw_episode_id], r.person, r.chair]
                           for r in room.itertuples()]
    return out


def site_sql(ctx):
    """The dump for this context."""
    ctx, _ = prepare(ctx)
    return dump(tables(ctx))
