"""Administrator department summary (APAS-F-032, SAD: GET /api/v1/dashboard/departments/{deptId}).

A course belongs to the department of the faculty member who teaches it. Every course
figure comes from course_dashboard, so the summary always agrees with the course dashboards
and with the at-risk rules (TC-Dash-03: totals match the underlying student data).
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.analytics import average_marks
from src.app.errors import AppError
from src.app.faculty_dashboard import course_dashboard
from src.app.models import Course, Faculty, User


def list_departments(db: Session) -> list[str]:
    """Departments that have at least one course, in alphabetical order."""
    rows = db.scalars(
        select(Faculty.department)
        .join(Course, Course.faculty_id == Faculty.id)
        .distinct()
        .order_by(Faculty.department)
    )
    return list(rows)


def department_summary(
    db: Session,
    department: str,
    user: User,
    attendance_threshold: float = 75.0,
    marks_threshold: float = 40.0,
    window: int = 3,
) -> dict:
    """Average performance and at-risk count for each course in one department."""
    courses = db.execute(
        select(Course.id, Faculty.department)
        .join(Faculty, Faculty.id == Course.faculty_id)
        .where(func.lower(Faculty.department) == department.strip().lower())
        .order_by(Course.code)
    ).all()
    if not courses:
        raise AppError(404, "NOT_FOUND", "Department not found or has no courses")

    rows = []
    student_averages = []
    for course_id, _department in courses:
        dashboard = course_dashboard(
            db, course_id, user, attendance_threshold, marks_threshold, window
        )
        student_averages.extend(
            s["averageMarks"] for s in dashboard["students"] if s["averageMarks"] is not None
        )
        rows.append({
            "courseId": dashboard["courseId"],
            "code": dashboard["courseCode"],
            "title": dashboard["courseTitle"],
            "enrolled": dashboard["enrolled"],
            "average": dashboard["classAverage"],
            "atRiskCount": len(dashboard["atRisk"]),
        })

    return {
        "department": courses[0][1],
        "totals": {
            "courses": len(rows),
            "enrolled": sum(row["enrolled"] for row in rows),
            "average": average_marks(student_averages) if student_averages else None,
            "atRiskCount": sum(row["atRiskCount"] for row in rows),
        },
        "courses": rows,
    }
