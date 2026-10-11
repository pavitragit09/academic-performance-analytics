"""Assignment completion analytics for the Academic Performance Analytics System.

Each assignment status is "submitted" (on time), "late" or "missing" (SRS APAS-F-012).
"""

VALID_STATUSES = ("submitted", "late", "missing")


def _validate(statuses: list) -> None:
    """Raise ValueError if statuses is empty or contains an unknown status."""
    if not statuses:
        raise ValueError("statuses list cannot be empty")
    invalid = [s for s in statuses if s not in VALID_STATUSES]
    if invalid:
        raise ValueError(f"invalid status(es): {invalid}; expected one of {VALID_STATUSES}")


def status_breakdown(statuses: list) -> dict:
    """Return the count of each assignment status."""
    _validate(statuses)
    return {status: statuses.count(status) for status in VALID_STATUSES}
