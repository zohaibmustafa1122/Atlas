"""ATLAS FastAPI application entry point.

Phase 1 exposes only a health check. Later phases add /api routes for
data, entities, graph, analytics, and the AI assistant (see app/api/).
"""

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database.database import init_db

settings = get_settings()
logger = get_logger(__name__)

app = FastAPI(title=settings.app_name, description="Open Data Intelligence & Decision Support Platform")


@app.on_event("startup")
def on_startup() -> None:
    logger.info("Starting %s (%s)", settings.app_name, settings.app_env)
    init_db()


@app.get("/")
def root() -> dict:
    return {"app": settings.app_name, "status": "ok", "environment": settings.app_env}


@app.get("/health")
def health() -> dict:
    return {"status": "healthy"}
