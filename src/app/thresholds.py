"""Administrator-configurable analytics thresholds service (APAS-F-025, SAD)."""

import json
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.audit import log_data_change
from src.app.errors import AppError
from src.app.models import AnalyticsThreshold

DEFAULT_ATTENDANCE_THRESHOLD = 75.0
DEFAULT_MARKS_THRESHOLD = 40.0
DEFAULT_TREND_WINDOW = 3


def get_analytics_thresholds(db: Session) -> AnalyticsThreshold:
    """Retrieve the current analytics thresholds, initializing defaults if none exist."""
    thresholds = db.scalar(select(AnalyticsThreshold).order_by(AnalyticsThreshold.id.desc()))
    if thresholds is None:
        thresholds = AnalyticsThreshold(
            attendance_threshold=DEFAULT_ATTENDANCE_THRESHOLD,
            marks_threshold=DEFAULT_MARKS_THRESHOLD,
            trend_window=DEFAULT_TREND_WINDOW,
        )
        db.add(thresholds)
        db.commit()
        db.refresh(thresholds)
    return thresholds


def update_analytics_thresholds(
    db: Session,
    attendance_threshold: float,
    marks_threshold: float,
    trend_window: int,
    user_id: int | None = None,
    ip_address: str | None = None,
) -> AnalyticsThreshold:
    """Validate, persist and audit-log updated analytics thresholds."""
    if not (0.0 <= attendance_threshold <= 100.0):
        raise AppError(
            422,
            "VALIDATION_ERROR",
            f"Attendance threshold must be between 0 and 100, got {attendance_threshold}",
        )
    if not (0.0 <= marks_threshold <= 100.0):
        raise AppError(
            422,
            "VALIDATION_ERROR",
            f"Marks threshold must be between 0 and 100, got {marks_threshold}",
        )
    if trend_window < 2:
        raise AppError(
            422,
            "VALIDATION_ERROR",
            f"Trend window must be at least 2, got {trend_window}",
        )

    thresholds = get_analytics_thresholds(db)

    old_state = {
        "attendance_threshold": thresholds.attendance_threshold,
        "marks_threshold": thresholds.marks_threshold,
        "trend_window": thresholds.trend_window,
    }
    new_state = {
        "attendance_threshold": round(float(attendance_threshold), 2),
        "marks_threshold": round(float(marks_threshold), 2),
        "trend_window": int(trend_window),
    }

    thresholds.attendance_threshold = new_state["attendance_threshold"]
    thresholds.marks_threshold = new_state["marks_threshold"]
    thresholds.trend_window = new_state["trend_window"]

    log_data_change(
        db=db,
        action="UPDATE_ANALYTICS_THRESHOLDS",
        entity="analytics_thresholds",
        user_id=user_id,
        old_value=json.dumps(old_state),
        new_value=json.dumps(new_state),
        ip_address=ip_address,
    )

    db.commit()
    db.refresh(thresholds)
    return thresholds
