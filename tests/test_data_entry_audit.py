"""Tests for marks and attendance entry, CSV upload and audit logging (APAS-F-010, F-011, SR-005, NF-005).

Covers:
- TC-Data-01: Upload marks from CSV
- TC-Data-02: Record or import attendance
- TC-Sec-05: Audit entry for a data change (old and new value)
- TC-Ops-01: Audit log retrieval
"""

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


def setup_course_with_enrolled_students(db, faculty_id):
    course = models.Course(code="UE24CS341A", title="Software Engineering", semester=5, faculty_id=faculty_id)
    db.add(course)
    db.flush()

    s1 = models.Student(usn="PES1UG24AM001", name="Asha", department="CSE", semester=5)
    s2 = models.Student(usn="PES1UG24AM002", name="Ravi", department="CSE", semester=5)
    s3 = models.Student(usn="PES1UG24AM003", name="Meera", department="CSE", semester=5)
    s_not_enrolled = models.Student(usn="PES1UG24AM099", name="Unenrolled", department="CSE", semester=5)
    db.add_all([s1, s2, s3, s_not_enrolled])
    db.flush()

    e1 = models.Enrollment(student_id=s1.id, course_id=course.id)
    e2 = models.Enrollment(student_id=s2.id, course_id=course.id)
    e3 = models.Enrollment(student_id=s3.id, course_id=course.id)
    db.add_all([e1, e2, e3])

    assessment = models.Assessment(
        course_id=course.id,
        name="ISA 1",
        max_marks=40,
        held_on=date(2026, 10, 5),
    )
    db.add(assessment)
    db.commit()

    return course.id, assessment.id, e1.id, e2.id, e3.id


