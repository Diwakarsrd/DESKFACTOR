import logging
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config, ingest, llm, pipeline
from .db import Analysis, SessionLocal, init_db

log = logging.getLogger("reviewer")
app = FastAPI(title="AI Clinical Document Reviewer", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def _startup():
    init_db()
    # Jobs run in-process, so anything still 'processing' at boot was interrupted by a restart.
    with SessionLocal() as s:
        s.query(Analysis).filter(Analysis.status == "processing").update({
            "status": "failed", "stage": "Failed", "completed_at": datetime.now(timezone.utc),
            "error": "Processing was interrupted by a server restart. Please submit the document again.",
        })
        s.commit()


def _iso(d):
    if not d:
        return None
    if d.tzinfo is None:  # SQLite drops tzinfo; values are stored as UTC
        d = d.replace(tzinfo=timezone.utc)
    return d.isoformat()


def _out(a: Analysis, full: bool) -> dict:
    d = {
        "id": a.id, "created_at": _iso(a.created_at), "completed_at": _iso(a.completed_at),
        "status": a.status, "stage": a.stage, "input_type": a.input_type, "filename": a.filename,
        "summary": a.summary, "warnings": a.warnings or [], "error": a.error,
    }
    if full:
        d["report"] = a.report
        d["source_preview"] = a.source_preview
    return d


def _update(aid: str, **fields):
    with SessionLocal() as s:
        a = s.get(Analysis, aid)
        for k, v in fields.items():
            setattr(a, k, v)
        s.commit()


def process(aid: str, kind: str, text: str | None, data: bytes | None):
    """Background job. Always ends in 'completed' or 'failed' with a user-readable message."""
    warnings: list[str] = []
    try:
        _update(aid, stage="Reading document")
        source = text if kind == "text" else ingest.extract_text(kind, data, warnings)
        _update(aid, source_preview=source[:1500])
        report = pipeline.build_report(source, warnings, on_stage=lambda st: _update(aid, stage=st))
        _update(aid, status="completed", stage="Done", summary=report.report_summary,
                report=report.model_dump(), warnings=warnings, completed_at=datetime.now(timezone.utc))
    except ingest.InputError as e:
        _update(aid, status="failed", stage="Failed", error=str(e), warnings=warnings, completed_at=datetime.now(timezone.utc))
    except llm.LLMError as e:
        _update(aid, status="failed", stage="Failed", error=f"AI processing failed: {e}", warnings=warnings,
                completed_at=datetime.now(timezone.utc))
    except Exception:  # last resort: never leave a report stuck in 'processing'
        log.exception("Unexpected pipeline failure")
        _update(aid, status="failed", stage="Failed", error="Something went wrong while processing this document. Please try again.",
                warnings=warnings, completed_at=datetime.now(timezone.utc))


@app.get("/api/health")
def health():
    return {"status": "ok", "provider": config.LLM_PROVIDER}


@app.post("/api/analyses", status_code=202)
async def create_analysis(background: BackgroundTasks, text: str | None = Form(None), file: UploadFile | None = File(None)):
    has_file = file is not None and bool(file.filename)
    has_text = bool((text or "").strip())
    if has_file and has_text:
        raise HTTPException(400, "Submit either text or a file, not both.")
    try:
        if has_file:
            data = await file.read()
            kind = ingest.validate_upload(data, file.filename)
            payload_text, name = None, file.filename[:255]
        else:
            payload_text = ingest.validate_text(text or "")
            data, kind, name = None, "text", None
    except ingest.InputError as e:
        raise HTTPException(400, str(e))
    with SessionLocal() as s:
        a = Analysis(input_type=kind, filename=name, status="processing", stage="Queued")
        s.add(a)
        s.commit()
        aid = a.id
    background.add_task(process, aid, kind, payload_text, data)
    return {"id": aid, "status": "processing"}


@app.get("/api/analyses")
def list_analyses(limit: int = 50):
    with SessionLocal() as s:
        rows = s.query(Analysis).order_by(Analysis.created_at.desc()).limit(min(limit, 100)).all()
        return [_out(r, full=False) for r in rows]


@app.get("/api/analyses/{aid}")
def get_analysis(aid: str):
    with SessionLocal() as s:
        a = s.get(Analysis, aid)
        if not a:
            raise HTTPException(404, "Report not found.")
        return _out(a, full=True)


@app.exception_handler(HTTPException)
async def _http_err(_, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)
