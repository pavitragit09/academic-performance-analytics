"""Exam results record keeping (APAS-F-013) for the Academic Performance Analytics System.

Stores internal and end-semester results per student and subject, rejects invalid
or duplicate records (APAS-F-014), and returns marks lists that feed exam_summary.
"""

EXAM_TYPES = ("internal", "end_semester")


class ExamRecords:
    """In-memory store of exam results keyed by (student_id, subject, exam_type)."""

    def __init__(self) -> None:
        self._records = {}

    def add_result(
        self,
        student_id: str,
        subject: str,
        exam_type: str,
        marks: float,
        max_marks: float = 100,
    ) -> dict:
        """Store one exam result and return the stored record."""
        if not student_id or not student_id.strip():
            raise ValueError("student_id cannot be empty")
        if not subject or not subject.strip():
            raise ValueError("subject cannot be empty")
        if exam_type not in EXAM_TYPES:
            raise ValueError("exam_type must be 'internal' or 'end_semester'")
        if max_marks <= 0:
            raise ValueError("max_marks must be positive")
        if marks < 0 or marks > max_marks:
            raise ValueError("marks must be between 0 and max_marks")

        key = (student_id, subject, exam_type)
        if key in self._records:
            raise ValueError("duplicate result for this student, subject and exam type")

        record = {
            "student_id": student_id,
            "subject": subject,
            "exam_type": exam_type,
            "marks": marks,
            "max_marks": max_marks,
        }
        self._records[key] = record
        return record

    def get_result(self, student_id: str, subject: str, exam_type: str) -> dict:
        """Return one stored result; raise KeyError if it does not exist."""
        key = (student_id, subject, exam_type)
        if key not in self._records:
            raise KeyError("no result recorded for this student, subject and exam type")
        return self._records[key]

    def results_for_student(self, student_id: str) -> list:
        """Return all results for a student (empty list if none)."""
        return [r for (sid, _, _), r in self._records.items() if sid == student_id]

    def marks_for_subject(self, subject: str, exam_type: str) -> list:
        """Return all marks for a subject and exam type, ready for exam_summary()."""
        if exam_type not in EXAM_TYPES:
            raise ValueError("exam_type must be 'internal' or 'end_semester'")
        return [
            r["marks"]
            for (_, subj, etype), r in self._records.items()
            if subj == subject and etype == exam_type
        ]
