# tests/test_web_app.py
from fastapi.testclient import TestClient

from src.web.app import create_app
from src.web.services import get_youtube_service


def test_unhandled_exception_returns_json_500_instead_of_plaintext(monkeypatch):
    # Any backend error that isn't an explicit HTTPException (bad
    # client_secret.json, a YouTube account with no channel, a corrupted
    # por_video/*.json file, ...) must not fall through to Starlette's default
    # plain-text 500 response — the frontend always does `response.json()` on
    # error bodies, and a plain-text body would make that throw silently.
    def _boom():
        raise RuntimeError("conta do YouTube sem canal")

    app = create_app()
    app.dependency_overrides[get_youtube_service] = _boom
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get("/api/videos")

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "conta do YouTube sem canal"}
