"""
Tests for pipeline step 15, the public site's data export.

The site cannot check its own data: it is a static build that reads whatever
JSON it is given, and a NaN, a missing film page or a number that drifted from
the app's would ship silently. So the checks are here, on the export.

The first group is pure. The second runs the export against the live database
into a temporary folder and skips when the database has not been built.
"""

import dataclasses
import json
import re
import uuid
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from rewatchables.pipeline import s15_export_site as export_site
from rewatchables.pipeline.site_export import common
from rewatchables.pipeline.site_export.films import SHELF
from views import ANCHOR, LINK_FLOOR, film_slugs, name_slugs, slugify

DB_PATH = Path(__file__).parent.parent / "rewatchables.db"


def _strict_load(path):
    """json.loads that refuses the bare NaN/Infinity json.dumps can write."""
    def refuse(token):
        raise ValueError(f"{path.name} contains {token}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=refuse)


# ── Serialisation ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (float("nan"), None),
    (np.float64("nan"), None),
    (pd.NaT, None),
    (None, None),
    (np.int64(7), 7),
    (np.float64(2.5), 2.5),
    (np.bool_(True), True),
    (pd.Timestamp("2015-12-01 00:00"), "2015-12-01"),
    ([np.int64(1), float("nan")], [1, None]),
    ("Heat", "Heat"),
])
def test_plain_value_writes_valid_json(value, expected):
    assert common.plain_value(value) == expected


def test_plain_value_survives_a_round_trip():
    out = json.dumps(common.plain_value(np.float64("nan")))
    assert out == "null"


def test_blurb_cuts_at_a_word_boundary():
    text = "word " * 100
    cut = common.blurb(text, limit=23)
    assert cut == "word word word word…"
    assert common.blurb("short", limit=23) == "short"
    assert common.blurb(None) == ""


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
    # Folded to one address: the earlier in sorted order keeps the plain one,
    # whichever order they arrive in.
    for names in (["café", "cafe"], ["cafe", "café"]):
        assert name_slugs(names) == {"cafe": "cafe", "café": "cafe-2"}


def test_write_pages_removes_pages_no_longer_in_use(tmp_path):
    (tmp_path / "gone.json").write_text("{}", encoding="utf-8")
    assert common.write_pages(tmp_path, {"kept": {"a": 1}}) == 1
    assert {p.name for p in tmp_path.glob("*.json")} == {"kept.json"}


def test_write_rows_puts_one_row_per_line(tmp_path):
    path = tmp_path / "rows.json"
    common.write_rows(path, [{"id": "a"}, {"id": "b"}])
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines == ["[", '{"id": "a"},', '{"id": "b"}', "]"]
    assert json.loads(path.read_text(encoding="utf-8")) == [{"id": "a"}, {"id": "b"}]


# ── Against the live database ─────────────────────────────────────────────────

live = pytest.mark.skipif(not DB_PATH.exists(),
                          reason="rewatchables.db has not been built yet")


@pytest.fixture(scope="module")
def ctx():
    from rewatchables.app.context import build_context
    from rewatchables.app.data import stamp
    return build_context(stamp())


@pytest.fixture(scope="module")
def exported(ctx, tmp_path_factory):
    out = tmp_path_factory.mktemp("site") / "data"
    pages = out / "films"
    pages.mkdir(parents=True)
    # A page for a film no longer in the catalogue, which the export must remove.
    (pages / "not-a-film.json").write_text("{}", encoding="utf-8")
    (out / "keywords").mkdir()
    (out / "keywords" / "not-a-keyword.json").write_text("{}", encoding="utf-8")
    export_site.export(ctx, out=out, theme_dest=None)
    return out


@live
def test_every_film_has_a_page_and_nothing_else(ctx, exported):
    pages = {p.stem for p in (exported / "films").glob("*.json")}
    assert pages == set(film_slugs(ctx.movies).values())


@live
def test_index_rows_match_the_pages(exported):
    rows = _strict_load(exported / "films.json")
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids))
    assert set(ids) == {p.stem for p in (exported / "films").glob("*.json")}


