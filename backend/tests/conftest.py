import io
import os

# Must be set before `app.main` is imported anywhere, since build_engine()
# reads it at startup time.
os.environ["MONGODB_MOCK"] = "1"

# Tests assert exact heuristic-extractor output (see sample_pdf_bytes below),
# but extract_fields() switches to live Claude calls whenever
# ANTHROPIC_API_KEY is set — and db.py's load_dotenv() would otherwise leak a
# real key in from a developer's local .env, making the suite
# non-deterministic and dependent on a network call + API spend. Set (not
# pop) it to empty: load_dotenv() only fills in variables that are *absent*
# from os.environ, so an empty string here still blocks it from being
# repopulated once `app.main` (imported below) triggers db.py's load_dotenv().
os.environ["ANTHROPIC_API_KEY"] = ""

import asyncio

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from reportlab.pdfgen import canvas

# mongomock (and therefore mongomock-motor) doesn't implement sessions
# (https://github.com/mongomock/mongomock/issues/700), but Odmantic's
# save() always opens one internally. This is a test-only shim: a no-op,
# falsy async context manager stands in for a real session — mongomock's
# write methods guard with `if session: raise NotImplementedError(...)`,
# so a falsy-but-present object is treated the same as no session at all.
# Production code (real Motor client against Atlas) never goes through
# this path.
from mongomock_motor import AsyncMongoMockClient


class _NoopSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def __bool__(self):
        return False


async def _fake_start_session(self, *args, **kwargs):
    return _NoopSession()


AsyncMongoMockClient.start_session = _fake_start_session

from app.main import app


class _LifespanManager:
    """Minimal stand-in for asgi-lifespan's LifespanManager: runs FastAPI's
    startup/shutdown handlers manually so the background queue worker task
    is created on the same event loop the test coroutine runs on — the same
    thing a real ASGI server does when it boots the app."""

    def __init__(self, app):
        self.app = app

    async def __aenter__(self):
        self._ctx = self.app.router.lifespan_context(self.app)
        await self._ctx.__aenter__()
        return self

    async def __aexit__(self, *exc):
        await self._ctx.__aexit__(*exc)


@pytest_asyncio.fixture
async def client():
    async with _LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


@pytest.fixture
def sample_pdf_bytes() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(100, 750, "Vertrag zwischen Max Mustermann und NotarNow GmbH")
    c.drawString(100, 730, "Datum: 15.03.2026")
    c.drawString(100, 710, "Dieses Dokument regelt die Bedingungen der Zusammenarbeit.")
    c.save()
    return buf.getvalue()


async def wait_for_status(client, doc_id, status="done", timeout=5):
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        resp = await client.get(f"/documents/{doc_id}")
        if resp.json()["status"] == status:
            return resp.json()
        await asyncio.sleep(0.1)
    raise TimeoutError(f"document {doc_id} did not reach status={status} in {timeout}s")
