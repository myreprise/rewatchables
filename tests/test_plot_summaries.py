"""
Tests for 12_enrich_plot_summaries.py — cleaning CMU plot summaries, reading
live Wikipedia sections, and promoting the better of the two onto
curated_movies.

The cleaner is lossy by nature, so the tests lean on the cases where getting it
wrong destroys real narrative text rather than markup. No test reaches
Wikipedia; see the `offline` fixture.
"""

import sqlite3
import uuid
from pathlib import Path

import pytest
import requests

from rewatchables.pipeline import s12_enrich_plot_summaries as mod

clean = mod.clean_wiki_markup
enrich_plot_summaries = mod.enrich_plot_summaries
extract_sections = mod.extract_sections
choose_plot = mod.choose_plot
real_fetch_extract = mod.fetch_extract   # captured before `offline` patches it


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Keep every test off the network. Unless a test passes its own `fetch=`,
    each article reads as missing -- which leaves exactly the CMU-only
    behaviour the older tests below pin down."""
    monkeypatch.setattr(mod, "fetch_extract", lambda session, page_id: None)
    monkeypatch.setattr(mod, "FETCH_SLEEP", 0)
    monkeypatch.setattr(mod, "RETRY_SLEEP", 0)


class TestCleanMarkup:
    def test_removes_plot_template(self):
        assert clean("{{Plot}} Los Angeles detectives approach a scene.") == \
            "Los Angeles detectives approach a scene."

    def test_removes_cite_templates(self):
        assert clean("Before {{cite web}} after") == "Before after"

    def test_possessive_s_template_is_restored(self):
        """A generic template strip would turn 'Titanic{{'s}}' into 'Titanic'."""
        assert clean("the Titanic{{'s}} final moments") == \
            "the Titanic's final moments"

    def test_bare_possessive_template_is_restored(self):
        assert clean("the Falcon{{'}}s arrival") == "the Falcon's arrival"

    def test_unclosed_link_keeps_its_text(self):
        """The corpus has 90 '[[' and zero ']]'. Deleting to a closing bracket
        would swallow the remainder of the sentence."""
        assert clean("crew [[Kevin Gage perpetrate a heist") == \
            "crew Kevin Gage perpetrate a heist"

    def test_prose_after_ref_survives(self):
        """Regression: an earlier regex consumed to the next brace and ate the
        narrative following a citation."""
        out = clean("In 1979,<ref name Cowie | first The Godfather Book}} "
                    "the film premiered")
        assert "the film premiered" in out
        assert "<ref" not in out

    def test_html_entities_unescaped(self):
        assert clean("A&mdash;B and&nbsp;C") == "A—B and C"

    def test_collapses_double_spacing(self):
        assert clean("Waters  and his partner  Ria") == \
            "Waters and his partner Ria"

    def test_fixes_space_before_punctuation(self):
        assert clean("word , punct .") == "word, punct."

    def test_tightens_parens(self):
        assert clean("text ( inner ) end") == "text (inner) end"

    def test_spaced_ndash_template(self):
        assert clean("a{{spaced ndash}}b") == "a - b"

    def test_strips_stray_braces(self):
        assert clean("text {{ unbalanced end") == "text unbalanced end"

    def test_empty_and_none(self):
        assert clean("") == ""
        assert clean(None) == ""

    def test_plain_text_is_untouched(self):
        s = "Career criminal Neil McCauley leads a crew of professionals."
        assert clean(s) == s

    def test_does_not_invent_text(self):
        """Cleaning may only remove; word count must never rise except where a
        template legitimately expands to a separator."""
        s = "{{Plot}} A B C [[D E &mdash; F"
        assert len(clean(s).split()) <= len(s.split())

    def test_bare_urls_removed(self):
        assert clean("the film http://www.example.com/a.html premiered") == \
            "the film premiered"

    def test_leading_punctuation_stripped(self):
        """The Godfather Part II's summary began ': In 1901'."""
        assert clean(": In 1901 Corleone, Sicily") == "In 1901 Corleone, Sicily"

    def test_leading_quote_kept(self):
        assert clean('"Big" Josh wakes up') == '"Big" Josh wakes up'


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path):
    """One curated film linked to a CMU summary via freebase_id, with a
    deliberately drifted page id."""
    p = str(tmp_path / "test.db")
    conn = sqlite3.connect(p)
    schema_dir = Path(__file__).parent.parent / "sql" / "schemas"
    for fname in ["raw_zone.sql", "staging_zone.sql", "curated_zone.sql"]:
        conn.executescript((schema_dir / fname).read_text())
    conn.execute(
        "INSERT INTO curated_movies (movie_id, tmdb_id, title, year, "
        "freebase_id, wikipedia_page_id, plot_summary, total_episodes_featured, "
        "revisit_count, canonical_key_confidence) "
        "VALUES (?, 2280, 'Big', 1988, '/m/016ky6', 38444154, "
        "'A boy becomes an adult overnight.', 1, 0, 'high')",
        (str(uuid.uuid4()),))
    conn.execute(
        "INSERT INTO raw_cmu_movies (wikipedia_page_id, freebase_id, name) "
        "VALUES (168597, '/m/016ky6', 'Big')")
    conn.execute(
        "INSERT INTO raw_cmu_summaries (wikipedia_page_id, summary, word_count) "
        "VALUES (168597, '{{Plot}} Josh  makes a wish and the Zoltar{{''s}} "
        "machine grants it.', 12)")
    conn.commit()
    conn.close()
    return p


