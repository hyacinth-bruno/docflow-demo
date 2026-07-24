"""
DocFlow — async document processing pipeline demo.

Mirrors a production pattern of:
  upload -> object storage -> queue -> worker (extraction) -> DB -> search
  with real-time progress pushed to the client over SSE.

WHAT IS SIMULATED vs REAL in this demo (see README for the full mapping):
  - Object storage       -> local disk (uploads/) instead of S3
  - Queue + worker         -> in-process asyncio.Queue instead of SQS + Lambda
  - Database              -> REAL: MongoDB via Odmantic's AIOEngine (Motor
                             underneath). Point MONGODB_URI at an Atlas
                             cluster and this is exactly what runs in prod.
  - AI extraction         -> heuristic/regex extractor by default.
                             If ANTHROPIC_API_KEY is set, real Claude API
                             calls are used instead (see extraction.py).
  - Semantic search       -> naive term-overlap scoring instead of Atlas
                             Vector Search (documented upgrade path in README)
"""

import asyncio
import hashlib
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .db import build_engine
from .extraction import extract_fields
from .models import DocumentOut, DocumentStatus
from .queue_sim import JobResult, QueueSimulator
from .repository import DocumentRepository
from .search import score_documents

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = build_engine()
    app.state.engine = engine
    app.state.repository = DocumentRepository(engine)

    # Constructed here (not at module import time) so the QueueSimulator's
    # internal asyncio.Queue binds to *this* event loop. Creating it at
    # import time is a subtle bug: it silently binds to whatever loop
    # happens to exist first, which breaks under multiple app instances
    # (e.g. the test suite, or certain reload setups) with
    # "Queue is bound to a different event loop".
    app.state.queue = QueueSimulator(
        handler=process_document, max_attempts=3, on_dead_letter=handle_dead_letter
    )
    worker_task = asyncio.create_task(app.state.queue.run_worker())

    yield

    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


