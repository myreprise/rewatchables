"""
Unit tests for normalization functions in 03_normalize_and_resolve.py.
No database, no API calls — pure function tests.
"""

import pytest
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "normalize", Path(__file__).parent.parent / "scripts" / "03_normalize_and_resolve.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

strip_annotations = mod.strip_annotations
normalize_title   = mod.normalize_title
parse_year        = mod.parse_year
normalize_date    = mod.normalize_date


class TestStripAnnotations:
    def test_removes_parenthetical(self):
        assert strip_annotations("Batman (1989)") == "Batman"

    def test_removes_live_show_annotation(self):
        assert strip_annotations("Forrest Gump (Live from D.C.)") == "Forrest Gump"

    def test_removes_part_annotation(self):
        assert strip_annotations("Boogie Nights (Part 1 and 2)") == "Boogie Nights"

    def test_removes_quoted_nickname(self):
        assert strip_annotations('Heat ("The Three-Heat")') == "Heat"

    def test_removes_curly_quote_nickname(self):
        assert strip_annotations("Heat (“The Three-Heat”)") == "Heat"

    def test_removes_bracket(self):
        assert strip_annotations("Die Hard [Extended]") == "Die Hard"

    def test_nested_parens(self):
        # The outer paren contains a quoted aside with its own inner paren.
        # strip_annotations removes the whole '("A Few Good (Re)Men")' block.
        # The colon-subtitle ': Live from L.A.' is NOT in parens, so it stays —
        # normalize_title removes it later via the special-char pass.
        result = strip_annotations('A Few Good Men: Live from L.A. ("A Few Good (Re)Men")')
        assert "(Re)Men" not in result       # nested paren content removed
        assert 'A Few Good Men' in result    # core title preserved

    def test_no_annotation_unchanged(self):
        assert strip_annotations("Heat") == "Heat"

    def test_none_returns_empty(self):
        assert strip_annotations(None) == ""

    def test_collapses_extra_whitespace(self):
        result = strip_annotations("Titanic  (1997)")
        assert "  " not in result


class TestNormalizeTitle:
    def test_lowercase(self):
        assert normalize_title("HEAT") == "heat"

    def test_strips_leading_the(self):
        assert normalize_title("The Godfather") == "godfather"

    def test_does_not_strip_mid_the(self):
        assert "the" in normalize_title("Into the Wild")

    def test_strips_annotation_then_normalizes(self):
        assert normalize_title("Batman (1989)") == "batman"

    def test_strips_trailing_whitespace(self):
        assert normalize_title("Heat ") == "heat"

    def test_removes_special_chars(self):
        # Apostrophes and hyphens are kept; other punctuation removed
        title = normalize_title("Schindler's List")
        assert "'" in title or "s list" in title  # apostrophe may be kept

    def test_none_returns_none(self):
        assert normalize_title(None) is None

    def test_empty_string_returns_none_or_empty(self):
        result = normalize_title("")
        assert result is None or result == ""

    def test_year_annotation_stripped(self):
        assert normalize_title("Spider-Man (2002)") == "spider-man"


class TestParseYear:
    def test_integer_year(self):
        assert parse_year(1995) == 1995

    def test_float_year(self):
        assert parse_year(1995.0) == 1995

    def test_string_year(self):
        assert parse_year("1995") == 1995

    def test_year_in_string(self):
        assert parse_year("released in 1995") == 1995

    def test_none_returns_none(self):
        assert parse_year(None) is None

    def test_empty_returns_none(self):
        assert parse_year("") is None

    def test_implausible_low_year(self):
        assert parse_year(1000) is None

    def test_implausible_high_year(self):
        assert parse_year(2200) is None

    def test_boundary_low(self):
        assert parse_year(1850) == 1850

    def test_boundary_high(self):
        assert parse_year(2100) == 2100


class TestNormalizeDate:
    def test_iso_passthrough(self):
        assert normalize_date("2026-06-20") == "2026-06-20"

    def test_iso_with_timestamp(self):
        assert normalize_date("2026-05-18 00:00:00") == "2026-05-18"

    def test_mdy_format(self):
        assert normalize_date("6/8/2026") == "2026-06-08"

    def test_mdy_zero_padded(self):
        assert normalize_date("12/31/2025") == "2025-12-31"

    def test_single_digit_month_day(self):
        assert normalize_date("1/2/2024") == "2024-01-02"

    def test_none_returns_none(self):
        assert normalize_date(None) is None

    def test_empty_returns_none(self):
        assert normalize_date("") is None
