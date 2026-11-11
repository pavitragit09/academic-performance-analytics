"""Tests for the administrator department summary (APAS-F-032, TC-Dash-03)
and report export as CSV and PDF (APAS-F-033, TC-Dash-04)."""

import csv
import io
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from src.app import models
from src.app.database import build_engine, get_db, init_db
from src.app.main import create_app
from src.app.reports import CSV_COLUMNS, _cell, course_report_pdf, report_filename
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


def add_course(db, faculty, code, title):
    course = models.Course(code=code, title=title, semester=5, faculty_id=faculty.id)
    db.add(course)
    db.flush()
    return course


def add_student(db, course, usn, name, marks, attended):
    """Three 20-mark quizzes and ten attendance sessions."""
    student = models.Student(usn=usn, name=name, department="CSE", semester=5)
    db.add(student)
    db.flush()
    enrollment = models.Enrollment(student_id=student.id, course_id=course.id)
    db.add(enrollment)
    db.flush()
    quizzes = sorted(course.assessments, key=lambda a: a.held_on)
    for quiz, value in zip(quizzes, marks):
        db.add(models.MarkEntry(assessment_id=quiz.id, enrollment_id=enrollment.id, marks=value))
    for day in range(1, 11):
        db.add(models.AttendanceRecord(
            enrollment_id=enrollment.id, session_date=date(2026, 10, day), present=day <= attended
        ))
    return enrollment


def add_quizzes(db, course):
    for day in (1, 8, 15):
        db.add(models.Assessment(
            course_id=course.id, name=f"Quiz {day}", max_marks=20, held_on=date(2026, 10, day)
        ))
    db.flush()
    db.refresh(course)


@pytest.fixture
def courses(engine):
    """CSE has two courses (one at-risk student each); ECE has one course with nobody at risk."""
    with Session(engine) as db:
        f1 = add_user(db, "faculty1", models.Role.FACULTY)
        f2 = add_user(db, "faculty2", models.Role.FACULTY)
        f3 = add_user(db, "faculty3", models.Role.FACULTY)
        add_user(db, "admin1", models.Role.ADMIN)
        add_user(db, "student1", models.Role.STUDENT)
        rao = models.Faculty(user_id=f1.id, name="A. Rao", department="CSE")
        iyer = models.Faculty(user_id=f2.id, name="B. Iyer", department="CSE")
        das = models.Faculty(user_id=f3.id, name="C. Das", department="ECE")
        db.add_all([rao, iyer, das])
        db.flush()

        se = add_course(db, rao, "UE24CS341A", "Software Engineering")
        db_course = add_course(db, iyer, "UE24CS342A", "Databases")
        signals = add_course(db, das, "UE24EC301A", "Signals")
        for course in (se, db_course, signals):
            add_quizzes(db, course)

        add_student(db, se, "PES001", "Asha", [16, 18, 17], attended=9)      # 85.0, fine
        add_student(db, se, "PES002", "Ravi", [9, 7, 5], attended=6)         # 35.0, at risk
        add_student(db, db_course, "PES003", "Meera", [14, 14, 14], attended=10)  # 70.0, fine
        add_student(db, db_course, "PES004", "Karan", [6, 6, 6], attended=10)     # 30.0, at risk
        add_student(db, signals, "PES005", "Divya", [12, 12, 12], attended=10)    # 60.0, fine
        db.commit()
        return {"se": se.id, "db": db_course.id, "signals": signals.id}


# ---------- APAS-F-032 department summary (TC-Dash-03) ----------

def test_admin_lists_departments(app, courses):
    response = login(app, "admin1").get(f"{API}/dashboard/departments")

    assert response.status_code == 200
    assert response.json() == {"departments": ["CSE", "ECE"]}


def test_department_summary_per_course(app, courses):
    body = login(app, "admin1").get(f"{API}/dashboard/departments/CSE").json()

    assert body["department"] == "CSE"
    assert body["courses"] == [
        {"courseId": courses["se"], "code": "UE24CS341A", "title": "Software Engineering",
         "enrolled": 2, "average": 60.0, "atRiskCount": 1},
        {"courseId": courses["db"], "code": "UE24CS342A", "title": "Databases",
         "enrolled": 2, "average": 50.0, "atRiskCount": 1},
    ]


def test_department_totals_match_the_course_dashboards(app, courses):
    """TC-Dash-03: totals reconcile with the underlying student data."""
    client = login(app, "admin1")
    summary = client.get(f"{API}/dashboard/departments/cse").json()
    dashboards = [
        client.get(f"{API}/dashboard/courses/{courses[key]}").json() for key in ("se", "db")
    ]
    student_averages = [
        s["averageMarks"] for d in dashboards for s in d["students"]
    ]

    assert summary["totals"] == {
        "courses": 2,
        "enrolled": sum(d["enrolled"] for d in dashboards),
        "average": round(sum(student_averages) / len(student_averages), 2),
        "atRiskCount": sum(len(d["atRisk"]) for d in dashboards),
    }
    assert summary["totals"] == {"courses": 2, "enrolled": 4, "average": 55.0, "atRiskCount": 2}


