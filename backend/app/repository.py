"""
Repository layer: the only place that knows Odmantic/Mongo query syntax.
Routes and the queue worker call this, never AIOEngine directly — keeps the
persistence layer swappable and makes the query logic independently
testable (see tests/test_repository.py).
"""

from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from odmantic import AIOEngine

from .models import DocumentModel


class DocumentRepository:
    def __init__(self, engine: AIOEngine):
        self.engine = engine

    async def create(self, filename: str, content_hash: str) -> DocumentModel:
        doc = DocumentModel(filename=filename, content_hash=content_hash)
        await self.engine.save(doc)
        return doc

    async def get(self, doc_id: str) -> Optional[DocumentModel]:
        try:
            oid = ObjectId(doc_id)
        except InvalidId:
            return None
        return await self.engine.find_one(DocumentModel, DocumentModel.id == oid)

    async def find_by_hash(self, content_hash: str) -> Optional[DocumentModel]:
        return await self.engine.find_one(DocumentModel, DocumentModel.content_hash == content_hash)

    async def list_all(self) -> list[DocumentModel]:
        return await self.engine.find(DocumentModel, sort=DocumentModel.created_at.desc())

    async def list_done(self) -> list[DocumentModel]:
        return await self.engine.find(
            DocumentModel,
            DocumentModel.status == "done",
            sort=DocumentModel.created_at.desc(),
        )

    async def save(self, doc: DocumentModel) -> DocumentModel:
        await self.engine.save(doc)
        return doc
