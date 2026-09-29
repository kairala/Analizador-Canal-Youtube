import json
from pathlib import Path

from src.reports import CORE_METRICS


def load_video_documents(output_dir: Path) -> list[dict]:
    por_video_dir = output_dir / "por_video"
    if not por_video_dir.is_dir():
        return []

    documents = []
    for path in sorted(por_video_dir.glob("*.json")):
        documents.append(json.loads(path.read_text(encoding="utf-8")))
    return documents


def compute_channel_averages(documents: list[dict]) -> dict:
    if not documents:
        return {metric: 0 for metric in CORE_METRICS}

    sums = {metric: 0 for metric in CORE_METRICS}
    for document in documents:
        totals = document.get("totals") or {}
        for metric in CORE_METRICS:
            sums[metric] += totals.get(metric, 0) or 0

    count = len(documents)
    return {metric: sums[metric] / count for metric in CORE_METRICS}
