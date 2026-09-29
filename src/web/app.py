# src/web/app.py
from fastapi import FastAPI

from src.web.analyze_routes import router as analyze_router
from src.web.extract_routes import router as extract_router
from src.web.jobs import JobRegistry
from src.web.setup import router as setup_router


def create_app() -> FastAPI:
    app = FastAPI(title="YouTube Analytics Extractor")
    app.state.extract_jobs = JobRegistry()
    app.state.analyze_jobs = JobRegistry()
    app.include_router(setup_router)
    app.include_router(extract_router)
    app.include_router(analyze_router)
    return app
