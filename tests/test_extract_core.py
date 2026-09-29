from datetime import date

from src.extract_core import extract_selected_videos, extract_video


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


def _always_empty_responder(_kwargs):
    return {"columnHeaders": [], "rows": []}


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


def test_extract_selected_videos_saves_each_and_returns_documents(tmp_path):
    videos = [
        {"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z"},
        {"id": "vid2", "title": "Video 2", "published_at": "2024-01-02T00:00:00Z"},
    ]
    service = ScriptedAnalyticsService(_always_empty_responder)

    documents, failed_ids = extract_selected_videos(
        service, tmp_path, date(2024, 2, 1), videos, print_fn=lambda _m: None
    )

    assert len(documents) == 2
    assert failed_ids == []
    assert (tmp_path / "por_video" / "vid1.json").exists()
    assert (tmp_path / "por_video" / "vid2.json").exists()


def test_extract_selected_videos_continues_when_saving_one_video_fails(tmp_path, monkeypatch):
    import src.extract_core as extract_core_module

    videos = [
        {"id": "vid1", "title": "Video 1", "published_at": "2024-01-01T00:00:00Z"},
        {"id": "vid2", "title": "Video 2", "published_at": "2024-01-02T00:00:00Z"},
    ]
    service = ScriptedAnalyticsService(_always_empty_responder)

    real_save = extract_core_module.save_video_report

    def flaky_save(output_dir, video_id, document):
        if video_id == "vid1":
            raise OSError("disk full")
        return real_save(output_dir, video_id, document)

    monkeypatch.setattr(extract_core_module, "save_video_report", flaky_save)

    documents, failed_ids = extract_selected_videos(
        service, tmp_path, date(2024, 2, 1), videos, print_fn=lambda _m: None
    )

    assert failed_ids == ["vid1"]
    assert len(documents) == 1
    assert documents[0]["video"]["id"] == "vid2"
