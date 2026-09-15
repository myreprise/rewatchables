"""
Tests for the Hosts & Guests section.

Three kinds of check. The room helpers in views.py, on small hand-built frames
where the right answer is obvious. The premises the section's design rests on,
read from the live database: that one person is on nearly every episode (the
reason he is left out of every grouping), that the episode number is not a
per-airing key (the reason the room is keyed on raw_episode_id), and that no
two spellings of one person survive normalisation. And the section itself,
driven through Streamlit's test harness.
"""

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from conftest import goto

sys.path.insert(0, str(Path(__file__).parent.parent))

from views import (
    ANCHOR, appearances_by_year, bench, bh_adjust, co_appearances,
    lean_phrase, lean_value, lineups, permutation_diffs, person_name,
    room_long,
)

DB_PATH = Path(__file__).parent.parent / "rewatchables.db"
APP = Path(__file__).parent.parent / "app.py"

needs_db = pytest.mark.skipif(
    not DB_PATH.exists(), reason="rewatchables.db has not been built yet")


# ── Names ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    ("Mallory Rubin*", "Mallory Rubin"),
    ("Mallory Rubin **", "Mallory Rubin"),
    ("  Chris Ryan ", "Chris Ryan"),
    ("Bill's Dad", "Bill's Dad"),
    ("K. Austin Collins", "K. Austin Collins"),
])
def test_person_name_drops_markers_and_keeps_names(value, expected):
    assert person_name(value) == expected


@pytest.mark.parametrize("empty", ["", "nan", "  ", None, float("nan"), "*"])
def test_person_name_treats_blanks_as_absent(empty):
    assert person_name(empty) is None


# ── The room, long ────────────────────────────────────────────────────────────

def _episodes():
    """Four airings. The last two share an episode number, as a revisit does."""
    return pd.DataFrame({
        "rid": ["a", "b", "c", "d"],
        "ep": [1, 2, 3, 3],
        "date": pd.to_datetime(["2019-01-01", "2019-06-01", "2020-01-01", "2024-01-01"]),
        "host": ["Bill Simmons", "Bill Simmons", "Juliet Litman", "Bill Simmons"],
        "guest1": ["Chris Ryan", "Chris Ryan", "Kari Simmons", "Chris Ryan"],
        "guest2": ["Mallory Rubin*", "Sean Fennessey", None, "nan"],
        "guest3": [None, "Chris Ryan", None, ""],
        "guest4": [None, None, None, None],
    })


def test_room_long_is_one_row_per_person_per_airing():
    long = room_long(_episodes(), "rid", keep=("date",))
    # b lists Chris Ryan twice; he is one appearance there.
    assert len(long) == 3 + 3 + 2 + 2
    assert not long.duplicated(["rid", "person"]).any()


def test_room_long_merges_the_asterisk():
    long = room_long(_episodes(), "rid")
    assert "Mallory Rubin" in set(long["person"])
    assert "Mallory Rubin*" not in set(long["person"])


def test_leaving_out_the_anchor_is_an_exact_match():
    """'Simmons' as a substring would take Kari Simmons out with him."""
    long = room_long(_episodes(), "rid")
    others = long[long["person"] != ANCHOR]
    assert "Kari Simmons" in set(others["person"])
    assert ANCHOR not in set(others["person"])


def test_a_revisit_with_a_reused_number_is_its_own_room():
    long = room_long(_episodes(), "rid")
    assert long[long["person"] == "Chris Ryan"]["rid"].nunique() == 3


def test_bench_counts_episodes_and_host_chairs():
    long = room_long(_episodes(), "rid", keep=("date",))
    b = bench(long, "rid", "date")
    assert b.loc["Chris Ryan", "episodes"] == 3
    assert b.loc["Chris Ryan", "hosted"] == 0
    assert b.loc["Juliet Litman", "hosted"] == 1
    assert b.index[0] == "Bill Simmons"          # ranked by episodes


def test_co_appearances_and_lineups():
    long = room_long(_episodes(), "rid")
    others = long[long["person"] != ANCHOR]
    pairs = co_appearances(others, "rid")
    assert pairs[("Chris Ryan", "Mallory Rubin")] == 1
    assert pairs[("Chris Ryan", "Sean Fennessey")] == 1
    assert ("Mallory Rubin", "Chris Ryan") not in pairs   # keys are sorted

    ups = lineups(others, "rid")
    assert ups["Chris Ryan"] == 1
    assert ups["Juliet Litman + Kari Simmons"] == 1


