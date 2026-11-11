
"""Tests for the FastAPI and database setup (issue #26)."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.app import models
from src.app.database import Base, build_engine, get_db, init_db
from src.app.errors import AppError
from src.app.main import create_app


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
def app(engine):
    application = create_app()

    def override_get_db():
        with Session(engine) as session:
            yield session

    application.dependency_overrides[get_db] = override_get_db
    return application


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def add_course(db):
    faculty = models.Faculty(name="A. Rao", department="CSE")
    student = models.Student(
        usn="PES1UG24AM001",
        name="Asha",
        department="CSE",
        semester=5,
    )
    db.add_all([faculty, student])
    db.flush()

    course = models.Course(
        code="UE24CS341A",
        title="SE",
        semester=5,
        faculty_id=faculty.id,
    )
    db.add(course)
    db.flush()

    enrollment = models.Enrollment(
        student_id=student.id,
        course_id=course.id,
    )
    db.add(enrollment)
    db.commit()

    return course, enrollment


def test_health_reports_api_and_database(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_app_starts_and_creates_tables(tmp_path):
    target = build_engine(f"sqlite:///{tmp_path / 'apas.db'}")
    init_db(target)

    assert "mark_entries" in inspect(target).get_table_names()
    target.dispose()


def test_all_sad_tables_exist(engine):
    expected = {
        "users",
        "students",
        "faculty",
        "courses",
        "enrollments",
        "assessments",
        "mark_entries",
        "attendance_records",
        "assignments",
        "assignment_submissions",
        "exam_results",
        "risk_flags",
        "interventions",
        "intervention_notes",
        "audit_log",
        "user_sessions",
        "analytics_thresholds",
    }

    assert expected == set(Base.metadata.tables)
    assert expected == set(inspect(engine).get_table_names())


def test_duplicate_enrollment_is_rejected(db):
    course, enrollment = add_course(db)

    db.add(
        models.Enrollment(
            student_id=enrollment.student_id,
            course_id=course.id,
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()


def test_duplicate_mark_for_assessment_is_rejected(db):
    course, enrollment = add_course(db)

    assessment = models.Assessment(
        course_id=course.id,
        name="ISA 1",
        max_marks=40,
        held_on=date(2026, 10, 5),
    )
    db.add(assessment)
    db.flush()

    db.add(
        models.MarkEntry(
            assessment_id=assessment.id,
            enrollment_id=enrollment.id,
            marks=30,
        )
    )
    db.commit()

    db.add(
        models.MarkEntry(
            assessment_id=assessment.id,
            enrollment_id=enrollment.id,
            marks=31,
        )
    )

    with pytest.raises(IntegrityError):
        db.commit()


def test_foreign_keys_are_enforced(db):
    db.add(models.Enrollment(student_id=999, course_id=999))

    with pytest.raises(IntegrityError):
        db.commit()


def test_risk_flag_stores_reasons_and_defaults(db):
    _course, enrollment = add_course(db)

    flag = models.RiskFlag(
        enrollment_id=enrollment.id,
        reasons=["low attendance", "low marks"],
    )
    db.add(flag)
    db.flush()

    intervention = models.Intervention(flag_id=flag.id)
    db.add(intervention)
    db.commit()
    db.refresh(flag)

    assert flag.reasons == ["low attendance", "low marks"]
    assert flag.active is True
    assert intervention.status is models.InterventionStatus.OPEN


def test_user_defaults_and_enum_role(db):
    user = models.User(
        username="faculty.rao",
        password_hash="hash",
        role=models.Role.FACULTY,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    assert user.role is models.Role.FACULTY
    assert user.is_active is True
    assert user.failed_logins == 0


def test_app_error_uses_standard_body(app, client):
    @app.get("/planned-failure")
    def planned_failure():
        raise AppError(403, "FORBIDDEN", "Not this course's faculty")

    response = client.get("/planned-failure")

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "FORBIDDEN",
            "message": "Not this course's faculty",
            "details": [],
        }
    }


def test_value_error_becomes_validation_error(app, client):
    @app.get("/analytics-failure")
    def analytics_failure():
        raise ValueError("total sessions must be positive")

    response = client.get("/analytics-failure")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["message"] == "total sessions must be positive"


def test_bad_request_data_lists_the_field(app, client):
    @app.get("/needs-number")
    def needs_number(value: int):
        return {"value": value}

    response = client.get("/needs-number", params={"value": "abc"})
    body = response.json()["error"]

    assert response.status_code == 422
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"][0]["field"] == "query.value"


def test_unknown_route_uses_standard_body(client):
    response = client.get("/api/v1/does-not-exist")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_unexpected_error_hides_details(app, client):
    @app.get("/crash")
    def crash():
        raise RuntimeError("database password is secret")

    response = client.get("/crash")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret" not in response.text
