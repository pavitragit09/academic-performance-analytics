"""Tests for availability monitoring and uptime tracking (APAS-NF-002, TC-Ops-01)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from scripts.check_availability import probe_once, run_checks
from src.app.availability import (
    get_availability_report,
    record_probe,
    reset_availability_stats,
)
from src.app.config import API_PREFIX
from src.app.database import build_engine, get_db, init_db
from src.app.main import create_app
from src.app.models import Role, User
from src.app.security import hash_password

PASSWORD = "Password123!"


@pytest.fixture(autouse=True)
def clean_availability():
    reset_availability_stats()
    yield
    reset_availability_stats()


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


def test_availability_calculation_math():
    reset_availability_stats(custom_start=datetime.now(timezone.utc) - timedelta(seconds=120))
    # 99 successes, 1 failure -> 99.0% (below 99.5%)
    for _ in range(99):
        record_probe(is_success=True)
    record_probe(is_success=False)

    report = get_availability_report()
    assert report["totalChecks"] == 100
    assert report["successfulChecks"] == 99
    assert report["failedChecks"] == 1
    assert report["availabilityPercentage"] == 99.0
    assert report["meetsTarget"] is False
    assert report["uptimeSeconds"] >= 120.0

    # Add 100 successes -> 199 / 200 = 99.5% (meets 99.5% target)
    for _ in range(100):
        record_probe(is_success=True)

    report2 = get_availability_report()
    assert report2["totalChecks"] == 200
    assert report2["availabilityPercentage"] == 99.5
    assert report2["meetsTarget"] is True


def test_health_check_records_probe(app):
    client = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
    resp = client.get(f"{API_PREFIX}/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "ok"}

    report = get_availability_report()
    assert report["successfulChecks"] >= 1
    assert report["availabilityPercentage"] == 100.0


def test_admin_can_access_availability_endpoint(app, db):
    create_user(db, "admin1", Role.ADMIN)
    admin_client = login(app, "admin1")

    # Probe health once to populate stats
    admin_client.get(f"{API_PREFIX}/health")

    resp = admin_client.get(f"{API_PREFIX}/availability")
    assert resp.status_code == 200
    data = resp.json()
    assert "uptimeSeconds" in data
    assert "availabilityPercentage" in data
    assert data["targetPercentage"] == 99.5
    assert data["successfulChecks"] >= 1


def test_availability_endpoint_role_restrictions(app, db):
    create_user(db, "faculty1", Role.FACULTY)
    create_user(db, "student1", Role.STUDENT)

    anon_client = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
    # Anonymous 401
    assert anon_client.get(f"{API_PREFIX}/availability").status_code == 401

    # Faculty 403
    fac_client = login(app, "faculty1")
    assert fac_client.get(f"{API_PREFIX}/availability").status_code == 403

    # Student 403
    stu_client = login(app, "student1")
    assert stu_client.get(f"{API_PREFIX}/availability").status_code == 403


def test_check_availability_script_helpers(tmp_path):
    # Test probe_once with mock
    with patch("urllib.request.urlopen") as mock_open:
        mock_open.return_value.__enter__.return_value.getcode.return_value = 200
        ok, code, ms = probe_once("http://mock/health")
        assert ok is True
        assert code == 200
        assert ms >= 0

    # Test run_checks with output file
    output_file = tmp_path / "evidence.json"
    with patch("scripts.check_availability.probe_once", return_value=(True, 200, 5.0)):
        summary = run_checks("http://mock/health", count=3, interval=0.01, output_path=str(output_file))
        assert summary["totalProbes"] == 3
        assert summary["successfulProbes"] == 3
        assert summary["availabilityPercentage"] == 100.0
        assert summary["meetsTarget"] is True
        assert output_file.exists()
