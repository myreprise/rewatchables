"""
Tests for the film dossier — the per-film detail view in app.py.

Two kinds of check live here. The first covers dossier.py, the pure presentation
helpers, where the failure modes are quiet: a 'nan' guest in the room, a missing
box office rendered as $0, an episode card swallowed by markdown.

The second covers the assumptions the dossier's *layout* rests on, read straight
from the live database. These are the ones worth pinning: the design puts Rotten
Tomatoes and Ebert in the film header rather than on each episode card because
those scores never vary between a film's episodes, and puts the Cruise vs. Hanks
verdict on the episode cards because it does. If the data ever stopped behaving
that way the layout would start asserting something untrue, and nothing else in
the app would notice.
"""

import re
import sqlite3
from pathlib import Path

import pytest

from conftest import NAV_GROUPS, film_count, goto
from views import clean, html, human_gap, stars, stat_tile

DB_PATH = Path(__file__).parent.parent / "rewatchables.db"

pytestmark = pytest.mark.skipif(
    not DB_PATH.exists(), reason="rewatchables.db has not been built yet"
)


@pytest.fixture(scope="module")
def conn():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    yield connection
    connection.close()


# ── Empty-cell handling ───────────────────────────────────────────────────────

@pytest.mark.parametrize("empty", ["nan", "NaN", " nan ", "", "  ", "None", None, float("nan")])
def test_clean_treats_sheet_blanks_as_absent(empty):
    assert clean(empty) is None


@pytest.mark.parametrize("value,expected", [
    ("Bill Simmons", "Bill Simmons"),
    ("  Chris Ryan  ", "Chris Ryan"),
    ("Nan Goldin", "Nan Goldin"),      # a real name that merely starts with nan
    ("The Re-Chips", "The Re-Chips"),
    (0, "0"),
])
def test_clean_keeps_real_values(value, expected):
    assert clean(value) == expected


def test_sheet_blanks_are_actually_present_in_the_database(conn):
    """The cleaner exists for a reason — confirm blanks still reach the database.

    The sentinel changed shape when the source moved from master.xlsx to
    episodes.csv. The xlsx path let pandas type each column by guessing and then
    stringified the guess, so an empty cell arrived as the literal string 'nan';
    the CSV is read with keep_default_na=False, so it arrives as ''. Either way
    a blank guest slot reaches the dossier and has to render as absent rather
    than as a guest called "nan" — clean() handles both, and still should, since
    a re-import through a path that infers dtypes would bring 'nan' back.
    """
    blanks = conn.execute(
        "SELECT COUNT(*) FROM raw_episodes_current "
        "WHERE guest2 IN ('', 'nan') OR guest2 IS NULL"
    ).fetchone()[0]
    assert blanks > 0, "no blank guest slots at all; clean() may no longer be needed"


# ── Star ratings ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (4.0, "&#9733;" * 4),
    (3.5, "&#9733;" * 3 + "&frac12;"),
    (2.0, "&#9733;" * 2),
    (0.5, "&frac12;"),
])
def test_stars_render_halves(value, expected):
    assert stars(value) == expected


def test_stars_absent_when_unrated():
    assert stars(None) is None
    assert stars(float("nan")) is None


# ── Gap between episodes ──────────────────────────────────────────────────────

@pytest.mark.parametrize("days,expected", [
    (1494, "4 yr 1 mo later"),      # Heat, episode 1 -> 116
    (648, "1 yr 9 mo later"),       # Heat, episode 116 -> 227
    (400, "1 yr 1 mo later"),
    (365, "1 yr later"),
    (90, "3 mo later"),
    (12, "12 days later"),
])
def test_human_gap(days, expected):
    assert human_gap(days) == expected


def test_gap_matches_the_real_episode_dates(conn):
    """The two gap markers on Heat's spine, computed from the database."""
    rows = conn.execute("""
        SELECT cem.episode_date
        FROM curated_episode_movies cem
        JOIN curated_movies cm ON cm.movie_id = cem.movie_id
        WHERE cm.title = 'Heat' AND cm.year = 1995
        ORDER BY cem.episode_number
    """).fetchall()
    assert len(rows) == 3

    from datetime import date

    dates = [date.fromisoformat(r["episode_date"]) for r in rows]
    gaps = [human_gap((b - a).days) for a, b in zip(dates, dates[1:])]
    assert gaps == ["4 yr 1 mo later", "1 yr 9 mo later"]


