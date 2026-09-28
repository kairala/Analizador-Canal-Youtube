from unittest.mock import MagicMock, patch

from src import auth


def test_get_credentials_returns_cached_valid_credentials(tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")
    client_secret_path = tmp_path / "client_secret.json"

    cached_creds = MagicMock(valid=True)

    with patch.object(auth.Credentials, "from_authorized_user_file", return_value=cached_creds) as loader, \
         patch.object(auth.InstalledAppFlow, "from_client_secrets_file") as flow_factory:
        result = auth.get_credentials(client_secret_path, token_path, ["scope1"])

    loader.assert_called_once_with(str(token_path), ["scope1"])
    flow_factory.assert_not_called()
    assert result is cached_creds


def test_get_credentials_refreshes_expired_token(tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")
    client_secret_path = tmp_path / "client_secret.json"

    expired_creds = MagicMock(valid=False, expired=True, refresh_token="refresh-me")
    expired_creds.to_json.return_value = '{"refreshed": true}'

    with patch.object(auth.Credentials, "from_authorized_user_file", return_value=expired_creds), \
         patch.object(auth.InstalledAppFlow, "from_client_secrets_file") as flow_factory:
        result = auth.get_credentials(client_secret_path, token_path, ["scope1"])

    expired_creds.refresh.assert_called_once()
    flow_factory.assert_not_called()
    assert result is expired_creds
    assert token_path.read_text(encoding="utf-8") == '{"refreshed": true}'


def test_get_credentials_falls_back_to_flow_when_refresh_fails(tmp_path):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")
    client_secret_path = tmp_path / "client_secret.json"

    expired_creds = MagicMock(valid=False, expired=True, refresh_token="revoked")
    expired_creds.refresh.side_effect = Exception("invalid_grant")

    new_creds = MagicMock()
    new_creds.to_json.return_value = '{"fresh": true}'
    flow = MagicMock()
    flow.run_local_server.return_value = new_creds

    with patch.object(auth.Credentials, "from_authorized_user_file", return_value=expired_creds), \
         patch.object(auth.InstalledAppFlow, "from_client_secrets_file", return_value=flow) as flow_factory:
        result = auth.get_credentials(client_secret_path, token_path, ["scope1"])

    flow_factory.assert_called_once_with(str(client_secret_path), ["scope1"])
    flow.run_local_server.assert_called_once_with(port=0)
    assert result is new_creds
    assert token_path.read_text(encoding="utf-8") == '{"fresh": true}'


def test_get_credentials_runs_flow_when_no_token_file(tmp_path):
    token_path = tmp_path / "token.json"
    client_secret_path = tmp_path / "client_secret.json"

    new_creds = MagicMock()
    new_creds.to_json.return_value = '{"fresh": true}'
    flow = MagicMock()
    flow.run_local_server.return_value = new_creds

    with patch.object(auth.InstalledAppFlow, "from_client_secrets_file", return_value=flow) as flow_factory:
        result = auth.get_credentials(client_secret_path, token_path, ["scope1"])

    flow_factory.assert_called_once_with(str(client_secret_path), ["scope1"])
    assert result is new_creds
    assert token_path.read_text(encoding="utf-8") == '{"fresh": true}'
