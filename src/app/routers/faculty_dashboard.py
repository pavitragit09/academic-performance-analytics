"""Faculty dashboard API (APAS-F-031, F-023, F-024)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.app.database import get_db
from src.app.faculty_dashboard import course_dashboard
from src.app.models import Role, User
from src.app.routers.auth import require_roles

router = APIRouter(prefix="/dashboard", tags=["Faculty Dashboard"])


@router.get("/courses/{course_id}")
def get_course_dashboard(
    course_id: int,
    attendance_threshold: float = Query(75.0, ge=0, le=100, alias="attendanceThreshold"),
    marks_threshold: float = Query(40.0, ge=0, le=100, alias="marksThreshold"),
    window: int = Query(3, ge=2),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FACULTY, Role.ADMIN)),
) -> dict:
    """Class averages, marks distribution, exam summaries and at-risk students."""
    return course_dashboard(
        db, course_id, user, attendance_threshold, marks_threshold, window
    )
