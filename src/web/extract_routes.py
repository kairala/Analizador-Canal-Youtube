# src/web/extract_routes.py
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.extract_core import extract_selected_videos
from src.storage import save_channel_videos_snapshot, save_consolidated
from src.web.jobs import JobAlreadyRunningError
from src.web.paths import app_data_dir
from src.web.services import get_analytics_service, get_youtube_service
from src.youtube_data import list_channel_videos

router = APIRouter(prefix="/api", tags=["extract"])


class ExtractRequest(BaseModel):
    video_ids: list[str]


def _output_dir() -> Path:
    return app_data_dir() / "output"


@router.get("/videos")
def get_videos(youtube_service=Depends(get_youtube_service)):
    videos = list_channel_videos(youtube_service)
    save_channel_videos_snapshot(_output_dir(), videos)
    return {"videos": videos}


@router.post("/extract")
def start_extract(
    request: Request,
    body: ExtractRequest,
    youtube_service=Depends(get_youtube_service),
    analytics_service=Depends(get_analytics_service),
):
    all_videos = list_channel_videos(youtube_service)
    id_set = set(body.video_ids)
    selected = [video for video in all_videos if video["id"] in id_set]
    if not selected:
        raise HTTPException(status_code=400, detail="nenhum vídeo válido selecionado")

    output_dir = _output_dir()
    today = date.today()

    def job(print_fn):
        documents, failed_ids = extract_selected_videos(
            analytics_service, output_dir, today, selected, print_fn=print_fn
        )
        if documents:
            save_consolidated(output_dir, documents, today.isoformat())
        print_fn(f"Concluído: {len(documents)} vídeo(s) processado(s), {len(failed_ids)} com erro.")

    try:
        request.app.state.extract_jobs.start("extract", job)
    except JobAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"started": True}


@router.get("/extract/stream")
def stream_extract(request: Request):
    def event_source():
        for line in request.app.state.extract_jobs.stream("extract"):
            yield f"data: {line}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(event_source(), media_type="text/event-stream")
