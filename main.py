from datetime import date
from pathlib import Path

from googleapiclient.discovery import build

from src.auth import SCOPES, get_credentials
from src.date_ranges import analytics_date_range
from src.reports import REPORTS
from src.selection import parse_selection
from src.storage import (
    assemble_video_document,
    save_channel_videos_snapshot,
    save_consolidated,
    save_video_report,
)
from src.youtube_analytics import run_report, shape_report_result
from src.youtube_data import list_channel_videos


def select_videos(videos, input_fn=input, print_fn=print):
    print_fn("Vídeos encontrados:")
    for i, video in enumerate(videos, start=1):
        published_date = video.get("published_at", "")[:10]
        print_fn(f"[{i}] {video['title']} (publicado em {published_date}) - ID: {video['id']}")

    while True:
        raw = input_fn("Digite o número do vídeo, vários separados por vírgula, ou 'todos': ")
        try:
            indices = parse_selection(raw, len(videos))
            return [videos[i - 1] for i in indices]
        except ValueError as exc:
            print_fn(f"Entrada inválida: {exc}. Tente novamente.")


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


def run(
    youtube_service,
    analytics_service,
    output_dir: Path,
    today: date,
    input_fn=input,
    print_fn=print,
    report_defs=REPORTS,
):
    videos = list_channel_videos(youtube_service)
    save_channel_videos_snapshot(output_dir, videos)

    if not videos:
        print_fn("Nenhum vídeo encontrado no canal.")
        return

    selected = select_videos(videos, input_fn=input_fn, print_fn=print_fn)

    documents = []
    failed_ids = []
    for video in selected:
        print_fn(f"Processando '{video['title']}' ({video['id']})...")
        try:
            shaped_reports = extract_video(analytics_service, video, today, report_defs, print_fn=print_fn)
            document = assemble_video_document(video, shaped_reports)
            save_video_report(output_dir, video["id"], document)
            documents.append(document)
        except Exception as exc:
            print_fn(f"  erro ao processar {video['id']}, pulando: {exc}")
            failed_ids.append(video["id"])

    if documents:
        save_consolidated(output_dir, documents, today.isoformat())

    print_fn(f"Concluído: {len(documents)} vídeo(s) processado(s), {len(failed_ids)} com erro.")
    if failed_ids:
        print_fn(f"Vídeos com erro: {', '.join(failed_ids)}")


def main():
    client_secret_path = Path("client_secret.json")
    token_path = Path("token.json")
    credentials = get_credentials(client_secret_path, token_path, SCOPES)

    youtube_service = build("youtube", "v3", credentials=credentials)
    analytics_service = build("youtubeAnalytics", "v2", credentials=credentials)

    run(youtube_service, analytics_service, Path("output"), date.today())


if __name__ == "__main__":
    main()