# ── Absent stats ──────────────────────────────────────────────────────────────

def test_stat_tile_shows_na_rather_than_zero():
    assert "n/a" in stat_tile("Box office", None)
    assert ">0<" not in stat_tile("Box office", None)


def test_stat_tile_renders_value_and_unit():
    tile = stat_tile("TMDB", "7.9", "/10")
    assert "7.9" in tile and "/10" in tile and "n/a" not in tile


def test_films_without_box_office_exist(conn):
    """The n/a path is reached in practice, not just in theory."""
    total = conn.execute("SELECT COUNT(*) FROM curated_movies").fetchone()[0]
    with_box = conn.execute(
        "SELECT COUNT(*) FROM v_movie_cmu WHERE box_office_revenue IS NOT NULL"
    ).fetchone()[0]
    assert 0 < with_box < total, "expected partial box-office coverage"


def test_every_wiki_synopsis_records_its_source(conn):
    """Since step 12 began taking live Wikipedia (2026-09) all 456 films have a
    synopsis, so the dossier's hide-when-missing path is now reached only by a
    film whose article has no plot section. What the data must still promise
    is that a synopsis on screen is never blank and always says which vintage
    of Wikipedia it came from.
    """
    bad = conn.execute(
        "SELECT COUNT(*) FROM curated_movies "
        "WHERE plot_summary_wiki = '' "
        "   OR (plot_summary_wiki IS NOT NULL "
        "       AND (plot_summary_wiki_source IS NULL "
        "            OR plot_summary_wiki_source NOT IN ('cmu_2012', 'wikipedia_live')))"
    ).fetchone()[0]
    assert bad == 0


# ── Markup flattening ─────────────────────────────────────────────────────────

def test_html_removes_the_indentation_markdown_would_read_as_code():
    markup = """
        <div class="a">
          <span>one</span>
        </div>"""
    assert html(markup) == '<div class="a"><span>one</span></div>'
    assert not any(line.startswith("    ") for line in html(markup).splitlines())


def test_html_keeps_every_block_it_is_given():
    blocks = "".join(html(f"\n    <div>{i}</div>") for i in range(3))
    assert blocks == "<div>0</div><div>1</div><div>2</div>"


# ── The invariants the layout depends on ──────────────────────────────────────

def _multi_episode_films(conn):
    return conn.execute("""
        SELECT cem.movie_id,
               COUNT(*)                            AS episodes,
               COUNT(DISTINCT re.tomatoes_score)   AS distinct_rt,
               COUNT(DISTINCT re.ebert_stars)      AS distinct_ebert,
               COUNT(DISTINCT re.cruise_hanks)     AS distinct_verdict
        FROM curated_episode_movies cem
        JOIN staging_episodes se ON se.staging_episode_id = cem.staging_episode_id
        JOIN raw_episodes re ON re.raw_episode_id = se.raw_episode_id
        GROUP BY cem.movie_id
        HAVING episodes > 1
    """).fetchall()


def test_ratings_belong_to_the_film_not_the_episode(conn):
    """RT and Ebert sit in the hero because they never move between episodes.

    If this ever fails, the scores have become episode-grained and showing one
    value per film in the header would be hiding the variation.
    """
    films = _multi_episode_films(conn)
    assert films, "no multi-episode films to check"
    varying_rt = [f["movie_id"] for f in films if f["distinct_rt"] > 1]
    varying_ebert = [f["movie_id"] for f in films if f["distinct_ebert"] > 1]
    assert varying_rt == [], f"RT now varies across episodes for {varying_rt}"
    assert varying_ebert == [], f"Ebert now varies across episodes for {varying_ebert}"


def test_the_cruise_hanks_verdict_is_episode_grained(conn):
    """The verdict rides on the episode card because it genuinely differs."""
    films = _multi_episode_films(conn)
    varying = [f["movie_id"] for f in films if f["distinct_verdict"] > 1]
    assert varying, "verdict no longer varies across episodes; it could move to the hero"


# ── Deep links ────────────────────────────────────────────────────────────────

