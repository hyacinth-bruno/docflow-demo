import pytest

from .conftest import wait_for_status

pytestmark = pytest.mark.asyncio


async def test_upload_and_process_persists_to_mongo(client, sample_pdf_bytes):
    resp = await client.post(
        "/documents",
        files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")},
    )
    assert resp.status_code == 200
    doc = resp.json()
    assert doc["status"] == "queued"
    assert doc["filename"] == "test.pdf"

    done = await wait_for_status(client, doc["id"])
    assert done["status"] == "done"
    assert done["extracted"]["document_type"] == "vertrag"
    assert "15.03.2026" in done["extracted"]["key_dates"]

    # Confirm it's actually readable back from the repository/Mongo layer,
    # not just held in a request-scoped variable.
    listed = (await client.get("/documents")).json()
    assert any(d["id"] == doc["id"] for d in listed)


async def test_duplicate_upload_is_idempotent(client, sample_pdf_bytes):
    first = (
        await client.post(
            "/documents",
            files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")},
        )
    ).json()
    second = (
        await client.post(
            "/documents",
            files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")},
        )
    ).json()
    assert first["id"] == second["id"]

    all_docs = (await client.get("/documents")).json()
    matching = [d for d in all_docs if d["filename"] == "test.pdf"]
    assert len(matching) == 1


async def test_search_finds_processed_document(client, sample_pdf_bytes):
    doc = (
        await client.post(
            "/documents",
            files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")},
        )
    ).json()
    await wait_for_status(client, doc["id"])

    results = (await client.get("/search", params={"q": "Vertrag"})).json()
    assert any(r["id"] == doc["id"] for r in results)


async def test_search_no_match_returns_empty(client, sample_pdf_bytes):
    doc = (
        await client.post(
            "/documents",
            files={"file": ("test.pdf", sample_pdf_bytes, "application/pdf")},
        )
    ).json()
    await wait_for_status(client, doc["id"])

    results = (await client.get("/search", params={"q": "zzzznomatch"})).json()
    assert results == []


async def test_get_nonexistent_document_returns_404(client):
    resp = await client.get("/documents/000000000000000000000000")
    assert resp.status_code == 404


async def test_get_document_with_malformed_id_returns_404(client):
    resp = await client.get("/documents/not-a-valid-object-id")
    assert resp.status_code == 404
