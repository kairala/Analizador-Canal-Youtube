from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def get_credentials(client_secret_path: Path, token_path: Path, scopes: list[str] = SCOPES) -> Credentials:
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception:
            creds = None

    flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), scopes)
    # Without a timeout this blocks the calling thread forever if the browser
    # doesn't open or the user never completes/cancels the Google consent
    # screen -- in the packaged binary (console=False) that leaves the app
    # window showing nothing, with no way to recover short of killing the
    # process. `run_local_server` raises WSGITimeoutError (a subclass of
    # AttributeError, so still a normal Exception) when this fires, which the
    # web app's catch-all exception handler turns into a readable JSON error.
    creds = flow.run_local_server(port=0, timeout_seconds=300)
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return creds
