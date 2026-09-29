# src/web/app.py
from fastapi import FastAPI

from src.web.setup import router as setup_router


def create_app() -> FastAPI:
    app = FastAPI(title="YouTube Analytics Extractor")
    app.include_router(setup_router)
    return app
