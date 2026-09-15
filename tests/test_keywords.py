"""
Tests for the keyword index — the vocabulary browser and the per-keyword view.

The design rests on a claim about the data rather than about the code: the
vocabulary is long-tailed rather than dirty, so nothing is merged, and the dead
ends are handled in presentation instead. Two of the checks here pin that claim
down, because if it ever stopped holding the whole approach would be wrong:

  * normalising the vocabulary rescues almost nothing, which is why there is no
    synonym map to maintain;
  * every keyword has somewhere to go next, which is what stops a one-film
    keyword page being a cul-de-sac.

The rest cover the presentation rules that keep a click from disappointing.
"""

import json
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

import pytest

from conftest import goto

sys.path.insert(0, str(Path(__file__).parent.parent))

from views import (
    BROWSE_FLOOR, LINK_FLOOR, chip_band, decade_bars, keyword_chip, plain,
    rank_by_reach, region_of,
)

DB_PATH = Path(__file__).parent.parent / "rewatchables.db"
APP = Path(__file__).parent.parent / "app.py"

pytestmark = pytest.mark.skipif(
    not DB_PATH.exists(), reason="rewatchables.db has not been built yet"
)


@pytest.fixture(scope="module")
def vocabulary():
    """keyword -> the films carrying it, straight from the database."""
    conn = sqlite3.connect(DB_PATH)
    index = {}
    for movie_id, raw in conn.execute("SELECT movie_id, keywords FROM curated_movies"):
        for word in json.loads(raw or "[]"):
            index.setdefault(word, []).append(movie_id)
    conn.close()
    return index


@pytest.fixture(scope="module")
def reach(vocabulary):
    return {word: len(ids) for word, ids in vocabulary.items()}


# ── Chip weighting ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("count,band", [
    (66, "b1"), (40, "b1"), (39, "b2"), (25, "b2"),
    (24, "b3"), (17, "b3"), (16, "b4"), (12, "b4"),
    (11, "b5"), (5, "b5"), (1, "b5"),
])
def test_chip_band_thresholds(count, band):
    assert chip_band(count) == band


def test_bands_never_invert(reach):
    """A more common keyword can never land in a lighter band."""
    order = ["b1", "b2", "b3", "b4", "b5"]
    ranked = sorted(reach.values(), reverse=True)
    bands = [order.index(chip_band(n)) for n in ranked]
    assert bands == sorted(bands), "band order does not follow reach order"


# ── Ranking, which is what removes the dead ends ──────────────────────────────

def test_rank_puts_the_far_reaching_keywords_first():
    reach = {"murder": 35, "honor": 1, "neo-noir": 29}
    assert rank_by_reach(["honor", "murder", "neo-noir"], reach) == [
        "murder", "neo-noir", "honor"]


def test_rank_is_stable_for_equal_reach():
    reach = {"b": 5, "a": 5, "c": 5}
    assert rank_by_reach(["c", "a", "b"], reach) == ["a", "b", "c"]


def test_ranking_and_capping_is_what_drops_the_dead_ends(vocabulary, reach):
    """The measurement the design was chosen on, re-run against live data.

    Unranked and uncapped, roughly a third of the chips on a film page lead to a
    page holding only that same film. Ranked by reach and capped at eight, it is
    a small fraction of that.
    """
    conn = sqlite3.connect(DB_PATH)
    films = [json.loads(raw or "[]")
             for (raw,) in conn.execute("SELECT keywords FROM curated_movies")]
    conn.close()

    everything = [w for ks in films for w in ks]
    naive = sum(1 for w in everything if reach[w] == 1) / len(everything)

    capped = [w for ks in films for w in rank_by_reach(ks, reach)[:8]]
    ranked = sum(1 for w in capped if reach[w] == 1) / len(capped)

    assert naive > 0.25, f"expected a substantial naive dead-end rate, got {naive:.0%}"
    assert ranked < 0.10, f"ranked+capped rate should be small, got {ranked:.0%}"
    assert ranked < naive / 3


# ── The link floor ────────────────────────────────────────────────────────────

def test_a_chip_below_the_floor_is_inert():
    markup = keyword_chip("honor", 1, inert=True)
    assert "is-inert" in markup
    assert "<a " not in markup and "href" not in markup


def test_a_chip_above_the_floor_is_not_marked_inert():
    assert "is-inert" not in keyword_chip("murder", 35)


def test_the_floor_leaves_most_chips_clickable(vocabulary, reach):
    conn = sqlite3.connect(DB_PATH)
    films = [json.loads(raw or "[]")
             for (raw,) in conn.execute("SELECT keywords FROM curated_movies")]
    conn.close()
    shown = [w for ks in films for w in rank_by_reach(ks, reach)[:8]]
    live = sum(1 for w in shown if reach[w] >= LINK_FLOOR)
    assert live / len(shown) > 0.9, "the link floor is hiding too many chips"


# ── Places: the one hierarchy that is really there ────────────────────────────

