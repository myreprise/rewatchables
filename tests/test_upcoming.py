"""
Tests for the upcoming-films path: 13_build_upcoming.py, the presentation
helpers in views.py, and the section in app.py.

The regression that matters most here is the overlap rule. A requested film that
becomes a real episode has to stop appearing on the list — and, just as
importantly, a requested film that merely SHARES A TITLE with an episode has to
stay. The source list holds a different Crash, a different Heat and a different
Miami Vice from the ones in the catalogue; matching on title removes all three.
Those cases have their own class below and should not be deleted.

No network. TMDB is reached only through the two caches, which are seeded
directly in the fixtures.
"""

import importlib.util
import json
import sqlite3
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent


def _load(script, name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


up = _load("13_build_upcoming.py", "build_upcoming")
keys = _load("_keys.py", "keys_mod")
convert = _load("convert_xlsx_to_csv.py", "convert_mod")

import views


# ---------------------------------------------------------------------------
# Business key and ids
# ---------------------------------------------------------------------------

class TestBusinessKey:
    def test_title_and_year_together(self):
        assert keys.upcoming_business_key("Crash", 1996) == "Crash|1996"

    def test_year_is_part_of_identity(self):
        """The whole point of the key. Two films can share a title."""
        assert (keys.upcoming_business_key("Crash", 1996)
                != keys.upcoming_business_key("Crash", 2005))

    def test_whitespace_does_not_change_identity(self):
        assert (keys.upcoming_business_key(" Heat ", " 1987 ")
                == keys.upcoming_business_key("Heat", "1987"))

    def test_missing_year_is_empty_not_none(self):
        assert keys.upcoming_business_key("Bad Influence", None) == "Bad Influence|"

    def test_year_ranges_survive_as_written(self):
        """Parsing here would collapse two TV series onto one key."""
        assert keys.upcoming_business_key("Oz", "1997-2003") == "Oz|1997-2003"

    def test_id_is_deterministic(self):
        assert (keys.make_upcoming_id("Toy Story", 1995)
                == keys.make_upcoming_id("Toy Story", 1995))

    def test_id_does_not_collide_with_an_episode_id(self):
        """Both spaces share a uuid5 namespace; the prefix is what separates them."""
        assert (keys.make_upcoming_id("Heat", "1987")
                != keys.make_episode_id("Heat", "1987", "Heat"))


# ---------------------------------------------------------------------------
# Year parsing — the guard that stops a TV series matching a film
# ---------------------------------------------------------------------------

class TestParseYear:
    def test_plain_year(self):
        assert up.parse_year("1995") == 1995
        assert up.parse_year(1995) == 1995

    def test_blank_is_none(self):
        assert up.parse_year("") is None
        assert up.parse_year(None) is None

    @pytest.mark.parametrize("value", ["1984-1990", "1997-2003"])
    def test_a_range_is_not_a_year(self, value):
        """Taking the first year of a range would hand a TV series a confident
        match against a film that merely shares its name."""
        assert up.parse_year(value) is None

    def test_no_auto_resolve_without_a_year(self):
        """The strictness that distinguishes this path from the episode one."""
        tmdb_id, method, conf, cands, networked = up.resolve_film(
            None, None, "Miami Vice (TV series)", None)
        assert tmdb_id is None
        assert method == "unresolved_no_year"
        assert networked is False


# ---------------------------------------------------------------------------
# The source reshape
# ---------------------------------------------------------------------------

class TestUpcomingReshape:
    def _frame(self, **overrides):
        import pandas as pd
        row = {
            "index": 1, "title": "The Thing", "contributor": "contributed by u/x",
            "year": 1982, "justification_1": None, "justification_2": None,
            "justification_3": None, "entry_name": "Thing, The",
        }
        row.update(overrides)
        return pd.DataFrame([row])

    def test_keeps_only_the_five_carrying_columns(self):
        out = convert.upcoming_reshape(self._frame(justification_1="on air"))
        assert list(out.columns) == [
            "title", "year", "contributor", "mention_note", "pitch_tags"]

    def test_justification_1_becomes_the_note(self):
        out = convert.upcoming_reshape(self._frame(justification_1="on air"))
        assert out["mention_note"].iloc[0] == "on air"

    def test_justification_3_also_becomes_the_note(self):
        """_1 and _3 are the same kind of thing said in two columns."""
        out = convert.upcoming_reshape(self._frame(justification_3="in the vote"))
        assert out["mention_note"].iloc[0] == "in the vote"

    def test_justification_2_becomes_tags_not_the_note(self):
        """_2 is a comma-separated pitch, a different kind of thing."""
        out = convert.upcoming_reshape(
            self._frame(justification_2="1980s, John Carpenter"))
        assert out["pitch_tags"].iloc[0] == "1980s, John Carpenter"
        assert out["mention_note"].isna().iloc[0]

    def test_contributed_by_prefix_is_stripped(self):
        out = convert.upcoming_reshape(self._frame(justification_1="x"))
        assert out["contributor"].iloc[0] == "u/x"

    def test_entry_name_is_dropped(self):
        """A sort key, not a name — derived by views.sort_title instead."""
        out = convert.upcoming_reshape(self._frame(justification_1="x"))
        assert "entry_name" not in out.columns


# ---------------------------------------------------------------------------
# The conversion phase — the xlsx is the source of truth
# ---------------------------------------------------------------------------

def write_xlsx(path, rows):
    """A minimal 'remaining films.xlsx' in the shape the real sheet has."""
    import pandas as pd
    pd.DataFrame(rows).to_excel(path, index=False)
    return path


class TestRefreshFromXlsx:
    def test_the_csv_is_regenerated_from_the_xlsx(self, tmp_path):
        xlsx = write_xlsx(tmp_path / "src.xlsx", [{
            "index": 1, "title": "The Thing", "contributor": "contributed by u/x",
            "year": 1982, "justification_1": "on air", "justification_2": None,
            "justification_3": None, "entry_name": "Thing, The"}])
        csv = tmp_path / "out.csv"
        assert up.refresh_csv_from_xlsx(xlsx, csv) is True
        text = csv.read_text(encoding="utf-8")
        assert "The Thing,1982,u/x,on air," in text

    def test_an_edit_to_the_csv_is_overwritten(self, tmp_path):
        """The trap this has to set loudly: the xlsx wins, every run."""
        xlsx = write_xlsx(tmp_path / "src.xlsx", [{
            "index": 1, "title": "The Thing", "contributor": "u/x",
            "year": 1982, "justification_1": "on air", "justification_2": None,
            "justification_3": None, "entry_name": "Thing, The"}])
        csv = tmp_path / "out.csv"
        csv.write_text(SOURCE_HEADER + "Hand Edited,1999,u/me,mine,\n",
                       encoding="utf-8")
        up.refresh_csv_from_xlsx(xlsx, csv)
        assert "Hand Edited" not in csv.read_text(encoding="utf-8")

    def test_a_missing_xlsx_falls_back_to_the_csv(self, tmp_path):
        """A fresh checkout has the tracked CSV but need not have the xlsx."""
        csv = tmp_path / "out.csv"
        csv.write_text(SOURCE_HEADER + "Toy Story,1995,u/a,on air,\n",
                       encoding="utf-8")
        assert up.refresh_csv_from_xlsx(tmp_path / "absent.xlsx", csv) is True
        assert "Toy Story" in csv.read_text(encoding="utf-8")

    def test_neither_file_stops_the_run(self, tmp_path):
        assert up.refresh_csv_from_xlsx(
            tmp_path / "absent.xlsx", tmp_path / "absent.csv") is False

    def test_a_locked_xlsx_stops_the_run_rather_than_falling_back(
            self, tmp_path, monkeypatch):
        """Excel holding the file open must NOT quietly build the old list.

        This is the failure mode the whole guard exists for: the user is looking
        at their edits on screen while the pipeline reads the previous version.
        """
        xlsx = write_xlsx(tmp_path / "src.xlsx", [{
            "index": 1, "title": "The Thing", "contributor": "u/x",
            "year": 1982, "justification_1": "on air", "justification_2": None,
            "justification_3": None, "entry_name": "Thing, The"}])
        csv = tmp_path / "out.csv"
        csv.write_text(SOURCE_HEADER + "Stale,1990,u/a,old,\n", encoding="utf-8")

        def locked(*_a, **_k):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(up._convert, "convert", locked)
        assert up.refresh_csv_from_xlsx(xlsx, csv) is False
        # ...and the stale CSV is untouched, not loaded.
        assert "Stale" in csv.read_text(encoding="utf-8")

    def test_build_converts_before_loading(self, db, tmp_path, monkeypatch):
        """End to end: a row that exists only in the xlsx reaches the raw zone."""
        xlsx = write_xlsx(tmp_path / "src.xlsx", [{
            "index": 1, "title": "Toy Story", "contributor": "u/a",
            "year": 1995, "justification_1": "on air", "justification_2": None,
            "justification_3": None, "entry_name": "Toy Story"}])
        csv = tmp_path / "out.csv"
        seed_search(db, "Toy Story", 1995, 862)
        monkeypatch.setattr(up, "SOURCE_XLSX", xlsx)
        monkeypatch.setattr(up, "SOURCE_CSV", csv)
        monkeypatch.setattr(up.time, "sleep", lambda *_: None)
        assert up.build(str(db)) == 0
        conn = sqlite3.connect(db)
        assert conn.execute(
            "SELECT title FROM curated_upcoming_films").fetchone()[0] == "Toy Story"

    def test_skip_convert_leaves_the_csv_alone(self, db, tmp_path, monkeypatch):
        """The escape hatch for a genuinely hand-edited CSV."""
        xlsx = write_xlsx(tmp_path / "src.xlsx", [{
            "index": 1, "title": "Toy Story", "contributor": "u/a",
            "year": 1995, "justification_1": "on air", "justification_2": None,
            "justification_3": None, "entry_name": "Toy Story"}])
        csv = write_source(tmp_path, ["Amadeus,1984,u/b,on air,\n"])
        seed_search(db, "Amadeus", 1984, 279)
        monkeypatch.setattr(up, "SOURCE_XLSX", xlsx)
        monkeypatch.setattr(up, "SOURCE_CSV", csv)
        monkeypatch.setattr(up.time, "sleep", lambda *_: None)
        assert up.build(str(db), skip_convert=True) == 0
        conn = sqlite3.connect(db)
        assert conn.execute(
            "SELECT title FROM curated_upcoming_films").fetchone()[0] == "Amadeus"


# ---------------------------------------------------------------------------
# The load
# ---------------------------------------------------------------------------

SOURCE_HEADER = "title,year,contributor,mention_note,pitch_tags\n"


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "t.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE curated_movies (
            movie_id TEXT PRIMARY KEY, tmdb_id INTEGER UNIQUE,
            title TEXT, year INTEGER, directors TEXT, rating_tmdb REAL,
            poster_url_tmdb TEXT, first_episode_date DATE,
            total_episodes_featured INTEGER);
        CREATE TABLE api_call_log (
            call_id TEXT PRIMARY KEY, api_source TEXT, query_text TEXT,
            response_status_code INTEGER, response_time_ms INTEGER,
            rate_limit_remaining INTEGER, called_at TIMESTAMP, error_message TEXT);
    """)
    up.ensure_schema(conn.cursor())
    conn.commit()
    conn.close()
    return path


def seed_movie(db, tmdb_id, title, year, movie_id=None):
    """One aired film in the catalogue."""
    movie_id = movie_id or str(uuid.uuid4())
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO curated_movies (movie_id, tmdb_id, title, year, "
        "first_episode_date, total_episodes_featured) VALUES (?, ?, ?, ?, ?, 1)",
        (movie_id, tmdb_id, title, year, "2020-01-01"))
    conn.commit()
    conn.close()
    return movie_id


def seed_search(db, title, year, tmdb_id, cand_title=None, cand_year=None):
    """A tmdb_search_cache hit, so resolution never reaches the network."""
    conn = sqlite3.connect(db)
    cur = conn.cursor()
    candidates = [{
        "id": tmdb_id, "title": cand_title or title,
        "year": str(cand_year or year), "popularity": 10.0,
        "vote_average": 7.5,
    }]
    up._enrich.cache_put(cur, title, year, candidates)
    # A metadata row whose keywords are set reads as "already fetched", so no
    # detail call is made either.
    cur.execute(
        "INSERT OR REPLACE INTO tmdb_metadata_cache "
        "(tmdb_id, genres, keywords, runtime_minutes, cast_names, plot_summary, "
        " poster_url_tmdb, financials_cached_at) "
        "VALUES (?, '[\"Drama\"]', '[\"a\"]', 100, '[\"Someone\"]', 'plot', "
        "        'http://p', CURRENT_TIMESTAMP)",
        (tmdb_id,))
    conn.commit()
    conn.close()


def write_source(tmp_path, rows):
    path = tmp_path / "upcoming.csv"
    path.write_text(SOURCE_HEADER + "".join(rows), encoding="utf-8")
    return path


def run_build(db, csv_path, monkeypatch, xlsx_path=None):
    """Build against a fixture CSV.

    SOURCE_XLSX is pointed at an absent file by default, which does two things:
    it exercises the "no xlsx, fall back to the tracked CSV" branch, and — much
    more importantly — it stops the conversion phase reading the REAL
    "data/remaining films.xlsx" and writing its 214 rows over the one-row
    fixture this test just wrote. Leaving it unpatched silently turns every
    assertion below into an assertion about the live source list.
    """
    monkeypatch.setattr(up, "SOURCE_XLSX",
                        Path(xlsx_path or csv_path.parent / "no-such.xlsx"))
    monkeypatch.setattr(up, "SOURCE_CSV", csv_path)
    monkeypatch.setattr(up.time, "sleep", lambda *_: None)
    return up.build(str(db))


class TestLoad:
    def test_rows_land_in_the_raw_zone(self, db, tmp_path, monkeypatch):
        seed_search(db, "Toy Story", 1995, 862)
        csv = write_source(tmp_path, ["Toy Story,1995,u/a,on air,\n"])
        assert run_build(db, csv, monkeypatch) == 0
        conn = sqlite3.connect(db)
        assert conn.execute(
            "SELECT COUNT(*) FROM raw_upcoming_films_current").fetchone()[0] == 1

    def test_a_second_identical_load_inserts_nothing(self, db, tmp_path, monkeypatch):
        seed_search(db, "Toy Story", 1995, 862)
        csv = write_source(tmp_path, ["Toy Story,1995,u/a,on air,\n"])
        run_build(db, csv, monkeypatch)
        run_build(db, csv, monkeypatch)
        conn = sqlite3.connect(db)
        assert conn.execute(
            "SELECT COUNT(*) FROM raw_upcoming_films").fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM raw_upcoming_films_current").fetchone()[0] == 1

    def test_an_edit_is_stored_as_a_new_version(self, db, tmp_path, monkeypatch):
        seed_search(db, "Toy Story", 1995, 862)
        run_build(db, write_source(tmp_path, ["Toy Story,1995,u/a,on air,\n"]),
                  monkeypatch)
        run_build(db, write_source(tmp_path, ["Toy Story,1995,u/a,said twice,\n"]),
                  monkeypatch)
        conn = sqlite3.connect(db)
        assert conn.execute(
            "SELECT COUNT(*) FROM raw_upcoming_films").fetchone()[0] == 2
        # ...but only the newer one is current.
        note = conn.execute(
            "SELECT mention_note FROM raw_upcoming_films_current").fetchone()[0]
        assert note == "said twice"

    def test_a_removed_film_falls_out_of_current(self, db, tmp_path, monkeypatch):
        seed_search(db, "Toy Story", 1995, 862)
        seed_search(db, "Amadeus", 1984, 279)
        run_build(db, write_source(tmp_path, [
            "Toy Story,1995,u/a,on air,\n", "Amadeus,1984,u/b,on air,\n"]),
            monkeypatch)
        run_build(db, write_source(tmp_path, ["Toy Story,1995,u/a,on air,\n"]),
                  monkeypatch)
        conn = sqlite3.connect(db)
        assert conn.execute(
            "SELECT COUNT(*) FROM raw_upcoming_films_current").fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM curated_upcoming_films").fetchone()[0] == 1

    def test_the_load_does_not_touch_raw_ingest_runs(self, db, tmp_path, monkeypatch):
        """raw_episodes_current pins to the newest row of that table. A load
        recorded there would empty the episode view — and the whole app."""
        conn = sqlite3.connect(db)
        conn.execute("""CREATE TABLE raw_ingest_runs (
            ingest_run_id TEXT PRIMARY KEY, source_url TEXT,
            sync_timestamp TIMESTAMP, rows_ingested INTEGER, sync_status TEXT)""")
        conn.commit()
        conn.close()
        seed_search(db, "Toy Story", 1995, 862)
        run_build(db, write_source(tmp_path, ["Toy Story,1995,u/a,on air,\n"]),
                  monkeypatch)
        conn = sqlite3.connect(db)
        assert conn.execute(
            "SELECT COUNT(*) FROM raw_ingest_runs").fetchone()[0] == 0


# ---------------------------------------------------------------------------
# THE OVERLAP RULE — the regression this whole section exists to protect
# ---------------------------------------------------------------------------

class TestOverlapRule:
    def test_a_film_that_aired_is_marked_superseded(self, db, tmp_path, monkeypatch):
        movie_id = seed_movie(db, 862, "Toy Story", 1995)
        seed_search(db, "Toy Story", 1995, 862)
        run_build(db, write_source(tmp_path, ["Toy Story,1995,u/a,on air,\n"]),
                  monkeypatch)
        conn = sqlite3.connect(db)
        row = conn.execute(
            "SELECT superseded_by_movie_id, superseded_at "
            "FROM curated_upcoming_films").fetchone()
        assert row[0] == movie_id
        assert row[1] is not None

    def test_a_superseded_film_leaves_the_pending_view(self, db, tmp_path, monkeypatch):
        seed_movie(db, 862, "Toy Story", 1995)
        seed_search(db, "Toy Story", 1995, 862)
        run_build(db, write_source(tmp_path, ["Toy Story,1995,u/a,on air,\n"]),
                  monkeypatch)
        conn = sqlite3.connect(db)
        assert conn.execute(
            "SELECT COUNT(*) FROM v_upcoming_pending").fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM v_upcoming_graduated").fetchone()[0] == 1

    def test_a_superseded_film_is_marked_not_deleted(self, db, tmp_path, monkeypatch):
        """It stays as evidence the rule fired, and so the app can show it."""
        seed_movie(db, 862, "Toy Story", 1995)
        seed_search(db, "Toy Story", 1995, 862)
        run_build(db, write_source(tmp_path, ["Toy Story,1995,u/a,on air,\n"]),
                  monkeypatch)
        conn = sqlite3.connect(db)
        assert conn.execute(
            "SELECT COUNT(*) FROM curated_upcoming_films").fetchone()[0] == 1

    # -- the four title collisions that make tmdb_id the key ----------------

    def test_a_different_film_with_the_same_title_stays(self, db, tmp_path, monkeypatch):
        """Crash (1996, Cronenberg) is not Crash (2005, Haggis).

        Matching on title removes it. This is the case the whole design turns
        on, so it is asserted on its own rather than folded into a loop.
        """
        seed_movie(db, 1640, "Crash", 2005)
        seed_search(db, "Crash", 1996, 884)
        run_build(db, write_source(tmp_path, ["Crash,1996,u/a,on air,\n"]),
                  monkeypatch)
        conn = sqlite3.connect(db)
        row = conn.execute(
            "SELECT tmdb_id, superseded_by_movie_id FROM curated_upcoming_films"
        ).fetchone()
        assert row == (884, None)
        assert conn.execute(
            "SELECT COUNT(*) FROM v_upcoming_pending").fetchone()[0] == 1

    def test_an_identical_title_string_is_not_enough(self, db, tmp_path, monkeypatch):
        """Heat (1987) and Heat (1995) are byte-identical as titles."""
        seed_movie(db, 949, "Heat", 1995)
        seed_search(db, "Heat", 1987, 42023, cand_title="Heat", cand_year=1986)
        run_build(db, write_source(tmp_path, ["Heat,1987,u/a,on air,\n"]),
                  monkeypatch)
        conn = sqlite3.connect(db)
        assert conn.execute(
            "SELECT superseded_by_movie_id FROM curated_upcoming_films"
        ).fetchone()[0] is None

    def test_a_tv_series_never_graduates(self, db, tmp_path, monkeypatch):
        """Miami Vice the series must not be absorbed by Miami Vice the film.

        It has no parseable year, so it never resolves, so it has no tmdb_id to
        match on — the safe direction to fail in.
        """
        seed_movie(db, 260, "Miami Vice", 2006)
        run_build(db, write_source(
            tmp_path, ["Miami Vice (TV series),1984-1990,u/a,on air,\n"]),
            monkeypatch)
        conn = sqlite3.connect(db)
        row = conn.execute(
            "SELECT tmdb_id, resolution_method, superseded_by_movie_id "
            "FROM curated_upcoming_films").fetchone()
        assert row == (None, "unresolved_no_year", None)

    def test_an_unresolved_film_can_never_be_superseded(self, db, tmp_path, monkeypatch):
        seed_movie(db, 999, "Bad Influence", 1990)
        run_build(db, write_source(tmp_path, ["Bad Influence,,u/a,on air,\n"]),
                  monkeypatch)
        conn = sqlite3.connect(db)
        assert conn.execute(
            "SELECT COUNT(*) FROM v_upcoming_pending").fetchone()[0] == 1


# ---------------------------------------------------------------------------
# Build details
# ---------------------------------------------------------------------------

class TestBuild:
    def test_metadata_comes_from_the_shared_cache(self, db, tmp_path, monkeypatch):
        seed_search(db, "Toy Story", 1995, 862)
        run_build(db, write_source(tmp_path, ["Toy Story,1995,u/a,on air,\n"]),
                  monkeypatch)
        conn = sqlite3.connect(db)
        genres, runtime, poster = conn.execute(
            "SELECT genres, runtime_minutes, poster_url_tmdb "
            "FROM curated_upcoming_films").fetchone()
        assert json.loads(genres) == ["Drama"]
        assert runtime == 100
        assert poster == "http://p"

    def test_rating_comes_from_the_winning_candidate(self, db, tmp_path, monkeypatch):
        """Free: TMDB returns vote_average on /search/movie, and it is the same
        field 06_build_curated writes to curated_movies."""
        seed_search(db, "Toy Story", 1995, 862)
        run_build(db, write_source(tmp_path, ["Toy Story,1995,u/a,on air,\n"]),
                  monkeypatch)
        conn = sqlite3.connect(db)
        assert conn.execute(
            "SELECT rating_tmdb FROM curated_upcoming_films").fetchone()[0] == 7.5

    def test_the_curated_table_is_rebuilt_not_appended(self, db, tmp_path, monkeypatch):
        seed_search(db, "Toy Story", 1995, 862)
        csv = write_source(tmp_path, ["Toy Story,1995,u/a,on air,\n"])
        run_build(db, csv, monkeypatch)
        run_build(db, csv, monkeypatch)
        conn = sqlite3.connect(db)
        assert conn.execute(
            "SELECT COUNT(*) FROM curated_upcoming_films").fetchone()[0] == 1

    def test_the_id_survives_a_rebuild(self, db, tmp_path, monkeypatch):
        """A shared ?upcoming= link has to keep working across pipeline runs."""
        seed_search(db, "Toy Story", 1995, 862)
        csv = write_source(tmp_path, ["Toy Story,1995,u/a,on air,\n"])
        run_build(db, csv, monkeypatch)
        conn = sqlite3.connect(db)
        first = conn.execute(
            "SELECT upcoming_film_id FROM curated_upcoming_films").fetchone()[0]
        conn.close()
        run_build(db, csv, monkeypatch)
        conn = sqlite3.connect(db)
        assert conn.execute(
            "SELECT upcoming_film_id FROM curated_upcoming_films").fetchone()[0] == first

    def test_year_range_is_kept_raw_and_parsed_to_null(self, db, tmp_path, monkeypatch):
        run_build(db, write_source(tmp_path, ["Oz,1997-2003,u/a,on air,\n"]),
                  monkeypatch)
        conn = sqlite3.connect(db)
        assert conn.execute(
            "SELECT year_raw, year FROM curated_upcoming_films").fetchone() \
            == ("1997-2003", None)


# ---------------------------------------------------------------------------
# Presentation helpers
# ---------------------------------------------------------------------------

class TestViews:
    def test_tags_split_on_commas(self):
        assert views.parse_tags("1980s, John Carpenter, Kurt Russell") == [
            "1980s", "John Carpenter", "Kurt Russell"]

    def test_tags_are_deduplicated_case_insensitively(self):
        assert views.parse_tags("1980s, 1980S") == ["1980s"]

    def test_no_tags_is_an_empty_list(self):
        assert views.parse_tags(None) == []
        assert views.parse_tags("") == []

    @pytest.mark.parametrize("title,expected", [
        ("The Blind Side", "Blind Side, The"),
        ("A Perfect Getaway", "Perfect Getaway, A"),
        ("An Officer and a Gentleman", "Officer and a Gentleman, An"),
        ("Blade Runner", "Blade Runner"),
        ("Theodore Rex", "Theodore Rex"),      # not the article "The"
    ])
    def test_sort_title(self, title, expected):
        assert views.sort_title(title) == expected

    def test_a_handle_links_to_the_user(self):
        assert views.contributor_link("u/lovegun59") == (
            "u/lovegun59", "https://www.reddit.com/user/lovegun59")

    def test_a_url_links_to_the_thread(self):
        label, href = views.contributor_link("https://reddit.com/r/x/comments/y")
        assert label == "reddit thread"
        assert href == "https://reddit.com/r/x/comments/y"

    def test_no_contributor_is_none(self):
        assert views.contributor_link("") == (None, None)
        assert views.contributor_link("nan") == (None, None)

    def test_every_resolution_method_has_a_note(self):
        """The section prints one for each; a missing key is a blank line."""
        methods = {"unresolved_no_year", "unresolved_no_match",
                   "unresolved_low_confidence", "unresolved_error"}
        assert methods <= set(views.RESOLUTION_NOTE)


# ---------------------------------------------------------------------------
# The app section
# ---------------------------------------------------------------------------

from conftest import goto  # noqa: E402

DB_PATH = ROOT / "rewatchables.db"

# Same gate the other app-level suites use: these drive the real app against the
# real database, so they are skipped rather than failed on a fresh checkout.
db_only = pytest.mark.skipif(
    not DB_PATH.exists(), reason="rewatchables.db has not been built yet")


@pytest.fixture(scope="module")
def at_section():
    """The app, once, parked on the section. Booting it costs ~10s."""
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90).run()
    return goto(at, "Upcoming Films")


def _grid_titles(at):
    return {b.label.split("\n")[0]
            for b in at.button if b.key.startswith("btn_up_grid_")}


@db_only
class TestSection:
    def test_the_rail_reaches_it(self, at_section):
        assert not at_section.exception
        assert any("still in the queue" in m.value for m in at_section.markdown)

    def test_it_states_how_many_are_pending(self, at_section):
        body = " ".join(m.value for m in at_section.markdown)
        assert "IN CONTENTION" in body.upper()

    def test_a_graduated_film_is_not_in_the_grid(self, at_section):
        """The requirement, asserted against the real database."""
        conn = sqlite3.connect(DB_PATH)
        made = {r[0] for r in conn.execute(
            "SELECT requested_title FROM v_upcoming_graduated")}
        conn.close()
        assert made, "no graduates in the database — the test proves nothing"
        assert not (_grid_titles(at_section) & made)

    def test_an_unresolved_film_still_gets_a_card(self, at_section):
        """Two TV series and a yearless film are real requests, not errors."""
        conn = sqlite3.connect(DB_PATH)
        unresolved = {r[0] for r in conn.execute(
            "SELECT title FROM v_upcoming_pending WHERE tmdb_id IS NULL")}
        conn.close()
        assert unresolved, "nothing unresolved — the test proves nothing"
        assert unresolved <= _grid_titles(at_section)