@live
def test_no_file_holds_a_bare_nan(exported):
    for path in exported.rglob("*.json"):
        _strict_load(path)


@live
def test_overview_numbers_are_the_apps(ctx, exported):
    from rewatchables.app.sections.overview import came_back_to, show_now

    ov = _strict_load(exported / "overview.json")
    now = show_now(ctx.episodes, ctx.merged, ctx.movies)
    assert ov["tiles"]["episodes"] == len(ctx.episodes)
    assert ov["tiles"]["films"] == len(ctx.movies)
    assert ov["tiles"]["last_12_months"] == now["n_last_year"]
    assert ov["as_of"] == now["latest_air"].strftime("%Y-%m-%d")
    slugs = film_slugs(ctx.movies)
    assert {f["id"] for f in ov["came_back_to"]} == {
        slugs[m] for m in came_back_to(ctx.movies)["movie_id"]}
    assert ov["anchor"] not in {r["name"] for r in ov["regulars"]}


@live
def test_film_page_episodes_match_the_links(ctx, exported):
    """Every airing of a multi-episode film is on its page, oldest first, and
    only the later ones carry a gap."""
    again = ctx.movies[ctx.movies["total_episodes_featured"] > 1].iloc[0]
    slug = film_slugs(ctx.movies)[again["movie_id"]]
    page = _strict_load(exported / "films" / f"{slug}.json")
    links = ctx.links[ctx.links["movie_id"] == again["movie_id"]]
    assert len(page["episodes"]) == len(links)
    numbers = [e["number"] for e in page["episodes"]]
    assert numbers == sorted(numbers)
    assert page["episodes"][0]["gap_before"] is None


@live
def test_shelves_never_hold_the_film_itself(exported):
    for path in (exported / "films").glob("*.json"):
        page = _strict_load(path)
        shelved = {f["id"] for f in page["by_director"] + page["shared_cast"]}
        assert page["id"] not in shelved
        assert len(page["by_director"]) <= SHELF
        assert len(page["shared_cast"]) <= SHELF


@live
def test_film_addresses_are_unique_and_url_safe(exported):
    ids = [r["id"] for r in _strict_load(exported / "films.json")]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", i) for i in ids)


@live
def test_no_file_carries_a_movie_id(ctx, exported):
    """movie_id changes on every rebuild, so none may reach the site."""
    some = list(ctx.movies["movie_id"].head(50))
    for path in exported.rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert not any(m in text for m in some), path.name


@live
def test_export_survives_a_rebuild_that_reissues_every_movie_id(ctx, exported, tmp_path):
    """Step 06 mints a new movie_id for every film on each rebuild. The export
    must come out byte for byte the same anyway, or every publish would
    rewrite every film page and break every shared link."""
    fresh = {m: str(uuid.uuid4()) for m in ctx.movies["movie_id"]}

    def reissue(frame):
        if "movie_id" not in frame.columns:
            return frame
        frame = frame.copy()
        frame["movie_id"] = frame["movie_id"].map(fresh).fillna(frame["movie_id"])
        return frame

    # Shuffled too: a rebuild inserts the films in whatever order it reaches
    # them, and the links query has no ORDER BY, so its rows move as well.
    def shuffle(frame):
        return reissue(frame).sample(frac=1, random_state=7)

    rebuilt = dataclasses.replace(
        ctx,
        movies=shuffle(ctx.movies),
        links=shuffle(ctx.links), merged=shuffle(ctx.merged),
        cruise_hanks=shuffle(ctx.cruise_hanks), rated=reissue(ctx.rated),
        graduated=reissue(ctx.graduated),
    )
    again = tmp_path / "data"
    export_site.export(rebuilt, out=again, theme_dest=None)
    for path in exported.rglob("*.json"):
        twin = again / path.relative_to(exported)
        assert twin.read_bytes() == path.read_bytes(), path.name


@live
def test_export_is_deterministic(ctx, exported, tmp_path):
    """A rerun over the same database writes the same bytes, so a commit after
    a pipeline run shows only what actually changed."""
    again = tmp_path / "data"
    export_site.export(ctx, out=again, theme_dest=None)
    for path in exported.rglob("*.json"):
        twin = again / path.relative_to(exported)
        assert twin.read_bytes() == path.read_bytes(), path.name


