"""Administrator settings API for configurable thresholds (APAS-F-025, SAD)."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from src.app.database import get_db
from src.app.models import Role, User
from src.app.routers.auth import require_roles
from src.app.thresholds import get_analytics_thresholds, update_analytics_thresholds

router = APIRouter(prefix="/settings", tags=["Settings"])


class ThresholdsResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    attendance_threshold: float = Field(alias="attendanceThreshold")
    marks_threshold: float = Field(alias="marksThreshold")
    trend_window: int = Field(alias="trendWindow")
    updated_at: str = Field(alias="updatedAt")


class ThresholdsUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    attendance_threshold: float = Field(ge=0, le=100, alias="attendanceThreshold")
    marks_threshold: float = Field(ge=0, le=100, alias="marksThreshold")
    trend_window: int = Field(ge=2, alias="trendWindow")


@router.get("/thresholds", response_model=ThresholdsResponse)
def get_thresholds(
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles(Role.ADMIN)),
) -> dict:
    """Retrieve the current administrator-configured analytics thresholds."""
    current = get_analytics_thresholds(db)
    return {
        "attendanceThreshold": current.attendance_threshold,
        "marksThreshold": current.marks_threshold,
        "trendWindow": current.trend_window,
        "updatedAt": current.updated_at.isoformat() if current.updated_at else "",
    }


@router.put("/thresholds", response_model=ThresholdsResponse)
def update_thresholds(
    body: ThresholdsUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.ADMIN)),
) -> dict:
    """Update administrator-configured analytics thresholds (audited)."""
    client_ip = request.client.host if request.client else None
    updated = update_analytics_thresholds(
        db=db,
        attendance_threshold=body.attendance_threshold,
        marks_threshold=body.marks_threshold,
        trend_window=body.trend_window,
        user_id=user.id,
        ip_address=client_ip,
    )
    return {
        "attendanceThreshold": updated.attendance_threshold,
        "marksThreshold": updated.marks_threshold,
        "trendWindow": updated.trend_window,
        "updatedAt": updated.updated_at.isoformat() if updated.updated_at else "",
    }
