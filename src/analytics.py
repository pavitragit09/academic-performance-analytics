def attendance_percentage(attended: int, total: int) -> float:
    """Return attendance as a percentage rounded to 2 decimals."""
    if total <= 0:
        raise ValueError("total classes must be positive")
    if attended < 0 or attended > total:
        raise ValueError("attended must be between 0 and total")
    return round(attended / total * 100, 2)


def average_marks(marks: list) -> float:
    """Return the average of a list of marks."""
    if not marks:
        raise ValueError("marks list cannot be empty")
    return round(sum(marks) / len(marks), 2)
