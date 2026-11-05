"""At-risk alerts (APAS-F-040) for the Academic Performance Analytics System.

Notifies the responsible faculty member when a student is NEWLY flagged as at-risk.
An alert is created synchronously when the risk check runs, so it is generated
immediately after the flag (the SRS requires within 1 minute).
"""

from datetime import datetime

from src.analytics import risk_reasons


class AlertService:
    """Tracks each student's last known risk state and creates alerts on new flags."""

    def __init__(self) -> None:
        self._last_reasons = {}  # student_id -> list of reasons from the last check
        self._alerts = []

    def check_student(
        self,
        student_id: str,
        faculty_id: str,
        attendance_pct: float,
        avg_marks: float,
        marks_history: list,
        attendance_threshold: float = 75.0,
        marks_threshold: float = 40.0,
        decline_window: int = 3,
        now: datetime = None,
    ):
        """Run the risk check; return a new alert dict if newly flagged, else None.

        Newly flagged = at risk now, and not at risk at the previous check
        (or never checked before). A student who stays at risk, or whose reasons
        change while still at risk, does not generate another alert. A student who
        recovers and is later flagged again does.
        """
        if not student_id or not student_id.strip():
            raise ValueError("student_id cannot be empty")
        if not faculty_id or not faculty_id.strip():
            raise ValueError("faculty_id cannot be empty")

        reasons = risk_reasons(
            attendance_pct,
            avg_marks,
            marks_history,
            attendance_threshold,
            marks_threshold,
            decline_window,
        )
        was_at_risk = bool(self._last_reasons.get(student_id))
        self._last_reasons[student_id] = reasons

        if reasons and not was_at_risk:
            alert = {
                "student_id": student_id,
                "faculty_id": faculty_id,
                "reasons": reasons,
                "created_at": now or datetime.now(),
            }
            self._alerts.append(alert)
            return alert
        return None

    def alerts_for_faculty(self, faculty_id: str) -> list:
        """Return all alerts raised for a faculty member, oldest first."""
        return [a for a in self._alerts if a["faculty_id"] == faculty_id]
