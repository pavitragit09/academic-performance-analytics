"""Report export API (APAS-F-033, SAD: GET /api/v1/reports/courses/{courseId})."""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from src.app.database import get_db
from src.app.faculty_dashboard import course_dashboard
from src.app.models import Role, User
from src.app.reports import course_report_csv, course_report_pdf, report_filename
from src.app.routers.auth import require_roles

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get(
    "/courses/{course_id}",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}, "application/pdf": {}}}},
)
def export_course_report(
    course_id: int,
    report_format: Literal["csv", "pdf"] = Query("csv", alias="format"),
    attendance_threshold: float = Query(75.0, ge=0, le=100, alias="attendanceThreshold"),
    marks_threshold: float = Query(40.0, ge=0, le=100, alias="marksThreshold"),
    window: int = Query(3, ge=2),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FACULTY, Role.ADMIN)),
) -> Response:
    """Download the course dashboard as a CSV or PDF file."""
    dashboard = course_dashboard(
        db, course_id, user, attendance_threshold, marks_threshold, window
    )
    if report_format == "pdf":
        content, media_type = course_report_pdf(dashboard), "application/pdf"
    else:
        content, media_type = course_report_csv(dashboard), "text/csv; charset=utf-8"
    filename = report_filename(dashboard, report_format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
