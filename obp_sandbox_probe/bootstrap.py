import os
from typing import Any

import httpx

OBP_BASE_URL = os.getenv("OBP_BASE_URL", "https://apisandbox.openbankproject.com").rstrip("/")
OBP_VERSION = os.getenv("OBP_VERSION", "v7.0.0")

runtime: dict[str, Any] = {
    "ready": False,
    "public_api": {},
    "direct_login": {
        "available": bool(os.getenv("OBP_CONSUMER_KEY")),
        "consumer_key_source": "environment" if os.getenv("OBP_CONSUMER_KEY") else None,
    },
}


def sanitized() -> dict[str, Any]:
    """Return diagnostics that never contain credentials or access tokens."""
    return runtime


async def bootstrap() -> dict[str, Any]:
    """Check public OBP connectivity without authenticating or reading user data."""
    global runtime
    result: dict[str, Any] = {
        "ready": False,
        "public_api": {},
        "direct_login": {
            "available": bool(os.getenv("OBP_CONSUMER_KEY")),
            "consumer_key_source": "environment" if os.getenv("OBP_CONSUMER_KEY") else None,
        },
    }

    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
        for name, path in {
            "root": f"/obp/{OBP_VERSION}/root",
            "banks": f"/obp/{OBP_VERSION}/banks",
        }.items():
            try:
                response = await client.get(f"{OBP_BASE_URL}{path}")
                result["public_api"][name] = {
                    "ok": response.status_code < 400,
                    "status_code": response.status_code,
                }
            except Exception as exc:
                result["public_api"][name] = {
                    "ok": False,
                    "error": type(exc).__name__,
                }

    result["ready"] = all(
        result["public_api"].get(name, {}).get("ok") for name in ("root", "banks")
    )
    runtime = result
    return result
