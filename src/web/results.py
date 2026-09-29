# src/web/results.py
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from src.web.paths import app_data_dir

router = APIRouter(prefix="/api", tags=["results"])


def _output_dir() -> Path:
    return app_data_dir() / "output"


def _reports_dir() -> Path:
    return app_data_dir() / "reports"


@router.get("/results")
def list_results():
    por_video_dir = _output_dir() / "por_video"
    reports_dir = _reports_dir()

    extracted_ids = {path.stem for path in por_video_dir.glob("*.json")} if por_video_dir.is_dir() else set()
    analyzed_ids = {path.stem for path in reports_dir.glob("*.md")} if reports_dir.is_dir() else set()

    all_ids = sorted(extracted_ids | analyzed_ids)
    return {
        "results": [
            {
                "video_id": video_id,
                "has_extraction": video_id in extracted_ids,
                "has_report": video_id in analyzed_ids,
            }
            for video_id in all_ids
        ]
    }


@router.get("/results/{video_id}")
def get_result(video_id: str):
    extraction_path = _output_dir() / "por_video" / f"{video_id}.json"
    report_path = _reports_dir() / f"{video_id}.md"

    if not extraction_path.exists() and not report_path.exists():
        raise HTTPException(status_code=404, detail="vídeo não encontrado")

    extraction = None
    if extraction_path.exists():
        try:
            extraction = json.loads(extraction_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # A corrupted/truncated extraction file should behave like a
            # missing one, not 500 the whole detail endpoint.
            extraction = None

    report = report_path.read_text(encoding="utf-8") if report_path.exists() else None

    return {"video_id": video_id, "extraction": extraction, "report": report}
