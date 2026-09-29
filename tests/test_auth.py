from unittest.mock import MagicMock, patch

import pytest
from google_auth_oauthlib.flow import WSGITimeoutError

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
    flow.run_local_server.assert_called_once_with(port=0, timeout_seconds=300)
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
    flow.run_local_server.assert_called_once_with(port=0, timeout_seconds=300)
    assert result is new_creds
    assert token_path.read_text(encoding="utf-8") == '{"fresh": true}'


def test_get_credentials_propagates_a_readable_error_when_the_flow_times_out(tmp_path):
    # Without a timeout, run_local_server blocks forever if the browser
    # doesn't open or the user never completes/cancels the consent screen --
    # the calling HTTP request's threadpool worker (and, in the packaged
    # binary, the whole app window) would hang indefinitely. The 5-minute
    # timeout makes run_local_server raise WSGITimeoutError instead; that
    # must propagate as a normal exception (it's a subclass of
    # AttributeError, still an Exception) rather than being swallowed, so
    # the web app's catch-all handler can turn it into a readable error.
    token_path = tmp_path / "token.json"
    client_secret_path = tmp_path / "client_secret.json"

    flow = MagicMock()
    flow.run_local_server.side_effect = WSGITimeoutError("Timed out waiting for response from authorization server")

    with patch.object(auth.InstalledAppFlow, "from_client_secrets_file", return_value=flow):
        with pytest.raises(WSGITimeoutError):
            auth.get_credentials(client_secret_path, token_path, ["scope1"])

    flow.run_local_server.assert_called_once_with(port=0, timeout_seconds=300)
    assert not token_path.exists()
