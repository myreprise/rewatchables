"""
Tests for the public site's database: site.sql, the dump pipeline step 15
writes, and the queries the site runs against it (site/src/queries/).

The site cannot check its own numbers: a page runs a query and draws what
comes back. So the queries are checked here instead, against the same
database the browser loads, and their answers compared with the Streamlit
app's own functions. A query that drifts from the app fails a test rather
than shipping a different number.

The first group is pure. The rest build the database from the live one and
skip when it has not been built.
"""

import dataclasses
import json
import re
import sqlite3
import subprocess
import sys
import uuid
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rewatchables.pipeline.site_export import site_db
from views import ANCHOR, LINK_FLOOR, film_slugs, name_slugs, slugify

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "rewatchables.db"
QUERIES = ROOT / "site" / "src" / "queries"
LOADER = ROOT / "site" / "src" / "data" / "site.db.py"

live = pytest.mark.skipif(not DB_PATH.exists(),
                          reason="rewatchables.db has not been built yet")


# ── Values ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,literal", [
    (None, "NULL"), (float("nan"), "NULL"), (pd.NaT, "NULL"),
    (np.int64(7), "7"), (2.0, "2"), (2.5, "2.5"), (np.bool_(True), "1"),
    (pd.Timestamp("2015-12-22"), "'2015-12-22'"),
    ("Ocean's Eleven", "'Ocean''s Eleven'"),
    ("one\ntwo", "'one' || char(10) || 'two'"),
])
def test_sql_value(value, literal):
    assert site_db.sql_value(value) == literal


def test_a_dump_round_trips_and_keeps_one_row_per_line():
    rows = {"film_genres": [["b-2000", 1, "Drama"], ["a-1999", 0, "it's\nhere"]]}
    text = site_db.dump(rows)
    inserts = [l for l in text.splitlines() if l.startswith("INSERT INTO film_genres")]
    assert len(inserts) == 2 and inserts[0].startswith("INSERT INTO film_genres VALUES('a-1999'")
    db = sqlite3.connect(":memory:")
    db.executescript(text)
    assert db.execute("SELECT genre FROM film_genres WHERE slug = 'a-1999'").fetchone() == ("it's\nhere",)


# ── Addresses ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("title,year,slug", [
    ("Heat", 1995, "heat-1995"),
    ("Mission: Impossible", 1996, "mission-impossible-1996"),
    ("Face/Off", 1997, "face-off-1997"),
    ("Ocean's Eleven", 2001, "oceans-eleven-2001"),
    ("Ocean’s Eleven", 2001, "oceans-eleven-2001"),
    ("When Harry Met Sally...", 1989, "when-harry-met-sally-1989"),
    ("Fast & Furious", 2009, "fast-and-furious-2009"),
    ("Amélie", 2001, "amelie-2001"),
    ("48 Hrs.", 1982, "48-hrs-1982"),
    ("Heat", None, "heat"),
    ("...", 2000, "film-2000"),
])
def test_slugify(title, year, slug):
    assert slugify(title, year) == slug


def _films(*rows):
    return pd.DataFrame(rows, columns=["movie_id", "title", "year", "tmdb_id"])


def test_film_slugs_suffix_only_the_films_that_collide():
    films = _films(("a", "Crash", 2004, 1640), ("b", "Crash", 2004, 9999),
                   ("c", "Heat", 1995, 949))
    assert film_slugs(films) == {
        "a": "crash-2004-1640", "b": "crash-2004-9999", "c": "heat-1995"}


def test_film_slugs_do_not_depend_on_movie_id():
    """The whole point: step 06 reissues movie_id on every rebuild."""
    one = film_slugs(_films(("a", "Heat", 1995, 949)))
    two = film_slugs(_films(("z", "Heat", 1995, 949)))
    assert list(one.values()) == list(two.values()) == ["heat-1995"]


