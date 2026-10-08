import pytest
from src.analytics import (
    attendance_percentage,
    average_marks,
    is_declining,
    is_at_risk,
    risk_reasons,
)


def test_attendance_percentage():
    assert attendance_percentage(45, 60) == 75.0


def test_attendance_invalid_total():
    with pytest.raises(ValueError):
        attendance_percentage(5, 0)


def test_attendance_attended_more_than_total():
    with pytest.raises(ValueError):
        attendance_percentage(10, 5)


def test_average_marks():
    assert average_marks([70, 80, 90]) == 80.0


def test_average_marks_empty():
    with pytest.raises(ValueError):
        average_marks([])


def test_is_declining_true():
    assert is_declining([80, 70, 60]) is True


def test_is_declining_false_when_improving():
    assert is_declining([60, 70, 80]) is False


def test_is_declining_not_enough_data():
    assert is_declining([80, 70]) is False


def test_is_declining_invalid_window():
    with pytest.raises(ValueError):
        is_declining([80, 70, 60], window=1)


def test_at_risk_low_attendance():
    assert is_at_risk(60.0, 75.0, [70, 72, 75]) is True


def test_at_risk_low_marks():
    assert is_at_risk(90.0, 30.0, [30, 32, 35]) is True


def test_at_risk_declining_trend():
    assert is_at_risk(90.0, 70.0, [85, 75, 65]) is True


def test_not_at_risk():
    assert is_at_risk(90.0, 75.0, [70, 75, 80]) is False


def test_risk_reasons_lists_all_conditions():
    reasons = risk_reasons(50.0, 30.0, [60, 40, 30])
    assert reasons == ["low attendance", "low average marks", "declining marks trend"]