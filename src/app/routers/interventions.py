"""Faculty API for intervention notes and status (APAS-F-041, F-042, SAD section 4.3.4)."""

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from src.app import interventions as service
from src.app.database import get_db
from src.app.models import InterventionStatus, User
from src.app.routers.auth import require_faculty

router = APIRouter(tags=["interventions"])


@router.get("/interventions", response_model=list[service.InterventionOut])
def list_interventions(
    course_id: int | None = Query(None, alias="courseId"),
    status: InterventionStatus | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_faculty),
):
    return service.list_interventions(db, user.id, course_id, status)


@router.post(
    "/interventions/{intervention_id}/notes",
    response_model=service.NoteCreated,
    status_code=status.HTTP_201_CREATED,
)
def add_note(
    intervention_id: int,
    data: service.NoteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_faculty),
):
    return service.add_note(db, intervention_id, data, user.id)


@router.get("/interventions/{intervention_id}/notes", response_model=list[service.NoteOut])
def list_notes(
    intervention_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_faculty),
):
    return service.list_notes(db, intervention_id, user.id)


@router.patch("/interventions/{intervention_id}/status", response_model=service.StatusOut)
def change_status(
    intervention_id: int,
    data: service.StatusIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_faculty),
):
    return service.change_status(db, intervention_id, data.status, user.id)