def test_name_slugs_suffix_a_collision_in_sorted_order():
    """Keywords and people have no TMDB id to break a tie with."""
    assert name_slugs(["writer's block", "Chris Ryan"]) == {
        "writer's block": "writers-block", "Chris Ryan": "chris-ryan"}
    for names in (["café", "cafe"], ["cafe", "café"]):
        assert name_slugs(names) == {"cafe": "cafe", "café": "cafe-2"}


# ── The database, built from the live one ─────────────────────────────────────

@pytest.fixture(scope="module")
def ctx():
    from rewatchables.app.context import build_context
    from rewatchables.app.data import stamp
    return build_context(stamp())


@pytest.fixture(scope="module")
def files(ctx):
    return site_db.site_files(ctx)


@pytest.fixture(scope="module")
def db(files):
    """site.db as the loader builds it."""
    con = sqlite3.connect(":memory:")
    con.executescript(files[0])
    con.row_factory = sqlite3.Row
    return con


def run(db, name, *params):
    sql = (QUERIES / f"{name}.sql").read_text(encoding="utf-8")
    return [dict(r) for r in db.execute(sql, params).fetchall()]


@pytest.fixture(scope="module")
def slugs(ctx):
    return film_slugs(ctx.movies)


@live
def test_the_dump_is_deterministic_and_survives_a_rebuild(ctx, files):
    """Step 06 mints a new movie_id for every film on each rebuild, and the
    links query has no ORDER BY. The dump must come out byte for byte the same
    anyway, or every publish would rewrite it."""
    fresh = {m: str(uuid.uuid4()) for m in ctx.movies["movie_id"]}

    def shuffle(frame):
        frame = frame.copy()
        if "movie_id" in frame.columns:
            frame["movie_id"] = frame["movie_id"].map(fresh).fillna(frame["movie_id"])
        return frame.sample(frac=1, random_state=11)

    rebuilt = dataclasses.replace(
        ctx, movies=shuffle(ctx.movies), links=shuffle(ctx.links), merged=shuffle(ctx.merged),
        cruise_hanks=shuffle(ctx.cruise_hanks), rated=shuffle(ctx.rated),
        graduated=shuffle(ctx.graduated))
    assert site_db.site_files(rebuilt) == files


@live
def test_no_movie_id_reaches_the_site(ctx, files):
    text = files[0] + files[1]
    assert not any(m in text for m in list(ctx.movies["movie_id"])[:80])


@live
def test_the_loader_builds_the_database(files):
    """The loader is what runs at build time, on Windows and in CI alike."""
    out = subprocess.run([sys.executable, str(LOADER)], capture_output=True, check=True).stdout
    assert out[:16] == b"SQLite format 3\x00"
    con = sqlite3.connect(":memory:")
    con.deserialize(out)
    assert con.execute("SELECT count(*) FROM films").fetchone()[0] > 0


@live
def test_row_counts_match_the_app(ctx, db):
    from rewatchables.app.sections.actors import actor_stats
    from rewatchables.app.sections.directors import director_stats
    from rewatchables.app.sections.hosts import the_room

    _, _, board = the_room(ctx.merged)
    count = lambda t: db.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    assert count("films") == len(ctx.movies)
    assert count("episodes") == len(ctx.links)
    assert count("keywords") == len(ctx.reach)
    assert count("people") == len(board)
    assert count("directors") == len(director_stats(ctx.rated))
    assert count("actors") == len(actor_stats(ctx.rated))
    assert count("requests") == len(ctx.upcoming)
    assert count("graduated") == len(ctx.graduated)


