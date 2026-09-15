"""
Tests for the people dimension: cast ids, TMDB gender, and the app's
name -> gender resolution.

Two halves. The first covers 09_enrich_metadata's new outputs -- cast_ids on
curated_movies and rows in curated_people -- with every network call mocked.
The second covers app.py's gender_map/explode_cast, which are what the Actors
section reads; those are pure functions over a frame and need no database.
"""

import json
import re
import sqlite3
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from rewatchables.pipeline import s09_enrich_metadata as mod

ROOT = Path(__file__).parent.parent

_parse             = mod._parse
enrich_metadata    = mod.enrich_metadata
people_put         = mod.people_put
ensure_people_table = mod.ensure_people_table
ensure_cache_table = mod.ensure_cache_table
GENDER_CODES       = mod.GENDER_CODES


DETAIL = {
    "id": 949,
    "title": "Heat",
    "overview": "Obsessive master thief Neil McCauley leads a top-notch crew.",
    "runtime": 170,
    "poster_path": "/e09dLw1Ljtccd2P4NsuUvVtS5du.jpg",
    "genres": [{"id": 80, "name": "Crime"}],
    "credits": {
        "cast": [
            {"id": 1158, "name": "Al Pacino",      "order": 0, "gender": 2},
            {"id": 380,  "name": "Robert De Niro", "order": 1, "gender": 2},
            {"id": 4038, "name": "Ashley Judd",    "order": 2, "gender": 1},
        ]
    },
    "keywords": {"keywords": [{"id": 642, "name": "robbery"}]},
    "budget": 60000000,
    "revenue": 187436818,
}


def _mock_response(data):
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = data
    return mock


# ---------------------------------------------------------------------------
# _parse: cast ids and gender
# ---------------------------------------------------------------------------

class TestParseCastIds:
    def test_cast_ids_parallel_to_cast_names(self):
        _, _, cast_names, cast_ids, *_ = _parse(DETAIL)
        assert json.loads(cast_names) == ["Al Pacino", "Robert De Niro",
                                          "Ashley Judd"]
        assert json.loads(cast_ids) == [1158, 380, 4038]

    def test_cast_ids_follow_billing_order_not_payload_order(self):
        """The two arrays are only joinable if both take the same sorted slice."""
        data = {**DETAIL, "credits": {"cast": [
            {"id": 3, "name": "Third",  "order": 2, "gender": 2},
            {"id": 1, "name": "First",  "order": 0, "gender": 1},
            {"id": 2, "name": "Second", "order": 1, "gender": 2},
        ]}}
        _, _, cast_names, cast_ids, *_ = _parse(data)
        assert json.loads(cast_names) == ["First", "Second", "Third"]
        assert json.loads(cast_ids) == [1, 2, 3]

    def test_cast_ids_capped_with_cast_names(self):
        data = {**DETAIL, "credits": {"cast": [
            {"id": i, "name": f"Actor {i}", "order": i, "gender": 2}
            for i in range(15)
        ]}}
        _, _, cast_names, cast_ids, *_ = _parse(data)
        assert len(json.loads(cast_names)) == 10
        assert len(json.loads(cast_ids)) == 10

    def test_missing_credits_gives_null_ids_and_no_people(self):
        _, _, cast_names, cast_ids, *_, people = _parse({**DETAIL, "credits": {}})
        assert cast_names is None and cast_ids is None
        assert people == []


class TestParseGender:
    @pytest.mark.parametrize("code,expected", [
        (1, "F"), (2, "M"), (3, "NB"), (0, "unknown"),
    ])
    def test_tmdb_codes_map_to_labels(self, code, expected):
        data = {**DETAIL, "credits": {"cast": [
            {"id": 7, "name": "Someone", "order": 0, "gender": code}]}}
        *_, people = _parse(data)
        assert people == [(7, "Someone", expected)]

    @pytest.mark.parametrize("entry", [
        {"id": 7, "name": "Someone", "order": 0},               # no gender key
        {"id": 7, "name": "Someone", "order": 0, "gender": None},
        {"id": 7, "name": "Someone", "order": 0, "gender": 9},  # outside the enum
    ])
    def test_absent_or_unexpected_gender_is_unknown_never_guessed(self, entry):
        """0 means "not set". Folding it into a gender overstates that gender."""
        *_, people = _parse({**DETAIL, "credits": {"cast": [entry]}})
        assert people == [(7, "Someone", "unknown")]

    def test_person_without_an_id_is_left_out_but_keeps_its_position(self):
        data = {**DETAIL, "credits": {"cast": [
            {"id": 1, "name": "Named",   "order": 0, "gender": 2},
            {"name": "Unkeyable",        "order": 1, "gender": 1},
            {"id": 3, "name": "Also",    "order": 2, "gender": 1},
        ]}}
        _, _, cast_names, cast_ids, *_, people = _parse(data)
        assert json.loads(cast_names) == ["Named", "Unkeyable", "Also"]
        assert json.loads(cast_ids) == [1, None, 3]
        assert [p[0] for p in people] == [1, 3]

    def test_every_code_in_the_enum_is_an_allowed_column_value(self):
        """GENDER_CODES and the curated_people CHECK constraint must agree."""
        conn = sqlite3.connect(":memory:")
        ensure_people_table(conn.cursor())
        people_put(conn.cursor(),
                   [(i, f"P{i}", g) for i, g in enumerate(GENDER_CODES.values())])
        assert conn.execute("SELECT COUNT(*) FROM curated_people").fetchone()[0] \
            == len(GENDER_CODES)


