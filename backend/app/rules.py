"""Deterministic checks. These never rely on the LLM, so they are auditable and repeatable."""
import re

from .schemas import Inconsistency, Report

# name -> (low, high, unit) adult reference ranges used only for *flagging*, not diagnosis.
RANGES = {
    "heart_rate": (50, 110, "bpm"),
    "resp_rate": (12, 24, "/min"),
    "spo2": (92, 100, "%"),
    "temperature_c": (36.0, 38.0, "°C"),
    "systolic": (90, 160, "mmHg"),
    "diastolic": (50, 100, "mmHg"),
}

# Allergy term -> drug names that should trigger a conflict warning.
CLASSES = {
    "penicillin": ["penicillin", "amoxicillin", "ampicillin", "piperacillin", "flucloxacillin", "augmentin", "amoxiclav"],
    "sulfa": ["sulfa", "sulfamethoxazole", "trimethoprim", "co-trimoxazole", "bactrim"],
    "nsaid": ["nsaid", "ibuprofen", "naproxen", "diclofenac", "aspirin", "ketorolac", "indomethacin"],
    "cephalosporin": ["cephalosporin", "cefuroxime", "ceftriaxone", "cefalexin", "cephalexin", "cefixime"],
    "macrolide": ["macrolide", "azithromycin", "clarithromycin", "erythromycin"],
    "opioid": ["opioid", "morphine", "codeine", "tramadol", "oxycodone", "fentanyl"],
}


def _num(s: str):
    m = re.search(r"-?\d+(?:\.\d+)?", s or "")
    return float(m.group()) if m else None


def _kind(name: str):
    n = name.lower()
    if "spo2" in n or "oxygen" in n or "saturation" in n:
        return "spo2"
    if "heart" in n or "pulse" in n or n.strip() in ("hr", "hr."):
        return "heart_rate"
    if "resp" in n or n.strip() in ("rr",):
        return "resp_rate"
    if "temp" in n:
        return "temperature_c"
    if "blood pressure" in n or n.strip() in ("bp",):
        return "bp"
    return None


def check_vitals(report: Report) -> None:
    for v in report.vitals:
        kind = _kind(v.name)
        if not kind:
            continue
        if kind == "bp":
            m = re.search(r"(\d{2,3})\s*/\s*(\d{2,3})", v.value)
            if not m:
                continue
            s, d = float(m.group(1)), float(m.group(2))
            flags = []
            if not RANGES["systolic"][0] <= s <= RANGES["systolic"][1]:
                flags.append("systolic outside typical range")
            if not RANGES["diastolic"][0] <= d <= RANGES["diastolic"][1]:
                flags.append("diastolic outside typical range")
            v.flag = "; ".join(flags)
            continue
        x = _num(v.value)
        if x is None:
            continue
        if kind == "temperature_c" and ("f" in v.unit.lower() or x > 45):
            x = (x - 32) * 5 / 9
        lo, hi, _ = RANGES[kind]
        if x < lo:
            v.flag = f"below typical range ({lo}-{hi})"
        elif x > hi:
            v.flag = f"above typical range ({lo}-{hi})"


def check_allergy_conflicts(report: Report) -> None:
    for a in report.allergies:
        terms = {a.name.lower()}
        for cls, drugs in CLASSES.items():
            if cls in a.name.lower() or any(d in a.name.lower() for d in drugs):
                terms.update(drugs)
        for m in report.medications:
            mname = m.name.lower()
            if any(t and t in mname for t in terms):
                report.potential_inconsistencies.append(Inconsistency(
                    description=f"Possible allergy conflict: '{m.name}' prescribed but allergy to '{a.name}' is documented.",
                    evidence=f"{m.evidence} | {a.evidence}".strip(" |"),
                    source="rules",
                ))


def check_completeness(report: Report) -> None:
    pi = {k.lower(): v for k, v in report.patient_information.items() if v}
    if not any(k in pi for k in ("name", "patient_name", "id", "mrn", "patient_id")):
        report.missing_information.append("No patient name or identifier found.")
    if "age" not in pi and "dob" not in pi and "date_of_birth" not in pi:
        report.missing_information.append("Patient age or date of birth not documented.")
    if not report.allergies:
        report.missing_information.append("Allergy status not documented (no allergies listed and no 'NKDA' statement).")
    if not report.vitals:
        report.missing_information.append("No vital signs documented.")
    if report.medications and not any(m.detail for m in report.medications):
        report.missing_information.append("Medications listed without dose or frequency.")


def run_all(report: Report) -> Report:
    check_vitals(report)
    check_allergy_conflicts(report)
    check_completeness(report)
    seen, uniq = set(), []
    for m in report.missing_information:
        if m.lower() not in seen:
            seen.add(m.lower())
            uniq.append(m)
    report.missing_information = uniq
    return report
