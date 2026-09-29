from pathlib import Path

from src.ai_report import generate_report


def analyze_selected_documents(
    client,
    selected_documents: list[dict],
    channel_averages: dict,
    reports_dir: Path,
    print_fn=print,
) -> tuple[list[str], list[str]]:
    processed_ids = []
    failed_ids = []
    for document in selected_documents:
        video = document.get("video", {})
        video_id = video.get("id", "desconhecido")
        print_fn(f"Analisando '{video.get('title', video_id)}' ({video_id})...")
        try:
            report_text = generate_report(client, document, channel_averages)
            reports_dir.mkdir(parents=True, exist_ok=True)
            (reports_dir / f"{video_id}.md").write_text(report_text, encoding="utf-8")
            processed_ids.append(video_id)
        except Exception as exc:
            print_fn(f"  erro ao analisar {video_id}, pulando: {exc}")
            failed_ids.append(video_id)
    return processed_ids, failed_ids
