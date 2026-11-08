
"""Tests for the Student Dashboard API (APAS-F-030)."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.app import models
from src.app.database import build_engine, get_db, init_db
from src.app.main import create_app
from src.app.security import hash_password


@pytest.fixture
def engine():
    test_engine = build_engine("sqlite://", poolclass=StaticPool)
    init_db(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def db(engine):
    with Session(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def client(engine):
    application = create_app()

    def override_get_db():
        with Session(engine, expire_on_commit=False) as session:
            yield session

    application.dependency_overrides[get_db] = override_get_db

    with TestClient(application, base_url="https://testserver") as test_client:
        yield test_client

    application.dependency_overrides.clear()


@pytest.fixture
def student_user(db):
    user = models.User(
        username="student1",
        password_hash=hash_password("StudentPass123!"),
        role=models.Role.STUDENT,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def faculty_user(db):
    user = models.User(
        username="faculty1",
        password_hash=hash_password("FacultyPass123!"),
        role=models.Role.FACULTY,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_user(db):
    user = models.User(
        username="admin1",
        password_hash=hash_password("AdminPass123!"),
        role=models.Role.ADMIN,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login(client, username, password):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )


@pytest.fixture
def dashboard_data(db, student_user):
    """Create academic records belonging to one student."""

    faculty = models.Faculty(
        name="A. Rao",
        department="CSE",
    )
    db.add(faculty)
    db.flush()

    student = models.Student(
        user_id=student_user.id,
        usn="PES001",
        name="Student One",
        department="CSE",
        semester=4,
    )
    db.add(student)
    db.flush()

    course = models.Course(
        code="CS101",
        title="Data Structures",
        semester=4,
        faculty_id=faculty.id,
    )
    db.add(course)
    db.flush()

    enrollment = models.Enrollment(
        student_id=student.id,
        course_id=course.id,
    )
    db.add(enrollment)
    db.flush()

    assessment = models.Assessment(
        course_id=course.id,
        name="Internal Assessment 1",
        max_marks=50,
        held_on=date(2026, 10, 15),
    )
    db.add(assessment)
    db.flush()

    mark = models.MarkEntry(
        assessment_id=assessment.id,
        enrollment_id=enrollment.id,
        marks=42,
    )

    attendance = models.AttendanceRecord(
        enrollment_id=enrollment.id,
        session_date=date(2026, 10, 16),
        present=True,
    )

    assignment = models.Assignment(
        course_id=course.id,
        title="Python Assignment",
        due_date=date(2026, 11, 10),
        max_score=20,
    )
    db.add(assignment)
    db.flush()

    submission = models.AssignmentSubmission(
        assignment_id=assignment.id,
        enrollment_id=enrollment.id,
        status=models.SubmissionStatus.SUBMITTED,
        score=18,
    )

    exam_result = models.ExamResult(
        enrollment_id=enrollment.id,
        exam_type="MIDTERM",
        marks=85,
        max_marks=100,
    )

    db.add_all([
        mark,
        attendance,
        submission,
        exam_result,
    ])
    db.commit()

    return student


def test_student_can_view_own_dashboard(
    client,
    student_user,
    dashboard_data,
):
    login_response = login(
        client,
        "student1",
        "StudentPass123!",
    )
    assert login_response.status_code == 200

    response = client.get("/api/v1/student/dashboard")

    assert response.status_code == 200

    data = response.json()

    assert data["student"]["id"] == dashboard_data.id
    assert data["student"]["name"] == "Student One"
    assert data["student"]["usn"] == "PES001"


def test_dashboard_returns_all_academic_sections(
    client,
    student_user,
    dashboard_data,
):
    login(client, "student1", "StudentPass123!")

    response = client.get("/api/v1/student/dashboard")

    assert response.status_code == 200

    data = response.json()

    assert len(data["marks"]) == 1
    assert data["marks"][0]["marks"] == 42
    assert data["marks"][0]["max_marks"] == 50

    assert len(data["attendance"]) == 1
    assert data["attendance"][0]["present"] is True

    assert len(data["assignments"]) == 1
    assert data["assignments"][0]["title"] == "Python Assignment"
    assert data["assignments"][0]["score"] == 18

    assert len(data["exam_results"]) == 1
    assert data["exam_results"][0]["marks"] == 85


def test_dashboard_requires_authentication(client):
    response = client.get("/api/v1/student/dashboard")

    assert response.status_code == 401


@pytest.mark.parametrize(
    "username,password",
    [
        ("faculty1", "FacultyPass123!"),
        ("admin1", "AdminPass123!"),
    ],
)
def test_non_student_roles_cannot_access_dashboard(
    client,
    faculty_user,
    admin_user,
    username,
    password,
):
    login(client, username, password)

    response = client.get("/api/v1/student/dashboard")

    assert response.status_code == 403


def test_student_without_linked_profile_receives_404(
    client,
    student_user,
):
    login(client, "student1", "StudentPass123!")

    response = client.get("/api/v1/student/dashboard")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_student_cannot_see_another_students_records(
    client,
    db,
    student_user,
    dashboard_data,
):
    other_user = models.User(
        username="student2",
        password_hash=hash_password("StudentPass456!"),
        role=models.Role.STUDENT,
        is_active=True,
    )
    db.add(other_user)
    db.flush()

    other_student = models.Student(
        user_id=other_user.id,
        usn="PES002",
        name="Student Two",
        department="CSE",
        semester=4,
    )
    db.add(other_student)
    db.flush()

    faculty = db.query(models.Faculty).first()

    other_course = models.Course(
        code="CS202",
        title="Database Systems",
        semester=4,
        faculty_id=faculty.id,
    )
    db.add(other_course)
    db.flush()

    other_enrollment = models.Enrollment(
        student_id=other_student.id,
        course_id=other_course.id,
    )
    db.add(other_enrollment)
    db.flush()

    other_assessment = models.Assessment(
        course_id=other_course.id,
        name="Internal Assessment",
        max_marks=50,
        held_on=date(2026, 10, 20),
    )
    db.add(other_assessment)
    db.flush()

    db.add(
        models.MarkEntry(
            assessment_id=other_assessment.id,
            enrollment_id=other_enrollment.id,
            marks=10,
        )
    )
    db.commit()

    login(client, "student1", "StudentPass123!")

    response = client.get("/api/v1/student/dashboard")

    assert response.status_code == 200

    data = response.json()

    assert data["student"]["usn"] == "PES001"
    assert all(
        mark["course_code"] != "CS202"
        for mark in data["marks"]
    )



def test_dashboard_includes_assignments_not_yet_submitted(
    client,
    db,
    student_user,
    dashboard_data,
):
    """Assignments should appear even when no submission exists."""

    course = db.query(models.Course).filter_by(
        code="CS101"
    ).first()

    pending_assignment = models.Assignment(
        course_id=course.id,
        title="Pending Python Assignment",
        due_date=date(2026, 11, 15),
        max_score=20,
    )
    db.add(pending_assignment)
    db.commit()

    login(client, "student1", "StudentPass123!")

    response = client.get("/api/v1/student/dashboard")

    assert response.status_code == 200

    assignments = response.json()["assignments"]

    pending = next(
        item for item in assignments
        if item["title"] == "Pending Python Assignment"
    )

    assert pending["submitted"] is False
    assert pending["status"] is None
    assert pending["score"] is None
    assert pending["max_score"] == 20
