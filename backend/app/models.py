"""
Persistence model (Odmantic, backed by AIOEngine/Motor) and the API-facing
DTOs. Kept separate on purpose: the DB shape is free to evolve (e.g. adding
fields, changing indexes) without breaking the API contract, and the API
response never accidentally leaks internal storage details.
"""

import time
from enum import Enum
from typing import Optional

from odmantic import Index, Model, Field as ODField
from pydantic import BaseModel


class DocumentStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class ExtractedFields(BaseModel):
    document_type: str
    key_dates: list[str] = []
    parties: list[str] = []
    summary: str
    confidence: float


class DocumentModel(Model):
    """Odmantic document — the source of truth in MongoDB."""

    filename: str
    content_hash: str = ODField(index=True)
    # No auth in this demo — session_id is a client-generated anonymous
    # identity (see frontend/lib/api.ts), not a real user account. Optional
    # with a None default so any pre-migration document without one still
    # hydrates cleanly instead of raising a validation error.
    session_id: Optional[str] = ODField(index=True, default=None)
    status: DocumentStatus = DocumentStatus.QUEUED
    created_at: float = ODField(default_factory=time.time)
    attempts: int = 0
    error: Optional[str] = None
    extracted: Optional[ExtractedFields] = None
    text_preview: Optional[str] = None

    model_config = {
        "collection": "documents",
        # Idempotency (see upload_document) is scoped per-session, not
        # global, so the uniqueness constraint has to be on the pair, not
        # content_hash alone.
        "indexes": lambda: [
            Index(
                DocumentModel.session_id,
                DocumentModel.content_hash,
                unique=True,
                name="session_content_hash_unique",
            )
        ],
    }


class ChatRequest(BaseModel):
    query: str


class ChatSource(BaseModel):
    id: str
    filename: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[ChatSource]


class DocumentOut(BaseModel):
    """API response shape. `id` is the stringified ObjectId."""

    id: str
    filename: str
    status: DocumentStatus
    created_at: float
    attempts: int
    error: Optional[str] = None
    extracted: Optional[ExtractedFields] = None
    text_preview: Optional[str] = None

    @classmethod
    def from_model(cls, doc: DocumentModel) -> "DocumentOut":
        return cls(
            id=str(doc.id),
            filename=doc.filename,
            status=doc.status,
            created_at=doc.created_at,
            attempts=doc.attempts,
            error=doc.error,
            extracted=doc.extracted,
            text_preview=doc.text_preview,
        )
