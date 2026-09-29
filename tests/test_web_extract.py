import threading

from fastapi.testclient import TestClient

import src.web.extract_routes as extract_routes_module
from src.web.app import create_app
from src.web.services import get_analytics_service, get_youtube_service


class ScriptedAnalyticsService:
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


def _always_empty_responder(_kwargs):
    return {"columnHeaders": [], "rows": []}


def _client(tmp_path, monkeypatch, videos):
    monkeypatch.setattr(extract_routes_module, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(extract_routes_module, "list_channel_videos", lambda _service: videos)

    app = create_app()
    app.dependency_overrides[get_youtube_service] = lambda: FakeYouTubeService(videos)
    app.dependency_overrides[get_analytics_service] = lambda: ScriptedAnalyticsService(_always_empty_responder)
    return app, TestClient(app)


def test_get_videos_returns_channel_videos_and_saves_snapshot(tmp_path, monkeypatch):
    videos = [{"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z"}]
    _app, client = _client(tmp_path, monkeypatch, videos)

    response = client.get("/api/videos")

    assert response.status_code == 200
    assert response.json() == {"videos": videos}
    assert (tmp_path / "output" / "channel_videos.json").exists()


def test_extract_stream_reports_progress_and_completion(tmp_path, monkeypatch):
    videos = [
        {"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z"},
        {"id": "vid2", "title": "Video 2", "published_at": "2024-01-02T00:00:00Z"},
    ]
    _app, client = _client(tmp_path, monkeypatch, videos)

    start_response = client.post("/api/extract", json={"video_ids": ["vid1", "vid2"]})
    assert start_response.status_code == 200

    with client.stream("GET", "/api/extract/stream") as response:
        body = "".join(response.iter_text())

    assert "Processando 'Video 1'" in body
    assert "Processando 'Video 2'" in body
    assert "Concluído: 2 vídeo(s) processado(s), 0 com erro." in body
    assert (tmp_path / "output" / "por_video" / "vid1.json").exists()
    assert (tmp_path / "output" / "por_video" / "vid2.json").exists()


def test_extract_processes_only_the_valid_ids_from_a_mixed_selection(tmp_path, monkeypatch):
    videos = [{"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z"}]
    _app, client = _client(tmp_path, monkeypatch, videos)

    start_response = client.post("/api/extract", json={"video_ids": ["vid1", "does-not-exist"]})
    assert start_response.status_code == 200

    with client.stream("GET", "/api/extract/stream") as response:
        body = "".join(response.iter_text())

    assert "Processando 'Video 1'" in body
    assert "Concluído: 1 vídeo(s) processado(s), 0 com erro." in body
    assert (tmp_path / "output" / "por_video" / "vid1.json").exists()


def test_extract_rejects_when_no_valid_video_ids(tmp_path, monkeypatch):
    videos = [{"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z"}]
    _app, client = _client(tmp_path, monkeypatch, videos)

    response = client.post("/api/extract", json={"video_ids": ["does-not-exist"]})

    assert response.status_code == 400


def test_extract_rejects_when_already_running(tmp_path, monkeypatch):
    videos = [{"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z"}]
    app, client = _client(tmp_path, monkeypatch, videos)

    release = threading.Event()
    app.state.extract_jobs.start("extract", lambda print_fn: release.wait(timeout=2))

    try:
        response = client.post("/api/extract", json={"video_ids": ["vid1"]})
        assert response.status_code == 409
    finally:
        release.set()
        list(app.state.extract_jobs.stream("extract"))
