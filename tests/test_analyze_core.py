import json

from src.analyze_core import analyze_selected_documents


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


def test_analyze_selected_documents_writes_a_report_per_video(tmp_path):
    documents = [
        {"video": {"id": "vid1", "title": "Video 1"}, "totals": {"views": 100}},
        {"video": {"id": "vid2", "title": "Video 2"}, "totals": {"views": 200}},
    ]
    client = ScriptedClient(_always_ok_responder)
    reports_dir = tmp_path / "reports"

    processed_ids, failed_ids = analyze_selected_documents(
        client, documents, {"views": 150}, reports_dir, print_fn=lambda _m: None
    )

    assert processed_ids == ["vid1", "vid2"]
    assert failed_ids == []
    assert (reports_dir / "vid1.md").exists()
    assert "Resumo de desempenho" in (reports_dir / "vid1.md").read_text(encoding="utf-8")


def test_analyze_selected_documents_continues_when_one_video_fails(tmp_path):
    documents = [
        {"video": {"id": "vid1", "title": "Video 1"}, "totals": {"views": 100}},
        {"video": {"id": "vid2", "title": "Video 2"}, "totals": {"views": 200}},
    ]

    def responder(kwargs):
        if "vid1" in kwargs["messages"][0]["content"]:
            raise RuntimeError("rate limited")
        return FakeResponse([FakeTextBlock("## Resumo de desempenho\nok")])

    client = ScriptedClient(responder)
    reports_dir = tmp_path / "reports"
    messages = []

    processed_ids, failed_ids = analyze_selected_documents(
        client, documents, {}, reports_dir, print_fn=messages.append
    )

    assert processed_ids == ["vid2"]
    assert failed_ids == ["vid1"]
    assert not (reports_dir / "vid1.md").exists()
    assert (reports_dir / "vid2.md").exists()
    assert any("erro" in m.lower() and "vid1" in m for m in messages)
