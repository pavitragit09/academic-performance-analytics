"""Router for marks, attendance entry, CSV upload and audit logs (F-010, F-011, SR-005, NF-005)."""

from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.app.audit import list_audit_logs
from src.app.database import get_db
from src.app.data_entry import (
    parse_attendance_csv,
    parse_marks_csv,
    record_attendance_batch,
    record_marks_batch,
    verify_course_faculty_or_admin,
)
from src.app.errors import AppError
from src.app.models import Role, User
from src.app.routers.auth import require_admin, require_roles

router = APIRouter(tags=["Marks, Attendance and Audit"])


class MarkEntryItem(BaseModel):
    usn: str
    marks: float


class MarksPayload(BaseModel):
    entries: list[MarkEntryItem]


class AttendanceRecordItem(BaseModel):
    usn: str
    attended: int = 1
    total: int = 1


class AttendancePayload(BaseModel):
    session_date: date | None = Field(default=None, alias="sessionDate")
    present: list[str] | None = None
    absent: list[str] | None = None
    records: list[AttendanceRecordItem] | None = None

    model_config = {"populate_by_name": True}


async def _extract_raw_csv_or_json(
    request: Request,
    file: UploadFile | None = None,
) -> tuple[str, Any]:
    """Return content-type and body/data from UploadFile, multipart form, raw body, or JSON."""
    if file is not None:
        content = await file.read()
        if not content:
            raise AppError(400, "BAD_FILE", "Empty file uploaded")
        return "text/csv", content

    ct = request.headers.get("content-type", "").lower()
    if "multipart/form-data" in ct:
        form = await request.form()
        for value in form.values():
            if hasattr(value, "read"):
                content = await value.read()
                if not content:
                    raise AppError(400, "BAD_FILE", "Empty file uploaded")
                return "text/csv", content
            elif isinstance(value, str):
                return "text/csv", value.encode("utf-8")
        raise AppError(400, "BAD_FILE", "No file found in multipart form")

    body = await request.body()
    if not body:
        raise AppError(400, "BAD_FILE", "Empty request payload")
    return ct, body


@router.post(
    "/courses/{course_id}/assessments/{assessment_id}/marks",
    status_code=201,
)
async def post_marks_entry(
    course_id: int,
    assessment_id: int,
    request: Request,
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FACULTY, Role.ADMIN)),
) -> dict[str, Any]:
    """
    Enter or upload marks for an assessment (APAS-F-010, TC-Data-01).

    Accessible to assigned Faculty or Administrator.
    """
    verify_course_faculty_or_admin(db, course_id, user)
    ct, body = await _extract_raw_csv_or_json(request, file)

    entries: list[dict[str, Any]] = []

    if "application/json" in ct:
        try:
            data = await request.json()
            if isinstance(data, dict) and "entries" in data:
                entries = data["entries"]
            elif isinstance(data, list):
                entries = data
            elif isinstance(data, dict) and "csv" in data:
                entries = parse_marks_csv(str(data["csv"]))
            else:
                raise ValueError
        except Exception:
            raise AppError(400, "BAD_FILE", "Invalid JSON payload for marks entry")
    else:
        entries = parse_marks_csv(body)

    return record_marks_batch(
        db=db,
        course_id=course_id,
        assessment_id=assessment_id,
        entries=entries,
        user_id=user.id,
    )


@router.post(
    "/courses/{course_id}/attendance",
    status_code=201,
)
async def post_attendance_entry(
    course_id: int,
    request: Request,
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.FACULTY, Role.ADMIN)),
) -> dict[str, Any]:
    """
    Record or import attendance (APAS-F-011, TC-Data-02).

    Accessible to assigned Faculty or Administrator.
    """
    verify_course_faculty_or_admin(db, course_id, user)
    ct, body = await _extract_raw_csv_or_json(request, file)

    session_date = date.today()
    records: list[dict[str, Any]] = []

    if "application/json" in ct:
        try:
            data = await request.json()
            raw_date = data.get("sessionDate") or data.get("session_date")
            if raw_date:
                if isinstance(raw_date, str):
                    session_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                elif isinstance(raw_date, date):
                    session_date = raw_date

            if "present" in data or "absent" in data:
                # SAD 4.3.2 format
                for usn in data.get("present", []):
                    records.append({"usn": usn, "attended": 1, "total": 1})
                for usn in data.get("absent", []):
                    records.append({"usn": usn, "attended": 0, "total": 1})
            elif "records" in data:
                records = data["records"]
            elif "csv" in data:
                session_date, records = parse_attendance_csv(str(data["csv"]), session_date)
            else:
                raise ValueError
        except Exception:
            raise AppError(400, "BAD_FILE", "Invalid JSON payload for attendance entry")
    else:
        session_date, records = parse_attendance_csv(body, session_date)

    return record_attendance_batch(
        db=db,
        course_id=course_id,
        session_date=session_date,
        records=records,
        user_id=user.id,
    )


@router.get("/audit-log")
def get_audit_log_entries(
    entity: str | None = Query(None),
    action: str | None = Query(None),
    user_id: int | None = Query(None, alias="userId"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> list[dict[str, Any]]:
    """
    Retrieve audit log entries (APAS-NF-005, TC-Ops-01).

    Accessible to Administrator only.
    """
    return list_audit_logs(
        db=db,
        entity=entity,
        action=action,
        user_id=user_id,
        limit=limit,
    )
