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
src/                       Analytics modules
src/app/                   FastAPI application, database and API routers
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

## Run the API

```bash
uvicorn src.app.main:app --reload
```

- Web UI: http://127.0.0.1:8000/ (run `python -m scripts.seed_demo` once for demo logins)
- Health check: http://127.0.0.1:8000/api/v1/health
- Interactive API docs: http://127.0.0.1:8000/docs

The server creates a local SQLite database, `apas.db`, on first start. Set `APAS_DATABASE_URL` to use a different database.

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
- Assignment completion rate and status breakdown
- Exam performance summary
