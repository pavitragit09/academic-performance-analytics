"""Marks and attendance entry, CSV upload and audit logging (APAS-F-010, APAS-F-011)."""

import csv
import io
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app import models
from src.app.audit import log_data_change
from src.app.errors import AppError
from src.app.records import check_student_enrolled, get_course_by_id, get_student_by_usn
from src.app.validation import validate_marks


def verify_course_faculty_or_admin(
    db: Session,
    course_id: int,
    user: models.User,
) -> models.Course:
    """
    Ensure the user is either an Administrator or the Faculty assigned to the course.

    Non-assigned faculty or students receive 403 Forbidden.
    """
    course = get_course_by_id(db, course_id)

    if user.role is models.Role.ADMIN or getattr(user.role, "value", None) == "ADMIN":
        return course

    if user.role is models.Role.FACULTY or getattr(user.role, "value", None) == "FACULTY":
        faculty = db.scalars(
            select(models.Faculty).where(models.Faculty.user_id == user.id)
        ).first()
        if faculty is not None and course.faculty_id == faculty.id:
            return course

    raise AppError(403, "FORBIDDEN", "Not this course's faculty")


def record_marks_batch(
    db: Session,
    course_id: int,
    assessment_id: int,
    entries: list[dict[str, Any]],
    user_id: int | None = None,
) -> dict[str, Any]:
    """
    Enter or upload marks for an assessment (APAS-F-010, TC-Data-01).

    Rejects non-enrolled students (TC-Data-06) and invalid marks.
    Writes every mark creation or edit to the audit log (TC-Sec-05).
    """
    course = get_course_by_id(db, course_id)
    assessment = db.get(models.Assessment, assessment_id)
    if assessment is None or assessment.course_id != course.id:
        raise AppError(
            404,
            "NOT_FOUND",
            f"Assessment {assessment_id} not found for course {course_id}",
        )

    accepted = 0
    rejected: list[dict[str, Any]] = []
    seen_enrollments: set[int] = set()

    for idx, entry in enumerate(entries, start=1):
        usn = str(entry.get("usn", "")).strip().upper()
        raw_marks = entry.get("marks")

        # 1. Check student enrolment using #28 check
        try:
            enrollment = check_student_enrolled(db, course.id, usn)
        except AppError as exc:
            rejected.append({"row": idx, "usn": usn, "reason": exc.message})
            continue

        if enrollment.id in seen_enrollments:
            rejected.append(
                {"row": idx, "usn": usn, "reason": f"Duplicate mark entry for USN '{usn}'"}
            )
            continue

        # 2. Validate mark range
        try:
            marks_val = float(raw_marks)
            validate_marks(marks_val, assessment.max_marks)
        except (ValueError, TypeError) as exc:
            rejected.append({"row": idx, "usn": usn, "reason": str(exc)})
            continue

        seen_enrollments.add(enrollment.id)

        # 3. Check for existing mark entry
        stmt = select(models.MarkEntry).where(
            models.MarkEntry.assessment_id == assessment.id,
            models.MarkEntry.enrollment_id == enrollment.id,
        )
        existing_mark = db.scalars(stmt).first()

        if existing_mark is not None:
            old_val = str(existing_mark.marks)
            existing_mark.marks = marks_val
            db.flush()
            log_data_change(
                db=db,
                action="UPDATE",
                entity=f"mark_entry:{existing_mark.id}",
                user_id=user_id,
                old_value=old_val,
                new_value=str(marks_val),
            )
        else:
            new_mark = models.MarkEntry(
                assessment_id=assessment.id,
                enrollment_id=enrollment.id,
                marks=marks_val,
            )
            db.add(new_mark)
            db.flush()
            log_data_change(
                db=db,
                action="CREATE",
                entity=f"mark_entry:{new_mark.id}",
                user_id=user_id,
                old_value=None,
                new_value=f"{usn} {marks_val}/{assessment.max_marks}",
            )

        accepted += 1

    db.commit()

    return {
        "accepted": accepted,
        "rejected": rejected,
        "newlyFlagged": [],
    }


def parse_marks_csv(csv_data: str | bytes) -> list[dict[str, Any]]:
    """Parse CSV text or bytes into list of mark entries."""
    if isinstance(csv_data, bytes):
        try:
            text = csv_data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = csv_data.decode("latin-1")
            except Exception:
                raise AppError(400, "BAD_FILE", "Unable to decode CSV as text")
    else:
        text = str(csv_data)

    if not text.strip():
        raise AppError(400, "BAD_FILE", "Empty CSV file")

    stream = io.StringIO(text)
    try:
        reader = csv.reader(stream)
        rows = list(reader)
    except Exception as exc:
        raise AppError(400, "BAD_FILE", f"Malformed CSV file: {exc}")

    if not rows:
        raise AppError(400, "BAD_FILE", "CSV file contains no rows")

    header = [h.strip().lower() for h in rows[0]]
    if "usn" not in header or "marks" not in header:
        raise AppError(400, "BAD_FILE", f"CSV header must contain usn and marks. Found: {rows[0]}")

    usn_idx = header.index("usn")
    marks_idx = header.index("marks")

    entries: list[dict[str, Any]] = []
    for row in rows[1:]:
        if not row or all(c.strip() == "" for c in row):
            continue
        if len(row) <= max(usn_idx, marks_idx):
            continue
        entries.append(
            {
                "usn": row[usn_idx].strip(),
                "marks": row[marks_idx].strip(),
            }
        )

    return entries


