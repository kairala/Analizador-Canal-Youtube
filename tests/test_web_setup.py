# tests/test_web_setup.py
import json

from fastapi.testclient import TestClient

import src.web.setup as web_setup_module
from src.web.app import create_app


def _client(tmp_path, monkeypatch):
    monkeypatch.setattr(web_setup_module, "app_data_dir", lambda: tmp_path)
    return TestClient(create_app())


def test_status_reports_not_configured_when_nothing_saved(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.get("/api/setup/status")

    assert response.status_code == 200
    assert response.json() == {"client_secret_configured": False, "anthropic_key_configured": False}


def test_save_setup_persists_files_and_status_reflects_it(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    payload = {
        "client_secret_json": json.dumps({"installed": {"client_id": "abc"}}),
        "anthropic_api_key": "sk-test-123",
    }

    response = client.post("/api/setup", json=payload)

    assert response.status_code == 200
    assert (tmp_path / "client_secret.json").read_text(encoding="utf-8") == payload["client_secret_json"]
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "ANTHROPIC_API_KEY=sk-test-123\n"

    status = client.get("/api/setup/status").json()
    assert status == {"client_secret_configured": True, "anthropic_key_configured": True}


def test_save_setup_rejects_invalid_json(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/api/setup", json={"client_secret_json": "not-json", "anthropic_api_key": "sk-test"}
    )

    assert response.status_code == 400
    assert not (tmp_path / "client_secret.json").exists()


def test_save_setup_rejects_blank_anthropic_key(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    payload = {
        "client_secret_json": json.dumps({"installed": {"client_id": "abc"}}),
        "anthropic_api_key": "   ",
    }

    response = client.post("/api/setup", json=payload)

    assert response.status_code == 400
    assert not (tmp_path / ".env").exists()

    status = client.get("/api/setup/status").json()
    assert status["anthropic_key_configured"] is False
