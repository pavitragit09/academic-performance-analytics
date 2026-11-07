"""Tests for the exam results API (APAS-F-013, system test TC-Data-04, validation TC-Data-05)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.app import models
from src.app.database import build_engine, get_db, init_db
from src.app.main import create_app


@pytest.fixture
def engine():
    test_engine = build_engine("sqlite://", poolclass=StaticPool)
    init_db(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def client(engine):
    application = create_app()

    def override_get_db():
        with Session(engine) as session:
            yield session

    application.dependency_overrides[get_db] = override_get_db
    return TestClient(application, raise_server_exceptions=False)


@pytest.fixture
def course_id(engine):
    """One course with three enrolled students, plus one student enrolled elsewhere."""
    with Session(engine) as db:
        faculty = models.Faculty(name="A. Rao", department="CSE")
        db.add(faculty)
        db.flush()
        course = models.Course(code="UE24CS341A", title="SE", semester=5, faculty_id=faculty.id)
        other = models.Course(code="UE24CS342A", title="DBMS", semester=5, faculty_id=faculty.id)
        db.add_all([course, other])
        db.flush()
        students = [
            models.Student(usn=f"PES1UG24AM00{i}", name=f"Student {i}", department="CSE", semester=5)
            for i in range(1, 5)
        ]
        db.add_all(students)
        db.flush()
        for student in students[:3]:
            db.add(models.Enrollment(student_id=student.id, course_id=course.id))
        db.add(models.Enrollment(student_id=students[3].id, course_id=other.id))
        db.commit()
        return course.id


def upload(client, course_id, exam_type="ESA", max_marks=100, results=None):
    body = {
        "examType": exam_type,
        "maxMarks": max_marks,
        "results": results if results is not None else [{"usn": "PES1UG24AM001", "marks": 71}],
    }
    return client.post(f"/api/v1/courses/{course_id}/exams", json=body)


# TC-Data-04: results are stored and visible
def test_upload_saves_results(client, course_id):
    response = upload(
        client,
        course_id,
        results=[{"usn": "PES1UG24AM001", "marks": 71}, {"usn": "PES1UG24AM002", "marks": 55.5}],
    )
    assert response.status_code == 201
    assert response.json() == {"accepted": 2, "rejected": []}


def test_saved_results_and_summary_are_returned(client, course_id):
    upload(
        client,
        course_id,
        results=[
            {"usn": "PES1UG24AM001", "marks": 50},
            {"usn": "PES1UG24AM002", "marks": 80},
            {"usn": "PES1UG24AM003", "marks": 30},
        ],
    )
    response = client.get(f"/api/v1/courses/{course_id}/exams", params={"exam_type": "ESA"})
    body = response.json()
    assert response.status_code == 200
    assert body["examType"] == "ESA"
    assert [r["usn"] for r in body["results"]] == [
        "PES1UG24AM001",
        "PES1UG24AM002",
        "PES1UG24AM003",
    ]
    assert body["results"][0] == {
        "usn": "PES1UG24AM001",
        "name": "Student 1",
        "examType": "ESA",
        "marks": 50.0,
        "maxMarks": 100.0,
    }
    assert body["summary"] == {
        "count": 3,
        "highest": 80.0,
        "lowest": 30.0,
        "average": 53.33,
        "passRate": 66.67,
    }


def test_internal_and_end_semester_are_stored_separately(client, course_id):
    upload(client, course_id, exam_type="ISA", max_marks=50, results=[{"usn": "PES1UG24AM001", "marks": 40}])
    upload(client, course_id, exam_type="ESA", results=[{"usn": "PES1UG24AM001", "marks": 70}])
    isa = client.get(f"/api/v1/courses/{course_id}/exams", params={"exam_type": "ISA"}).json()
    esa = client.get(f"/api/v1/courses/{course_id}/exams", params={"exam_type": "ESA"}).json()
    assert isa["results"][0]["marks"] == 40.0
    assert isa["results"][0]["maxMarks"] == 50.0
    assert esa["results"][0]["marks"] == 70.0


def test_no_results_gives_empty_list_and_no_summary(client, course_id):
    response = client.get(f"/api/v1/courses/{course_id}/exams", params={"exam_type": "ISA"})
    assert response.status_code == 200
    assert response.json() == {"examType": "ISA", "results": [], "summary": None}


# TC-Data-05: invalid and duplicate rows are rejected and reported
def test_marks_above_maximum_rejected_and_other_rows_saved(client, course_id):
    response = upload(
        client,
        course_id,
        results=[{"usn": "PES1UG24AM001", "marks": 101}, {"usn": "PES1UG24AM002", "marks": 60}],
    )
    assert response.status_code == 201
    body = response.json()
    assert body["accepted"] == 1
    assert body["rejected"] == [{"row": 1, "reason": "marks must be between 0 and 100.0"}]


def test_negative_marks_rejected(client, course_id):
    body = upload(client, course_id, results=[{"usn": "PES1UG24AM001", "marks": -1}]).json()
    assert body["accepted"] == 0
    assert body["rejected"][0]["row"] == 1


def test_boundary_marks_are_accepted(client, course_id):
    body = upload(
        client,
        course_id,
        results=[{"usn": "PES1UG24AM001", "marks": 0}, {"usn": "PES1UG24AM002", "marks": 100}],
    ).json()
    assert body == {"accepted": 2, "rejected": []}


def test_unknown_usn_rejected(client, course_id):
    body = upload(client, course_id, results=[{"usn": "NOPE", "marks": 50}]).json()
    assert body["accepted"] == 0
    assert body["rejected"] == [{"row": 1, "reason": "student is not enrolled in this course"}]


def test_student_enrolled_in_another_course_rejected(client, course_id):
    body = upload(client, course_id, results=[{"usn": "PES1UG24AM004", "marks": 50}]).json()
    assert body["accepted"] == 0
    assert body["rejected"][0]["reason"] == "student is not enrolled in this course"


def test_duplicate_within_batch_rejected(client, course_id):
    body = upload(
        client,
        course_id,
        results=[{"usn": "PES1UG24AM001", "marks": 50}, {"usn": "PES1UG24AM001", "marks": 60}],
    ).json()
    assert body["accepted"] == 1
    assert body["rejected"] == [{"row": 2, "reason": "duplicate entry within uploaded batch"}]


def test_duplicate_of_saved_result_rejected_and_original_kept(client, course_id):
    upload(client, course_id, results=[{"usn": "PES1UG24AM001", "marks": 50}])
    body = upload(client, course_id, results=[{"usn": "PES1UG24AM001", "marks": 90}]).json()
    assert body["accepted"] == 0
    assert body["rejected"][0]["reason"] == "a result for this student and exam type already exists"
    saved = client.get(f"/api/v1/courses/{course_id}/exams", params={"exam_type": "ESA"}).json()
    assert saved["results"][0]["marks"] == 50.0


# Request errors use the standard error body (SAD section 4.4)
def test_unknown_course_returns_404(client):
    response = upload(client, 999)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_unknown_course_on_read_returns_404(client):
    response = client.get("/api/v1/courses/999/exams", params={"exam_type": "ESA"})
    assert response.status_code == 404


@pytest.mark.parametrize(
    "body",
    [
        {"examType": "QUIZ", "maxMarks": 100, "results": [{"usn": "PES1UG24AM001", "marks": 50}]},
        {"examType": "ESA", "maxMarks": 0, "results": [{"usn": "PES1UG24AM001", "marks": 50}]},
        {"examType": "ESA", "maxMarks": 100, "results": []},
        {"examType": "ESA", "maxMarks": 100},
    ],
)
def test_malformed_request_returns_422(client, course_id, body):
    response = client.post(f"/api/v1/courses/{course_id}/exams", json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_invalid_exam_type_on_read_returns_422(client, course_id):
    response = client.get(f"/api/v1/courses/{course_id}/exams", params={"exam_type": "QUIZ"})
    assert response.status_code == 422


# SR-005: every saved result writes an audit entry
def test_each_saved_result_writes_an_audit_entry(client, engine, course_id):
    upload(
        client,
        course_id,
        results=[{"usn": "PES1UG24AM001", "marks": 50}, {"usn": "PES1UG24AM002", "marks": 101}],
    )
    with Session(engine) as db:
        entries = db.scalars(select(models.AuditLogEntry)).all()
    assert len(entries) == 1
    assert entries[0].action == "CREATE"
    assert entries[0].entity.startswith("exam_result:")
    assert "PES1UG24AM001" in entries[0].new_value