
"""Tests for session-based authentication and role-based authorization."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends, Request
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.app import models
from src.app.database import build_engine, get_db, init_db
from src.app.main import create_app
from src.app.routers.auth import (
    SESSION_COOKIE,
    require_admin,
    require_faculty,
    require_student,
    verify_student_ownership,
)
from src.app.security import hash_password, hash_session_token


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

    @application.get("/api/v1/test/admin")
    def admin_test(user=Depends(require_admin)):
        return {"username": user.username, "role": user.role.value}

    @application.get("/api/v1/test/faculty")
    def faculty_test(user=Depends(require_faculty)):
        return {"username": user.username, "role": user.role.value}

    @application.get("/api/v1/test/student")
    def student_test(user=Depends(require_student)):
        return {"username": user.username, "role": user.role.value}

    @application.get("/api/v1/test/students/{student_id}")
    def student_record_test(
        student_id: int,
        request: Request,
        user=Depends(require_student),
        session: Session = Depends(get_db),
    ):
        student = verify_student_ownership(
            student_id, user, session, request
        )
        return {"student_id": student.id, "name": student.name}

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


def test_successful_login(client, student_user, db):
    response = login(client, "student1", "StudentPass123!")

    assert response.status_code == 200
    assert response.json()["userId"] == student_user.id
    assert response.json()["role"] == "STUDENT"
    assert response.json()["name"] == "student1"
    assert "access_token" not in response.json()

    cookie_header = response.headers["set-cookie"]
    assert "HttpOnly" in cookie_header
    assert "Secure" in cookie_header
    assert "SameSite=lax" in cookie_header

    raw_token = client.cookies.get(SESSION_COOKIE)
    assert raw_token is not None

    stored_session = db.scalar(select(models.UserSession))
    assert stored_session is not None
    assert stored_session.token_hash != raw_token
    assert stored_session.user_id == student_user.id


def test_invalid_password(client, student_user, db):
    response = login(client, "student1", "WrongPass123!")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"

    db.refresh(student_user)
    assert student_user.failed_logins == 1


def test_unknown_username(client):
    response = login(client, "unknown", "SomePass123!")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_inactive_user_cannot_login(client, db):
    user = models.User(
        username="inactive",
        password_hash=hash_password("StudentPass123!"),
        role=models.Role.STUDENT,
        is_active=False,
    )
    db.add(user)
    db.commit()

    response = login(client, "inactive", "StudentPass123!")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_profile_requires_session(client):
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401


def test_profile_with_valid_session(client, student_user):
    response = login(client, "student1", "StudentPass123!")
    assert response.status_code == 200

    profile_response = client.get("/api/v1/auth/me")

    assert profile_response.status_code == 200
    assert profile_response.json()["username"] == "student1"
    assert profile_response.json()["role"] == "STUDENT"


def test_invalid_session_is_rejected(client):
    response = client.get(
        "/api/v1/auth/me",
        headers={"Cookie": f"{SESSION_COOKIE}=invalid-session-token"},
    )

    assert response.status_code == 401


def test_logout_revokes_session(client, db, student_user):
    login_response = login(client, "student1", "StudentPass123!")
    assert login_response.status_code == 200

    raw_token = client.cookies.get(SESSION_COOKIE)
    assert raw_token is not None

    logout_response = client.post("/api/v1/auth/logout")
    assert logout_response.status_code == 204

    stored_session = db.scalar(
        select(models.UserSession).where(
            models.UserSession.token_hash == hash_session_token(raw_token)
        )
    )

    assert stored_session is not None
    assert stored_session.is_revoked is True

    profile_response = client.get("/api/v1/auth/me")
    assert profile_response.status_code == 401


def test_fifth_failed_attempt_locks_account(client, student_user, db):
    for attempt in range(5):
        response = login(client, "student1", "WrongPass123!")

        if attempt < 4:
            assert response.status_code == 401
        else:
            assert response.status_code == 423
            assert response.json()["error"]["code"] == "ACCOUNT_LOCKED"

    db.refresh(student_user)
    assert student_user.failed_logins == 5
    assert student_user.locked_until is not None

    locked_until = student_user.locked_until
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)

    assert locked_until > datetime.now(timezone.utc)


def test_locked_account_rejects_correct_password(client, student_user):
    for _ in range(5):
        login(client, "student1", "WrongPass123!")

    response = login(client, "student1", "StudentPass123!")

    assert response.status_code == 423
    assert response.json()["error"]["code"] == "ACCOUNT_LOCKED"


def test_expired_session_is_rejected(client, student_user, db):
    login_response = login(client, "student1", "StudentPass123!")
    assert login_response.status_code == 200

    stored_session = db.scalar(select(models.UserSession))
    assert stored_session is not None

    stored_session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()

    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401

    db.refresh(stored_session)
    assert stored_session.is_revoked is True


def test_admin_can_access_admin_endpoint(client, admin_user):
    login(client, "admin1", "AdminPass123!")

    response = client.get("/api/v1/test/admin")

    assert response.status_code == 200
    assert response.json()["role"] == "ADMIN"


def test_student_cannot_access_admin_endpoint(client, student_user):
    login(client, "student1", "StudentPass123!")

    response = client.get("/api/v1/test/admin")
    assert response.status_code == 403


def test_faculty_cannot_access_admin_endpoint(client, faculty_user):
    login(client, "faculty1", "FacultyPass123!")

    response = client.get("/api/v1/test/admin")
    assert response.status_code == 403


def test_faculty_can_access_faculty_endpoint(client, faculty_user):
    login(client, "faculty1", "FacultyPass123!")

    response = client.get("/api/v1/test/faculty")

    assert response.status_code == 200
    assert response.json()["role"] == "FACULTY"


def test_student_can_access_student_endpoint(client, student_user):
    login(client, "student1", "StudentPass123!")

    response = client.get("/api/v1/test/student")

    assert response.status_code == 200
    assert response.json()["role"] == "STUDENT"


def test_role_change_uses_current_database_role(client, db, student_user):
    login(client, "student1", "StudentPass123!")

    student_user.role = models.Role.FACULTY
    db.commit()

    profile_response = client.get("/api/v1/auth/me")

    assert profile_response.status_code == 200
    assert profile_response.json()["role"] == "FACULTY"

    admin_response = client.get("/api/v1/test/admin")
    assert admin_response.status_code == 403


def test_student_can_access_own_record(client, db, student_user):
    student = models.Student(
        user_id=student_user.id,
        usn="PES001",
        name="Student One",
        department="CSE",
        semester=4,
    )
    db.add(student)
    db.commit()
    db.refresh(student)

    login(client, "student1", "StudentPass123!")

    response = client.get(f"/api/v1/test/students/{student.id}")

    assert response.status_code == 200
    assert response.json()["student_id"] == student.id


def test_student_cannot_access_another_students_record(
    client, db, student_user
):
    another_user = models.User(
        username="student2",
        password_hash=hash_password("StudentPass456!"),
        role=models.Role.STUDENT,
        is_active=True,
    )
    db.add(another_user)
    db.commit()
    db.refresh(another_user)

    another_student = models.Student(
        user_id=another_user.id,
        usn="PES002",
        name="Student Two",
        department="CSE",
        semester=4,
    )
    db.add(another_student)
    db.commit()
    db.refresh(another_student)

    login(client, "student1", "StudentPass123!")

    response = client.get(
        f"/api/v1/test/students/{another_student.id}"
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"

    audit_entry = db.scalar(
        select(models.AuditLogEntry).where(
            models.AuditLogEntry.action == "ACCESS_DENIED"
        )
    )
    assert audit_entry is not None



# TC-Auth-02.2: a student cannot call a faculty-only function
def test_student_cannot_access_faculty_endpoint(client, student_user):
    login(client, "student1", "StudentPass123!")

    response = client.get("/api/v1/test/faculty")

    assert response.status_code == 403


# TC-Sec-04: injection strings are handled safely in the login fields
def test_login_with_sql_injection_strings_is_rejected(client, student_user, db):
    attempts = [
        ("' OR '1'='1", "' OR '1'='1"),
        ("student1' --", "anything"),
        ("'; DROP TABLE users; --", "anything"),
    ]

    for username, password in attempts:
        response = login(client, username, password)
        assert response.status_code == 401

    assert db.scalar(select(models.UserSession)) is None
    assert db.scalar(
        select(models.User).where(models.User.username == "student1")
    ) is not None
