import pytest

from .conftest import wait_for_status

pytestmark = pytest.mark.asyncio

SESSION_B = {"X-Session-Id": "session-b"}


async def test_missing_session_id_returns_400(client):
    resp = await client.get("/documents", headers={"X-Session-Id": ""})
    assert resp.status_code == 400


async def test_other_session_cannot_list_document(client, sample_pdf_bytes):
    await client.post(
        "/documents", files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
    )

    own = (await client.get("/documents")).json()
    other = (await client.get("/documents", headers=SESSION_B)).json()
    assert len(own) == 1
    assert other == []


async def test_other_session_gets_404_for_direct_lookup(client, sample_pdf_bytes):
    doc = (
        await client.post(
            "/documents", files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        )
    ).json()

    resp = await client.get(f"/documents/{doc['id']}", headers=SESSION_B)
    assert resp.status_code == 404


async def test_search_and_chat_are_session_scoped(client, sample_pdf_bytes):
    doc = (
        await client.post(
            "/documents", files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        )
    ).json()
    await wait_for_status(client, doc["id"])

    own_results = (await client.get("/search", params={"q": "Vertrag"})).json()
    other_results = (
        await client.get("/search", params={"q": "Vertrag"}, headers=SESSION_B)
    ).json()
    assert any(r["id"] == doc["id"] for r in own_results)
    assert other_results == []

    other_chat = (
        await client.post("/chat", json={"query": "Vertrag"}, headers=SESSION_B)
    ).json()
    assert other_chat["sources"] == []


async def test_bulk_delete_only_clears_caller_session(client, sample_pdf_bytes):
    doc = (
        await client.post(
            "/documents", files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        )
    ).json()

    await client.delete("/documents", headers=SESSION_B)

    resp = await client.get(f"/documents/{doc['id']}")
    assert resp.status_code == 200


async def test_identical_content_across_sessions_both_process(client, sample_pdf_bytes):
    # Regression test: without namespacing the queue's idempotency key by
    # session_id, the second session's upload would silently never get
    # enqueued (the bare content_hash key was already consumed by the first
    # session) and would sit at "queued" forever.
    own_doc = (
        await client.post(
            "/documents", files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")}
        )
    ).json()
    other_doc = (
        await client.post(
            "/documents",
            files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")},
            headers=SESSION_B,
        )
    ).json()

    assert own_doc["id"] != other_doc["id"]

    own_done = await wait_for_status(client, own_doc["id"])
    other_done = await wait_for_status(client, other_doc["id"], headers=SESSION_B)
    assert own_done["status"] == "done"
    assert other_done["status"] == "done"
