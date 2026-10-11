"""Exam performance summary / dashboard data for the Academic Performance Analytics System."""

from src.analytics import average_marks


def exam_summary(
    marks: list,
    max_marks: float = 100,
    pass_percentage: float = 40.0,
) -> dict:
    """Return summary stats for one exam: count, highest, lowest, average, pass rate (%)."""
    if not marks:
        raise ValueError("marks list cannot be empty")
    if max_marks <= 0:
        raise ValueError("max_marks must be positive")
    if any(m < 0 or m > max_marks for m in marks):
        raise ValueError("each mark must be between 0 and max_marks")

    passed = sum(1 for m in marks if m * 100 >= pass_percentage * max_marks)
    return {
        "count": len(marks),
        "highest": max(marks),
        "lowest": min(marks),
        "average": average_marks(marks),
        "pass_rate": round(passed / len(marks) * 100, 2),
    }