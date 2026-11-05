"""Health check used for monitoring (SAD section 4.4)."""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.app.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    """Report that the API is running and can reach the database."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}