class TestEnrich:
    def test_fills_cleaned_columns(self, db):
        updated, filled = enrich_plot_summaries(db)
        assert (updated, filled) == (1, 1)
        conn = sqlite3.connect(db)
        text, words = conn.execute(
            "SELECT plot_summary_wiki, plot_summary_wiki_words "
            "FROM curated_movies WHERE tmdb_id = 2280").fetchone()
        conn.close()
        assert text == "Josh makes a wish and the Zoltar's machine grants it."
        assert words == 10

    def test_tmdb_summary_is_left_alone(self, db):
        enrich_plot_summaries(db)
        conn = sqlite3.connect(db)
        tmdb = conn.execute("SELECT plot_summary FROM curated_movies "
                            "WHERE tmdb_id = 2280").fetchone()[0]
        conn.close()
        assert tmdb == "A boy becomes an adult overnight."

    def test_raw_text_is_preserved(self, db):
        """Cleaning must stay reversible."""
        enrich_plot_summaries(db)
        conn = sqlite3.connect(db)
        raw = conn.execute("SELECT summary FROM raw_cmu_summaries").fetchone()[0]
        conn.close()
        assert "{{Plot}}" in raw

    def test_second_run_is_a_noop(self, db):
        enrich_plot_summaries(db)
        updated, filled = enrich_plot_summaries(db)
        assert (updated, filled) == (0, 1)

    def test_force_recleans(self, db):
        enrich_plot_summaries(db)
        updated, _ = enrich_plot_summaries(db, force=True)
        assert updated == 1

    def test_links_through_freebase_not_page_id(self, db):
        """curated.wikipedia_page_id is 38444154; the corpus says 168597. Only
        the freebase path connects them."""
        updated, _ = enrich_plot_summaries(db)
        assert updated == 1, "freebase join must survive page-id drift"

    def test_view_exposes_raw_column_names(self, db):
        enrich_plot_summaries(db)
        conn = sqlite3.connect(db)
        row = conn.execute("SELECT plot_summary_wiki_raw, "
                           "plot_summary_wiki_raw_words FROM v_movie_cmu").fetchone()
        conn.close()
        assert "{{Plot}}" in row[0], "the view serves RAW corpus text"

    def test_exits_without_cmu_tables(self, tmp_path):
        p = str(tmp_path / "bare.db")
        conn = sqlite3.connect(p)
        schema_dir = Path(__file__).parent.parent / "sql" / "schemas"
        conn.executescript((schema_dir / "curated_zone.sql").read_text())
        conn.commit()
        conn.close()
        with pytest.raises(SystemExit):
            enrich_plot_summaries(p)


# ---------------------------------------------------------------------------
# Live Wikipedia: reading sections out of a TextExtracts article
# ---------------------------------------------------------------------------

# The shape TextExtracts actually returns (explaintext, exsectionformat=wiki):
# headings on their own lines, and here a plot made only of subsections.
GODFATHER_II = (
    "The Godfather Part II is a 1974 American epic crime film.\n\n"
    "== Plot ==\n\n\n"
    "=== Vito ===\n"
    "In 1901, nine-year-old Vito Andolini escapes from Corleone.\n"
    "He is processed at Ellis Island.\n\n"
    "=== Michael ===\n"
    "In 1958, Michael holds meetings at his Lake Tahoe estate.\n\n\n"
    "== Cast ==\n"
    "Al Pacino as Michael Corleone\n"
)


