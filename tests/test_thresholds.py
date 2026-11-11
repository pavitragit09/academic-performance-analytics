"""Tests for administrator-configurable analytics thresholds (APAS-F-025, TC-Ops-01, TC-Sec-05)."""

from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.app import models
from src.app.audit import list_audit_logs
from src.app.config import API_PREFIX
from src.app.database import build_engine, get_db, init_db
from src.app.main import create_app
from src.app.models import AuditLogEntry, Role, User
from src.app.security import hash_password
from src.app.thresholds import (
    DEFAULT_ATTENDANCE_THRESHOLD,
    DEFAULT_MARKS_THRESHOLD,
    DEFAULT_TREND_WINDOW,
    get_analytics_thresholds,
    update_analytics_thresholds,
)

PASSWORD = "Password123!"


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


def create_user(db: Session, username: str, role: Role) -> User:
    user = User(
        username=username,
        password_hash=hash_password(PASSWORD),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login(app, username: str) -> TestClient:
    client = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
    resp = client.post(f"{API_PREFIX}/auth/login", json={"username": username, "password": PASSWORD})
    assert resp.status_code == 200
    return client


def test_default_thresholds_initialized(db: Session):
    thresholds = get_analytics_thresholds(db)
    assert thresholds.attendance_threshold == DEFAULT_ATTENDANCE_THRESHOLD
    assert thresholds.marks_threshold == DEFAULT_MARKS_THRESHOLD
    assert thresholds.trend_window == DEFAULT_TREND_WINDOW


def test_admin_get_and_update_thresholds(app, db):
    admin = create_user(db, "admin1", Role.ADMIN)
    admin_client = login(app, "admin1")

    # GET default thresholds
    resp = admin_client.get(f"{API_PREFIX}/settings/thresholds")
    assert resp.status_code == 200
    data = resp.json()
    assert data["attendanceThreshold"] == 75.0
    assert data["marksThreshold"] == 40.0
    assert data["trendWindow"] == 3

    # PUT updated thresholds
    update_resp = admin_client.put(
        f"{API_PREFIX}/settings/thresholds",
        json={"attendanceThreshold": 80.0, "marksThreshold": 50.0, "trendWindow": 4},
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["attendanceThreshold"] == 80.0
    assert updated["marksThreshold"] == 50.0
    assert updated["trendWindow"] == 4

    # Verify audit log recorded
    logs = list_audit_logs(db, entity="analytics_thresholds")
    assert len(logs) >= 1
    assert logs[0]["userId"] == admin.id
    assert logs[0]["action"] == "UPDATE_ANALYTICS_THRESHOLDS"
    assert "80.0" in logs[0]["newValue"]


def test_thresholds_role_enforcement(app, db):
    create_user(db, "faculty1", Role.FACULTY)
    create_user(db, "student1", Role.STUDENT)

    anon_client = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
    # Unauthenticated
    resp = anon_client.get(f"{API_PREFIX}/settings/thresholds")
    assert resp.status_code == 401

    # Faculty forbidden
    fac_client = login(app, "faculty1")
    resp_fac_get = fac_client.get(f"{API_PREFIX}/settings/thresholds")
    assert resp_fac_get.status_code == 403
    resp_fac_put = fac_client.put(
        f"{API_PREFIX}/settings/thresholds",
        json={"attendanceThreshold": 80.0, "marksThreshold": 50.0, "trendWindow": 3},
    )
    assert resp_fac_put.status_code == 403

    # Student forbidden
    stu_client = login(app, "student1")
    resp_stu_get = stu_client.get(f"{API_PREFIX}/settings/thresholds")
    assert resp_stu_get.status_code == 403


def test_thresholds_validation_ranges(app, db):
    create_user(db, "admin1", Role.ADMIN)
    admin_client = login(app, "admin1")

    # Negative attendance
    r1 = admin_client.put(
        f"{API_PREFIX}/settings/thresholds",
        json={"attendanceThreshold": -5.0, "marksThreshold": 40.0, "trendWindow": 3},
    )
    assert r1.status_code in (400, 422)

    # Attendance > 100
    r2 = admin_client.put(
        f"{API_PREFIX}/settings/thresholds",
        json={"attendanceThreshold": 105.0, "marksThreshold": 40.0, "trendWindow": 3},
    )
    assert r2.status_code in (400, 422)

    # Marks < 0
    r3 = admin_client.put(
        f"{API_PREFIX}/settings/thresholds",
        json={"attendanceThreshold": 75.0, "marksThreshold": -1.0, "trendWindow": 3},
    )
    assert r3.status_code in (400, 422)

    # Marks > 100
    r4 = admin_client.put(
        f"{API_PREFIX}/settings/thresholds",
        json={"attendanceThreshold": 75.0, "marksThreshold": 150.0, "trendWindow": 3},
    )
    assert r4.status_code in (400, 422)

    # Trend window < 2
    r5 = admin_client.put(
        f"{API_PREFIX}/settings/thresholds",
        json={"attendanceThreshold": 75.0, "marksThreshold": 40.0, "trendWindow": 1},
    )
    assert r5.status_code in (400, 422)


def test_threshold_update_dynamically_affects_dashboard(app, db):
    admin = create_user(db, "admin1", Role.ADMIN)
    faculty_user = create_user(db, "prof", Role.FACULTY)
    faculty = models.Faculty(name="Prof. X", department="CSE", user_id=faculty_user.id)
    student = models.Student(usn="1MS21CS001", name="Alice", department="CSE", semester=5)
    db.add_all([faculty, student])
    db.flush()

    course = models.Course(code="CS501", title="Algorithms", semester=5, faculty_id=faculty.id)
    db.add(course)
    db.flush()

    enrollment = models.Enrollment(student_id=student.id, course_id=course.id)
    db.add(enrollment)
    db.flush()

    # Student has 70% attendance (7 present out of 10)
    for i in range(7):
        db.add(models.AttendanceRecord(enrollment_id=enrollment.id, session_date=date(2026, 10, i + 1), present=True))
    for i in range(3):
        db.add(models.AttendanceRecord(enrollment_id=enrollment.id, session_date=date(2026, 10, 8 + i), present=False))

    assessment = models.Assessment(course_id=course.id, name="Quiz 1", max_marks=100.0, held_on=date.today())
    db.add(assessment)
    db.flush()
    db.add(models.MarkEntry(assessment_id=assessment.id, enrollment_id=enrollment.id, marks=50.0))
    db.commit()

    admin_client = login(app, "admin1")

    # Under default threshold (attendance 75%): student is at risk (70% < 75%)
    resp1 = admin_client.get(f"{API_PREFIX}/dashboard/courses/{course.id}")
    assert resp1.status_code == 200
    assert len(resp1.json()["atRisk"]) == 1

    # Now admin lowers attendance threshold to 65%
    put_resp = admin_client.put(
        f"{API_PREFIX}/settings/thresholds",
        json={"attendanceThreshold": 65.0, "marksThreshold": 40.0, "trendWindow": 3},
    )
    assert put_resp.status_code == 200

    # Without query parameters, dashboard now sees student is NOT at risk (70% >= 65%)
    resp2 = admin_client.get(f"{API_PREFIX}/dashboard/courses/{course.id}")
    assert resp2.status_code == 200
    assert len(resp2.json()["atRisk"]) == 0
