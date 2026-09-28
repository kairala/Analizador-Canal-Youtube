from datetime import date

from src.date_ranges import analytics_date_range


def test_analytics_date_range_from_iso_published_at():
    start, end = analytics_date_range("2024-05-01T12:00:00Z", date(2024, 6, 15))
    assert (start, end) == ("2024-05-01", "2024-06-15")


def test_analytics_date_range_same_day():
    start, end = analytics_date_range("2024-06-15T08:00:00Z", date(2024, 6, 15))
    assert (start, end) == ("2024-06-15", "2024-06-15")
