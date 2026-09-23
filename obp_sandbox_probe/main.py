import os
import secrets
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="GestionaleCloud - OBP Sandbox Probe", version="1.0.0")

OBP_BASE_URL = os.getenv("OBP_BASE_URL", "https://apisandbox.openbankproject.com").rstrip("/")
OBP_VERSION = os.getenv("OBP_VERSION", "v7.0.0")
AUTHORIZATION_URL = os.getenv("OBP_AUTHORIZATION_URL", "")
TOKEN_URL = os.getenv("OBP_TOKEN_URL", "")
CLIENT_ID = os.getenv("OBP_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("OBP_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("OBP_REDIRECT_URI", "")
SCOPE = os.getenv("OBP_SCOPE", "openid profile email")

# Sandbox-only volatile state. Nothing is persisted.
_pending_states: set[str] = set()
_token: dict[str, Any] | None = None


def api_url(path: str) -> str:
    return f"{OBP_BASE_URL}{path}"


def auth_ready() -> bool:
    return all([AUTHORIZATION_URL, TOKEN_URL, CLIENT_ID, REDIRECT_URI])


def token_headers() -> dict[str, str]:
    if not _token or not _token.get("access_token"):
        raise HTTPException(status_code=401, detail="No active OAuth/OIDC token. Use /login first.")
    return {"Authorization": f"Bearer {_token['access_token']}"}


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    status = "READY" if auth_ready() else "NEEDS OAUTH CLIENT CONFIG"
    token_status = "PRESENT" if _token and _token.get("access_token") else "ABSENT"
    return f"""
    <!doctype html>
    <html lang="it">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>OBP Sandbox Probe</title>
      <style>
        body {{ font-family: system-ui, sans-serif; max-width: 820px; margin: 48px auto; padding: 0 18px; }}
        .card {{ border: 1px solid #ddd; border-radius: 14px; padding: 20px; margin: 16px 0; }}
        code {{ background:#f4f4f4; padding:2px 6px; border-radius:5px; }}
        a.button {{ display:inline-block; padding:10px 14px; border:1px solid #222; border-radius:9px; text-decoration:none; margin:5px 6px 5px 0; }}
      </style>
    </head>
    <body>
      <h1>GestionaleCloud · OBP Sandbox Probe</h1>
      <p>Servizio isolato, read-only, senza collegamento al database del gestionale.</p>

      <div class="card">
        <b>OBP:</b> <code>{OBP_BASE_URL}</code><br>
        <b>API:</b> <code>{OBP_VERSION}</code><br>
        <b>OAuth:</b> <code>{status}</code><br>
        <b>Token volatile:</b> <code>{token_status}</code>
      </div>

      <div class="card">
        <a class="button" href="/health">Health</a>
        <a class="button" href="/public-probe">Test pubblico OBP</a>
        <a class="button" href="/login">Collega account sandbox</a>
        <a class="button" href="/authenticated-probe">Test autenticato</a>
        <a class="button" href="/logout">Cancella token test</a>
      </div>

      <p><small>Nessun pagamento, scrittura o riconciliazione è implementato in questo probe.</small></p>
    </body>
    </html>
    """


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "obp-sandbox-probe",
        "obp_base_url": OBP_BASE_URL,
        "obp_version": OBP_VERSION,
        "oauth_configured": auth_ready(),
        "token_present": bool(_token and _token.get("access_token")),
    }


@app.get("/public-probe")
async def public_probe() -> dict[str, Any]:
    results: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        for name, path in {
            "root": f"/obp/{OBP_VERSION}/root",
            "banks": f"/obp/{OBP_VERSION}/banks",
        }.items():
            try:
                response = await client.get(api_url(path))
                results[name] = {
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type"),
                    "body": response.json() if "json" in response.headers.get("content-type", "") else response.text[:1000],
                }
            except Exception as exc:
                results[name] = {"error": type(exc).__name__, "detail": str(exc)}
    return results


