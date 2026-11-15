
"""Student dashboard API (APAS-F-030 and APAS-F-034)."""

from fastapi import APIRouter, Depends
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from src.app.database import get_db
from src.app.errors import AppError
from src.app.models import (
    Assessment,
    Assignment,
    AssignmentSubmission,
    AttendanceRecord,
    Course,
    Enrollment,
    ExamResult,
    MarkEntry,
    Student,
    User,
)
from src.app.routers.auth import require_student


router = APIRouter(prefix="/student", tags=["Student Dashboard"])


@router.get("/dashboard")
def get_student_dashboard(
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    """Return academic information belonging only to the logged-in student."""

    # Find the student profile linked to the authenticated user.
    student = db.scalar(
        select(Student).where(Student.user_id == user.id)
    )

    if student is None:
        raise AppError(
            404,
            "NOT_FOUND",
            "Student profile is not linked to this account",
        )

    # Retrieve only this student's course enrollments.
    enrollments = db.scalars(
        select(Enrollment).where(
            Enrollment.student_id == student.id
        )
    ).all()

    enrollment_ids = [enrollment.id for enrollment in enrollments]

    # Retrieve courses belonging to this student's enrollments.
    courses = {
        course.id: course
        for course in db.scalars(
            select(Course)
            .join(
                Enrollment,
                Enrollment.course_id == Course.id,
            )
            .where(Enrollment.student_id == student.id)
        ).all()
    }

    marks = []
    attendance = []
    assignments = []
    exam_results = []

    if enrollment_ids:

        # Retrieve marks and their corresponding assessments
        # in chronological order for trend visualisation.
        mark_entries = db.execute(
            select(MarkEntry, Assessment, Enrollment)
            .join(
                Assessment,
                MarkEntry.assessment_id == Assessment.id,
            )
            .join(
                Enrollment,
                MarkEntry.enrollment_id == Enrollment.id,
            )
            .where(
                MarkEntry.enrollment_id.in_(enrollment_ids)
            )
            .order_by(
                Assessment.held_on.asc(),
                MarkEntry.id.asc(),
            )
        ).all()

        for entry, assessment, enrollment in mark_entries:
            course = courses.get(enrollment.course_id)

            marks.append({
                "course_code": course.code if course else None,
                "course_title": course.title if course else None,
                "assessment": assessment.name,
                "marks": entry.marks,
                "max_marks": assessment.max_marks,
                "held_on": assessment.held_on.isoformat(),
            })

        # Retrieve attendance with its course information,
        # in chronological order for per-course trends.
        attendance_records = db.execute(
            select(AttendanceRecord, Enrollment)
            .join(
                Enrollment,
                AttendanceRecord.enrollment_id == Enrollment.id,
            )
            .where(
                AttendanceRecord.enrollment_id.in_(enrollment_ids)
            )
            .order_by(
                AttendanceRecord.session_date.asc(),
                AttendanceRecord.id.asc(),
            )
        ).all()

        for record, enrollment in attendance_records:
            course = courses.get(enrollment.course_id)

            attendance.append({
                "course_code": course.code if course else None,
                "course_title": course.title if course else None,
                "session_date": record.session_date.isoformat(),
                "present": record.present,
            })

        # Retrieve all assignments, including those not yet submitted.
        assignment_rows = db.execute(
            select(Assignment, AssignmentSubmission, Enrollment)
            .join(
                Enrollment,
                Enrollment.course_id == Assignment.course_id,
            )
            .outerjoin(
                AssignmentSubmission,
                and_(
                    AssignmentSubmission.assignment_id == Assignment.id,
                    AssignmentSubmission.enrollment_id == Enrollment.id,
                ),
            )
            .where(
                Enrollment.student_id == student.id
            )
            .order_by(Assignment.due_date)
        ).all()

        for assignment, submission, enrollment in assignment_rows:
            course = courses.get(enrollment.course_id)

            assignments.append({
                "course_code": course.code if course else None,
                "title": assignment.title,
                "due_date": assignment.due_date.isoformat(),
                "status": (
                    submission.status.value if submission else None
                ),
                "score": (
                    submission.score if submission else None
                ),
                "max_score": assignment.max_score,
                "submitted": submission is not None,
            })

        # Retrieve examination results.
        exam_rows = db.execute(
            select(ExamResult, Enrollment)
            .join(
                Enrollment,
                ExamResult.enrollment_id == Enrollment.id,
            )
            .where(
                ExamResult.enrollment_id.in_(enrollment_ids)
            )
        ).all()

        for result, enrollment in exam_rows:
            course = courses.get(enrollment.course_id)

            exam_results.append({
                "course_code": course.code if course else None,
                "course_title": course.title if course else None,
                "exam_type": result.exam_type,
                "marks": result.marks,
                "max_marks": result.max_marks,
            })

    return {
        "student": {
            "id": student.id,
            "name": student.name,
            "usn": student.usn,
            "department": student.department,
            "semester": student.semester,
        },
        "marks": marks,
        "attendance": attendance,
        "assignments": assignments,
        "exam_results": exam_results,
    }