# ── Keyword and person pages ──────────────────────────────────────────────────

def _pages(exported, kind):
    return {p.stem: _strict_load(p) for p in (exported / kind).glob("*.json")}


@live
def test_a_keyword_has_a_page_exactly_when_its_chip_links(ctx, exported):
    """The app's rule: a keyword on LINK_FLOOR films or more is a link."""
    pages = _pages(exported, "keywords")
    live_words = {w for w, n in ctx.reach.items() if n >= LINK_FLOOR}
    assert {p["word"] for p in pages.values()} == live_words
    assert "not-a-keyword" not in pages
    index = _strict_load(exported / "keywords.json")
    assert len(index["vocabulary"]) == len(ctx.reach)
    assert {c["word"] for c in index["vocabulary"] if c["id"]} == live_words


@live
def test_keyword_pages_match_the_apps_profile(ctx, exported):
    from rewatchables.app.overlays.keyword import keyword_profile

    pages = _pages(exported, "keywords")
    slugs = film_slugs(ctx.movies)
    for page in list(pages.values())[::50]:
        prof = keyword_profile(ctx.movies, ctx.keywords, page["word"])
        assert {f["id"] for f in page["films"]} == {
            slugs[m] for m in prof["films"]["movie_id"]}
        assert page["thin"] == prof["thin"]
        assert page["peak"] == prof["peak"]
        assert [c["word"] for c in page["partners"]] == prof["partners"]


@live
def test_everyone_but_the_anchor_has_a_person_page(ctx, exported):
    from views import room_long

    pages = _pages(exported, "people")
    room = set(room_long(ctx.merged, "raw_episode_id")["person"])
    assert {p["name"] for p in pages.values()} == room - {ANCHOR}
    index = _strict_load(exported / "people.json")
    assert [r["id"] for r in index] and {r["id"] for r in index} == set(pages)
    episodes = [r["episodes"] for r in index]
    assert episodes == sorted(episodes, reverse=True)


@live
def test_person_pages_match_the_hosts_lookup(ctx, exported):
    from rewatchables.app.analysis import person_shelf
    from rewatchables.app.sections.hosts import the_room

    _, _, board = the_room(ctx.merged)
    for page in _pages(exported, "people").values():
        me = board.loc[page["name"]]
        assert page["episodes"] == me["episodes"]
        assert page["hosted"] == me["hosted"]
        assert len(page["shelf"]) == len(person_shelf(ctx.merged, page["name"]))
        assert ANCHOR not in {c["name"] for c in page["company"]}
        if not page["regular"]:
            assert page["leans"] == []


@live
def test_every_link_lands_on_a_page(exported):
    """A film, keyword or person id anywhere in the data names a page that
    exists, so the site has no dead links of its own making."""
    films = {p.stem for p in (exported / "films").glob("*.json")}
    keywords = {p.stem for p in (exported / "keywords").glob("*.json")}
    people = {p.stem for p in (exported / "people").glob("*.json")}

    for page in _pages(exported, "films").values():
        assert {f["id"] for f in page["by_director"] + page["shared_cast"]} <= films
        assert {k["id"] for k in page["keywords"] if k["id"]} <= keywords
        assert all(k["id"] for k in page["keywords"] if k["live"])
        for ep in page["episodes"]:
            for seat in [ep["host"], *ep["guests"]]:
                if seat and seat["name"] != ANCHOR:
                    assert seat["id"] in people, seat
    for page in _pages(exported, "keywords").values():
        assert {f["id"] for f in page["films"]} <= films
        assert {c["id"] for c in page["partners"] if c["id"]} <= keywords
    for page in _pages(exported, "people").values():
        assert {f["id"] for f in page["shelf"]} <= films
        assert {c["id"] for c in page["company"]} <= people
    overview = _strict_load(exported / "overview.json")
    assert {r["id"] for r in overview["regulars"]} <= people

    def linked(rows):
        return {r["id"] for r in rows if r.get("id")}

    sections = _pages(exported, "sections")
    for rows in (sections["ratings"]["critics_love"], sections["ratings"]["audiences_love"],
                 sections["boxoffice"]["best"], sections["boxoffice"]["worst"],
                 sections["boxoffice"]["table"], sections["timeline"]["oldest"],
                 sections["timeline"]["revisited"], sections["verdicts"]["ledger"],
                 sections["verdicts"]["cruise"]["rail"]):
        assert linked(rows) <= films
    assert linked(sections["verdicts"]["guests"]) <= people

    directors = {p.stem for p in (exported / "directors").glob("*.json")}
    actors = {p.stem for p in (exported / "actors").glob("*.json")}
    hosts = sections["hosts"]
    for rows in (hosts["bench"], hosts["regulars"], hosts["all_comparisons"], hosts["without"]):
        assert linked(rows) <= people
    for group in hosts["without"]:
        assert linked(group["episodes"]) <= films
    assert linked(sections["directors"]["table"]) == directors
    assert linked(sections["actors"]["table"]) <= actors
    for kind, others in (("directors", actors), ("actors", directors)):
        for page in _pages(exported, kind).values():
            assert linked(page["films"]) <= films
            assert linked(page["collaborators"]) <= others


