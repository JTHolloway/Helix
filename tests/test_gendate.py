"""The date parser is the foundation: if it is wrong, every chart is wrong."""
from datetime import date

import pytest
from hypothesis import given, strategies as st

from helix.model.gendate import GenDate, age_at, parse


@pytest.mark.parametrize("text,kind,year", [
    ("12 MAR 1841", "exact", 1841),
    ("1841", "exact", 1841),
    ("3/7/1899", "exact", 1899),
    ("1861-04-07", "exact", 1861),
    ("abt 1834", "about", 1834),
    ("circa 1834", "about", 1834),
    ("c 1834", "about", 1834),
    ("est 1795", "estimated", 1795),
    ("bef 1900", "before", None),
    ("aft 1866", "after", None),
    ("bet 1820 and 1825", "between", 1822),
    ("Q3 1871", "quarter", 1871),
    ("1850s", "exact", 1854),
    ("Jan 1888", "exact", 1888),
])
def test_parses(text, kind, year):
    d = parse(text)
    assert d.kind == kind
    if year is not None:
        assert abs(d.year - year) <= 1


def test_dual_dating():
    """Before 1752 the English year began on 25 March, so '12 Feb 1723'
    means 1724 to us. Getting this wrong silently shifts a generation."""
    d = parse("1723/24")
    assert d.calendar == "dual"
    assert d.earliest.year == 1724
    assert "1723/24" in d.display


def test_never_raises():
    for junk in ["", "   ", "no idea", "??", "1841?", "sometime in the war",
                 "32 Feb 1900", "0000", "----", "1234567890"]:
        d = parse(junk)
        assert isinstance(d, GenDate)


def test_original_is_preserved():
    """Never destroy what the user typed."""
    d = parse("maybe the spring of 1841")
    assert d.kind == "unknown"
    assert d.original == "maybe the spring of 1841"


def test_json_round_trip():
    for text in ["12 MAR 1841", "abt 1834", "bet 1820 and 1825", "gibberish"]:
        d = parse(text)
        assert GenDate.from_json(d.to_json()) == d


def test_age_is_a_range_not_a_number():
    """Two fuzzy dates cannot produce an exact age. Printing one is a lie
    the chart then repeats for a hundred years."""
    a = age_at(parse("abt 1834"), parse("12 Mar 1900"))
    assert a.low != a.high
    assert "\u2013" in a.display


def test_age_exact_when_dates_exact():
    a = age_at(parse("1 Jan 1800"), parse("1 Jan 1870"))
    assert a.low == a.high == 70


def test_ordering():
    assert parse("1800").sort_value < parse("1900").sort_value
    assert parse("bef 1850").definitely_before(parse("1900"))
    assert not parse("abt 1850").definitely_before(parse("abt 1851"))


@given(st.integers(min_value=1500, max_value=2100))
def test_any_year_parses(y):
    d = parse(str(y))
    assert d.year == y
