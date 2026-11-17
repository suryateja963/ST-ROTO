import pytest

from st_roto import frames


def test_parse_lists_ranges_and_negatives():
    assert frames.parse("12-14, 30") == [12, 13, 14, 30]
    assert frames.parse("30 12-14 13") == [12, 13, 14, 30]
    assert frames.parse("-3--1, 5") == [-3, -2, -1, 5]
    assert frames.parse("20-18") == [18, 19, 20]
    assert frames.parse("") == [] and frames.parse("  ") == []


def test_parse_errors_name_the_part():
    with pytest.raises(ValueError, match="'a-b'"):
        frames.parse("1, a-b")
    with pytest.raises(ValueError):
        frames.parse("1-2-3")


def test_ranges_round_trip():
    for text in ("12-14, 30", "-3--1, 5", "7"):
        assert frames.ranges(frames.parse(text)) == text
    assert frames.ranges([]) == ""
