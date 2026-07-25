"""
Chat/Q&A over already-processed documents — a lightweight RAG.

Retrieval is deliberately *not* new: it reuses search.py's score_documents(),
the same naive term-overlap function already standing in for real Atlas
Vector Search. That means whenever search.py is upgraded to real vector
search, this module's answers improve for free, with zero changes here —
the retrieval seam is the whole point (see search.py's own docstring).

The caller (main.py) is responsible for the "no API key" short-circuit and
for building/budget-trimming context_docs before calling this; this module
assumes a key is present and just makes the one Claude call, the same
assumption _extract_with_claude in extraction.py already makes. Unlike
extraction.py, the response here is plain prose, not structured JSON, so
none of that module's markdown-fence-stripping is needed.
"""

import os


async def answer_question(query: str, context_docs: list[tuple[str, str, str]]) -> str:
    """context_docs: (filename, document_type, text) tuples, already
    budget-trimmed by the caller."""
    import httpx

    excerpts = "\n\n".join(
        f"--- {filename} ({document_type}) ---\n{text}"
        for filename, document_type, text in context_docs
    )
    prompt = (
        "Answer the question using ONLY the document excerpts below. "
        "If the answer isn't contained in them, say so explicitly rather than guessing. "
        "Be concise.\n\n"
        f"Question: {query}\n\n"
        f"Document excerpts:\n{excerpts}"
    )

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
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        return "".join(
            block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text"
        ).strip()
