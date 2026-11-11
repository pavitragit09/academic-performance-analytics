"""Tests for TLS 1.2+ enforcement and HSTS headers (APAS-SR-001, SAD 4.4)."""

import os
import ssl
from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.app.config import API_PREFIX
from src.app.database import build_engine, get_db, init_db
from src.app.main import create_app
from src.app.tls import HSTS_HEADER, build_tls_context, is_tls_enforced


@pytest.fixture
def engine():
    test_engine = build_engine("sqlite://", poolclass=StaticPool)
    init_db(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def app(engine):
    application = create_app()

    def override_get_db():
        with Session(engine) as session:
            yield session

    application.dependency_overrides[get_db] = override_get_db
    return application


def test_tls_context_minimum_version():
    context = build_tls_context()
    assert isinstance(context, ssl.SSLContext)
    assert context.minimum_version == ssl.TLSVersion.TLSv1_2


def test_tls_enforced_flag_detection(monkeypatch):
    monkeypatch.delenv("APAS_ENFORCE_TLS", raising=False)
    assert is_tls_enforced() is False

    monkeypatch.setenv("APAS_ENFORCE_TLS", "0")
    assert is_tls_enforced() is False

    monkeypatch.setenv("APAS_ENFORCE_TLS", "false")
    assert is_tls_enforced() is False

    monkeypatch.setenv("APAS_ENFORCE_TLS", "1")
    assert is_tls_enforced() is True

    monkeypatch.setenv("APAS_ENFORCE_TLS", "true")
    assert is_tls_enforced() is True


def test_http_allowed_when_tls_not_enforced(app, monkeypatch):
    monkeypatch.delenv("APAS_ENFORCE_TLS", raising=False)
    client = TestClient(app, base_url="http://testserver", raise_server_exceptions=False)
    resp = client.get(f"{API_PREFIX}/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "ok"}
    assert "Strict-Transport-Security" not in resp.headers


def test_http_redirected_to_https_when_enforced(app, monkeypatch):
    monkeypatch.setenv("APAS_ENFORCE_TLS", "1")
    client = TestClient(app, base_url="http://testserver", follow_redirects=False, raise_server_exceptions=False)

    # Insecure GET redirects with 301
    resp_get = client.get(f"{API_PREFIX}/health")
    assert resp_get.status_code == 301
    assert resp_get.headers["Location"].startswith("https://")
    assert resp_get.headers.get("Strict-Transport-Security") == HSTS_HEADER

    # Insecure POST redirects with 307
    resp_post = client.post(f"{API_PREFIX}/auth/login", json={"username": "a", "password": "b"})
    assert resp_post.status_code == 307
    assert resp_post.headers["Location"].startswith("https://")
    assert resp_post.headers.get("Strict-Transport-Security") == HSTS_HEADER


def test_https_allowed_with_hsts_header_when_enforced(app, monkeypatch):
    monkeypatch.setenv("APAS_ENFORCE_TLS", "1")
    # Request via HTTPS scheme
    client = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
    resp = client.get(f"{API_PREFIX}/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "database": "ok"}
    assert resp.headers.get("Strict-Transport-Security") == HSTS_HEADER

    # Request via HTTP with X-Forwarded-Proto: https
    http_client = TestClient(app, base_url="http://testserver", raise_server_exceptions=False)
    resp_forwarded = http_client.get(f"{API_PREFIX}/health", headers={"X-Forwarded-Proto": "https"})
    assert resp_forwarded.status_code == 200
    assert resp_forwarded.headers.get("Strict-Transport-Security") == HSTS_HEADER
