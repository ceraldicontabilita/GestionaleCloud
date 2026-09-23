import html
import logging
import os
import secrets
import time
from typing import Any
from urllib.parse import parse_qs, quote

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .bootstrap import bootstrap, sanitized

app = FastAPI(title="GestionaleCloud - OBP Sandbox Probe", version="3.0.0")
logger = logging.getLogger("obp_sandbox_probe")

# Avoid verbose HTTP client logging: an Authorization header must never be emitted.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

OBP_BASE_URL = os.getenv("OBP_BASE_URL", "https://apisandbox.openbankproject.com").rstrip("/")
OBP_VERSION = os.getenv("OBP_VERSION", "v7.0.0")
CSRF_TTL_SECONDS = 10 * 60

_csrf_tokens: dict[str, float] = {}
_direct_token: str | None = None
_last_probe: dict[str, Any] = {
    "authenticated": False,
    "current_user": {},
    "accounts": {},
    "transactions": {},
    "ready": False,
}


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
        "base-uri 'none'; frame-ancestors 'none'"
    )
    return response


@app.on_event("startup")
async def run_bootstrap() -> None:
    # Public sandbox connectivity only. Authentication is always user-initiated.
    await bootstrap()
    logger.info("OBP public connectivity check completed")


def _public_runtime() -> dict[str, Any]:
    return dict(sanitized())


def _page(title: str, content: str) -> str:
    return f"""
    <!doctype html>
    <html lang="it">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>{html.escape(title)}</title>
      <style>
        body {{ font-family: system-ui, sans-serif; max-width: 760px; margin: 48px auto; padding: 0 18px; color:#17202a; }}
        .card {{ border: 1px solid #d8dee4; border-radius: 14px; padding: 20px; margin: 16px 0; }}
        label {{ display:block; margin:14px 0 5px; font-weight:650; }}
        input {{ width:100%; box-sizing:border-box; padding:11px; border:1px solid #aab2bd; border-radius:8px; }}
        button,.button {{ display:inline-block; padding:10px 14px; border:1px solid #253858; border-radius:9px; background:#253858; color:white; text-decoration:none; cursor:pointer; margin:5px 6px 5px 0; }}
        code {{ background:#f4f5f7; padding:2px 6px; border-radius:5px; }}
        .ok {{ color:#147d36; font-weight:700; }} .fail {{ color:#b42318; font-weight:700; }}
        small {{ color:#52606d; }} form.inline {{ display:inline; }}
      </style>
    </head>
    <body>
      {content}
    </body>
    </html>
    """


@app.get("/", response_class=HTMLResponse)
async def home() -> str:
    public = _public_runtime()
    verified = bool(_last_probe.get("ready"))
    state_class = "ok" if verified else "fail"
    state = "VERIFICATO" if verified else "LOGIN RICHIESTO"
    accounts = _last_probe.get("accounts", {}).get("count", 0)
    transactions = _last_probe.get("transactions", {}).get("count", 0)
    content = f"""
      <h1>GestionaleCloud · OBP Sandbox Probe</h1>
      <p>Servizio sandbox isolato e read-only. Nessun collegamento a GestionaleCloud o Supabase.</p>
      <div class="card">
        <b>Test autenticato:</b> <span class="{state_class}">{state}</span><br>
        <b>Connettività pubblica:</b> <code>{'OK' if public.get('ready') else 'DA VERIFICARE'}</code><br>
        <b>Account leggibili:</b> <code>{accounts}</code><br>
        <b>Transazioni campione:</b> <code>{transactions}</code>
      </div>
      <div class="card">
        <a class="button" href="/direct-login">Avvia Direct Login</a>
        <a class="button" href="/direct-result">Ultimo risultato</a>
        <a class="button" href="/health">Health</a>
        <form class="inline" method="post" action="/logout"><button type="submit">Cancella token</button></form>
      </div>
      <p><small>Username e password vengono inviati via HTTPS soltanto a questo backend, usati per il login OBP e poi scartati. Il token resta esclusivamente nella memoria volatile del processo.</small></p>
    """
    return _page("OBP Sandbox Probe", content)


@app.get("/health")
async def health() -> dict[str, Any]:
    diag = _public_runtime()
    return {
        "ok": True,
        "service": "obp-sandbox-probe",
        "version": "3.0.0",
        "obp_base_url": OBP_BASE_URL,
        "obp_version": OBP_VERSION,
        "public_connectivity_ready": diag.get("ready", False),
        "direct_login_configured": bool(os.getenv("OBP_CONSUMER_KEY")),
        "authenticated_token_in_memory": bool(_direct_token),
    }


@app.get("/diagnostic")
async def diagnostic() -> dict[str, Any]:
    return {"public": _public_runtime(), "authenticated": _safe_probe_result()}


@app.post("/retest")
async def retest() -> dict[str, Any]:
    await bootstrap()
    return _public_runtime()


