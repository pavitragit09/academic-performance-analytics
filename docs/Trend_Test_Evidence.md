# APAS – Trend Test Evidence

**Project:** Academic Performance Analytics System (APAS)  
**Sprint:** Sprint 2  
**Task:** Trend Test Evidence  
**Date:** 10 November 2026  
**Implementation File:** `src/trend.py`  
**Test File:** `tests/test_trend.py`  
**Testing Framework:** pytest  
**Python Version:** 3.11.9

## 1. Objective

To verify the correctness and reliability of the trend analysis functionality in the Academic Performance Analytics System through automated unit testing.

The tests validate trend slope calculations, trend classification, marks drop percentage calculations, and identification of students showing consecutive academic declines.

## 2. Test Execution

The following command was executed from the project root directory:

```powershell
pytest tests/test_trend.py -v
```

## 3. Test Execution Summary

| Metric | Result |
|---|---:|
| Total test cases | 15 |
| Passed test cases | 15 |
| Failed test cases | 0 |
| Execution time | 0.11 seconds |
| Overall result | PASS |

## 4. Detailed Test Case Results

| Test Case | Description | Result |
|---|---|---|
| test_slope_falling | Verifies calculation of a falling trend slope | PASS |
| test_slope_rising | Verifies calculation of a rising trend slope | PASS |
| test_slope_requires_two_marks | Checks minimum marks requirement for slope calculation | PASS |
| test_label_declining | Verifies declining trend classification | PASS |
| test_label_improving | Verifies improving trend classification | PASS |
| test_label_stable | Verifies stable trend classification | PASS |
| test_label_insufficient_data | Checks classification when insufficient data is available | PASS |
| test_negative_tolerance_is_invalid | Checks rejection of negative tolerance values | PASS |
| test_drop_percentage | Verifies marks drop percentage calculation | PASS |
| test_drop_percentage_rising_is_negative | Checks negative drop percentage when marks increase | PASS |
| test_drop_percentage_not_enough_data | Checks behavior with insufficient marks data | PASS |
| test_drop_percentage_invalid_window | Checks rejection of invalid calculation windows | PASS |
| test_flag_declining_students | Verifies identification of declining students | PASS |
| test_flag_uses_strict_consecutive_decline | Checks strict consecutive decline detection | PASS |
| test_flag_rejects_invalid_window | Checks rejection of invalid windows during declining student identification | PASS |

## 5. Functional Areas Verified

The test execution covers the following functional areas:

1. **Trend Slope Calculation:** Verifies rising and falling academic performance trends and minimum data requirements.
2. **Trend Classification:** Verifies improving, declining, stable, and insufficient-data classifications.
3. **Drop Percentage Calculation:** Checks percentage changes in marks and validates input windows.
4. **Declining Student Identification:** Verifies detection of students with consecutive declining performance and rejection of invalid windows.
5. **Input Validation:** Ensures invalid tolerance values and calculation windows are handled correctly.

## 6. Test Execution Evidence

The following is the execution summary from the actual pytest run:

```text
collected 15 items

tests/test_trend.py::test_slope_falling PASSED
tests/test_trend.py::test_slope_rising PASSED
tests/test_trend.py::test_slope_requires_two_marks PASSED
tests/test_trend.py::test_label_declining PASSED
tests/test_trend.py::test_label_improving PASSED
tests/test_trend.py::test_label_stable PASSED
tests/test_trend.py::test_label_insufficient_data PASSED
tests/test_trend.py::test_negative_tolerance_is_invalid PASSED
tests/test_trend.py::test_drop_percentage PASSED
tests/test_trend.py::test_drop_percentage_rising_is_negative PASSED
tests/test_trend.py::test_drop_percentage_not_enough_data PASSED
tests/test_trend.py::test_drop_percentage_invalid_window PASSED
tests/test_trend.py::test_flag_declining_students PASSED
tests/test_trend.py::test_flag_uses_strict_consecutive_decline PASSED
tests/test_trend.py::test_flag_rejects_invalid_window PASSED

15 passed in 0.11s
```

## 7. Conclusion

All 15 trend analysis test cases passed successfully.

The testing activity verifies the core functionality of academic performance trend analysis, including slope calculation, trend classification, drop percentage calculation, and identification of declining students.

No test failures were reported.
