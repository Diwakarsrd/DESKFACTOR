import json
import os

os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from fastapi.testclient import TestClient

from app import ingest, llm, pipeline, rules
from app.main import app
from app.schemas import Item, Report, Vital

NOTE = ("Patient: Jane Roe, 54F. Allergies: Penicillin (rash). Vitals: BP 182/110, HR 118, SpO2 90%. "
        "Meds: Amoxicillin 500 mg TID. Complaint: chest pain since yesterday. Dx: hypertension.")

FAKE = {
    "patient_information": {"name": "Jane Roe", "age": "54", "sex": "F"},
    "symptoms": [{"name": "chest pain", "detail": "since yesterday", "evidence": "chest pain since yesterday", "confidence": "high"}],
    "diagnoses": [{"name": "hypertension", "evidence": "Dx: hypertension", "confidence": "high"},
                  {"name": "diabetes", "evidence": "history of diabetes mellitus", "confidence": "high"}],
    "medications": [{"name": "Amoxicillin", "detail": "500 mg TID", "evidence": "Amoxicillin 500 mg TID", "confidence": "high"}],
    "allergies": [{"name": "Penicillin", "detail": "rash", "evidence": "Allergies: Penicillin (rash)", "confidence": "high"}],
    "vitals": [{"name": "Blood pressure", "value": "182/110", "unit": "mmHg", "evidence": "BP 182/110", "confidence": "high"},
               {"name": "SpO2", "value": "90", "unit": "%", "evidence": "SpO2 90%", "confidence": "high"}],
}


def fake_complete(system, user, images=None, json_mode=False, max_tokens=0):
    return json.dumps(FAKE) if json_mode else "Summary of the case. " * 5


def test_grounding_drops_hallucination(monkeypatch):
    monkeypatch.setattr(llm, "complete", fake_complete)
    r = pipeline.build_report(NOTE, [])
    assert [d.name for d in r.diagnoses] == ["hypertension"]  # "diabetes" removed
    assert any("diabetes" in x for x in r.requires_review)


def test_rules_flag_vitals_and_allergy_conflict(monkeypatch):
    monkeypatch.setattr(llm, "complete", fake_complete)
    r = pipeline.build_report(NOTE, [])
    assert any(v.flag for v in r.vitals)
    assert any(i.source == "rules" and "allergy" in i.description.lower() for i in r.potential_inconsistencies)


def test_malformed_json_retries_then_fails(monkeypatch):
    monkeypatch.setattr(llm, "complete", lambda *a, **k: "not json")
    try:
        pipeline.extract(NOTE)
        assert False
    except llm.LLMError:
        pass


def test_input_validation():
    for bad in ["", "short"]:
        try:
            ingest.validate_text(bad)
            assert False
        except ingest.InputError:
            pass
    try:
        ingest.validate_upload(b"hello world", "x.exe")
        assert False
    except ingest.InputError:
        pass


def test_api_end_to_end(monkeypatch):
    monkeypatch.setattr(llm, "complete", fake_complete)
    with TestClient(app) as c:
        assert c.post("/api/analyses", data={"text": ""}).status_code == 400
        r = c.post("/api/analyses", data={"text": NOTE})
        assert r.status_code == 202
        got = c.get(f"/api/analyses/{r.json()['id']}").json()
        assert got["status"] == "completed" and got["summary"] and got["report"]["diagnoses"]
        assert len(c.get("/api/analyses").json()) >= 1
        assert c.get("/api/analyses/nope").status_code == 404
