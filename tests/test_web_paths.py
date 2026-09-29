# tests/test_web_paths.py
from src.web.paths import app_data_dir


def test_app_data_dir_creates_and_returns_a_directory(monkeypatch, tmp_path):
    target = tmp_path / "yt-data-extractor"
    monkeypatch.setattr("platformdirs.user_data_dir", lambda _appname: str(target))

    result = app_data_dir()

    assert result == target
    assert result.is_dir()
