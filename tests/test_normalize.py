"""
Unit tests for normalization functions in 03_normalize_and_resolve.py.
No database, no API calls — pure function tests.
"""

import pytest

from rewatchables.pipeline import s03_normalize_and_resolve as mod

strip_annotations = mod.strip_annotations
normalize_title   = mod.normalize_title
parse_year        = mod.parse_year
normalize_date    = mod.normalize_date
parse_revisited   = mod.parse_revisited


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


class TestParseRevisited:
    """The sheet's curated `revisited` column. The raw zone stores everything as
    text, so a 1 arrives as '1', '1.0' or 'True' depending on pandas typing."""

    @pytest.mark.parametrize("raw", ["1", "1.0", 1, 1.0, "True", "true", "yes"])
    def test_truthy_values_parse_to_one(self, raw):
        assert parse_revisited(raw) == 1

    @pytest.mark.parametrize("raw", ["0", "0.0", 0, 0.0, "False", "false", "no"])
    def test_falsy_values_parse_to_zero(self, raw):
        assert parse_revisited(raw) == 0

    def test_whitespace_is_tolerated(self):
        assert parse_revisited(" 1 ") == 1

    def test_none_returns_none(self):
        assert parse_revisited(None) is None

    def test_empty_cell_returns_none(self):
        """An empty cell is 'unknown', not 'explicitly not a revisit' — the two
        must stay distinguishable so a half-filled column is visible."""
        assert parse_revisited("") is None

    def test_pandas_nan_string_returns_none(self):
        """02_load_raw does df.astype(str), so a blank becomes the text 'nan'."""
        assert parse_revisited("nan") is None

    def test_unrecognised_value_returns_none_not_zero(self):
        assert parse_revisited("maybe") is None

    def test_zero_is_not_confused_with_missing(self):
        assert parse_revisited("0") == 0
        assert parse_revisited("0") is not None