@live
def test_every_reference_lands_on_a_row(db):
    """Nothing points at a film, episode or person that is not there."""
    orphans = {
        "film_genres": "SELECT slug FROM film_genres WHERE slug NOT IN (SELECT slug FROM films)",
        "film_cast": "SELECT slug FROM film_cast WHERE slug NOT IN (SELECT slug FROM films)",
        "film_keywords": "SELECT word FROM film_keywords WHERE word NOT IN (SELECT word FROM keywords)",
        "film_shelves": "SELECT other FROM film_shelves WHERE other NOT IN (SELECT slug FROM films)",
        "episodes": "SELECT slug FROM episodes WHERE slug NOT IN (SELECT slug FROM films)",
        "episode_room": "SELECT episode FROM episode_room WHERE episode NOT IN (SELECT id FROM episodes)",
        "graduated": "SELECT film FROM graduated WHERE film IS NOT NULL AND film NOT IN (SELECT slug FROM films)",
        "person_company": "SELECT other FROM person_company WHERE other NOT IN (SELECT name FROM people)",
    }
    for table, sql in orphans.items():
        assert db.execute(sql).fetchall() == [], table


@live
def test_addresses_are_unique_and_url_safe(db):
    for table in ("films", "keywords", "people", "directors", "actors", "requests"):
        rows = [r[0] for r in db.execute(f"SELECT slug FROM {table} WHERE slug IS NOT NULL")]
        assert len(rows) == len(set(rows)), table
        assert all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", s) for s in rows), table


@live
def test_a_keyword_has_an_address_exactly_when_its_chip_links(ctx, db):
    linked = {r[0] for r in db.execute("SELECT word FROM keywords WHERE slug IS NOT NULL")}
    assert linked == {w for w, n in ctx.reach.items() if n >= LINK_FLOOR}


@live
def test_synopses_parse_and_belong_to_films(db, files):
    synopses = json.loads(files[1])
    films = {r[0] for r in db.execute("SELECT slug FROM films")}
    assert synopses and set(synopses) <= films


@live
def test_every_section_has_its_charts_and_no_duplicated_tables(db):
    figures = Counter(r[0] for r in db.execute("SELECT section FROM figures"))
    for section in ("overview", "ratings", "boxoffice", "timeline", "genres", "verdicts",
                    "hosts", "directors", "actors"):
        assert figures[section], section
    for section, keys in site_db.DERIVED.items():
        stored = {r[0] for r in db.execute("SELECT key FROM section_data WHERE section = ?", (section,))}
        assert not stored & keys, section
    for (value,) in db.execute("SELECT value FROM section_data"):
        json.loads(value)


@live
def test_every_query_runs(db):
    for path in QUERIES.glob("*.sql"):
        sql = path.read_text(encoding="utf-8")
        n = len(set(re.findall(r"\?\d", sql))) or sql.count("?")
        # A dummy that is valid both as text and as a JSON array (region_films).
        db.execute(sql, ['["x"]'] * n).fetchall()


# ── Each query against the app function it must agree with ───────────────────

