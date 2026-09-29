from pathlib import Path

import anthropic
from dotenv import load_dotenv

from src.ai_report import generate_report
from src.report_data import compute_channel_averages, load_video_documents
from src.selection import parse_selection


def select_videos(documents, input_fn=input, print_fn=print):
    print_fn("Vídeos já extraídos disponíveis para análise:")
    for i, document in enumerate(documents, start=1):
        video = document.get("video", {})
        print_fn(f"[{i}] {video.get('title', '(sem título)')} - ID: {video.get('id', '?')}")

    while True:
        raw = input_fn("Digite o número do vídeo, vários separados por vírgula, ou 'todos': ")
        try:
            indices = parse_selection(raw, len(documents))
            return [documents[i - 1] for i in indices]
        except ValueError as exc:
            print_fn(f"Entrada inválida: {exc}. Tente novamente.")


def run(client, output_dir: Path, reports_dir: Path, input_fn=input, print_fn=print):
    documents = load_video_documents(output_dir)

    if not documents:
        print_fn(
            f"Nenhum vídeo extraído encontrado em {output_dir / 'por_video'}. "
            "Rode 'python main.py' primeiro para extrair os dados."
        )
        return

    channel_averages = compute_channel_averages(documents)
    selected = select_videos(documents, input_fn=input_fn, print_fn=print_fn)

    processed = 0
    failed_ids = []
    for document in selected:
        video = document.get("video", {})
        video_id = video.get("id", "desconhecido")
        print_fn(f"Analisando '{video.get('title', video_id)}' ({video_id})...")
        try:
            report_text = generate_report(client, document, channel_averages)
            reports_dir.mkdir(parents=True, exist_ok=True)
            (reports_dir / f"{video_id}.md").write_text(report_text, encoding="utf-8")
            processed += 1
        except Exception as exc:
            print_fn(f"  erro ao analisar {video_id}, pulando: {exc}")
            failed_ids.append(video_id)

    print_fn(f"Concluído: {processed} relatório(s) gerado(s), {len(failed_ids)} com erro.")
    if failed_ids:
        print_fn(f"Vídeos com erro: {', '.join(failed_ids)}")


def main():
    load_dotenv()
    client = anthropic.Anthropic()
    run(client, Path("output"), Path("reports"))


if __name__ == "__main__":
    main()