def _new_csrf_token() -> str:
    now = time.monotonic()
    expired = [token for token, created in _csrf_tokens.items() if now - created > CSRF_TTL_SECONDS]
    for token in expired:
        _csrf_tokens.pop(token, None)
    token = secrets.token_urlsafe(32)
    _csrf_tokens[token] = now
    return token


def _valid_csrf(cookie_token: str | None, form_token: str) -> bool:
    if not cookie_token or not secrets.compare_digest(cookie_token, form_token):
        return False
    created = _csrf_tokens.pop(form_token, None)
    return created is not None and time.monotonic() - created <= CSRF_TTL_SECONDS


@app.get("/direct-login", response_class=HTMLResponse)
async def direct_login_form() -> HTMLResponse:
    if not os.getenv("OBP_CONSUMER_KEY"):
        raise HTTPException(status_code=503, detail="OBP_CONSUMER_KEY is not configured.")
    csrf_token = _new_csrf_token()
    content = f"""
      <h1>Direct Login · OBP Sandbox</h1>
      <div class="card">
        <form method="post" action="/direct-login" autocomplete="on">
          <input type="hidden" name="csrf_token" value="{html.escape(csrf_token)}">
          <label for="username">Username sandbox OBP</label>
          <input id="username" name="username" type="text" autocomplete="username" required>
          <label for="password">Password sandbox OBP</label>
          <input id="password" name="password" type="password" autocomplete="current-password" required>
          <p><button type="submit">Accedi e verifica</button> <a href="/">Annulla</a></p>
        </form>
      </div>
      <p><small>Le credenziali non vengono salvate né inserite nei log. Il form usa una protezione CSRF monouso e non è memorizzabile nella cache.</small></p>
    """
    response = HTMLResponse(_page("Direct Login OBP", content))
    response.set_cookie(
        "__Host-obp_probe_csrf",
        csrf_token,
        max_age=CSRF_TTL_SECONDS,
        secure=True,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return response


def _escape_direct_login_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


async def _json_or_none(response: httpx.Response) -> dict[str, Any] | None:
    try:
        body = response.json()
    except Exception:
        return None
    return body if isinstance(body, dict) else None


async def _run_direct_probe(username: str, password: str) -> dict[str, Any]:
    global _direct_token

    consumer_key = os.getenv("OBP_CONSUMER_KEY", "")
    result: dict[str, Any] = {
        "authenticated": False,
        "current_user": {},
        "accounts": {},
        "transactions": {},
        "ready": False,
    }
    if not consumer_key:
        result["error"] = "consumer_key_not_configured"
        return result

    authorization = (
        f'DirectLogin username="{_escape_direct_login_value(username)}",'
        f'password="{_escape_direct_login_value(password)}",'
        f'consumer_key="{_escape_direct_login_value(consumer_key)}"'
    )

    try:
        async with httpx.AsyncClient(timeout=25.0, follow_redirects=False) as client:
            login_response = await client.post(
                f"{OBP_BASE_URL}/my/logins/direct",
                headers={"Authorization": authorization, "Accept": "application/json"},
            )
            login_body = await _json_or_none(login_response)
            token = login_body.get("token") if login_body else None
            result["login_status"] = login_response.status_code
            result["authenticated"] = bool(login_response.status_code in (200, 201) and token)
            login_response = None
            login_body = None
            authorization = ""
            username = ""
            password = ""
            if not result["authenticated"]:
                _direct_token = None
                result["error"] = "authentication_failed"
                return result

            _direct_token = str(token)
            token_headers = {"Authorization": f'DirectLogin token="{_direct_token}"'}

            user_response = await client.get(
                f"{OBP_BASE_URL}/obp/{OBP_VERSION}/users/current",
                headers=token_headers,
            )
            result["current_user"] = {
                "ok": user_response.status_code < 400,
                "status_code": user_response.status_code,
            }

            accounts_response = await client.get(
                f"{OBP_BASE_URL}/obp/{OBP_VERSION}/my/accounts",
                headers=token_headers,
            )
            accounts_body = await _json_or_none(accounts_response)
            accounts = accounts_body.get("accounts", []) if accounts_body else []
            if not isinstance(accounts, list):
                accounts = []
            result["accounts"] = {
                "ok": accounts_response.status_code < 400,
                "status_code": accounts_response.status_code,
                "count": len(accounts),
            }

            if accounts:
                account = accounts[0] if isinstance(accounts[0], dict) else {}
                bank_id = account.get("bank_id")
                account_id = account.get("id") or account.get("account_id")
                views = account.get("views_available") or []
                owner_view = next(
                    (
                        view
                        for view in views
                        if isinstance(view, dict) and view.get("id") == "owner"
                    ),
                    None,
                )
                first_view = views[0] if views and isinstance(views[0], dict) else {}
                view_id = (owner_view or first_view).get("id", "owner")
                if bank_id and account_id:
                    transaction_url = (
                        f"{OBP_BASE_URL}/obp/{OBP_VERSION}/banks/{quote(str(bank_id), safe='')}"
                        f"/accounts/{quote(str(account_id), safe='')}/{quote(str(view_id), safe='')}"
                        "/transactions"
                    )
                    transactions_response = await client.get(
                        transaction_url,
                        headers=token_headers,
                        params={"limit": 5},
                    )
                    transactions_body = await _json_or_none(transactions_response)
                    transactions = (
                        transactions_body.get("transactions", []) if transactions_body else []
                    )
                    if not isinstance(transactions, list):
                        transactions = []
                    result["transactions"] = {
                        "ok": transactions_response.status_code < 400,
                        "status_code": transactions_response.status_code,
                        "count": len(transactions),
                        "limit": 5,
                    }
                else:
                    result["transactions"] = {"ok": False, "error": "account_identifiers_missing"}
            else:
                result["transactions"] = {"ok": False, "error": "no_accounts_available"}
    except Exception as exc:
        _direct_token = None
        result["error"] = type(exc).__name__
        return result
    finally:
        authorization = ""
        password = ""

    result["ready"] = bool(
        result["authenticated"]
        and result["current_user"].get("ok")
        and result["accounts"].get("ok")
        and result["transactions"].get("ok")
    )
    return result


@app.post("/direct-login")
async def direct_login_submit(request: Request) -> RedirectResponse:
    global _last_probe
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/x-www-form-urlencoded":
        raise HTTPException(status_code=415, detail="Form encoding required.")
    try:
        content_length = int(request.headers.get("content-length", "0"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request length.")
    if content_length > 8192:
        raise HTTPException(status_code=413, detail="Form is too large.")

    raw_form = await request.body()
    if len(raw_form) > 8192:
        raise HTTPException(status_code=413, detail="Form is too large.")
    try:
        fields = parse_qs(
            raw_form.decode("utf-8"),
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=3,
        )
    except (UnicodeDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid form data.")

    username = fields.get("username", [""])[0]
    password = fields.get("password", [""])[0]
    csrf_token = fields.get("csrf_token", [""])[0]
    cookie_token = request.cookies.get("__Host-obp_probe_csrf")
    if not _valid_csrf(cookie_token, csrf_token):
        raise HTTPException(status_code=400, detail="Invalid or expired form token.")
    if not username or not password:
        raise HTTPException(status_code=400, detail="Username and password are required.")

    _last_probe = await _run_direct_probe(username, password)
    username = ""
    password = ""
    fields.clear()
    raw_form = b""
    response = RedirectResponse("/direct-result", status_code=303)
    response.delete_cookie(
        "__Host-obp_probe_csrf",
        path="/",
        secure=True,
        httponly=True,
        samesite="strict",
    )
    return response


def _safe_probe_result() -> dict[str, Any]:
    return {**_last_probe, "token_present_in_memory": bool(_direct_token)}


@app.get("/direct-probe")
async def direct_probe() -> dict[str, Any]:
    return _safe_probe_result()


@app.get("/direct-result", response_class=HTMLResponse)
async def direct_result() -> str:
    result = _safe_probe_result()
    ready = bool(result.get("ready"))
    status_class = "ok" if ready else "fail"
    status = "VERIFICA COMPLETATA" if ready else "VERIFICA NON COMPLETATA"
    content = f"""
      <h1>Risultato Direct Login</h1>
      <div class="card">
        <p class="{status_class}">{status}</p>
        <b>Autenticazione:</b> <code>{'OK' if result.get('authenticated') else 'NO'}</code><br>
        <b>/users/current:</b> <code>{'OK' if result.get('current_user', {}).get('ok') else 'NO'}</code><br>
        <b>/my/accounts:</b> <code>{'OK' if result.get('accounts', {}).get('ok') else 'NO'}</code><br>
        <b>Account:</b> <code>{result.get('accounts', {}).get('count', 0)}</code><br>
        <b>Prime transazioni:</b> <code>{'OK' if result.get('transactions', {}).get('ok') else 'NO'}</code><br>
        <b>Transazioni lette:</b> <code>{result.get('transactions', {}).get('count', 0)}</code><br>
        <b>Token volatile presente:</b> <code>{'SI' if result.get('token_present_in_memory') else 'NO'}</code>
      </div>
      <a class="button" href="/direct-login">Nuovo test</a>
      <a class="button" href="/">Home</a>
    """
    return _page("Risultato Direct Login", content)


@app.post("/logout")
async def logout() -> RedirectResponse:
    global _direct_token, _last_probe
    _direct_token = None
    _last_probe = {
        "authenticated": False,
        "current_user": {},
        "accounts": {},
        "transactions": {},
        "ready": False,
    }
    _csrf_tokens.clear()
    return RedirectResponse("/", status_code=303)