@pytest.mark.parametrize("keyword,region", [
    ("los angeles, california", "california"),
    ("manhattan, new york city", "new york city"),
    ("chicago, illinois", "illinois"),
    ("heist", None),
    ("", None),
    (None, None),
])
def test_region_of(keyword, region):
    assert region_of(keyword) == region


def test_place_keywords_actually_exist(vocabulary):
    places = [w for w in vocabulary if region_of(w)]
    assert len(places) > 20, "the place pattern no longer matches the data"
    regions = Counter(region_of(w) for w in places)
    assert regions["california"] > 1, "california should gather several places"


# ── Decade bars ───────────────────────────────────────────────────────────────

def test_decade_bars_are_proportional_to_the_counts():
    markup = decade_bars({1980: 7, 1990: 14, 2000: 0})
    heights = [int(h) for h in re.findall(r"height:(\d+)%", markup)]
    assert heights == [50, 100, 0]


def test_the_tallest_decade_is_marked_as_the_peak():
    markup = decade_bars({1980: 3, 1990: 9})
    assert markup.count("is-peak") == 1
    peak_block = markup.split('class="rw-kw-bar is-peak"')[1]
    assert ">9<" in peak_block


def test_decade_bars_on_nothing_render_nothing():
    assert decade_bars({}) == ""


# ── Plot text that markdown would otherwise mangle ────────────────────────────

def test_dollar_amounts_do_not_become_latex():
    """Two dollar signs in a synopsis are read as maths and eat the text."""
    text = "stealing $1.6 million in bonds from a $20,000 safe"
    assert plain(text) == r"stealing \$1.6 million in bonds from a \$20,000 safe"


def test_the_corpus_really_contains_such_summaries():
    conn = sqlite3.connect(DB_PATH)
    n = conn.execute(
        "SELECT COUNT(*) FROM curated_movies "
        "WHERE plot_summary_wiki LIKE '%$%$%'"
    ).fetchone()[0]
    conn.close()
    assert n > 0, "no summaries with paired dollar signs; plain() may be moot"


# ── The claim the whole design rests on ───────────────────────────────────────

def _normalise(keyword):
    """The aggressive normalisation used to test whether merging would help."""
    def singular(word):
        if word.endswith("ies") and len(word) > 4:
            return word[:-3] + "y"
        if word.endswith(("ses", "xes", "ches", "shes")):
            return word[:-2]
        if word.endswith("s") and not word.endswith("ss"):
            return word[:-1]
        return word

    text = re.sub(r"[^a-z0-9 ]", " ", keyword.lower())
    return " ".join(singular(w) for w in text.split())


def test_consolidating_the_vocabulary_would_barely_help(vocabulary, reach):
    """Why there is no synonym map to maintain.

    If a future enrichment ever did introduce large numbers of spelling
    variants, this would fail — and revisiting the decision would be right.
    """
    groups = {}
    for word in vocabulary:
        groups.setdefault(_normalise(word), []).append(word)

    merged = {g: v for g, v in groups.items() if len(v) > 1}
    rescued = sum(
        1 for members in merged.values()
        for word in members
        if reach[word] == 1 and sum(reach[m] for m in members) >= 2
    )
    singletons = sum(1 for n in reach.values() if n == 1)

    assert singletons > 1000, "the long tail has gone; revisit the design"
    assert rescued / singletons < 0.05, (
        f"normalising now rescues {rescued} of {singletons} singletons — "
        "a controlled vocabulary may be worth building after all"
    )


def test_no_keyword_page_is_a_cul_de_sac(vocabulary):
    """Every keyword has at least one other keyword to travel to.

    This is what lets a one-film keyword page still be a junction, and it holds
    because the median film carries seventeen keywords.
    """
    by_film = {}
    conn = sqlite3.connect(DB_PATH)
    for movie_id, raw in conn.execute("SELECT movie_id, keywords FROM curated_movies"):
        by_film[movie_id] = set(json.loads(raw or "[]"))
    conn.close()

    stranded = []
    for word, ids in vocabulary.items():
        partners = set().union(*(by_film[i] for i in ids)) - {word}
        if not partners:
            stranded.append(word)
    assert stranded == [], f"keywords with nowhere to go: {stranded[:5]}"


def test_the_browse_floor_leaves_a_usable_index(reach):
    browsable = [w for w, n in reach.items() if n >= BROWSE_FLOOR]
    assert 150 < len(browsable) < 600, (
        f"{len(browsable)} browsable keywords — too few to explore or too many "
        "to scan; the floor needs revisiting"
    )


# ── The round trip through the app ────────────────────────────────────────────

@pytest.fixture
def app():
    apptest = pytest.importorskip("streamlit.testing.v1")
    at = apptest.AppTest.from_file(str(APP), default_timeout=240)
    at.run()
    assert not at.exception, at.exception
    return at


