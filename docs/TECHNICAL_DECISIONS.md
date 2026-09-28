# Technical Decisions

## Choices and reasons
- **React + Vite (frontend):** small, fast to build and deploy as a static site, and the UI is a handful of components. Next.js would add server-side features the app does not need, since all logic lives in the API.
- **FastAPI (backend):** typed request/response handling, multipart uploads, background tasks and automatic `/docs` with little code. Pydantic is shared between validation of LLM output and API models.
- **PostgreSQL (Neon) / SQLite:** reports are relational records (status, timestamps, summary) with a JSON report column. SQLAlchemy lets the same code run on SQLite locally and Postgres in production. Neon's free tier survives redeploys, unlike Render's ephemeral disk.
- **LLM approach:** vision-capable LLM plus code-level validation, rather than a custom model, because no labelled clinical data is available and the requirement is broad input types. Provider is swappable via env var to avoid lock-in.

## Architecture decisions
- Strict frontend/backend separation: the frontend only calls REST endpoints.
- Asynchronous processing with polling: analyses can take 10-40 seconds and would exceed proxy timeouts if handled in one request. The `stage` field gives the user live progress.
- Every analysis is persisted immediately as `processing`, so failures are visible in history.
- Config through environment variables only; no secrets in the repo.

## Trade-offs
- In-process background tasks (FastAPI `BackgroundTasks`) instead of a queue: simple and adequate for a demo, but jobs are lost on restart.
- Dropping unsupported items favours precision over recall: a true finding with a paraphrased quote could be removed, but it is listed under "Needs review" so it is not silent.
- Vision transcription for PDFs without a text layer costs more calls; page count is capped at 8.
- No auth or multi-tenancy, to keep scope to the assignment.

## Known weaknesses
Handwriting accuracy is model-dependent; reference ranges are generic adult values; allergy mapping is a short list; grounding uses token overlap, which can accept a quote that is loosely matched; no PII redaction (synthetic data assumed); tests use a mocked LLM so real-model behaviour is verified manually with the samples.

## What I would improve next
Job queue (Redis/RQ) with retries; user auth and per-user history; age- and context-aware reference ranges; a fuller drug-interaction and allergy knowledge base (e.g. RxNorm); side-by-side view highlighting evidence in the source; evaluation set with labelled synthetic notes and precision/recall metrics; streaming progress; PII redaction and audit logging.
