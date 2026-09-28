import pytest

from src.selection import parse_selection


def test_parse_single_number():
    assert parse_selection("2", total=5) == [2]


def test_parse_comma_separated_list():
    assert parse_selection(" 1, 3,5 ", total=5) == [1, 3, 5]


def test_parse_deduplicates_and_sorts():
    assert parse_selection("3,1,3", total=5) == [1, 3]


def test_parse_all_keyword_portuguese():
    assert parse_selection("todos", total=3) == [1, 2, 3]


def test_parse_all_keyword_english():
    assert parse_selection("ALL", total=3) == [1, 2, 3]


def test_parse_rejects_empty_input():
    with pytest.raises(ValueError):
        parse_selection("   ", total=3)


def test_parse_rejects_non_numeric_token():
    with pytest.raises(ValueError):
        parse_selection("abc", total=3)


def test_parse_rejects_out_of_range_number():
    with pytest.raises(ValueError):
        parse_selection("99", total=3)


def test_parse_rejects_when_no_videos_available():
    with pytest.raises(ValueError):
        parse_selection("1", total=0)