def _movie_id(title):
    """Resolve a film's movie_id at run time rather than hardcoding it.

    curated_movies.movie_id is a fresh uuid4 minted by 06_build_curated, which
    clears and rebuilds the table on every run, so a literal id only survives
    until the next rebuild. tmdb_id is the stable identifier; look the row up by
    it. (The app's ?movie= links have the same fragility, which is a real issue
    for a shared URL but not one this test can fix.)
    """
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute(
        "SELECT movie_id FROM curated_movies WHERE title = ? ORDER BY year LIMIT 1",
        (title,)).fetchone()
    conn.close()
    assert row, f"{title!r} is not in curated_movies"
    return row[0]


def _chips(at, prefix):
    return [b for b in at.button if b.key.startswith(prefix)]


def test_the_index_lists_every_browsable_keyword(app, reach):
    goto(app, "Keywords")
    chips = _chips(app, "btn_kw_band_")
    expected = sum(1 for n in reach.values() if n >= BROWSE_FLOOR)
    assert len(chips) == expected


def test_every_index_chip_states_its_reach(app):
    goto(app, "Keywords")
    for chip in _chips(app, "btn_kw_band_")[:20]:
        assert re.search(r"\s\d+$", chip.label), f"no reach on {chip.label!r}"


def test_clicking_a_keyword_opens_it(app):
    goto(app, "Keywords")
    chip = next(c for c in _chips(app, "btn_kw_band_") if c.label.startswith("neo-noir"))
    chip.click().run()

    assert not app.exception, app.exception
    assert app.session_state["kw_word"] == "neo-noir"
    assert dict(app.query_params)["keyword"] == ["neo-noir"]


def test_a_keyword_page_shows_every_film_carrying_it(app, vocabulary):
    goto(app, "Keywords")
    next(c for c in _chips(app, "btn_kw_band_")
         if c.label.startswith("neo-noir")).click().run()
    assert len(_chips(app, "btn_film_kw_")) == len(vocabulary["neo-noir"])


def test_back_leaves_the_keyword_view(app):
    goto(app, "Keywords")
    next(c for c in _chips(app, "btn_kw_band_")
         if c.label.startswith("murder")).click().run()
    app.button(key="btn_kw_back").click().run()

    assert app.session_state["kw_word"] is None
    assert dict(app.query_params) == {}


def test_a_thin_keyword_draws_no_chart_but_still_offers_exits():
    """The worst case in the catalogue: a keyword belonging to one film."""
    apptest = pytest.importorskip("streamlit.testing.v1")
    at = apptest.AppTest.from_file(str(APP), default_timeout=240)
    at.query_params["keyword"] = "honor"
    at.run()

    assert not at.exception, at.exception
    assert at.session_state["kw_word"] == "honor"
    drawn = [m.value for m in at.markdown if 'class="rw-kw-bar' in str(m.value)]
    assert drawn == [], "a one-film keyword should not draw a decade chart"
    assert len(_chips(at, "btn_film_kw_")) == 1
    assert _chips(at, "btn_kw_partners_"), "no way out of a one-film keyword"


def test_a_keyword_with_a_comma_survives_the_url():
    """`los angeles, california` is the second most common keyword."""
    apptest = pytest.importorskip("streamlit.testing.v1")
    at = apptest.AppTest.from_file(str(APP), default_timeout=240)
    at.query_params["keyword"] = "los angeles, california"
    at.run()

    assert not at.exception, at.exception
    assert at.session_state["kw_word"] == "los angeles, california"
    assert any("Part of" in str(m.value) for m in at.markdown), "no region line"


def test_an_unknown_keyword_falls_back_rather_than_erroring():
    apptest = pytest.importorskip("streamlit.testing.v1")
    at = apptest.AppTest.from_file(str(APP), default_timeout=240)
    at.query_params["keyword"] = "not-a-real-keyword"
    at.run()

    assert not at.exception, at.exception
    assert at.session_state["kw_word"] is None


def test_a_film_page_caps_and_ranks_its_keywords():
    """The loop's first hop: a dossier hands you onward to a keyword."""
    apptest = pytest.importorskip("streamlit.testing.v1")
    at = apptest.AppTest.from_file(str(APP), default_timeout=240)
    at.query_params["movie"] = _movie_id("Heat")
    at.run()

    chips = _chips(at, "btn_kw_film_")
    assert len(chips) == 8, "the film chip row should be capped at eight"
    counts = [int(c.label.rsplit(" ", 1)[1]) for c in chips]
    assert counts == sorted(counts, reverse=True), "chips are not ranked by reach"
    assert min(counts) >= LINK_FLOOR


def test_a_keyword_click_from_a_film_page_closes_the_film():
    apptest = pytest.importorskip("streamlit.testing.v1")
    at = apptest.AppTest.from_file(str(APP), default_timeout=240)
    at.query_params["movie"] = _movie_id("Heat")
    at.run()
    _chips(at, "btn_kw_film_")[0].click().run()

    assert at.session_state["dt_movie"] is None
    assert at.session_state["kw_word"] == "los angeles, california"
    assert "movie" not in dict(at.query_params)
