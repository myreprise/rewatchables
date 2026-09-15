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
import os
import sys
from datetime import datetime
from pathlib import Path

import openpyxl
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


# ---------------------------------------------------------------------------
# The workbook source: data/episodes.xlsx -> data/episodes.csv (step 01)
# ---------------------------------------------------------------------------
# Since 2026-09-15 the workbook is what gets edited and the CSV is rendered from
# it. The properties pinned here are the ones that make that safe: the render
# is exact, a cell Excel has mangled is refused rather than passed on, and the
# step never builds from a stale or half-saved file without saying so.

build_workbook = convert_mod.build_episode_workbook
render_workbook = convert_mod.render_episode_workbook
write_episode_csv = convert_mod.write_episode_csv
excel_lock_file = convert_mod.excel_lock_file
EPISODE_COLUMNS = convert_mod.EPISODE_COLUMNS
step01 = _load("render_source", "01_render_source.py")

sys.path.insert(0, str(Path(__file__).parent.parent))
from views import stale_notice  # noqa: E402

REPO_XLSX = Path(__file__).parent.parent / "data" / "episodes.xlsx"

# Formatted rows in a test workbook. The real one has 3,000, which costs
# seconds on every build and read; the behaviour is the same at 60.
FEW = 60


def _row(**values):
    row = dict.fromkeys(EPISODE_COLUMNS, "")
    row.update(ep="1", title="Heat", date="2015-12-22", host="Bill Simmons",
               guest1="Chris Ryan", year="1995", genre="Crime;Drama;",
               director="Michael Mann", ebert="3.5/4", tomatoes_score="0.83",
               rating="0.83", is_film="1", ebert_stars="3.5", revisited="1")
    row.update(values)
    return row


def _source(tmp_path):
    """A two-episode CSV and the workbook built from it."""
    rows = [
        _row(),
        _row(ep="7", ep_ex_1999="1", title="A Few Good Men", date="2017-08-10",
             guest2="Amanda Dobbins", year="", ebert="Not reviewed",
             ebert_stars="", tomatoes_score="", rating="", cruise_hanks="Cruise",
             notes='Bill says "#1", then leaves', revisited="0"),
    ]
    csv = tmp_path / "episodes.csv"
    pd.DataFrame(rows, columns=EPISODE_COLUMNS).to_csv(
        csv, index=False, lineterminator="\n")
    xlsx = tmp_path / "episodes.xlsx"
    assert build_workbook(csv, xlsx, format_rows=FEW) == 0
    return csv, xlsx


def _edit(xlsx, excel_row, **cells):
    wb = openpyxl.load_workbook(xlsx)
    ws = wb["episodes"]
    for column, value in cells.items():
        ws.cell(row=excel_row, column=EPISODE_COLUMNS.index(column) + 1).value = value
    wb.save(xlsx)


