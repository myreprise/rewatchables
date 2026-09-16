"""
per_database, the cache behind the charts a widget does not affect.

The sections trust two things about it: a chart is built once for a given
database however many reruns ask for it, and a rebuilt database builds it
again. Serving a chart from the wrong database would be a silent error, so
both are pinned here. (That caching changes nothing a visitor sees was checked
against the rendered app; see reports/progress/009.)
"""

from rewatchables.app import charts


def test_builds_once_per_key_and_database():
    calls = []

    def build():
        calls.append(1)
        return object()

    first = charts.per_database("test:once", 1.0, build)
    again = charts.per_database("test:once", 1.0, build)
    assert first is again
    assert len(calls) == 1


def test_a_rebuilt_database_builds_again():
    calls = []

    def build():
        calls.append(1)
        return len(calls)

    assert charts.per_database("test:stamp", 1.0, build) == 1
    assert charts.per_database("test:stamp", 2.0, build) == 2


def test_keys_do_not_collide():
    a = charts.per_database("test:a", 1.0, lambda: "a")
    b = charts.per_database("test:b", 1.0, lambda: "b")
    assert (a, b) == ("a", "b")
