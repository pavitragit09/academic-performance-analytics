"""Tests for at-risk checks, flags and alert e-mails (APAS-F-040, system test TC-Int-01)."""

import smtplib
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.app import models
from src.app.config import get_mail_from, get_smtp_host, get_smtp_port
from src.app.database import build_engine, get_db, init_db
from src.app.main import create_app
from src.app.notifications import RiskAlert, build_alert_email, get_email_sender, send_email
from src.app.security import hash_password

FACULTY_EMAIL = "arao@pes.edu"


@pytest.fixture
def engine():
    test_engine = build_engine("sqlite://", poolclass=StaticPool)
    init_db(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def faculty_user(engine):
    with Session(engine, expire_on_commit=False) as db:
        user = models.User(
            username="faculty1",
            password_hash=hash_password("FacultyPass123!"),
            role=models.Role.FACULTY,
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(models.Faculty(user_id=user.id, name="A. Rao", department="CSE", email=FACULTY_EMAIL))
        db.commit()
        return user.id


@pytest.fixture
def sent():
    """Every e-mail the app tried to send during a test."""
    return []


@pytest.fixture
def app(engine, sent):
    application = create_app()

    def override_get_db():
        with Session(engine, expire_on_commit=False) as session:
            yield session

    def fake_sender(to, subject, body):
        sent.append({"to": to, "subject": subject, "body": body})
        return True

    application.dependency_overrides[get_db] = override_get_db
    application.dependency_overrides[get_email_sender] = lambda: fake_sender
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(app, faculty_user):
    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as test_client:
        response = test_client.post(
            "/api/v1/auth/login", json={"username": "faculty1", "password": "FacultyPass123!"}
        )
        assert response.status_code == 200
        yield test_client


@pytest.fixture
def course(engine, faculty_user):
    """A course taught by the logged-in faculty with two enrolled students (S1 and S2)."""
    with Session(engine) as db:
        faculty = db.scalar(select(models.Faculty).where(models.Faculty.user_id == faculty_user))
        course = models.Course(code="UE24CS341A", title="SE", semester=5, faculty_id=faculty.id)
        db.add(course)
        db.flush()
        enrollments = {}
        for usn, name in [("PES1UG24AM001", "Asha"), ("PES1UG24AM002", "Ravi")]:
            student = models.Student(usn=usn, name=name, department="CSE", semester=5)
            db.add(student)
            db.flush()
            enrollment = models.Enrollment(student_id=student.id, course_id=course.id)
            db.add(enrollment)
            db.flush()
            enrollments[usn] = enrollment.id
        db.commit()
        return {"id": course.id, "enrollments": enrollments}


def add_attendance(engine, enrollment_id, present, absent, start_day=1):
    """Record `present` present days then `absent` absent days from start_day."""
    with Session(engine) as db:
        for offset in range(present + absent):
            db.add(
                models.AttendanceRecord(
                    enrollment_id=enrollment_id,
                    session_date=date(2026, 8, 1) + timedelta(days=start_day + offset),
                    present=offset < present,
                )
            )
        db.commit()


def add_marks(engine, course_id, enrollment_id, percentages, max_marks=50):
    """Record one assessment per value, oldest first, scored as the given percentages."""
    with Session(engine) as db:
        for index, percent in enumerate(percentages):
            assessment = models.Assessment(
                course_id=course_id,
                name=f"Quiz {index + 1}",
                max_marks=max_marks,
                held_on=date(2026, 9, 1 + index),
            )
            db.add(assessment)
            db.flush()
            db.add(
                models.MarkEntry(
                    assessment_id=assessment.id,
                    enrollment_id=enrollment_id,
                    marks=percent / 100 * max_marks,
                )
            )
        db.commit()


def risk_check(client, course_id):
    return client.post(f"/api/v1/courses/{course_id}/risk-check")


S1 = "PES1UG24AM001"
S2 = "PES1UG24AM002"


# TC-Int-01: a newly flagged student triggers an alert to the course's faculty
def test_low_attendance_student_is_flagged_and_faculty_emailed(client, engine, course, sent):
    add_attendance(engine, course["enrollments"][S1], present=6, absent=4)  # 60%
    response = risk_check(client, course["id"])
    assert response.status_code == 200
    assert response.json() == {"checked": 2, "newlyFlagged": [S1]}
    assert len(sent) == 1
    assert sent[0]["to"] == FACULTY_EMAIL
    assert S1 in sent[0]["subject"]
    assert "low attendance" in sent[0]["body"]


def test_flag_is_saved_with_reasons(client, engine, course):
    add_attendance(engine, course["enrollments"][S1], present=6, absent=4)
    risk_check(client, course["id"])
    with Session(engine) as db:
        flags = db.scalars(select(models.RiskFlag)).all()
    assert len(flags) == 1
    assert flags[0].active is True
    assert flags[0].reasons == ["low attendance"]


def test_healthy_student_is_not_flagged(client, engine, course, sent):
    add_attendance(engine, course["enrollments"][S1], present=9, absent=1)
    add_marks(engine, course["id"], course["enrollments"][S1], [70, 75, 80])
    response = risk_check(client, course["id"])
    assert response.json() == {"checked": 2, "newlyFlagged": []}
    assert sent == []


def test_student_with_no_data_is_not_flagged(client, course, sent):
    assert risk_check(client, course["id"]).json() == {"checked": 2, "newlyFlagged": []}
    assert sent == []


def test_declining_marks_trend_is_flagged(client, engine, course, sent):
    add_marks(engine, course["id"], course["enrollments"][S1], [80, 70, 60])
    assert risk_check(client, course["id"]).json()["newlyFlagged"] == [S1]
    assert "declining marks trend" in sent[0]["body"]


def test_low_average_marks_is_flagged(client, engine, course, sent):
    add_marks(engine, course["id"], course["enrollments"][S1], [30, 35, 38])
    assert risk_check(client, course["id"]).json()["newlyFlagged"] == [S1]
    assert "low average marks" in sent[0]["body"]


def test_all_reasons_are_listed(client, engine, course, sent):
    add_attendance(engine, course["enrollments"][S1], present=5, absent=5)
    add_marks(engine, course["id"], course["enrollments"][S1], [40, 30, 20])
    risk_check(client, course["id"])
    body = sent[0]["body"]
    assert "low attendance" in body
    assert "low average marks" in body
    assert "declining marks trend" in body


def test_each_newly_flagged_student_gets_an_email(client, engine, course, sent):
    add_attendance(engine, course["enrollments"][S1], present=5, absent=5)
    add_attendance(engine, course["enrollments"][S2], present=5, absent=5)
    assert risk_check(client, course["id"]).json()["newlyFlagged"] == [S1, S2]
    assert len(sent) == 2


def test_student_who_stays_at_risk_is_not_alerted_again(client, engine, course, sent):
    add_attendance(engine, course["enrollments"][S1], present=6, absent=4)
    risk_check(client, course["id"])
    second = risk_check(client, course["id"])
    assert second.json() == {"checked": 2, "newlyFlagged": []}
    assert len(sent) == 1


def test_reasons_are_updated_without_a_new_alert(client, engine, course, sent):
    add_attendance(engine, course["enrollments"][S1], present=6, absent=4)
    risk_check(client, course["id"])
    add_marks(engine, course["id"], course["enrollments"][S1], [30, 35, 38])
    assert risk_check(client, course["id"]).json()["newlyFlagged"] == []
    assert len(sent) == 1
    flags = client.get(f"/api/v1/courses/{course['id']}/at-risk").json()
    assert flags[0]["reasons"] == ["low attendance", "low average marks"]


def test_recovered_then_flagged_again_alerts_again(client, engine, course, sent):
    enrollment_id = course["enrollments"][S1]
    add_attendance(engine, enrollment_id, present=6, absent=4)  # 60%: flagged
    risk_check(client, course["id"])
    add_attendance(engine, enrollment_id, present=30, absent=0, start_day=11)  # 36/40 = 90%: recovered
    risk_check(client, course["id"])
    assert client.get(f"/api/v1/courses/{course['id']}/at-risk").json() == []
    add_attendance(engine, enrollment_id, present=0, absent=30, start_day=41)  # 36/70 = 51%: flagged again
    assert risk_check(client, course["id"]).json()["newlyFlagged"] == [S1]
    assert len(sent) == 2


def test_faculty_without_email_still_flags_without_error(client, engine, course, faculty_user, sent):
    with Session(engine) as db:
        faculty = db.scalar(select(models.Faculty).where(models.Faculty.user_id == faculty_user))
        faculty.email = None
        db.commit()
    add_attendance(engine, course["enrollments"][S1], present=6, absent=4)
    response = risk_check(client, course["id"])
    assert response.status_code == 200
    assert response.json()["newlyFlagged"] == [S1]
    assert sent == []


# The at-risk list for the dashboard
def test_at_risk_list_shows_flagged_students_with_reasons(client, engine, course):
    add_attendance(engine, course["enrollments"][S1], present=6, absent=4)
    risk_check(client, course["id"])
    response = client.get(f"/api/v1/courses/{course['id']}/at-risk")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["usn"] == S1
    assert body[0]["name"] == "Asha"
    assert body[0]["reasons"] == ["low attendance"]
    assert "flaggedAt" in body[0]


def test_at_risk_list_is_empty_before_any_check(client, course):
    assert client.get(f"/api/v1/courses/{course['id']}/at-risk").json() == []


# Access control (APAS-F-002, SR-003)
def test_risk_check_requires_login(app, course):
    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as anonymous:
        assert anonymous.post(f"/api/v1/courses/{course['id']}/risk-check").status_code == 401
        assert anonymous.get(f"/api/v1/courses/{course['id']}/at-risk").status_code == 401


def test_faculty_cannot_check_another_facultys_course(client, engine):
    with Session(engine) as db:
        other = models.Faculty(name="B. Nair", department="CSE", email="bnair@pes.edu")
        db.add(other)
        db.flush()
        course = models.Course(code="UE24CS999Z", title="Other", semester=5, faculty_id=other.id)
        db.add(course)
        db.commit()
        other_course_id = course.id
    assert risk_check(client, other_course_id).status_code == 403
    assert client.get(f"/api/v1/courses/{other_course_id}/at-risk").status_code == 403


def test_unknown_course_returns_404(client):
    assert risk_check(client, 999).status_code == 404


# Notification service
def make_alert(**overrides):
    values = dict(
        faculty_email=FACULTY_EMAIL,
        faculty_name="A. Rao",
        usn=S1,
        student_name="Asha",
        course_code="UE24CS341A",
        reasons=["low attendance", "declining marks trend"],
    )
    values.update(overrides)
    return RiskAlert(**values)


def test_alert_email_names_student_course_and_reasons():
    subject, body = build_alert_email(make_alert())
    assert S1 in subject
    assert "UE24CS341A" in subject
    assert "Dear A. Rao" in body
    assert "Asha" in body
    assert "- low attendance" in body
    assert "- declining marks trend" in body


class FakeSMTP:
    """Stands in for smtplib.SMTP and records what it was asked to send."""

    instances = []
    failures_before_success = 0

    def __init__(self, host, port, timeout=None):
        FakeSMTP.instances.append(self)
        self.host, self.port, self.messages = host, port, []
        self.should_fail = len(FakeSMTP.instances) <= FakeSMTP.failures_before_success

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def send_message(self, message):
        if self.should_fail:
            raise smtplib.SMTPException("server unavailable")
        self.messages.append(message)


@pytest.fixture(autouse=False)
def fake_smtp():
    FakeSMTP.instances = []
    FakeSMTP.failures_before_success = 0
    return FakeSMTP


def test_send_email_delivers_message_to_the_mail_server(fake_smtp):
    ok = send_email(
        "arao@pes.edu", "Subject", "Body", host="mail.test", port=2525, sender="apas@pes.edu", smtp_factory=fake_smtp
    )
    assert ok is True
    server = fake_smtp.instances[0]
    assert (server.host, server.port) == ("mail.test", 2525)
    message = server.messages[0]
    assert message["To"] == "arao@pes.edu"
    assert message["From"] == "apas@pes.edu"
    assert message["Subject"] == "Subject"
    assert "Body" in message.get_content()


def test_send_email_retries_then_succeeds(fake_smtp):
    fake_smtp.failures_before_success = 2
    ok = send_email("a@b.c", "S", "B", retry_delay=0, smtp_factory=fake_smtp)
    assert ok is True
    assert len(fake_smtp.instances) == 3


def test_send_email_gives_up_after_all_retries_without_raising(fake_smtp):
    fake_smtp.failures_before_success = 99
    ok = send_email("a@b.c", "S", "B", retries=3, retry_delay=0, smtp_factory=fake_smtp)
    assert ok is False
    assert len(fake_smtp.instances) == 3


def test_send_email_survives_unreachable_server():
    def unreachable(host, port, timeout=None):
        raise ConnectionRefusedError("no server")

    assert send_email("a@b.c", "S", "B", retries=2, retry_delay=0, smtp_factory=unreachable) is False


def test_default_sender_is_send_email():
    assert get_email_sender() is send_email


def test_mail_settings_default_to_mailhog(monkeypatch):
    for name in ("APAS_SMTP_HOST", "APAS_SMTP_PORT", "APAS_MAIL_FROM"):
        monkeypatch.delenv(name, raising=False)
    assert (get_smtp_host(), get_smtp_port(), get_mail_from()) == ("localhost", 1025, "apas@localhost")


def test_mail_settings_can_be_overridden(monkeypatch):
    monkeypatch.setenv("APAS_SMTP_HOST", "smtp.pes.edu")
    monkeypatch.setenv("APAS_SMTP_PORT", "587")
    monkeypatch.setenv("APAS_MAIL_FROM", "alerts@pes.edu")
    assert (get_smtp_host(), get_smtp_port(), get_mail_from()) == ("smtp.pes.edu", 587, "alerts@pes.edu")