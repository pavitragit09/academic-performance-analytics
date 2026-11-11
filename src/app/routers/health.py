"""Health check and availability monitoring (SAD section 4.4, APAS-NF-002)."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.app.availability import get_availability_report, record_probe
from src.app.database import get_db
from src.app.models import Role, User
from src.app.routers.auth import require_roles

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    """Report that the API is running and can reach the database."""
    try:
        db.execute(text("SELECT 1"))
        record_probe(is_success=True)
        return {"status": "ok", "database": "ok"}
    except Exception:
        record_probe(is_success=False)
        raise


@router.get("/availability")
def availability(
    _user: User = Depends(require_roles(Role.ADMIN)),
) -> dict:
    """Availability metrics and 99.5% uptime target tracking (Admin only, APAS-NF-002)."""
    return get_availability_report()
