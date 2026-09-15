"""
Unit tests for candidate scoring in 04_enrich.py.
No database, no API calls.
"""


import pytest

from rewatchables.pipeline import s04_enrich as mod

score_candidate   = mod.score_candidate
strip_annotations = mod.strip_annotations
normalize_title   = mod.normalize_title


class TestScoreCandidate:
    def test_exact_title_and_year(self):
        conf, tsim, yscore = score_candidate("Heat", 1995, "Heat", "1995")
        assert conf == 1.0
        assert tsim == 1.0
        assert yscore == 1.0

    def test_exact_title_no_year(self):
        # year_score should be neutral (0.5) when neither side has a year
        conf, tsim, yscore = score_candidate("Heat", None, "Heat", None)
        assert tsim == 1.0
        assert yscore == 0.5
        assert conf == pytest.approx(0.75 * 1.0 + 0.25 * 0.5)

    def test_within_year_window(self):
        # Year off by 1 — should give partial credit (0.6)
        conf, tsim, yscore = score_candidate("Heat", 1994, "Heat", "1995")
        assert yscore == 0.6
        assert conf == pytest.approx(0.75 * 1.0 + 0.25 * 0.6)

    def test_outside_year_window(self):
        conf, tsim, yscore = score_candidate("Heat", 1990, "Heat", "1995")
        assert yscore == 0.0

    def test_title_mismatch_lowers_score(self):
        conf, tsim, yscore = score_candidate("Terminator 2", 1991,
                                              "Terminator 2: Judgment Day", "1991")
        assert tsim < 1.0
        assert yscore == 1.0
        assert conf < 1.0
        assert conf > 0.6  # still a strong match

    def test_poor_title_match(self):
        conf, tsim, _ = score_candidate("Victory", 1981, "The Great Victory", "1981")
        assert tsim < 0.85  # shouldn't auto-resolve

    def test_score_between_0_and_1(self):
        conf, tsim, yscore = score_candidate("Anything", 2000, "Something Else", "1950")
        assert 0.0 <= conf <= 1.0
        assert 0.0 <= tsim <= 1.0
        assert yscore in (0.0, 0.5, 0.6, 1.0)

    def test_candidate_year_none(self):
        # Candidate has no year — should not crash, year_score = 0.5
        conf, tsim, yscore = score_candidate("Heat", 1995, "Heat", None)
        assert yscore == 0.5

    def test_annotation_stripped_before_scoring(self):
        # The enrich script strips annotations from the search title before
        # calling score_candidate, so we test normalize_title consistency
        q_raw = "Batman (1989)"
        q_norm = normalize_title(strip_annotations(q_raw))
        c_norm = normalize_title("Batman")
        assert q_norm == c_norm
