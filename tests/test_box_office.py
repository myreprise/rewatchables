"""
Tests for the Box Office section and the money helpers behind it.

The section exists because the obvious version of it is wrong twice over.

Drawn from CMU's box_office_revenue -- the only source the app had before -- a
decade trend measures the Freebase snapshot date rather than the films: CMU
froze in Nov 2012, so it knows ~92% of the catalogue before 2010, 31% of the
2010s and none of the 2020s. Drawn in nominal dollars it measures CPI: the
1980s median gross is $63M against the 2000s' $172M, and most of that gap is
inflation. TMDB covers 447 of 454 evenly, and everything user-facing is
converted to CPI_BASE_YEAR dollars.

The pure helpers are tested directly; the section is tested through AppTest
for the properties that would quietly produce a plausible-looking wrong chart.
"""

import sqlite3
from pathlib import Path

import pytest

from conftest import goto
from views import (
    BREAK_EVEN_MULTIPLE, CPI_BASE_YEAR, CPI_PROVISIONAL_FROM, CPI_U,
    money, multiple, real_usd,
)

APP = Path(__file__).parent.parent / "app.py"
DB = Path(__file__).parent.parent / "rewatchables.db"


@pytest.fixture(scope="module")
def conn():
    c = sqlite3.connect(DB)
    yield c
    c.close()


# ── real_usd ──────────────────────────────────────────────────────────────────

def test_base_year_is_unchanged_by_adjustment():
    assert real_usd(100, CPI_BASE_YEAR) == pytest.approx(100)


def test_older_dollars_are_worth_more():
    """A 1975 dollar buys ~5.8 of today's, so adjustment must scale up."""
    assert real_usd(100, 1975) > real_usd(100, 1995) > real_usd(100, 2015)


def test_adjustment_matches_the_cpi_ratio():
    expected = 1_000_000 * CPI_U[CPI_BASE_YEAR] / CPI_U[1980]
    assert real_usd(1_000_000, 1980) == pytest.approx(expected)


def test_missing_amount_is_none():
    assert real_usd(None, 1990) is None


def test_zero_is_none_not_zero():
    """TMDB's 0-for-unknown must not survive into an adjusted series."""
    assert real_usd(0, 1990) is None


def test_year_outside_the_table_is_none():
    """Better to drop the film than to mix a nominal figure into a real one."""
    assert real_usd(1_000_000, 1950) is None
    assert real_usd(1_000_000, None) is None


def test_every_catalogue_year_is_covered(conn):
    """A year missing from CPI_U silently drops that film from every chart."""
    years = {r[0] for r in conn.execute(
        "SELECT DISTINCT year FROM curated_movies WHERE year IS NOT NULL")}
    missing = sorted(y for y in years if y not in CPI_U)
    assert not missing, f"CPI_U has no entry for {missing}"


# ── money ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (2_185_372_000, "$2.2B"),
    (103_000_000, "$103.0M"),
    (718_490, "$718.5K"),
    (250, "$250"),
])
def test_money_picks_a_scale_per_value(value, expected):
    assert money(value) == expected


def test_money_passes_missing_through():
    assert money(None) is None


# ── multiple ──────────────────────────────────────────────────────────────────

def test_multiple_is_revenue_over_budget():
    assert multiple(100, 25) == pytest.approx(4.0)


def test_multiple_needs_both_sides():
    assert multiple(100, None) is None
    assert multiple(None, 25) is None


def test_multiple_rejects_a_zero_budget():
    """The div-by-zero that TMDB's 0-for-unknown would otherwise cause."""
    assert multiple(100, 0) is None


def test_break_even_is_above_one():
    """Gross is not profit: the rule of thumb is ~2.5x the production budget."""
    assert BREAK_EVEN_MULTIPLE > 1


# ── The data the section rests on ─────────────────────────────────────────────

def test_tmdb_covers_the_catalogue_far_better_than_cmu(conn):
    """The reason the section charts TMDB and keeps CMU only as a cross-check."""
    tmdb = conn.execute(
        "SELECT COUNT(*) FROM curated_movies WHERE revenue_tmdb IS NOT NULL"
    ).fetchone()[0]
    cmu = conn.execute(
        "SELECT COUNT(*) FROM v_movie_cmu WHERE box_office_revenue IS NOT NULL"
    ).fetchone()[0]
    assert tmdb > cmu


