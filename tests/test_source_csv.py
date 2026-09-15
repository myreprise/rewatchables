"""
Tests for the CSV source file: the verbatim read in 02_load_raw.py and the
one-off conversion in convert_xlsx_to_csv.py.

data/episodes.csv replaced data/master.xlsx so that git can diff the episode
list — the xlsx showed up only as "Bin 71028 -> 76009 bytes". Two properties
have to hold for that to be worth anything:

  * the file is read VERBATIM. pandas types a column by guessing, and the xlsx
    path then stringified the guess, which is how '1995.0' and the literal
    string 'nan' reached the raw zone. dtype=str with keep_default_na=False
    turns all of that off.
  * the conversion is lossless in the only sense that matters: the business keys
    are unchanged, so staging ids stay stable and manual review decisions still
    replay.
"""

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).parent.parent / "scripts" / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


load_raw = _load("load_raw", "02_load_raw.py")
convert_mod = _load("convert_xlsx", "convert_xlsx_to_csv.py")
keys = _load("keys", "_keys.py")

read_source = load_raw.read_source
render = convert_mod.render
convert = convert_mod.convert
episode_business_key = keys.episode_business_key

REPO_CSV = Path(__file__).parent.parent / "data" / "episodes.csv"


# ---------------------------------------------------------------------------
# read_source — nothing inferred
# ---------------------------------------------------------------------------

class TestVerbatimRead:
    def test_empty_cell_is_empty_string_not_nan(self, tmp_path):
        p = tmp_path / "e.csv"
        p.write_text("ep,title,guest2\n1,Heat,\n", encoding="utf-8")
        df = read_source(p)
        # The xlsx path produced the literal three-letter string 'nan' here,
        # which then had to be filtered out again in views.clean().
        assert df["guest2"][0] == ""

    def test_integer_year_keeps_no_decimal_point(self, tmp_path):
        p = tmp_path / "e.csv"
        p.write_text("ep,year\n1,1995\n2,\n", encoding="utf-8")
        df = read_source(p)
        # A blank in the column used to make pandas infer float64 for the whole
        # column, turning every year into '1995.0'.
        assert list(df["year"]) == ["1995", ""]

    def test_half_star_ratings_survive(self, tmp_path):
        p = tmp_path / "e.csv"
        p.write_text("ep,ebert_stars\n1,3.5\n2,4\n", encoding="utf-8")
        assert list(read_source(p)["ebert_stars"]) == ["3.5", "4"]

    def test_leading_zeros_are_preserved(self, tmp_path):
        p = tmp_path / "e.csv"
        p.write_text("ep,title\n007,Heat\n", encoding="utf-8")
        assert read_source(p)["ep"][0] == "007"

    @pytest.mark.parametrize("value", ["NA", "null", "None", "N/A", "nan"])
    def test_values_that_look_like_nulls_are_kept_as_text(self, tmp_path, value):
        # keep_default_na=False. A film legitimately titled 'NA' must not become
        # a missing value, and neither must a note reading 'None'.
        p = tmp_path / "e.csv"
        p.write_text(f"ep,notes\n1,{value}\n", encoding="utf-8")
        assert read_source(p)["notes"][0] == value

    def test_column_names_with_spaces_are_normalised(self, tmp_path):
        # Excel exports reintroduce the space in 'ep ex_1999'.
        p = tmp_path / "e.csv"
        p.write_text("ep,ep ex_1999\n1,1\n", encoding="utf-8")
        assert "ep_ex_1999" in read_source(p).columns

    def test_quoted_commas_round_trip(self, tmp_path):
        p = tmp_path / "e.csv"
        p.write_text('ep,notes\n1,"Bill says hi, then leaves"\n', encoding="utf-8")
        assert read_source(p)["notes"][0] == "Bill says hi, then leaves"


# ---------------------------------------------------------------------------
# render — the conversion rule, one cell at a time
# ---------------------------------------------------------------------------

