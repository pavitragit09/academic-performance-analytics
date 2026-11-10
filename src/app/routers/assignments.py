"""Faculty API for assignments and submissions (APAS-F-012, SAD Table 14)."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from src.app import assignment_records as records
from src.app.database import get_db
from src.app.models import User
from src.app.routers.auth import require_faculty

router = APIRouter(tags=["assignments"])


@router.post(
    "/courses/{course_id}/assignments",
    response_model=records.AssignmentOut,
    status_code=status.HTTP_201_CREATED,
)
def create_assignment(
    course_id: int,
    data: records.AssignmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_faculty),
):
    return records.create_assignment(db, course_id, data, user.id)


@router.get("/courses/{course_id}/assignments", response_model=list[records.AssignmentOut])
def list_assignments(
    course_id: int, db: Session = Depends(get_db), user: User = Depends(require_faculty)
):
    return records.list_assignments(db, course_id, user.id)


@router.put("/assignments/{assignment_id}/submissions")
def record_submissions(
    assignment_id: int,
    data: records.SubmissionsUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_faculty),
) -> dict:
    return {"updated": records.record_submissions(db, assignment_id, data, user.id)}


@router.get(
    "/assignments/{assignment_id}/submissions", response_model=list[records.SubmissionOut]
)
def list_submissions(
    assignment_id: int, db: Session = Depends(get_db), user: User = Depends(require_faculty)
):
    return records.list_submissions(db, assignment_id, user.id)


@router.get(
    "/courses/{course_id}/assignment-completion",
    response_model=list[records.StudentCompletion],
)
def course_completion(
    course_id: int,
    include_late: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_faculty),
):
    return records.course_completion(db, course_id, user.id, include_late)
