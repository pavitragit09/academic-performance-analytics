"""Course, student, enrolment and faculty records management (APAS-F-015)."""

import csv
import io
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app import models
from src.app.errors import AppError


def list_courses(db: Session, faculty_id: int | None = None) -> list[models.Course]:
    """List all courses, optionally filtered by assigned faculty member."""
    stmt = select(models.Course)
    if faculty_id is not None:
        stmt = stmt.where(models.Course.faculty_id == faculty_id)
    stmt = stmt.order_by(models.Course.code)
    return list(db.scalars(stmt).all())


def get_course_by_id(db: Session, course_id: int) -> models.Course:
    """Fetch a course by ID or raise 404."""
    course = db.get(models.Course, course_id)
    if course is None:
        raise AppError(404, "NOT_FOUND", f"Course with id {course_id} not found")
    return course


def get_course_by_code(db: Session, code: str) -> models.Course | None:
    """Fetch a course by code or return None."""
    stmt = select(models.Course).where(models.Course.code == code)
    return db.scalars(stmt).first()


def create_course(
    db: Session,
    code: str,
    title: str,
    semester: int,
    faculty_id: int,
) -> models.Course:
    """Create a new course assigned to a faculty member."""
    clean_code = code.strip().upper() if code else ""
    clean_title = title.strip() if title else ""

    if not clean_code:
        raise AppError(422, "VALIDATION_ERROR", "Course code cannot be empty")
    if not clean_title:
        raise AppError(422, "VALIDATION_ERROR", "Course title cannot be empty")
    if semester <= 0:
        raise AppError(422, "VALIDATION_ERROR", "Semester must be a positive integer")

    faculty = db.get(models.Faculty, faculty_id)
    if faculty is None:
        raise AppError(404, "NOT_FOUND", f"Faculty with id {faculty_id} not found")

    existing = get_course_by_code(db, clean_code)
    if existing is not None:
        raise AppError(
            409,
            "DUPLICATE_ENTRY",
            f"Course with code '{clean_code}' already exists",
        )

    course = models.Course(
        code=clean_code,
        title=clean_title,
        semester=semester,
        faculty_id=faculty_id,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return course


def assign_faculty_to_course(
    db: Session,
    course_id: int,
    faculty_id: int,
) -> models.Course:
    """Assign or reassign a course to a faculty member."""
    course = get_course_by_id(db, course_id)
    faculty = db.get(models.Faculty, faculty_id)
    if faculty is None:
        raise AppError(404, "NOT_FOUND", f"Faculty with id {faculty_id} not found")

    course.faculty_id = faculty_id
    db.commit()
    db.refresh(course)
    return course


def get_student_by_id(db: Session, student_id: int) -> models.Student:
    """Fetch student by ID or raise 404."""
    student = db.get(models.Student, student_id)
    if student is None:
        raise AppError(404, "NOT_FOUND", f"Student with id {student_id} not found")
    return student


def get_student_by_usn(db: Session, usn: str) -> models.Student | None:
    """Fetch student by USN or return None."""
    stmt = select(models.Student).where(models.Student.usn == usn.strip().upper())
    return db.scalars(stmt).first()


def list_students(
    db: Session,
    department: str | None = None,
    semester: int | None = None,
) -> list[models.Student]:
    """List all students with optional filters."""
    stmt = select(models.Student)
    if department is not None:
        stmt = stmt.where(models.Student.department == department)
    if semester is not None:
        stmt = stmt.where(models.Student.semester == semester)
    stmt = stmt.order_by(models.Student.usn)
    return list(db.scalars(stmt).all())


def create_student(
    db: Session,
    usn: str,
    name: str,
    department: str,
    semester: int,
) -> models.Student:
    """Create a new student record."""
    clean_usn = usn.strip().upper() if usn else ""
    clean_name = name.strip() if name else ""
    clean_dept = department.strip() if department else ""

    if not clean_usn:
        raise AppError(422, "VALIDATION_ERROR", "USN cannot be empty")
    if not clean_name:
        raise AppError(422, "VALIDATION_ERROR", "Name cannot be empty")
    if not clean_dept:
        raise AppError(422, "VALIDATION_ERROR", "Department cannot be empty")
    if semester <= 0:
        raise AppError(422, "VALIDATION_ERROR", "Semester must be a positive integer")

    existing = get_student_by_usn(db, clean_usn)
    if existing is not None:
        raise AppError(
            409,
            "DUPLICATE_ENTRY",
            f"Student with USN '{clean_usn}' already exists",
        )

    student = models.Student(
        usn=clean_usn,
        name=clean_name,
        department=clean_dept,
        semester=semester,
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


def enroll_student(db: Session, course_id: int, usn: str) -> models.Enrollment:
    """Enrol a student in a course by USN."""
    course = get_course_by_id(db, course_id)
    student = get_student_by_usn(db, usn)
    if student is None:
        raise AppError(404, "NOT_FOUND", f"Student with USN '{usn}' not found")

    stmt = select(models.Enrollment).where(
        models.Enrollment.course_id == course.id,
        models.Enrollment.student_id == student.id,
    )
    existing = db.scalars(stmt).first()
    if existing is not None:
        raise AppError(
            409,
            "DUPLICATE_ENTRY",
            f"Student '{student.usn}' is already enrolled in course '{course.code}'",
        )

    enrollment = models.Enrollment(student_id=student.id, course_id=course.id)
    db.add(enrollment)
    db.commit()
    db.refresh(enrollment)
    return enrollment


def list_course_enrollments(db: Session, course_id: int) -> list[dict[str, Any]]:
    """List enrolled students for a course."""
    course = get_course_by_id(db, course_id)
    stmt = (
        select(models.Student, models.Enrollment)
        .join(models.Enrollment, models.Student.id == models.Enrollment.student_id)
        .where(models.Enrollment.course_id == course.id)
        .order_by(models.Student.usn)
    )
    rows = db.execute(stmt).all()
    return [
        {
            "enrollmentId": enrollment.id,
            "studentId": student.id,
            "usn": student.usn,
            "name": student.name,
            "department": student.department,
            "semester": student.semester,
        }
        for student, enrollment in rows
    ]


def check_student_enrolled(
    db: Session,
    course_id: int,
    usn: str,
) -> models.Enrollment:
    """
    Reusable enrolment check: ensure student exists and is enrolled in the course.

    Used by marks and attendance entry (APAS-F-015, TC-Data-06).
    Raises AppError(400, "NOT_ENROLLED", ...) if not enrolled.
    """
    clean_usn = usn.strip().upper() if usn else ""
    student = get_student_by_usn(db, clean_usn)
    if student is None:
        raise AppError(
            400,
            "NOT_ENROLLED",
            f"Student with USN '{clean_usn}' is not enrolled in course {course_id} (student not found)",
        )

    stmt = select(models.Enrollment).where(
        models.Enrollment.course_id == course_id,
        models.Enrollment.student_id == student.id,
    )
    enrollment = db.scalars(stmt).first()
    if enrollment is None:
        raise AppError(
            400,
            "NOT_ENROLLED",
            f"Student '{clean_usn}' is not enrolled in course {course_id}",
        )
    return enrollment


def is_student_enrolled(db: Session, course_id: int, usn: str) -> bool:
    """Return True if student exists and is enrolled in course, else False."""
    try:
        check_student_enrolled(db, course_id, usn)
        return True
    except AppError:
        return False


def import_students_csv(db: Session, csv_data: str | bytes) -> dict[str, Any]:
    """
    Import students from CSV text or bytes.

    Expected CSV header: usn, name, department, semester
    Reports bad rows, rejects duplicates, and handles malformed files gracefully.
    """
    if isinstance(csv_data, bytes):
        try:
            text = csv_data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = csv_data.decode("latin-1")
            except Exception:
                raise AppError(400, "BAD_FILE", "Unable to decode CSV file as text")
    else:
        text = str(csv_data)

    if not text.strip():
        raise AppError(400, "BAD_FILE", "CSV file is empty")

    stream = io.StringIO(text)
    try:
        reader = csv.reader(stream)
        rows = list(reader)
    except Exception as exc:
        raise AppError(400, "BAD_FILE", f"Malformed CSV file: {exc}")

    if not rows:
        raise AppError(400, "BAD_FILE", "CSV file has no rows")

    header = [h.strip().lower() for h in rows[0]]
    expected_cols = {"usn", "name", "department", "semester"}
    if not expected_cols.issubset(set(header)):
        raise AppError(
            400,
            "BAD_FILE",
            f"CSV header must contain usn, name, department, semester. Found: {rows[0]}",
        )

    usn_idx = header.index("usn")
    name_idx = header.index("name")
    dept_idx = header.index("department")
    sem_idx = header.index("semester")

    accepted = 0
    rejected: list[dict[str, Any]] = []
    seen_file_usns: set[str] = set()
    to_create: list[models.Student] = []

    for row_idx, row in enumerate(rows[1:], start=2):
        if not row or all(c.strip() == "" for c in row):
            continue

        if len(row) <= max(usn_idx, name_idx, dept_idx, sem_idx):
            rejected.append({"row": row_idx, "reason": "Missing required columns"})
            continue

        raw_usn = row[usn_idx].strip().upper()
        raw_name = row[name_idx].strip()
        raw_dept = row[dept_idx].strip()
        raw_sem = row[sem_idx].strip()

        if not raw_usn or not raw_name or not raw_dept:
            rejected.append(
                {"row": row_idx, "usn": raw_usn, "reason": "USN, name, and department cannot be empty"}
            )
            continue

        try:
            sem_val = int(raw_sem)
            if sem_val <= 0:
                raise ValueError
        except ValueError:
            rejected.append(
                {"row": row_idx, "usn": raw_usn, "reason": f"Invalid semester '{raw_sem}'"}
            )
            continue

        if raw_usn in seen_file_usns:
            rejected.append(
                {"row": row_idx, "usn": raw_usn, "reason": f"Duplicate USN '{raw_usn}' within file"}
            )
            continue

        # Check existing in DB
        if get_student_by_usn(db, raw_usn) is not None:
            rejected.append(
                {"row": row_idx, "usn": raw_usn, "reason": f"Student '{raw_usn}' already exists in database"}
            )
            continue

        seen_file_usns.add(raw_usn)
        to_create.append(
            models.Student(
                usn=raw_usn,
                name=raw_name,
                department=raw_dept,
                semester=sem_val,
            )
        )
        accepted += 1

    if to_create:
        db.add_all(to_create)
        db.commit()

    return {
        "accepted": accepted,
        "rejected": rejected,
        "totalRows": len(rows) - 1,
    }


def import_enrollments_csv(
    db: Session,
    course_id: int,
    csv_data: str | bytes,
) -> dict[str, Any]:
    """
    Import course enrolments from CSV text or bytes.

    Expected CSV header: usn
    Reports bad rows and duplicates without crashing on malformed files.
    """
    course = get_course_by_id(db, course_id)

    if isinstance(csv_data, bytes):
        try:
            text = csv_data.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = csv_data.decode("latin-1")
            except Exception:
                raise AppError(400, "BAD_FILE", "Unable to decode CSV file as text")
    else:
        text = str(csv_data)

    if not text.strip():
        raise AppError(400, "BAD_FILE", "CSV file is empty")

    stream = io.StringIO(text)
    try:
        reader = csv.reader(stream)
        rows = list(reader)
    except Exception as exc:
        raise AppError(400, "BAD_FILE", f"Malformed CSV file: {exc}")

    if not rows:
        raise AppError(400, "BAD_FILE", "CSV file has no rows")

    header = [h.strip().lower() for h in rows[0]]
    if "usn" not in header:
        raise AppError(400, "BAD_FILE", f"CSV header must contain 'usn'. Found: {rows[0]}")

    usn_idx = header.index("usn")

    accepted = 0
    rejected: list[dict[str, Any]] = []
    seen_file_usns: set[str] = set()
    to_create: list[models.Enrollment] = []

    # Get existing enrolled student IDs for this course
    existing_enrolled_stmt = select(models.Enrollment.student_id).where(
        models.Enrollment.course_id == course.id
    )
    existing_student_ids = set(db.scalars(existing_enrolled_stmt).all())

    for row_idx, row in enumerate(rows[1:], start=2):
        if not row or all(c.strip() == "" for c in row):
            continue

        if len(row) <= usn_idx:
            rejected.append({"row": row_idx, "reason": "Missing USN column"})
            continue

        raw_usn = row[usn_idx].strip().upper()
        if not raw_usn:
            rejected.append({"row": row_idx, "reason": "USN cannot be empty"})
            continue

        if raw_usn in seen_file_usns:
            rejected.append(
                {"row": row_idx, "usn": raw_usn, "reason": f"Duplicate USN '{raw_usn}' in file"}
            )
            continue

        student = get_student_by_usn(db, raw_usn)
        if student is None:
            rejected.append(
                {"row": row_idx, "usn": raw_usn, "reason": f"Student '{raw_usn}' does not exist"}
            )
            continue

        if student.id in existing_student_ids:
            rejected.append(
                {"row": row_idx, "usn": raw_usn, "reason": f"Student '{raw_usn}' already enrolled in course"}
            )
            continue

        seen_file_usns.add(raw_usn)
        existing_student_ids.add(student.id)
        to_create.append(
            models.Enrollment(student_id=student.id, course_id=course.id)
        )
        accepted += 1

    if to_create:
        db.add_all(to_create)
        db.commit()

    return {
        "accepted": accepted,
        "rejected": rejected,
        "totalRows": len(rows) - 1,
    }
