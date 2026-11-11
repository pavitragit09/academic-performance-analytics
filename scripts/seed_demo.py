"""Fill the local database with sample data for the demo videos.

Usage (from the repository root):
    python -m scripts.seed_demo
    uvicorn src.app.main:app --reload

Demo logins (sample data only, never use these on a real system):
    faculty1 / DemoFaculty1!    teaches UE24CS341A Software Engineering
    admin1   / DemoAdmin1!
    student1 / DemoStudent1!    linked to PES1UG24AM001 (Asha)
"""

from datetime import date

from sqlalchemy import select

from src.app import models
from src.app.database import SessionLocal, init_db
from src.app.security import hash_password

# usn, name, marks out of 20 for three quizzes, sessions present out of 10,
# assignment statuses, ISA 1 marks out of 40
STUDENTS = [
    ("PES1UG24AM001", "Asha", [16, 18, 17], 9, ["SUBMITTED", "SUBMITTED"], 36),
    ("PES1UG24AM002", "Ravi", [12, 10, 7], 6, ["LATE", "MISSING"], 14),
    ("PES1UG24AM003", "Meera", [14, 15, 15], 10, ["SUBMITTED", "LATE"], 30),
    ("PES1UG24AM004", "Karan", [7, 6, 8], 8, ["MISSING", "MISSING"], 12),
    ("PES1UG24AM005", "Divya", [19, 18, 20], 10, ["SUBMITTED", "SUBMITTED"], 39),
    ("PES1UG24AM006", "Arjun", [13, 14, 12], 7, ["SUBMITTED", "MISSING"], 25),
]


def add_user(db, username, password, role):
    user = models.User(
        username=username, password_hash=hash_password(password), role=role, is_active=True
    )
    db.add(user)
    db.flush()
    return user


def seed() -> None:
    init_db()
    with SessionLocal() as db:
        if db.scalar(select(models.User).limit(1)) is not None:
            raise SystemExit("The database already has users. Delete apas.db and run this again.")

        faculty_user = add_user(db, "faculty1", "DemoFaculty1!", models.Role.FACULTY)
        add_user(db, "admin1", "DemoAdmin1!", models.Role.ADMIN)
        student_user = add_user(db, "student1", "DemoStudent1!", models.Role.STUDENT)

        faculty = models.Faculty(
            user_id=faculty_user.id, name="Dr. A. Rao", department="CSE", email="arao@example.edu"
        )
        db.add(faculty)
        db.flush()
        course = models.Course(
            code="UE24CS341A", title="Software Engineering", semester=5, faculty_id=faculty.id
        )
        db.add(course)
        db.flush()

        quizzes = []
        for number, held_on in enumerate([date(2026, 10, 1), date(2026, 10, 15), date(2026, 10, 29)], 1):
            quiz = models.Assessment(
                course_id=course.id, name=f"Quiz {number}", max_marks=20, held_on=held_on
            )
            db.add(quiz)
            quizzes.append(quiz)
        labs = [
            models.Assignment(course_id=course.id, title=f"Lab {n}", due_date=due, max_score=10)
            for n, due in [(1, date(2026, 10, 10)), (2, date(2026, 10, 24))]
        ]
        db.add_all(labs)
        db.flush()

        for usn, name, marks, present, statuses, isa in STUDENTS:
            student = models.Student(usn=usn, name=name, department="CSE", semester=5)
            if usn == "PES1UG24AM001":
                student.user_id = student_user.id
            db.add(student)
            db.flush()
            enrollment = models.Enrollment(student_id=student.id, course_id=course.id)
            db.add(enrollment)
            db.flush()

            for quiz, value in zip(quizzes, marks):
                db.add(models.MarkEntry(assessment_id=quiz.id, enrollment_id=enrollment.id, marks=value))
            for day in range(1, 11):
                db.add(models.AttendanceRecord(
                    enrollment_id=enrollment.id,
                    session_date=date(2026, 10, day * 2),
                    present=day <= present,
                ))
            for lab, status in zip(labs, statuses):
                db.add(models.AssignmentSubmission(
                    assignment_id=lab.id,
                    enrollment_id=enrollment.id,
                    status=models.SubmissionStatus(status),
                    score=None if status == "MISSING" else 8,
                ))
            db.add(models.ExamResult(
                enrollment_id=enrollment.id, exam_type="ISA1", marks=isa, max_marks=40
            ))

        db.commit()
    print(f"Demo data added: 1 course, {len(STUDENTS)} students. Log in as faculty1 / DemoFaculty1!")


if __name__ == "__main__":
    seed()
