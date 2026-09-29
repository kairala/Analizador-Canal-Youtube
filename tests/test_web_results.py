# tests/test_web_results.py
import json

from fastapi.testclient import TestClient

import src.web.results as results_module
from src.web.app import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(results_module, "app_data_dir", lambda: tmp_path)
    return TestClient(create_app())


def test_list_results_is_empty_when_nothing_extracted_or_analyzed(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/results")

    assert response.status_code == 200
    assert response.json() == {"results": []}


def test_list_results_flags_extraction_and_report_presence(tmp_path, monkeypatch):
    por_video = tmp_path / "output" / "por_video"
    por_video.mkdir(parents=True)
    (por_video / "vid1.json").write_text(json.dumps({"video": {"id": "vid1"}}), encoding="utf-8")

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "vid1.md").write_text("# relatório", encoding="utf-8")
    (reports_dir / "vid2.md").write_text("# relatório sem extração salva", encoding="utf-8")

    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/results")

    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {"video_id": "vid1", "has_extraction": True, "has_report": True},
            {"video_id": "vid2", "has_extraction": False, "has_report": True},
        ]
    }


def test_get_result_returns_extraction_and_report_when_both_exist(tmp_path, monkeypatch):
    por_video = tmp_path / "output" / "por_video"
    por_video.mkdir(parents=True)
    document = {"video": {"id": "vid1", "title": "Video 1"}, "totals": {"views": 100}}
    (por_video / "vid1.json").write_text(json.dumps(document), encoding="utf-8")

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "vid1.md").write_text("# relatório do vid1", encoding="utf-8")

    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/results/vid1")

    assert response.status_code == 200
    assert response.json() == {"video_id": "vid1", "extraction": document, "report": "# relatório do vid1"}


def test_get_result_returns_only_extraction_when_report_is_missing(tmp_path, monkeypatch):
    por_video = tmp_path / "output" / "por_video"
    por_video.mkdir(parents=True)
    document = {"video": {"id": "vid1", "title": "Video 1"}, "totals": {"views": 100}}
    (por_video / "vid1.json").write_text(json.dumps(document), encoding="utf-8")

    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/results/vid1")

    assert response.status_code == 200
    assert response.json() == {"video_id": "vid1", "extraction": document, "report": None}


def test_get_result_returns_only_report_when_extraction_is_missing(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "vid1.md").write_text("# relatório do vid1", encoding="utf-8")

    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/results/vid1")

    assert response.status_code == 200
    assert response.json() == {"video_id": "vid1", "extraction": None, "report": "# relatório do vid1"}


def test_get_result_returns_404_when_video_id_is_unknown(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/results/does-not-exist")

    assert response.status_code == 404


def test_get_result_treats_a_corrupted_extraction_file_as_unavailable(tmp_path, monkeypatch):
    # A file left mid-write (e.g. the app was closed during extraction) should
    # behave like a missing extraction, not 500 the whole detail endpoint.
    por_video = tmp_path / "output" / "por_video"
    por_video.mkdir(parents=True)
    (por_video / "vid1.json").write_text('{"video": {"id": "vid1"', encoding="utf-8")

    reports_dir = tmp_path / "reports"
    reports_dir.mkdir(parents=True)
    (reports_dir / "vid1.md").write_text("# relatório do vid1", encoding="utf-8")

    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/results/vid1")

    assert response.status_code == 200
    assert response.json() == {"video_id": "vid1", "extraction": None, "report": "# relatório do vid1"}