def test_appearances_by_year_carries_the_denominator():
    eps = _episodes()
    long = room_long(eps, "rid", keep=("date",))
    on, aired = appearances_by_year(long, eps, "rid", "date")
    assert aired.to_dict() == {2019: 2, 2020: 1, 2024: 1}
    assert on.loc["Chris Ryan"].to_dict() == {2019: 2, 2020: 0, 2024: 1}
    assert (on.loc["Chris Ryan"] / aired).loc[2019] == 1.0


# ── Leans ─────────────────────────────────────────────────────────────────────

def test_a_real_difference_is_detected_and_a_null_one_is_not():
    rng = np.random.default_rng(1)
    n = 300
    mask = np.zeros(n, dtype=bool)
    mask[:40] = True
    shifted = rng.normal(0, 1, n) + np.where(mask, 1.5, 0)
    flat = rng.normal(0, 1, n)
    out = permutation_diffs({"shifted": shifted, "flat": flat},
                            {"x": mask}, n_perm=2000).set_index("metric")
    assert out.loc["shifted", "p"] < 0.001
    assert out.loc["flat", "p"] > 0.05
    assert out.loc["shifted", "n"] == 40


def test_permutation_results_are_fixed_by_the_seed():
    rng = np.random.default_rng(2)
    vals = {"v": rng.normal(0, 1, 120)}
    masks = {"x": rng.random(120) < 0.2}
    a = permutation_diffs(vals, masks, n_perm=500, seed=0)
    b = permutation_diffs(vals, masks, n_perm=500, seed=0)
    pd.testing.assert_frame_equal(a, b)


def test_unknown_values_are_left_out_of_both_means():
    vals = np.array([1.0, 1.0, np.nan, 5.0, 5.0, 5.0])
    mask = np.array([True, True, True, False, False, False])
    row = permutation_diffs({"v": vals}, {"x": mask}, n_perm=200).iloc[0]
    assert row["mean_in"] == 1.0
    assert row["mean_out"] == 5.0
    assert row["diff"] == -4.0


def test_bh_matches_a_worked_example():
    q = bh_adjust([0.01, 0.04, 0.03, 0.005])
    assert np.allclose(q, [0.02, 0.04, 0.04, 0.02])


def test_bh_is_monotone_in_p():
    # 0.04 * 2/1 = 0.08 would exceed the next q-value; it is capped at 0.041.
    assert np.allclose(bh_adjust([0.04, 0.041]), [0.041, 0.041])


@pytest.mark.parametrize("args,expected", [
    (("Romance", 0.79, 0.16, 0.63), "Romance 79% vs 16%"),
    (("rt", 0.70, 0.90, -0.20), "RT -20 pts"),
    (("age", 32.0, 24.0, 8.0), "films 8 yr older"),
    (("age", 20.0, 25.0, -5.0), "films 5 yr newer"),
])
def test_lean_phrase(args, expected):
    assert lean_phrase(*args) == expected


@pytest.mark.parametrize("metric,value,signed,expected", [
    ("Romance", 0.79, False, "79%"),
    ("Romance", 0.63, True, "+63 pts"),     # a gap between percentages is points
    ("rt", -0.2, True, "-20 pts"),
    ("age", 24.26, False, "24.3 yr"),
    ("age", -5.1, True, "-5.1 yr"),
])
def test_lean_value(metric, value, signed, expected):
    assert lean_value(metric, value, signed=signed) == expected


def test_no_regulars_means_no_comparisons_rather_than_an_error():
    out = permutation_diffs({"v": np.zeros(5)}, {})
    assert out.empty and "p" in out.columns


# ── The premises, from the live database ──────────────────────────────────────

@pytest.fixture(scope="module")
def film_rooms():
    connection = sqlite3.connect(DB_PATH)
    frame = pd.read_sql(
        "SELECT raw_episode_id, ep, host, guest1, guest2, guest3, guest4 "
        "FROM raw_episodes_current WHERE CAST(is_film AS TEXT) = '1'",
        connection)
    connection.close()
    return frame


