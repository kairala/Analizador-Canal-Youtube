from datetime import date
from pathlib import Path

import pytest

import main as main_module
from main import extract_video, run, select_videos
from src.reports import ReportDef


class ScriptedAnalyticsService:
    """Fake analytics client whose response/behavior depends on the query kwargs."""

    def __init__(self, responder):
        self._responder = responder
        self._kwargs = None

    def reports(self):
        return self

    def query(self, **kwargs):
        self._kwargs = kwargs
        return self

    def execute(self):
        return self._responder(self._kwargs)


class FakeYouTubeService:
    def __init__(self, videos):
        self._videos = videos


def fake_list_channel_videos(_service):
    return _service._videos


# --- select_videos ---


def test_select_videos_returns_chosen_subset():
    videos = [{"id": "v1", "title": "A"}, {"id": "v2", "title": "B"}, {"id": "v3", "title": "C"}]
    inputs = iter(["1,3"])

    selected = select_videos(videos, input_fn=lambda _prompt: next(inputs), print_fn=lambda _msg: None)

    assert selected == [videos[0], videos[2]]


def test_select_videos_retries_on_invalid_input():
    videos = [{"id": "v1", "title": "A"}]
    inputs = iter(["not-a-number", "1"])
    messages = []

    selected = select_videos(videos, input_fn=lambda _prompt: next(inputs), print_fn=messages.append)

    assert selected == [videos[0]]
    assert any("inválida" in message for message in messages)


# --- extract_video ---


def test_extract_video_keeps_going_when_one_report_fails_or_is_empty():
    def responder(kwargs):
        if "insightTrafficSourceType" in kwargs.get("dimensions", ""):
            raise RuntimeError("quota exceeded")
        if kwargs.get("dimensions") == "day":
            return {"columnHeaders": [{"name": "day"}, {"name": "views"}], "rows": []}
        if not kwargs.get("dimensions"):
            return {"columnHeaders": [{"name": "views"}], "rows": [[100]]}
        return {"columnHeaders": [{"name": kwargs["dimensions"]}], "rows": [["x"]]}

    service = ScriptedAnalyticsService(responder)
    video = {"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z"}
    messages = []

    result = extract_video(service, video, date(2024, 2, 1), print_fn=messages.append)

    assert result["totals"] == {"views": 100}
    assert result["daily"] == []
    assert result["traffic_sources"] == []
    assert any("traffic_sources" in message for message in messages)
    assert result["errors"] == {"traffic_sources": "quota exceeded"}


# --- run (end to end with fakes) ---


def _always_empty_responder(_kwargs):
    return {"columnHeaders": [], "rows": []}


def test_run_saves_all_videos_and_consolidated_file(tmp_path, monkeypatch):
    videos = [
        {"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z", "duration": "PT1M"},
        {"id": "vid2", "title": "Video 2", "published_at": "2024-01-02T00:00:00Z", "duration": "PT2M"},
    ]
    youtube_service = FakeYouTubeService(videos)
    analytics_service = ScriptedAnalyticsService(_always_empty_responder)
    monkeypatch.setattr(main_module, "list_channel_videos", fake_list_channel_videos)

    run(
        youtube_service,
        analytics_service,
        tmp_path,
        date(2024, 2, 1),
        input_fn=lambda _prompt: "todos",
        print_fn=lambda _msg: None,
    )

    assert (tmp_path / "por_video" / "vid1.json").exists()
    assert (tmp_path / "por_video" / "vid2.json").exists()
    assert (tmp_path / "consolidado.json").exists()
    assert (tmp_path / "channel_videos.json").exists()


def test_run_continues_when_saving_one_video_fails(tmp_path, monkeypatch):
    import src.extract_core as extract_core_module

    videos = [
        {"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z", "duration": "PT1M"},
        {"id": "vid2", "title": "Video 2", "published_at": "2024-01-02T00:00:00Z", "duration": "PT2M"},
    ]
    youtube_service = FakeYouTubeService(videos)
    analytics_service = ScriptedAnalyticsService(_always_empty_responder)
    monkeypatch.setattr(main_module, "list_channel_videos", fake_list_channel_videos)

    real_save_video_report = extract_core_module.save_video_report

    def flaky_save(output_dir, video_id, document):
        if video_id == "vid1":
            raise OSError("disk full")
        return real_save_video_report(output_dir, video_id, document)

    monkeypatch.setattr(extract_core_module, "save_video_report", flaky_save)

    run(
        youtube_service,
        analytics_service,
        tmp_path,
        date(2024, 2, 1),
        input_fn=lambda _prompt: "todos",
        print_fn=lambda _msg: None,
    )

    assert not (tmp_path / "por_video" / "vid1.json").exists()
    assert (tmp_path / "por_video" / "vid2.json").exists()
    assert (tmp_path / "consolidado.json").exists()


def test_run_prints_summary_and_failed_ids_even_when_all_videos_fail(tmp_path, monkeypatch):
    import src.extract_core as extract_core_module

    videos = [
        {"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z", "duration": "PT1M"},
        {"id": "vid2", "title": "Video 2", "published_at": "2024-01-02T00:00:00Z", "duration": "PT2M"},
    ]
    youtube_service = FakeYouTubeService(videos)
    analytics_service = ScriptedAnalyticsService(_always_empty_responder)
    monkeypatch.setattr(main_module, "list_channel_videos", fake_list_channel_videos)

    def always_fails(output_dir, video_id, document):
        raise OSError("disk full")

    monkeypatch.setattr(extract_core_module, "save_video_report", always_fails)
    messages = []

    run(
        youtube_service,
        analytics_service,
        tmp_path,
        date(2024, 2, 1),
        input_fn=lambda _prompt: "todos",
        print_fn=messages.append,
    )

    assert not (tmp_path / "consolidado.json").exists()
    summary = [m for m in messages if "Concluído" in m]
    assert summary and "0 vídeo(s) processado(s)" in summary[0] and "2 com erro" in summary[0]
    assert any("vid1" in m and "vid2" in m for m in messages if "erro" in m.lower())


def test_run_handles_channel_with_no_videos(tmp_path, monkeypatch):
    youtube_service = FakeYouTubeService([])
    analytics_service = ScriptedAnalyticsService(_always_empty_responder)
    monkeypatch.setattr(main_module, "list_channel_videos", fake_list_channel_videos)
    messages = []

    run(
        youtube_service,
        analytics_service,
        tmp_path,
        date(2024, 2, 1),
        input_fn=lambda _prompt: pytest.fail("should not prompt when there are no videos"),
        print_fn=messages.append,
    )

    assert any("Nenhum vídeo" in message for message in messages)
    assert not (tmp_path / "consolidado.json").exists()
    assert (tmp_path / "channel_videos.json").exists()
