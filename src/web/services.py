import anthropic
from dotenv import dotenv_values
from googleapiclient.discovery import build

from src.auth import SCOPES, get_credentials
from src.web.paths import app_data_dir


def get_youtube_service():
    data_dir = app_data_dir()
    credentials = get_credentials(data_dir / "client_secret.json", data_dir / "token.json", SCOPES)
    return build("youtube", "v3", credentials=credentials)


def get_analytics_service():
    data_dir = app_data_dir()
    credentials = get_credentials(data_dir / "client_secret.json", data_dir / "token.json", SCOPES)
    return build("youtubeAnalytics", "v2", credentials=credentials)


def get_anthropic_client():
    data_dir = app_data_dir()
    env = dotenv_values(data_dir / ".env")
    return anthropic.Anthropic(api_key=env.get("ANTHROPIC_API_KEY"))