# ---------------------------------------------------------------------------
# people_put
# ---------------------------------------------------------------------------

@pytest.fixture
def people_db():
    conn = sqlite3.connect(":memory:")
    ensure_people_table(conn.cursor())
    yield conn
    conn.close()


class TestPeoplePut:
    def test_writes_rows_tagged_as_tmdb_sourced(self, people_db):
        people_put(people_db.cursor(), [(1158, "Al Pacino", "M")])
        assert people_db.execute(
            "SELECT name, gender, gender_source FROM curated_people"
        ).fetchall() == [("Al Pacino", "M", "tmdb")]

    def test_second_write_of_the_same_person_does_not_duplicate(self, people_db):
        people_put(people_db.cursor(), [(1158, "Al Pacino", "M")])
        people_put(people_db.cursor(), [(1158, "Al Pacino", "M")])
        assert people_db.execute(
            "SELECT COUNT(*) FROM curated_people").fetchone()[0] == 1

    def test_refetch_refreshes_a_tmdb_row(self, people_db):
        """TMDB filling in a gender it previously had unset must land."""
        people_put(people_db.cursor(), [(7, "Someone", "unknown")])
        people_put(people_db.cursor(), [(7, "Someone Else", "F")])
        assert people_db.execute(
            "SELECT name, gender FROM curated_people WHERE tmdb_person_id = 7"
        ).fetchone() == ("Someone Else", "F")

    def test_a_manual_correction_survives_a_refetch(self, people_db):
        """A hand correction exists because TMDB was wrong -- refetching it
        back to TMDB's answer would silently undo the fix on every run."""
        people_db.execute(
            "INSERT INTO curated_people "
            "(tmdb_person_id, name, gender, gender_source) "
            "VALUES (7, 'Someone', 'NB', 'manual')")
        people_put(people_db.cursor(), [(7, "Someone", "M")])
        assert people_db.execute(
            "SELECT gender, gender_source FROM curated_people "
            "WHERE tmdb_person_id = 7").fetchone() == ("NB", "manual")

    def test_a_cmu_backfilled_row_is_refreshed_by_tmdb(self, people_db):
        """CMU is the fallback for what TMDB did not know, so TMDB wins once it
        does know -- the opposite of the manual case above."""
        people_db.execute(
            "INSERT INTO curated_people "
            "(tmdb_person_id, name, gender, gender_source) "
            "VALUES (7, 'Someone', 'F', 'cmu')")
        people_put(people_db.cursor(), [(7, "Someone", "M")])
        assert people_db.execute(
            "SELECT gender, gender_source FROM curated_people "
            "WHERE tmdb_person_id = 7").fetchone() == ("M", "tmdb")

    def test_ensure_people_table_is_idempotent(self, people_db):
        people_put(people_db.cursor(), [(1158, "Al Pacino", "M")])
        ensure_people_table(people_db.cursor())   # must not raise, must not clear
        assert people_db.execute(
            "SELECT COUNT(*) FROM curated_people").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# End-to-end through enrich_metadata
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    schema_dir = ROOT / "sql" / "schemas"
    for fname in ["raw_zone.sql", "staging_zone.sql", "curated_zone.sql"]:
        conn.executescript((schema_dir / fname).read_text())
    conn.execute(
        "INSERT INTO curated_movies "
        "(movie_id, tmdb_id, title, year, total_episodes_featured, "
        " revisit_count, canonical_key_confidence) "
        "VALUES (?, 949, 'Heat', 1995, 1, 0, 'high')", (str(uuid.uuid4()),))
    conn.commit()
    conn.close()
    yield db_path


