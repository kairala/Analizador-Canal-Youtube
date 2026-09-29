import pytest

from src.ai_report import build_report_prompt, generate_report


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


class FakeMessages:
    def __init__(self, response):
        self._response = response
        self.last_kwargs = None

    def stream(self, **kwargs):
        self.last_kwargs = kwargs
        return _StreamContext(self._response)


class FakeClient:
    def __init__(self, response):
        self.messages = FakeMessages(response)


def test_build_report_prompt_includes_video_and_averages_json():
    video_document = {"video": {"id": "vid1", "title": "Video 1"}, "totals": {"views": 100}}
    channel_averages = {"views": 50}

    prompt = build_report_prompt(video_document, channel_averages)

    assert "vid1" in prompt
    assert "Video 1" in prompt
    assert '"views": 100' in prompt
    assert '"views": 50' in prompt


def test_generate_report_returns_text_from_response():
    response = FakeResponse([FakeTextBlock("## Resumo de desempenho\nok")])
    client = FakeClient(response)
    video_document = {"video": {"id": "vid1", "title": "Video 1"}, "totals": {"views": 100}}
    channel_averages = {"views": 50}

    result = generate_report(client, video_document, channel_averages)

    assert "Resumo de desempenho" in result
    assert client.messages.last_kwargs["model"] == "claude-opus-5"
    assert client.messages.last_kwargs["thinking"] == {"type": "adaptive"}
    assert client.messages.last_kwargs["output_config"] == {"effort": "medium"}
    assert client.messages.last_kwargs["max_tokens"] >= 8192
    assert isinstance(client.messages.last_kwargs["system"], str)
    assert client.messages.last_kwargs["system"]
    assert client.messages.last_kwargs["messages"] == [
        {"role": "user", "content": build_report_prompt(video_document, channel_averages)}
    ]


def test_generate_report_raises_on_refusal():
    response = FakeResponse([], stop_reason="refusal")
    client = FakeClient(response)
    video_document = {"video": {"id": "vid1"}, "totals": {}}

    with pytest.raises(RuntimeError):
        generate_report(client, video_document, {})


def test_generate_report_raises_when_response_is_incomplete():
    # e.g. thinking + response text together hit the max_tokens cap — the
    # model never reached a natural end_turn, so the report is truncated.
    response = FakeResponse([FakeTextBlock("## Resumo de desempenho\ntrunc")], stop_reason="max_tokens")
    client = FakeClient(response)
    video_document = {"video": {"id": "vid1"}, "totals": {}}

    with pytest.raises(RuntimeError):
        generate_report(client, video_document, {})


def test_generate_report_raises_when_response_has_no_text():
    response = FakeResponse([], stop_reason="end_turn")
    client = FakeClient(response)
    video_document = {"video": {"id": "vid1"}, "totals": {}}

    with pytest.raises(RuntimeError):
        generate_report(client, video_document, {})
