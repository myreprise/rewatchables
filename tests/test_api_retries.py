"""
The API steps under the shared retry policy in rewatchables.http.

test_http.py pins the policy itself. This pins that each step actually uses
it -- a dropped connection is asked again, a rejected key is not -- and that
the API key never reaches a log line or api_call_log.

No network: requests.get and time.sleep are patched throughout.
"""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from rewatchables.pipeline import s04_enrich
from rewatchables.pipeline import s08_apply_review
from rewatchables.pipeline import s09_enrich_metadata
from rewatchables.pipeline import s10_resolve_external_ids
from rewatchables.pipeline import s12_enrich_plot_summaries

SCHEMA_DIR = Path(__file__).parent.parent / "sql" / "schemas"
KEY = "SEKRIT-KEY"


def _resp(payload=None, status=200, headers=None):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = payload if payload is not None else {}
    r.headers = headers or {}
    return r


def _dropped():
    # requests puts the whole URL, key included, into the exception string.
    return requests.ConnectionError(
        f"GET https://api.themoviedb.org/3/movie/1?api_key={KEY} failed")


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    for mod in (s04_enrich, s08_apply_review, s09_enrich_metadata,
                s10_resolve_external_ids):
        monkeypatch.setattr(mod, "TMDB_API_KEY", KEY)


@pytest.fixture
def no_wait():
    with patch("time.sleep") as sleep:
        yield sleep


class TestStep04Search:
    @pytest.fixture
    def db(self, tmp_path):
        path = tmp_path / "t.db"
        conn = sqlite3.connect(path)
        for name in ("raw_zone.sql", "staging_zone.sql", "curated_zone.sql"):
            conn.executescript((SCHEMA_DIR / name).read_text(encoding="utf-8"))
        conn.close()
        return str(path)

    def _logged(self, db):
        conn = sqlite3.connect(db)
        rows = conn.execute(
            "SELECT response_status_code, error_message FROM api_call_log").fetchall()
        conn.close()
        return rows

    def test_a_dropped_connection_is_retried(self, db, no_wait):
        ok = _resp({"results": [{"id": 949, "title": "Heat",
                                 "release_date": "1995-12-15"}]})
        with patch("requests.get", side_effect=[_dropped(), ok]) as g:
            candidates = s04_enrich.search_tmdb(db, "Heat", 1995)
        assert g.call_count == 2
        assert candidates[0]["id"] == 949
        assert self._logged(db) == [(200, None)]

    def test_a_rejected_key_is_not_retried(self, db, no_wait):
        with patch("requests.get", return_value=_resp(status=401)) as g:
            assert s04_enrich.search_tmdb(db, "Heat", 1995) is None
        assert g.call_count == 1
        assert self._logged(db) == [(401, "HTTP 401")]

    def test_giving_up_is_logged_without_the_key(self, db, no_wait, caplog):
        with patch("requests.get", side_effect=_dropped()) as g:
            assert s04_enrich.search_tmdb(db, "Heat", 1995) is None
        assert g.call_count == 3
        (status, error), = self._logged(db)
        assert status is None and "api_key=***" in error
        assert KEY not in caplog.text


class TestStep08Details:
    def test_giving_up_returns_none_without_the_key(self, no_wait, caplog):
        with patch("requests.get", side_effect=_dropped()) as g:
            assert s08_apply_review.get_movie_details(949) is None
        assert g.call_count == 3
        assert KEY not in caplog.text


class TestStep09Details:
    def test_a_server_error_is_retried(self, no_wait):
        with patch("requests.get",
                   side_effect=[_resp(status=503), _resp({"id": 949})]) as g:
            assert s09_enrich_metadata.fetch_details(949) == {"id": 949}
        assert g.call_count == 2

    def test_a_rejected_key_is_not_retried(self, no_wait):
        """It used to be asked three times, six seconds apart."""
        with patch("requests.get", return_value=_resp(status=401)) as g:
            assert s09_enrich_metadata.fetch_details(949) is None
        assert g.call_count == 1


class TestStep10:
    def test_a_dropped_connection_is_retried(self, no_wait):
        ok = _resp({"wikidata_id": "Q1", "imdb_id": "tt1"})
        with patch("requests.get", side_effect=[_dropped(), ok]) as g:
            assert s10_resolve_external_ids.fetch_external_ids(1) == {
                "wikidata_qid": "Q1", "imdb_id": "tt1"}
        assert g.call_count == 2

    def test_a_wikidata_batch_survives_a_timeout(self, no_wait):
        """A batch used to degrade to empty on the first hiccup."""
        payload = {"entities": {"Q1": {"claims": {},
                                       "sitelinks": {"enwiki": {"title": "Heat"}}}}}
        with patch("requests.get",
                   side_effect=[requests.Timeout("slow"), _resp(payload)]):
            out = s10_resolve_external_ids.fetch_wikidata(["Q1"])
        assert out["Q1"]["enwiki_title"] == "Heat"


class TestStep12Fetch:
    def test_an_api_error_inside_a_200_is_retried(self, no_wait):
        calls = []

        def fetch(page_id):
            calls.append(page_id)
            if len(calls) < 2:
                raise RuntimeError("maxlag: server lagged")
            return (1, "Big", "text")

        assert s12_enrich_plot_summaries._fetch_with_retries(fetch, 7) == (1, "Big", "text")
        assert calls == [7, 7]

    def test_a_429_waits_as_long_as_wikipedia_asks(self, no_wait):
        """raise_for_status turns a 429 into an HTTPError; its Retry-After
        still sets the wait."""
        calls = []

        def fetch(page_id):
            calls.append(page_id)
            if len(calls) == 1:
                raise requests.HTTPError(
                    "429", response=_resp(status=429, headers={"Retry-After": "5"}))
            return (1, "Big", "text")

        s12_enrich_plot_summaries._fetch_with_retries(fetch, 7)
        assert no_wait.call_args.args[0] == 5
