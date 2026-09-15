"""HTTP for the pipeline's API steps: one retry policy, one redaction rule.

Steps 04, 08, 09 and 10 call TMDB; 10 and 12 call Wikimedia. Each used to carry
its own retry loop, and the loops disagreed: 04 retried only a dropped
connection, 09 and 10 retried every status but 404 -- a rejected API key
included -- and none honoured a 429's Retry-After.

The policy they share now: retry a timeout, a dropped connection, a 429 or a
5xx, up to three attempts in all, waiting 2 s and then 4 s. On a 429 the wait
is the server's Retry-After instead, capped at a minute. Any other status is an
answer, and is returned at once.

requests.get and time.sleep are looked up on every call rather than bound at
import, so a test that patches "requests.get" or "time.sleep" reaches through
this module.
"""

import logging
import time

import requests

logger = logging.getLogger(__name__)

ATTEMPTS = 3
BACKOFF = 2              # seconds; the wait before retry n is BACKOFF * n
MAX_RETRY_AFTER = 60     # seconds; a longer Retry-After is capped, not obeyed
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
TRANSIENT = (requests.Timeout, requests.ConnectionError)


class RetryableStatus(Exception):
    """A response worth asking again for: a 429 or a 5xx."""

    def __init__(self, response):
        super().__init__(f"HTTP {response.status_code}")
        self.response = response


def redact(text, secret):
    """`text` with `secret` masked.

    requests writes the whole URL, api_key and all, into its exception strings,
    and those strings reach the logs and api_call_log.
    """
    if text and secret:
        return str(text).replace(secret, "***")
    return text


def _wait(error, attempt, backoff):
    """Seconds to wait after `error` on attempt `attempt`, counted from 0.

    Any error carrying a 429 response counts: the RetryableStatus that get()
    raises, or the HTTPError a caller's own raise_for_status() raised (step 12).
    """
    response = getattr(error, "response", None)
    if getattr(response, "status_code", None) == 429:
        try:
            asked = float(response.headers.get("Retry-After"))
            return min(max(asked, 0.0), MAX_RETRY_AFTER)
        except (TypeError, ValueError):
            pass  # absent, or given as an HTTP date: use the backoff
    return backoff * (attempt + 1)


def call_with_retries(fn, *, retry_on=TRANSIENT, attempts=ATTEMPTS,
                      backoff=BACKOFF, what="request", secret=None):
    """Return fn(), calling it again while it raises one of `retry_on`.

    At most `attempts` calls. The last failure is re-raised; an exception not
    in `retry_on` propagates from the first call.
    """
    attempts = max(1, attempts)
    for attempt in range(attempts):
        try:
            return fn()
        except retry_on as e:
            if attempt == attempts - 1:
                raise
            wait = _wait(e, attempt, backoff)
            logger.warning(f"{what}: {redact(str(e), secret)} "
                           f"(attempt {attempt + 1}/{attempts}); "
                           f"retrying in {wait:g}s")
            time.sleep(wait)


def get(url, *, what="request", secret=None, session=None,
        attempts=ATTEMPTS, backoff=BACKOFF, **kwargs):
    """GET `url` under the retry policy and return the final response.

    A 4xx other than 429 comes back at once: whether a 404 is an answer or an
    error is the caller's decision. If every attempt meets a 429 or a 5xx, the
    last such response is returned. If every attempt fails in transport, the
    last error is raised. `kwargs` (params, headers, timeout) go to requests.
    """
    def attempt():
        r = (session if session is not None else requests).get(url, **kwargs)
        if r.status_code in RETRY_STATUSES:
            raise RetryableStatus(r)
        return r

    try:
        return call_with_retries(
            attempt, retry_on=TRANSIENT + (RetryableStatus,),
            attempts=attempts, backoff=backoff, what=what, secret=secret)
    except RetryableStatus as e:
        return e.response
