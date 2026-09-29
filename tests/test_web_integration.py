# tests/test_web_integration.py
#
# src/web/extract_routes.py, src/web/analyze_routes.py and src/web/results.py
# each independently compute app_data_dir() / "output" / app_data_dir() /
# "reports". Every other test file monkeypatches app_data_dir in exactly ONE
# router module at a time, so no test ever exercises two routers against the
# same real data directory -- a path-convention drift between them would
# pass the entire suite green undetected. This test patches the actual root
# of app_data_dir() globally (platformdirs.user_data_dir, which every
# router's app_data_dir() call ultimately goes through -- see
# src/web/paths.py) so every router is forced to agree on the same
# tmp_path-based directory, and walks the real user journey across all of
# them: extract -> analyze -> browse.
from fastapi.testclient import TestClient

import src.web.extract_routes as extract_routes_module
from src.web.app import create_app
from src.web.services import get_analytics_service, get_anthropic_client, get_youtube_service


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
    pass


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


class ScriptedAnthropicClient:
    def __init__(self, responder):
        self.messages = ScriptedMessages(responder)


def _always_empty_analytics_responder(_kwargs):
    return {"columnHeaders": [], "rows": []}


def _always_ok_anthropic_responder(_kwargs):
    return FakeResponse([FakeTextBlock("## Resumo de desempenho\nok")])


def test_extract_analyze_and_browse_routers_agree_on_app_data_dir(tmp_path, monkeypatch):
    # Patch the root every router's app_data_dir() ultimately resolves
    # through, globally -- not per module -- so a path-convention drift
    # between extract_routes.py, analyze_routes.py and results.py would make
    # this test fail instead of silently passing.
    monkeypatch.setattr("platformdirs.user_data_dir", lambda _appname: str(tmp_path))

    videos = [{"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z"}]
    monkeypatch.setattr(extract_routes_module, "list_channel_videos", lambda _service: videos)

    app = create_app()
    app.dependency_overrides[get_youtube_service] = lambda: FakeYouTubeService()
    app.dependency_overrides[get_analytics_service] = lambda: ScriptedAnalyticsService(
        _always_empty_analytics_responder
    )
    app.dependency_overrides[get_anthropic_client] = lambda: ScriptedAnthropicClient(_always_ok_anthropic_responder)
    client = TestClient(app)

    # 1. Extract
    start_extract = client.post("/api/extract", json={"video_ids": ["vid1"]})
    assert start_extract.status_code == 200

    with client.stream("GET", "/api/extract/stream") as response:
        extract_log = "".join(response.iter_text())
    assert "Concluído: 1 vídeo(s) processado(s), 0 com erro." in extract_log

    # 2. The just-extracted video must show up as analyzable -- this is the
    # cross-router check: analyze_routes.py's app_data_dir() must resolve to
    # the same "output" directory extract_routes.py just wrote into.
    analyzable = client.get("/api/analyzable")
    assert analyzable.status_code == 200
    assert [v["id"] for v in analyzable.json()["videos"]] == ["vid1"]

    # 3. Analyze
    start_analyze = client.post("/api/analyze", json={"video_ids": ["vid1"]})
    assert start_analyze.status_code == 200

    with client.stream("GET", "/api/analyze/stream") as response:
        analyze_log = "".join(response.iter_text())
    assert "Concluído: 1 relatório(s) gerado(s), 0 com erro." in analyze_log

    # 4. Browse -- results.py's app_data_dir() must resolve to the same
    # "output" and "reports" directories the other two routers used.
    results = client.get("/api/results")
    assert results.status_code == 200
    assert results.json() == {
        "results": [{"video_id": "vid1", "has_extraction": True, "has_report": True}]
    }

    detail = client.get("/api/results/vid1")
    assert detail.status_code == 200
    body = detail.json()
    assert body["video_id"] == "vid1"
    assert body["extraction"] is not None
    assert body["extraction"]["video"]["id"] == "vid1"
    assert body["report"] is not None
    assert "Resumo de desempenho" in body["report"]
