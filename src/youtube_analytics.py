import time

from src.http_retry import call_with_http_retry
from src.reports import ReportDef


def parse_analytics_response(response: dict) -> list[dict]:
    headers = [h["name"] for h in response.get("columnHeaders", [])]
    rows = response.get("rows", []) or []
    return [dict(zip(headers, row)) for row in rows]


def shape_report_result(report_def: ReportDef, rows: list[dict]):
    if not report_def.dimensions:
        return rows[0] if rows else {}
    return rows


def _apply_column_renames(rows: list[dict], renames: dict) -> list[dict]:
    if not renames:
        return rows
    return [{renames.get(key, key): value for key, value in row.items()} for row in rows]


def run_report(
    analytics_service,
    video_id: str,
    start_date: str,
    end_date: str,
    report_def: ReportDef,
    sleep=time.sleep,
) -> list[dict]:
    params = {
        "ids": "channel==MINE",
        "startDate": start_date,
        "endDate": end_date,
        "metrics": ",".join(report_def.metrics),
        "filters": f"video=={video_id}",
    }
    if report_def.dimensions:
        params["dimensions"] = ",".join(report_def.dimensions)

    def _execute():
        return analytics_service.reports().query(**params).execute()

    response = call_with_http_retry(_execute, sleep=sleep)
    rows = parse_analytics_response(response)
    return _apply_column_renames(rows, report_def.column_renames)