def test_other_department_is_separate(app, courses):
    body = login(app, "admin1").get(f"{API}/dashboard/departments/ECE").json()

    assert body["totals"] == {"courses": 1, "enrolled": 1, "average": 60.0, "atRiskCount": 0}


def test_department_thresholds_change_the_counts(app, courses):
    body = login(app, "admin1").get(
        f"{API}/dashboard/departments/CSE", params={"marksThreshold": 75}
    ).json()

    assert [row["atRiskCount"] for row in body["courses"]] == [1, 2]


def test_department_with_no_data(app, engine, courses):
    with Session(engine) as db:
        db.add(models.Faculty(name="D. Nair", department="MECH"))
        db.commit()
    client = login(app, "admin1")

    assert client.get(f"{API}/dashboard/departments/MECH").status_code == 404
    response = client.get(f"{API}/dashboard/departments/Unknown")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_empty_course_has_no_average(app, engine, courses):
    with Session(engine) as db:
        das = db.query(models.Faculty).filter_by(name="C. Das").one()
        add_course(db, das, "UE24EC302A", "Empty course")
        db.commit()

    body = login(app, "admin1").get(f"{API}/dashboard/departments/ECE").json()

    assert body["courses"][1]["average"] is None
    assert body["totals"]["average"] == 60.0


@pytest.mark.parametrize("username", ["faculty1", "student1"])
def test_department_summary_is_admin_only(app, courses, username):
    client = login(app, username)

    assert client.get(f"{API}/dashboard/departments/CSE").status_code == 403
    assert client.get(f"{API}/dashboard/departments").status_code == 403


def test_department_summary_needs_login(app, courses):
    client = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)

    assert client.get(f"{API}/dashboard/departments/CSE").status_code == 401


# ---------- APAS-F-033 report export (TC-Dash-04) ----------

def export(client, course_id, **params):
    return client.get(f"{API}/reports/courses/{course_id}", params=params)


def test_csv_matches_the_dashboard(app, courses):
    """TC-Dash-04: every exported value equals the dashboard value."""
    client = login(app, "faculty1")
    response = export(client, courses["se"], format="csv")
    dashboard = client.get(f"{API}/dashboard/courses/{courses['se']}").json()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == (
        'attachment; filename="UE24CS341A_report.csv"'
    )
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert list(rows[0].keys()) == CSV_COLUMNS
    assert len(rows) == dashboard["enrolled"]
    reasons = {r["usn"]: "; ".join(r["reasons"]) for r in dashboard["atRisk"]}
    for row, student in zip(rows, dashboard["students"]):
        assert row["usn"] == student["usn"]
        assert row["name"] == student["name"]
        assert float(row["attendancePct"]) == student["attendancePct"]
        assert float(row["averageMarks"]) == student["averageMarks"]
        assert row["declining"] == str(student["declining"]).lower()
        assert row["atRisk"] == str(student["atRisk"]).lower()
        assert row["riskReasons"] == reasons.get(student["usn"], "")


def test_csv_is_the_default_format(app, courses):
    response = export(login(app, "faculty1"), courses["se"])

    assert response.status_code == 200
    assert response.text.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert "PES002,Ravi,60.0,35.0,true" in response.text


def test_pdf_contains_the_dashboard_figures(app, courses):
    response = export(login(app, "faculty1"), courses["se"], format="pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        'attachment; filename="UE24CS341A_report.pdf"'
    )
    pdf = response.content
    assert pdf.startswith(b"%PDF")
    for text in (b"UE24CS341A", b"Software Engineering", b"Class average: 60.0",
                 b"At risk: 1", b"Asha", b"Ravi", b"85.0", b"35.0", b"low attendance"):
        assert text in pdf


def test_admin_can_export_any_course(app, courses):
    response = export(login(app, "admin1"), courses["signals"], format="pdf")

    assert response.status_code == 200


def test_unknown_format_is_rejected(app, courses):
    response = export(login(app, "faculty1"), courses["se"], format="xlsx")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_faculty_cannot_export_another_course(app, courses):
    response = export(login(app, "faculty1"), courses["db"], format="csv")

    assert response.status_code == 403


def test_export_of_missing_course(app, courses):
    assert export(login(app, "admin1"), 999).status_code == 404


def test_student_cannot_export(app, courses):
    assert export(login(app, "student1"), courses["se"]).status_code == 403


def test_csv_cells_are_safe_in_spreadsheets():
    assert _cell(None) == ""
    assert _cell(True) == "true"
    assert _cell(False) == "false"
    assert _cell(72.5) == "72.5"
    assert _cell("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert _cell("@cmd") == "'@cmd"
    assert _cell("Asha") == "Asha"


def test_pdf_and_filename_for_course_without_data():
    dashboard = {
        "courseId": 1, "courseCode": "??", "courseTitle": "Empty", "enrolled": 0,
        "classAverage": None, "marksDistribution": {"0-39": 0}, "exams": [],
        "atRisk": [], "lowCompletion": [], "students": [],
    }

    assert report_filename(dashboard, "pdf") == "course_report.pdf"
    pdf = course_report_pdf(dashboard)
    assert pdf.startswith(b"%PDF")
    assert b"Class average: -" in pdf
    assert b"Exam summaries" not in pdf
