"""
Persistence model (Odmantic, backed by AIOEngine/Motor) and the API-facing
DTOs. Kept separate on purpose: the DB shape is free to evolve (e.g. adding
fields, changing indexes) without breaking the API contract, and the API
response never accidentally leaks internal storage details.
"""

import time
from enum import Enum
from typing import Optional

from odmantic import Model, Field as ODField
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
    content_hash: str = ODField(index=True, unique=True)
    status: DocumentStatus = DocumentStatus.QUEUED
    created_at: float = ODField(default_factory=time.time)
    attempts: int = 0
    error: Optional[str] = None
    extracted: Optional[ExtractedFields] = None
    text_preview: Optional[str] = None

    model_config = {"collection": "documents"}


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
