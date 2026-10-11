import pytest
from src.assignments import completion_rate, low_completion_students, status_breakdown


def test_status_breakdown_counts():
    result = status_breakdown(["submitted", "late", "missing", "submitted"])
    assert result == {"submitted": 2, "late": 1, "missing": 1}


def test_empty_list_raises():
    with pytest.raises(ValueError):
        status_breakdown([])


def test_unknown_status_raises():
    with pytest.raises(ValueError):
        status_breakdown(["submitted", "done"])


def test_completion_rate_srs_example():
    assert completion_rate(["submitted"] * 8 + ["missing"] * 2) == 80.0


def test_completion_rate_all_submitted():
    assert completion_rate(["submitted"] * 5) == 100.0


def test_completion_rate_all_missing():
    assert completion_rate(["missing"] * 4) == 0.0


def test_completion_rate_excludes_late_by_default():
    assert completion_rate(["submitted", "late", "missing"]) == 33.33


def test_completion_rate_include_late():
    assert completion_rate(["submitted", "late", "missing"], include_late=True) == 66.67


def test_completion_rate_empty_raises():
    with pytest.raises(ValueError):
        completion_rate([])


def test_low_completion_students():
    students = {
        "Asha": ["submitted"] * 4,
        "Ravi": ["submitted", "missing", "missing", "late"],
        "Meera": [],
    }
    assert low_completion_students(students) == ["Ravi"]


def test_low_completion_at_threshold_not_flagged():
    students = {"Kiran": ["submitted", "submitted", "submitted", "missing"]}
    assert low_completion_students(students) == []


def test_low_completion_invalid_threshold_raises():
    with pytest.raises(ValueError):
        low_completion_students({"Asha": ["submitted"]}, threshold=120)