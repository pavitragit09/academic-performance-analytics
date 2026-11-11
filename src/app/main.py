"""FastAPI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.app.config import API_PREFIX
from src.app.database import init_db
from src.app.errors import register_error_handlers
from src.app.tls import TLSEnforcementMiddleware
from src.app.routers import (
    assignments,
    auth,
    dashboard,
    data_entry,
    exams,
    faculty_dashboard,
    health,
    interventions,
    records,
    reports,
    risk,
    settings,
    users,
)
from src.app.routers.auth import get_current_user

WEB_DIR = Path(__file__).parent / "web"


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

    # Enforce TLS 1.2+ when APAS_ENFORCE_TLS is set (APAS-SR-001).
    application.add_middleware(TLSEnforcementMiddleware)

    # Register API routers.
    application.include_router(health.router, prefix=API_PREFIX)
    application.include_router(auth.router, prefix=API_PREFIX)
    application.include_router(exams.router, prefix=API_PREFIX)
    application.include_router(users.router, prefix=API_PREFIX)
    application.include_router(risk.router, prefix=API_PREFIX)
    application.include_router(dashboard.router, prefix=API_PREFIX)
    application.include_router(assignments.router, prefix=API_PREFIX)
    application.include_router(faculty_dashboard.router, prefix=API_PREFIX)
    application.include_router(records.router, prefix=API_PREFIX)
    application.include_router(data_entry.router, prefix=API_PREFIX)
    application.include_router(reports.router, prefix=API_PREFIX)
    application.include_router(settings.router, prefix=API_PREFIX)
    application.include_router(interventions.router, prefix=API_PREFIX)



    # Web UI (APAS-NF-004): static pages that call the API above.
    application.mount("/app", StaticFiles(directory=WEB_DIR, html=True), name="web")

    @application.get("/", include_in_schema=False)
    def home() -> RedirectResponse:
        return RedirectResponse("/app/")

    return application


app = create_app()
