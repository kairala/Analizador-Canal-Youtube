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


def test_core_metrics_excludes_unsupported_impressions_metrics():
    by_name = {r.name: r for r in REPORTS}
    assert "impressions" not in by_name["totals"].metrics
    assert "impressionsClickThroughRate" not in by_name["totals"].metrics


def test_reports_have_expected_column_renames_matching_spec():
    by_name = {r.name: r for r in REPORTS}
    assert by_name["totals"].column_renames == {}
    assert by_name["daily"].column_renames == {"day": "date"}
    assert by_name["traffic_sources"].column_renames == {"insightTrafficSourceType": "source"}
    assert by_name["devices"].column_renames == {"deviceType": "device"}
    assert by_name["geography"].column_renames == {}
    assert by_name["demographics"].column_renames == {
        "ageGroup": "age_group",
        "viewerPercentage": "viewer_percentage",
    }
    assert by_name["retention"].column_renames == {
        "elapsedVideoTimeRatio": "elapsed_ratio",
        "audienceWatchRatio": "audience_watch_ratio",
        "relativeRetentionPerformance": "relative_retention_performance",
    }
