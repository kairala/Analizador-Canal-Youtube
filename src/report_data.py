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
    # A video published shortly before extraction has no Analytics data yet
    # (~48h reporting lag) and its `totals` comes back as `{}`. Counting it
    # as a zero-views video would dilute the average that the AI report
    # compares every video against, so it's excluded entirely.
    documents_with_data = [document for document in documents if document.get("totals")]

    if not documents_with_data:
        return {metric: 0 for metric in CORE_METRICS}

    sums = {metric: 0 for metric in CORE_METRICS}
    for document in documents_with_data:
        totals = document["totals"]
        for metric in CORE_METRICS:
            sums[metric] += totals.get(metric, 0) or 0

    count = len(documents_with_data)
    return {metric: sums[metric] / count for metric in CORE_METRICS}
