import json

from src.storage import (
    assemble_video_document,
    save_channel_videos_snapshot,
    save_consolidated,
    save_video_report,
)


def test_assemble_video_document_merges_meta_and_reports():
    video_meta = {"id": "vid1", "title": "Video 1"}
    shaped_reports = {"totals": {"views": 10}, "daily": [{"day": "2024-01-01", "views": 10}]}

    document = assemble_video_document(video_meta, shaped_reports)

    assert document == {
        "video": {"id": "vid1", "title": "Video 1"},
        "totals": {"views": 10},
        "daily": [{"day": "2024-01-01", "views": 10}],
    }


def test_save_video_report_writes_expected_file(tmp_path):
    document = {"video": {"id": "vid1"}, "totals": {"views": 10}}

    path = save_video_report(tmp_path, "vid1", document)

    assert path == tmp_path / "por_video" / "vid1.json"
    assert json.loads(path.read_text(encoding="utf-8")) == document


def test_save_consolidated_writes_expected_file(tmp_path):
    documents = [{"video": {"id": "vid1"}}, {"video": {"id": "vid2"}}]

    path = save_consolidated(tmp_path, documents, "2026-09-28")

    assert path == tmp_path / "consolidado.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "generated_at": "2026-09-28",
        "videos": documents,
    }


def test_save_channel_videos_snapshot_writes_expected_file(tmp_path):
    videos = [{"id": "vid1", "title": "Video 1"}]

    path = save_channel_videos_snapshot(tmp_path, videos)

    assert path == tmp_path / "channel_videos.json"
    assert json.loads(path.read_text(encoding="utf-8")) == videos
