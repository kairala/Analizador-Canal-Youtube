# src/web/app.py
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.web.analyze_routes import router as analyze_router
from src.web.extract_routes import router as extract_router
from src.web.jobs import JobRegistry
from src.web.results import router as results_router
from src.web.setup import router as setup_router

STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="YouTube Analytics Extractor")
    app.state.extract_jobs = JobRegistry()
    app.state.analyze_jobs = JobRegistry()
    app.include_router(setup_router)
    app.include_router(extract_router)
    app.include_router(analyze_router)
    app.include_router(results_router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    return app
