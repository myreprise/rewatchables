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
from views import film_slugs, slugify

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
    assert export_site.plain_value(value) == expected


def test_plain_value_survives_a_round_trip():
    out = json.dumps(export_site.plain_value(np.float64("nan")))
    assert out == "null"


def test_blurb_cuts_at_a_word_boundary():
    text = "word " * 100
    cut = export_site.blurb(text, limit=23)
    assert cut == "word word word word…"
    assert export_site.blurb("short", limit=23) == "short"
    assert export_site.blurb(None) == ""


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


def test_write_rows_puts_one_row_per_line(tmp_path):
    path = tmp_path / "rows.json"
    export_site.write_rows(path, [{"id": "a"}, {"id": "b"}])
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
        assert len(page["by_director"]) <= export_site.SHELF
        assert len(page["shared_cast"]) <= export_site.SHELF


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

    # Shuffled too: a rebuild inserts the films in whatever order it reaches them.
    rebuilt = dataclasses.replace(
        ctx,
        movies=reissue(ctx.movies).sample(frac=1, random_state=7),
        links=reissue(ctx.links), merged=reissue(ctx.merged),
        cruise_hanks=reissue(ctx.cruise_hanks), rated=reissue(ctx.rated),
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
