"""
Tests for step 17 (the curated category tables), the app's loader, and the
Categories section and dossier block that read them.

The rules that matter most:
  * an episode is placed by date window AND title, never by either alone, and
    anything else is an override or stays unmapped;
  * several rewatchvault episodes may share one airing (Boogie Nights is two
    pages' worth of episodes on the site and one row in the list);
  * a category id comes from the slug, else from a banner that means exactly
    one id; aliases fold duplicates, and a chain of aliases is refused;
  * the build is a rebuild: running it twice changes nothing.

Unit tests use the invented fixture page from test_categories.py. The app
tests read the real database and are skipped where it hasn't been built.
"""

import sqlite3
import zlib
from pathlib import Path

import pytest

from rewatchables import rewatchvault as rv
from rewatchables.pipeline import s16_load_categories as s16
from rewatchables.pipeline import s17_build_categories as s17
from conftest import goto
from test_categories import PAGE

ROOT = Path(__file__).resolve().parent.parent


def _airing(number, when, title, movie_id=None):
    return {"episode_movie_id": f"em-{number}", "movie_id": movie_id or f"m-{number}",
            "episode_number": number, "episode_date": when, "episode_title": title,
            "movie_title": title}


class TestTitles:
    def test_alike(self):
        assert s17.titles_agree("Ocean's 11", "Oceans 11")
        assert s17.titles_agree("Love & Basketball", "Love and Basketball")

    def test_containment_needs_four_characters(self):
        assert s17.titles_agree("Boogie Nights", "Boogie Nights (Part 1 and 2)")
        assert not s17.titles_agree("F1", "F1 Racing Special")

    def test_different(self):
        assert not s17.titles_agree("Heat", "The Exorcist")


class TestMapEpisodes:
    AIRINGS = [_airing(170, "2020-10-27", "Rocky IV"),
               _airing(171, "2020-10-29", "The Exorcist"),
               _airing(275, "2022-09-27", "Boogie Nights (Part 1 and 2)"),
               _airing(1, "2015-12-22", "Heat"),
               _airing(112, "2019-12-20", "Dunkirk")]

    def _map(self, rv_episodes, overrides=None):
        return {r["rv_episode_slug"]: r
                for r in s17.map_episodes(rv_episodes, self.AIRINGS, overrides or {})}

    def test_a_day_late_with_the_title_maps(self):
        """rewatchvault usually dates an episode a day after the list does."""
        row = self._map({"rocky-iv": ("2020-10-28", "Rocky IV")})["rocky-iv"]
        assert (row["match_rule"], row["episode_number"], row["day_offset"]) == ("date_title", 170, -1)

    def test_the_title_picks_between_neighbours(self):
        """The Exorcist aired two days after Rocky IV: inside the window."""
        assert self._map({"rocky-iv": ("2020-10-27", "Rocky IV")})["rocky-iv"]["episode_number"] == 170

    def test_two_rewatchvault_episodes_can_share_one_airing(self):
        rows = self._map({"boogie-nights-part-1": ("2022-09-27", "Boogie Nights"),
                          "boogie-nights-part-2": ("2022-09-27", "Boogie Nights")})
        assert {r["episode_number"] for r in rows.values()} == {275}

    def test_outside_the_window_is_unmapped_not_guessed(self):
        """Dunkirk: rewatchvault 2019-12-30, the list 2019-12-20."""
        row = self._map({"dunkirk": ("2019-12-30", "Dunkirk")})["dunkirk"]
        assert row["match_rule"] == "unmapped" and row["movie_id"] is None

    def test_the_date_alone_is_not_enough(self):
        row = self._map({"mystery": ("2020-10-27", "Some Other Film")})["mystery"]
        assert row["match_rule"] == "unmapped"

    def test_an_override_places_a_placeholder_date(self):
        rows = self._map({"heat-2017": ("2017-08-07", "Heat")},
                         {"heat-2017": (1, "2015-12-22", "placeholder")})
        assert (rows["heat-2017"]["match_rule"], rows["heat-2017"]["episode_number"]) == ("override", 1)

    def test_an_override_to_nowhere_is_reported(self):
        rows = self._map({"heat-2017": ("2017-08-07", "Heat")},
                         {"heat-2017": (99, "2015-12-22", "typo")})
        assert rows["heat-2017"]["match_rule"] == "unmapped"
        assert "no airing" in rows["heat-2017"]["note"]

    def test_a_stale_override_falls_back_to_the_rule(self):
        """Dunkirk is overridden to the list's 2019-12-20. Once the list is
        corrected to the feed's 2019-12-30, the override's airing is gone and
        the date rule links it instead -- nothing goes unmapped."""
        airings = [_airing(112, "2019-12-30", "Dunkirk")]
        rows = {r["rv_episode_slug"]: r for r in s17.map_episodes(
            {"dunkirk": ("2019-12-30", "Dunkirk")}, airings,
            {"dunkirk": (112, "2019-12-20", "list date")})}
        row = rows["dunkirk"]
        assert (row["match_rule"], row["episode_number"]) == ("date_title", 112)
        assert "no airing" in row["note"]

    def test_the_corrected_episodes_need_no_override(self):
        """Dunkirk and Fast Five were overridden until the episode list took
        the podcast feed's dates (2026-10-13); the rule places them now."""
        overrides = s17.read_overrides()
        assert "dunkirk" not in overrides and "fast-five" not in overrides

    def test_the_tracked_overrides_file_reads(self):
        overrides = s17.read_overrides()
        assert overrides["ocean-s-11"][:2] == (34, "2018-06-07")


