# Vett Backend — Phase 1 MVP

FastAPI · PostgreSQL · Adzuna API

## Quickstart

```bash
# 1. Copy env and fill in your Adzuna credentials
cp .env.example .env

# 2. Start PostgreSQL (Docker)
docker-compose up db -d

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run migrations
alembic upgrade head

# 5. Start the API server
uvicorn app.main:app --reload --port 8000
```

Interactive docs: http://localhost:8000/docs

## Or run everything with Docker

```bash
docker-compose up --build
```

## Architecture

```
app/
├── main.py              # FastAPI app + APScheduler startup
├── config.py            # Pydantic settings (env vars)
├── database.py          # Async SQLAlchemy engine + session
├── models/
│   ├── user.py          # User, UserProfile
│   ├── job.py           # Job, JobFitScore, SavedJob, DismissedJob
│   └── application.py   # Application
├── schemas/             # Pydantic request/response models
├── api/
│   ├── auth.py          # POST /register, POST /login
│   ├── users.py         # GET/PATCH /me, /me/profile
│   ├── jobs.py          # GET /feed, GET /:id, POST /save, /dismiss, /scan
│   ├── applications.py  # POST /, GET /, PATCH /:id, GET /:id/cover-note
│   └── cv.py            # POST /cv/upload
└── services/
    ├── adzuna.py        # Adzuna API client
    ├── cv_parser.py     # PDF/DOCX text + skill extraction
    ├── fit_scorer.py    # 4-dimension fit scoring engine
    └── job_scanner.py   # Background scan: fetch → parse → score → persist
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Create account, returns JWT |
| POST | `/api/v1/auth/login` | Login, returns JWT |
| GET | `/api/v1/users/me` | Current user |
| GET | `/api/v1/users/me/profile` | User profile |
| PATCH | `/api/v1/users/me/profile` | Update profile / complete onboarding |
| POST | `/api/v1/cv/upload` | Upload CV (PDF/DOCX), auto-parses skills |
| GET | `/api/v1/jobs/feed` | Personalised job feed, sorted by fit score |
| GET | `/api/v1/jobs/{id}` | Full job detail |
| POST | `/api/v1/jobs/save` | Save a job |
| DELETE | `/api/v1/jobs/save/{id}` | Unsave a job |
| GET | `/api/v1/jobs/saved/list` | Saved jobs |
| POST | `/api/v1/jobs/dismiss` | Dismiss a job (removes from feed) |
| POST | `/api/v1/jobs/scan` | Manually trigger scan for current user |
| POST | `/api/v1/applications` | Apply to a job (one-tap) |
| GET | `/api/v1/applications` | Application tracker |
| PATCH | `/api/v1/applications/{id}` | Update status / notes |
| GET | `/api/v1/applications/{id}/cover-note` | Reveal auto-generated cover note |

## Fit Scoring

4-dimension weighted scoring (0–100 overall):

| Dimension | Weight | Logic |
|-----------|--------|-------|
| Skills | 40% | Overlap between user's CV skills and job's required skills |
| Experience | 25% | Years of experience + seniority level match |
| Location | 20% | Remote preference vs job's remote flag |
| Salary | 15% | User salary band vs job salary band |

Jobs scoring below the user's `min_fit_score` (default: 60) are hidden from the feed.

## Environment Variables

See `.env.example` for all variables. Key ones:

- `ADZUNA_APP_ID` / `ADZUNA_API_KEY` — from https://developer.adzuna.com
- `SECRET_KEY` — long random string for JWT signing
- `DATABASE_URL` — async PostgreSQL connection string
- `SCAN_INTERVAL_HOURS` — how often the background scanner runs (default: 6)
