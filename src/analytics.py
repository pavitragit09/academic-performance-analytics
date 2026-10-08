"""Core analytics for the Academic Performance Analytics System."""


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


def is_declining(marks: list, window: int = 3) -> bool:
    """True if the last `window` marks are strictly decreasing (oldest -> newest)."""
    if window < 2:
        raise ValueError("window must be at least 2")
    if len(marks) < window:
        return False
    recent = marks[-window:]
    return all(recent[i] > recent[i + 1] for i in range(len(recent) - 1))


def risk_reasons(
    attendance_pct: float,
    avg_marks: float,
    marks_history: list,
    attendance_threshold: float = 75.0,
    marks_threshold: float = 40.0,
    decline_window: int = 3,
) -> list:
    """Return the list of reasons a student needs intervention (empty list = fine)."""
    reasons = []
    if attendance_pct < attendance_threshold:
        reasons.append("low attendance")
    if avg_marks < marks_threshold:
        reasons.append("low average marks")
    if is_declining(marks_history, decline_window):
        reasons.append("declining marks trend")
    return reasons


def is_at_risk(
    attendance_pct: float,
    avg_marks: float,
    marks_history: list,
    attendance_threshold: float = 75.0,
    marks_threshold: float = 40.0,
    decline_window: int = 3,
) -> bool:
    """True if the student meets at least one at-risk condition."""
    return bool(
        risk_reasons(
            attendance_pct,
            avg_marks,
            marks_history,
            attendance_threshold,
            marks_threshold,
            decline_window,
        )
    )