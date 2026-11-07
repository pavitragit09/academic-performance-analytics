"""FastAPI application entry point. Run with: uvicorn src.app.main:app --reload"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.app.config import API_PREFIX
from src.app.database import init_db
from src.app.errors import register_error_handlers
from src.app.routers import exams, health

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Create any missing tables when the server starts."""
    init_db()
    yield


def create_app() -> FastAPI:
    """Build the application: routers under /api/v1 and standard errors."""
    application = FastAPI(title="Academic Performance Analytics System", lifespan=lifespan)
    register_error_handlers(application)
    application.include_router(health.router, prefix=API_PREFIX)
    application.include_router(exams.router, prefix=API_PREFIX)
    return application


app = create_app()