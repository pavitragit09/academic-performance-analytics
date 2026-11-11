"""Faculty and administrator dashboard API (APAS-F-031, F-023, F-024, F-032)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from src.app.database import get_db
from src.app.department_summary import department_summary, list_departments
from src.app.faculty_dashboard import course_dashboard, dashboard_courses
from src.app.models import Role, User
from src.app.routers.auth import require_roles

router = APIRouter(prefix="/dashboard", tags=["Faculty Dashboard"])


@router.get("/my-courses")
def get_my_courses(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FACULTY, Role.ADMIN)),
) -> dict:
    """Courses for the web UI's course picker (own courses for faculty, all for admin)."""
    return {"courses": dashboard_courses(db, user)}


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


@router.get("/departments")
def get_departments(
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles(Role.ADMIN)),
) -> dict:
    """Departments that have courses, for choosing a department summary."""
    return {"departments": list_departments(db)}


@router.get("/departments/{department}")
def get_department_summary(
    department: str,
    attendance_threshold: float = Query(75.0, ge=0, le=100, alias="attendanceThreshold"),
    marks_threshold: float = Query(40.0, ge=0, le=100, alias="marksThreshold"),
    window: int = Query(3, ge=2),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.ADMIN)),
) -> dict:
    """Average performance and at-risk count per course in one department (admin only)."""
    return department_summary(
        db, department, user, attendance_threshold, marks_threshold, window
    )
