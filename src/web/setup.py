# src/web/setup.py
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.web.paths import app_data_dir

router = APIRouter(prefix="/api/setup", tags=["setup"])


class SetupPayload(BaseModel):
    client_secret_json: str
    anthropic_api_key: str


def _client_secret_path(data_dir: Path) -> Path:
    return data_dir / "client_secret.json"


def _env_path(data_dir: Path) -> Path:
    return data_dir / ".env"


@router.get("/status")
def get_status():
    data_dir = app_data_dir()
    return {
        "client_secret_configured": _client_secret_path(data_dir).exists(),
        "anthropic_key_configured": _env_path(data_dir).exists(),
    }


@router.post("")
def save_setup(payload: SetupPayload):
    data_dir = app_data_dir()

    try:
        json.loads(payload.client_secret_json)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"client_secret.json inválido: {exc}")

    api_key = payload.anthropic_api_key.strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="a chave da API Anthropic não pode ficar em branco")

    _client_secret_path(data_dir).write_text(payload.client_secret_json, encoding="utf-8")
    _env_path(data_dir).write_text(f"ANTHROPIC_API_KEY={api_key}\n", encoding="utf-8")
    return {"ok": True}
