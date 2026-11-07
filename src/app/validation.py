
"""Input validation helpers for APAS marks and attendance records."""

from datetime import date
from math import isfinite

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.models import (
    Assessment,
    Enrollment,
    MarkEntry,
    AttendanceRecord,
)


def validate_marks(marks: float, max_marks: float) -> None:
    """Ensure marks are finite and within the assessment range."""
    if isinstance(marks, bool) or not isinstance(marks, (int, float)):
        raise ValueError("marks must be a number")

    if isinstance(max_marks, bool) or not isinstance(max_marks, (int, float)):
        raise ValueError("max_marks must be a number")

    if not isfinite(marks) or not isfinite(max_marks):
        raise ValueError("marks and max_marks must be finite")

    if max_marks <= 0:
        raise ValueError("max_marks must be positive")

    if marks < 0 or marks > max_marks:
        raise ValueError(f"marks must be between 0 and {max_marks}")


def validate_attendance(attended: int, total: int) -> None:
    """Ensure attendance counts are valid."""
    if isinstance(attended, bool) or not isinstance(attended, int):
        raise ValueError("attended must be an integer")

    if isinstance(total, bool) or not isinstance(total, int):
        raise ValueError("total must be an integer")

    if total < 0 or attended < 0:
        raise ValueError("attendance counts cannot be negative")

    if attended > total:
        raise ValueError("attended cannot be greater than total")


def validate_mark_entry(
    db: Session,
    assessment_id: int,
    enrollment_id: int,
    marks: float,
) -> None:
    """Validate marks, assessment, enrollment and duplicate entries."""
    assessment = db.get(Assessment, assessment_id)

    if assessment is None:
        raise ValueError("assessment does not exist")

    enrollment = db.get(Enrollment, enrollment_id)

    if enrollment is None:
        raise ValueError("enrollment does not exist")

    if enrollment.course_id != assessment.course_id:
        raise ValueError("enrollment does not belong to the assessment course")

    validate_marks(marks, assessment.max_marks)

    existing = db.scalar(
        select(MarkEntry).where(
            MarkEntry.assessment_id == assessment_id,
            MarkEntry.enrollment_id == enrollment_id,
        )
    )

    if existing is not None:
        raise ValueError(
            "duplicate mark entry for this assessment and enrollment"
        )


def validate_attendance_entry(
    db: Session,
    enrollment_id: int,
    session_date: date,
) -> None:
    """Validate enrollment and reject duplicate attendance."""
    enrollment = db.get(Enrollment, enrollment_id)

    if enrollment is None:
        raise ValueError("enrollment does not exist")

    if not isinstance(session_date, date):
        raise ValueError("session_date must be a valid date")

    existing = db.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.enrollment_id == enrollment_id,
            AttendanceRecord.session_date == session_date,
        )
    )

    if existing is not None:
        raise ValueError(
            "duplicate attendance entry for this enrollment and date"
        )


def validate_mark_batch(db: Session, rows: list[dict]) -> dict:
    """Validate a mark batch and report accepted and rejected rows."""
    accepted = []
    rejected = []
    seen = set()

    for row_number, row in enumerate(rows, start=1):
        try:
            assessment_id = row["assessment_id"]
            enrollment_id = row["enrollment_id"]
            marks = row["marks"]

            key = (assessment_id, enrollment_id)

            if key in seen:
                raise ValueError("duplicate entry within uploaded batch")

            seen.add(key)

            validate_mark_entry(
                db,
                assessment_id,
                enrollment_id,
                marks,
            )

            accepted.append({"row": row_number, "data": row.copy()})

        except (KeyError, TypeError, ValueError) as exc:
            rejected.append({"row": row_number, "reason": str(exc)})

    return {
        "accepted": accepted,
        "rejected": rejected,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
    }


def validate_attendance_batch(db: Session, rows: list[dict]) -> dict:
    """Validate an attendance batch and report accepted and rejected rows."""
    accepted = []
    rejected = []
    seen = set()

    for row_number, row in enumerate(rows, start=1):
        try:
            enrollment_id = row["enrollment_id"]
            session_date = row["session_date"]
            present = row["present"]

            if not isinstance(present, bool):
                raise ValueError("present must be a boolean")

            key = (enrollment_id, session_date)

            if key in seen:
                raise ValueError("duplicate entry within uploaded batch")

            seen.add(key)

            validate_attendance_entry(
                db,
                enrollment_id,
                session_date,
            )

            accepted.append({"row": row_number, "data": row.copy()})

        except (KeyError, TypeError, ValueError) as exc:
            rejected.append({"row": row_number, "reason": str(exc)})

    return {
        "accepted": accepted,
        "rejected": rejected,
        "accepted_count": len(accepted),
        "rejected_count": len(rejected),
    }
