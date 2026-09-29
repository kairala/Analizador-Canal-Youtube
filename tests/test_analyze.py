import json

import pytest

from analyze import run, select_videos


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


def _write_document(por_video_dir, video_id, title, views=100):
    document = {"video": {"id": video_id, "title": title}, "totals": {"views": views}}
    (por_video_dir / f"{video_id}.json").write_text(json.dumps(document), encoding="utf-8")


def _always_ok_responder(_kwargs):
    return FakeResponse([FakeTextBlock("## Resumo de desempenho\nok")])


def test_select_videos_returns_chosen_subset():
    documents = [
        {"video": {"id": "v1", "title": "A"}},
        {"video": {"id": "v2", "title": "B"}},
        {"video": {"id": "v3", "title": "C"}},
    ]
    inputs = iter(["1,3"])

    selected = select_videos(documents, input_fn=lambda _p: next(inputs), print_fn=lambda _m: None)

    assert selected == [documents[0], documents[2]]


def test_select_videos_retries_on_invalid_input():
    documents = [{"video": {"id": "v1", "title": "A"}}]
    inputs = iter(["not-a-number", "1"])
    messages = []

    selected = select_videos(documents, input_fn=lambda _p: next(inputs), print_fn=messages.append)

    assert selected == [documents[0]]
    assert any("inválida" in m for m in messages)


def test_run_generates_reports_for_all_selected_videos(tmp_path):
    output_dir = tmp_path / "output"
    por_video = output_dir / "por_video"
    por_video.mkdir(parents=True)
    _write_document(por_video, "vid1", "Video 1")
    _write_document(por_video, "vid2", "Video 2")

    client = ScriptedClient(_always_ok_responder)
    reports_dir = tmp_path / "reports"

    run(client, output_dir, reports_dir, input_fn=lambda _p: "todos", print_fn=lambda _m: None)

    assert (reports_dir / "vid1.md").exists()
    assert (reports_dir / "vid2.md").exists()
    assert "Resumo de desempenho" in (reports_dir / "vid1.md").read_text(encoding="utf-8")


def test_run_continues_when_one_video_fails(tmp_path):
    output_dir = tmp_path / "output"
    por_video = output_dir / "por_video"
    por_video.mkdir(parents=True)
    _write_document(por_video, "vid1", "Video 1")
    _write_document(por_video, "vid2", "Video 2")

    def responder(kwargs):
        if "vid1" in kwargs["messages"][0]["content"]:
            raise RuntimeError("rate limited")
        return FakeResponse([FakeTextBlock("## Resumo de desempenho\nok")])

    client = ScriptedClient(responder)
    reports_dir = tmp_path / "reports"
    messages = []

    run(client, output_dir, reports_dir, input_fn=lambda _p: "todos", print_fn=messages.append)

    assert not (reports_dir / "vid1.md").exists()
    assert (reports_dir / "vid2.md").exists()
    assert any("erro" in m.lower() and "vid1" in m for m in messages)


def test_run_prints_summary_even_when_all_videos_fail(tmp_path):
    output_dir = tmp_path / "output"
    por_video = output_dir / "por_video"
    por_video.mkdir(parents=True)
    _write_document(por_video, "vid1", "Video 1")
    _write_document(por_video, "vid2", "Video 2")

    def always_fails(_kwargs):
        raise RuntimeError("no api key")

    client = ScriptedClient(always_fails)
    reports_dir = tmp_path / "reports"
    messages = []

    run(client, output_dir, reports_dir, input_fn=lambda _p: "todos", print_fn=messages.append)

    assert not (reports_dir / "vid1.md").exists()
    assert not (reports_dir / "vid2.md").exists()
    summary = [m for m in messages if "Concluído" in m]
    assert summary and "0 relatório(s) gerado(s)" in summary[0] and "2 com erro" in summary[0]


def test_run_handles_no_documents_found(tmp_path):
    output_dir = tmp_path / "output"
    reports_dir = tmp_path / "reports"
    messages = []

    run(
        ScriptedClient(_always_ok_responder),
        output_dir,
        reports_dir,
        input_fn=lambda _p: pytest.fail("should not prompt when there are no videos"),
        print_fn=messages.append,
    )

    assert any("Nenhum vídeo" in m for m in messages)
    assert not reports_dir.exists()
