# Academic Performance Analytics System

Analyzes student marks, attendance, assignments and examinations, provides dashboards,
and identifies students whose performance is declining or who need intervention.

Course: Software Engineering (team project)

## Team

| Member | Responsibility |
|---|---|
| Pavitra | Repository owner, at-risk flag, SRS |
| Preeti | Marks trend / decline detection, SRS |
| Pranav | Assignment completion rate, SAD |
| Ryona | Exam performance summary / dashboard data, Test Plan |

## Project structure

```
.github/workflows/ci.yml   CI: runs pytest on every PR and push to main
src/                       Application code
tests/                     Unit tests (one or more per feature)
docs/                      SRS, SAD and Test Plan
requirements.txt           Python dependencies
pytest.ini                 Pytest configuration
```

## Getting started

```bash
git clone <repo-url>
cd academic-performance-analytics
python -m venv .venv
# Windows: .venv\Scripts\activate    Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
pytest
```

## Team workflow

1. `git checkout main` then `git pull origin main`
2. `git checkout -b feature/<name>`
3. Write the feature **and its tests**
4. Run `pytest` locally before pushing
5. `git push origin feature/<name>`
6. Open a Pull Request into `main` and request a teammate as reviewer
7. Merge only when CI is green and at least one teammate has approved
8. Everyone pulls the latest `main` after a merge

`main` is protected: no direct pushes, force pushes or merges without a passing CI check and an approval.

## Features implemented

- Attendance percentage
- Average marks
- Declining marks trend detection
- At-risk student flag with reasons (low attendance, low marks, declining trend)
