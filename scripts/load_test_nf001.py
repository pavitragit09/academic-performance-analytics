"""Load test for APAS-NF-001 (TC-Perf-01): 500-student course, p90 response time <= 3 s.

Seeds a throwaway SQLite database with one course of 500 students (marks, attendance, ISA
results), starts the real API with uvicorn, logs in as the course's faculty, then fires
concurrent requests at the read endpoints and reports p50/p90/p95/max for each.

Run from the repo root:
    python scripts\\load_test_nf001.py
Options: --students 500  --requests 200  --concurrency 10  --limit 3.0
Exit code 0 = every endpoint met the limit, 1 = at least one missed it.
"""

import argparse
import os
import statistics
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

USERNAME = "loadtest_faculty"
PASSWORD = "LoadTestPass123!"
PORT = 8765


def seed(db_url: str, students: int) -> int:
    """Create one faculty, one course and `students` enrolled students. Return the course id."""
    from sqlalchemy.orm import Session

    from src.app import models
    from src.app.database import build_engine, init_db
    from src.app.security import hash_password

    engine = build_engine(db_url)
    init_db(engine)
    with Session(engine) as db:
        user = models.User(
            username=USERNAME,
            password_hash=hash_password(PASSWORD),
            role=models.Role.FACULTY,
            is_active=True,
        )
        db.add(user)
        db.flush()
        faculty = models.Faculty(user_id=user.id, name="Load Test", department="CSE")
        db.add(faculty)
        db.flush()
        course = models.Course(code="LOAD500", title="Load test", semester=5, faculty_id=faculty.id)
        db.add(course)
        db.flush()
        assessments = []
        for index in range(4):
            assessment = models.Assessment(
                course_id=course.id, name=f"Quiz {index + 1}", max_marks=50,
                held_on=date(2026, 9, 1) + timedelta(days=7 * index),
            )
            db.add(assessment)
            assessments.append(assessment)
        db.flush()
        for number in range(students):
            student = models.Student(
                usn=f"PES1UG24LT{number:04d}", name=f"Student {number}", department="CSE", semester=5
            )
            db.add(student)
            db.flush()
            enrollment = models.Enrollment(student_id=student.id, course_id=course.id)
            db.add(enrollment)
            db.flush()
            for offset in range(40):  # 40 sessions; every 4th student is a poor attender
                present = (offset % 4 != 0) if number % 4 else (offset % 2 == 0)
                db.add(models.AttendanceRecord(
                    enrollment_id=enrollment.id,
                    session_date=date(2026, 8, 1) + timedelta(days=offset),
                    present=present,
                ))
            for index, assessment in enumerate(assessments):
                db.add(models.MarkEntry(
                    assessment_id=assessment.id, enrollment_id=enrollment.id,
                    marks=float((number * 7 + index * 3) % 51),
                ))
            db.add(models.ExamResult(
                enrollment_id=enrollment.id, exam_type="ISA", marks=float(number % 41), max_marks=40.0
            ))
        db.commit()
        course_id = course.id
    engine.dispose()
    return course_id


def wait_for_server(base: str) -> None:
    for _ in range(60):
        try:
            if httpx.get(f"{base}/api/v1/health", timeout=1).status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    raise RuntimeError("API did not start within 30 seconds")


def login_cookie(base: str) -> dict:
    """Log in and return the session cookie as a header (it is Secure, so plain http would drop it)."""
    from src.app.routers.auth import SESSION_COOKIE

    response = httpx.post(f"{base}/api/v1/auth/login", json={"username": USERNAME, "password": PASSWORD})
    response.raise_for_status()
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{SESSION_COOKIE}="):
            return {"Cookie": header.split(";", 1)[0]}
    raise RuntimeError("login did not return a session cookie")


def timed(client: httpx.Client, method: str, url: str, headers: dict) -> tuple[float, int]:
    start = time.perf_counter()
    response = client.request(method, url, headers=headers)
    return time.perf_counter() - start, response.status_code


def run_endpoint(base, headers, name, method, path, requests, concurrency, limit) -> bool:
    with httpx.Client(base_url=base, timeout=60) as client:
        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            results = list(pool.map(lambda _: timed(client, method, path, headers), range(requests)))
    times = sorted(seconds for seconds, _ in results)
    failures = sum(1 for _, code in results if code >= 400)
    p90 = times[int(0.9 * len(times)) - 1]
    p95 = times[int(0.95 * len(times)) - 1]
    verdict = "PASS" if p90 <= limit and failures == 0 else "FAIL"
    print(
        f"{verdict}  {name:<28} p50={statistics.median(times):.3f}s  p90={p90:.3f}s  "
        f"p95={p95:.3f}s  max={times[-1]:.3f}s  errors={failures}/{requests}"
    )
    return verdict == "PASS"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--students", type=int, default=500)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--limit", type=float, default=3.0, help="p90 limit in seconds")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        db_url = f"sqlite:///{Path(folder, 'load.db').as_posix()}"
        print(f"Seeding {args.students} students...")
        course_id = seed(db_url, args.students)

        env = {**os.environ, "APAS_DATABASE_URL": db_url}
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "src.app.main:app", "--port", str(PORT), "--log-level", "warning"],
            cwd=ROOT, env=env,
        )
        base = f"http://127.0.0.1:{PORT}"
        try:
            wait_for_server(base)
            headers = login_cookie(base)
            print(f"{args.requests} requests per endpoint, {args.concurrency} concurrent, p90 limit {args.limit}s\n")
            checks = [
                ("GET exam results (500 rows)", "GET", f"/api/v1/courses/{course_id}/exams?exam_type=ISA", args.concurrency),
                ("GET at-risk list", "GET", f"/api/v1/courses/{course_id}/at-risk", args.concurrency),
                # A batch job one faculty member runs after an upload, so it is tested one user at a time.
                ("POST risk-check (500 students)", "POST", f"/api/v1/courses/{course_id}/risk-check", 1),
            ]
            outcomes = [
                run_endpoint(base, headers, name, method, path, args.requests, users, args.limit)
                for name, method, path, users in checks
            ]
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()

    print("\nNF-001:", "MET" if all(outcomes) else "NOT MET")
    return 0 if all(outcomes) else 1


if __name__ == "__main__":
    sys.exit(main())