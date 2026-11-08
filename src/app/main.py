"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from src.app.config import API_PREFIX
from src.app.database import init_db
from src.app.errors import register_error_handlers
from src.app.routers import auth, dashboard, exams, health, risk
from src.app.routers.auth import get_current_user


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Initialize database tables when the application starts."""
    init_db()
    yield


def create_app() -> FastAPI:
    """Create the APAS application."""

    application = FastAPI(
        title="Academic Performance Analytics System",
        lifespan=lifespan,
        dependencies=[
            Depends(get_current_user),
        ],
    )

    # Register standard error responses.
    register_error_handlers(application)

    # Register API routers.
    application.include_router(health.router, prefix=API_PREFIX)
    application.include_router(auth.router, prefix=API_PREFIX)
    application.include_router(exams.router, prefix=API_PREFIX)
    application.include_router(risk.router, prefix=API_PREFIX)
    application.include_router(dashboard.router, prefix=API_PREFIX)

    return application


app = create_app()