class TestEnrichFillsPeople:
    def test_cast_ids_and_people_written(self, tmp_db):
        with patch("requests.get", return_value=_mock_response(DETAIL)):
            enrich_metadata(tmp_db)

        conn = sqlite3.connect(tmp_db)
        cast_ids = conn.execute(
            "SELECT cast_ids FROM curated_movies WHERE tmdb_id = 949"
        ).fetchone()[0]
        people = conn.execute(
            "SELECT tmdb_person_id, name, gender, gender_source "
            "FROM curated_people ORDER BY tmdb_person_id").fetchall()
        conn.close()

        assert json.loads(cast_ids) == [1158, 380, 4038]
        assert people == [
            (380,  "Robert De Niro", "M", "tmdb"),
            (1158, "Al Pacino",      "M", "tmdb"),
            (4038, "Ashley Judd",    "F", "tmdb"),
        ]

    def test_the_cast_ids_join_curated_people_by_position(self, tmp_db):
        """The point of storing ids: name is not a key, position is not a name.

        cast_names[i] and cast_ids[i] describe the same credit, and that id
        resolves to exactly one person row.
        """
        with patch("requests.get", return_value=_mock_response(DETAIL)):
            enrich_metadata(tmp_db)

        conn = sqlite3.connect(tmp_db)
        names, ids = conn.execute(
            "SELECT cast_names, cast_ids FROM curated_movies WHERE tmdb_id = 949"
        ).fetchone()
        by_id = dict(conn.execute(
            "SELECT tmdb_person_id, name FROM curated_people").fetchall())
        conn.close()

        for name, pid in zip(json.loads(names), json.loads(ids)):
            assert by_id[pid] == name

    def test_a_row_cached_before_cast_ids_is_refetched_exactly_once(self, tmp_path):
        """Every existing database has 450-odd rows cached without cast ids.

        They must cost one refetch each and then settle -- the same contract
        keywords and the financial columns already have.
        """
        db_path = str(tmp_path / "stale.db")
        conn = sqlite3.connect(db_path)
        schema_dir = ROOT / "sql" / "schemas"
        for fname in ["raw_zone.sql", "staging_zone.sql", "curated_zone.sql"]:
            conn.executescript((schema_dir / fname).read_text())
        conn.execute(
            "INSERT INTO curated_movies "
            "(movie_id, tmdb_id, title, year, genres, keywords, runtime_minutes, "
            " cast_names, plot_summary, poster_url_tmdb, budget_tmdb, "
            " revenue_tmdb, total_episodes_featured, revisit_count, "
            " canonical_key_confidence) "
            "VALUES (?, 949, 'Heat', 1995, '[\"Crime\"]', '[\"robbery\"]', 170, "
            "        '[\"Al Pacino\"]', 'A film.', 'https://x/p.jpg', 1, 2, "
            "        1, 0, 'high')", (str(uuid.uuid4()),))
        # A pre-cast_ids cache row: complete by the old contract, stale by the new.
        conn.execute(
            "INSERT INTO tmdb_metadata_cache "
            "(tmdb_id, genres, keywords, runtime_minutes, cast_names, "
            " plot_summary, poster_url_tmdb, budget_tmdb, revenue_tmdb, "
            " financials_cached_at) "
            "VALUES (949, '[\"Crime\"]', '[\"robbery\"]', 170, "
            "        '[\"Al Pacino\"]', 'A film.', 'https://x/p.jpg', 1, 2, "
            "        CURRENT_TIMESTAMP)")
        conn.commit()
        conn.close()

        with patch("requests.get", return_value=_mock_response(DETAIL)) as first:
            enrich_metadata(db_path)
        assert first.call_count == 1

        with patch("requests.get", return_value=_mock_response(DETAIL)) as again:
            enrich_metadata(db_path)
        assert again.call_count == 0, "the refetch must settle after one pass"

        conn = sqlite3.connect(db_path)
        assert conn.execute(
            "SELECT COUNT(*) FROM curated_people").fetchone()[0] == 3
        conn.close()

    def test_people_survive_a_curated_rebuild(self, tmp_db):
        """06_build_curated wipes curated_movies but not curated_people.

        That is the whole reason gender lives in its own table: a rebuild must
        cost zero API calls, and must not lose the dimension.
        """
        with patch("requests.get", return_value=_mock_response(DETAIL)):
            enrich_metadata(tmp_db)

        conn = sqlite3.connect(tmp_db)
        movie_id = conn.execute(
            "SELECT movie_id FROM curated_movies").fetchone()[0]
        conn.execute("DELETE FROM curated_movies")     # what 06 does
        conn.execute(
            "INSERT INTO curated_movies "
            "(movie_id, tmdb_id, title, year, total_episodes_featured, "
            " revisit_count, canonical_key_confidence) "
            "VALUES (?, 949, 'Heat', 1995, 1, 0, 'high')", (movie_id,))
        conn.commit()
        assert conn.execute(
            "SELECT COUNT(*) FROM curated_people").fetchone()[0] == 3
        conn.close()

        with patch("requests.get", return_value=_mock_response(DETAIL)) as g:
            enrich_metadata(tmp_db)
        assert g.call_count == 0, "the rebuild must refill from cache"

        conn = sqlite3.connect(tmp_db)
        assert json.loads(conn.execute(
            "SELECT cast_ids FROM curated_movies").fetchone()[0]) == \
            [1158, 380, 4038]
        assert conn.execute(
            "SELECT COUNT(*) FROM curated_people").fetchone()[0] == 3
        conn.close()


