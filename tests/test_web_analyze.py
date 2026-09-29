import json
import threading

from fastapi.testclient import TestClient

import src.web.analyze_routes as analyze_routes_module
from src.web.app import create_app
from src.web.services import get_anthropic_client


class FakeTextBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class FakeResponse:
    def __init__(self, content, stop_reason="end_turn"):
        self.content = content
        self.stop_reason = stop_reason


class _StreamContext:
    def __init__(self, response):
        self._response = response

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get_final_message(self):
        return self._response


class ScriptedMessages:
    def __init__(self, responder):
        self._responder = responder

    def stream(self, **kwargs):
        return _StreamContext(self._responder(kwargs))


class ScriptedClient:
    def __init__(self, responder):
        self.messages = ScriptedMessages(responder)


def _always_ok_responder(_kwargs):
    return FakeResponse([FakeTextBlock("## Resumo de desempenho\nok")])


def _write_document(por_video_dir, video_id, title, views=100):
    document = {"video": {"id": video_id, "title": title}, "totals": {"views": views}}
    (por_video_dir / f"{video_id}.json").write_text(json.dumps(document), encoding="utf-8")


def _client(tmp_path, monkeypatch, responder=_always_ok_responder):
    monkeypatch.setattr(analyze_routes_module, "app_data_dir", lambda: tmp_path)

    app = create_app()
    app.dependency_overrides[get_anthropic_client] = lambda: ScriptedClient(responder)
    return app, TestClient(app)


def test_get_analyzable_lists_extracted_videos(tmp_path, monkeypatch):
    por_video = tmp_path / "output" / "por_video"
    por_video.mkdir(parents=True)
    _write_document(por_video, "vid1", "Video 1")
    _app, client = _client(tmp_path, monkeypatch)

    response = client.get("/api/analyzable")

    assert response.status_code == 200
    assert response.json() == {"videos": [{"id": "vid1", "title": "Video 1"}]}


def test_analyze_stream_reports_progress_and_completion(tmp_path, monkeypatch):
    por_video = tmp_path / "output" / "por_video"
    por_video.mkdir(parents=True)
    _write_document(por_video, "vid1", "Video 1")
    _write_document(por_video, "vid2", "Video 2")
    _app, client = _client(tmp_path, monkeypatch)

    start_response = client.post("/api/analyze", json={"video_ids": ["vid1", "vid2"]})
    assert start_response.status_code == 200

    with client.stream("GET", "/api/analyze/stream") as response:
        body = "".join(response.iter_text())

    assert "Analisando 'Video 1'" in body
    assert "Concluído: 2 relatório(s) gerado(s), 0 com erro." in body
    assert (tmp_path / "reports" / "vid1.md").exists()
    assert (tmp_path / "reports" / "vid2.md").exists()


def test_analyze_rejects_when_no_valid_video_ids(tmp_path, monkeypatch):
    por_video = tmp_path / "output" / "por_video"
    por_video.mkdir(parents=True)
    _write_document(por_video, "vid1", "Video 1")
    _app, client = _client(tmp_path, monkeypatch)

    response = client.post("/api/analyze", json={"video_ids": ["does-not-exist"]})

    assert response.status_code == 400


def test_analyze_rejects_when_already_running(tmp_path, monkeypatch):
    por_video = tmp_path / "output" / "por_video"
    por_video.mkdir(parents=True)
    _write_document(por_video, "vid1", "Video 1")
    app, client = _client(tmp_path, monkeypatch)

    release = threading.Event()
    app.state.analyze_jobs.start("analyze", lambda print_fn: release.wait(timeout=2))

    try:
        response = client.post("/api/analyze", json={"video_ids": ["vid1"]})
        assert response.status_code == 409
    finally:
        release.set()
        list(app.state.analyze_jobs.stream("analyze"))
