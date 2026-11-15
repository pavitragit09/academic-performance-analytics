"""Scalability test for APAS-NF-003 (TC-Perf-02): 5,000 students and 200 concurrent users.

Seeds a throwaway SQLite database with 5,000 students spread over 50 courses (100 per
course, one faculty member per course, 3 marks, 20 attendance records and an ISA result
each), starts the real API, logs in 200 users (50 faculty and 150 students), and has all
200 use the API at the same time. Every request must succeed ("no functional
degradation") and the 90th percentile must stay within the limit.

Run from the repo root:
    python scripts\\load_test_nf003.py
Options: --courses 50  --per-course 100  --rounds 5  --limit 3.0
Exit code 0 = NF-003 met, 1 = not met.
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

from scripts.load_test_nf001 import PORT, wait_for_server  # noqa: E402

PASSWORD = "LoadTestPass123!"
STUDENT_USERS_PER_COURSE = 3


def seed(db_url: str, courses: int, per_course: int) -> dict:
    """Create the data. Returns the usernames and course ids the virtual users need."""
    from sqlalchemy.orm import Session

    from src.app import models
    from src.app.database import build_engine, init_db
    from src.app.security import hash_password

    engine = build_engine(db_url)
    init_db(engine)
    password_hash = hash_password(PASSWORD)  # hashed once and shared, so seeding stays fast
    faculty_logins, student_logins, course_ids = [], [], []

    with Session(engine) as db:
        for c in range(courses):
            user = models.User(
                username=f"fac{c:03d}", password_hash=password_hash,
                role=models.Role.FACULTY, is_active=True,
            )
            db.add(user)
            db.flush()
            faculty = models.Faculty(user_id=user.id, name=f"Faculty {c}", department="CSE")
            db.add(faculty)
            db.flush()
            course = models.Course(code=f"LT{c:03d}", title=f"Course {c}", semester=5, faculty_id=faculty.id)
            db.add(course)
            db.flush()
            assessments = []
            for index in range(3):
                assessment = models.Assessment(
                    course_id=course.id, name=f"Quiz {index + 1}", max_marks=50,
                    held_on=date(2026, 9, 1) + timedelta(days=7 * index),
                )
                db.add(assessment)
                assessments.append(assessment)
            db.flush()
            for number in range(per_course):
                login_user_id = None
                if number < STUDENT_USERS_PER_COURSE:
                    student_user = models.User(
                        username=f"stu{c:03d}{number}", password_hash=password_hash,
                        role=models.Role.STUDENT, is_active=True,
                    )
                    db.add(student_user)
                    db.flush()
                    login_user_id = student_user.id
                    student_logins.append(student_user.username)
                student = models.Student(
                    user_id=login_user_id, usn=f"PES1UG24NF{c:03d}{number:03d}",
                    name=f"Student {c}-{number}", department="CSE", semester=5,
                )
                db.add(student)
                db.flush()
                enrollment = models.Enrollment(student_id=student.id, course_id=course.id)
                db.add(enrollment)
                db.flush()
                for offset in range(20):
                    db.add(models.AttendanceRecord(
                        enrollment_id=enrollment.id,
                        session_date=date(2026, 8, 1) + timedelta(days=offset),
                        present=(offset + number) % 4 != 0,
                    ))
                for index, assessment in enumerate(assessments):
                    db.add(models.MarkEntry(
                        assessment_id=assessment.id, enrollment_id=enrollment.id,
                        marks=float((number * 7 + index * 3) % 51),
                    ))
                db.add(models.ExamResult(
                    enrollment_id=enrollment.id, exam_type="ISA",
                    marks=float(number % 41), max_marks=40.0,
                ))
            faculty_logins.append(user.username)
            course_ids.append(course.id)
        db.commit()
    engine.dispose()
    return {"faculty": faculty_logins, "students": student_logins, "courses": course_ids}


def login_cookie(base: str, username: str) -> dict:
    from src.app.routers.auth import SESSION_COOKIE

    response = httpx.post(
        f"{base}/api/v1/auth/login", json={"username": username, "password": PASSWORD}, timeout=120
    )
    response.raise_for_status()
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{SESSION_COOKIE}="):
            return {"Cookie": header.split(";", 1)[0]}
    raise RuntimeError(f"no session cookie for {username}")


def virtual_user(base: str, headers: dict, paths: list[str], rounds: int) -> list[tuple[float, int]]:
    """One user: repeat their requests `rounds` times. Returns (seconds, status) per request."""
    results = []
    with httpx.Client(base_url=base, timeout=120, headers=headers) as client:
        for _ in range(rounds):
            for path in paths:
                start = time.perf_counter()
                try:
                    code = client.get(path).status_code
                except httpx.HTTPError:
                    code = 599
                results.append((time.perf_counter() - start, code))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--courses", type=int, default=50)
    parser.add_argument("--per-course", type=int, default=100)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--limit", type=float, default=None, help="optional p90 limit in seconds (not enforced if omitted)")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        db_url = f"sqlite:///{Path(folder, 'scale.db').as_posix()}"
        print(f"Seeding {args.courses * args.per_course} students in {args.courses} courses...")
        data = seed(db_url, args.courses, args.per_course)

        env = {**os.environ, "APAS_DATABASE_URL": db_url}
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "src.app.main:app", "--port", str(PORT), "--log-level", "warning"],
            cwd=ROOT, env=env,
        )
        base = f"http://127.0.0.1:{PORT}"
        try:
            wait_for_server(base)
            users = []
            for index, username in enumerate(data["faculty"]):
                course_id = data["courses"][index]
                users.append((username, [
                    f"/api/v1/courses/{course_id}/exams?exam_type=ISA",
                    f"/api/v1/courses/{course_id}/at-risk",
                ]))
            for username in data["students"]:
                users.append((username, ["/api/v1/student/dashboard"]))
            print(f"Logging in {len(users)} users...")
            with ThreadPoolExecutor(max_workers=len(users)) as pool:
                cookies = list(pool.map(lambda user: login_cookie(base, user[0]), users))

            print(f"{len(users)} users working at the same time, {args.rounds} rounds each, "
                  f"p90 limit: {args.limit or 'none'}\n")
            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=len(users)) as pool:
                futures = [
                    pool.submit(virtual_user, base, cookies[i], users[i][1], args.rounds)
                    for i in range(len(users))
                ]
                results = [item for future in futures for item in future.result()]
            elapsed = time.perf_counter() - start
        finally:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()

    times = sorted(seconds for seconds, _ in results)
    errors = sum(1 for _, code in results if code >= 400)
    p90 = times[int(0.9 * len(times)) - 1]
    p95 = times[int(0.95 * len(times)) - 1]
    ok = errors == 0 and (args.limit is None or p90 <= args.limit)
    print(f"{'PASS' if ok else 'FAIL'}  {len(results)} requests in {elapsed:.1f}s  "
          f"p50={statistics.median(times):.3f}s  p90={p90:.3f}s  p95={p95:.3f}s  "
          f"max={times[-1]:.3f}s  errors={errors}/{len(results)}")
    print("\nNF-003:", "MET" if ok else "NOT MET")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())