@live
def test_film_rows_carry_the_explorers_ratings(ctx, exported):
    rows = {r["id"]: r for r in _strict_load(exported / "films.json")}
    rated = ctx.rated.assign(slug=ctx.rated["movie_id"].map(film_slugs(ctx.movies)))
    for _, m in rated.iterrows():
        row = rows[m["slug"]]
        if pd.isna(m["tomatoes_avg"]):
            assert row["rt"] is None
        else:
            assert row["rt"] == pytest.approx(m["tomatoes_avg"] * 100, abs=0.05)
        assert row["director"] == m["director_primary"]


# ── Chart sections ────────────────────────────────────────────────────────────

SECTION_FIGURES = {
    "ratings": {"rt", "ebert", "tmdb", "rt_vs_tmdb", "rt_by_genre"},
    "boxoffice": {"by_decade", "cost_vs_gross", "money_vs_rating", "by_genre"},
    "timeline": {"per_year", "decade_genre", "age", "rating_by_decade", "genre_strip",
                 "revisits", "revisit_gaps", "revisit_genres"},
    "genres": {"frequency", "share", "by_decade", "co_occurrence"},
    "verdicts": {"running_margin", "genre_lean"},
    "hosts": {"who_is_on_when", "who_sits_together"},
    "directors": {"leaderboard", "scatter"},
    "actors": {"leaderboard", "scatter"},
}


@live
def test_every_section_ships_every_chart(exported):
    pages = _pages(exported, "sections")
    assert set(pages) == set(SECTION_FIGURES)
    for name, figs in SECTION_FIGURES.items():
        assert set(pages[name]["figures"]) == figs, name
        for fig in pages[name]["figures"].values():
            assert fig is None or fig["data"], name


@live
def test_section_numbers_are_the_apps(ctx, exported):
    from rewatchables.app.sections import boxoffice, ratings, timeline, verdicts

    pages = _pages(exported, "sections")
    s = boxoffice.summary(ctx.movies)
    out = pages["boxoffice"]["summary"]
    assert (out["with_gross"], out["under_break_even"], out["merit_films"]) == (
        s["with_gross"], s["under_break_even"], s["merit_films"])
    assert out["rho"] == round(s["rho"], 2)
    assert len(pages["boxoffice"]["table"]) == s["with_gross"]

    critic, _ = ratings.divergence(ctx.merged)
    assert [r["title"] for r in pages["ratings"]["critics_love"]] == list(critic["title"])

    assert len(pages["timeline"]["revisited"]) == len(timeline.revisited_films(ctx.movies))

    v = pages["verdicts"]
    assert v["standing"] == verdicts.standing(ctx.cruise_hanks)
    assert len(v["ledger"]) == len(ctx.cruise_hanks)
    _, lead_changes = verdicts.running_margin(ctx.cruise_hanks)
    assert v["lead_changes"] == lead_changes
    numbers = [x["episode"] for x in v["ledger"]]
    assert numbers == sorted(numbers, reverse=True)


