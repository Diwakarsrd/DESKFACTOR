# AI/ML Design

## Models and services
One vision-capable LLM (Gemini or Claude, selected by `LLM_PROVIDER`) is called over HTTPS for three jobs: (1) transcribing images and scanned PDF pages, (2) schema-constrained information extraction, (3) writing the summary. `pdfplumber` reads PDF text layers and `pypdfium2` renders pages to images. No model is trained or fine-tuned; the design is prompt- and validation-driven.

## How a document is processed
1. **Validate.** Empty or too-short text, oversized input (text 20k chars, file 10 MB), and unsupported types are rejected before any AI call. File type is checked by magic bytes, not by extension.
2. **Get source text.**
   - Text: used as-is.
   - PDF: `pdfplumber` text layer first. If fewer than 40 characters come back, the PDF is treated as scanned: up to 8 pages are rendered and transcribed by the vision model.
   - Image: transcribed by the vision model with a strict prompt: copy exactly, never correct clinical content, write `[illegible]` for anything uncertain, output `[NO_TEXT]` if nothing is readable.
3. **Quality gate.** No text, `[NO_TEXT]`, fewer than 8 words, or more than 40% `[illegible]` tokens stops the pipeline with a clear message asking for a clearer copy. Some `[illegible]` tokens add a warning instead.

## How information is extracted
The transcript (never the raw file) goes to the LLM with a system prompt that requires: use only explicit information, no inferred diagnoses or doses, and for **every** item a short verbatim `evidence` quote plus a `confidence` level. Gemini is run in JSON mode; both providers get a schema description in the prompt. Output is parsed tolerantly (code fences and surrounding prose stripped) and validated with Pydantic (`Extraction`). Patient information is a free key-value map, since documents vary.

## How the report is generated
1. **Grounding check (code).** Each item's evidence must appear in the source text (normalised substring match, or at least 85% token overlap to tolerate OCR and whitespace noise). Items that fail are removed and recorded in "Needs review". Inconsistency claims from the model need a verifiable quote too.
2. **Rule checks (code, no LLM).**
   - Vital signs vs adult reference ranges (HR, RR, SpO2, temperature with F to C conversion, BP), which sets a `flag`.
   - Drug-allergy conflicts using names and common class mappings (penicillins, sulfa, NSAIDs, cephalosporins, macrolides, opioids).
   - Completeness: patient identifier, age/DOB, allergy status, vitals, dose/frequency on medications.
3. **Requires-review list** is assembled from low-confidence items, flagged vitals, inconsistencies, removed items, OCR warnings and any irrelevant-content note.
4. **Report Summary.** A second LLM call receives only the validated structured JSON (not the document), so it cannot introduce facts that failed grounding. If that call fails, a deterministic template summary is used instead.

## Structured output
Pydantic models (`schemas.py`) define the contract: `Item`, `Vital`, `Inconsistency`, `Extraction` (LLM output), `Report` (adds `report_summary`, `requires_review`). The stored JSON is exactly `Report.model_dump()`, and the frontend renders it into sections rather than showing raw output.

## Missing, uncertain and irrelevant information
- Missing: the model lists expected-but-absent items, and code adds its own completeness checks. Both are shown under "Missing or incomplete information".
- Uncertain: confidence levels are shown per item, low confidence is repeated in "Needs review", and `[illegible]` spans are never guessed.
- Irrelevant: the model is told to extract only clinical content and describe other content in `document_relevance_note` (the sample with cafeteria text exercises this).
- Inconsistent: model-detected contradictions (with quotes) plus rule-detected allergy conflicts, labelled by source.

## Reducing incorrect or unsupported output
Evidence-required schema, code-level grounding, low temperature (0.1), "use only what is written" instructions, deterministic rules for safety-relevant checks, summary from validated data only, and no treatment advice.

## Failure handling
| Failure | Behaviour |
|---|---|
| Malformed / schema-invalid JSON | One retry with the validation error appended, then `failed` with a readable message |
| LLM timeout, HTTP error, blocked or empty response | `failed`, "AI processing failed: ..." |
| Summary call fails | Deterministic fallback summary, report still completes |
| Corrupt or password-protected PDF | 400-style `failed` message naming the cause |
| Unreadable image | Quality gate message |
| Any unexpected exception | Caught, logged, stored as `failed`; a report is never left stuck in `processing` |

## Key design decisions
- **Vision LLM instead of a separate OCR engine.** One integration handles print, scans and handwriting, and can be told to mark uncertainty. Trade-off: cost, latency, and no per-character confidence.
- **Two-step (transcribe, then extract).** Grounding needs a text source to check against, and the transcript is shown to the user for auditability.
- **Grounding in code, not in the prompt.** Prompts reduce hallucination; only code can guarantee an unsupported item is removed.
- **Rules for safety checks.** Deterministic, testable and explainable, unlike asking the model to notice conflicts.
