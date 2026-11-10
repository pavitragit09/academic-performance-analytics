"""Tests for course and student records management (APAS-F-015, TC-Data-06)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.app import models
from src.app.database import build_engine, get_db, init_db
from src.app.errors import AppError
from src.app.main import create_app
from src.app.records import check_student_enrolled, is_student_enrolled
from src.app.security import hash_password

API = "/api/v1"
PASSWORD = "TestPassword123!"


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


def create_user_and_login(app, db, username, role, faculty_profile=False):
    user = models.User(
        username=username,
        password_hash=hash_password(PASSWORD),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()

    fac_id = None
    if faculty_profile:
        fac = models.Faculty(
            user_id=user.id,
            name=f"Prof. {username}",
            department="CSE",
            email=f"{username}@college.edu",
        )
        db.add(fac)
        db.flush()
        fac_id = fac.id

    db.commit()

    client = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
    resp = client.post(f"{API}/auth/login", json={"username": username, "password": PASSWORD})
    assert resp.status_code == 200
    return client, user.id, fac_id


def test_admin_create_and_list_courses(app, engine):
    with Session(engine) as db:
        admin_client, _, _ = create_user_and_login(app, db, "admin_user", models.Role.ADMIN)
        _, _, faculty_id = create_user_and_login(app, db, "prof_rao", models.Role.FACULTY, faculty_profile=True)

    # Admin creates course
    resp = admin_client.post(
        f"{API}/courses",
        json={
            "code": "CS101",
            "title": "Intro to Programming",
            "semester": 1,
            "facultyId": faculty_id,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["code"] == "CS101"
    assert data["title"] == "Intro to Programming"
    assert data["facultyId"] == faculty_id
    course_id = data["id"]

    # Duplicate course code is rejected
    resp_dup = admin_client.post(
        f"{API}/courses",
        json={
            "code": "CS101",
            "title": "Duplicate",
            "semester": 1,
            "facultyId": faculty_id,
        },
    )
    assert resp_dup.status_code == 409

    # Admin lists courses
    resp_list = admin_client.get(f"{API}/courses")
    assert resp_list.status_code == 200
    courses = resp_list.json()
    assert any(c["id"] == course_id and c["code"] == "CS101" for c in courses)


def test_admin_assign_faculty(app, engine):
    with Session(engine) as db:
        admin_client, _, _ = create_user_and_login(app, db, "admin_fac", models.Role.ADMIN)
        _, _, fac1_id = create_user_and_login(app, db, "prof1", models.Role.FACULTY, faculty_profile=True)
        _, _, fac2_id = create_user_and_login(app, db, "prof2", models.Role.FACULTY, faculty_profile=True)

    resp = admin_client.post(
        f"{API}/courses",
        json={
            "code": "CS102",
            "title": "Data Structures",
            "semester": 2,
            "facultyId": fac1_id,
        },
    )
    assert resp.status_code == 201
    course_id = resp.json()["id"]

    # Reassign to fac2
    resp_reassign = admin_client.put(
        f"{API}/courses/{course_id}/faculty",
        json={"facultyId": fac2_id},
    )
    assert resp_reassign.status_code == 200
    assert resp_reassign.json()["facultyId"] == fac2_id


def test_admin_create_and_list_students(app, engine):
    with Session(engine) as db:
        admin_client, _, _ = create_user_and_login(app, db, "admin_stu", models.Role.ADMIN)

    # Create student
    resp = admin_client.post(
        f"{API}/students",
        json={
            "usn": "PES1UG24AM001",
            "name": "Asha Rao",
            "department": "CSE",
            "semester": 5,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["usn"] == "PES1UG24AM001"
    assert data["name"] == "Asha Rao"

    # Duplicate USN rejected
    resp_dup = admin_client.post(
        f"{API}/students",
        json={
            "usn": "PES1UG24AM001",
            "name": "Asha Clone",
            "department": "CSE",
            "semester": 5,
        },
    )
    assert resp_dup.status_code == 409

    # List students
    resp_list = admin_client.get(f"{API}/students")
    assert resp_list.status_code == 200
    students = resp_list.json()
    assert any(s["usn"] == "PES1UG24AM001" for s in students)


def test_admin_enrollment_and_listing(app, engine):
    with Session(engine) as db:
        admin_client, _, _ = create_user_and_login(app, db, "admin_enr", models.Role.ADMIN)
        _, _, fac_id = create_user_and_login(app, db, "prof_enr", models.Role.FACULTY, faculty_profile=True)

    # Create course & student
    c_resp = admin_client.post(
        f"{API}/courses",
        json={"code": "CS201", "title": "Algorithms", "semester": 3, "facultyId": fac_id},
    )
    course_id = c_resp.json()["id"]

    s_resp = admin_client.post(
        f"{API}/students",
        json={"usn": "PES1UG24AM010", "name": "Rahul", "department": "CSE", "semester": 3},
    )
    assert s_resp.status_code == 201

    # Enrol student
    resp_enr = admin_client.post(
        f"{API}/courses/{course_id}/enrollments",
        json={"usn": "PES1UG24AM010"},
    )
    assert resp_enr.status_code == 201

    # Duplicate enrolment rejected
    resp_enr_dup = admin_client.post(
        f"{API}/courses/{course_id}/enrollments",
        json={"usn": "PES1UG24AM010"},
    )
    assert resp_enr_dup.status_code == 409

    # List enrolments
    resp_enr_list = admin_client.get(f"{API}/courses/{course_id}/enrollments")
    assert resp_enr_list.status_code == 200
    enrolled = resp_enr_list.json()
    assert len(enrolled) == 1
    assert enrolled[0]["usn"] == "PES1UG24AM010"
    assert enrolled[0]["name"] == "Rahul"


def test_csv_import_students(app, engine):
    with Session(engine) as db:
        admin_client, _, _ = create_user_and_login(app, db, "admin_csv_stu", models.Role.ADMIN)

    csv_data = (
        "usn,name,department,semester\n"
        "PES1UG24AM101,Alice,CSE,5\n"
        "PES1UG24AM102,Bob,ECE,5\n"
        "PES1UG24AM101,AliceDuplicate,CSE,5\n"  # duplicate in file
        "PES1UG24AM103,Charlie,CSE,invalid\n"   # invalid semester
        ",EmptyUSN,CSE,5\n"                      # missing USN
    )

    resp = admin_client.post(
        f"{API}/students/upload",
        content=csv_data,
        headers={"Content-Type": "text/csv"},
    )
    assert resp.status_code == 201
    res = resp.json()
    assert res["accepted"] == 2
    assert len(res["rejected"]) == 3
    assert any("Duplicate USN" in r["reason"] for r in res["rejected"])
    assert any("Invalid semester" in r["reason"] for r in res["rejected"])


def test_csv_import_enrollments(app, engine):
    with Session(engine) as db:
        admin_client, _, _ = create_user_and_login(app, db, "admin_csv_enr", models.Role.ADMIN)
        _, _, fac_id = create_user_and_login(app, db, "prof_csv", models.Role.FACULTY, faculty_profile=True)

    c_resp = admin_client.post(
        f"{API}/courses",
        json={"code": "CS301", "title": "OS", "semester": 5, "facultyId": fac_id},
    )
    course_id = c_resp.json()["id"]

    # Pre-create 2 students
    admin_client.post(f"{API}/students", json={"usn": "PES1UG24AM201", "name": "Dave", "department": "CSE", "semester": 5})
    admin_client.post(f"{API}/students", json={"usn": "PES1UG24AM202", "name": "Eve", "department": "CSE", "semester": 5})

    csv_data = (
        "usn\n"
        "PES1UG24AM201\n"
        "PES1UG24AM202\n"
        "PES1UG24AM999\n"  # unknown student
        "PES1UG24AM201\n"  # duplicate in file
    )

    resp = admin_client.post(
        f"{API}/courses/{course_id}/enrollments/upload",
        content=csv_data,
        headers={"Content-Type": "text/csv"},
    )
    assert resp.status_code == 201
    res = resp.json()
    assert res["accepted"] == 2
    assert len(res["rejected"]) == 2
    assert any("does not exist" in r["reason"] for r in res["rejected"])
    assert any("Duplicate USN" in r["reason"] for r in res["rejected"])


def test_tc_data_06_enrolment_controls_marks_entry(engine):
    """
    TC-Data-06: enrolment controls marks entry.
    Enrolled students appear in course records; non-enrolled students are rejected.
    """
    with Session(engine) as db:
        fac = models.Faculty(name="Dr. Smith", department="CSE")
        db.add(fac)
        db.flush()

        course = models.Course(code="SE300", title="Software Engineering", semester=5, faculty_id=fac.id)
        db.add(course)
        db.flush()

        s1 = models.Student(usn="PES1UG24AM301", name="Enrolled Student", department="CSE", semester=5)
        s2 = models.Student(usn="PES1UG24AM302", name="Not Enrolled", department="CSE", semester=5)
        db.add_all([s1, s2])
        db.flush()

        enr = models.Enrollment(student_id=s1.id, course_id=course.id)
        db.add(enr)
        db.commit()

        # Enrolled student check succeeds
        enrollment_record = check_student_enrolled(db, course.id, "PES1UG24AM301")
        assert enrollment_record.id == enr.id
        assert is_student_enrolled(db, course.id, "PES1UG24AM301") is True

        # Non-enrolled student check fails with AppError(400, "NOT_ENROLLED")
        with pytest.raises(AppError) as exc_info:
            check_student_enrolled(db, course.id, "PES1UG24AM302")
        assert exc_info.value.status_code == 400
        assert exc_info.value.code == "NOT_ENROLLED"
        assert "not enrolled" in exc_info.value.message.lower()
        assert is_student_enrolled(db, course.id, "PES1UG24AM302") is False

        # Unregistered USN check fails
        with pytest.raises(AppError) as exc_unreg:
            check_student_enrolled(db, course.id, "NONEXISTENT")
        assert exc_unreg.value.status_code == 400
        assert exc_unreg.value.code == "NOT_ENROLLED"


def test_server_side_role_blocking_faculty_and_students(app, engine):
    """Verify non-admin roles (Faculty and Student) are blocked (403) from admin endpoints."""
    with Session(engine) as db:
        fac_client, _, _ = create_user_and_login(app, db, "prof_blocked", models.Role.FACULTY, faculty_profile=True)
        stu_client, _, _ = create_user_and_login(app, db, "stu_blocked", models.Role.STUDENT)

    # Faculty blocked from creating courses or students
    assert fac_client.post(f"{API}/courses", json={"code": "CS999", "title": "T", "semester": 1, "facultyId": 1}).status_code == 403
    assert fac_client.post(f"{API}/students", json={"usn": "U1", "name": "N", "department": "D", "semester": 1}).status_code == 403
    assert fac_client.post(f"{API}/students/upload", content="usn\n1").status_code == 403
    assert fac_client.post(f"{API}/courses/1/enrollments", json={"usn": "U1"}).status_code == 403
    assert fac_client.post(f"{API}/courses/1/enrollments/upload", content="usn\n1").status_code == 403

    # Student blocked from all admin endpoints
    assert stu_client.post(f"{API}/courses", json={"code": "CS999", "title": "T", "semester": 1, "facultyId": 1}).status_code == 403
    assert stu_client.get(f"{API}/courses").status_code == 403
    assert stu_client.post(f"{API}/students", json={"usn": "U1", "name": "N", "department": "D", "semester": 1}).status_code == 403
    assert stu_client.get(f"{API}/students").status_code == 403
    assert stu_client.post(f"{API}/courses/1/enrollments", json={"usn": "U1"}).status_code == 403
    assert stu_client.get(f"{API}/courses/1/enrollments").status_code == 403


def test_malformed_csv_does_not_crash(app, engine):
    """Verify malformed CSV files do not crash the application and return 400 BAD_FILE."""
    with Session(engine) as db:
        admin_client, _, _ = create_user_and_login(app, db, "admin_malformed", models.Role.ADMIN)

    # Completely empty body
    resp_empty = admin_client.post(f"{API}/students/upload", content="", headers={"Content-Type": "text/csv"})
    assert resp_empty.status_code == 400
    assert resp_empty.json()["error"]["code"] == "BAD_FILE"

    # CSV missing required headers
    bad_header_csv = "wrong,columns,here\n1,2,3"
    resp_bad = admin_client.post(f"{API}/students/upload", content=bad_header_csv, headers={"Content-Type": "text/csv"})
    assert resp_bad.status_code == 400
    assert resp_bad.json()["error"]["code"] == "BAD_FILE"