def test_every_movie_id_resolves_to_exactly_one_film(conn):
    """?movie=<id> must never be ambiguous."""
    total, distinct = conn.execute(
        "SELECT COUNT(*), COUNT(DISTINCT movie_id) FROM curated_movies"
    ).fetchone()
    assert total == distinct


def test_every_episode_link_points_at_a_real_film(conn):
    """A dossier reached from any grid always has episodes to show."""
    orphans = conn.execute("""
        SELECT COUNT(*) FROM curated_episode_movies cem
        LEFT JOIN curated_movies cm ON cm.movie_id = cem.movie_id
        WHERE cm.movie_id IS NULL
    """).fetchone()[0]
    assert orphans == 0


def test_every_film_the_grids_show_has_at_least_one_episode(conn):
    """The grids are built from curated_movies; a film with no episode link
    would open a dossier with an empty spine."""
    filmless = conn.execute("""
        SELECT COUNT(*) FROM curated_movies cm
        WHERE NOT EXISTS (
            SELECT 1 FROM curated_episode_movies cem WHERE cem.movie_id = cm.movie_id
        )
    """).fetchone()[0]
    assert filmless == 0


# ── The round trip through the app ────────────────────────────────────────────
# Driven through Streamlit's own test harness. The behaviour worth pinning is
# the one that decided the design: opening a dossier must not disturb the filter
# set behind it. A button was chosen over a plain ?movie= link precisely because
# a link reloads the session and clears those filters.

APP = Path(__file__).parent.parent / "app.py"


@pytest.fixture
def app():
    apptest = pytest.importorskip("streamlit.testing.v1")
    at = apptest.AppTest.from_file(str(APP), default_timeout=180)
    at.run()
    assert not at.exception, at.exception
    return at


@pytest.fixture
def filtered(app):
    """Movie Explorer, narrowed to the three Godfather films."""
    goto(app, "Movie Explorer")
    app.text_input(key="flt_search").set_value("godfather").run()
    assert film_count(app) == "3 films match your filters"
    return app


def _film_buttons(at):
    return [b for b in at.button if b.key.startswith("btn_film_")]


def test_every_poster_in_the_grid_opens_a_dossier(filtered):
    buttons = _film_buttons(filtered)
    assert len(buttons) == 3
    assert [b.label.split("\n")[0] for b in buttons] == [
        "The Godfather Part III", "The Godfather Part II", "The Godfather",
    ]


def test_opening_a_dossier_leaves_the_filters_alone(filtered):
    """The reason the click is a button and not a ?movie= link."""
    _film_buttons(filtered)[0].click().run()

    assert filtered.session_state["dt_movie"] is not None
    assert filtered.session_state["flt_search"] == "godfather"


def test_the_dossier_is_addressable(filtered):
    _film_buttons(filtered)[0].click().run()

    params = dict(filtered.query_params)
    # The film's address, not its movie_id: step 06 reissues every movie_id on
    # a rebuild, and a link built on it broke the next time the pipeline ran.
    slugs = filtered.session_state["_film_slugs"]
    assert params["movie"] == slugs[filtered.session_state["dt_movie"]]
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*-\d{4}", params["movie"])
    # The slug, not the label — the label is free to change now.
    assert params["from"] == "explorer"


def test_the_step_arrows_walk_the_filtered_set(filtered):
    buttons = _film_buttons(filtered)
    first = buttons[0].label.split("\n")[0]
    buttons[0].click().run()
    opened = filtered.session_state["dt_movie"]

    filtered.button(key="btn_dt_next").click().run()
    assert filtered.session_state["dt_movie"] != opened
    # Still inside the three-film result set, filter untouched.
    assert filtered.session_state["flt_search"] == "godfather"
    assert first == "The Godfather Part III"


def test_back_restores_the_filtered_grid(filtered):
    _film_buttons(filtered)[0].click().run()
    filtered.button(key="btn_dt_back").click().run()

    assert filtered.session_state["dt_movie"] is None
    assert film_count(filtered) == "3 films match your filters"
    assert dict(filtered.query_params) == {}


def test_changing_section_closes_the_dossier(filtered):
    _film_buttons(filtered)[0].click().run()
    assert filtered.session_state["dt_movie"] is not None

    goto(filtered, "Genres")
    assert filtered.session_state["dt_movie"] is None


