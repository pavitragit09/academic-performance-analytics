"""Faculty API for at-risk checks and alerts (APAS-F-040, SAD Notification Service)."""

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from src.app import risk
from src.app.database import get_db
from src.app.models import User
from src.app.notifications import EmailSender, build_alert_email, get_email_sender
from src.app.routers.auth import require_faculty

router = APIRouter(tags=["risk"])


@router.post("/courses/{course_id}/risk-check", response_model=risk.RiskCheckReport)
def run_risk_check(
    course_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(require_faculty),
    send: EmailSender = Depends(get_email_sender),
):
    """Check every student in the course; e-mail the faculty about each newly flagged one."""
    report, alerts = risk.check_course(db, course_id, user.id)
    for alert in alerts:
        if alert.faculty_email:
            subject, body = build_alert_email(alert)
            background_tasks.add_task(send, alert.faculty_email, subject, body)
    return report


@router.get("/courses/{course_id}/at-risk", response_model=list[risk.AtRiskStudent])
def list_at_risk(
    course_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_faculty),
):
    """Students currently flagged at-risk in the course, with their reasons."""
    return risk.active_flags(db, course_id, user.id)