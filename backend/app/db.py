"""
Engine factory. Swapping between a real MongoDB Atlas cluster and an
in-memory mock is a one-line change (which client class gets constructed),
which is the whole point of going through AIOEngine/Motor instead of talking
to the driver directly in route handlers.
"""

import os

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from odmantic import AIOEngine

load_dotenv()  # no-op if .env doesn't exist — Render/Fly set real env vars directly

MONGODB_URI = os.environ.get("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.environ.get("MONGODB_DB", "docflow")


def build_engine(client=None) -> AIOEngine:
    """
    client=None -> connects to MONGODB_URI (real MongoDB / Atlas), unless
    MONGODB_MOCK=1 is set, in which case an in-memory mock client is used
    instead (set by the test suite — see tests/conftest.py). Passing a
    client explicitly always takes priority.
    """
    if client is None:
        if os.environ.get("MONGODB_MOCK") == "1":
            from mongomock_motor import AsyncMongoMockClient
            client = AsyncMongoMockClient()
        else:
            client = AsyncIOMotorClient(MONGODB_URI)
    return AIOEngine(client=client, database=MONGODB_DB)
