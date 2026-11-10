"""Assignment records (APAS-F-012): assignments and each student's submission.

Faculty record each enrolled student's status (submitted, late or missing) and score.
Completion rates reuse the Sprint 1 analytics in src/assignments.py (APAS-F-024).
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.errors import AppError
from src.app.exam_results import get_course
from src.app.models import (
    Assignment,
    AssignmentSubmission,
    Enrollment,
    Student,
    SubmissionStatus,
)
from src.assignments import completion_rate, status_breakdown

Status = Literal["submitted", "late", "missing"]


class AssignmentCreate(BaseModel):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    due_date: date
    max_score: Annotated[float, Field(gt=0)]


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    title: str
    due_date: date
    max_score: float


class SubmissionIn(BaseModel):
    usn: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30)]
    status: Status
    score: float | None = None


class SubmissionsUpdate(BaseModel):
    submissions: Annotated[list[SubmissionIn], Field(min_length=1)]


class SubmissionOut(BaseModel):
    usn: str
    name: str
    status: Status
    score: float | None


class StudentCompletion(BaseModel):
    usn: str
    name: str
    submitted: int
    late: int
    missing: int
    completion_pct: float | None


def get_assignment(db: Session, assignment_id: int, user_id: int) -> Assignment:
    """Return an assignment only if its course belongs to the logged-in faculty member."""
    assignment = db.get(Assignment, assignment_id)
    if assignment is None:
        raise AppError(404, "NOT_FOUND", "Assignment not found")
    get_course(db, assignment.course_id, user_id)
    return assignment


def create_assignment(
    db: Session, course_id: int, data: AssignmentCreate, user_id: int
) -> Assignment:
    get_course(db, course_id, user_id)
    assignment = Assignment(course_id=course_id, **data.model_dump())
    db.add(assignment)
    db.commit()
    return assignment


def list_assignments(db: Session, course_id: int, user_id: int) -> list[Assignment]:
    get_course(db, course_id, user_id)
    query = select(Assignment).where(Assignment.course_id == course_id)
    return list(db.scalars(query.order_by(Assignment.due_date, Assignment.id)))


def _enrollments_by_usn(db: Session, course_id: int) -> dict[str, Enrollment]:
    """Map each enrolled student's USN to their enrollment in this course."""
    query = (
        select(Student.usn, Enrollment)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .where(Enrollment.course_id == course_id)
    )
    return {usn: enrollment for usn, enrollment in db.execute(query)}


def _check_row(row: SubmissionIn, max_score: float, enrolled: dict, seen: set) -> str | None:
    """Return why a submission row is invalid, or None when it is valid."""
    if row.usn in seen:
        return f"{row.usn} appears more than once"
    if row.usn not in enrolled:
        return f"{row.usn} is not enrolled in this course"
    if row.status == "missing" and row.score is not None:
        return "a missing submission cannot have a score"
    if row.score is not None and not 0 <= row.score <= max_score:
        return f"score must be between 0 and {max_score:g}"
    return None


def record_submissions(
    db: Session, assignment_id: int, data: SubmissionsUpdate, user_id: int
) -> int:
    """Save each student's status and score. Any invalid row rejects the whole request."""
    assignment = get_assignment(db, assignment_id, user_id)
    enrolled = _enrollments_by_usn(db, assignment.course_id)
    errors = []
    seen = set()
    for index, row in enumerate(data.submissions):
        reason = _check_row(row, assignment.max_score, enrolled, seen)
        if reason:
            errors.append({"row": index + 1, "usn": row.usn, "reason": reason})
        seen.add(row.usn)
    if errors:
        raise AppError(422, "VALIDATION_ERROR", "Some submissions are invalid", errors)

    existing = {
        submission.enrollment_id: submission
        for submission in db.scalars(
            select(AssignmentSubmission).where(AssignmentSubmission.assignment_id == assignment_id)
        )
    }
    for row in data.submissions:
        enrollment_id = enrolled[row.usn].id
        submission = existing.get(enrollment_id)
        if submission is None:
            submission = AssignmentSubmission(
                assignment_id=assignment_id, enrollment_id=enrollment_id
            )
            db.add(submission)
        submission.status = SubmissionStatus(row.status.upper())
        submission.score = row.score
    db.commit()
    return len(data.submissions)


def list_submissions(db: Session, assignment_id: int, user_id: int) -> list[SubmissionOut]:
    get_assignment(db, assignment_id, user_id)
    query = (
        select(Student.usn, Student.name, AssignmentSubmission.status, AssignmentSubmission.score)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .join(AssignmentSubmission, AssignmentSubmission.enrollment_id == Enrollment.id)
        .where(AssignmentSubmission.assignment_id == assignment_id)
        .order_by(Student.usn)
    )
    return [
        SubmissionOut(usn=usn, name=name, status=status.value.lower(), score=score)
        for usn, name, status, score in db.execute(query)
    ]


def completion_for_course(db: Session, course_id: int, include_late: bool = False) -> list:
    """Return each enrolled student's status counts and completion rate (APAS-F-024).

    The caller must already have checked the user may see this course.
    """
    statuses = {usn: [] for usn in _enrollments_by_usn(db, course_id)}
    query = (
        select(Student.usn, AssignmentSubmission.status)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .join(AssignmentSubmission, AssignmentSubmission.enrollment_id == Enrollment.id)
        .where(Enrollment.course_id == course_id)
    )
    for usn, status in db.execute(query):
        statuses[usn].append(status.value.lower())
    names_query = select(Student.usn, Student.name).where(Student.usn.in_(statuses))
    names = {usn: name for usn, name in db.execute(names_query)}

    results = []
    for usn in sorted(statuses):
        values = statuses[usn]
        counts = status_breakdown(values) if values else {"submitted": 0, "late": 0, "missing": 0}
        percent = completion_rate(values, include_late) if values else None
        results.append(StudentCompletion(usn=usn, name=names[usn], completion_pct=percent, **counts))
    return results


def course_completion(
    db: Session, course_id: int, user_id: int, include_late: bool = False
) -> list:
    """Completion rates for a course the logged-in faculty member teaches."""
    get_course(db, course_id, user_id)
    return completion_for_course(db, course_id, include_late)