class TestEpisodeWorkbook:
    def test_renders_back_to_exactly_the_csv_it_was_built_from(self, tmp_path):
        csv, xlsx = _source(tmp_path)
        df, errors, _ = render_workbook(xlsx)
        assert errors == []
        assert df.equals(read_source(csv))
        again = tmp_path / "again.csv"
        assert write_episode_csv(df, again)
        assert again.read_bytes() == csv.read_bytes()

    def test_preformatted_blank_rows_are_not_episodes(self, tmp_path):
        _, xlsx = _source(tmp_path)
        assert openpyxl.load_workbook(xlsx)["episodes"].max_row == FEW
        assert len(render_workbook(xlsx)[0]) == 2

    def test_text_columns_are_text_below_the_data(self, tmp_path):
        """What keeps Excel from turning a typed '3/4' into the fourth of March."""
        _, xlsx = _source(tmp_path)
        ws = openpyxl.load_workbook(xlsx)["episodes"]
        ebert = EPISODE_COLUMNS.index("ebert") + 1
        assert ws.cell(row=FEW, column=ebert).number_format == "@"

    def test_a_row_typed_into_the_sheet_renders_like_the_rest(self, tmp_path):
        _, xlsx = _source(tmp_path)
        _edit(xlsx, 4, ep=481, title="Rambo: First Blood Part II",
              date=datetime(2026, 9, 14), host="Bill Simmons", year=1985,
              ebert="1.5/4", tomatoes_score=0.3, is_film=1, revisited=0)
        df, errors, _ = render_workbook(xlsx)
        assert errors == []
        new = df.iloc[-1]
        assert (new["ep"], new["date"], new["year"], new["tomatoes_score"]) == (
            "481", "2026-09-14", "1985", "0.3")
        # Left blank, and filled from the column each one copies.
        assert (new["rating"], new["ebert_stars"]) == ("0.3", "1.5")

    def test_a_rating_excel_turned_into_a_date_is_refused(self, tmp_path):
        _, xlsx = _source(tmp_path)
        _edit(xlsx, 2, ebert=datetime(2026, 3, 4))
        _, errors, _ = render_workbook(xlsx)
        assert len(errors) == 1
        assert "row 2" in errors[0] and "ebert" in errors[0] and "date" in errors[0]

    @pytest.mark.parametrize("column,value", [
        ("date", "22/12/2015"),
        ("tomatoes_score", 83),          # 83% is 0.83
        ("cruise_hanks", "Hanks!"),
        ("is_film", 2),
        ("ep", None),
        ("year", 95),
    ])
    def test_values_outside_the_column_rules_are_refused(self, tmp_path, column, value):
        _, xlsx = _source(tmp_path)
        _edit(xlsx, 2, **{column: value})
        _, errors, _ = render_workbook(xlsx)
        assert any(column in e and "row 2" in e for e in errors), errors

    @pytest.mark.parametrize("cells,column", [
        ({"tomatoes_score": 83}, "tomatoes_score"),
        ({"rating": "=M2"}, "rating"),
        ({"ebert": "3/5"}, "ebert"),
    ])
    def test_one_mistake_is_reported_once(self, tmp_path, cells, column):
        """Not also as its copy disagreeing: that second message would send
        you to clear the copy, which is the wrong cell."""
        _, xlsx = _source(tmp_path)
        _edit(xlsx, 2, **cells)
        _, errors, _ = render_workbook(xlsx)
        assert len(errors) == 1 and column in errors[0], errors

    def test_iso_text_in_the_date_column_is_accepted(self, tmp_path):
        _, xlsx = _source(tmp_path)
        _edit(xlsx, 2, date="2015-12-22")
        df, errors, _ = render_workbook(xlsx)
        assert errors == [] and df["date"][0] == "2015-12-22"

    def test_a_formula_with_no_saved_result_is_refused(self, tmp_path):
        """openpyxl writes the formula but no cached value -- as any tool but
        Excel would -- so reading it by value alone would see a blank."""
        _, xlsx = _source(tmp_path)
        _edit(xlsx, 2, rating="=N2")
        _, errors, _ = render_workbook(xlsx)
        assert any("formula" in e for e in errors), errors

    def test_a_derived_column_that_disagrees_is_refused(self, tmp_path):
        _, xlsx = _source(tmp_path)
        _edit(xlsx, 2, ebert_stars=2.0)
        _, errors, _ = render_workbook(xlsx)
        assert any("ebert_stars" in e for e in errors), errors

    def test_a_duplicate_airing_is_refused(self, tmp_path):
        _, xlsx = _source(tmp_path)
        _edit(xlsx, 3, ep=1, title="Heat", date=datetime(2015, 12, 22))
        _, errors, _ = render_workbook(xlsx)
        assert any("same episode number, date and title" in e for e in errors), errors

    def test_a_renamed_column_is_refused(self, tmp_path):
        _, xlsx = _source(tmp_path)
        wb = openpyxl.load_workbook(xlsx)
        wb["episodes"].cell(row=1, column=EPISODE_COLUMNS.index("notes") + 1).value = "comments"
        wb.save(xlsx)
        _, errors, _ = render_workbook(xlsx)
        assert any("notes" in e for e in errors) and any("comments" in e for e in errors)

    def test_a_future_air_date_is_a_warning_not_an_error(self, tmp_path):
        _, xlsx = _source(tmp_path)
        _edit(xlsx, 2, date=datetime(2999, 1, 1))
        _, errors, warnings = render_workbook(xlsx)
        assert errors == [] and any("future" in w for w in warnings)

    def test_float_noise_is_rendered_away(self):
        assert render(0.8300000000000001) == "0.83"

    def test_building_never_overwrites_the_source(self, tmp_path):
        csv, xlsx = _source(tmp_path)
        assert build_workbook(csv, xlsx) == 1


