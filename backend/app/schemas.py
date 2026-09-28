from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]


class Item(BaseModel):
    """One extracted fact, always tied to a quote from the source."""
    name: str
    detail: str = ""
    evidence: str = ""
    confidence: Confidence = "medium"


class Vital(BaseModel):
    name: str
    value: str
    unit: str = ""
    evidence: str = ""
    confidence: Confidence = "medium"
    flag: str = ""  # filled by rule checks, never by the LLM


class Inconsistency(BaseModel):
    description: str
    evidence: str = ""
    source: Literal["model", "rules"] = "model"


class Extraction(BaseModel):
    """What the LLM must return (schema-validated)."""
    patient_information: dict[str, str] = Field(default_factory=dict)
    symptoms: list[Item] = Field(default_factory=list)
    diagnoses: list[Item] = Field(default_factory=list)
    medications: list[Item] = Field(default_factory=list)
    vitals: list[Vital] = Field(default_factory=list)
    allergies: list[Item] = Field(default_factory=list)
    clinical_observations: list[Item] = Field(default_factory=list)
    clinical_concerns: list[Item] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    potential_inconsistencies: list[Inconsistency] = Field(default_factory=list)
    document_relevance_note: str = ""


class Report(Extraction):
    report_summary: str = ""
    requires_review: list[str] = Field(default_factory=list)