def test_cmu_coverage_collapses_after_its_snapshot(conn):
    """Pins the bias that made CMU unusable for a decade trend.

    If this ever stops holding, CMU has been reloaded from a newer dump and the
    section's choice of source is worth revisiting.
    """
    rows = dict(conn.execute("""
        SELECT m.year / 10 * 10 AS decade,
               COUNT(v.box_office_revenue) * 1.0 / COUNT(*)
        FROM curated_movies m
        LEFT JOIN v_movie_cmu v ON v.movie_id = m.movie_id
        WHERE m.year IS NOT NULL GROUP BY decade"""))
    assert rows[1990] > 0.8, "CMU should know most pre-2010 films"
    assert rows[2010] < 0.5, "CMU's Freebase snapshot froze in 2012"


def test_tmdb_coverage_does_not_collapse(conn):
    """The property that makes a decade comparison legitimate at all."""
    rows = dict(conn.execute("""
        SELECT year / 10 * 10 AS decade,
               COUNT(revenue_tmdb) * 1.0 / COUNT(*)
        FROM curated_movies WHERE year IS NOT NULL GROUP BY decade"""))
    for decade, share in rows.items():
        assert share > 0.75, f"{decade}s only {share:.0%} covered"


def test_no_zero_financials_survived_the_load(conn):
    """0 means 'not published'; it must have become NULL at ingest."""
    bad = conn.execute(
        "SELECT COUNT(*) FROM curated_movies "
        "WHERE budget_tmdb = 0 OR revenue_tmdb = 0").fetchone()[0]
    assert bad == 0


# ── The rendered section ──────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def box_office():
    apptest = pytest.importorskip("streamlit.testing.v1")
    at = apptest.AppTest.from_file(str(APP), default_timeout=300)
    at.run()
    assert not at.exception, at.exception
    goto(at, "Box Office")
    assert not at.exception, at.exception
    return at


def test_the_section_renders(box_office):
    assert box_office.session_state["nav_section"] == "boxoffice"
    assert len(box_office.get("plotly_chart")) >= 4


def test_every_money_figure_is_labelled_as_adjusted(box_office):
    """An unlabelled dollar figure invites a nominal reading of a real series."""
    # Keyed on the value rather than the wording: any tile actually showing
    # dollars has to say which year's dollars they are.
    money_tiles = [m for m in box_office.metric if str(m.value).startswith("$")]
    assert money_tiles, "expected at least one dollar figure on the page"
    for tile in money_tiles:
        assert str(CPI_BASE_YEAR) in tile.label, (
            f"{tile.label!r} shows {tile.value} without saying what dollars")


def test_the_method_is_stated_on_the_page(box_office):
    """Return is not profit, and the page has to say so where it is shown."""
    captions = " ".join(str(c.value) for c in box_office.caption)
    assert "CPI" in captions
    assert "not profit" in captions
    assert str(BREAK_EVEN_MULTIPLE) in captions


def test_missing_figures_are_declared_not_counted_as_zero(box_office):
    captions = " ".join(str(c.value) for c in box_office.caption)
    assert "no published gross" in captions
    assert "rather than counted as zero" in captions


def test_films_still_in_release_are_kept_out_of_the_leaderboards(box_office, conn):
    """TMDB has a 2026 title at a $750K budget against a $506M gross.

    Left in, it takes second place on the returns table at 674x and pushes a
    real result off the bottom.
    """
    provisional = [r[0] for r in conn.execute(
        "SELECT title FROM curated_movies WHERE year >= ?", (CPI_PROVISIONAL_FROM,))]
    assert provisional, "expected at least one film released in a provisional year"

    leaderboards = box_office.dataframe[:2]
    listed = set()
    for df in leaderboards:
        listed |= set(df.value["Film"])
    assert not (listed & set(provisional)), (
        f"{listed & set(provisional)} should be excluded from the leaderboards")

    captions = " ".join(str(c.value) for c in box_office.caption)
    for title in provisional:
        assert title in captions, f"{title} excluded without saying so"


def test_thin_decades_are_flagged(box_office):
    """Two 1960s films must not read as a decade trend."""
    captions = " ".join(str(c.value) for c in box_office.caption)
    assert "too thin to read as a trend" in captions
