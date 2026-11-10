"""Tests for assignment records (APAS-F-012, TC-Data-03)."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
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


def add_user(db, username, role):
    user = models.User(
        username=username, password_hash=hash_password(PASSWORD), role=role, is_active=True
    )
    db.add(user)
    db.flush()
    return user


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


@pytest.fixture
def course_id(engine):
    """A course taught by faculty1, with Asha and Bala enrolled and Chitra not enrolled."""
    with Session(engine) as db:
        teacher = add_user(db, "faculty1", models.Role.FACULTY)
        other = add_user(db, "faculty2", models.Role.FACULTY)
        add_user(db, "student1", models.Role.STUDENT)
        faculty = models.Faculty(user_id=teacher.id, name="A. Rao", department="CSE")
        db.add_all([faculty, models.Faculty(user_id=other.id, name="B. Rao", department="CSE")])
        db.flush()
        course = models.Course(code="UE24CS341A", title="SE", semester=5, faculty_id=faculty.id)
        db.add(course)
        for usn, name in [("PES001", "Asha"), ("PES002", "Bala"), ("PES003", "Chitra")]:
            db.add(models.Student(usn=usn, name=name, department="CSE", semester=5))
        db.flush()
        for student in db.scalars(select(models.Student).where(models.Student.usn != "PES003")):
            db.add(models.Enrollment(student_id=student.id, course_id=course.id))
        db.commit()
        return course.id


@pytest.fixture
def client(app, course_id):
    return login(app, "faculty1")


@pytest.fixture
def assignment(client, course_id):
    response = client.post(
        f"{API}/courses/{course_id}/assignments",
        json={"title": "Lab 1", "due_date": "2026-11-10", "max_score": 10},
    )
    assert response.status_code == 201
    return response.json()


def put_submissions(client, assignment_id, submissions):
    return client.put(
        f"{API}/assignments/{assignment_id}/submissions", json={"submissions": submissions}
    )


def test_create_and_list_assignments(client, course_id, assignment):
    assert assignment["course_id"] == course_id
    assert assignment["title"] == "Lab 1"
    assert client.get(f"{API}/courses/{course_id}/assignments").json() == [assignment]


def test_assignments_are_listed_by_due_date(client, course_id, assignment):
    client.post(
        f"{API}/courses/{course_id}/assignments",
        json={"title": "Lab 0", "due_date": "2026-11-01", "max_score": 5},
    )

    titles = [a["title"] for a in client.get(f"{API}/courses/{course_id}/assignments").json()]

    assert titles == ["Lab 0", "Lab 1"]


@pytest.mark.parametrize(
    "change", [{"title": "  "}, {"max_score": 0}, {"due_date": "not-a-date"}]
)
def test_invalid_assignment_is_rejected(client, course_id, change):
    body = {"title": "Lab 1", "due_date": "2026-11-10", "max_score": 10, **change}

    response = client.post(f"{API}/courses/{course_id}/assignments", json=body)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unknown_course_or_assignment_returns_not_found(client, assignment):
    body = {"title": "Lab", "due_date": "2026-11-10", "max_score": 10}
    assert client.post(f"{API}/courses/999/assignments", json=body).status_code == 404
    assert client.get(f"{API}/courses/999/assignments").status_code == 404
    assert client.get(f"{API}/assignments/999/submissions").status_code == 404
    assert client.get(f"{API}/courses/999/assignment-completion").status_code == 404
    response = put_submissions(client, 999, [{"usn": "PES001", "status": "submitted"}])
    assert response.status_code == 404


def test_status_and_score_are_stored_per_student(client, assignment):
    response = put_submissions(
        client,
        assignment["id"],
        [
            {"usn": "PES001", "status": "submitted", "score": 9},
            {"usn": "PES002", "status": "missing"},
        ],
    )

    assert response.status_code == 200
    assert response.json() == {"updated": 2}
    assert client.get(f"{API}/assignments/{assignment['id']}/submissions").json() == [
        {"usn": "PES001", "name": "Asha", "status": "submitted", "score": 9.0},
        {"usn": "PES002", "name": "Bala", "status": "missing", "score": None},
    ]


def test_recording_again_updates_instead_of_duplicating(client, engine, assignment):
    put_submissions(client, assignment["id"], [{"usn": "PES001", "status": "missing"}])

    put_submissions(client, assignment["id"], [{"usn": "PES001", "status": "late", "score": 6}])

    rows = client.get(f"{API}/assignments/{assignment['id']}/submissions").json()
    assert rows == [{"usn": "PES001", "name": "Asha", "status": "late", "score": 6.0}]
    with Session(engine) as db:
        assert len(db.scalars(select(models.AssignmentSubmission)).all()) == 1


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        ({"usn": "PES003", "status": "submitted"}, "not enrolled"),
        ({"usn": "NOPE", "status": "submitted"}, "not enrolled"),
        ({"usn": "PES001", "status": "submitted", "score": 11}, "between 0 and 10"),
        ({"usn": "PES001", "status": "late", "score": -1}, "between 0 and 10"),
        ({"usn": "PES001", "status": "missing", "score": 5}, "cannot have a score"),
    ],
)
def test_invalid_submission_is_rejected_with_reason(client, assignment, row, reason):
    response = put_submissions(client, assignment["id"], [row])

    error = response.json()["error"]
    assert response.status_code == 422
    assert error["code"] == "VALIDATION_ERROR"
    assert reason in error["details"][0]["reason"]
    assert error["details"][0]["row"] == 1


def test_unknown_status_is_rejected(client, assignment):
    response = put_submissions(client, assignment["id"], [{"usn": "PES001", "status": "done"}])

    assert response.status_code == 422


def test_empty_submission_list_is_rejected(client, assignment):
    assert put_submissions(client, assignment["id"], []).status_code == 422


def test_one_bad_row_saves_nothing(client, assignment):
    response = put_submissions(
        client,
        assignment["id"],
        [
            {"usn": "PES001", "status": "submitted", "score": 9},
            {"usn": "PES001", "status": "late", "score": 5},
        ],
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"] == [
        {"row": 2, "usn": "PES001", "reason": "PES001 appears more than once"}
    ]
    assert client.get(f"{API}/assignments/{assignment['id']}/submissions").json() == []


def test_course_completion_uses_on_time_submissions(client, course_id, assignment):
    second = client.post(
        f"{API}/courses/{course_id}/assignments",
        json={"title": "Lab 2", "due_date": "2026-11-12", "max_score": 10},
    ).json()
    put_submissions(client, assignment["id"], [{"usn": "PES001", "status": "submitted"}])
    put_submissions(client, second["id"], [{"usn": "PES001", "status": "late", "score": 4}])

    response = client.get(f"{API}/courses/{course_id}/assignment-completion")

    assert response.status_code == 200
    assert response.json() == [
        {"usn": "PES001", "name": "Asha", "submitted": 1, "late": 1, "missing": 0,
         "completion_pct": 50.0},
        {"usn": "PES002", "name": "Bala", "submitted": 0, "late": 0, "missing": 0,
         "completion_pct": None},
    ]
    lenient = client.get(
        f"{API}/courses/{course_id}/assignment-completion", params={"include_late": True}
    ).json()
    assert lenient[0]["completion_pct"] == 100.0


def test_stored_status_uses_the_database_enum(client, engine, assignment):
    put_submissions(client, assignment["id"], [{"usn": "PES002", "status": "late", "score": 3}])

    with Session(engine) as db:
        submission = db.scalar(select(models.AssignmentSubmission))
        assert submission.status is models.SubmissionStatus.LATE
        assert submission.score == 3
        assert db.get(models.Assignment, assignment["id"]).due_date == date(2026, 11, 10)


def test_login_is_required(app, course_id):
    anonymous = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)

    response = anonymous.get(f"{API}/courses/{course_id}/assignments")

    assert response.status_code == 401


def test_students_cannot_use_assignment_records(app, course_id, assignment):
    student = login(app, "student1")

    assert student.get(f"{API}/courses/{course_id}/assignments").status_code == 403
    response = put_submissions(student, assignment["id"], [{"usn": "PES001", "status": "late"}])
    assert response.status_code == 403


def test_other_faculty_cannot_see_or_change_this_course(app, course_id, assignment):
    other = login(app, "faculty2")

    assert other.get(f"{API}/courses/{course_id}/assignments").status_code == 403
    assert other.get(f"{API}/assignments/{assignment['id']}/submissions").status_code == 403
    assert other.get(f"{API}/courses/{course_id}/assignment-completion").status_code == 403
    response = put_submissions(other, assignment["id"], [{"usn": "PES001", "status": "late"}])
    assert response.status_code == 403
