"""Availability monitoring service (APAS-NF-002, 99.5% uptime target)."""

from datetime import datetime, timezone
import threading
from typing import Any

TARGET_AVAILABILITY_PCT = 99.5

_lock = threading.Lock()
_started_at = datetime.now(timezone.utc)
_successful_probes = 0
_failed_probes = 0


def reset_availability_stats(custom_start: datetime | None = None) -> None:
    """Reset statistics (used primarily for test isolation)."""
    global _started_at, _successful_probes, _failed_probes
    with _lock:
        _started_at = custom_start or datetime.now(timezone.utc)
        _successful_probes = 0
        _failed_probes = 0


def record_probe(is_success: bool = True) -> None:
    """Record a health check probe result."""
    global _successful_probes, _failed_probes
    with _lock:
        if is_success:
            _successful_probes += 1
        else:
            _failed_probes += 1


def get_availability_report() -> dict[str, Any]:
    """Compute uptime, probe counts, availability percentage and SLA compliance."""
    with _lock:
        now = datetime.now(timezone.utc)
        uptime_seconds = max(0.0, (now - _started_at).total_seconds())
        total = _successful_probes + _failed_probes
        if total == 0:
            pct = 100.0
        else:
            pct = round((_successful_probes / total) * 100.0, 2)

        meets_target = pct >= TARGET_AVAILABILITY_PCT
        return {
            "uptimeSeconds": round(uptime_seconds, 2),
            "totalChecks": total,
            "successfulChecks": _successful_probes,
            "failedChecks": _failed_probes,
            "availabilityPercentage": pct,
            "targetPercentage": TARGET_AVAILABILITY_PCT,
            "meetsTarget": meets_target,
            "startedAt": _started_at.isoformat(),
        }