class TestExtractSections:
    def test_plot_includes_its_subsections(self):
        """Regression: reading only the text before the first subsection gave
        The Godfather Part II an empty plot."""
        plot = extract_sections(GODFATHER_II)["plot_text"]
        assert "Vito Andolini" in plot and "Lake Tahoe" in plot

    def test_plot_stops_at_the_next_section(self):
        assert "Al Pacino" not in extract_sections(GODFATHER_II)["plot_text"]

    def test_lead_is_not_plot(self):
        assert "epic crime film" not in extract_sections(GODFATHER_II)["plot_text"]

    def test_subsection_headings_become_paragraphs(self):
        paras = extract_sections(GODFATHER_II)["plot_text"].split("\n\n")
        assert paras[0] == "Vito" and "Michael" in paras

    def test_lines_become_blank_line_paragraphs(self):
        """The app renders this as markdown, where one newline is no break."""
        assert "from Corleone.\n\nHe is processed" in \
            extract_sections(GODFATHER_II)["plot_text"]

    def test_synopsis_counts_as_plot(self):
        s = extract_sections("Lead.\n== Synopsis ==\nA heist goes wrong.\n")
        assert (s["plot_heading"], s["plot_text"]) == \
            ("Synopsis", "A heist goes wrong.")

    def test_article_without_a_plot(self):
        s = extract_sections("Lead.\n== Production ==\nShot in Toronto.\n")
        assert s["plot_text"] is None and s["plot_heading"] is None

    def test_empty_extract(self):
        assert set(extract_sections("").values()) == {None}

    def test_themes_are_kept_out_of_the_plot(self):
        s = extract_sections("== Plot ==\nChris visits.\n"
                             "== Themes and interpretations ==\n"
                             "A satire of liberal racism.\n")
        assert s["plot_text"] == "Chris visits."
        assert s["themes_heading"] == "Themes and interpretations"
        assert s["themes_text"] == "A satire of liberal racism."

    def test_theme_park_is_not_a_theme(self):
        """'Theme park attraction' is a real heading in this catalogue."""
        s = extract_sections("== Plot ==\nx\n"
                             "== Theme park attraction ==\nA ride opened.\n")
        assert s["themes_text"] is None

    def test_box_office_analysis_is_not_a_theme(self):
        """Both headings are real in this catalogue and match 'analysis'."""
        s = extract_sections("== Box office analysis ==\nIt opened at #1.\n"
                             "== Commercial analysis ==\nMerchandise sold.\n")
        assert s["themes_text"] is None

    def test_critical_analysis_is_a_theme(self):
        s = extract_sections("== Critical analysis ==\nA film about guilt.\n")
        assert s["themes_text"] == "A film about guilt."

    def test_nested_theme_sections_counted_once(self):
        s = extract_sections("== Themes ==\nGuilt.\n=== Symbolism ===\nOranges.\n")
        assert s["themes_heading"] == "Themes"
        assert s["themes_text"].count("Oranges.") == 1

    def test_theme_sections_in_different_places_are_joined(self):
        s = extract_sections("== Analysis ==\nA.\n== Reception ==\nGood.\n"
                             "=== Themes ===\nB.\n")
        assert s["themes_heading"] == "Analysis; Themes"
        assert "Good." not in s["themes_text"]


class TestChoosePlot:
    def test_longer_live_wins(self):
        assert choose_plot("a b", "a b c") == ("a b c", "wikipedia_live")

    def test_longer_cmu_wins(self):
        assert choose_plot("a b c", "a b") == ("a b c", "cmu_2012")

    def test_tie_goes_to_live(self):
        assert choose_plot("a b c", "x y z") == ("x y z", "wikipedia_live")

    def test_single_source(self):
        assert choose_plot(None, "x") == ("x", "wikipedia_live")
        assert choose_plot("x", None) == ("x", "cmu_2012")

    def test_neither(self):
        assert choose_plot(None, None) == (None, None)


class _Response:
    def __init__(self, payload, status=200):
        self.payload, self.status_code = payload, status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class _Session:
    def __init__(self, payload, status=200):
        self.response = _Response(payload, status)
        self.params = None

    def get(self, url, timeout=None, params=None):
        self.params = params
        return self.response


