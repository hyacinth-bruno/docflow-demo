"""
Naive term-overlap search over extracted document fields.

Production equivalent: embed each document's extracted summary at write
time, store the vector (MongoDB Atlas Vector Search or pgvector), and rank
by cosine similarity against an embedded query. The scoring function below
is a placeholder with the same input/output shape as that would have, so
swapping it later doesn't touch any caller.
"""

import re


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zäöüß0-9]+", text.lower()))


def score_documents(query: str, documents: list) -> list[dict]:
    """documents: list[DocumentModel], already filtered to status == done."""
    query_tokens = _tokenize(query)
    results = []
    for doc in documents:
        if not doc.extracted:
            continue
        haystack = " ".join(
            [doc.extracted.summary, doc.extracted.document_type, *doc.extracted.parties]
        )
        doc_tokens = _tokenize(haystack)
        overlap = query_tokens & doc_tokens
        if not overlap:
            continue
        score = len(overlap) / max(len(query_tokens), 1)
        results.append(
            {
                "id": str(doc.id),
                "filename": doc.filename,
                "document_type": doc.extracted.document_type,
                "summary": doc.extracted.summary,
                "score": round(score, 3),
            }
        )
    return sorted(results, key=lambda r: r["score"], reverse=True)