class TestExcelLock:
    @pytest.mark.parametrize("owner", ["~$episodes.xlsx", "~$isodes.xlsx"])
    def test_the_owner_file_is_found_under_either_name(self, tmp_path, owner):
        (tmp_path / owner).write_text("")
        assert excel_lock_file(tmp_path / "episodes.xlsx") == tmp_path / owner

    def test_no_owner_file_means_not_open(self, tmp_path):
        assert excel_lock_file(tmp_path / "episodes.xlsx") is None


class TestRenderSourceStep:
    def test_writes_the_csv_from_the_workbook(self, tmp_path):
        csv, xlsx = _source(tmp_path)
        _edit(xlsx, 2, guest3="Mallory Rubin")
        assert step01.render_source(xlsx, csv, tmp_path / "logs") == 0
        assert read_source(csv)["guest3"][0] == "Mallory Rubin"
        assert not (tmp_path / "logs").exists()

    def test_no_workbook_falls_back_to_the_tracked_csv(self, tmp_path):
        csv, xlsx = _source(tmp_path)
        xlsx.unlink()
        before = csv.read_bytes()
        assert step01.render_source(xlsx, csv, tmp_path / "logs") == 0
        assert csv.read_bytes() == before

    def test_a_workbook_open_in_excel_is_refused(self, tmp_path):
        csv, xlsx = _source(tmp_path)
        (tmp_path / "~$episodes.xlsx").write_text("")
        before = csv.read_bytes()
        assert step01.render_source(xlsx, csv, tmp_path / "logs") == 1
        assert csv.read_bytes() == before

    def test_a_bad_cell_leaves_the_csv_untouched(self, tmp_path):
        csv, xlsx = _source(tmp_path)
        _edit(xlsx, 2, ebert=datetime(2026, 3, 4))
        before = csv.read_bytes()
        assert step01.render_source(xlsx, csv, tmp_path / "logs") == 1
        assert csv.read_bytes() == before

    def test_a_csv_edited_after_the_workbook_is_kept_before_it_is_replaced(self, tmp_path):
        csv, xlsx = _source(tmp_path)
        csv.write_bytes(csv.read_bytes().replace(b"Michael Mann", b"Mike Mann"))
        later = xlsx.stat().st_mtime + 60
        os.utime(csv, (later, later))
        logs = tmp_path / "logs"
        assert step01.render_source(xlsx, csv, logs) == 0
        kept = list(logs.glob("episodes.csv.replaced-*"))
        assert len(kept) == 1 and b"Mike Mann" in kept[0].read_bytes()
        assert b"Michael Mann" in csv.read_bytes()

    def test_an_unchanged_csv_is_not_rewritten(self, tmp_path):
        csv, xlsx = _source(tmp_path)
        step01.render_source(xlsx, csv, tmp_path / "logs")
        stamp = csv.stat().st_mtime_ns
        assert step01.render_source(xlsx, csv, tmp_path / "logs") == 0
        assert csv.stat().st_mtime_ns == stamp


class TestStaleBanner:
    def test_shown_when_the_workbook_was_saved_after_the_load(self):
        notice = stale_notice(datetime(2026, 9, 15, 8, 0), datetime(2026, 9, 15, 7, 0))
        assert "orchestrate.py --from 1" in notice

    def test_hidden_once_the_load_is_newer(self):
        assert stale_notice(datetime(2026, 9, 15, 7, 0), datetime(2026, 9, 15, 8, 0)) == ""

    @pytest.mark.parametrize("saved,loaded", [
        (None, datetime(2026, 9, 15)), (datetime(2026, 9, 15), None)])
    def test_hidden_when_either_time_is_unknown(self, saved, loaded):
        assert stale_notice(saved, loaded) == ""


@pytest.mark.skipif(not REPO_XLSX.exists(), reason="data/episodes.xlsx not present")
class TestRepoWorkbook:
    def test_the_workbook_renders_to_exactly_the_tracked_csv(self):
        """The two files move together: step 01 writes one from the other. If
        this fails, the CSV was edited by hand, or the workbook was changed and
        step 01 has not been run since -- commit the two together."""
        df, errors, _ = render_workbook(REPO_XLSX)
        assert errors == []
        assert df.equals(read_source(REPO_CSV))
