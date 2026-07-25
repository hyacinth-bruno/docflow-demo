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

    async def create(self, filename: str, content_hash: str, session_id: str) -> DocumentModel:
        doc = DocumentModel(filename=filename, content_hash=content_hash, session_id=session_id)
        await self.engine.save(doc)
        return doc

    async def get(self, doc_id: str) -> Optional[DocumentModel]:
        """Unscoped by design — used internally by the queue worker
        (process_document, handle_dead_letter in main.py), which already
        knows the exact doc_id for the job it's processing and has no
        "current session" in scope. HTTP routes must use get_scoped()
        instead so one session can't look up another's document by id."""
        try:
            oid = ObjectId(doc_id)
        except InvalidId:
            return None
        return await self.engine.find_one(DocumentModel, DocumentModel.id == oid)

    async def get_scoped(self, doc_id: str, session_id: str) -> Optional[DocumentModel]:
        try:
            oid = ObjectId(doc_id)
        except InvalidId:
            return None
        return await self.engine.find_one(
            DocumentModel, DocumentModel.id == oid, DocumentModel.session_id == session_id
        )

    async def find_by_hash(self, session_id: str, content_hash: str) -> Optional[DocumentModel]:
        return await self.engine.find_one(
            DocumentModel,
            DocumentModel.session_id == session_id,
            DocumentModel.content_hash == content_hash,
        )

    async def list_all(self) -> list[DocumentModel]:
        return await self.engine.find(DocumentModel, sort=DocumentModel.created_at.desc())

    async def list_by_session(self, session_id: str) -> list[DocumentModel]:
        return await self.engine.find(
            DocumentModel,
            DocumentModel.session_id == session_id,
            sort=DocumentModel.created_at.desc(),
        )

    async def list_done(self) -> list[DocumentModel]:
        return await self.engine.find(
            DocumentModel,
            DocumentModel.status == "done",
            sort=DocumentModel.created_at.desc(),
        )

    async def list_done_by_session(self, session_id: str) -> list[DocumentModel]:
        return await self.engine.find(
            DocumentModel,
            DocumentModel.status == "done",
            DocumentModel.session_id == session_id,
            sort=DocumentModel.created_at.desc(),
        )

    async def save(self, doc: DocumentModel) -> DocumentModel:
        await self.engine.save(doc)
        return doc

    async def delete(self, doc: DocumentModel) -> None:
        await self.engine.delete(doc)

    async def delete_all(self) -> int:
        docs = await self.list_all()
        for doc in docs:
            await self.engine.delete(doc)
        return len(docs)

    async def delete_by_session(self, session_id: str) -> list[DocumentModel]:
        docs = await self.list_by_session(session_id)
        for doc in docs:
            await self.engine.delete(doc)
        return docs