app = FastAPI(title="DocFlow Demo API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Per-document SSE event queues. In-memory by design — these are ephemeral
# progress notifications, not state that needs to survive a restart, so they
# don't belong in Mongo.
EVENT_QUEUES: dict[str, asyncio.Queue] = {}


async def push_event(doc_id: str, event: str, data: dict):
    q = EVENT_QUEUES.get(doc_id)
    if q:
        await q.put({"event": event, "data": data})


def get_repository(request: Request) -> DocumentRepository:
    return request.app.state.repository


def get_queue(request: Request) -> QueueSimulator:
    return request.app.state.queue


# --- The processing "Lambda handler" ---------------------------------------
async def process_document(doc_id: str) -> JobResult:
    """
    This is the unit of work a queue worker (SQS -> Lambda in production)
    would execute. Raising an exception here triggers the queue simulator's
    retry/backoff, and eventually its DLQ, exactly like SQS redrive policies.
    """
    repo: DocumentRepository = app.state.repository
    record = await repo.get(doc_id)
    if record is None:
        return JobResult(ok=False, error="document_not_found")

    record.status = DocumentStatus.PROCESSING
    record.attempts += 1
    await repo.save(record)
    await push_event(doc_id, "status", {"status": "processing"})

    try:
        file_path = UPLOAD_DIR / f"{doc_id}.pdf"
        text = _extract_text(file_path)
        record.text_preview = text[:400]
        await push_event(doc_id, "progress", {"step": "text_extracted", "chars": len(text)})

        await asyncio.sleep(0.3)  # simulate network latency to extraction service
        fields = await extract_fields(text)
        record.extracted = fields
        await push_event(doc_id, "progress", {"step": "fields_extracted"})

        record.status = DocumentStatus.DONE
        await repo.save(record)
        await push_event(doc_id, "status", {"status": "done"})
        return JobResult(ok=True)
    except Exception as e:
        record.error = str(e)
        await repo.save(record)
        raise


async def handle_dead_letter(doc_id: str, error: str) -> None:
    """Called once a job exhausts all retries and lands in the DLQ.

    Without this, a document that fails permanently just sits in `processing`
    forever from the frontend's point of view — the queue stops retrying but
    never tells anyone, so the SSE stream hangs instead of resolving.
    """
    repo: DocumentRepository = app.state.repository
    record = await repo.get(doc_id)
    if record is None:
        return
    record.status = DocumentStatus.FAILED
    record.error = error
    await repo.save(record)
    await push_event(doc_id, "status", {"status": "failed", "error": error})


def _extract_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as e:
        raise RuntimeError(f"pdf_text_extraction_failed: {e}")


@app.post("/documents", response_model=DocumentOut)
async def upload_document(
    file: UploadFile = File(...),
    repo: DocumentRepository = Depends(get_repository),
    queue: QueueSimulator = Depends(get_queue),
):
    if file.content_type != "application/pdf" and not file.filename.endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported in this demo")

    content = await file.read()
    content_hash = hashlib.sha256(content).hexdigest()

    # Idempotency: identical upload returns the existing document instead of
    # reprocessing it — the same principle used for idempotent SQS consumers,
    # now enforced with a unique index in Mongo rather than an in-process set.
    # Exception: a FAILED record is *not* replayed as-is — without this, a
    # permanently failed job could never be retried by re-uploading the same
    # file, even after the bug that caused the failure is fixed. Reset it and
    # re-enqueue instead, using a fresh idempotency key so the queue
    # simulator's own in-process dedup (which never forgets a key) doesn't
    # silently drop the retry.
    existing = await repo.find_by_hash(content_hash)
    if existing and existing.status != DocumentStatus.FAILED:
        return DocumentOut.from_model(existing)

    if existing:
        existing.status = DocumentStatus.QUEUED
        existing.error = None
        existing.attempts = 0
        existing.extracted = None
        await repo.save(existing)
        doc_id = str(existing.id)
        (UPLOAD_DIR / f"{doc_id}.pdf").write_bytes(content)
        EVENT_QUEUES[doc_id] = asyncio.Queue()
        await queue.enqueue(doc_id, idempotency_key=f"{content_hash}:retry:{time.time()}")
        return DocumentOut.from_model(existing)

    record = await repo.create(filename=file.filename, content_hash=content_hash)
    doc_id = str(record.id)
    (UPLOAD_DIR / f"{doc_id}.pdf").write_bytes(content)
    EVENT_QUEUES[doc_id] = asyncio.Queue()

    await queue.enqueue(doc_id, idempotency_key=content_hash)
    return DocumentOut.from_model(record)


@app.get("/documents/{doc_id}", response_model=DocumentOut)
async def get_document(doc_id: str, repo: DocumentRepository = Depends(get_repository)):
    record = await repo.get(doc_id)
    if record is None:
        raise HTTPException(404, "Document not found")
    return DocumentOut.from_model(record)


@app.get("/documents")
async def list_documents(repo: DocumentRepository = Depends(get_repository)):
    records = await repo.list_all()
    return [DocumentOut.from_model(r) for r in records]


@app.get("/documents/{doc_id}/events")
async def document_events(doc_id: str, repo: DocumentRepository = Depends(get_repository)):
    record = await repo.get(doc_id)
    if record is None:
        raise HTTPException(404, "Document not found")

    async def event_stream():
        # Replay current status immediately so a late-connecting client
        # (e.g. page refresh) isn't stuck waiting for the next event.
        yield f"event: status\ndata: {DocumentOut.from_model(record).model_dump_json()}\n\n"
        if record.status in (DocumentStatus.DONE, DocumentStatus.FAILED):
            return

        q = EVENT_QUEUES.setdefault(doc_id, asyncio.Queue())
        while True:
            item = await q.get()
            yield f"event: {item['event']}\ndata: {_to_json(item['data'])}\n\n"
            if item["event"] == "status" and item["data"].get("status") in ("done", "failed"):
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/search")
async def search(q: str, repo: DocumentRepository = Depends(get_repository)):
    docs = await repo.list_done()
    return score_documents(q, docs)


@app.get("/admin/dlq")
async def dead_letter_queue(queue: QueueSimulator = Depends(get_queue)):
    """Inspect jobs that exhausted retries — mirrors an SQS DLQ view."""
    return queue.dlq


def _to_json(data: dict) -> str:
    import json
    return json.dumps(data)