def sample(movies, n=40):
    """Every film with more than one episode, plus a spread of the rest."""
    again = movies[movies["total_episodes_featured"] > 1]
    rest = movies.drop(again.index).iloc[:: max(1, len(movies) // n)]
    return pd.concat([again, rest])


@live
def test_film_queries_match_the_dossier(ctx, db, slugs):
    from rewatchables.app.overlays.dossier import cast_billing, same_director, shared_cast
    from views import rank_by_reach

    billing = cast_billing(ctx.movies)
    for _, m in sample(ctx.movies).iterrows():
        s = slugs[m["movie_id"]]
        assert [k["word"] for k in run(db, "film_keywords", s)] == \
            rank_by_reach(m["keywords"] or [], ctx.reach), s
        cast = run(db, "film_cast", s)
        assert [c["name"] for c in cast] == list(m["cast_names"][:10]), s
        assert [c["films"] for c in cast] == [billing.get(n, 0) for n in m["cast_names"][:10]], s
        assert len(run(db, "film_episodes", s)) == (ctx.links["movie_id"] == m["movie_id"]).sum()
        for kind, shelf in (("director", same_director(ctx.movies, m)),
                            ("cast", shared_cast(ctx.movies, m))):
            got = [f["slug"] for f in run(db, "film_shelf", s, kind)]
            assert len(got) == min(len(shelf), site_db.SHELF), (s, kind)
            assert set(got) <= {slugs[x] for x in shelf["movie_id"]}, (s, kind)


@live
def test_film_episodes_carry_the_dossiers_labels(ctx, db, slugs):
    """The gap and revisit kind the spine prints: views.human_gap between a
    film's airings in episode order, and the revisit type in words."""
    from views import clean, human_gap

    for _, m in sample(ctx.movies).iterrows():
        eps = ctx.links[ctx.links["movie_id"] == m["movie_id"]].sort_values(
            "episode_number", kind="mergesort")
        want, previous = [], None
        for _, e in eps.iterrows():
            days = (e["episode_date"] - previous).days if previous is not None else 0
            gap = human_gap(days) if days > 0 else None
            previous = e["episode_date"]
            kind = None
            if e["is_revisit"]:
                kind = (clean(e["revisit_type"]) or "revisit").replace("_", " ").replace(" revisit", "")
            want.append((gap, kind))
        got = run(db, "film_episodes", slugs[m["movie_id"]])
        assert [(e["gap_before"], e["revisit_kind"]) for e in got] == want, m["title"]


@live
def test_explorer_rows_carry_the_explorers_ratings(ctx, db, slugs):
    rows = {r["slug"]: r for r in run(db, "explorer")}
    assert len(rows) == len(ctx.movies)
    for _, m in ctx.rated.iterrows():
        r = rows[slugs[m["movie_id"]]]
        if pd.isna(m["tomatoes_avg"]):
            assert r["rt"] is None
        else:
            assert r["rt"] == pytest.approx(m["tomatoes_avg"] * 100, abs=0.05)
        assert r["director_primary"] == m["director_primary"]


@live
def test_keyword_queries_match_the_keyword_overlay(ctx, db, slugs):
    from rewatchables.app.overlays.keyword import keyword_profile

    words = [w for w, n in sorted(ctx.reach.items()) if n >= LINK_FLOOR][::60]
    for word in words:
        prof = keyword_profile(ctx.movies, ctx.keywords, word)
        films = run(db, "keyword_films", word)
        assert {f["slug"] for f in films} == {slugs[m] for m in prof["films"]["movie_id"]}, word
        assert [p["word"] for p in run(db, "keyword_partners", word)] == prof["partners"], word
        if not prof["thin"]:
            decades = Counter(f["decade"] for f in films if f["decade"] is not None)
            assert max(decades, key=lambda d: (decades[d], -d)) == prof["peak"], word


@live
def test_keyword_region_and_catalogue_match_the_overlay(ctx, db):
    """The page finds a keyword's region siblings by the same rule as
    views.region_of, then counts their films with region_films."""
    from rewatchables.app.overlays.keyword import keyword_profile
    from views import region_of

    vocabulary = [r["word"] for r in run(db, "keywords")]
    regional = [w for w, n in sorted(ctx.reach.items()) if n >= LINK_FLOOR and region_of(w)][::15]
    assert regional
    for word in regional:
        prof = keyword_profile(ctx.movies, ctx.keywords, word)
        siblings = [w for w in vocabulary if region_of(w) == region_of(word)]
        if prof["region"] is None:
            assert len(siblings) <= 1, word
            continue
        assert len(siblings) == prof["region_places"], word
        assert run(db, "region_films", json.dumps(siblings))[0]["films"] == prof["region_films"], word
    cat = run(db, "catalogue")[0]
    assert cat["films"] == len(ctx.movies) and cat["airings"] == len(ctx.links)
    assert cat["avg_tmdb"] == pytest.approx(ctx.movies["rating_tmdb"].dropna().mean())


@live
def test_person_queries_match_the_hosts_lookup(ctx, db):
    from rewatchables.app.analysis import LEAN_Q, person_shelf
    from rewatchables.app.sections.hosts import (
        regular_leans, sits_with, the_room, verdict_tally,
    )

    _, others, board = the_room(ctx.merged)
    regulars, _, leans = regular_leans(ctx.merged, others, board)
    held = leans[leans["q"] < LEAN_Q]
    assert [p["name"] for p in run(db, "people")] == list(board.index)
    for name in board.index:
        shelf = person_shelf(ctx.merged, name)
        got = run(db, "person_shelf", name)
        assert [(r["date"], r["number"]) for r in got] == \
            [(f"{d:%Y-%m-%d}", int(n)) for d, n in zip(shelf["episode_date"], shelf["episode_number"])], name
        ids = set(shelf["raw_episode_id"])
        assert [(c["name"], c["episodes"]) for c in run(db, "person_company", name)] == \
            [(o, int(n)) for o, n in sits_with(others, ids, name).head(site_db.COMPANY).items()], name
        tally = verdict_tally(ctx.merged, ids)
        assert {v["verdict"]: v["n"] for v in run(db, "person_verdicts", name)} == \
            {k: int(n) for k, n in tally.items()}, name
        mine = held[held["person"] == name].sort_values(["q", "metric"], kind="mergesort")
        assert len(run(db, "person_leans", name)) == len(mine), name
    assert len(run(db, "leans")) == len(leans)


@live
def test_hosts_queries_match_the_section(ctx, db):
    from rewatchables.app.sections.hosts import BENCH_FLOOR, the_room, without_anchor

    _, _, board = the_room(ctx.merged)
    assert [p["name"] for p in run(db, "bench", BENCH_FLOOR)] == \
        list(board[board["episodes"] >= BENCH_FLOOR].index)
    solo = run(db, "without_anchor", ANCHOR)
    groups = without_anchor(ctx.merged)
    assert len(solo) == sum(len(g) for _, g in groups)
    assert Counter(r["host"] or "No host listed" for r in solo) == \
        Counter({host: len(g) for host, g in groups})


@live
def test_spotlight_queries_match_directors_and_actors(ctx, db, slugs):
    from rewatchables.app.analysis import films_by_actor, films_by_director
    from rewatchables.app.sections.actors import (
        directors_returned_to, ranked_actors, top_actors,
    )
    from rewatchables.app.sections.directors import (
        actors_brought_back, ranked_directors, top_directors,
    )

    rated = ctx.rated
    assert [d["name"] for d in run(db, "directors_table")] == list(ranked_directors(rated)["director"])
    assert [a["name"] for a in run(db, "actors_table")] == \
        list(ranked_actors(rated, ctx.gender_map)["actor"])
    for kind, top in (("director", top_directors(rated)["director"]),
                      ("actor", top_actors(rated)["actor"])):
        picker = run(db, "spotlight_picker", kind)
        assert {p["name"] for p in picker} == set(top), kind
    for name in list(top_directors(rated)["director"])[:8]:
        films = films_by_director(rated, name)
        assert {f["slug"] for f in run(db, "spotlight_films", "director", name)} == \
            {slugs[m] for m in films["movie_id"]}, name
        assert [(c["name"], c["films"]) for c in run(db, "collaborators", "director", name)] == \
            actors_brought_back(films), name
    for name in list(top_actors(rated)["actor"])[:8]:
        films = films_by_actor(rated, name)
        assert {f["slug"] for f in run(db, "spotlight_films", "actor", name)} == \
            {slugs[m] for m in films["movie_id"]}, name
        assert [(c["name"], c["films"]) for c in run(db, "collaborators", "actor", name)] == \
            directors_returned_to(films), name


@live
def test_section_queries_match_their_frames(ctx, db, slugs):
    from rewatchables.app.sections.boxoffice import money_table

    assert [r["slug"] for r in run(db, "money_table")] == \
        [slugs[m] for m in money_table(ctx.movies)["movie_id"]]
    ledger = Counter(r["verdict"] for r in run(db, "ledger"))
    assert ledger == Counter(ctx.cruise_hanks["verdict"])
    requests = run(db, "requests")
    assert len(requests) == len(ctx.upcoming)
    source = ctx.upcoming.sort_values("source_row_number")
    for got, (_, want) in zip(requests, source.iterrows()):
        assert got["title"] == want["title"]
        assert (got["tags"].split("|") if got["tags"] else []) == list(want["tags"]), want["title"]
    assert len(run(db, "graduated")) == len(ctx.graduated)


# ── Each section's stored numbers against the app ─────────────────────────────

def section(db, name):
    return {r["key"]: json.loads(r["value"]) for r in run(db, "section_data", name)}


@live
def test_overview_numbers_are_the_apps(ctx, db, slugs):
    from rewatchables.app.sections.overview import came_back_to, show_now
    from rewatchables.app.state import SLUGS

    ov = section(db, "overview")
    now = show_now(ctx.episodes, ctx.merged, ctx.movies)
    assert ov["tiles"]["episodes"] == len(ctx.episodes)
    assert ov["tiles"]["films"] == len(ctx.movies)
    assert ov["tiles"]["last_12_months"] == now["n_last_year"]
    assert ov["as_of"] == now["latest_air"].strftime("%Y-%m-%d")
    assert {f["id"] for f in ov["came_back_to"]} == {
        slugs[m] for m in came_back_to(ctx.movies)["movie_id"]}
    assert ov["anchor"] not in {r["name"] for r in ov["regulars"]}
    # One door per section but the overview, each to a page the site has.
    assert len(ov["doors"]) == len(SLUGS) - 1
    pages = ROOT / "site" / "src"
    for door in ov["doors"]:
        assert (pages / f"{door['path']}.md").exists(), door["path"]


@live
def test_section_numbers_are_the_apps(ctx, db):
    from rewatchables.app.sections import (
        actors, boxoffice, directors, hosts, ratings, timeline, upcoming, verdicts,
    )

    b = section(db, "boxoffice")["summary"]
    s = boxoffice.summary(ctx.movies)
    assert (b["with_gross"], b["under_break_even"], b["merit_films"]) == (
        s["with_gross"], s["under_break_even"], s["merit_films"])
    assert b["rho"] == round(s["rho"], 2)

    critic, _ = ratings.divergence(ctx.merged)
    assert [r["title"] for r in section(db, "ratings")["critics_love"]] == list(critic["title"])

    assert len(section(db, "timeline")["revisited"]) == len(timeline.revisited_films(ctx.movies))

    v = section(db, "verdicts")
    assert v["standing"] == verdicts.standing(ctx.cruise_hanks)
    assert v["lead_changes"] == verdicts.running_margin(ctx.cruise_hanks)[1]

    h = section(db, "hosts")
    room, others, board = hosts.the_room(ctx.merged)
    with_anchor, hosted = hosts.anchor_share(room)
    assert (h["with_anchor"], h["anchor_hosted"], h["everyone_else"]) == (
        len(with_anchor), hosted, len(board))
    assert h["comparisons"] == len(hosts.regular_leans(ctx.merged, others, board)[2])

    d = section(db, "directors")
    assert d["tiles"]["directors"] == directors.director_counts(ctx.rated).size
    r, n = directors.volume_reception(ctx.rated)
    assert (d["r"], d["scatter_people"]) == (round(r, 2), n)

    a = section(db, "actors")
    assert a["tiles"]["actors"] == len(actors.cast_counts(ctx.rated))
    assert a["credits_total"] == sum(actors.gender_credits(ctx.rated, ctx.gender_map).values())
    r, n = actors.volume_reception(ctx.rated)
    assert (a["r"], a["scatter_people"]) == (round(r, 2), n)

    assert section(db, "upcoming")["summary"] == upcoming.queue_summary(ctx.upcoming, ctx.graduated)