class TestFetchExtract:
    def test_reads_revision_title_and_text(self):
        session = _Session({"query": {"pages": [{
            "pageid": 48526729, "title": "Get Out",
            "revisions": [{"revid": 42}], "extract": "== Plot ==\nChris."}]}})
        assert real_fetch_extract(session, 48526729) == \
            (42, "Get Out", "== Plot ==\nChris.")
        assert session.params["pageids"] == 48526729
        assert session.params["explaintext"]

    def test_missing_page_is_none(self):
        session = _Session({"query": {"pages": [{"pageid": 1, "missing": True}]}})
        assert real_fetch_extract(session, 1) is None

    def test_api_error_raises(self):
        with pytest.raises(RuntimeError):
            real_fetch_extract(
                _Session({"error": {"code": "badvalue", "info": "bad"}}), 1)

    def test_http_error_raises(self):
        with pytest.raises(requests.HTTPError):
            real_fetch_extract(_Session({}, status=503), 1)


# ---------------------------------------------------------------------------
# Integration: best of both, and the fetch cache
# ---------------------------------------------------------------------------

BIG = 38444154   # Big's current page id; CMU's is 168597
LIVE_PLOT = ("Josh Baskin, a twelve-year-old boy, makes a wish at a Zoltar "
             "machine to be big and wakes up the next morning as a "
             "thirty-year-old man.")


def article(plot=None, themes=None):
    s = "Big is a 1988 film.\n"
    if plot:
        s += f"== Plot ==\n{plot}\n"
    if themes:
        s += f"== Themes ==\n{themes}\n"
    return s


def fetcher(articles, calls=None, revid=111):
    """A stand-in for Wikipedia: page id -> article text."""
    def fetch(page_id):
        if calls is not None:
            calls.append(page_id)
        if page_id not in articles:
            return None
        return revid, f"page {page_id}", articles[page_id]
    return fetch


def _row(db, title="Big"):
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM curated_movies WHERE title = ?",
                       (title,)).fetchone()
    conn.close()
    return row


def _add_film(db, title, page_id):
    conn = sqlite3.connect(db)
    conn.execute(
        "INSERT INTO curated_movies (movie_id, title, year, wikipedia_page_id, "
        "total_episodes_featured, revisit_count, canonical_key_confidence) "
        "VALUES (?, ?, 2017, ?, 1, 0, 'high')",
        (str(uuid.uuid4()), title, page_id))
    conn.commit()
    conn.close()


class TestBestOfBoth:
    def test_longer_live_plot_replaces_a_thin_cmu_one(self, db):
        enrich_plot_summaries(db, fetch=fetcher({BIG: article(LIVE_PLOT)}))
        row = _row(db)
        assert row["plot_summary_wiki"] == LIVE_PLOT
        assert row["plot_summary_wiki_source"] == "wikipedia_live"
        assert row["plot_summary_wiki_words"] == len(LIVE_PLOT.split())
        assert row["wikipedia_revid"] == 111

    def test_longer_cmu_plot_is_kept(self, db):
        enrich_plot_summaries(db, fetch=fetcher({BIG: article("Josh grows up.")}))
        row = _row(db)
        assert row["plot_summary_wiki_source"] == "cmu_2012"
        assert row["plot_summary_wiki"].startswith("Josh makes a wish")

    def test_the_losing_live_text_is_still_stored(self, db):
        enrich_plot_summaries(db, fetch=fetcher({BIG: article("Josh grows up.")}))
        conn = sqlite3.connect(db)
        stored = conn.execute(
            "SELECT plot_text, plot_words FROM raw_wiki_articles "
            "WHERE wikipedia_page_id = ?", (BIG,)).fetchone()
        conn.close()
        assert stored == ("Josh grows up.", 3)

    def test_live_fills_a_film_cmu_never_had(self, db):
        _add_film(db, "Get Out", 48526729)
        updated, filled = enrich_plot_summaries(db, fetch=fetcher(
            {48526729: article("Chris visits his girlfriend's family.")}))
        assert (updated, filled) == (2, 2)
        assert _row(db, "Get Out")["plot_summary_wiki_source"] == "wikipedia_live"

    def test_live_is_read_by_the_current_page_id(self, db):
        """Big's article was recreated after 2012; CMU's id would miss it."""
        calls = []
        enrich_plot_summaries(db, fetch=fetcher({}, calls))
        assert calls == [BIG]

    def test_themes_are_stored_apart_from_the_plot(self, db):
        enrich_plot_summaries(db, fetch=fetcher({BIG: article(
            LIVE_PLOT, themes="A fable about growing up too fast.")}))
        row = _row(db)
        assert row["themes_wiki"] == "A fable about growing up too fast."
        assert row["themes_wiki_heading"] == "Themes"
        assert row["themes_wiki_words"] == 7
        assert "fable" not in row["plot_summary_wiki"]

    def test_second_run_writes_nothing(self, db):
        fetch = fetcher({BIG: article(LIVE_PLOT)})
        enrich_plot_summaries(db, fetch=fetch)
        assert enrich_plot_summaries(db, fetch=fetch) == (0, 1)

    def test_adds_the_new_columns_to_an_older_database(self, db):
        if sqlite3.sqlite_version_info < (3, 35, 0):
            pytest.skip("needs ALTER TABLE ... DROP COLUMN")
        conn = sqlite3.connect(db)
        for col in ["plot_summary_wiki_source", "wikipedia_revid", "themes_wiki",
                    "themes_wiki_heading", "themes_wiki_words"]:
            conn.execute(f"ALTER TABLE curated_movies DROP COLUMN {col}")
        conn.commit()
        conn.close()
        enrich_plot_summaries(db, fetch=fetcher({BIG: article(LIVE_PLOT)}))
        assert _row(db)["plot_summary_wiki_source"] == "wikipedia_live"


