
"""Marks trend and decline detection for APAS."""


def trend_slope(marks: list) -> float:
    """Return the linear trend slope of marks, from oldest to newest.

    Negative slope means marks are falling; positive means rising.
    """
    if len(marks) < 2:
        raise ValueError("at least 2 marks are required")

    n = len(marks)
    x_mean = (n - 1) / 2
    y_mean = sum(marks) / n

    numerator = sum(
        (i - x_mean) * (mark - y_mean)
        for i, mark in enumerate(marks)
    )
    denominator = sum((i - x_mean) ** 2 for i in range(n))

    return round(numerator / denominator, 2)


def trend_label(marks: list, tolerance: float = 1.0) -> str:
    """Classify marks as declining, improving, stable, or insufficient."""
    if tolerance < 0:
        raise ValueError("tolerance cannot be negative")

    if len(marks) < 2:
        return "insufficient data"

    slope = trend_slope(marks)

    if slope < -tolerance:
        return "declining"
    if slope > tolerance:
        return "improving"
    return "stable"


def drop_percentage(marks: list, window: int = 3) -> float:
    """Calculate percentage drop between the first and last recent marks.

    A positive value means marks dropped; a negative value means they rose.
    Returns 0.0 when there are fewer than two usable marks or the
    first mark in the window is zero.
    """
    if window < 2:
        raise ValueError("window must be at least 2")

    recent = marks[-window:]

    if len(recent) < 2 or recent[0] == 0:
        return 0.0

    return round(
        (recent[0] - recent[-1]) / recent[0] * 100,
        2,
    )


def flag_declining_students(
    students: dict,
    window: int = 3,
    tolerance: float = 1.0,
) -> list:
    """Return names of students with a declining recent marks trend."""
    if window < 2:
        raise ValueError("window must be at least 2")

    flagged = []

    for name, marks in students.items():
        if (
            len(marks) >= window
            and trend_label(marks[-window:], tolerance) == "declining"
        ):
            flagged.append(name)

    return flagged