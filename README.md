# GrantReady — Phase 1 MVP

Local web app that lets an Alberta farmer answer a short questionnaire and get back a
ranked, accurately sourced list of grant programs they actually qualify for, grouped by
urgency, with a draft application blurb per program.

All grant facts come from `grantready_seed_programs.json` (13 programs) — nothing is
invented. Flagged entries show a "Verify before applying" badge, and every card shows
its source URL and last-verified date.

## Architecture

- **Backend** — FastAPI (Python), `backend/`. Seed JSON loaded in memory behind a
  `ProgramRepository` interface (`app/repository.py`) so a real database can drop in later.
  - Layer 1: deterministic eligibility gate on structured fields (`app/matching.py`)
  - Layer 2: TF-IDF relevance ranking of the eligible set against `eligible_use` text
  - Results grouped into three urgency tiers: enrollment-deadline / rolling / invite-only
  - Blurbs: template per program (`app/blurbs.py`); if `ANTHROPIC_API_KEY` is set, a
    live-generated draft is attempted with the template as fallback
- **Frontend** — React (Vite), `frontend/`. Single page: questionnaire → results.
- No auth, no accounts, no persistence between sessions.

## Run it

Backend (port **8001** — 8000 is in use by another project on this machine):

```sh
cd backend
python3 -m venv .venv          # first time only
.venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Frontend (port 5173, proxies `/api` to 8001):

```sh
cd frontend
npm install                    # first time only
npm run dev
```

Then open http://localhost:5173

## API

- `GET /api/health` — status + program count
- `GET /api/programs` — raw seed programs
- `POST /api/match` — questionnaire answers → tiered matches (see `app/models.py`)
# grant-ready