@app.get("/login")
async def login() -> RedirectResponse:
    if not auth_ready():
        missing = [
            key for key, value in {
                "OBP_AUTHORIZATION_URL": AUTHORIZATION_URL,
                "OBP_TOKEN_URL": TOKEN_URL,
                "OBP_CLIENT_ID": CLIENT_ID,
                "OBP_REDIRECT_URI": REDIRECT_URI,
            }.items() if not value
        ]
        raise HTTPException(status_code=503, detail={"message": "OAuth client not configured", "missing": missing})

    state = secrets.token_urlsafe(32)
    _pending_states.add(state)

    params = httpx.QueryParams({
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "state": state,
    })
    return RedirectResponse(f"{AUTHORIZATION_URL}?{params}")


@app.get("/callback")
async def callback(request: Request) -> RedirectResponse:
    global _token

    error = request.query_params.get("error")
    if error:
        raise HTTPException(status_code=400, detail={
            "error": error,
            "description": request.query_params.get("error_description"),
        })

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    if not code or not state or state not in _pending_states:
        raise HTTPException(status_code=400, detail="Invalid callback code/state.")

    _pending_states.discard(state)

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
    }
    auth = (CLIENT_ID, CLIENT_SECRET) if CLIENT_SECRET else None
    if not CLIENT_SECRET:
        data["client_secret"] = ""

    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.post(
            TOKEN_URL,
            data=data,
            auth=auth,
            headers={"Accept": "application/json"},
        )

    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail={
            "message": "Token exchange failed",
            "status_code": response.status_code,
            "body": response.text[:2000],
        })

    payload = response.json()
    if not payload.get("access_token"):
        raise HTTPException(status_code=502, detail="Token endpoint returned no access_token.")

    # Volatile memory only. Never returned to the browser.
    _token = payload
    return RedirectResponse("/authenticated-probe")


@app.get("/authenticated-probe")
async def authenticated_probe() -> dict[str, Any]:
    headers = token_headers()
    result: dict[str, Any] = {}

    async with httpx.AsyncClient(timeout=25.0, follow_redirects=True) as client:
        current_user = await client.get(api_url(f"/obp/{OBP_VERSION}/users/current"), headers=headers)
        result["current_user"] = {
            "status_code": current_user.status_code,
            "body": current_user.json() if "json" in current_user.headers.get("content-type", "") else current_user.text[:1500],
        }

        accounts = await client.get(api_url(f"/obp/{OBP_VERSION}/my/accounts"), headers=headers)
        accounts_body = accounts.json() if "json" in accounts.headers.get("content-type", "") else {"raw": accounts.text[:2000]}
        result["accounts"] = {"status_code": accounts.status_code, "body": accounts_body}

        # Best-effort, read-only transaction probe on the first accessible account.
        account_list = accounts_body.get("accounts", []) if isinstance(accounts_body, dict) else []
        if account_list:
            account = account_list[0]
            bank_id = account.get("bank_id")
            account_id = account.get("id") or account.get("account_id")

            view_id = "owner"
            views = account.get("views_available") or []
            if views:
                owner = next((v for v in views if v.get("id") == "owner"), None)
                if owner:
                    view_id = owner.get("id", "owner")
                elif views[0].get("id"):
                    view_id = views[0]["id"]

            if bank_id and account_id:
                tx_path = f"/obp/{OBP_VERSION}/banks/{bank_id}/accounts/{account_id}/{view_id}/transactions"
                tx = await client.get(api_url(tx_path), headers=headers, params={"limit": 10})
                result["transactions_first_account"] = {
                    "status_code": tx.status_code,
                    "bank_id": bank_id,
                    "account_id": account_id,
                    "view_id": view_id,
                    "body": tx.json() if "json" in tx.headers.get("content-type", "") else tx.text[:2500],
                }

    return result


@app.get("/logout")
async def logout() -> RedirectResponse:
    global _token
    _token = None
    _pending_states.clear()
    return RedirectResponse("/")