def test_tc_data_01_upload_marks_from_csv(app, engine):
    """
    TC-Data-01: upload marks from CSV (APAS-F-010).
    CSV of marks for one course.
    Marks appear against the correct students and course; non-enrolled students rejected.
    """
    with Session(engine) as db:
        fac_client, _, fac_id = create_user_and_login(app, db, "teacher1", models.Role.FACULTY, faculty_profile=True)
        course_id, assessment_id, e1_id, e2_id, e3_id = setup_course_with_enrolled_students(db, fac_id)

    csv_content = (
        "usn,marks\n"
        "PES1UG24AM001,35\n"
        "PES1UG24AM002,28.5\n"
        "PES1UG24AM099,30\n"       # non-enrolled student
        "PES1UG24AM001,39\n"       # duplicate USN in file
        "PES1UG24AM003,45\n"       # marks > max_marks (40)
    )

    resp = fac_client.post(
        f"{API}/courses/{course_id}/assessments/{assessment_id}/marks",
        content=csv_content,
        headers={"Content-Type": "text/csv"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["accepted"] == 2
    assert len(data["rejected"]) == 3
    assert any("not enrolled" in r["reason"].lower() for r in data["rejected"])
    assert any("Duplicate" in r["reason"] for r in data["rejected"])
    assert any("between 0 and" in r["reason"].lower() for r in data["rejected"])

    # Verify marks landed in database against correct enrollment
    with Session(engine) as db:
        m1 = db.scalars(
            select(models.MarkEntry).where(
                models.MarkEntry.assessment_id == assessment_id,
                models.MarkEntry.enrollment_id == e1_id,
            )
        ).first()
        m2 = db.scalars(
            select(models.MarkEntry).where(
                models.MarkEntry.assessment_id == assessment_id,
                models.MarkEntry.enrollment_id == e2_id,
            )
        ).first()
        assert m1 is not None and m1.marks == 35.0
        assert m2 is not None and m2.marks == 28.5


def test_tc_data_02_record_and_import_attendance(app, engine):
    """
    TC-Data-02: record or import attendance (APAS-F-011).
    Attendance CSV and JSON for one class session.
    Entries saved and counted in each student's total.
    """
    with Session(engine) as db:
        fac_client, _, fac_id = create_user_and_login(app, db, "teacher_att", models.Role.FACULTY, faculty_profile=True)
        course_id, _, e1_id, e2_id, _ = setup_course_with_enrolled_students(db, fac_id)

    # 1. Record via SAD JSON format { "sessionDate": "...", "present": [...], "absent": [...] }
    json_payload = {
        "sessionDate": "2026-10-06",
        "present": ["PES1UG24AM001"],
        "absent": ["PES1UG24AM002"],
    }
    resp_json = fac_client.post(
        f"{API}/courses/{course_id}/attendance",
        json=json_payload,
    )
    assert resp_json.status_code == 201
    assert resp_json.json()["recorded"] == 2

    # 2. Record via CSV format for next session
    csv_payload = (
        "session_date,usn,status\n"
        "2026-10-07,PES1UG24AM001,present\n"
        "2026-10-07,PES1UG24AM002,present\n"
        "2026-10-07,PES1UG24AM099,present\n"  # non-enrolled
    )
    resp_csv = fac_client.post(
        f"{API}/courses/{course_id}/attendance",
        content=csv_payload,
        headers={"Content-Type": "text/csv"},
    )
    assert resp_csv.status_code == 201
    assert resp_csv.json()["recorded"] == 2
    assert len(resp_csv.json()["rejected"]) == 1
    assert "not enrolled" in resp_csv.json()["rejected"][0]["reason"].lower()

    # Verify records in database
    with Session(engine) as db:
        recs_s1 = db.scalars(
            select(models.AttendanceRecord).where(models.AttendanceRecord.enrollment_id == e1_id)
        ).all()
        assert len(recs_s1) == 2
        assert sum(1 for r in recs_s1 if r.present) == 2

        recs_s2 = db.scalars(
            select(models.AttendanceRecord).where(models.AttendanceRecord.enrollment_id == e2_id)
        ).all()
        assert len(recs_s2) == 2
        # On 10-06 absent (False), on 10-07 present (True)
        assert sum(1 for r in recs_s2 if r.present) == 1


def test_tc_sec_05_audit_entry_for_data_change(app, engine):
    """
    TC-Sec-05: audit entry for a data change (APAS-SR-005).
    Edit a mark; log entry recorded with user, time, old value and new value.
    """
    with Session(engine) as db:
        fac_client, user_id, fac_id = create_user_and_login(app, db, "teacher_audit", models.Role.FACULTY, faculty_profile=True)
        course_id, assessment_id, e1_id, _, _ = setup_course_with_enrolled_students(db, fac_id)

    # First entry: create mark (old_value=None, new_value=30.0)
    resp1 = fac_client.post(
        f"{API}/courses/{course_id}/assessments/{assessment_id}/marks",
        json={"entries": [{"usn": "PES1UG24AM001", "marks": 30.0}]},
    )
    assert resp1.status_code == 201

    # Edit mark (update from 30.0 to 38.0)
    resp2 = fac_client.post(
        f"{API}/courses/{course_id}/assessments/{assessment_id}/marks",
        json={"entries": [{"usn": "PES1UG24AM001", "marks": 38.0}]},
    )
    assert resp2.status_code == 201

    # Verify audit log entry in database
    with Session(engine) as db:
        audit_entries = db.scalars(
            select(models.AuditLogEntry)
            .where(models.AuditLogEntry.action == "UPDATE")
            .order_by(models.AuditLogEntry.id.desc())
        ).all()

        assert len(audit_entries) >= 1
        entry = audit_entries[0]
        assert entry.user_id == user_id
        assert entry.old_value == "30.0"
        assert entry.new_value == "38.0"
        assert entry.timestamp is not None
        assert "mark_entry" in entry.entity


def test_tc_ops_01_audit_log_retrieval(app, engine):
    """
    TC-Ops-01: audit log retrieval (APAS-NF-005).
    Edit a mark, log in as admin, retrieve audit log entries.
    Non-admin access is blocked (403).
    """
    with Session(engine) as db:
        fac_client, _, fac_id = create_user_and_login(app, db, "teacher_ops", models.Role.FACULTY, faculty_profile=True)
        admin_client, _, _ = create_user_and_login(app, db, "admin_ops", models.Role.ADMIN)
        stu_client, _, _ = create_user_and_login(app, db, "student_ops", models.Role.STUDENT)
        course_id, assessment_id, _, _, _ = setup_course_with_enrolled_students(db, fac_id)

    # Edit a mark to generate audit events
    fac_client.post(
        f"{API}/courses/{course_id}/assessments/{assessment_id}/marks",
        json={"entries": [{"usn": "PES1UG24AM001", "marks": 32.0}]},
    )

    # Admin retrieves audit logs
    resp_admin = admin_client.get(f"{API}/audit-log")
    assert resp_admin.status_code == 200
    logs = resp_admin.json()
    assert isinstance(logs, list)
    assert len(logs) > 0
    assert any("mark_entry" in log["entity"] for log in logs)

    # Non-admin users are blocked
    resp_fac = fac_client.get(f"{API}/audit-log")
    assert resp_fac.status_code == 403

    resp_stu = stu_client.get(f"{API}/audit-log")
    assert resp_stu.status_code == 403


def test_course_faculty_access_control(app, engine):
    """Verify faculty cannot enter marks or attendance for courses they are not assigned to."""
    with Session(engine) as db:
        _, _, fac1_id = create_user_and_login(app, db, "teacher_assigned", models.Role.FACULTY, faculty_profile=True)
        other_fac_client, _, _ = create_user_and_login(app, db, "teacher_other", models.Role.FACULTY, faculty_profile=True)
        course_id, assessment_id, _, _, _ = setup_course_with_enrolled_students(db, fac1_id)

    # other_fac is not assigned to course_id -> 403
    resp_marks = other_fac_client.post(
        f"{API}/courses/{course_id}/assessments/{assessment_id}/marks",
        json={"entries": [{"usn": "PES1UG24AM001", "marks": 30}]},
    )
    assert resp_marks.status_code == 403
    assert resp_marks.json()["error"]["code"] == "FORBIDDEN"

    resp_att = other_fac_client.post(
        f"{API}/courses/{course_id}/attendance",
        json={"sessionDate": "2026-10-08", "present": ["PES1UG24AM001"]},
    )
    assert resp_att.status_code == 403
    assert resp_att.json()["error"]["code"] == "FORBIDDEN"


def test_upload_marks_via_uploadfile_multipart(app, engine):
    """Verify marks entry via standard multipart UploadFile."""
    with Session(engine) as db:
        fac_client, _, fac_id = create_user_and_login(app, db, "fac_multipart", models.Role.FACULTY, faculty_profile=True)
        cid, aid, _, _, _ = setup_course_with_enrolled_students(db, fac_id)

    csv_content = "usn,marks\nPES1UG24AM001,40\n"
    res = fac_client.post(
        f"/api/v1/courses/{cid}/assessments/{aid}/marks",
        files={"file": ("marks.csv", csv_content.encode("utf-8"), "text/csv")},
    )
    assert res.status_code == 201
    assert res.json()["accepted"] == 1
