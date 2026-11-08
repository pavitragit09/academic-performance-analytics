"""E-mail notifications for at-risk alerts (APAS-F-040, SAD Notification Service).

Alerts are sent from a background task so an upload or risk check is never slowed
down. A failed send is retried and then logged; it never breaks the request, and the
alert is still saved and shown through the at-risk list.
"""

import logging
import smtplib
import time
from collections.abc import Callable
from dataclasses import dataclass
from email.message import EmailMessage

from src.app.config import get_mail_from, get_smtp_host, get_smtp_port

logger = logging.getLogger(__name__)

# A sender takes (to, subject, body) and returns True when the mail was handed over.
EmailSender = Callable[[str, str, str], bool]


@dataclass
class RiskAlert:
    """Everything needed to tell a faculty member about a newly flagged student."""

    faculty_email: str | None
    faculty_name: str
    usn: str
    student_name: str
    course_code: str
    reasons: list[str]


def build_alert_email(alert: RiskAlert) -> tuple[str, str]:
    """Return (subject, body) for an at-risk alert."""
    subject = f"[APAS] {alert.usn} flagged at-risk in {alert.course_code}"
    reasons = "\n".join(f"- {reason}" for reason in alert.reasons)
    body = (
        f"Dear {alert.faculty_name},\n\n"
        f"{alert.student_name} ({alert.usn}) has been flagged as at-risk in "
        f"{alert.course_code} for the following reasons:\n{reasons}\n\n"
        "Please review the student on the APAS dashboard and plan an intervention.\n"
    )
    return subject, body


def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    host: str | None = None,
    port: int | None = None,
    sender: str | None = None,
    retries: int = 3,
    retry_delay: float = 1.0,
    smtp_factory=smtplib.SMTP,
) -> bool:
    """Send one e-mail, retrying on failure. Returns False if every attempt failed."""
    message = EmailMessage()
    message["From"] = sender or get_mail_from()
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    for attempt in range(1, retries + 1):
        try:
            with smtp_factory(host or get_smtp_host(), port or get_smtp_port(), timeout=10) as server:
                server.send_message(message)
            return True
        except (OSError, smtplib.SMTPException) as exc:
            logger.warning("E-mail to %s failed (attempt %s of %s): %s", to, attempt, retries, exc)
            if attempt < retries:
                time.sleep(retry_delay)

    logger.error("E-mail to %s could not be sent after %s attempts", to, retries)
    return False


def get_email_sender() -> EmailSender:
    """FastAPI dependency. Tests replace this with a fake sender."""
    return send_email