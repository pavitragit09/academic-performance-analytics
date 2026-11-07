
"""Exam results service and request/response schemas (APAS-F-013, SAD Table 14).

Faculty submit a batch of results for one exam of one course. Each row is checked
(APAS-F-014): the student must be enrolled, marks must be within 0 to the exam
maximum, and a student can only have one result per exam type. Valid rows are
saved; invalid and duplicate rows are reported back, not silently dropped.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.errors import AppError
from src.app.models import (
    AuditLogEntry,
    Course,
    Enrollment,
    ExamResult,
    Faculty,
    Student,
)
from src.app.validation import validate_marks
from src.exam_summary import exam_summary

ExamType = Literal["ISA", "ESA"]


class ExamRow(BaseModel):
    usn: str
    marks: float


class ExamUpload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    exam_type: ExamType = Field(alias="examType")
    max_marks: float = Field(alias="maxMarks", gt=0)
    results: list[ExamRow] = Field(min_length=1)


class RejectedRow(BaseModel):
    row: int
    reason: str


class UploadReport(BaseModel):
    accepted: int
    rejected: list[RejectedRow]


class ExamResultOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    usn: str
    name: str
    exam_type: str = Field(alias="examType")
    marks: float
    max_marks: float = Field(alias="maxMarks")


class ExamSummaryOut(BaseModel):
    count: int
    highest: float
    lowest: float
    average: float
    pass_rate: float = Field(alias="passRate")

    model_config = ConfigDict(populate_by_name=True)


class CourseExams(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    exam_type: str = Field(alias="examType")
    results: list[ExamResultOut]
    summary: ExamSummaryOut | None


def get_course(db: Session, course_id: int, user_id: int) -> Course:
    """Return a course only if it belongs to the authenticated faculty member."""

    course = db.get(Course, course_id)

    if course is None:
        raise AppError(404, "NOT_FOUND", "Course not found")

    faculty = db.scalar(
        select(Faculty).where(
            Faculty.id == course.faculty_id,
            Faculty.user_id == user_id,
        )
    )

    if faculty is None:
        raise AppError(
            403,
            "FORBIDDEN",
            "You do not have permission to access this course",
        )

    return course


def save_exam_results(
    db: Session,
    course_id: int,
    data: ExamUpload,
    user_id: int,
) -> UploadReport:
    """Save valid rows and report the rest. Writes an audit entry for every saved result."""

    get_course(db, course_id, user_id)

    enrollments = {
        usn: enrollment_id
        for usn, enrollment_id in db.execute(
            select(Student.usn, Enrollment.id)
            .join(Enrollment, Enrollment.student_id == Student.id)
            .where(Enrollment.course_id == course_id)
        )
    }

    already_saved = set(
        db.scalars(
            select(ExamResult.enrollment_id).where(
                ExamResult.exam_type == data.exam_type,
                ExamResult.enrollment_id.in_(enrollments.values()),
            )
        )
    )

    rejected: list[RejectedRow] = []
    accepted = 0
    seen: set[int] = set()

    for row_number, row in enumerate(data.results, start=1):
        enrollment_id = enrollments.get(row.usn)

        try:
            if enrollment_id is None:
                raise ValueError("student is not enrolled in this course")

            if enrollment_id in seen:
                raise ValueError("duplicate entry within uploaded batch")

            seen.add(enrollment_id)
            validate_marks(row.marks, data.max_marks)

            if enrollment_id in already_saved:
                raise ValueError(
                    "a result for this student and exam type already exists"
                )

        except ValueError as exc:
            rejected.append(
                RejectedRow(row=row_number, reason=str(exc))
            )
            continue

        result = ExamResult(
            enrollment_id=enrollment_id,
            exam_type=data.exam_type,
            marks=row.marks,
            max_marks=data.max_marks,
        )

        db.add(result)
        db.flush()

        db.add(
            AuditLogEntry(
                user_id=user_id,
                action="CREATE",
                entity=f"exam_result:{result.id}",
                old_value=None,
                new_value=(
                    f"{row.usn} {data.exam_type} "
                    f"{row.marks}/{data.max_marks}"
                ),
            )
        )

        accepted += 1

    db.commit()

    return UploadReport(accepted=accepted, rejected=rejected)


def course_exam_results(
    db: Session,
    course_id: int,
    exam_type: ExamType,
    user_id: int,
) -> CourseExams:
    """Return exam results and summary for a course owned by the faculty member."""

    get_course(db, course_id, user_id)

    rows = db.execute(
        select(Student.usn, Student.name, ExamResult)
        .join(Enrollment, Enrollment.student_id == Student.id)
        .join(ExamResult, ExamResult.enrollment_id == Enrollment.id)
        .where(
            Enrollment.course_id == course_id,
            ExamResult.exam_type == exam_type,
        )
        .order_by(Student.usn)
    ).all()

    results = [
        ExamResultOut(
            usn=usn,
            name=name,
            exam_type=result.exam_type,
            marks=result.marks,
            max_marks=result.max_marks,
        )
        for usn, name, result in rows
    ]

    summary = None

    if rows:
        summary = ExamSummaryOut(
            **exam_summary(
                [result.marks for _, _, result in rows],
                max_marks=rows[0][2].max_marks,
            )
        )

    return CourseExams(
        exam_type=exam_type,
        results=results,
        summary=summary,
    )
