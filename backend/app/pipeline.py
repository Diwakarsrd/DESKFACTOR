"""Extraction -> grounding -> rule checks -> summary. Every stage degrades safely."""
import json
import re
from typing import Callable

from pydantic import ValidationError

from . import llm, rules
from .schemas import Extraction, Report

EXTRACT_SYSTEM = """You extract structured data from a clinical document for a reviewing clinician.
Rules:
- Use ONLY information explicitly present in the document. Never infer diagnoses, doses or values.
- For every item include "evidence": a SHORT verbatim quote (max ~15 words) copied exactly from the document.
- "confidence": high = clearly stated; medium = partly ambiguous; low = uncertain/illegible/abbreviated. Text marked [illegible] must be low or omitted.
- Record "no known drug allergies"/NKDA as an allergies item named "No known drug allergies".
- If the document is not clinical or partly irrelevant, extract only clinical content and describe the irrelevance in "document_relevance_note".
- List things a reviewer would expect but are absent under "missing_information" (short strings).
- List contradictions within the document under "potential_inconsistencies" (with evidence quotes), e.g. conflicting dates, values, or a symptom that contradicts a stated finding.
- "clinical_concerns" are issues stated or clearly implied by documented findings (e.g. documented fever with tachycardia); do not add new diagnoses.
Return ONLY one JSON object with keys:
patient_information (object of string->string, e.g. name, age, sex, mrn, dob, visit_date, clinician),
symptoms, diagnoses, medications, allergies, clinical_observations, clinical_concerns
 (each a list of {name, detail, evidence, confidence}; for medications put dose/route/frequency in detail),
vitals (list of {name, value, unit, evidence, confidence}),
missing_information (list of strings),
potential_inconsistencies (list of {description, evidence}),
document_relevance_note (string, may be empty)."""

SUMMARY_SYSTEM = """You write the 'Report Summary' for a clinician reviewing a document quickly.
Use ONLY the structured JSON provided. Do not add facts. 4-7 sentences of plain prose, no markdown, covering where applicable:
primary concerns, key symptoms/findings, diagnoses, relevant medications, significant vitals (mention flagged ones),
important missing information, inconsistencies, and what needs review. Be concise and neutral. Do not give treatment advice."""


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9/.%°]+", " ", s.lower()).strip()


def is_grounded(evidence: str, source_norm: str, source_tokens: set[str]) -> bool:
    ev = _norm(evidence)
    if not ev:
        return False
    if ev in source_norm:
        return True
    toks = [t for t in ev.split() if t]
    if not toks:
        return False
    return sum(t in source_tokens for t in toks) / len(toks) >= 0.85  # tolerant to OCR/whitespace noise


def extract(source: str) -> Extraction:
    """LLM extraction with one retry on malformed/invalid output."""
    prompt = f"Document:\n<<<\n{source}\n>>>"
    last_err = ""
    for attempt in range(2):
        user = prompt if not last_err else f"{prompt}\n\nYour previous reply was invalid ({last_err}). Return only valid JSON matching the schema."
        raw = llm.complete(EXTRACT_SYSTEM, user, json_mode=True, max_tokens=6000)
        try:
            return Extraction.model_validate(llm.parse_json(raw))
        except (ValueError, ValidationError) as e:
            last_err = str(e)[:200]
    raise llm.LLMError("The AI returned a malformed report twice. Please try again.")


def ground(ex: Extraction, source: str) -> tuple[Extraction, list[str]]:
    """Drop items whose evidence quote cannot be found in the source; report what was removed."""
    src_norm = _norm(source)
    src_tokens = set(src_norm.split())
    removed: list[str] = []
    for field in ("symptoms", "diagnoses", "medications", "allergies", "clinical_observations", "clinical_concerns", "vitals"):
        kept = []
        for it in getattr(ex, field):
            if is_grounded(it.evidence, src_norm, src_tokens):
                kept.append(it)
            else:
                removed.append(f"Removed unsupported {field.replace('_', ' ')} item: '{it.name}' (no matching text in the document).")
        setattr(ex, field, kept)
    keep_inc = []
    for inc in ex.potential_inconsistencies:
        if inc.evidence and is_grounded(inc.evidence, src_norm, src_tokens):
            keep_inc.append(inc)
        else:
            removed.append(f"Dropped an unverified inconsistency claim: '{inc.description[:80]}'.")
    ex.potential_inconsistencies = keep_inc
    return ex, removed


def build_requires_review(r: Report, removed: list[str], warnings: list[str]) -> list[str]:
    out = []
    for field in ("symptoms", "diagnoses", "medications", "allergies", "clinical_observations", "vitals"):
        for it in getattr(r, field):
            if it.confidence == "low":
                out.append(f"Low-confidence {field[:-1] if field != 'clinical_observations' else 'observation'}: {it.name}")
    out += [f"Vital sign flagged: {v.name} {v.value}{v.unit and ' ' + v.unit} - {v.flag}" for v in r.vitals if v.flag]
    out += [f"Check: {i.description}" for i in r.potential_inconsistencies]
    out += removed
    out += warnings
    if r.document_relevance_note:
        out.append(f"Document note: {r.document_relevance_note}")
    return out


def fallback_summary(r: Report) -> str:
    parts = []
    if r.diagnoses:
        parts.append("Diagnoses mentioned: " + ", ".join(d.name for d in r.diagnoses) + ".")
    if r.symptoms:
        parts.append("Symptoms: " + ", ".join(s.name for s in r.symptoms) + ".")
    if r.medications:
        parts.append("Medications: " + ", ".join(m.name for m in r.medications) + ".")
    flagged = [v for v in r.vitals if v.flag]
    if flagged:
        parts.append("Flagged vitals: " + ", ".join(f"{v.name} {v.value}" for v in flagged) + ".")
    if r.missing_information:
        parts.append(f"{len(r.missing_information)} item(s) of information are missing.")
    if r.potential_inconsistencies:
        parts.append(f"{len(r.potential_inconsistencies)} potential inconsistency(ies) need review.")
    return " ".join(parts) or "The document contained little extractable clinical information."


def summarize(r: Report) -> str:
    """Summary is generated from validated structured data only, never from the raw document."""
    data = json.dumps(r.model_dump(exclude={"report_summary"}), ensure_ascii=False)
    try:
        text = llm.complete(SUMMARY_SYSTEM, f"Structured data:\n{data}", max_tokens=700).strip()
        return text if len(text) > 40 else fallback_summary(r)
    except llm.LLMError:
        return fallback_summary(r)


def build_report(source: str, warnings: list[str], on_stage: Callable[[str], None] = lambda s: None) -> Report:
    on_stage("Extracting clinical information")
    ex = extract(source)
    on_stage("Verifying against source text")
    ex, removed = ground(ex, source)
    report = Report(**ex.model_dump())
    on_stage("Running safety checks")
    rules.run_all(report)
    report.requires_review = build_requires_review(report, removed, warnings)
    on_stage("Writing summary")
    report.report_summary = summarize(report)
    return report