@needs_db
def test_the_anchor_is_on_nearly_every_episode(film_rooms):
    """Why he is left out of every grouping. If this ever stops holding, the
    section's premise has gone and he belongs back in the panels."""
    long = room_long(film_rooms, "raw_episode_id")
    share = long[long["person"] == ANCHOR]["raw_episode_id"].nunique() / len(film_rooms)
    assert share > 0.8


@needs_db
def test_the_episode_number_is_not_a_per_airing_key(film_rooms):
    """Why the room is keyed on raw_episode_id."""
    assert film_rooms["raw_episode_id"].is_unique
    assert film_rooms["ep"].duplicated().any()


@needs_db
def test_no_person_survives_normalisation_under_two_spellings(film_rooms):
    """A second marker or a case slip would split someone's count in two."""
    names = set(room_long(film_rooms, "raw_episode_id")["person"])
    folded = {}
    for name in names:
        folded.setdefault("".join(ch for ch in name.lower() if ch.isalnum()), []).append(name)
    assert [v for v in folded.values() if len(v) > 1] == []


# ── The section ───────────────────────────────────────────────────────────────

@pytest.fixture
def hosts():
    apptest = pytest.importorskip("streamlit.testing.v1")
    at = apptest.AppTest.from_file(str(APP), default_timeout=180)
    at.run()
    goto(at, "Hosts & Guests")
    assert not at.exception, at.exception
    return at


def _person_films(at):
    return [b for b in at.button if b.key.startswith("btn_film_person")]


@needs_db
def test_the_anchor_is_not_offered_in_the_lookup(hosts):
    options = hosts.selectbox(key="flt_person").options
    assert options and not any(ANCHOR in o for o in options)


@needs_db
def test_the_lookup_shows_every_episode_a_person_was_on(hosts, film_rooms):
    """Mallory Rubin, because one of her episodes is the one the sheet marks."""
    name = "Mallory Rubin"
    expected = room_long(film_rooms, "raw_episode_id").query("person == @name")
    hosts.selectbox(key="flt_person").set_value(name).run()
    assert not hosts.exception, hosts.exception
    assert len(_person_films(hosts)) == expected["raw_episode_id"].nunique()
    assert dict(hosts.query_params).get("person") == [name]


@needs_db
def test_a_person_url_opens_the_lookup_on_a_cold_load():
    apptest = pytest.importorskip("streamlit.testing.v1")
    at = apptest.AppTest.from_file(str(APP), default_timeout=180)
    at.query_params["person"] = "Van Lathan"
    at.run()
    assert not at.exception, at.exception
    assert at.session_state["nav_section"] == "hosts"
    assert at.session_state["flt_person"] == "Van Lathan"


@needs_db
def test_the_dossier_arrows_walk_the_persons_films(hosts):
    """In grid order, a revisited film visited once, the pick left alone."""
    hosts.selectbox(key="flt_person").set_value("Juliet Litman").run()
    # btn_film_person<i>_<movie_id>: the grid order, read off the grid itself.
    shelf = list(dict.fromkeys(b.key.split("_", 3)[3] for b in _person_films(hosts)))
    assert len(shelf) < len(_person_films(hosts)), "expected a revisit on her shelf"

    _person_films(hosts)[0].click().run()
    assert hosts.session_state["dt_movie"] == shelf[0]
    assert hosts.button(key="btn_dt_prev").disabled

    hosts.button(key="btn_dt_next").click().run()
    assert hosts.session_state["dt_movie"] == shelf[1]
    assert any(f"Film 2 of {len(shelf)}" in str(m.value) for m in hosts.markdown)
    assert hosts.session_state["_keep_flt_person"] == "Juliet Litman"


@needs_db
def test_the_dossier_hands_off_to_the_lookup(hosts):
    _person_films(hosts)[0].click().run()
    assert hosts.session_state["dt_movie"] is not None
    hand_off = [b for b in hosts.button if b.key.startswith("btn_dt_person_")]
    assert hand_off, "the dossier offers no way back to the people in the room"
    name = hand_off[0].label
    hand_off[0].click().run()
    assert hosts.session_state["dt_movie"] is None
    assert hosts.session_state["nav_section"] == "hosts"
    assert hosts.session_state["flt_person"] == name
