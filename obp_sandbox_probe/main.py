import os
import secrets
import json
import logging
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .bootstrap import bootstrap, sanitized, runtime

app = FastAPI(title="GestionaleCloud - OBP Sandbox Probe", version="2.0.0")
logger = logging.getLogger("obp_sandbox_probe")

OBP_BASE_URL = os.getenv("OBP_BASE_URL", "https://apisandbox.openbankproject.com").rstrip("/")
OBP_VERSION = os.getenv("OBP_VERSION", "v7.0.0")
REDIRECT_URI = os.getenv(
    "OBP_REDIRECT_URI",
    "https://gestionalecloud-obp-sandbox-probe.onrender.com/callback",
)

_pending_states: set[str] = set()
_oauth_token: dict[str, Any] | None = None


@app.on_event("startup")
async def run_bootstrap() -> None:
    # Sandbox only. No database writes, no ERP integration.
    await bootstrap()
    logger.info("OBP_BOOTSTRAP_DIAGNOSTIC %s", json.dumps(_public_runtime(), ensure_ascii=False))


def _public_runtime() -> dict[str, Any]:
    data = dict(sanitized())
    for k in list(data):
        if k.startswith("_"):
            data.pop(k, None)
    return data


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    diag = _public_runtime()
    ready = diag.get("ready", False)
    state = "PASS" if ready else "CHECK REQUIRED"
    return f"""
    <!doctype html>
    <html lang="it">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>OBP Sandbox Probe</title>
      <style>
        body {{ font-family: system-ui, sans-serif; max-width: 880px; margin: 48px auto; padding: 0 18px; }}
        .card {{ border: 1px solid #ddd; border-radius: 14px; padding: 20px; margin: 16px 0; }}
        code {{ background:#f4f4f4; padding:2px 6px; border-radius:5px; }}
        a.button {{ display:inline-block; padding:10px 14px; border:1px solid #222; border-radius:9px; text-decoration:none; margin:5px 6px 5px 0; }}
        .ok {{ font-weight:700; }}
      </style>
    </head>
    <body>
      <h1>GestionaleCloud · OBP Sandbox Probe</h1>
      <p>Servizio isolato e read-only. Nessun collegamento al database del gestionale.</p>
      <div class="card">
        <b>Esito automatico:</b> <code>{state}</code><br>
        <b>OBP:</b> <code>{OBP_BASE_URL}</code><br>
        <b>API:</b> <code>{OBP_VERSION}</code><br>
        <b>Account leggibili:</b> <code>{diag.get("accounts", {}).get("count", 0)}</code><br>
        <b>Transazioni campione:</b> <code>{diag.get("transactions", {}).get("count", 0)}</code>
      </div>
      <div class="card">
        <a class="button" href="/health">Health</a>
        <a class="button" href="/diagnostic">Diagnostica completa</a>
        <a class="button" href="/login">Test OAuth/OIDC interattivo</a>
        <a class="button" href="/oauth-probe">Test OAuth autenticato</a>
        <a class="button" href="/logout">Cancella token OAuth test</a>
      </div>
      <p><small>Il bootstrap prova automaticamente API pubbliche, discovery OIDC, registrazione dinamica client e Direct Login con account demo ufficiale OBP. I segreti non vengono mostrati.</small></p>
    </body>
    </html>
    """


@app.get("/health")
async def health() -> dict[str, Any]:
    diag = _public_runtime()
    return {
        "ok": True,
        "service": "obp-sandbox-probe",
        "version": "2.0.0",
        "obp_base_url": OBP_BASE_URL,
        "obp_version": OBP_VERSION,
        "bootstrap_ready": diag.get("ready", False),
    }


@app.get("/diagnostic")
async def diagnostic() -> dict[str, Any]:
    return _public_runtime()


@app.post("/retest")
async def retest() -> dict[str, Any]:
    await bootstrap()
    return _public_runtime()


def _runtime_value(key: str, default: str = "") -> str:
    return str(sanitized().get(key, default) or default)


@app.get("/login")
async def login() -> RedirectResponse:
    authorization_url = os.getenv("OBP_AUTHORIZATION_URL") or _runtime_value("_authorization_endpoint")
    client_id = os.getenv("OBP_CLIENT_ID") or _runtime_value("_client_id")
    if not authorization_url or not client_id:
        raise HTTPException(
            status_code=503,
            detail="OIDC authorization endpoint/client not available. See /diagnostic. Direct Login bootstrap may still have passed.",
        )

    state = secrets.token_urlsafe(32)
    _pending_states.add(state)
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": os.getenv("OBP_SCOPE", "openid profile email"),
        "state": state,
    }
    return RedirectResponse(f"{authorization_url}?{urlencode(params)}")


@app.get("/callback")
async def callback(request: Request) -> RedirectResponse:
    global _oauth_token

    error = request.query_params.get("error")
    if error:
        raise HTTPException(status_code=400, detail={
            "error": error,
            "description": request.query_params.get("error_description"),
        })

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state or state not in _pending_states:
        raise HTTPException(status_code=400, detail="Invalid OAuth callback code/state.")
    _pending_states.discard(state)

    token_url = os.getenv("OBP_TOKEN_URL") or _runtime_value("_token_endpoint")
    client_id = os.getenv("OBP_CLIENT_ID") or _runtime_value("_client_id")
    client_secret = os.getenv("OBP_CLIENT_SECRET") or _runtime_value("_client_secret")

    if not token_url or not client_id:
        raise HTTPException(status_code=503, detail="Token endpoint/client not available.")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
    }
    if client_secret:
        data["client_secret"] = client_secret

    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.post(token_url, data=data, headers={"Accept": "application/json"})

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail={
            "message": "OAuth token exchange failed",
            "status_code": response.status_code,
            "body": response.text[:1500],
        })

    payload = response.json()
    if not payload.get("access_token"):
        raise HTTPException(status_code=502, detail="Token endpoint returned no access_token.")

    _oauth_token = payload
    return RedirectResponse("/oauth-probe")


@app.get("/oauth-probe")
async def oauth_probe() -> dict[str, Any]:
    if not _oauth_token or not _oauth_token.get("access_token"):
        raise HTTPException(status_code=401, detail="No OAuth access token. Use /login first.")

    headers = {"Authorization": f"Bearer {_oauth_token['access_token']}"}
    result: dict[str, Any] = {
        "refresh_token_present": bool(_oauth_token.get("refresh_token")),
    }

    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
        for name, path in {
            "current_user": f"/obp/{OBP_VERSION}/users/current",
            "accounts": f"/obp/{OBP_VERSION}/my/accounts",
        }.items():
            r = await client.get(f"{OBP_BASE_URL}{path}", headers=headers)
            try:
                body = r.json()
            except Exception:
                body = r.text[:1500]
            result[name] = {"status_code": r.status_code, "body": body}

    return result


@app.get("/logout")
async def logout() -> RedirectResponse:
    global _oauth_token
    _oauth_token = None
    _pending_states.clear()
    return RedirectResponse("/")
