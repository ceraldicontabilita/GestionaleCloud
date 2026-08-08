"""MCP bearer-token verification delegated to GestionaleCloud."""

from __future__ import annotations

from typing import Any

from mcp.server.auth.provider import AccessToken

from .client import APIRequestError, GestionaleAPIClient


class GestionaleTokenVerifier:
    """Validate the same JWT used by the ERP, including revocation and role."""

    def __init__(self, client: GestionaleAPIClient):
        self.client = client

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            result = await self.client.verify_token(token)
        except APIRequestError:
            return None
        user = result.get("user") or {}
        role = str(user.get("role") or "sola_lettura")
        scopes = ["gestionale:read", "gestionale:propose"]
        if role == "admin":
            scopes.append("gestionale:write")
        claims: dict[str, Any] = {
            "role": role,
            "email": user.get("email") or result.get("email"),
            "mfa_verified": bool(user.get("mfa_verified")),
        }
        return AccessToken(
            token=token,
            client_id="gestionale-cloud",
            scopes=scopes,
            subject=str(claims["email"] or "gestionale-user"),
            claims=claims,
        )
