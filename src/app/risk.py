"""At-risk checks saved to the database (APAS-F-040).

Uses the same analytics functions as the dashboards, so alerts and dashboards agree.
A RiskFlag row with active=True is the saved "already flagged" state: a student only
triggers an alert when they are at risk now and have no active flag. A student who
recovers has the flag switched off, so being flagged again alerts again.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.analytics import attendance_percentage, average_marks, risk_reasons
from src.app.exam_results import get_course
from src.app.models import (
    Assessment,
    AttendanceRecord,
    Course,
    Enrollment,
    MarkEntry,
    RiskFlag,
    Student,
)
from src.app.notifications import RiskAlert

# With no attendance or marks recorded yet there is no evidence of risk, so those
# checks are given a value that passes the thresholds instead of flagging a student.
NO_DATA_PASSES = 100.0


class RiskCheckReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    checked: int
    newly_flagged: list[str] = Field(alias="newlyFlagged")


class AtRiskStudent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    usn: str
    name: str
    reasons: list[str]
    flagged_at: datetime = Field(alias="flaggedAt")


def current_reasons(
    db: Session,
    enrollment_id: int,
    attendance_threshold: float | None = None,
    marks_threshold: float | None = None,
    trend_window: int | None = None,
) -> list[str]:
    """Return why a student is at risk right now (empty list = fine)."""
    if attendance_threshold is None or marks_threshold is None or trend_window is None:
        from src.app.thresholds import get_analytics_thresholds

        configured = get_analytics_thresholds(db)
        if attendance_threshold is None:
            attendance_threshold = configured.attendance_threshold
        if marks_threshold is None:
            marks_threshold = configured.marks_threshold
        if trend_window is None:
            trend_window = configured.trend_window
    """Return why a student is at risk right now (empty list = fine)."""
    presence = db.scalars(
        select(AttendanceRecord.present).where(AttendanceRecord.enrollment_id == enrollment_id)
    ).all()
    attendance_pct = (
        attendance_percentage(sum(1 for present in presence if present), len(presence))
        if presence
        else NO_DATA_PASSES
    )

    rows = db.execute(
        select(MarkEntry.marks, Assessment.max_marks)
        .join(Assessment, Assessment.id == MarkEntry.assessment_id)
        .where(MarkEntry.enrollment_id == enrollment_id)
        .order_by(Assessment.held_on, MarkEntry.id)
    ).all()
    history = [round(marks / max_marks * 100, 2) for marks, max_marks in rows if max_marks > 0]
    avg = average_marks(history) if history else NO_DATA_PASSES

    return risk_reasons(attendance_pct, avg, history, attendance_threshold=attendance_threshold, marks_threshold=marks_threshold, decline_window=trend_window)


def evaluate_enrollment(
    db: Session,
    enrollment: Enrollment,
    course: Course,
    attendance_threshold: float | None = None,
    marks_threshold: float | None = None,
    trend_window: int | None = None,
) -> RiskAlert | None:
    """Update the saved flag for one student; return an alert only if newly flagged."""
    reasons = current_reasons(
        db,
        enrollment.id,
        attendance_threshold=attendance_threshold,
        marks_threshold=marks_threshold,
        trend_window=trend_window,
    )
    active = db.scalar(
        select(RiskFlag).where(RiskFlag.enrollment_id == enrollment.id, RiskFlag.active.is_(True))
    )

    if not reasons:
        if active is not None:
            active.active = False  # recovered; a later flag counts as new
        return None

    if active is not None:
        active.reasons = reasons  # still at risk: keep reasons current, no new alert
        return None

    db.add(RiskFlag(enrollment_id=enrollment.id, reasons=reasons, active=True))
    return RiskAlert(
        faculty_email=course.faculty.email,
        faculty_name=course.faculty.name,
        usn=enrollment.student.usn,
        student_name=enrollment.student.name,
        course_code=course.code,
        reasons=reasons,
    )


def check_course(
    db: Session,
    course_id: int,
    user_id: int,
    attendance_threshold: float | None = None,
    marks_threshold: float | None = None,
    trend_window: int | None = None,
) -> tuple[RiskCheckReport, list[RiskAlert]]:
    """Check every student in a course. Returns the report and the alerts to send."""
    course = get_course(db, course_id, user_id)
    enrollments = db.scalars(
        select(Enrollment).where(Enrollment.course_id == course_id).order_by(Enrollment.id)
    ).all()

    alerts = []
    for enrollment in enrollments:
        alert = evaluate_enrollment(
            db,
            enrollment,
            course,
            attendance_threshold=attendance_threshold,
            marks_threshold=marks_threshold,
            trend_window=trend_window,
        )
        if alert is not None:
            alerts.append(alert)
    db.commit()

    report = RiskCheckReport(checked=len(enrollments), newly_flagged=[a.usn for a in alerts])
    return report, alerts


def active_flags(db: Session, course_id: int, user_id: int) -> list[AtRiskStudent]:
    """List the students currently flagged at-risk in a course."""
    get_course(db, course_id, user_id)

    rows = db.execute(
        select(Student.usn, Student.name, RiskFlag)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .join(RiskFlag, RiskFlag.enrollment_id == Enrollment.id)
        .where(Enrollment.course_id == course_id, RiskFlag.active.is_(True))
        .order_by(Student.usn)
    ).all()
    return [
        AtRiskStudent(usn=usn, name=name, reasons=flag.reasons, flagged_at=flag.flagged_at)
        for usn, name, flag in rows
    ]