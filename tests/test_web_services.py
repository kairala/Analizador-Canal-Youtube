import src.web.services as services_module


def test_get_youtube_service_uses_app_data_dir_paths_and_correct_api(tmp_path, monkeypatch):
    monkeypatch.setattr(services_module, "app_data_dir", lambda: tmp_path)

    captured = {}

    def fake_get_credentials(client_secret_path, token_path, scopes):
        captured["client_secret_path"] = client_secret_path
        captured["token_path"] = token_path
        captured["scopes"] = scopes
        return "fake-creds"

    def fake_build(api_name, api_version, credentials):
        captured["api_name"] = api_name
        captured["api_version"] = api_version
        captured["credentials"] = credentials
        return f"{api_name}-{api_version}-service"

    monkeypatch.setattr(services_module, "get_credentials", fake_get_credentials)
    monkeypatch.setattr(services_module, "build", fake_build)

    result = services_module.get_youtube_service()

    assert result == "youtube-v3-service"
    assert captured["client_secret_path"] == tmp_path / "client_secret.json"
    assert captured["token_path"] == tmp_path / "token.json"
    assert captured["credentials"] == "fake-creds"


def test_get_analytics_service_uses_youtubeanalytics_v2(tmp_path, monkeypatch):
    monkeypatch.setattr(services_module, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(services_module, "get_credentials", lambda *a, **k: "fake-creds")
    monkeypatch.setattr(
        services_module, "build", lambda api_name, api_version, credentials: (api_name, api_version)
    )

    result = services_module.get_analytics_service()

    assert result == ("youtubeAnalytics", "v2")


def test_get_anthropic_client_reads_api_key_from_app_data_env_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-test-999\n", encoding="utf-8")
    monkeypatch.setattr(services_module, "app_data_dir", lambda: tmp_path)

    captured = {}

    class FakeAnthropic:
        def __init__(self, api_key=None):
            captured["api_key"] = api_key

    monkeypatch.setattr(services_module.anthropic, "Anthropic", FakeAnthropic)

    services_module.get_anthropic_client()

    assert captured["api_key"] == "sk-test-999"
