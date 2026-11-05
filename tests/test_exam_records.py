import pytest
from src.exam_records import ExamRecords
from src.exam_summary import exam_summary


@pytest.fixture
def records():
    return ExamRecords()


# TC-Data-04.1
def test_add_and_get_internal_result(records):
    records.add_result("S1", "Maths", "internal", 45, max_marks=50)
    assert records.get_result("S1", "Maths", "internal") == {
        "student_id": "S1",
        "subject": "Maths",
        "exam_type": "internal",
        "marks": 45,
        "max_marks": 50,
    }


# TC-Data-04.2
def test_add_end_semester_result(records):
    record = records.add_result("S1", "Maths", "end_semester", 72)
    assert record["exam_type"] == "end_semester"
    assert record["max_marks"] == 100


# TC-Data-04.3
def test_internal_and_end_semester_stored_separately(records):
    records.add_result("S1", "Maths", "internal", 40)
    records.add_result("S1", "Maths", "end_semester", 70)
    assert records.get_result("S1", "Maths", "internal")["marks"] == 40
    assert records.get_result("S1", "Maths", "end_semester")["marks"] == 70


# TC-Data-04.4
def test_results_for_student_returns_all_subjects(records):
    records.add_result("S1", "Maths", "internal", 40)
    records.add_result("S1", "Physics", "internal", 55)
    records.add_result("S2", "Maths", "internal", 60)
    results = records.results_for_student("S1")
    assert {r["subject"] for r in results} == {"Maths", "Physics"}
    assert len(results) == 2


def test_results_for_unknown_student_is_empty(records):
    assert records.results_for_student("nobody") == []


# TC-Data-04.5
def test_marks_for_subject_feeds_exam_summary(records):
    records.add_result("S1", "Maths", "internal", 50)
    records.add_result("S2", "Maths", "internal", 80)
    records.add_result("S3", "Maths", "internal", 30)
    records.add_result("S1", "Maths", "end_semester", 99)
    marks = records.marks_for_subject("Maths", "internal")
    assert sorted(marks) == [30, 50, 80]
    assert exam_summary(marks)["average"] == 53.33


def test_marks_for_subject_with_no_results(records):
    assert records.marks_for_subject("Chemistry", "internal") == []


def test_marks_for_subject_invalid_exam_type(records):
    with pytest.raises(ValueError):
        records.marks_for_subject("Maths", "quiz")


# TC-Data-04.6 (also APAS-F-014)
def test_duplicate_result_rejected(records):
    records.add_result("S1", "Maths", "internal", 40)
    with pytest.raises(ValueError):
        records.add_result("S1", "Maths", "internal", 50)
    assert records.get_result("S1", "Maths", "internal")["marks"] == 40


# TC-Data-04.7 (also APAS-F-014)
def test_negative_marks_rejected(records):
    with pytest.raises(ValueError):
        records.add_result("S1", "Maths", "internal", -1)


def test_marks_above_max_rejected(records):
    with pytest.raises(ValueError):
        records.add_result("S1", "Maths", "internal", 51, max_marks=50)


def test_boundary_marks_accepted(records):
    records.add_result("S1", "Maths", "internal", 0)
    records.add_result("S2", "Maths", "internal", 100)
    assert records.get_result("S1", "Maths", "internal")["marks"] == 0
    assert records.get_result("S2", "Maths", "internal")["marks"] == 100


# TC-Data-04.8
def test_invalid_exam_type_rejected(records):
    with pytest.raises(ValueError):
        records.add_result("S1", "Maths", "quiz", 40)


# TC-Data-04.9
def test_invalid_max_marks_rejected(records):
    with pytest.raises(ValueError):
        records.add_result("S1", "Maths", "internal", 10, max_marks=0)


# TC-Data-04.10
@pytest.mark.parametrize("student_id, subject", [("", "Maths"), ("  ", "Maths"), ("S1", ""), ("S1", " ")])
def test_blank_student_or_subject_rejected(records, student_id, subject):
    with pytest.raises(ValueError):
        records.add_result(student_id, subject, "internal", 40)


# TC-Data-04.11
def test_get_missing_result_raises(records):
    with pytest.raises(KeyError):
        records.get_result("S1", "Maths", "internal")
