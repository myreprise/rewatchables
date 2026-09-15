"""
Tests for 11_load_cmu.py — loading the vendored CMU subset into the raw zone.
"""

import json
import sqlite3
import uuid
from pathlib import Path

import pytest

from rewatchables.pipeline import s11_load_cmu as mod

load_cmu = mod.load_cmu

MOVIES_TSV = """\
wikipedia_page_id\tfreebase_id\tname\trelease_date\tbox_office_revenue\truntime\tlanguages\tcountries\tgenres
97646\t/m/0p3_y\tDie Hard\t1988-07-15\t140767956\t131.0\t{}\t{}\t{"/m/02kdv5l": "Action"}
168597\t/m/016ky6\tBig\t1988-06-03\t\t\t{}\t{}\t{"/m/06n90": "Comedy"}
"""

# 'Big' has no summary here, so the LEFT JOIN in the view is exercised too.
SUMMARIES_TSV = """\
wikipedia_page_id\tsummary
97646\tNYPD officer John McClane travels to Los Angeles and fights terrorists.
"""

CHARACTERS_TSV = """\
fb_character_actor_map_id\twikipedia_page_id\tfreebase_id\trelease_date\tcharacter_name\tactor_dob\tactor_gender\tactor_height_m\tactor_ethnicity_fbid\tactor_name\tactor_age_at_release\tfb_character_id\tfb_actor_id
/m/a1\t97646\t/m/0p3_y\t1988-07-15\tJohn McClane\t1955-03-19\tM\t1.83\t/m/0x67\tBruce Willis\t33\t/m/c1\t/m/act1
/m/a2\t168597\t/m/016ky6\t1988-06-03\tJosh\t\t\t\t\tTom Hanks\t\t\t/m/act2
/m/a3\t168597\t/m/016ky6\t1988-06-03\tBad Row\t2011-09-02\tM\t\t\tJohn Doe\t-15\t\t/m/act3
"""


@pytest.fixture
def source(tmp_path):
    d = tmp_path / "cmu"
    d.mkdir()
    (d / "movies.tsv").write_text(MOVIES_TSV, encoding="utf-8")
    (d / "plot_summaries.tsv").write_text(SUMMARIES_TSV, encoding="utf-8")
    (d / "characters.tsv").write_text(CHARACTERS_TSV, encoding="utf-8")
    (d / "manifest.json").write_text(json.dumps({
        "source_url": "http://example.invalid/MovieSummaries.tar.gz",
        "tarball_sha256": "a" * 64}), encoding="utf-8")
    return d


@pytest.fixture
def db(tmp_path):
    """Two curated films. 'Big' carries a CURRENT page id that does not match
    the corpus — only freebase_id links it."""
    p = str(tmp_path / "test.db")
    conn = sqlite3.connect(p)
    schema_dir = Path(__file__).parent.parent / "sql" / "schemas"
    for fname in ["raw_zone.sql", "staging_zone.sql", "curated_zone.sql"]:
        conn.executescript((schema_dir / fname).read_text())
    for tmdb_id, title, year, fb, pid in [
        (562, "Die Hard", 1988, "/m/0p3_y", 97646),
        (2280, "Big", 1988, "/m/016ky6", 38444154),
    ]:
        conn.execute(
            "INSERT INTO curated_movies (movie_id, tmdb_id, title, year, "
            "freebase_id, wikipedia_page_id, total_episodes_featured, "
            "revisit_count, canonical_key_confidence) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, 0, 'high')",
            (str(uuid.uuid4()), tmdb_id, title, year, fb, pid))
    conn.commit()
    conn.close()
    return p