class TestCategories:
    def test_aliases_fold_duplicates(self):
        aliases = s17.read_aliases()
        assert aliases["dion"] == "heat-check" and aliases["casting"] == "recasting"
        assert aliases["belated-quote"] == "best-quote"
        assert aliases["milking-moment"] == "toe-to-toe"
        # The -proposal ids are talk about a category, not awards (report 031).
        assert not any(a.endswith("-proposal") for a in aliases)
        assert len(aliases) == 14

    def test_a_chain_of_aliases_is_refused(self, tmp_path):
        path = tmp_path / "a.csv"
        path.write_text("alias_slug,canonical_slug,note\na,b,\nb,c,\n", encoding="utf-8")
        with pytest.raises(SystemExit):
            s17.read_aliases(path)

    def test_a_banner_with_one_id_places_an_opaque_slug(self):
        by_banner = s17.banner_categories([("ep-apex-1", "ep", "Apex Mountain")], {})
        page = {"category_slug": None, "banner": "Apex Mountain"}
        assert s17.resolve_category(page, {}, by_banner) == ("apex", "banner")

    def test_a_banner_seen_nowhere_else_becomes_its_own_category(self):
        page = {"category_slug": None, "banner": "Private Hudson Game Over Man category"}
        assert s17.resolve_category(page, {}, {}) == (
            "private-hudson-game-over-man-category", "banner")

    def test_a_banner_with_two_ids_is_left_unplaced(self):
        by_banner = s17.banner_categories([("ep-apex-1", "ep", "Apex Mountain"),
                                           ("ep-apex-wrapper-2", "ep", "Apex Mountain")], {})
        page = {"category_slug": None, "banner": "Apex Mountain"}
        assert s17.resolve_category(page, {}, by_banner) == (None, "none")

    def test_an_alias_applies_to_slug_and_banner_alike(self):
        aliases = {"dion": "heat-check"}
        by_banner = s17.banner_categories([("ep-dion-1", "ep", "Dion Award"),
                                           ("ep-heat-check-2", "ep", "Dion Award")], aliases)
        assert by_banner["Dion Award"] == {"heat-check"}
        assert s17.resolve_category({"category_slug": "dion", "banner": "x"}, aliases, {}) == (
            "heat-check", "slug")


@pytest.fixture
def built(tmp_path):
    """A database with one airing, the fixture page stored, and step 17 run."""
    conn = s16.connect(tmp_path / "t.db")
    conn.executescript((ROOT / "sql/schemas/curated_zone.sql").read_text(encoding="utf-8"))
    conn.execute("INSERT INTO curated_movies (movie_id, title) VALUES ('m-1', 'Made Up Film')")
    conn.execute("""INSERT INTO curated_episode_movies
                    (episode_movie_id, staging_episode_id, movie_id, episode_number,
                     episode_date, episode_title, mention_order)
                    VALUES ('em-1', 's-1', 'm-1', 300, '2024-03-04', 'Made Up Film', 1)""")
    load = s16.start_load(conn, "web", "pilot", "x", "y", 1, ["made-up-film-apex-7"])
    art = rv.article_html(PAGE)
    s16.store(conn, "raw_category_pages", load, "made-up-film-apex-7", s16._sha(art),
              {"url": "u", "http_status": 200, "article_html": zlib.compress(art.encode())})
    conn.commit()
    summary = s17.build(conn, tmp_path / "none.csv", tmp_path / "none.csv")
    yield conn, summary
    conn.close()


