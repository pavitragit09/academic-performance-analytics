
"""Tests for administrator user management (APAS-F-004)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
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


def login(client, username, password):
    return client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )


def test_admin_can_create_user(client, admin_user, db):
    assert login(client, "admin1", "AdminPass123!").status_code == 200

    response = client.post(
        "/api/v1/users",
        json={
            "username": "newstudent",
            "password": "StudentPass123!",
            "role": "STUDENT",
        },
    )

    assert response.status_code == 201
    assert response.json()["username"] == "newstudent"
    assert response.json()["role"] == "STUDENT"
    assert response.json()["is_active"] is True
    assert "password" not in response.json()
    assert "password_hash" not in response.json()

    user = db.scalar(
        select(models.User).where(models.User.username == "newstudent")
    )
    assert user is not None
    assert user.password_hash != "StudentPass123!"


def test_new_user_can_login_with_assigned_role(client, admin_user):
    login(client, "admin1", "AdminPass123!")

    response = client.post(
        "/api/v1/users",
        json={
            "username": "newfaculty",
            "password": "FacultyPass123!",
            "role": "FACULTY",
        },
    )
    assert response.status_code == 201

    client.post("/api/v1/auth/logout")

    login_response = login(client, "newfaculty", "FacultyPass123!")

    assert login_response.status_code == 200
    assert login_response.json()["role"] == "FACULTY"


def test_admin_can_list_users(client, admin_user):
    login(client, "admin1", "AdminPass123!")

    response = client.get("/api/v1/users")

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["username"] == "admin1"


def test_admin_can_view_user(client, admin_user):
    login(client, "admin1", "AdminPass123!")

    response = client.get(f"/api/v1/users/{admin_user.id}")

    assert response.status_code == 200
    assert response.json()["username"] == "admin1"


def test_admin_can_update_username(client, admin_user):
    login(client, "admin1", "AdminPass123!")

    response = client.put(
        f"/api/v1/users/{admin_user.id}",
        json={"username": "updatedadmin"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "updatedadmin"


def test_admin_can_assign_role(client, admin_user, student_user):
    login(client, "admin1", "AdminPass123!")

    response = client.put(
        f"/api/v1/users/{student_user.id}",
        json={"role": "FACULTY"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "FACULTY"


def test_admin_can_deactivate_user(client, admin_user, student_user, db):
    login(client, "admin1", "AdminPass123!")

    response = client.patch(
        f"/api/v1/users/{student_user.id}/status",
        json={"is_active": False},
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is False

    db.refresh(student_user)
    assert student_user.is_active is False

    client.post("/api/v1/auth/logout")

    login_response = login(client, "student1", "StudentPass123!")

    assert login_response.status_code == 403
    assert login_response.json()["error"]["message"] == "Account is inactive"


def test_admin_can_reactivate_user(client, admin_user, student_user, db):
    student_user.is_active = False
    db.commit()

    login(client, "admin1", "AdminPass123!")

    response = client.patch(
        f"/api/v1/users/{student_user.id}/status",
        json={"is_active": True},
    )

    assert response.status_code == 200
    assert response.json()["is_active"] is True


def test_non_admin_cannot_access_user_management(client, student_user):
    assert login(client, "student1", "StudentPass123!").status_code == 200

    response = client.get("/api/v1/users")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_duplicate_username_is_rejected(client, admin_user, student_user):
    login(client, "admin1", "AdminPass123!")

    response = client.post(
        "/api/v1/users",
        json={
            "username": "student1",
            "password": "AnotherPass123!",
            "role": "STUDENT",
        },
    )

    assert response.status_code == 409


def test_missing_user_returns_404(client, admin_user):
    login(client, "admin1", "AdminPass123!")

    response = client.get("/api/v1/users/99999")

    assert response.status_code == 404


def test_admin_cannot_deactivate_own_account(client, admin_user):
    login(client, "admin1", "AdminPass123!")

    response = client.patch(
        f"/api/v1/users/{admin_user.id}/status",
        json={"is_active": False},
    )

    assert response.status_code == 400
