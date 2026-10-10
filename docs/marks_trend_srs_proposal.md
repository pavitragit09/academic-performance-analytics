# Preeti's SRS Contribution — APAS

**Project:** Academic Performance Analytics System  
**Contributor:** Preeti  
**Area:** Marks Trend and Decline Detection  
**Related Requirement:** APAS-F-022  
**Status:** Proposed for review

## 1. Purpose

This document proposes a clarification to the marks-trend and decline-detection requirement in the Software Requirements Specification (SRS). The objective is to align the requirement with the implemented functionality and define clear acceptance criteria for testing.

## 2. Existing Requirement

The current SRS requirement APAS-F-022 states that the system shall detect a declining trend when a student's marks decrease over the last N consecutive assessments, with a default N of 3 and a configurable value.

## 3. Proposed Requirement Clarification

The system shall evaluate a student's marks over the most recent N assessments, where N defaults to 3 and must be at least 2. It shall calculate the linear trend slope of the marks and classify the trend as:

- **Declining:** The slope is less than the negative tolerance.
- **Improving:** The slope is greater than the positive tolerance.
- **Stable:** The slope falls within the tolerance.
- **Insufficient data:** Fewer than two marks are available for trend classification.

The default tolerance shall be 1.0 mark per assessment. The tolerance must be non-negative.

The system shall identify students with a declining trend over the configured assessment window.

## 4. Acceptance Criteria

1. A sequence of marks with a sufficiently negative slope is classified as declining.
2. A sequence with a sufficiently positive slope is classified as improving.
3. A sequence whose slope falls within the configured tolerance is classified as stable.
4. Fewer than two marks result in an insufficient-data classification.
5. The configured assessment window must be at least two assessments.
6. Students whose recent trend is declining are identified by the decline-detection function.
7. Automated tests cover declining, improving, stable, insufficient-data, and invalid-input cases.

## 5. Traceability and Testing

This proposal relates to APAS-F-022 and its existing test reference, TC-An-03.

The implementation and its unit tests are maintained in:

- `src/trend.py`
- `tests/test_trend.py`

The team should update the official SRS acceptance criteria and the corresponding Requirements Traceability Matrix (RTM) after this proposal is reviewed and accepted.

## 6. Review Notes

This document is a proposed SRS contribution. The SRS owner should confirm the revised definition, incorporate the agreed wording into the official SRS, and ensure the associated test case and RTM entry remain consistent.