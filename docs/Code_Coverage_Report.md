# APAS – Code Coverage Report

**Project:** Academic Performance Analytics System (APAS)  
**Requirement:** NF-006 – Code Coverage Report  
**Date:** 09 November 2026  
**Test Framework:** pytest with pytest-cov  
**Python Version:** 3.11.9

## 1. Objective

To measure the line coverage of the APAS source code and verify that the analytics module satisfies the minimum coverage requirement of 80%.

## 2. Test Execution

Command used:

```powershell
pytest --cov=src --cov-report=term-missing --cov-report=html


```

## 3. Test Results

| Metric | Result |
|---|---:|
| Total tests executed | 192 |
| Tests passed | 192 |
| Tests failed | 0 |
| Warnings | 1 |
| Overall line coverage | 97% |
| Total statements | 884 |
| Covered statements | 861 |
| Missing statements | 23 |

## 4. Analytics Module Coverage

| Module | Statements | Missing | Coverage |
|---|---:|---:|---:|
| src/analytics.py | 28 | 0 | 100% |

The analytics module achieves 100% line coverage, exceeding the required minimum of 80%.

## 5. Selected Module Coverage

| Module | Coverage |
|---|---:|
| src/alerts.py | 100% |
| src/analytics.py | 100% |
| src/app/database.py | 86% |
| src/app/errors.py | 100% |
| src/app/models.py | 100% |
| src/app/routers/auth.py | 92% |
| src/app/routers/dashboard.py | 100% |
| src/app/validation.py | 94% |
| src/trend.py | 97% |

## 6. Warning

One Starlette deprecation warning was reported regarding the use of httpx with starlette.testclient. It did not affect test execution or results.

## 7. Conclusion

The APAS project achieved 97% overall line coverage, with all 192 tests passing.

The analytics module achieved 100% line coverage, successfully meeting the NF-006 requirement of at least 80%.

The detailed HTML coverage report is available in the `docs/coverage/` directory. Open `docs/coverage/index.html` in a browser to inspect file-level coverage details.


