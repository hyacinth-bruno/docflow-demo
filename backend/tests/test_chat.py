import pytest

pytestmark = pytest.mark.asyncio


async def test_chat_without_api_key_returns_friendly_answer(client):
    # conftest.py forces ANTHROPIC_API_KEY="" for every test, so this always
    # hits the no-key short-circuit — no network call, fully deterministic.
    resp = await client.post("/chat", json={"query": "what is this document about?"})
    assert resp.status_code == 200
    data = resp.json()
    assert "ANTHROPIC_API_KEY" in data["answer"]
    assert data["sources"] == []


async def test_chat_rejects_empty_query(client):
    resp = await client.post("/chat", json={"query": "   "})
    assert resp.status_code == 400
