from datetime import date
from pathlib import Path

from googleapiclient.discovery import build

from src.auth import SCOPES, get_credentials
from src.extract_core import extract_selected_videos, extract_video
from src.reports import REPORTS
from src.selection import parse_selection
from src.storage import save_channel_videos_snapshot, save_consolidated
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

    documents, failed_ids = extract_selected_videos(
        analytics_service, output_dir, today, selected, print_fn=print_fn, report_defs=report_defs
    )

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
