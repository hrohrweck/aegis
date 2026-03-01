"""FastAPI dashboard application setup."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = TEMPLATES_DIR / "static"


def create_dashboard_app() -> FastAPI:
    """Create the FastAPI dashboard application."""
    app = FastAPI(
        title="Aegis Dashboard",
        description="Monitoring dashboard for the Aegis AI content curation bot",
        version="0.1.0",
    )

    # Mount static files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app


templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