class TestFetchCache:
    def test_each_article_is_fetched_once(self, db):
        calls = []
        fetch = fetcher({BIG: article(LIVE_PLOT)}, calls)
        enrich_plot_summaries(db, fetch=fetch)
        enrich_plot_summaries(db, fetch=fetch)
        assert calls == [BIG]

    def test_refresh_fetches_again(self, db):
        calls = []
        fetch = fetcher({BIG: article(LIVE_PLOT)}, calls)
        enrich_plot_summaries(db, fetch=fetch)
        enrich_plot_summaries(db, refresh=True, fetch=fetch)
        assert calls == [BIG, BIG]

    def test_an_article_without_a_plot_is_not_re_asked(self, db):
        calls = []
        fetch = fetcher({BIG: article()}, calls)
        enrich_plot_summaries(db, fetch=fetch)
        enrich_plot_summaries(db, fetch=fetch)
        assert calls == [BIG]
        assert _row(db)["plot_summary_wiki_source"] == "cmu_2012"

    def test_rebuild_refills_from_the_cache_without_the_network(self, db):
        """06_build_curated wipes curated_movies; putting these columns back
        must not need Wikipedia."""
        enrich_plot_summaries(db, fetch=fetcher(
            {BIG: article(LIVE_PLOT, themes="Growing up.")}))
        cols = ["plot_summary_wiki", "plot_summary_wiki_words",
                "plot_summary_wiki_source", "wikipedia_revid", "themes_wiki",
                "themes_wiki_heading", "themes_wiki_words"]
        before = {c: _row(db)[c] for c in cols}

        conn = sqlite3.connect(db)
        conn.execute("UPDATE curated_movies SET "
                     + ", ".join(f"{c} = NULL" for c in cols))
        conn.commit()
        conn.close()

        calls = []
        enrich_plot_summaries(db, fetch=fetcher({}, calls))
        assert calls == [], "a rebuild must not reach the network"
        assert {c: _row(db)[c] for c in cols} == before

    def test_a_failed_fetch_is_not_cached(self, db):
        calls = []

        def down(page_id):
            calls.append(page_id)
            raise ConnectionError("offline")

        enrich_plot_summaries(db, fetch=down)
        assert calls == [BIG] * mod.FETCH_ATTEMPTS
        assert _row(db)["plot_summary_wiki_source"] == "cmu_2012", \
            "CMU is still promoted while Wikipedia is unreachable"

        retry = []
        enrich_plot_summaries(db, fetch=fetcher({BIG: article(LIVE_PLOT)}, retry))
        assert retry == [BIG], "the failed film is asked again next run"
        assert _row(db)["plot_summary_wiki_source"] == "wikipedia_live"

    def test_an_outage_stops_fetching(self, db):
        for i in range(8):
            _add_film(db, f"Film {i}", 1000 + i)
        attempted = set()

        def down(page_id):
            attempted.add(page_id)
            raise ConnectionError("offline")

        _, filled = enrich_plot_summaries(db, fetch=down)
        assert len(attempted) == mod.MAX_CONSECUTIVE_FAILURES
        assert filled == 1, "the run still finishes with what it has"
