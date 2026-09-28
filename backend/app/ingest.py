"""Input validation and text extraction (typed PDF text layer, scan/handwriting via vision OCR)."""
import io

import pdfplumber
import pypdfium2 as pdfium
from PIL import Image, ImageOps

from . import config, llm

MAX_IMAGE_SIDE = 2000
MAX_IMAGE_BYTES = 3 * 1024 * 1024

TRANSCRIBE_SYSTEM = (
    "You are a careful medical-document transcriber. Transcribe ALL text visible in the image exactly as written, "
    "preserving line breaks, numbers, units and abbreviations. Never guess or correct clinical content. "
    "If a word or number is unreadable or uncertain, write [illegible] in its place. "
    "If the image contains no legible text, output exactly: [NO_TEXT]. Output only the transcription."
)


class InputError(Exception):
    """User-fixable problem with the submitted input."""


def sniff(data: bytes) -> str:
    if data[:5] == b"%PDF-":
        return "pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "unknown"


def validate_upload(data: bytes, filename: str | None) -> str:
    if not data:
        raise InputError("The uploaded file is empty.")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise InputError(f"File is larger than {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    kind = sniff(data)
    if kind == "unknown":
        raise InputError("Unsupported file type. Upload a PDF, PNG, JPG or WebP file.")
    if kind == "pdf":
        return "pdf"
    try:
        Image.open(io.BytesIO(data)).verify()
    except Exception as e:
        raise InputError("The image could not be read. It may be corrupted; try exporting it again.") from e
    return "image"


def validate_text(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise InputError("Please enter some clinical text or upload a file.")
    if len(text) < 20:
        raise InputError("The text is too short to analyse. Add more clinical detail.")
    if len(text) > config.MAX_TEXT_CHARS:
        raise InputError(f"Text is longer than {config.MAX_TEXT_CHARS:,} characters.")
    return text


def prepare_image(data: bytes) -> bytes:
    """Decode, fix phone-camera rotation, and shrink to a JPEG the vision API accepts (Groq caps base64 at 4 MB)."""
    try:
        img = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as e:
        raise InputError("The image could not be read. It may be corrupted; try exporting it again.") from e
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    for quality in (85, 70, 55):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        if buf.tell() <= MAX_IMAGE_BYTES:
            break
    return buf.getvalue()


def _transcribe_image(data: bytes) -> str:
    out = llm.complete(TRANSCRIBE_SYSTEM, "Transcribe this clinical document.", images=[(prepare_image(data), "image/jpeg")])
    return out.strip()


def _pdf_text_layer(data: bytes) -> tuple[str, int]:
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            n = len(pdf.pages)
            pages = [(p.extract_text() or "") for p in pdf.pages[: config.MAX_PDF_PAGES]]
        return "\n\n".join(pages).strip(), n
    except Exception as e:  # corrupt / encrypted
        raise InputError("The PDF could not be opened. It may be corrupted or password-protected.") from e


def _pdf_ocr(data: bytes) -> str:
    try:
        pdf = pdfium.PdfDocument(data)
    except Exception as e:
        raise InputError("The PDF could not be opened. It may be corrupted or password-protected.") from e
    out = []
    for i in range(min(len(pdf), config.MAX_PDF_PAGES)):
        img = pdf[i].render(scale=2).to_pil().convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        out.append(_transcribe_image(buf.getvalue()))
    return "\n\n".join(out)


def extract_text(kind: str, data: bytes, warnings: list[str]) -> str:
    """Return source text for the pipeline. Appends non-fatal issues to `warnings`."""
    if kind == "image":
        text = _transcribe_image(data)
    else:
        text, n_pages = _pdf_text_layer(data)
        if n_pages > config.MAX_PDF_PAGES:
            warnings.append(f"Only the first {config.MAX_PDF_PAGES} of {n_pages} pages were processed.")
        if len(text) < 40:  # scanned / image-only PDF
            warnings.append("No text layer found; pages were read with OCR, which may be less accurate.")
            text = _pdf_ocr(data)
    return assess_quality(text, warnings)


def assess_quality(text: str, warnings: list[str]) -> str:
    text = text.strip()
    if not text or text == "[NO_TEXT]":
        raise InputError("No readable text was found in the document. Try a clearer scan or paste the text.")
    words = text.split()
    bad = text.count("[illegible]")
    if len(words) < 8 or bad / max(len(words), 1) > 0.4:
        raise InputError("The document is too blurry or incomplete to read reliably. Upload a clearer copy.")
    if bad:
        warnings.append(f"{bad} unreadable section(s) were marked [illegible]; related fields may be incomplete.")
    return text
