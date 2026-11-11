"""Course and student records router (APAS-F-015)."""

from typing import Any
from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app import models
from src.app.database import get_db
from src.app.errors import AppError
from src.app.models import Role, User
from src.app.records import (
    assign_faculty_to_course,
    create_course,
    create_student,
    enroll_student,
    get_course_by_id,
    import_enrollments_csv,
    import_students_csv,
    list_course_enrollments,
    list_courses,
    list_students,
)
from src.app.routers.auth import require_admin, require_roles

router = APIRouter(tags=["Course and Student Records"])


# Pydantic Request Schemas
class CreateCourseRequest(BaseModel):
    code: str
    title: str
    semester: int
    faculty_id: int = Field(alias="facultyId")

    model_config = {"populate_by_name": True}


class AssignFacultyRequest(BaseModel):
    faculty_id: int = Field(alias="facultyId")

    model_config = {"populate_by_name": True}


class CreateStudentRequest(BaseModel):
    usn: str
    name: str
    department: str
    semester: int


class EnrollStudentRequest(BaseModel):
    usn: str


async def _extract_csv_text(
    request: Request,
    file: UploadFile | None = None,
) -> str:
    """Extract CSV text from standard UploadFile, multipart form, raw body, or JSON."""
    if file is not None:
        content = await file.read()
        if not content:
            raise AppError(400, "BAD_FILE", "Empty file uploaded")
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("latin-1")

    content_type = request.headers.get("content-type", "").lower()
    if "multipart/form-data" in content_type:
        form = await request.form()
        for value in form.values():
            if hasattr(value, "read"):
                content = await value.read()
                if not content:
                    raise AppError(400, "BAD_FILE", "Empty file uploaded")
                try:
                    return content.decode("utf-8")
                except UnicodeDecodeError:
                    return content.decode("latin-1")
            elif isinstance(value, str):
                return value
        raise AppError(400, "BAD_FILE", "No file found in multipart form")

    body = await request.body()
    if not body:
        raise AppError(400, "BAD_FILE", "Empty request body")

    if "application/json" in content_type:
        try:
            data = await request.json()
            if isinstance(data, dict) and "csv" in data:
                return str(data["csv"])
            raise ValueError
        except Exception:
            raise AppError(400, "BAD_FILE", "Invalid JSON body, expected {'csv': '...'}")

    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("latin-1")


# Course Endpoints
@router.post("/courses", status_code=201)
def create_new_course(
    req: CreateCourseRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Admin-only: create a new course and assign faculty."""
    course = create_course(
        db=db,
        code=req.code,
        title=req.title,
        semester=req.semester,
        faculty_id=req.faculty_id,
    )
    return {
        "id": course.id,
        "code": course.code,
        "title": course.title,
        "semester": course.semester,
        "facultyId": course.faculty_id,
    }


@router.get("/courses")
def get_courses(
    faculty_id: int | None = Query(None, alias="facultyId"),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.ADMIN, Role.FACULTY)),
) -> list[dict[str, Any]]:
    """List courses (Admin sees all; Faculty can view)."""
    courses = list_courses(db=db, faculty_id=faculty_id)
    return [
        {
            "id": c.id,
            "code": c.code,
            "title": c.title,
            "semester": c.semester,
            "facultyId": c.faculty_id,
        }
        for c in courses
    ]


@router.put("/courses/{course_id}/faculty")
def assign_course_faculty(
    course_id: int,
    req: AssignFacultyRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Admin-only: assign or reassign faculty to a course."""
    course = assign_faculty_to_course(db=db, course_id=course_id, faculty_id=req.faculty_id)
    return {
        "id": course.id,
        "code": course.code,
        "title": course.title,
        "semester": course.semester,
        "facultyId": course.faculty_id,
    }


# Student Endpoints
@router.post("/students", status_code=201)
def create_new_student(
    req: CreateStudentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Admin-only: create a student record."""
    student = create_student(
        db=db,
        usn=req.usn,
        name=req.name,
        department=req.department,
        semester=req.semester,
    )
    return {
        "id": student.id,
        "usn": student.usn,
        "name": student.name,
        "department": student.department,
        "semester": student.semester,
    }


@router.get("/students")
def get_students(
    department: str | None = Query(None),
    semester: int | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> list[dict[str, Any]]:
    """Admin-only: list students."""
    students = list_students(db=db, department=department, semester=semester)
    return [
        {
            "id": s.id,
            "usn": s.usn,
            "name": s.name,
            "department": s.department,
            "semester": s.semester,
        }
        for s in students
    ]


@router.post("/students/upload", status_code=201)
async def upload_students_csv(
    request: Request,
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Admin-only: bulk import students via CSV."""
    csv_text = await _extract_csv_text(request, file)
    return import_students_csv(db=db, csv_data=csv_text)


# Enrolment Endpoints
@router.post("/courses/{course_id}/enrollments", status_code=201)
def enroll_student_in_course(
    course_id: int,
    req: EnrollStudentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Admin-only: enrol a student in a course by USN."""
    enrollment = enroll_student(db=db, course_id=course_id, usn=req.usn)
    return {
        "id": enrollment.id,
        "courseId": enrollment.course_id,
        "studentId": enrollment.student_id,
    }


@router.get("/courses/{course_id}/enrollments")
def get_course_enrollments(
    course_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.ADMIN, Role.FACULTY)),
) -> list[dict[str, Any]]:
    """List enrolled students for a course (Admin or assigned Faculty)."""
    course = get_course_by_id(db, course_id)
    if user.role is Role.FACULTY:
        faculty = db.scalars(
            select(models.Faculty).where(models.Faculty.user_id == user.id)
        ).first()
        if faculty is not None and course.faculty_id != faculty.id:
            raise AppError(403, "FORBIDDEN", "Not this course's faculty")

    return list_course_enrollments(db=db, course_id=course_id)


@router.post("/courses/{course_id}/enrollments/upload", status_code=201)
async def upload_enrollments_csv(
    course_id: int,
    request: Request,
    file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
) -> dict[str, Any]:
    """Admin-only: bulk import course enrolments via CSV."""
    csv_text = await _extract_csv_text(request, file)
    return import_enrollments_csv(db=db, course_id=course_id, csv_data=csv_text)
