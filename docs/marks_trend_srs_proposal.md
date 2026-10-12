# Preeti's SRS Contribution - APAS

**Project:** Academic Performance Analytics System  
**Contributor:** Preeti  
**Area:** Marks Trend and Decline Detection  
**Related Requirement:** APAS-F-022  
**Status:** Proposed for team review; not yet approved

## 1. Purpose

This document proposes a clarification of the marks-trend and decline-detection requirement in the Software Requirements Specification (SRS). It describes the regression-based trend functionality implemented in the code and identifies the decision required to keep the SRS, implementation, acceptance criteria, and Requirements Traceability Matrix (RTM) consistent.

## 2. Existing Requirement

The current SRS requirement APAS-F-022 states that the system shall detect a declining trend when a student's marks decrease over the last N consecutive assessments, with a default N of 3 and a configurable value.

This definition describes consecutive decreases. It is not equivalent to regression-based trend classification.

## 3. Proposed Requirement Clarification

The following is a proposed alternative definition for team review. It must not replace the official SRS wording until the team approves the change.

The system shall evaluate a student's marks over the most recent N assessments, where N defaults to 3 and must be at least 2. It shall calculate the linear regression slope of the marks and classify the trend as follows:

- **Declining:** The slope is less than the negative tolerance.
- **Improving:** The slope is greater than the positive tolerance.
- **Stable:** The slope falls within the configured tolerance.
- **Insufficient data:** Fewer than two marks are available for trend classification.

The default tolerance shall be 1.0 mark per assessment. The tolerance must be non-negative.

The system shall identify students whose recent trend is classified as declining by the regression-based trend function.

## 4. Acceptance Criteria

If the team approves the proposed regression-based definition:

1. A sequence of marks with a sufficiently negative slope is classified as declining.
2. A sequence with a sufficiently positive slope is classified as improving.
3. A sequence whose slope falls within the configured tolerance is classified as stable.
4. Fewer than two marks result in an insufficient-data classification.
5. The configured assessment window must contain at least two assessments.
6. Students whose recent trend is classified as declining are identified by the regression-based decline-detection function.
7. Automated tests cover declining, improving, stable, insufficient-data, and invalid-input cases.

The team should confirm these criteria against the implementation and acceptance tests before incorporating them into the official SRS.

## 5. Traceability and Testing

This proposal relates to APAS-F-022 and the existing test reference TC-An-03.

The relevant implementation and unit tests are maintained in:

- `src/trend.py`
- `tests/test_trend.py`
- `src/analytics.py` for the separate consecutive-decrease check

The team should decide which definition APAS-F-022 will use. Following approval, the SRS acceptance criteria, implementation, test cases, and the corresponding RTM entry should be aligned.

## 6. Review Notes

This document is a proposed SRS contribution and does not establish requirement acceptance.

The SRS owner and project team should review the proposed regression-based definition, decide whether it should replace the existing consecutive-decrease definition, and document the approved decision. Until that review is complete, the official SRS wording and RTM acceptance status should remain unchanged.