@live
def test_a_spotlight_page_for_everyone_in_the_apps_pickers(ctx, exported):
    from rewatchables.app.analysis import films_by_actor, films_by_director
    from rewatchables.app.sections.actors import top_actors
    from rewatchables.app.sections.directors import top_directors

    for kind, top, films_of in (("directors", top_directors(ctx.rated)["director"], films_by_director),
                                ("actors", top_actors(ctx.rated)["actor"], films_by_actor)):
        pages = _pages(exported, kind)
        assert {p["name"] for p in pages.values()} == set(top), kind
        for page in pages.values():
            assert len(page["films"]) == len(films_of(ctx.rated, page["name"]))
            assert page["figures"]["genres"]["data"] and page["figures"]["decades"]["data"]


@live
def test_people_section_numbers_are_the_apps(ctx, exported):
    from rewatchables.app.sections import actors, directors, hosts

    pages = _pages(exported, "sections")
    h = pages["hosts"]
    room, others, board = hosts.the_room(ctx.merged)
    with_anchor, hosted = hosts.anchor_share(room)
    assert (h["with_anchor"], h["anchor_hosted"], h["everyone_else"]) == (
        len(with_anchor), hosted, len(board))
    assert sum(len(g["episodes"]) for g in h["without"]) == len(ctx.merged) - len(with_anchor)
    regulars, _, leans = hosts.regular_leans(ctx.merged, others, board)
    assert [r["name"] for r in h["regulars"]] == regulars
    assert h["comparisons"] == len(leans) == len(h["all_comparisons"])

    d = pages["directors"]
    counts = directors.director_counts(ctx.rated)
    assert d["tiles"]["directors"] == counts.size
    assert len(d["table"]) == len(directors.director_stats(ctx.rated))

    a = pages["actors"]
    assert a["tiles"]["actors"] == len(actors.cast_counts(ctx.rated))
    assert len(a["table"]) == len(actors.actor_stats(ctx.rated))
    assert a["credits_total"] == sum(actors.gender_credits(ctx.rated, ctx.gender_map).values())


# ── Upcoming, the doors, the computed captions ────────────────────────────────

@live
def test_every_request_has_a_page_and_the_numbers_are_the_apps(ctx, exported):
    from rewatchables.app.sections.upcoming import queue_summary, unmatched

    u = _strict_load(exported / "upcoming.json")
    pages = _pages(exported, "upcoming")
    assert len(u["requests"]) == len(ctx.upcoming) == len(pages)
    assert {r["id"] for r in u["requests"]} == set(pages)
    assert all(re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", i) for i in pages)
    assert u["summary"] == queue_summary(ctx.upcoming, ctx.graduated)
    assert {r["id"] for r in u["unmatched"]} <= set(pages)
    assert len(u["unmatched"]) == len(unmatched(ctx.upcoming))
    films = {p.stem for p in (exported / "films").glob("*.json")}
    assert {g["id"] for g in u["graduated"] if g["id"]} <= films
    orders = [r["order"] for r in u["requests"]]
    assert orders == sorted(orders)


@live
def test_overview_has_a_door_for_every_section_the_site_has(exported):
    from rewatchables.app.state import SLUGS

    doors = _strict_load(exported / "overview.json")["doors"]
    assert len(doors) == len(SLUGS) - 1
    site = Path(__file__).parent.parent / "site" / "src"
    for door in doors:
        assert (site / f"{door['path']}.md").exists(), door["path"]


@live
def test_scatter_captions_are_computed(ctx, exported):
    from rewatchables.app.sections import actors, directors

    pages = _pages(exported, "sections")
    r, n = directors.volume_reception(ctx.rated)
    assert (pages["directors"]["r"], pages["directors"]["scatter_people"]) == (round(r, 2), n)
    r, n = actors.volume_reception(ctx.rated)
    assert (pages["actors"]["r"], pages["actors"]["scatter_people"]) == (round(r, 2), n)