class TestBuild:
    def test_the_entry_is_placed_and_counted(self, built):
        conn, summary = built
        assert (summary["entries"], summary["bullets"], summary["picks"]) == (1, 3, 2)
        assert summary["unmapped"] == []
        row = conn.execute("""SELECT movie_id, episode_number, air_date, category_slug,
                                     answer, source_url FROM curated_category_entries""").fetchone()
        # The episode list's date wins over rewatchvault's, which runs a day late.
        assert row == ("m-1", 300, "2024-03-04", "apex", "The invented answer, by Pat Example",
                       "https://rewatchvault.com/archive/discussions/made-up-film-apex-7")

    def test_every_link_is_kept_with_its_place(self, built):
        conn, _ = built
        rows = conn.execute("""SELECT location, position, kind, name
                               FROM curated_category_mentions
                               ORDER BY location, position, start""").fetchall()
        assert ("answer", 0, "person", "Pat Example") in rows
        assert ("bullet", 1, "movie", "Other Film") in rows
        assert ("pick", 1, "person", "Lee Sample") in rows

    def test_offsets_point_at_names_in_the_stored_text(self, built):
        conn, _ = built
        for text, start, end, name in conn.execute(
                """SELECT b.text, m.start, m."end", m.name FROM curated_category_mentions m
                   JOIN curated_category_bullets b
                     ON b.discussion_slug = m.discussion_slug AND b.position = m.position
                   WHERE m.location = 'bullet'"""):
            assert text[start:end] == name

    def test_the_category_row(self, built):
        conn, _ = built
        assert conn.execute("SELECT category_slug, family, display_name, entries "
                            "FROM curated_categories").fetchall() == [
            ("apex", "standing", "Apex Mountain", 1)]

    def test_a_rebuild_changes_nothing(self, built, tmp_path):
        conn, _ = built
        before = [conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall() for t in s17.TABLES]
        s17.build(conn, tmp_path / "none.csv", tmp_path / "none.csv")
        after = [conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall() for t in s17.TABLES]
        assert before == after

    def test_a_category_with_no_icon_is_a_one_off(self, tmp_path):
        """Aliens' c8 has no icon; its own-banner category is a one-off."""
        conn = s16.connect(tmp_path / "noicon.db")
        conn.executescript((ROOT / "sql/schemas/curated_zone.sql").read_text(encoding="utf-8"))
        html = PAGE.replace('<img class="archive-icon" src="/assets/category-awards/apex-0a1b2c3d.svg"/>', "")
        load = s16.start_load(conn, "web", "7", "x", "y", 1, ["made-up-film-apex-7"])
        art = rv.article_html(html)
        s16.store(conn, "raw_category_pages", load, "made-up-film-apex-7", s16._sha(art),
                  {"url": "u", "http_status": 200, "article_html": zlib.compress(art.encode())})
        s17.build(conn, tmp_path / "none.csv", tmp_path / "none.csv")
        assert conn.execute("SELECT family FROM curated_categories").fetchone() == ("one_off",)
        conn.close()

    def test_no_pages_builds_empty_tables(self, tmp_path):
        conn = sqlite3.connect(tmp_path / "empty.db")
        conn.executescript((ROOT / "sql/schemas/curated_zone.sql").read_text(encoding="utf-8"))
        summary = s17.build(conn, tmp_path / "none.csv", tmp_path / "none.csv")
        assert summary["entries"] == 0
        conn.close()