# ---------------------------------------------------------------------------
# app.py: name -> gender resolution
# ---------------------------------------------------------------------------

def _app_helpers():
    """gender_from_people and explode_cast, lifted out of app.py.

    app.py runs Streamlit at import, so the functions are read out of its AST
    and executed in a bare namespace -- the same trick conftest uses for NAV.
    """
    import ast
    from collections import Counter

    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    wanted = {"gender_from_people", "explode_cast", "GENDERS", "GENDER_LABEL",
              "BILLED"}
    # explode_cast falls back to the app's module-level GENDER_MAP, which is
    # built from the database at import. An empty one here is the right stand-in:
    # every test that cares about gender passes its own map explicitly, and the
    # ungendered tests must behave the same either way.
    ns = {"Counter": Counter, "pd": pd, "GENDER_MAP": {}}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            exec(compile(ast.Module([node], []), "<app>", "exec"), ns)
        elif isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) in wanted for t in node.targets):
            exec(compile(ast.Module([node], []), "<app>", "exec"), ns)
    missing = wanted - set(ns)
    assert not missing, f"app.py no longer defines {missing}"
    return ns


APP = _app_helpers()


def _frame(*casts):
    return pd.DataFrame({"cast_names": list(casts)})


class TestGenderFromPeople:
    PEOPLE = pd.DataFrame([
        {"name": "Al Pacino",   "gender": "M"},
        {"name": "Ashley Judd", "gender": "F"},
        {"name": "Someone",     "gender": "unknown"},
    ])

    def test_maps_names_to_gender(self):
        m = APP["gender_from_people"](self.PEOPLE)
        assert m["Al Pacino"] == "M"
        assert m["Ashley Judd"] == "F"

    def test_a_name_with_no_person_row_is_unknown(self):
        m = APP["gender_from_people"](self.PEOPLE)
        assert m.get("Nobody At All", "unknown") == "unknown"

    def test_two_people_sharing_a_name_collapse_to_unknown(self):
        """The app groups by name, so one bar can be two people.

        Where those two disagree the honest answer is 'unknown', not whichever
        row the join happened to reach first.
        """
        clash = pd.DataFrame([
            {"name": "Chris Evans", "gender": "M"},
            {"name": "Chris Evans", "gender": "F"},
        ])
        assert APP["gender_from_people"](clash)["Chris Evans"] == "unknown"

    def test_agreeing_duplicates_keep_their_gender(self):
        dupes = pd.DataFrame([
            {"name": "Al Pacino", "gender": "M"},
            {"name": "Al Pacino", "gender": "M"},
        ])
        assert APP["gender_from_people"](dupes)["Al Pacino"] == "M"

    def test_a_null_gender_reads_as_unknown(self):
        rows = pd.DataFrame([{"name": "Someone", "gender": None}])
        assert APP["gender_from_people"](rows)["Someone"] == "unknown"


