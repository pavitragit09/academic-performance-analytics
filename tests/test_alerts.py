from datetime import datetime

import pytest
from src.alerts import AlertService

HEALTHY = dict(attendance_pct=90, avg_marks=70, marks_history=[60, 65, 70])
LOW_ATTENDANCE = dict(attendance_pct=60, avg_marks=70, marks_history=[60, 65, 70])


@pytest.fixture
def service():
    return AlertService()


# TC-Int-01.1
def test_newly_flagged_student_creates_alert(service):
    alert = service.check_student("S1", "F1", **LOW_ATTENDANCE)
    assert alert["student_id"] == "S1"
    assert alert["faculty_id"] == "F1"
    assert alert["reasons"] == ["low attendance"]


# TC-Int-01.2
def test_healthy_student_creates_no_alert(service):
    assert service.check_student("S1", "F1", **HEALTHY) is None
    assert service.alerts_for_faculty("F1") == []


# TC-Int-01.3
def test_still_at_risk_does_not_alert_again(service):
    service.check_student("S1", "F1", **LOW_ATTENDANCE)
    assert service.check_student("S1", "F1", **LOW_ATTENDANCE) is None
    assert len(service.alerts_for_faculty("F1")) == 1


# TC-Int-01.4
def test_changed_reasons_while_at_risk_does_not_alert_again(service):
    service.check_student("S1", "F1", **LOW_ATTENDANCE)
    worse = dict(attendance_pct=60, avg_marks=30, marks_history=[60, 65, 70])
    assert service.check_student("S1", "F1", **worse) is None


# TC-Int-01.5
def test_recovered_then_reflagged_alerts_again(service):
    service.check_student("S1", "F1", **LOW_ATTENDANCE)
    service.check_student("S1", "F1", **HEALTHY)
    assert service.check_student("S1", "F1", **LOW_ATTENDANCE) is not None
    assert len(service.alerts_for_faculty("F1")) == 2


# TC-Int-01.6
def test_alert_created_at_uses_given_time(service):
    when = datetime(2026, 11, 5, 12, 0, 0)
    alert = service.check_student("S1", "F1", now=when, **LOW_ATTENDANCE)
    assert alert["created_at"] == when


def test_alert_created_at_defaults_to_current_time(service):
    before = datetime.now()
    alert = service.check_student("S1", "F1", **LOW_ATTENDANCE)
    after = datetime.now()
    assert before <= alert["created_at"] <= after


# TC-Int-01.7
def test_multiple_reasons_all_listed(service):
    alert = service.check_student(
        "S1", "F1", attendance_pct=50, avg_marks=30, marks_history=[80, 60, 40]
    )
    assert alert["reasons"] == ["low attendance", "low average marks", "declining marks trend"]


# TC-Int-01.8
def test_alerts_are_per_faculty(service):
    service.check_student("S1", "F1", **LOW_ATTENDANCE)
    service.check_student("S2", "F2", **LOW_ATTENDANCE)
    assert [a["student_id"] for a in service.alerts_for_faculty("F1")] == ["S1"]
    assert [a["student_id"] for a in service.alerts_for_faculty("F2")] == ["S2"]
    assert service.alerts_for_faculty("F3") == []


# TC-Int-01.9
def test_custom_thresholds_are_used(service):
    # 80% attendance is fine by default, but at risk with a stricter 85% threshold
    assert service.check_student("S1", "F1", 80, 70, [60, 65, 70]) is None
    alert = service.check_student("S2", "F1", 80, 70, [60, 65, 70], attendance_threshold=85)
    assert alert["reasons"] == ["low attendance"]


# TC-Int-01.10
@pytest.mark.parametrize("student_id, faculty_id", [("", "F1"), (" ", "F1"), ("S1", ""), ("S1", " ")])
def test_blank_ids_rejected(service, student_id, faculty_id):
    with pytest.raises(ValueError):
        service.check_student(student_id, faculty_id, **LOW_ATTENDANCE)
