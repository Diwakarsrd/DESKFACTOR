"""Thin provider-agnostic LLM client (Groq, Gemini or Anthropic) over plain HTTP."""
import base64
import json
import re
import time

import httpx

from . import config

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
RETRY_STATUSES = {429, 500, 502, 503, 504}


class LLMError(Exception):
    pass


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def complete(system: str, user: str, images: list[tuple[bytes, str]] | None = None,
             json_mode: bool = False, max_tokens: int = 4096) -> str:
    """images: list of (bytes, mime_type)."""
    images = images or []
    try:
        if config.LLM_PROVIDER == "groq":
            return _groq(system, user, images, json_mode, max_tokens)
        if config.LLM_PROVIDER == "anthropic":
            return _anthropic(system, user, images, max_tokens)
        return _gemini(system, user, images, json_mode, max_tokens)
    except httpx.TimeoutException as e:
        raise LLMError("The AI service timed out.") from e
    except httpx.HTTPError as e:
        raise LLMError(f"Could not reach the AI service: {e.__class__.__name__}") from e


def _post(url: str, headers: dict, body: dict, attempts: int = 3) -> httpx.Response:
    """POST with backoff on rate limits and transient server errors (honours Retry-After, capped)."""
    for i in range(attempts):
        r = httpx.post(url, headers=headers, json=body, timeout=90)
        if r.status_code not in RETRY_STATUSES or i == attempts - 1:
            return r
        try:
            wait = float(r.headers.get("retry-after", ""))
        except ValueError:
            wait = 2.0 * (i + 1)
        time.sleep(min(max(wait, 1.0), 20.0))
    return r


def _fail(r: httpx.Response):
    if r.status_code == 429:
        raise LLMError("The AI service is rate-limited right now. Please wait a minute and try again.")
    if r.status_code in (401, 403):
        raise LLMError("The AI service rejected the server's API key.")
    raise LLMError(f"AI service returned {r.status_code}: {r.text[:200]}")


def _groq(system, user, images, json_mode, max_tokens):
    if not config.GROQ_API_KEY:
        raise LLMError("GROQ_API_KEY is not configured on the server.")
    if images:
        # Vision models on Groq are most reliable with instructions inline next to the image.
        content = [{"type": "text", "text": f"{system}\n\n{user}"}]
        content += [{"type": "image_url", "image_url": {"url": f"data:{m};base64,{_b64(b)}"}} for b, m in images]
        messages = [{"role": "user", "content": content}]
        model = config.GROQ_VISION_MODEL
    else:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        model = config.GROQ_MODEL
    body = {"model": model, "messages": messages, "temperature": 0.1, "max_completion_tokens": max_tokens}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    r = _post(GROQ_URL, {"Authorization": f"Bearer {config.GROQ_API_KEY}"}, body)
    if r.status_code == 400 and "json_validate_failed" in r.text:
        # Groq rejects invalid JSON server-side; hand back what it generated so the caller's retry path runs.
        try:
            return r.json()["error"].get("failed_generation", "")
        except (ValueError, KeyError):
            return ""
    if r.status_code != 200:
        _fail(r)
    try:
        return r.json()["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError) as e:
        raise LLMError("AI service returned an empty response.") from e


def _anthropic(system, user, images, max_tokens):
    if not config.ANTHROPIC_API_KEY:
        raise LLMError("ANTHROPIC_API_KEY is not configured on the server.")
    content = [{"type": "image", "source": {"type": "base64", "media_type": m, "data": _b64(b)}} for b, m in images]
    content.append({"type": "text", "text": user})
    r = _post(
        "https://api.anthropic.com/v1/messages",
        {"x-api-key": config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        {"model": config.ANTHROPIC_MODEL, "max_tokens": max_tokens, "system": system,
         "messages": [{"role": "user", "content": content}]},
    )
    if r.status_code != 200:
        _fail(r)
    return "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")


def _gemini(system, user, images, json_mode, max_tokens):
    if not config.GEMINI_API_KEY:
        raise LLMError("GEMINI_API_KEY is not configured on the server.")
    parts = [{"inline_data": {"mime_type": m, "data": _b64(b)}} for b, m in images]
    parts.append({"text": user})
    gen = {"maxOutputTokens": max_tokens, "temperature": 0.1}
    if json_mode:
        gen["responseMimeType"] = "application/json"
    r = _post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{config.GEMINI_MODEL}:generateContent",
        {"x-goog-api-key": config.GEMINI_API_KEY},
        {"systemInstruction": {"parts": [{"text": system}]},
         "contents": [{"role": "user", "parts": parts}], "generationConfig": gen},
    )
    if r.status_code != 200:
        _fail(r)
    try:
        cand = r.json()["candidates"][0]
        return "".join(p.get("text", "") for p in cand["content"]["parts"])
    except (KeyError, IndexError) as e:
        raise LLMError("AI service returned an empty or blocked response.") from e


def parse_json(text: str) -> dict:
    """Tolerant JSON extraction: strips code fences and surrounding prose."""
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    return json.loads(t[start:end + 1])