class TestLoader:
    def test_a_database_without_the_tables_loads_empty(self, tmp_path, monkeypatch):
        from rewatchables.app import data
        path = tmp_path / "old.db"
        sqlite3.connect(path).close()
        monkeypatch.setattr(data, "DB_PATH", path)
        data.load_categories.clear()
        cats = data.load_categories("old")
        assert cats.entries.empty and cats.coverage["complete"] is False
        data.load_categories.clear()

    def test_coverage_counts_the_episodes_still_to_come(self, built, tmp_path, monkeypatch):
        from rewatchables.app import data
        conn, _ = built
        wb = s16.start_load(conn, "workbook", None, "f", "h", 2)
        for slug, ep in [("made-up-film-apex-7", "made-up-film"), ("next-film-apex-1", "next-film")]:
            s16.store(conn, "raw_category_workbook_rows", wb, slug, slug,
                      {"source_file": "f", "source_row_number": 2, "episode_slug": ep,
                       "air_date": "2024-03-05", "payload": zlib.compress(b"[]")})
        conn.commit()
        monkeypatch.setattr(data, "DB_PATH", tmp_path / "t.db")
        data.load_categories.clear()
        cov = data.load_categories("built").coverage
        data.load_categories.clear()
        assert (cov["episodes_covered"], cov["episodes_known"], cov["complete"]) == (1, 2, False)


# ── The app, on the real database ─────────────────────────────────────────────

DB_PATH = ROOT / "rewatchables.db"


def _has_entries():
    if not DB_PATH.exists():
        return False
    conn = sqlite3.connect(DB_PATH)
    try:
        return conn.execute("SELECT COUNT(*) FROM curated_category_entries").fetchone()[0] > 0
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


with_entries = pytest.mark.skipif(not _has_entries(),
                                  reason="no category entries in rewatchables.db yet")


@pytest.fixture(scope="module")
def at_categories():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
    return goto(at, "Categories")


def _markdown(at):
    return " ".join(m.value for m in at.markdown)


@with_entries
class TestSection:
    def test_it_renders(self, at_categories):
        assert not at_categories.exception

    def test_it_says_how_much_it_covers_until_it_covers_everything(self, at_categories):
        from rewatchables.app import data
        complete = data.load_categories(DB_PATH.stat().st_mtime).coverage["complete"]
        assert ("Partial data." in _markdown(at_categories)) is (not complete)

    def test_entries_carry_their_source(self, at_categories):
        text = _markdown(at_categories)
        assert "rewatchvault.com/archive/discussions/" in text
        assert "an independent archive of The Rewatchables" in text

    def test_the_category_view_lists_answers(self, at_categories):
        at = at_categories.radio(key="flt_cat_view").set_value("By category").run()
        assert not at.exception
        assert len(at.dataframe) == 1

    def test_the_discussions_open_under_the_table(self, at_categories):
        at = at_categories.radio(key="flt_cat_view").set_value("By category").run()
        at = at.toggle(key="flt_cat_read").set_value(True).run()
        assert not at.exception
        assert len(at.expander) >= 1

    def test_one_category_of_each_family_renders(self, at_categories):
        """Plus the uncategorised bucket, when there is one."""
        conn = sqlite3.connect(DB_PATH)
        picks = [r[0] for r in conn.execute(
            "SELECT MIN(category_slug) FROM curated_categories GROUP BY family")]
        if conn.execute("SELECT COUNT(*) FROM curated_category_entries "
                        "WHERE category_slug IS NULL").fetchone()[0]:
            picks.append("__none__")
        conn.close()
        at = at_categories.radio(key="flt_cat_view").set_value("By category").run()
        for slug in picks:
            at = at.selectbox(key="flt_cat_cat").set_value(slug).run()
            assert not at.exception, slug
            assert len(at.dataframe) == 1, slug


@with_entries
def test_the_dossier_shows_a_films_entries():
    from streamlit.testing.v1 import AppTest
    conn = sqlite3.connect(DB_PATH)
    movie_id = conn.execute("SELECT movie_id FROM curated_category_entries "
                            "WHERE movie_id IS NOT NULL LIMIT 1").fetchone()[0]
    conn.close()
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    at.session_state["dt_movie"] = movie_id
    at.run()
    assert not at.exception
    assert any("In the categories" in m.value for m in at.markdown)


def test_the_coverage_note_reads_as_a_sentence():
    """html() joins lines with no space; a wrapped note read '473episodes'."""
    from rewatchables.app.category_cards import coverage_note
    note = coverage_note({"episodes_covered": 10, "episodes_known": 473, "entries": 211,
                          "complete": False})
    assert "10 of 473 episodes, 211 entries so far. Counts here cover only these episodes;" in note
    assert coverage_note({"complete": True}) == ""


# ── Phase 4: totals ───────────────────────────────────────────────────────────

def _cats(rows):
    import pandas as pd
    return pd.DataFrame(rows, columns=["category_slug", "family", "display_name", "entries",
                                       "first_aired", "last_aired"])


