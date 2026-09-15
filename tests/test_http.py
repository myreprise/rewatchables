"""
The pipeline's shared retry policy, in rewatchables.http.

No network: requests.get and time.sleep are patched, the way every API test in
this suite does it -- which is also a check that the module looks both up at
call time, so those patches keep reaching through it.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from rewatchables import http


def _response(status, headers=None):
    r = MagicMock()
    r.status_code = status
    r.headers = headers or {}
    return r


class TestGet:
    def test_success_is_returned_without_a_wait(self):
        ok = _response(200)
        with patch("requests.get", return_value=ok) as g, \
             patch("time.sleep") as sleep:
            assert http.get("u", timeout=5) is ok
        assert g.call_count == 1
        sleep.assert_not_called()

    def test_arguments_reach_requests(self):
        with patch("requests.get", return_value=_response(200)) as g, \
             patch("time.sleep"):
            http.get("u", params={"q": "Heat"}, headers={"A": "b"}, timeout=7)
        g.assert_called_once_with("u", params={"q": "Heat"},
                                  headers={"A": "b"}, timeout=7)

    def test_a_timeout_is_retried_with_a_growing_wait(self):
        ok = _response(200)
        with patch("requests.get",
                   side_effect=[requests.Timeout("t"), requests.ConnectionError("c"), ok]) as g, \
             patch("time.sleep") as sleep:
            assert http.get("u") is ok
        assert g.call_count == 3
        assert [c.args[0] for c in sleep.call_args_list] == [2, 4]

    def test_transport_failure_on_every_attempt_raises_the_last(self):
        with patch("requests.get", side_effect=requests.Timeout("gone")) as g, \
             patch("time.sleep") as sleep:
            with pytest.raises(requests.Timeout):
                http.get("u")
        assert g.call_count == http.ATTEMPTS
        assert sleep.call_count == http.ATTEMPTS - 1   # no wait after the last

    def test_a_server_error_is_retried(self):
        ok = _response(200)
        with patch("requests.get", side_effect=[_response(503), ok]) as g, \
             patch("time.sleep"):
            assert http.get("u") is ok
        assert g.call_count == 2

    def test_a_persistent_server_error_returns_the_last_response(self):
        last = _response(502)
        with patch("requests.get", side_effect=[_response(500), _response(503), last]), \
             patch("time.sleep"):
            assert http.get("u") is last

    @pytest.mark.parametrize("status", [400, 401, 403, 404])
    def test_a_client_error_is_an_answer_not_a_retry(self, status):
        """401 is the case that matters: a bad key must not be asked three times."""
        answer = _response(status)
        with patch("requests.get", return_value=answer) as g, \
             patch("time.sleep") as sleep:
            assert http.get("u") is answer
        assert g.call_count == 1
        sleep.assert_not_called()

    def test_an_unexpected_exception_is_not_retried(self):
        with patch("requests.get", side_effect=ValueError("bug")) as g, \
             patch("time.sleep"):
            with pytest.raises(ValueError):
                http.get("u")
        assert g.call_count == 1

    def test_a_session_is_used_when_given(self):
        session = MagicMock()
        session.get.return_value = _response(200)
        with patch("requests.get") as g, patch("time.sleep"):
            http.get("u", session=session, timeout=3)
        session.get.assert_called_once_with("u", timeout=3)
        g.assert_not_called()


class TestRetryAfter:
    def _wait_for(self, headers):
        ok = _response(200)
        with patch("requests.get", side_effect=[_response(429, headers), ok]), \
             patch("time.sleep") as sleep:
            assert http.get("u") is ok
        return sleep.call_args.args[0]

    def test_a_429_waits_as_long_as_the_server_asks(self):
        assert self._wait_for({"Retry-After": "7"}) == 7

    def test_an_excessive_retry_after_is_capped(self):
        assert self._wait_for({"Retry-After": "3600"}) == http.MAX_RETRY_AFTER

    @pytest.mark.parametrize("headers", [{}, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}])
    def test_without_a_usable_retry_after_the_backoff_applies(self, headers):
        assert self._wait_for(headers) == http.BACKOFF


class TestCallWithRetries:
    def test_retries_what_it_is_told_to(self):
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise RuntimeError("api error")
            return "ok"

        with patch("time.sleep"):
            assert http.call_with_retries(flaky, retry_on=(Exception,)) == "ok"
        assert len(calls) == 3

    def test_the_backoff_base_is_the_callers(self):
        with patch("time.sleep") as sleep:
            with pytest.raises(RuntimeError):
                http.call_with_retries(lambda: (_ for _ in ()).throw(RuntimeError()),
                                       retry_on=(RuntimeError,), backoff=0.5)
        assert [c.args[0] for c in sleep.call_args_list] == [0.5, 1.0]

    def test_the_secret_never_reaches_the_log(self, caplog):
        def leaky():
            raise requests.ConnectionError("GET /movie/1?api_key=SEKRIT failed")

        with patch("time.sleep"), pytest.raises(requests.ConnectionError):
            http.call_with_retries(leaky, what="tmdb", secret="SEKRIT")
        assert "SEKRIT" not in caplog.text
        assert "api_key=***" in caplog.text


class TestRedact:
    def test_masks_the_secret(self):
        assert http.redact("key=abc&x=abc", "abc") == "key=***&x=***"

    @pytest.mark.parametrize("secret", [None, ""])
    def test_without_a_secret_the_text_is_unchanged(self, secret):
        assert http.redact("key=abc", secret) == "key=abc"

    def test_passes_none_through(self):
        assert http.redact(None, "abc") is None