def test_a_movie_url_opens_that_dossier_on_a_cold_load(conn):
    """?movie=heat-1995 has to survive a fresh session, not just an in-app click."""
    apptest = pytest.importorskip("streamlit.testing.v1")
    movie_id, title = conn.execute(
        "SELECT movie_id, title FROM curated_movies WHERE title = 'Heat' AND year = 1995"
    ).fetchone()

    at = apptest.AppTest.from_file(str(APP), default_timeout=180)
    at.query_params["movie"] = "heat-1995"
    at.query_params["from"] = "keywords"
    at.run()

    assert not at.exception, at.exception
    assert at.session_state["dt_movie"] == movie_id
    # The nav rail follows the link, so Back lands somewhere sensible.
    assert at.session_state["nav_section"] == "keywords"
    assert any(title in str(m.value) for m in at.markdown)


def test_a_link_by_current_movie_id_still_opens(conn):
    """Links minted before addresses carry a movie_id. One that is still
    current opens its film; it was always going to stop at the next rebuild."""
    apptest = pytest.importorskip("streamlit.testing.v1")
    movie_id = conn.execute(
        "SELECT movie_id FROM curated_movies WHERE title = 'Heat' AND year = 1995"
    ).fetchone()[0]

    at = apptest.AppTest.from_file(str(APP), default_timeout=180)
    at.query_params["movie"] = movie_id
    at.run()

    assert not at.exception, at.exception
    assert at.session_state["dt_movie"] == movie_id


def test_film_from_address():
    from rewatchables.app.state import film_from_address

    slugs = {"id-heat": "heat-1995", "id-speed": "speed-1994"}
    assert film_from_address("heat-1995", slugs) == "id-heat"
    assert film_from_address("id-speed", slugs) == "id-speed"
    assert film_from_address("heat-1996", slugs) is None
    assert film_from_address(None, slugs) is None


def test_an_unknown_movie_id_falls_back_to_the_section(conn):
    apptest = pytest.importorskip("streamlit.testing.v1")
    at = apptest.AppTest.from_file(str(APP), default_timeout=180)
    at.query_params["movie"] = "not-a-real-movie-id"
    at.run()

    assert not at.exception, at.exception
    assert at.session_state["dt_movie"] is None


# ── The ?from= slug contract ───────────────────────────────────────────────────
# Section labels used to be the URL key, so renaming a section broke every link
# anyone had shared. The slug is the key now and the label is free to move.


@pytest.mark.parametrize("legacy,expected", [
    ("Movie Explorer", "explorer"),
    ("Cruise vs. Hanks", "verdicts"),
    ("Timeline", "timeline"),
    # Revisits is no longer a section; its links land on what absorbed it.
    ("Revisits", "timeline"),
    # Directors & Cast split into Directors and Actors. Both its old label and
    # its old slug land on Directors.
    ("Directors & Cast", "directors"),
    ("people", "directors"),
])
def test_links_minted_under_the_old_label_scheme_still_land(conn, legacy, expected):
    apptest = pytest.importorskip("streamlit.testing.v1")
    at = apptest.AppTest.from_file(str(APP), default_timeout=180)
    at.query_params["movie"] = "heat-1995"
    at.query_params["from"] = legacy
    at.run()

    assert not at.exception, at.exception
    assert at.session_state["nav_section"] == expected


def test_an_unknown_from_falls_back_to_the_first_section(conn):
    apptest = pytest.importorskip("streamlit.testing.v1")
    at = apptest.AppTest.from_file(str(APP), default_timeout=180)
    at.query_params["movie"] = "heat-1995"
    at.query_params["from"] = "Section That Never Existed"
    at.run()

    assert not at.exception, at.exception
    assert at.session_state["nav_section"] == "overview"


def test_every_rail_label_is_reachable(app):
    """Each of the nine sections renders without error from a cold rail click."""
    for group in NAV_GROUPS:
        for label in group:
            goto(app, label)
            assert not app.exception, f"{label}: {app.exception}"


def test_revisits_now_lives_under_the_timeline(app):
    goto(app, "Timeline & Revisits")
    headings = " ".join(str(m.value) for m in app.markdown)
    assert "Films they came back to" in headings
    assert "Episodes per year" in headings
