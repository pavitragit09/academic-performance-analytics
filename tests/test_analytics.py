import pytest
from src.analytics import attendance_percentage, average_marks


def test_attendance_percentage():
    assert attendance_percentage(45, 60) == 75.0


def test_attendance_invalid_total():
    with pytest.raises(ValueError):
        attendance_percentage(5, 0)


def test_average_marks():
    assert average_marks([70, 80, 90]) == 80.0


def test_average_marks_empty():
    with pytest.raises(ValueError):
        average_marks([])