class TestRender:
    @pytest.mark.parametrize("value, expected", [
        (float("nan"), ""),
        (None, ""),
        (1995.0, "1995"),        # int-valued float loses the '.0'
        (3.5, "3.5"),            # a real fraction keeps it
        (0.83, "0.83"),
        (1, "1"),
        ("Heat ", "Heat"),       # 120 titles carried trailing whitespace
        ("  Heat  ", "Heat"),
        ("", ""),
        (pd.Timestamp("2015-12-22"), "2015-12-22"),
    ])
    def test_cases(self, value, expected):
        assert render(value) == expected


# ---------------------------------------------------------------------------
# The conversion as a whole
# ---------------------------------------------------------------------------

class TestConversion:
    def _xlsx(self, tmp_path):
        path = tmp_path / "master.xlsx"
        pd.DataFrame({
            "ep": [1, 2],
            "ep ex_1999": [None, 2.0],
            "title": ["Heat ", "The Insider"],
            "date": [pd.Timestamp("2015-12-22"), pd.Timestamp("2019-05-23")],
            "year": [1995.0, 1999.0],
            "guest2": [None, "Chris Ryan"],
            "ebert_stars": [3.5, 4.0],
        }).to_excel(path, index=False)
        return path

    def test_produces_a_csv_that_reads_back_identically(self, tmp_path):
        out = tmp_path / "episodes.csv"
        assert convert(self._xlsx(tmp_path), out) == 0
        df = read_source(out)
        assert list(df["year"]) == ["1995", "1999"]
        assert list(df["guest2"]) == ["", "Chris Ryan"]
        assert list(df["title"]) == ["Heat", "The Insider"]
        assert list(df["ebert_stars"]) == ["3.5", "4"]
        assert list(df["date"]) == ["2015-12-22", "2019-05-23"]

    def test_business_keys_are_unchanged_by_the_conversion(self, tmp_path):
        """The property that lets the switch happen without losing review work.

        Staging ids are uuid5 over ep+date+title. If the conversion moved any of
        those three, every staging id would change and the manual review
        decisions in data/manual_review.csv would detach.
        """
        xlsx = self._xlsx(tmp_path)
        out = tmp_path / "episodes.csv"
        convert(xlsx, out)

        before = pd.read_excel(xlsx)
        before.columns = [c.replace(" ", "_") for c in before.columns]
        before = before.astype(str)
        after = read_source(out)

        before_keys = [episode_business_key(r.ep, r.date, r.title)
                       for r in before.itertuples()]
        after_keys = [episode_business_key(r.ep, r.date, r.title)
                      for r in after.itertuples()]
        assert before_keys == after_keys

    def test_dry_run_writes_nothing(self, tmp_path):
        out = tmp_path / "episodes.csv"
        assert convert(self._xlsx(tmp_path), out, dry_run=True) == 0
        assert not out.exists()

    def test_missing_xlsx_is_reported_not_raised(self, tmp_path):
        assert convert(tmp_path / "absent.xlsx", tmp_path / "o.csv") == 1


# ---------------------------------------------------------------------------
# The file actually in the repo
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not REPO_CSV.exists(), reason="data/episodes.csv not present")
class TestRepoSourceFile:
    def test_reads_and_has_the_expected_columns(self):
        df = read_source(REPO_CSV)
        assert len(df) > 400
        assert {"ep", "title", "date", "is_film", "revisited"} <= set(df.columns)

    def test_carries_no_dtype_artifacts(self):
        df = read_source(REPO_CSV)
        flat = df.values.ravel()
        assert "nan" not in set(flat)
        assert not any(v.endswith(".0") for v in df["year"] if v)

    def test_business_keys_are_unique(self):
        """Two rows sharing a key would upsert onto each other and one would be
        silently dropped. ep alone is not unique — revisits reuse the number."""
        df = read_source(REPO_CSV)
        found = [episode_business_key(r.ep, r.date, r.title)
                 for r in df.itertuples()]
        assert len(found) == len(set(found))

    def test_no_leading_or_trailing_whitespace(self):
        """Invisible in a diff, and it would vanish on the first hand edit,
        producing a version row that records no real change."""
        df = read_source(REPO_CSV)
        offenders = [(c, v) for c in df.columns for v in df[c]
                     if v != v.strip()]
        assert offenders == []
