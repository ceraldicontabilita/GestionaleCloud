#!/usr/bin/env python
"""Local backend runner with an in-memory Mongo, for screenshotting the
AUTHENTICATED app without a real MongoDB Atlas connection.

It monkeypatches motor's client with mongomock_motor (a real-MongoDB-free async
mock), seeds one admin user so PIN-login can mint a JWT, and runs the app. The
app's own lifespan already tolerates a missing DB, so pages render (with empty
data) and the PIN flow works.

Run from the repo root:

    .venv/bin/pip install mongomock_motor mongomock      # one-time
    .venv/bin/python .claude/skills/run-gestionale/mock_backend.py

Then drive the frontend with the PIN (see SKILL.md):

    node .claude/skills/run-gestionale/driver.mjs /dipendenti \
        --device mobile --pin 141574 --out dipendenti.png

This is agent tooling, not product code. It does not modify the repo.
"""
import os
import sys
import asyncio
import secrets

# auth.py (jwt verify) and the unified settings secret both read SECRET_KEY from
# the environment. They only need to read the SAME value for PIN tokens to pass
# /api/auth/verify locally — the value itself is irrelevant — so set a random,
# ephemeral one for this process (no hardcoded secret).
os.environ.setdefault("SECRET_KEY", secrets.token_urlsafe(32))

import motor.motor_asyncio as _motor
from mongomock_motor import AsyncMongoMockClient

# Resolve the repo root from this file: <root>/.claude/skills/run-gestionale/
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, _ROOT)

# One shared in-memory client so all collections persist within the process.
_shared = AsyncMongoMockClient()


class _PatchedClient:
    def __new__(cls, *args, **kwargs):
        return _shared


_motor.AsyncIOMotorClient = _PatchedClient


async def _seed():
    from app.config import settings
    from app.database import Collections
    users = _shared[settings.DB_NAME][Collections.USERS]
    if await users.find_one({"role": "admin"}):
        return
    await users.insert_one({
        "id": "admin-local",
        "username": "admin",
        "email": "admin@local.test",
        "name": "Admin Local",
        "role": "admin",
        "is_active": True,
    })


if __name__ == "__main__":
    asyncio.run(_seed())
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, log_level="warning")
