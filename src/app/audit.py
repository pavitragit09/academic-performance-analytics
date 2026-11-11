"""Audit logging service (APAS-SR-005, APAS-NF-005, TC-Sec-05, TC-Ops-01)."""

from typing import Any
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.app.models import AuditLogEntry, utc_now


def log_data_change(
    db: Session,
    action: str,
    entity: str,
    user_id: int | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    ip_address: str | None = None,
) -> AuditLogEntry:
    """Record an audit log entry with user, timestamp, old and new values."""
    entry = AuditLogEntry(
        user_id=user_id,
        action=action,
        entity=entity,
        old_value=old_value,
        new_value=new_value,
        timestamp=utc_now(),
        ip_address=ip_address,
    )
    db.add(entry)
    db.flush()
    return entry


def list_audit_logs(
    db: Session,
    entity: str | None = None,
    action: str | None = None,
    user_id: int | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Retrieve audit log entries (Administrator access, TC-Ops-01)."""
    stmt = select(AuditLogEntry)
    if entity is not None:
        stmt = stmt.where(AuditLogEntry.entity.like(f"%{entity}%"))
    if action is not None:
        stmt = stmt.where(AuditLogEntry.action == action)
    if user_id is not None:
        stmt = stmt.where(AuditLogEntry.user_id == user_id)

    stmt = stmt.order_by(AuditLogEntry.id.desc()).limit(limit)
    entries = db.scalars(stmt).all()

    return [
        {
            "id": e.id,
            "userId": e.user_id,
            "action": e.action,
            "entity": e.entity,
            "oldValue": e.old_value,
            "newValue": e.new_value,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "ipAddress": e.ip_address,
        }
        for e in entries
    ]
