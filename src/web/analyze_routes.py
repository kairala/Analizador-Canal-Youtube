# src/web/analyze_routes.py
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.analyze_core import analyze_selected_documents
from src.report_data import compute_channel_averages, load_video_documents
from src.web.jobs import JobAlreadyRunningError
from src.web.paths import app_data_dir
from src.web.services import get_anthropic_client

router = APIRouter(prefix="/api", tags=["analyze"])


class AnalyzeRequest(BaseModel):
    video_ids: list[str]


def _output_dir() -> Path:
    return app_data_dir() / "output"


def _reports_dir() -> Path:
    return app_data_dir() / "reports"


@router.get("/analyzable")
def get_analyzable():
    documents = load_video_documents(_output_dir())
    videos = [document.get("video", {}) for document in documents]
    return {"videos": videos}


@router.post("/analyze")
def start_analyze(request: Request, body: AnalyzeRequest, client=Depends(get_anthropic_client)):
    documents = load_video_documents(_output_dir())
    id_set = set(body.video_ids)
    selected = [document for document in documents if document.get("video", {}).get("id") in id_set]
    if not selected:
        raise HTTPException(status_code=400, detail="nenhum vídeo válido selecionado")

    channel_averages = compute_channel_averages(documents)
    reports_dir = _reports_dir()

    def job(print_fn):
        processed_ids, failed_ids = analyze_selected_documents(
            client, selected, channel_averages, reports_dir, print_fn=print_fn
        )
        print_fn(f"Concluído: {len(processed_ids)} relatório(s) gerado(s), {len(failed_ids)} com erro.")

    try:
        request.app.state.analyze_jobs.start("analyze", job)
    except JobAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"started": True}


@router.get("/analyze/stream")
def stream_analyze(request: Request):
    def event_source():
        for line in request.app.state.analyze_jobs.stream("analyze"):
            yield f"data: {line}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
