"""Tests for the web UI (APAS-NF-004, TC-UX-01).

The full accessibility audit (axe-core, WCAG 2.1 AA, desktop and mobile) is run with
scripts/a11y_audit.py; these tests keep the accessibility and security basics from regressing.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.app import models
from src.app.database import build_engine, get_db, init_db
from src.app.main import create_app
from src.app.security import hash_password

API = "/api/v1"
PASSWORD = "TestPass123!"
WEB = Path(__file__).resolve().parents[1] / "src" / "app" / "web"


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
        with Session(engine, expire_on_commit=False) as session:
            yield session

    application.dependency_overrides[get_db] = override_get_db
    return application


@pytest.fixture
def client(app):
    return TestClient(app, base_url="https://testserver", raise_server_exceptions=False)


def login(app, username):
    client = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
    response = client.post(f"{API}/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200
    return client


@pytest.fixture
def courses(engine):
    with Session(engine) as db:
        users = {}
        for name, role in [("faculty1", models.Role.FACULTY), ("faculty2", models.Role.FACULTY),
                           ("admin1", models.Role.ADMIN), ("student1", models.Role.STUDENT)]:
            users[name] = models.User(
                username=name, password_hash=hash_password(PASSWORD), role=role, is_active=True
            )
            db.add(users[name])
        db.flush()
        rao = models.Faculty(user_id=users["faculty1"].id, name="A. Rao", department="CSE")
        iyer = models.Faculty(user_id=users["faculty2"].id, name="B. Iyer", department="CSE")
        db.add_all([rao, iyer])
        db.flush()
        db.add_all([
            models.Course(code="UE24CS342A", title="Databases", semester=5, faculty_id=rao.id),
            models.Course(code="UE24CS341A", title="Software Engineering", semester=5, faculty_id=rao.id),
            models.Course(code="UE24CS343A", title="Networks", semester=5, faculty_id=iyer.id),
        ])
        db.commit()


# ---------- pages are served ----------

def test_home_redirects_to_the_web_ui(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "/app/"


def test_ui_files_are_public(client):
    for path, kind in [("/app/", "text/html"), ("/app/app.js", "javascript"), ("/app/app.css", "text/css")]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert kind in response.headers["content-type"], path


# ---------- accessibility basics (WCAG 2.1 AA) ----------

def page():
    return (WEB / "index.html").read_text(encoding="utf-8")


def test_page_language_title_and_viewport():
    html = page()

    assert '<html lang="en">' in html                                     # 3.1.1
    assert re.search(r"<title>[^<]+</title>", html)                       # 2.4.2
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in html  # reflow
    assert "user-scalable=no" not in html and "maximum-scale" not in html  # 1.4.4 zoom allowed


def test_landmarks_and_skip_link():
    html = page()

    assert '<a class="skip-link" href="#main">' in html                   # 2.4.1
    assert '<main id="main"' in html
    assert "<header" in html and "<footer" in html and "<nav" in html
    assert 'role="status" aria-live="polite"' in html                     # 4.1.3


def test_focus_is_visible_and_motion_can_be_reduced():
    css = (WEB / "app.css").read_text(encoding="utf-8")

    assert ":focus-visible { outline: 3px solid" in css                   # 2.4.7
    assert "prefers-reduced-motion" in css
    assert "min-height: 44px" in css                                      # 2.5.5 target size
    assert "overflow-x: auto" in css                                      # tables scroll, page reflows


def test_form_fields_have_labels_and_errors_are_announced():
    js = (WEB / "app.js").read_text(encoding="utf-8")

    for field in ("username", "password"):
        assert f'h("label", {{ for: "{field}" }}' in js                   # 1.3.1, 3.3.2
    assert 'autocomplete: "current-password"' in js                       # 1.3.5
    assert 'role: "alert"' in js                                          # 3.3.1
    assert 'scope: "col"' in js and 'scope: "row"' in js and 'h("caption"' in js  # 1.3.1 tables


def test_status_is_not_shown_by_colour_alone():
    js = (WEB / "app.js").read_text(encoding="utf-8")

    assert '"⚠ At risk"' in js and '"✓ On track"' in js                   # 1.4.1


# ---------- security basics ----------

def test_no_inline_code_and_a_content_security_policy():
    html = page()

    assert "Content-Security-Policy" in html
    assert "script-src 'self'" in html and "unsafe-inline" not in html
    assert re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html) is None       # no inline scripts
    assert "<style" not in html and " style=" not in html


def test_server_data_is_never_inserted_as_html():
    js = (WEB / "app.js").read_text(encoding="utf-8")

    assert "innerHTML" not in js and "outerHTML" not in js
    assert "insertAdjacentHTML" not in js and "document.write" not in js
    assert "eval(" not in js


# ---------- course picker API used by the UI ----------

def test_faculty_sees_only_own_courses(app, courses):
    body = login(app, "faculty1").get(f"{API}/dashboard/my-courses").json()

    assert [c["code"] for c in body["courses"]] == ["UE24CS341A", "UE24CS342A"]
    assert set(body["courses"][0]) == {"courseId", "code", "title"}


def test_admin_sees_every_course(app, courses):
    body = login(app, "admin1").get(f"{API}/dashboard/my-courses").json()

    assert [c["code"] for c in body["courses"]] == ["UE24CS341A", "UE24CS342A", "UE24CS343A"]


def test_students_and_anonymous_users_cannot_list_courses(app, client, courses):
    assert login(app, "student1").get(f"{API}/dashboard/my-courses").status_code == 403
    assert client.get(f"{API}/dashboard/my-courses").status_code == 401
