"""Tests for intervention notes and status (APAS-F-041, APAS-F-042, TC-Int-02, TC-Int-03)."""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.app import models
from src.app.database import build_engine, get_db, init_db
from src.app.main import create_app
from src.app.notifications import get_email_sender
from src.app.security import hash_password


@pytest.fixture
def engine():
    test_engine = build_engine("sqlite://", poolclass=StaticPool)
    init_db(test_engine)
    yield test_engine
    test_engine.dispose()


def make_faculty(engine, username, name, email):
    with Session(engine, expire_on_commit=False) as db:
        user = models.User(
            username=username,
            password_hash=hash_password("FacultyPass123!"),
            role=models.Role.FACULTY,
            is_active=True,
        )
        db.add(user)
        db.flush()
        faculty = models.Faculty(user_id=user.id, name=name, department="CSE", email=email)
        db.add(faculty)
        db.commit()
        return faculty.id


@pytest.fixture
def app(engine):
    application = create_app()

    def override_get_db():
        with Session(engine, expire_on_commit=False) as session:
            yield session

    application.dependency_overrides[get_db] = override_get_db
    application.dependency_overrides[get_email_sender] = lambda: (lambda *args: True)
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def faculty_id(engine):
    return make_faculty(engine, "faculty1", "A. Rao", "arao@pes.edu")


def login(app, username):
    test_client = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
    response = test_client.post(
        "/api/v1/auth/login", json={"username": username, "password": "FacultyPass123!"}
    )
    assert response.status_code == 200
    return test_client


@pytest.fixture
def client(app, faculty_id):
    with login(app, "faculty1") as test_client:
        yield test_client


@pytest.fixture
def course(engine, faculty_id):
    """A course with two students; both have poor attendance so a risk check flags them."""
    with Session(engine) as db:
        course = models.Course(code="UE24CS341A", title="SE", semester=5, faculty_id=faculty_id)
        db.add(course)
        db.flush()
        ids = []
        for usn, name in [("PES1UG24AM001", "Asha"), ("PES1UG24AM002", "Ravi")]:
            student = models.Student(usn=usn, name=name, department="CSE", semester=5)
            db.add(student)
            db.flush()
            enrollment = models.Enrollment(student_id=student.id, course_id=course.id)
            db.add(enrollment)
            db.flush()
            for offset in range(10):
                db.add(
                    models.AttendanceRecord(
                        enrollment_id=enrollment.id,
                        session_date=date(2026, 8, 1) + timedelta(days=offset),
                        present=offset < 5,
                    )
                )
            ids.append(enrollment.id)
        db.commit()
        return {"id": course.id, "enrollments": ids}


@pytest.fixture
def interventions(client, course):
    """Run the risk check and return the list of opened interventions."""
    assert client.post(f"/api/v1/courses/{course['id']}/risk-check").status_code == 200
    response = client.get("/api/v1/interventions")
    assert response.status_code == 200
    return response.json()


def note_body(**overrides):
    body = {"actionTaken": "Met student; agreed weekly doubt-clearing sessions", "notedOn": "2026-11-10"}
    body.update(overrides)
    return body


# An intervention opens when a student is flagged
def test_flagging_a_student_opens_an_intervention(interventions):
    assert len(interventions) == 2
    first = interventions[0]
    assert first["usn"] == "PES1UG24AM001"
    assert first["reasons"] == ["low attendance"]
    assert first["status"] == "OPEN"
    assert "interventionId" in first and "updatedAt" in first


def test_repeat_risk_check_does_not_open_a_second_intervention(client, course, interventions):
    client.post(f"/api/v1/courses/{course['id']}/risk-check")
    assert len(client.get("/api/v1/interventions").json()) == 2


def test_list_can_be_filtered_by_course_and_status(client, course, interventions):
    by_course = client.get(f"/api/v1/interventions?courseId={course['id']}").json()
    assert len(by_course) == 2
    first_id = interventions[0]["interventionId"]
    client.patch(f"/api/v1/interventions/{first_id}/status", json={"status": "IN_PROGRESS"})
    open_only = client.get(f"/api/v1/interventions?courseId={course['id']}&status=OPEN").json()
    assert [i["usn"] for i in open_only] == ["PES1UG24AM002"]


def test_list_for_unknown_course_is_404(client):
    assert client.get("/api/v1/interventions?courseId=999").status_code == 404


# TC-Int-02 / APAS-F-041: notes
def test_note_is_saved_and_shown_in_history(client, interventions):
    intervention_id = interventions[0]["interventionId"]
    response = client.post(f"/api/v1/interventions/{intervention_id}/notes", json=note_body())
    assert response.status_code == 201
    assert "noteId" in response.json()

    history = client.get(f"/api/v1/interventions/{intervention_id}/notes").json()
    assert len(history) == 1
    assert history[0]["actionTaken"] == "Met student; agreed weekly doubt-clearing sessions"
    assert history[0]["notedOn"] == "2026-11-10"


