import json
from pathlib import Path


def assemble_video_document(video_meta: dict, shaped_reports: dict) -> dict:
    return {"video": video_meta, **shaped_reports}


def save_video_report(output_dir: Path, video_id: str, document: dict) -> Path:
    folder = output_dir / "por_video"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{video_id}.json"
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_consolidated(output_dir: Path, documents: list[dict], generated_at: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "consolidado.json"
    payload = {"generated_at": generated_at, "videos": documents}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_channel_videos_snapshot(output_dir: Path, videos: list[dict]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "channel_videos.json"
    path.write_text(json.dumps(videos, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
