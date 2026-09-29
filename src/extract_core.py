from datetime import date
from pathlib import Path

from src.date_ranges import analytics_date_range
from src.reports import REPORTS
from src.storage import assemble_video_document, save_video_report
from src.youtube_analytics import run_report, shape_report_result


def extract_video(analytics_service, video, today, report_defs=REPORTS, print_fn=print):
    start_date, end_date = analytics_date_range(video["published_at"], today)
    shaped = {}
    errors = {}
    for report_def in report_defs:
        try:
            rows = run_report(analytics_service, video["id"], start_date, end_date, report_def)
        except Exception as exc:
            print_fn(f"  aviso: falha ao extrair '{report_def.name}' para {video['id']}: {exc}")
            rows = []
            errors[report_def.name] = str(exc)
        shaped[report_def.name] = shape_report_result(report_def, rows)
    if errors:
        shaped["errors"] = errors
    return shaped


def extract_selected_videos(
    analytics_service,
    output_dir: Path,
    today: date,
    selected_videos: list[dict],
    print_fn=print,
    report_defs=REPORTS,
) -> tuple[list[dict], list[str]]:
    documents = []
    failed_ids = []
    for video in selected_videos:
        print_fn(f"Processando '{video['title']}' ({video['id']})...")
        try:
            shaped_reports = extract_video(analytics_service, video, today, report_defs, print_fn=print_fn)
            document = assemble_video_document(video, shaped_reports)
            save_video_report(output_dir, video["id"], document)
            documents.append(document)
        except Exception as exc:
            print_fn(f"  erro ao processar {video['id']}, pulando: {exc}")
            failed_ids.append(video["id"])
    return documents, failed_ids
