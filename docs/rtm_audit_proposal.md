# APAS Requirements Traceability Matrix (RTM) Audit

## Purpose

This document records the implementation and test evidence inspected for the Academic Performance Analytics System (APAS). It identifies requirements that need further verification before their official RTM status is changed.

This audit is a review proposal. It does not replace the official SRS or independently establish that a requirement has been accepted.

## Status guidance

- N — Not started, as defined by the current SRS.
- P — In progress, as defined by the current SRS.
- A — Accepted, as defined by the current SRS.

Existing code and passing unit tests are evidence of implementation and testing. Acceptance must also be checked against the requirement's acceptance criteria and any applicable integration or system tests.

## Evidence reviewed

| Area | Implementation inspected | Tests inspected | Evidence observed |
|---|---|---|---|
| Attendance percentage | `src/analytics.py` | `tests/test_analytics.py` | Calculation and invalid-input cases are tested. |
| Average marks | `src/analytics.py` | `tests/test_analytics.py` | Average calculation and empty-input handling are tested. |
| Declining marks | `src/analytics.py` | `tests/test_analytics.py` | Consecutive-decrease behavior and insufficient-data handling are tested. |
| Trend analysis | `src/trend.py` | `tests/test_trend.py` | Regression-based trend behavior is tested separately. |
| At-risk detection | `src/analytics.py` | `tests/test_analytics.py` | Low attendance, low marks, declining marks, and combined reasons are tested. |
| Assignment completion | `src/assignments.py` | `tests/test_assignments.py` | Status breakdown, completion rate, late-submission handling, and threshold validation are tested. |
| Exam summary | `src/exam_summary.py` | `tests/test_exam_summary.py` | Count, highest, lowest, average, pass rate, and invalid inputs are tested. |

## Findings requiring review

### 1. APAS-F-022: Declining marks

The official SRS defines a declining trend as marks decreasing over the last N consecutive assessments, with a default N of 3.

The inspected implementations use different rules:

- `src/analytics.py::is_declining` checks whether the last `window` marks are strictly decreasing. Its default window is 3.
- `src/trend.py::trend_label` classifies marks using a linear regression slope and a tolerance. `flag_declining_students` applies this classification to the selected recent window.
- `src/trend.py::drop_percentage` calculates percentage change between the first and last marks in the selected window; this is separate from regression-based classification.

For example, `[80, 65, 70]` does not satisfy the strict consecutive-decrease rule, but the existing `test_flag_uses_overall_trend` expects the regression-based implementation to flag it as declining.

**Action proposed:** Confirm with the team which definition APAS-F-022 should use. Align the approved requirement, implementation, and acceptance tests after that decision. Until then, preserve the current SRS wording and leave the official RTM status unchanged. The existing unit tests provide implementation evidence but do not independently establish system-level acceptance.

### 2. Requirements Traceability Matrix statuses

The SRS RTM currently marks requirements as Not started.

**Action proposed:** Review each requirement individually against implementation, acceptance criteria, and test evidence. Update its official status only when the team has sufficient evidence and the required review is complete.

### 3. Requirements not established by the inspected modules

The inspected Python modules and unit tests do not, by themselves, establish completion of authentication, access control, data import, dashboards, exports, interventions, or all non-functional and security requirements.

**Action proposed:** Locate the relevant implementation and verification evidence before assigning these requirements an Accepted status.

### 4. Assignment completion rate

The inspected implementation excludes late submissions by default and supports optionally including them. The tests verify both behaviors.

**Action proposed:** Preserve the SRS definition of on-time submissions divided by total assigned unless the team formally approves a change.

### 5. Scope of the evidence

Unit tests establish coverage of the tested functions and cases. They do not alone establish that the complete system satisfies every functional, non-functional, integration, or security requirement.

**Action proposed:** Link relevant tests and other verification evidence to the official RTM as the team completes its review.

## Review checklist

- [ ] Confirm the intended APAS-F-022 definition.
- [ ] Map each functional requirement to implementation evidence.
- [ ] Map each applicable requirement to verification evidence.
- [ ] Verify non-functional and security requirements separately.
- [ ] Update official RTM statuses only after review.
- [ ] Obtain the required teammate approval before merging changes to the official SRS.
