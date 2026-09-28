# AI Clinical Document Reviewer

A deployed full-stack app that takes clinical documentation (typed text, a PDF, or a photo/scan, including handwriting), extracts the clinically relevant information, and produces a structured review with a concise **Report Summary**. Every extracted finding carries a quote from the source and a confidence level, and unsupported claims are removed automatically.

> **All data used in development and demos is synthetic.** This tool supports a reviewer; it does not provide diagnosis or treatment advice.

- **Live app:** `<ADD FRONTEND URL>`
- **API:** `<ADD BACKEND URL>` (health check: `/api/health`, docs: `/docs`)
- **Screenshots:** add to `docs/screenshots/` and link here

## Features
- Three input types: pasted text, image (PNG/JPG/WebP), PDF (typed or scanned)
- Report Summary first, then detailed sections: patient information, symptoms, diagnoses, medications, vitals, allergies, observations, concerns, missing information, potential inconsistencies, items requiring review
- Evidence quote and confidence (high/medium/low) on every finding
- Hallucination guard: findings whose quote is not in the source are removed and listed under "Needs review"
- Deterministic safety checks: vital-sign range flags, drug-allergy conflicts, completeness checks
- Persistent history with status, timestamp, summary and full report
- Loading state with live stage, and clear error messages for every failure mode

## Tech stack
| Layer | Choice |
|---|---|
| Frontend | React 18 + Vite, deployed on Vercel |
| Backend | FastAPI (Python 3.11+), Pydantic v2, deployed on Render |
| Database | PostgreSQL (Neon) in production, SQLite locally, via SQLAlchemy |
| PDF text | pdfplumber (text layer), pypdfium2 (page rendering for scanned PDFs) |
| AI | One vision-capable LLM behind a small provider interface: Groq, Gemini or Claude (env var) |

## Architecture
```mermaid
flowchart LR
  U[User browser] --> FE[React frontend - Vercel]
  FE -- REST / JSON --> API[FastAPI backend - Render]
  subgraph Backend
    API --> V[Validation: type, size, magic bytes]
    V --> DP[Document-processing layer]
    DP -->|typed PDF| PL[pdfplumber text layer]
    DP -->|scan / image| OCR[Vision transcription]
    DP -->|plain text| T[Pass-through]
    PL --> AI
    OCR --> AI
    T --> AI
    AI[AI layer: schema-constrained extraction] --> G[Grounding check]
    G --> R[Rule checks: vitals, allergy conflicts, completeness]
    R --> S[Summary from validated data]
    S --> DB[(PostgreSQL / SQLite)]
  end
  OCR -. HTTPS .-> LLM[External LLM API]
  AI -. HTTPS .-> LLM
  S -. HTTPS .-> LLM
  API --> DB
```
Flow: `Input -> Validation -> Document processing -> AI extraction -> Grounding -> Rule checks -> Summary -> Persistence -> Report`. Processing runs as a background task; the frontend polls `GET /api/analyses/{id}`.

## Repository structure
```
backend/app/   main.py (API), ingest.py (validation + text extraction), llm.py (provider client),
               pipeline.py (extract/ground/summarise), rules.py (deterministic checks), db.py, schemas.py, config.py
backend/tests/ pipeline + API tests with a mocked LLM
frontend/src/  App.jsx, api.js, components/{SubmitForm,History,ReportView}.jsx
docs/          AI_DESIGN.md, TECHNICAL_DECISIONS.md
samples/       synthetic test notes
render.yaml    backend deployment blueprint
```

## API
| Method | Path | Purpose |
|---|---|---|
| POST | `/api/analyses` | multipart form: `text` **or** `file`. Returns `202 {id, status}` |
| GET | `/api/analyses` | list previous analyses (summary, status, timestamps) |
| GET | `/api/analyses/{id}` | full report, status, stage, warnings, error |
| GET | `/api/health` | liveness |

Errors are `{"error": "<message>"}` with 400 (bad input), 404 (unknown id). Processing failures are stored as `status: failed` with a readable `error`.

## Configuration
Backend (`backend/.env.example`): `LLM_PROVIDER` (`groq`|`gemini`|`anthropic`), `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_VISION_MODEL`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `DATABASE_URL`, `CORS_ORIGINS`, `MAX_UPLOAD_MB`.
Frontend (`frontend/.env.example`): `VITE_API_URL`.

## Run locally
```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set your API key
export $(grep -v '^#' .env | xargs)
uvicorn app.main:app --reload --port 8000

# Frontend (new terminal)
cd frontend
npm install
cp .env.example .env
npm run dev            # http://localhost:5173

# Tests (LLM is mocked, no key needed)
cd backend && python -m pytest -q
```
**Database:** tables are created automatically on startup. Locally this creates `reviewer.db` (SQLite). For Postgres set `DATABASE_URL=postgresql://user:pass@host/db`.

## Deploy
1. **Neon:** create a project, copy the connection string.
2. **Render:** new Web Service from this repo (`render.yaml` is included). Set `GROQ_API_KEY`, `DATABASE_URL`, and `CORS_ORIGINS=<your Vercel URL>`; the blueprint defaults to `LLM_PROVIDER=groq`. If selecting another provider, set its matching API key and model variables instead.
3. **Vercel:** import the repo, root directory `frontend`, env `VITE_API_URL=<Render URL>`.

## Known limitations
- No authentication; anyone with the URL can see all reports. Acceptable only because data is synthetic.
- Background tasks run in-process; a server restart mid-analysis loses that job (it is marked `failed` with a "please resubmit" message on the next startup).
- Handwriting accuracy depends on the vision model; the system flags `[illegible]` rather than guessing but cannot guarantee correct transcription.
- Vital-sign ranges are adult defaults and ignore age, context and units beyond basic temperature conversion.
- The allergy-conflict list covers common drug classes only.
- Only the first 8 PDF pages are processed; English-language documents only.
- The free Render tier sleeps when idle, so the first request can be slow.
