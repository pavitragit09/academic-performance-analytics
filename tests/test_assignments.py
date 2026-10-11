import pytest
from src.assignments import status_breakdown


def test_status_breakdown_counts():
    result = status_breakdown(["submitted", "late", "missing", "submitted"])
    assert result == {"submitted": 2, "late": 1, "missing": 1}


def test_empty_list_raises():
    with pytest.raises(ValueError):
        status_breakdown([])


def test_unknown_status_raises():
    with pytest.raises(ValueError):
        status_breakdown(["submitted", "done"])
