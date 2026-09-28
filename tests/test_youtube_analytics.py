from src.reports import ReportDef
from src.youtube_analytics import parse_analytics_response, run_report, shape_report_result


class FakeAnalyticsService:
    def __init__(self, response):
        self._response = response
        self.last_kwargs = None

    def reports(self):
        return self

    def query(self, **kwargs):
        self.last_kwargs = kwargs
        return self

    def execute(self):
        return self._response


def test_parse_analytics_response_zips_headers_with_rows():
    response = {
        "columnHeaders": [{"name": "day"}, {"name": "views"}],
        "rows": [["2024-01-01", 10], ["2024-01-02", 5]],
    }
    assert parse_analytics_response(response) == [
        {"day": "2024-01-01", "views": 10},
        {"day": "2024-01-02", "views": 5},
    ]


def test_parse_analytics_response_handles_no_rows():
    response = {"columnHeaders": [{"name": "views"}], "rows": []}
    assert parse_analytics_response(response) == []


def test_shape_report_result_returns_single_dict_for_aggregate_report():
    report_def = ReportDef(name="totals", dimensions=[], metrics=["views"])
    assert shape_report_result(report_def, [{"views": 42}]) == {"views": 42}


def test_shape_report_result_returns_empty_dict_when_no_rows_for_aggregate_report():
    report_def = ReportDef(name="totals", dimensions=[], metrics=["views"])
    assert shape_report_result(report_def, []) == {}


def test_shape_report_result_returns_list_for_timeseries_report():
    report_def = ReportDef(name="daily", dimensions=["day"], metrics=["views"])
    rows = [{"day": "2024-01-01", "views": 10}]
    assert shape_report_result(report_def, rows) == rows


def test_run_report_builds_expected_query_and_parses_response():
    response = {
        "columnHeaders": [{"name": "day"}, {"name": "views"}],
        "rows": [["2024-01-01", 10]],
    }
    service = FakeAnalyticsService(response)
    report_def = ReportDef(name="daily", dimensions=["day"], metrics=["views"])

    result = run_report(service, "vid1", "2024-01-01", "2024-02-01", report_def)

    assert result == [{"day": "2024-01-01", "views": 10}]
    assert service.last_kwargs == {
        "ids": "channel==MINE",
        "startDate": "2024-01-01",
        "endDate": "2024-02-01",
        "metrics": "views",
        "filters": "video==vid1",
        "dimensions": "day",
    }


def test_run_report_omits_dimensions_key_for_aggregate_report():
    response = {"columnHeaders": [{"name": "views"}], "rows": [[42]]}
    service = FakeAnalyticsService(response)
    report_def = ReportDef(name="totals", dimensions=[], metrics=["views"])

    run_report(service, "vid1", "2024-01-01", "2024-02-01", report_def)

    assert "dimensions" not in service.last_kwargs


def test_run_report_applies_column_renames():
    response = {
        "columnHeaders": [{"name": "day"}, {"name": "views"}],
        "rows": [["2024-01-01", 10]],
    }
    service = FakeAnalyticsService(response)
    report_def = ReportDef(
        name="daily",
        dimensions=["day"],
        metrics=["views"],
        column_renames={"day": "date"},
    )

    result = run_report(service, "vid1", "2024-01-01", "2024-02-01", report_def)

    assert result == [{"date": "2024-01-01", "views": 10}]
