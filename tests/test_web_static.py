# tests/test_web_static.py
from fastapi.testclient import TestClient

from src.web.app import create_app


def test_index_page_is_served_at_root():
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "YouTube Analytics Extractor" in response.text


def test_static_assets_are_served():
    client = TestClient(create_app())

    response = client.get("/static/app.js")

    assert response.status_code == 200
