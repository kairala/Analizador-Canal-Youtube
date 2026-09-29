# src/web/app.py
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
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

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request, exc):
        # Any exception that isn't an explicit HTTPException would otherwise fall
        # through to Starlette's default plain-text 500 response, which the
        # frontend's `response.json()` calls can't parse — turning every
        # unexpected backend error into a silent, invisible failure in the UI.
        return JSONResponse(status_code=500, content={"detail": str(exc) or type(exc).__name__})

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    return app
