"""Tests for the faculty course dashboard (APAS-F-031, F-023, F-024, TC-Dash-02)."""

from datetime import date

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


def login(app, username):
    client = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
    response = client.post(f"{API}/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200
    return client


def add_user(db, username, role):
    user = models.User(
        username=username, password_hash=hash_password(PASSWORD), role=role, is_active=True
    )
    db.add(user)
    db.flush()
    return user


def enroll(db, course, usn, name):
    student = models.Student(usn=usn, name=name, department="CSE", semester=5)
    db.add(student)
    db.flush()
    enrollment = models.Enrollment(student_id=student.id, course_id=course.id)
    db.add(enrollment)
    db.flush()
    return enrollment


@pytest.fixture
def course_id(engine):
    """Asha is doing well; Ravi has low attendance, low and falling marks; Meera has no data."""
    with Session(engine) as db:
        teacher = add_user(db, "faculty1", models.Role.FACULTY)
        other = add_user(db, "faculty2", models.Role.FACULTY)
        add_user(db, "admin1", models.Role.ADMIN)
        add_user(db, "student1", models.Role.STUDENT)
        faculty = models.Faculty(user_id=teacher.id, name="A. Rao", department="CSE")
        db.add_all([faculty, models.Faculty(user_id=other.id, name="B. Rao", department="CSE")])
        db.flush()
        course = models.Course(code="UE24CS341A", title="SE", semester=5, faculty_id=faculty.id)
        db.add(course)
        db.flush()
        asha = enroll(db, course, "PES001", "Asha")
        ravi = enroll(db, course, "PES002", "Ravi")
        enroll(db, course, "PES003", "Meera")

        tests = []
        for day in (1, 8, 15):
            test = models.Assessment(
                course_id=course.id, name=f"Quiz {day}", max_marks=20, held_on=date(2026, 10, day)
            )
            db.add(test)
            tests.append(test)
        db.flush()
        for test, asha_marks, ravi_marks in zip(tests, [16, 18, 17], [9, 7, 5]):
            db.add(models.MarkEntry(assessment_id=test.id, enrollment_id=asha.id, marks=asha_marks))
            db.add(models.MarkEntry(assessment_id=test.id, enrollment_id=ravi.id, marks=ravi_marks))

        for day in range(1, 11):
            session_date = date(2026, 10, day)
            db.add(models.AttendanceRecord(
                enrollment_id=asha.id, session_date=session_date, present=day != 10
            ))
            db.add(models.AttendanceRecord(
                enrollment_id=ravi.id, session_date=session_date, present=day <= 6
            ))

        db.add(models.ExamResult(enrollment_id=asha.id, exam_type="ISA1", marks=36, max_marks=40))
        db.add(models.ExamResult(enrollment_id=ravi.id, exam_type="ISA1", marks=12, max_marks=40))

        lab = models.Assignment(
            course_id=course.id, title="Lab 1", due_date=date(2026, 10, 20), max_score=10
        )
        db.add(lab)
        db.flush()
        db.add(models.AssignmentSubmission(
            assignment_id=lab.id, enrollment_id=asha.id,
            status=models.SubmissionStatus.SUBMITTED, score=9,
        ))
        db.add(models.AssignmentSubmission(
            assignment_id=lab.id, enrollment_id=ravi.id, status=models.SubmissionStatus.MISSING,
        ))
        db.commit()
        return course.id


def get_dashboard(client, course_id, **params):
    return client.get(f"{API}/dashboard/courses/{course_id}", params=params)


def test_dashboard_summarises_the_course(app, course_id):
    response = get_dashboard(login(app, "faculty1"), course_id)
    body = response.json()

    assert response.status_code == 200
    assert body["courseCode"] == "UE24CS341A"
    assert body["enrolled"] == 3
    assert body["classAverage"] == 60.0
    assert body["marksDistribution"] == {"0-39": 1, "40-59": 0, "60-74": 0, "75-100": 1}
    assert body["exams"] == [
        {"examType": "ISA1", "count": 2, "highest": 90.0, "lowest": 30.0,
         "average": 60.0, "pass_rate": 50.0}
    ]


def test_at_risk_list_matches_the_flagging_rules(app, course_id):
    body = get_dashboard(login(app, "faculty1"), course_id).json()

    assert body["atRisk"] == [
        {
            "usn": "PES002",
            "name": "Ravi",
            "reasons": ["low attendance", "low average marks", "declining marks trend"],
        }
    ]
    assert body["lowCompletion"] == ["PES002"]


def test_each_student_row(app, course_id):
    rows = {s["usn"]: s for s in get_dashboard(login(app, "faculty1"), course_id).json()["students"]}

    assert rows["PES001"] == {
        "usn": "PES001", "name": "Asha", "attendancePct": 90.0, "averageMarks": 85.0,
        "declining": False, "assignmentCompletionPct": 100.0, "atRisk": False,
    }
    assert rows["PES002"]["declining"] is True
    assert rows["PES002"]["assignmentCompletionPct"] == 0.0
    assert rows["PES003"] == {
        "usn": "PES003", "name": "Meera", "attendancePct": None, "averageMarks": None,
        "declining": False, "assignmentCompletionPct": None, "atRisk": False,
    }


def test_thresholds_change_who_is_at_risk(app, course_id):
    body = get_dashboard(
        login(app, "faculty1"), course_id, attendanceThreshold=95, marksThreshold=10, window=4
    ).json()

    assert body["atRisk"] == [
        {"usn": "PES001", "name": "Asha", "reasons": ["low attendance"]},
        {"usn": "PES002", "name": "Ravi", "reasons": ["low attendance"]},
    ]


@pytest.mark.parametrize(
    "params",
    [{"attendanceThreshold": 101}, {"marksThreshold": -1}, {"window": 1}],
)
def test_invalid_thresholds_are_rejected(app, course_id, params):
    response = get_dashboard(login(app, "faculty1"), course_id, **params)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_empty_course_has_no_averages(app, engine, course_id):
    with Session(engine) as db:
        faculty = db.query(models.Faculty).filter_by(name="A. Rao").one()
        empty = models.Course(code="UE24CS342A", title="Empty", semester=5, faculty_id=faculty.id)
        db.add(empty)
        db.commit()
        empty_id = empty.id

    body = get_dashboard(login(app, "faculty1"), empty_id).json()

    assert body["enrolled"] == 0
    assert body["classAverage"] is None
    assert body["exams"] == []
    assert body["atRisk"] == []
    assert body["students"] == []


def test_admin_can_see_any_course(app, course_id):
    assert get_dashboard(login(app, "admin1"), course_id).status_code == 200
    assert get_dashboard(login(app, "admin1"), 999).status_code == 404


def test_other_faculty_and_students_are_forbidden(app, course_id):
    assert get_dashboard(login(app, "faculty2"), course_id).status_code == 403
    assert get_dashboard(login(app, "student1"), course_id).status_code == 403


def test_login_is_required(app, course_id):
    anonymous = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)

    assert get_dashboard(anonymous, course_id).status_code == 401


def test_unknown_course_returns_not_found(app, course_id):
    assert get_dashboard(login(app, "faculty1"), 999).status_code == 404