class TestExplodeCastByGender:
    GENDER = {"Al Pacino": "M", "Robert De Niro": "M", "Ashley Judd": "F"}

    def test_unfiltered_counts_are_unchanged(self):
        df = _frame(["Al Pacino", "Ashley Judd"], ["Al Pacino"])
        out = APP["explode_cast"](df)
        assert dict(zip(out["actor"], out["count"])) == \
            {"Al Pacino": 2, "Ashley Judd": 1}

    def test_filtering_to_one_gender_keeps_only_those_actors(self):
        df = _frame(["Al Pacino", "Ashley Judd", "Robert De Niro"])
        women = APP["explode_cast"](df, gender="F", gender_map=self.GENDER)
        assert list(women["actor"]) == ["Ashley Judd"]

    def test_the_two_genders_partition_the_credits(self):
        """Men + women + unknown must equal the ungendered total, or a headline
        share is being computed over a different population than it claims."""
        df = _frame(["Al Pacino", "Ashley Judd", "Nobody"], ["Al Pacino"])
        total = APP["explode_cast"](df)["count"].sum()
        split = sum(
            APP["explode_cast"](df, gender=g, gender_map=self.GENDER)["count"].sum()
            for g in ("M", "F", "NB", "unknown"))
        assert split == total

    def test_an_actor_with_no_gender_row_lands_in_unknown(self):
        df = _frame(["Nobody"])
        out = APP["explode_cast"](df, gender="unknown", gender_map=self.GENDER)
        assert list(out["actor"]) == ["Nobody"]

    def test_ranking_within_a_gender_is_by_count(self):
        df = _frame(["Ashley Judd"], ["Ashley Judd"], ["Al Pacino"])
        out = APP["explode_cast"](df, gender="M", gender_map=self.GENDER)
        assert list(out["actor"]) == ["Al Pacino"]
        out = APP["explode_cast"](df, gender="F", gender_map=self.GENDER)
        assert list(out["count"]) == [2]


# ---------------------------------------------------------------------------
# The Actors section, end to end
# ---------------------------------------------------------------------------

DB_PATH = ROOT / "rewatchables.db"
APP_FILE = ROOT / "app.py"


@pytest.fixture(scope="module")
def actors_page():
    apptest = pytest.importorskip("streamlit.testing.v1")
    if not DB_PATH.exists():
        pytest.skip("rewatchables.db has not been built yet")
    from conftest import goto
    at = apptest.AppTest.from_file(str(APP_FILE), default_timeout=240)
    at.run()
    assert not at.exception, at.exception
    at = goto(at, "Actors")
    assert not at.exception, at.exception
    return at


@pytest.fixture(scope="module")
def db_gender():
    """name -> gender straight from the database, bypassing the app."""
    if not DB_PATH.exists():
        pytest.skip("rewatchables.db has not been built yet")
    conn = sqlite3.connect(DB_PATH)
    have = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "curated_people" not in have:
        conn.close()
        pytest.skip("curated_people has not been populated yet")
    rows = conn.execute("SELECT name, gender FROM curated_people").fetchall()
    conn.close()
    if not rows:
        pytest.skip("curated_people is empty")
    return rows


class TestActorsSectionSplit:
    def test_the_section_renders_a_column_per_gender(self, actors_page,
                                                     db_gender):
        """Asserted on the column headings rather than the chart keys: AppTest
        does not carry a plotly_chart's key, and the heading is what a reader
        actually uses to tell the two columns apart."""
        headers = [str(m.value) for m in actors_page.markdown
                   if "actors</p>" in str(m.value)]
        assert any("<b>Men</b>" in h for h in headers)
        assert any("<b>Women</b>" in h for h in headers)

    def test_each_column_reports_its_own_population(self, actors_page,
                                                    db_gender):
        """A ranking of fifteen names means nothing without the size of the
        field it was drawn from."""
        headers = [str(m.value) for m in actors_page.markdown
                   if "actors</p>" in str(m.value)]
        counts = [int(re.search(r"([\d,]+) actors", h).group(1).replace(",", ""))
                  for h in headers]
        assert len(counts) == 2 and all(c > 0 for c in counts)
        assert counts[0] > counts[1], "men are the larger field in this catalogue"

    def test_the_combined_leaderboard_is_still_there(self, actors_page):
        """The split is an addition. Losing the overall ranking would trade one
        question for another rather than answering both."""
        headings = [str(m.value) for m in actors_page.markdown]
        assert any("Most-featured actors<" in h for h in headings), \
            "the ungendered leaderboard is gone"

    def test_the_note_names_the_unrecorded_credits(self, actors_page):
        """A share is only readable next to the population it excludes."""
        notes = [str(m.value) for m in actors_page.markdown
                 if "credits" in str(m.value) and "ch-note" in str(m.value)]
        assert any("none recorded" in n for n in notes), \
            "the split does not disclose its unrecorded credits"

    def test_tmdb_records_a_gender_for_nearly_every_billed_actor(self, db_gender):
        """The claim the whole feature rests on.

        If this ever fell far, the split would be charting TMDB's coverage
        rather than the podcast's casting, and the panel would need to say so
        much more loudly than a footnote.
        """
        unknown = sum(1 for _, g in db_gender if g == "unknown")
        assert unknown / len(db_gender) < 0.10, (
            f"{unknown}/{len(db_gender)} people have no recorded gender — "
            "the split is no longer measuring what it claims")
