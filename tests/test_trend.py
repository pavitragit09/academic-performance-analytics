
import pytest

from src.trend import (
    trend_slope,
    trend_label,
    drop_percentage,
    flag_declining_students,
)


def test_slope_falling():
    assert trend_slope([80, 70, 60]) == -10.0


def test_slope_rising():
    assert trend_slope([50, 60, 70]) == 10.0


def test_slope_requires_two_marks():
    with pytest.raises(ValueError):
        trend_slope([50])


def test_label_declining():
    assert trend_label([80, 70, 60]) == "declining"


def test_label_improving():
    assert trend_label([50, 60, 70]) == "improving"


def test_label_stable():
    assert trend_label([60, 60.5, 61]) == "stable"


def test_label_insufficient_data():
    assert trend_label([50]) == "insufficient data"


def test_negative_tolerance_is_invalid():
    with pytest.raises(ValueError):
        trend_label([80, 70, 60], tolerance=-1)


def test_drop_percentage():
    assert drop_percentage([80, 70, 60]) == 25.0


def test_drop_percentage_rising_is_negative():
    assert drop_percentage([60, 70, 80]) == -33.33


def test_drop_percentage_not_enough_data():
    assert drop_percentage([70]) == 0.0


def test_drop_percentage_invalid_window():
    with pytest.raises(ValueError):
        drop_percentage([80, 70, 60], window=1)


def test_flag_declining_students():
    students = {
        "A": [80, 70, 60],
        "B": [50, 60, 70],
        "C": [60],
    }
    assert flag_declining_students(students) == ["A"]


def test_flag_uses_overall_trend():
    students = {"A": [80, 65, 70]}
    assert flag_declining_students(students) == ["A"]


def test_flag_rejects_invalid_window():
    with pytest.raises(ValueError):
        flag_declining_students({"A": [80, 70, 60]}, window=1)