def test_notes_are_listed_oldest_first(client, interventions):
    intervention_id = interventions[0]["interventionId"]
    client.post(
        f"/api/v1/interventions/{intervention_id}/notes",
        json=note_body(actionTaken="Second meeting", notedOn="2026-11-12"),
    )
    client.post(
        f"/api/v1/interventions/{intervention_id}/notes",
        json=note_body(actionTaken="First meeting", notedOn="2026-11-05"),
    )
    history = client.get(f"/api/v1/interventions/{intervention_id}/notes").json()
    assert [n["actionTaken"] for n in history] == ["First meeting", "Second meeting"]


@pytest.mark.parametrize("action", ["", "   "])
def test_empty_note_is_rejected(client, interventions, action):
    intervention_id = interventions[0]["interventionId"]
    response = client.post(
        f"/api/v1/interventions/{intervention_id}/notes", json=note_body(actionTaken=action)
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_note_with_invalid_date_is_rejected(client, interventions):
    intervention_id = interventions[0]["interventionId"]
    response = client.post(
        f"/api/v1/interventions/{intervention_id}/notes", json=note_body(notedOn="not-a-date")
    )
    assert response.status_code == 422


def test_note_on_unknown_intervention_is_404(client):
    assert client.post("/api/v1/interventions/999/notes", json=note_body()).status_code == 404


# TC-Int-03 / APAS-F-042: status
def test_status_moves_open_to_in_progress_to_resolved(client, interventions):
    intervention_id = interventions[0]["interventionId"]
    first = client.patch(f"/api/v1/interventions/{intervention_id}/status", json={"status": "IN_PROGRESS"})
    assert first.status_code == 200
    assert first.json()["status"] == "IN_PROGRESS"
    assert first.json()["interventionId"] == intervention_id
    assert "updatedBy" in first.json() and "updatedAt" in first.json()

    second = client.patch(f"/api/v1/interventions/{intervention_id}/status", json={"status": "RESOLVED"})
    assert second.status_code == 200
    assert second.json()["status"] == "RESOLVED"


@pytest.mark.parametrize(
    "path,target",
    [
        (["IN_PROGRESS", "RESOLVED"], "OPEN"),  # RESOLVED -> OPEN
        (["IN_PROGRESS", "RESOLVED"], "IN_PROGRESS"),  # RESOLVED -> IN_PROGRESS
        ([], "RESOLVED"),  # OPEN -> RESOLVED (skips a step)
        ([], "OPEN"),  # OPEN -> OPEN
    ],
)
def test_illegal_status_change_is_409(client, interventions, path, target):
    intervention_id = interventions[0]["interventionId"]
    for step in path:
        client.patch(f"/api/v1/interventions/{intervention_id}/status", json={"status": step})
    response = client.patch(f"/api/v1/interventions/{intervention_id}/status", json={"status": target})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATUS_TRANSITION"


def test_unknown_status_value_is_422(client, interventions):
    intervention_id = interventions[0]["interventionId"]
    response = client.patch(f"/api/v1/interventions/{intervention_id}/status", json={"status": "DONE"})
    assert response.status_code == 422


def test_status_change_writes_an_audit_entry(client, engine, faculty_id, interventions):
    intervention_id = interventions[0]["interventionId"]
    client.patch(f"/api/v1/interventions/{intervention_id}/status", json={"status": "IN_PROGRESS"})
    with Session(engine) as db:
        entry = db.scalar(
            select(models.AuditLogEntry).where(
                models.AuditLogEntry.entity == f"intervention:{intervention_id}"
            )
        )
    assert entry is not None
    assert (entry.old_value, entry.new_value) == ("OPEN", "IN_PROGRESS")
    assert entry.user_id is not None


def test_status_on_unknown_intervention_is_404(client):
    response = client.patch("/api/v1/interventions/999/status", json={"status": "IN_PROGRESS"})
    assert response.status_code == 404


# Access control (APAS-F-002, SR-003)
def test_login_required(app, interventions):
    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as anonymous:
        assert anonymous.get("/api/v1/interventions").status_code == 401
        assert anonymous.post("/api/v1/interventions/1/notes", json=note_body()).status_code == 401
        assert anonymous.patch("/api/v1/interventions/1/status", json={"status": "IN_PROGRESS"}).status_code == 401


def test_faculty_cannot_touch_another_facultys_intervention(app, engine, interventions):
    make_faculty(engine, "faculty2", "B. Nair", "bnair@pes.edu")
    intervention_id = interventions[0]["interventionId"]
    with login(app, "faculty2") as other:
        assert other.get("/api/v1/interventions").json() == []
        assert other.post(f"/api/v1/interventions/{intervention_id}/notes", json=note_body()).status_code == 403
        assert other.get(f"/api/v1/interventions/{intervention_id}/notes").status_code == 403
        assert other.patch(
            f"/api/v1/interventions/{intervention_id}/status", json={"status": "IN_PROGRESS"}
        ).status_code == 403


def test_other_facultys_course_filter_is_403(app, engine, course):
    make_faculty(engine, "faculty2", "B. Nair", "bnair@pes.edu")
    with login(app, "faculty2") as other:
        assert other.get(f"/api/v1/interventions?courseId={course['id']}").status_code == 403