def _mention(slug, name, d, location="answer", kind="person"):
    return {"discussion_slug": d, "location": location, "position": 0, "start": 0,
            "end": len(name), "kind": kind, "slug": slug, "name": name}


class TestTotals:
    def test_lifespans_keep_recurring_categories_only(self):
        from rewatchables.app.sections import categories as sec
        spans = sec.lifespans(_cats([
            ("apex", "standing", "Apex Mountain", 480, "2016-12-23", "2026-10-05"),
            ("romo", "segment", "Tony Romo", 46, "2024-02-06", "2025-01-06"),
            ("remake-proposal", "standing", "Remake", 1, "2022-08-01", "2022-08-01"),
            ("blake", "one_off", "Blake Lively Story Time", 3, "2019-08-02", "2019-08-02"),
            ("rushmore", "segment", "Mount Rushmore for Butlers", 1, "2023-05-16", "2023-05-16"),
        ]), "2026-10-05")
        assert spans["category_slug"].tolist() == ["apex", "romo"]
        assert spans.set_index("category_slug")["running"].to_dict() == {"apex": True, "romo": False}

    def test_axis_labels_are_short_and_distinct(self):
        from rewatchables.app.sections import categories as sec
        assert sec.short_label("The Dion Waiters Award for Best Heat Check Performance") ==             "Dion Waiters Award for Best…"
        assert sec.short_label("Apex Mountain") == "Apex Mountain"
        spans = sec.lifespans(_cats([
            ("a", "standing", "The Stephen A. Smith Hottest Take Award One", 5, "2018-01-01", "2026-10-05"),
            ("b", "standing", "The Stephen A. Smith Hottest Take Award Two", 5, "2019-01-01", "2026-10-05"),
        ]), "2026-10-05")
        fig = sec.lifespan_figure(spans)
        assert len(set(y for y in fig.data[0].y if y)) == 2

    def test_the_fullest_name_is_shown(self):
        import pandas as pd
        from rewatchables.app.sections import categories as sec
        m = pd.DataFrame([_mention("film-person:p", "Pacino", "a"), _mention("film-person:p", "Pacino", "b"),
                          _mention("film-person:p", "Al Pacino", "c")])
        assert sec.display_names(m) == {"film-person:p": "Al Pacino"}

    def test_ranking_skips_hosts_namesakes_and_mislinked_words(self):
        import pandas as pd
        from rewatchables.app.sections import categories as sec
        entries = pd.DataFrame([
            {"discussion_slug": "d1", "rv_episode_slug": "e1", "category_slug": "winner", "banner": "Who Won the Movie?"},
            {"discussion_slug": "d2", "rv_episode_slug": "e2", "category_slug": "winner", "banner": "Who Won the Movie?"},
            {"discussion_slug": "d3", "rv_episode_slug": "e3", "category_slug": "ebert-review", "banner": "Roger Ebert's review"},
        ])
        mentions = pd.DataFrame([
            _mention("film-person:tc", "Tom Cruise", "d1"), _mention("film-person:tc", "Tom Cruise", "d2"),
            _mention("bill-simmons", "Bill Simmons", "d1"),          # a host
            _mention("film-person:re", "Roger Ebert", "d3"),         # his own segment
            _mention("film-person:co", "common", "d2"),              # a word, mislinked
            _mention("film-person:co", "Common", "d1"),
        ])
        ranked = sec.people_ranking(entries, mentions, {"answer"})
        assert ranked == [("Tom Cruise", 2, 2), ("Common", 1, 1)]

    def test_excluded_categories_are_left_out(self):
        import pandas as pd
        from rewatchables.app.sections import categories as sec
        entries = pd.DataFrame([{"discussion_slug": "d1", "rv_episode_slug": "e1",
                                 "category_slug": "cruise-hanks", "banner": "Cruise or Hanks?"}])
        mentions = pd.DataFrame([_mention("film-person:tc", "Tom Cruise", "d1")])
        assert sec.people_ranking(entries, mentions, {"answer"}, exclude={"cruise-hanks"}) == []


@with_entries
def test_the_totals_view_renders(at_categories):
    at = at_categories.radio(key="flt_cat_view").set_value("Totals").run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "How long each category has run" in text and "Who the categories name" in text
    assert "Tom Cruise" in text
    at = at.selectbox(key="flt_cat_people").set_value("winner").run()
    assert not at.exception