def record_attendance_batch(
    db: Session,
    course_id: int,
    session_date: date,
    records: list[dict[str, Any]],
    user_id: int | None = None,
) -> dict[str, Any]:
    """
    Record or import attendance (APAS-F-011, TC-Data-02).

    Persists into attendance_records (enrollment_id, session_date, present).
    Rejects non-enrolled students and logs every record to audit log.
    """
    course = get_course_by_id(db, course_id)

    recorded = 0
    rejected: list[dict[str, Any]] = []
    seen_enrollments: set[int] = set()

    for idx, rec in enumerate(records, start=1):
        usn = str(rec.get("usn", "")).strip().upper()
        raw_present = rec.get("present")
        if raw_present is None:
            raw_att = rec.get("attended", 1)
            try:
                is_present = int(raw_att) > 0
            except (ValueError, TypeError):
                is_present = False
        elif isinstance(raw_present, bool):
            is_present = raw_present
        else:
            is_present = str(raw_present).strip().lower() in ("true", "1", "present", "yes", "p")

        # Check enrolment
        try:
            enrollment = check_student_enrolled(db, course.id, usn)
        except AppError as exc:
            rejected.append({"row": idx, "usn": usn, "reason": exc.message})
            continue

        if enrollment.id in seen_enrollments:
            rejected.append(
                {"row": idx, "usn": usn, "reason": f"Duplicate attendance row for USN '{usn}'"}
            )
            continue

        seen_enrollments.add(enrollment.id)

        # Check existing attendance record for this enrollment and session date
        stmt = select(models.AttendanceRecord).where(
            models.AttendanceRecord.enrollment_id == enrollment.id,
            models.AttendanceRecord.session_date == session_date,
        )
        existing = db.scalars(stmt).first()

        if existing is not None:
            old_str = "present" if existing.present else "absent"
            existing.present = is_present
            db.flush()
            log_data_change(
                db=db,
                action="UPDATE",
                entity=f"attendance_record:{existing.id}",
                user_id=user_id,
                old_value=old_str,
                new_value="present" if is_present else "absent",
            )
        else:
            att_rec = models.AttendanceRecord(
                enrollment_id=enrollment.id,
                session_date=session_date,
                present=is_present,
            )
            db.add(att_rec)
            db.flush()
            log_data_change(
                db=db,
                action="CREATE",
                entity=f"attendance_record:{att_rec.id}",
                user_id=user_id,
                old_value=None,
                new_value=f"{usn} {session_date} {'present' if is_present else 'absent'}",
            )

        recorded += 1

    db.commit()

    return {
        "recorded": recorded,
        "rejected": rejected,
    }


def parse_attendance_csv(
    csv_data: str | bytes,
    default_date: date | None = None,
) -> tuple[date, list[dict[str, Any]]]:
    """Parse CSV into session date and list of attendance records."""
    if isinstance(csv_data, bytes):
        try:
            text = csv_data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = csv_data.decode("latin-1")
            except Exception:
                raise AppError(400, "BAD_FILE", "Unable to decode CSV as text")
    else:
        text = str(csv_data)

    if not text.strip():
        raise AppError(400, "BAD_FILE", "Empty CSV file")

    stream = io.StringIO(text)
    try:
        reader = csv.reader(stream)
        rows = list(reader)
    except Exception as exc:
        raise AppError(400, "BAD_FILE", f"Malformed CSV file: {exc}")

    if not rows:
        raise AppError(400, "BAD_FILE", "CSV file contains no rows")

    header = [h.strip().lower() for h in rows[0]]
    if "usn" not in header:
        raise AppError(400, "BAD_FILE", f"CSV header must contain 'usn'. Found: {rows[0]}")

    usn_idx = header.index("usn")
    status_idx = header.index("status") if "status" in header else None
    present_idx = header.index("present") if "present" in header else None
    att_idx = header.index("attended") if "attended" in header else None
    date_idx = (
        header.index("session_date")
        if "session_date" in header
        else (header.index("date") if "date" in header else None)
    )

    records: list[dict[str, Any]] = []
    found_date = default_date or date.today()

    for row in rows[1:]:
        if not row or all(c.strip() == "" for c in row):
            continue
        if len(row) <= usn_idx:
            continue

        raw_usn = row[usn_idx].strip()
        if not raw_usn:
            continue

        if date_idx is not None and len(row) > date_idx and row[date_idx].strip():
            try:
                found_date = datetime.strptime(row[date_idx].strip(), "%Y-%m-%d").date()
            except ValueError:
                pass

        if present_idx is not None and len(row) > present_idx:
            val = row[present_idx].strip().lower()
            is_pres = val in ("true", "1", "yes", "p", "present")
        elif status_idx is not None and len(row) > status_idx:
            st = row[status_idx].strip().lower()
            is_pres = st in ("present", "1", "yes", "p", "true")
        elif att_idx is not None and len(row) > att_idx:
            try:
                is_pres = int(row[att_idx].strip()) > 0
            except ValueError:
                is_pres = False
        else:
            is_pres = True

        records.append({"usn": raw_usn, "present": is_pres})

    return found_date, records
