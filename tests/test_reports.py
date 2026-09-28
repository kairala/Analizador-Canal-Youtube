from src.reports import REPORTS


def test_reports_have_expected_names_in_order():
    names = [r.name for r in REPORTS]
    assert names == [
        "totals",
        "daily",
        "traffic_sources",
        "devices",
        "geography",
        "demographics",
        "retention",
    ]


def test_every_report_has_metrics():
    for report_def in REPORTS:
        assert len(report_def.metrics) > 0


def test_totals_is_aggregate_and_daily_is_timeseries_with_same_metrics():
    by_name = {r.name: r for r in REPORTS}
    assert by_name["totals"].dimensions == []
    assert by_name["daily"].dimensions == ["day"]
    assert by_name["daily"].metrics == by_name["totals"].metrics


def test_breakdown_reports_have_expected_dimensions():
    by_name = {r.name: r for r in REPORTS}
    assert by_name["traffic_sources"].dimensions == ["insightTrafficSourceType"]
    assert by_name["devices"].dimensions == ["deviceType"]
    assert by_name["geography"].dimensions == ["country"]
    assert by_name["demographics"].dimensions == ["ageGroup", "gender"]
    assert by_name["retention"].dimensions == ["elapsedVideoTimeRatio"]
