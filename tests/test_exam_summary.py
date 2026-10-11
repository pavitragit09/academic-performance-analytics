import pytest
from src.exam_summary import exam_summary


def test_basic_summary():
    result = exam_summary([50, 80, 30])
    assert result == {
        "count": 3,
        "highest": 80,
        "lowest": 30,
        "average": 53.33,
        "pass_rate": 66.67,
    }


def test_all_fail():
    result = exam_summary([10, 20, 30])
    assert result["pass_rate"] == 0.0


def test_all_pass():
    assert exam_summary([40, 60, 90])["pass_rate"] == 100.0


def test_single_value():
    result = exam_summary([75])
    assert result["highest"] == 75
    assert result["lowest"] == 75
    assert result["average"] == 75.0
    assert result["pass_rate"] == 100.0


def test_pass_mark_boundary_counts_as_pass():
    assert exam_summary([40])["pass_rate"] == 100.0
    assert exam_summary([39])["pass_rate"] == 0.0


def test_custom_max_marks():
    # out of 50, pass mark is 20
    assert exam_summary([20, 19], max_marks=50)["pass_rate"] == 50.0


def test_empty_marks():
    with pytest.raises(ValueError):
        exam_summary([])


def test_negative_mark():
    with pytest.raises(ValueError):
        exam_summary([50, -1])


def test_mark_above_max():
    with pytest.raises(ValueError):
        exam_summary([50, 101])


def test_invalid_max_marks():
    with pytest.raises(ValueError):
        exam_summary([50], max_marks=0)