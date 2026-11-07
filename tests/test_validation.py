
"""Tests for APAS marks and attendance validation."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.app.database import Base
from src.app.models import (
    Faculty,
    Student,
    Course,
    Enrollment,
    Assessment,
    MarkEntry,
    AttendanceRecord,
)
from src.app.validation import (
    validate_marks,
    validate_attendance,
    validate_mark_entry,
    validate_attendance_entry,
    validate_mark_batch,
    validate_attendance_batch,
)


@pytest.fixture
def db():
    """Create an isolated in-memory database for each test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)

    TestingSession = sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    session = TestingSession()

    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def sample_records(db):
    """Create sample faculty, student, course and assessment records."""
    faculty = Faculty(
        name="Test Faculty",
        department="CSE",
    )
    db.add(faculty)
    db.flush()

    student = Student(
        usn="TEST001",
        name="Test Student",
        department="CSE",
        semester=4,
    )
    db.add(student)
    db.flush()

    course = Course(
        code="TEST101",
        title="Test Course",
        semester=4,
        faculty_id=faculty.id,
    )
    db.add(course)
    db.flush()

    enrollment = Enrollment(
        student_id=student.id,
        course_id=course.id,
    )
    db.add(enrollment)
    db.flush()

    assessment = Assessment(
        course_id=course.id,
        name="Internal Assessment 1",
        max_marks=50,
        held_on=date(2026, 11, 1),
    )
    db.add(assessment)
    db.commit()

    return {
        "student": student,
        "faculty": faculty,
        "course": course,
        "enrollment": enrollment,
        "assessment": assessment,
    }


def test_valid_marks():
    validate_marks(35, 50)


@pytest.mark.parametrize("marks", [-1, 51])
def test_marks_outside_range(marks):
    with pytest.raises(ValueError):
        validate_marks(marks, 50)


def test_zero_marks_are_valid():
    validate_marks(0, 50)


def test_maximum_marks_are_valid():
    validate_marks(50, 50)


def test_zero_max_marks_rejected():
    with pytest.raises(ValueError):
        validate_marks(10, 0)


def test_non_finite_marks_rejected():
    with pytest.raises(ValueError):
        validate_marks(float("nan"), 50)


def test_valid_attendance():
    validate_attendance(8, 10)


def test_attended_greater_than_total_rejected():
    with pytest.raises(ValueError):
        validate_attendance(11, 10)


def test_negative_attendance_rejected():
    with pytest.raises(ValueError):
        validate_attendance(-1, 10)


def test_valid_mark_entry(db, sample_records):
    assessment = sample_records["assessment"]
    enrollment = sample_records["enrollment"]

    validate_mark_entry(
        db,
        assessment.id,
        enrollment.id,
        35,
    )


def test_duplicate_mark_entry_rejected(db, sample_records):
    assessment = sample_records["assessment"]
    enrollment = sample_records["enrollment"]

    db.add(
        MarkEntry(
            assessment_id=assessment.id,
            enrollment_id=enrollment.id,
            marks=30,
        )
    )
    db.commit()

    with pytest.raises(ValueError, match="duplicate"):
        validate_mark_entry(
            db,
            assessment.id,
            enrollment.id,
            35,
        )


def test_nonexistent_assessment_rejected(db, sample_records):
    enrollment = sample_records["enrollment"]

    with pytest.raises(ValueError, match="assessment does not exist"):
        validate_mark_entry(db, 9999, enrollment.id, 35)


def test_valid_attendance_entry(db, sample_records):
    enrollment = sample_records["enrollment"]

    validate_attendance_entry(
        db,
        enrollment.id,
        date(2026, 11, 2),
    )


def test_duplicate_attendance_entry_rejected(db, sample_records):
    enrollment = sample_records["enrollment"]
    session_date = date(2026, 11, 2)

    db.add(
        AttendanceRecord(
            enrollment_id=enrollment.id,
            session_date=session_date,
            present=True,
        )
    )
    db.commit()

    with pytest.raises(ValueError, match="duplicate"):
        validate_attendance_entry(
            db,
            enrollment.id,
            session_date,
        )


def test_batch_reports_invalid_marks(db, sample_records):
    assessment = sample_records["assessment"]
    enrollment = sample_records["enrollment"]

    result = validate_mark_batch(
        db,
        [
            {
                "assessment_id": assessment.id,
                "enrollment_id": enrollment.id,
                "marks": 40,
            },
            {
                "assessment_id": assessment.id,
                "enrollment_id": enrollment.id,
                "marks": 60,
            },
        ],
    )

    assert result["accepted_count"] == 1
    assert result["rejected_count"] == 1
    assert result["rejected"][0]["row"] == 2


def test_batch_reports_duplicate_rows(db, sample_records):
    assessment = sample_records["assessment"]
    enrollment = sample_records["enrollment"]

    row = {
        "assessment_id": assessment.id,
        "enrollment_id": enrollment.id,
        "marks": 40,
    }

    result = validate_mark_batch(db, [row, row])

    assert result["accepted_count"] == 1
    assert result["rejected_count"] == 1
    assert "duplicate" in result["rejected"][0]["reason"]


def test_attendance_batch_accepts_valid_rows(db, sample_records):
    enrollment = sample_records["enrollment"]

    result = validate_attendance_batch(
        db,
        [
            {
                "enrollment_id": enrollment.id,
                "session_date": date(2026, 11, 3),
                "present": True,
            }
        ],
    )

    assert result["accepted_count"] == 1
    assert result["rejected_count"] == 0


def test_attendance_batch_rejects_duplicate_rows(db, sample_records):
    enrollment = sample_records["enrollment"]

    row = {
        "enrollment_id": enrollment.id,
        "session_date": date(2026, 11, 3),
        "present": True,
    }

    result = validate_attendance_batch(db, [row, row])

    assert result["accepted_count"] == 1
    assert result["rejected_count"] == 1
    assert "duplicate" in result["rejected"][0]["reason"]


def test_attendance_batch_rejects_invalid_present_value(db, sample_records):
    enrollment = sample_records["enrollment"]

    result = validate_attendance_batch(
        db,
        [
            {
                "enrollment_id": enrollment.id,
                "session_date": date(2026, 11, 3),
                "present": "yes",
            }
        ],
    )

    assert result["accepted_count"] == 0
    assert result["rejected_count"] == 1
    assert "boolean" in result["rejected"][0]["reason"]



def test_nonexistent_enrollment_rejected(db, sample_records):
    assessment = sample_records["assessment"]

    with pytest.raises(ValueError, match="enrollment does not exist"):
        validate_mark_entry(db, assessment.id, 9999, 35)


def test_enrollment_from_different_course_rejected(db, sample_records):
    faculty = sample_records["faculty"]
    student = sample_records["student"]
    assessment = sample_records["assessment"]

    another_course = Course(
        code="TEST202",
        title="Another Course",
        semester=4,
        faculty_id=faculty.id,
    )
    db.add(another_course)
    db.flush()

    another_enrollment = Enrollment(
        student_id=student.id,
        course_id=another_course.id,
    )
    db.add(another_enrollment)
    db.commit()

    with pytest.raises(ValueError, match="does not belong"):
        validate_mark_entry(
            db,
            assessment.id,
            another_enrollment.id,
            35,
        )


def test_nonexistent_attendance_enrollment_rejected(db):
    with pytest.raises(ValueError, match="enrollment does not exist"):
        validate_attendance_entry(
            db,
            9999,
            date(2026, 11, 3),
        )

