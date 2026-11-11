"""Faculty course dashboard (APAS-F-031, SAD: GET /api/v1/dashboard/courses/{courseId}).

Built from the Sprint 1 analytics: attendance_percentage, average_marks, risk_reasons,
is_declining, exam_summary and low_completion_students, so the dashboard and the
at-risk alerts use the same rules.
"""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.analytics import attendance_percentage, average_marks, is_declining, risk_reasons
from src.app.assignment_records import completion_for_course
from src.app.errors import AppError
from src.app.exam_results import get_course
from src.app.models import (
    Assessment,
    AttendanceRecord,
    Course,
    Enrollment,
    ExamResult,
    Faculty,
    MarkEntry,
    Role,
    Student,
    User,
)
from src.app.risk import NO_DATA_PASSES
from src.assignments import low_completion_students
from src.exam_summary import exam_summary

# Bands for the marks distribution chart, by each student's average percentage.
BANDS = [("0-39", 0, 40), ("40-59", 40, 60), ("60-74", 60, 75), ("75-100", 75, 101)]


def _course_for(db: Session, course_id: int, user: User) -> Course:
    """Faculty see only their own courses; administrators see every course."""
    if user.role is Role.ADMIN:
        course = db.get(Course, course_id)
        if course is None:
            raise AppError(404, "NOT_FOUND", "Course not found")
        return course
    return get_course(db, course_id, user.id)


def _band(percent: float) -> str:
    return next(name for name, low, high in BANDS if low <= percent < high)


def _attendance_by_enrollment(db: Session, enrollment_ids: list[int]) -> dict:
    presence = defaultdict(list)
    rows = db.execute(
        select(AttendanceRecord.enrollment_id, AttendanceRecord.present).where(
            AttendanceRecord.enrollment_id.in_(enrollment_ids)
        )
    )
    for enrollment_id, present in rows:
        presence[enrollment_id].append(present)
    return {
        enrollment_id: attendance_percentage(sum(values), len(values))
        for enrollment_id, values in presence.items()
    }


def _marks_by_enrollment(db: Session, enrollment_ids: list[int]) -> dict:
    """Each student's marks as percentages, oldest assessment first."""
    history = defaultdict(list)
    rows = db.execute(
        select(MarkEntry.enrollment_id, MarkEntry.marks, Assessment.max_marks)
        .join(Assessment, Assessment.id == MarkEntry.assessment_id)
        .where(MarkEntry.enrollment_id.in_(enrollment_ids))
        .order_by(Assessment.held_on, MarkEntry.id)
    )
    for enrollment_id, marks, max_marks in rows:
        if max_marks > 0:
            history[enrollment_id].append(round(marks / max_marks * 100, 2))
    return history


def _exam_summaries(db: Session, enrollment_ids: list[int]) -> list[dict]:
    """One exam_summary per exam type, on percentages so different max marks compare."""
    by_type = defaultdict(list)
    rows = db.execute(
        select(ExamResult.exam_type, ExamResult.marks, ExamResult.max_marks)
        .where(ExamResult.enrollment_id.in_(enrollment_ids))
        .order_by(ExamResult.exam_type)
    )
    for exam_type, marks, max_marks in rows:
        if max_marks > 0:
            by_type[exam_type].append(round(marks / max_marks * 100, 2))
    return [
        {"examType": exam_type, **exam_summary(percentages, max_marks=100)}
        for exam_type, percentages in by_type.items()
    ]


def course_dashboard(
    db: Session,
    course_id: int,
    user: User,
    attendance_threshold: float = 75.0,
    marks_threshold: float = 40.0,
    window: int = 3,
) -> dict:
    """Return the faculty dashboard for one course."""
    course = _course_for(db, course_id, user)
    enrollments = db.execute(
        select(Enrollment.id, Student.usn, Student.name)
        .join(Student, Student.id == Enrollment.student_id)
        .where(Enrollment.course_id == course.id)
        .order_by(Student.usn)
    ).all()
    enrollment_ids = [enrollment_id for enrollment_id, _usn, _name in enrollments]

    attendance = _attendance_by_enrollment(db, enrollment_ids)
    marks = _marks_by_enrollment(db, enrollment_ids)
    completion = {row.usn: row for row in completion_for_course(db, course.id)}

    students = []
    at_risk = []
    distribution = {name: 0 for name, _low, _high in BANDS}
    for enrollment_id, usn, name in enrollments:
        history = marks.get(enrollment_id, [])
        average = average_marks(history) if history else None
        attendance_pct = attendance.get(enrollment_id)
        reasons = risk_reasons(
            attendance_pct if attendance_pct is not None else NO_DATA_PASSES,
            average if average is not None else NO_DATA_PASSES,
            history,
            attendance_threshold,
            marks_threshold,
            window,
        )
        if average is not None:
            distribution[_band(average)] += 1
        if reasons:
            at_risk.append({"usn": usn, "name": name, "reasons": reasons})
        students.append({
            "usn": usn,
            "name": name,
            "attendancePct": attendance_pct,
            "averageMarks": average,
            "declining": is_declining(history, window),
            "assignmentCompletionPct": completion[usn].completion_pct,
            "atRisk": bool(reasons),
        })

    averages = [s["averageMarks"] for s in students if s["averageMarks"] is not None]
    statuses = {
        usn: ["submitted"] * row.submitted + ["late"] * row.late + ["missing"] * row.missing
        for usn, row in completion.items()
    }

    return {
        "courseId": course.id,
        "courseCode": course.code,
        "courseTitle": course.title,
        "enrolled": len(enrollments),
        "classAverage": average_marks(averages) if averages else None,
        "marksDistribution": distribution,
        "exams": _exam_summaries(db, enrollment_ids),
        "atRisk": at_risk,
        "lowCompletion": low_completion_students(statuses),
        "students": students,
    }


def dashboard_courses(db: Session, user: User) -> list[dict]:
    """Courses the user may open on the dashboard: all for an admin, own courses for faculty."""
    query = select(Course).order_by(Course.code)
    if user.role is not Role.ADMIN:
        query = query.join(Faculty, Faculty.id == Course.faculty_id).where(Faculty.user_id == user.id)
    return [
        {"courseId": course.id, "code": course.code, "title": course.title}
        for course in db.scalars(query)
    ]
