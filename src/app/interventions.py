"""Interventions for flagged students (APAS-F-041 notes, APAS-F-042 status).

An intervention is opened when a student is flagged at risk (see risk.py). Faculty record
the action they took as notes, and move the intervention through
OPEN -> IN_PROGRESS -> RESOLVED. Every status change is written to the audit log.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.errors import AppError
from src.app.exam_results import get_course
from src.app.models import (
    AuditLogEntry,
    Course,
    Enrollment,
    Faculty,
    Intervention,
    InterventionNote,
    InterventionStatus,
    RiskFlag,
    Student,
)

ALLOWED_TRANSITIONS = {
    InterventionStatus.OPEN: {InterventionStatus.IN_PROGRESS},
    InterventionStatus.IN_PROGRESS: {InterventionStatus.RESOLVED},
    InterventionStatus.RESOLVED: set(),
}


class NoteIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    action_taken: str = Field(alias="actionTaken")
    noted_on: date = Field(alias="notedOn")

    @field_validator("action_taken")
    @classmethod
    def action_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("actionTaken must not be empty")
        return value


class NoteCreated(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    note_id: int = Field(alias="noteId")


class NoteOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    note_id: int = Field(alias="noteId")
    action_taken: str = Field(alias="actionTaken")
    noted_on: date = Field(alias="notedOn")


class StatusIn(BaseModel):
    status: InterventionStatus


class StatusOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    intervention_id: int = Field(alias="interventionId")
    status: InterventionStatus
    updated_by: int = Field(alias="updatedBy")
    updated_at: datetime = Field(alias="updatedAt")


class InterventionOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    intervention_id: int = Field(alias="interventionId")
    usn: str
    reasons: list[str]
    status: InterventionStatus
    updated_at: datetime = Field(alias="updatedAt")


def ensure_intervention(db: Session, flag: RiskFlag) -> Intervention:
    """Return the intervention for a flag, opening one if it does not exist yet."""
    intervention = db.scalar(select(Intervention).where(Intervention.flag_id == flag.id))
    if intervention is None:
        intervention = Intervention(flag_id=flag.id, status=InterventionStatus.OPEN)
        db.add(intervention)
        db.flush()
    return intervention


def get_owned_intervention(db: Session, intervention_id: int, user_id: int) -> Intervention:
    """Return an intervention only if it belongs to a course taught by this faculty member."""
    row = db.execute(
        select(Intervention, Course)
        .join(RiskFlag, RiskFlag.id == Intervention.flag_id)
        .join(Enrollment, Enrollment.id == RiskFlag.enrollment_id)
        .join(Course, Course.id == Enrollment.course_id)
        .where(Intervention.id == intervention_id)
    ).first()
    if row is None:
        raise AppError(404, "NOT_FOUND", "Intervention not found")

    intervention, course = row
    owner = db.scalar(
        select(Faculty).where(Faculty.id == course.faculty_id, Faculty.user_id == user_id)
    )
    if owner is None:
        raise AppError(403, "FORBIDDEN", "You do not have permission to access this intervention")
    return intervention


def list_interventions(
    db: Session,
    user_id: int,
    course_id: int | None = None,
    status: InterventionStatus | None = None,
) -> list[InterventionOut]:
    """List interventions in the faculty member's courses, optionally for one course or status."""
    query = (
        select(Intervention, RiskFlag, Student.usn)
        .join(RiskFlag, RiskFlag.id == Intervention.flag_id)
        .join(Enrollment, Enrollment.id == RiskFlag.enrollment_id)
        .join(Student, Student.id == Enrollment.student_id)
        .join(Course, Course.id == Enrollment.course_id)
        .join(Faculty, Faculty.id == Course.faculty_id)
        .where(Faculty.user_id == user_id)
        .order_by(Intervention.id)
    )
    if course_id is not None:
        get_course(db, course_id, user_id)  # 404 / 403 for unknown or someone else's course
        query = query.where(Course.id == course_id)
    if status is not None:
        query = query.where(Intervention.status == status)

    return [
        InterventionOut(
            interventionId=intervention.id,
            usn=usn,
            reasons=flag.reasons,
            status=intervention.status,
            updatedAt=intervention.updated_at,
        )
        for intervention, flag, usn in db.execute(query).all()
    ]


def add_note(db: Session, intervention_id: int, data: NoteIn, user_id: int) -> NoteCreated:
    """Record the action a faculty member took for a flagged student."""
    intervention = get_owned_intervention(db, intervention_id, user_id)
    faculty = db.scalar(select(Faculty).where(Faculty.user_id == user_id))

    note = InterventionNote(
        intervention_id=intervention.id,
        faculty_id=faculty.id,
        action_taken=data.action_taken,
        noted_on=data.noted_on,
    )
    db.add(note)
    db.flush()
    db.add(
        AuditLogEntry(
            user_id=user_id,
            action="CREATE",
            entity=f"intervention_note:{note.id}",
            old_value=None,
            new_value=f"intervention {intervention.id}: {data.action_taken}",
        )
    )
    db.commit()
    return NoteCreated(noteId=note.id)


def list_notes(db: Session, intervention_id: int, user_id: int) -> list[NoteOut]:
    """The notes recorded for an intervention, oldest first."""
    intervention = get_owned_intervention(db, intervention_id, user_id)
    notes = db.scalars(
        select(InterventionNote)
        .where(InterventionNote.intervention_id == intervention.id)
        .order_by(InterventionNote.noted_on, InterventionNote.id)
    ).all()
    return [
        NoteOut(noteId=n.id, actionTaken=n.action_taken, notedOn=n.noted_on) for n in notes
    ]


def change_status(
    db: Session, intervention_id: int, new_status: InterventionStatus, user_id: int
) -> StatusOut:
    """Move an intervention forward: OPEN -> IN_PROGRESS -> RESOLVED, nothing else."""
    intervention = get_owned_intervention(db, intervention_id, user_id)
    old_status = intervention.status

    if new_status not in ALLOWED_TRANSITIONS[old_status]:
        raise AppError(
            409,
            "INVALID_STATUS_TRANSITION",
            f"Cannot change status from {old_status.value} to {new_status.value}",
        )

    intervention.status = new_status
    db.add(
        AuditLogEntry(
            user_id=user_id,
            action="UPDATE",
            entity=f"intervention:{intervention.id}",
            old_value=old_status.value,
            new_value=new_status.value,
        )
    )
    db.commit()
    db.refresh(intervention)
    return StatusOut(
        interventionId=intervention.id,
        status=intervention.status,
        updatedBy=user_id,
        updatedAt=intervention.updated_at,
    )