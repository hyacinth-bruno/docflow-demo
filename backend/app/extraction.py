"""
Extraction adapter. This is the seam where a real OCR/AI provider plugs in
(Azure Document Intelligence, Textract, or a multimodal LLM call), matching
the "extraction into typed Pydantic models" requirement.

Behaviour:
  - If ANTHROPIC_API_KEY is set in the environment, this calls the real
    Claude API and asks it to return the fields as JSON, which is then
    parsed straight into the Pydantic model below (fail-closed: a parse
    error surfaces as a normal job failure, so it goes through the same
    retry/DLQ path as any other extraction error).
  - Otherwise, it falls back to a deterministic heuristic extractor so the
    demo runs end-to-end with no external dependency.

In both cases the output type is identical, which is the point: the rest of
the pipeline never needs to know which extractor produced the data.
"""

import json
import os
import re

from .models import ExtractedFields


async def extract_fields(text: str) -> ExtractedFields:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return await _extract_with_claude(text)
    return _extract_heuristic(text)


def _extract_heuristic(text: str) -> ExtractedFields:
    date_pattern = re.compile(r"\b\d{1,2}[./]\d{1,2}[./]\d{2,4}\b")
    dates = date_pattern.findall(text)[:5]

    doc_type = "unknown"
    lowered = text.lower()
    for candidate in ["vertrag", "contract", "invoice", "rechnung", "notariell", "certificate"]:
        if candidate in lowered:
            doc_type = candidate
            break

    summary = " ".join(text.split()[:40]) or "No extractable text found"

    return ExtractedFields(
        document_type=doc_type,
        key_dates=dates,
        parties=[],
        summary=summary,
        confidence=0.4,  # heuristic extraction is deliberately low-confidence
    )


async def _extract_with_claude(text: str) -> ExtractedFields:
    import httpx

    schema_hint = (
        "Return ONLY valid JSON matching this shape, no prose, no markdown: "
        '{"document_type": string, "key_dates": string[], "parties": string[], '
        '"summary": string, "confidence": number between 0 and 1}'
    )
    prompt = f"{schema_hint}\n\nDocument text:\n{text[:50000]}"

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": os.environ["ANTHROPIC_API_KEY"],
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-5",
                "max_tokens": 1500,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        raw = "".join(
            block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text"
        )
        data = json.loads(_strip_markdown_fence(raw))
        return ExtractedFields(**data)


def _strip_markdown_fence(raw: str) -> str:
    # Claude sometimes wraps JSON in ```json ... ``` despite being asked for
    # raw JSON only. Strip the fence rather than relying on the model to
    # always comply.
    stripped = raw.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\n?", "", stripped)
        stripped = re.sub(r"\n?```$", "", stripped)
    return stripped.strip()