class TestLoad:
    def test_loads_all_three_tables(self, db, source):
        movies, summaries, chars, linked = load_cmu(db, source)
        assert (movies, summaries, chars, linked) == (2, 1, 3, 2)
        conn = sqlite3.connect(db)
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ["raw_cmu_movies", "raw_cmu_summaries",
                            "raw_cmu_characters"]}
        conn.close()
        assert counts == {"raw_cmu_movies": 2, "raw_cmu_summaries": 1,
                          "raw_cmu_characters": 3}

    def test_reload_is_idempotent(self, db, source):
        load_cmu(db, source)
        load_cmu(db, source)
        conn = sqlite3.connect(db)
        n = conn.execute("SELECT COUNT(*) FROM raw_cmu_characters").fetchone()[0]
        loads = conn.execute("SELECT COUNT(*) FROM raw_cmu_loads").fetchone()[0]
        conn.close()
        assert n == 3, "rows must be replaced, not appended"
        assert loads == 2, "each load is still recorded for provenance"

    def test_blanks_become_null(self, db, source):
        load_cmu(db, source)
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT box_office_revenue, runtime FROM "
                           "raw_cmu_movies WHERE name = 'Big'").fetchone()
        char = conn.execute("SELECT actor_dob, actor_gender, actor_height_m, "
                            "actor_age_at_release FROM raw_cmu_characters "
                            "WHERE actor_name = 'Tom Hanks'").fetchone()
        conn.close()
        assert row == (None, None)
        assert char == (None, None, None, None)

    def test_numeric_types_are_converted(self, db, source):
        load_cmu(db, source)
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT box_office_revenue, runtime FROM "
                           "raw_cmu_movies WHERE name = 'Die Hard'").fetchone()
        conn.close()
        assert row == (140767956, 131.0)
        assert isinstance(row[0], int) and isinstance(row[1], float)

    def test_impossible_ages_are_preserved(self, db, source):
        """Raw zone keeps bad source data; filtering belongs downstream."""
        load_cmu(db, source)
        conn = sqlite3.connect(db)
        age = conn.execute("SELECT actor_age_at_release FROM raw_cmu_characters "
                           "WHERE actor_name = 'John Doe'").fetchone()[0]
        conn.close()
        assert age == -15

    def test_word_count_computed(self, db, source):
        load_cmu(db, source)
        conn = sqlite3.connect(db)
        wc = conn.execute("SELECT word_count FROM raw_cmu_summaries "
                          "WHERE wikipedia_page_id = 97646").fetchone()[0]
        conn.close()
        assert wc == 11

    def test_records_load_provenance(self, db, source):
        load_cmu(db, source)
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT source_url, tarball_sha256, movies_loaded, "
                           "summaries_loaded, characters_loaded FROM "
                           "raw_cmu_loads").fetchone()
        conn.close()
        assert row == ("http://example.invalid/MovieSummaries.tar.gz",
                       "a" * 64, 2, 1, 3)

    def test_does_not_touch_raw_ingest_runs(self, db, source):
        """A CMU load in raw_ingest_runs would starve 03_normalize, which pins
        staging to the newest row there."""
        load_cmu(db, source)
        conn = sqlite3.connect(db)
        n = conn.execute("SELECT COUNT(*) FROM raw_ingest_runs").fetchone()[0]
        conn.close()
        assert n == 0


class TestJoinView:
    def test_links_both_films(self, db, source):
        load_cmu(db, source)
        conn = sqlite3.connect(db)
        titles = {r[0] for r in conn.execute("SELECT title FROM v_movie_cmu")}
        conn.close()
        assert titles == {"Die Hard", "Big"}

    def test_view_survives_page_id_drift(self, db, source):
        """'Big' has current page id 38444154 but the corpus says 168597. The
        view must still link it — a direct page-id join would not."""
        load_cmu(db, source)
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT cmu_page_id, cmu_name FROM v_movie_cmu "
                           "WHERE title = 'Big'").fetchone()
        naive = conn.execute(
            "SELECT COUNT(*) FROM curated_movies m JOIN raw_cmu_movies c "
            "ON c.wikipedia_page_id = m.wikipedia_page_id").fetchone()[0]
        conn.close()
        assert row == (168597, "Big")
        assert naive == 1, "the naive page-id join should drop one film"

    def test_missing_summary_is_null_not_dropped(self, db, source):
        load_cmu(db, source)
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT plot_summary_wiki_raw, "
                           "plot_summary_wiki_raw_words "
                           "FROM v_movie_cmu WHERE title = 'Big'").fetchone()
        conn.close()
        assert row == (None, None), "LEFT JOIN must keep the film"

    def test_summary_text_round_trips(self, db, source):
        load_cmu(db, source)
        conn = sqlite3.connect(db)
        text = conn.execute("SELECT plot_summary_wiki_raw FROM v_movie_cmu "
                            "WHERE title = 'Die Hard'").fetchone()[0]
        conn.close()
        assert text.startswith("NYPD officer John McClane")


class TestGuards:
    def test_missing_source_files_exit(self, db, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        with pytest.raises(SystemExit):
            load_cmu(db, empty)

    def test_header_mismatch_exits(self, db, source):
        (source / "movies.tsv").write_text(
            "page_id\tfb\tname\n1\t/m/x\tNope\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            load_cmu(db, source)

    def test_summary_header_mismatch_exits(self, db, source):
        (source / "plot_summaries.tsv").write_text(
            "id\ttext\n97646\thello\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            load_cmu(db, source)

    def test_runs_without_manifest(self, db, source):
        (source / "manifest.json").unlink()
        movies, *_ = load_cmu(db, source)
        assert movies == 2
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT source_url, manifest_json FROM "
                           "raw_cmu_loads").fetchone()
        conn.close()
        assert row == (None, None)
