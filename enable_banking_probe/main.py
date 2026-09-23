import html
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import httpx
import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

app = FastAPI(title="GestionaleCloud - Banco BPM Real Probe", version="1.0.0")

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

API_ORIGIN = os.getenv("ENABLE_BANKING_API_ORIGIN", "https://api.enablebanking.com").rstrip("/")
APPLICATION_ID = os.getenv("ENABLE_BANKING_APPLICATION_ID", "")
PRIVATE_KEY_PEM = os.getenv("ENABLE_BANKING_PRIVATE_KEY_PEM", "").replace("\\n", "\n")
REDIRECT_URL = os.getenv(
    "ENABLE_BANKING_REDIRECT_URL",
    "https://gestionalecloud-banco-bpm-probe.onrender.com/callback",
)
COUNTRY = "IT"
PSU_TYPE = "business"
ACCESS_DAYS = min(max(int(os.getenv("ENABLE_BANKING_ACCESS_DAYS", "90")), 1), 180)
CSRF_TTL_SECONDS = 10 * 60
STATE_TTL_SECONDS = 15 * 60

_csrf_tokens: dict[str, float] = {}
_pending_states: dict[str, float] = {}
_session_id: str | None = None
_account_uids: list[str] = []
_last_result: dict[str, Any] = {
    "connected": False,
    "session": {},
    "accounts": {},
    "balances": {},
    "transactions": {},
    "ready": False,
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
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


def _configured() -> bool:
    return bool(APPLICATION_ID and PRIVATE_KEY_PEM)


def _page(title: str, content: str) -> str:
    return f"""
    <!doctype html>
    <html lang="it">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width,initial-scale=1">
      <title>{html.escape(title)}</title>
      <style>
        body {{ font-family:system-ui,sans-serif;max-width:760px;margin:48px auto;padding:0 18px;color:#17202a; }}
        .card {{ border:1px solid #d8dee4;border-radius:14px;padding:20px;margin:16px 0; }}
        button,.button {{ display:inline-block;padding:11px 15px;border:1px solid #253858;border-radius:9px;background:#253858;color:white;text-decoration:none;cursor:pointer;margin:5px 6px 5px 0; }}
        code {{ background:#f4f5f7;padding:2px 6px;border-radius:5px; }}
        .ok {{ color:#147d36;font-weight:700; }} .wait {{ color:#9a6700;font-weight:700; }}
        small {{ color:#52606d; }} form.inline {{ display:inline; }}
      </style>
    </head>
    <body>{content}</body>
    </html>
    """


def _clean_expired(values: dict[str, float], ttl: int) -> None:
    now = time.monotonic()
    for value, created in list(values.items()):
        if now - created > ttl:
            values.pop(value, None)


def _new_csrf() -> str:
    _clean_expired(_csrf_tokens, CSRF_TTL_SECONDS)
    token = secrets.token_urlsafe(32)
    _csrf_tokens[token] = time.monotonic()
    return token


def _consume_csrf(cookie_token: str | None, form_token: str) -> bool:
    if not cookie_token or not secrets.compare_digest(cookie_token, form_token):
        return False
    created = _csrf_tokens.pop(form_token, None)
    return created is not None and time.monotonic() - created <= CSRF_TTL_SECONDS


def _app_jwt() -> str:
    if not _configured():
        raise RuntimeError("enable_banking_not_configured")
    issued_at = int(datetime.now(timezone.utc).timestamp())
    return jwt.encode(
        {
            "iss": "enablebanking.com",
            "aud": "api.enablebanking.com",
            "iat": issued_at,
            "exp": issued_at + 15 * 60,
        },
        PRIVATE_KEY_PEM,
        algorithm="RS256",
        headers={"kid": APPLICATION_ID},
    )


def _api_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_app_jwt()}", "Accept": "application/json"}


async def _json_dict(response: httpx.Response) -> dict[str, Any] | None:
    try:
        body = response.json()
    except Exception:
        return None
    return body if isinstance(body, dict) else None


async def _resolve_banco_bpm(client: httpx.AsyncClient) -> dict[str, str] | None:
    response = await client.get(
        f"{API_ORIGIN}/aspsps",
        headers=_api_headers(),
        params={"country": COUNTRY, "psu_type": PSU_TYPE},
    )
    body = await _json_dict(response)
    aspsps = body.get("aspsps", []) if body else []
    candidates = [
        item
        for item in aspsps
        if isinstance(item, dict) and "banco bpm" in str(item.get("name", "")).lower()
    ]
    if not candidates:
        return None
    selected = next(
        (item for item in candidates if "corporate" in str(item.get("name", "")).lower()),
        candidates[0],
    )
    return {"name": str(selected["name"]), "country": str(selected.get("country", COUNTRY))}


async def _start_authorization() -> str:
    state = secrets.token_urlsafe(32)
    _clean_expired(_pending_states, STATE_TTL_SECONDS)
    _pending_states[state] = time.monotonic()

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
        aspsp = await _resolve_banco_bpm(client)
        if not aspsp:
            _pending_states.pop(state, None)
            raise RuntimeError("banco_bpm_business_not_available")
        response = await client.post(
            f"{API_ORIGIN}/auth",
            headers=_api_headers(),
            json={
                "access": {
                    "valid_until": (
                        datetime.now(timezone.utc) + timedelta(days=ACCESS_DAYS)
                    ).isoformat()
                },
                "aspsp": aspsp,
                "state": state,
                "redirect_url": REDIRECT_URL,
                "psu_type": PSU_TYPE,
            },
        )
        body = await _json_dict(response)
    if response.status_code != 200 or not body or not body.get("url"):
        _pending_states.pop(state, None)
        raise RuntimeError(f"authorization_start_failed_{response.status_code}")
    return str(body["url"])


def _safe_result() -> dict[str, Any]:
    return {**_last_result, "session_present_in_memory": bool(_session_id)}


@app.get("/", response_class=HTMLResponse)
async def home() -> HTMLResponse:
    csrf = _new_csrf()
    configured = _configured()
    status = "PRONTO AL COLLEGAMENTO" if configured else "CONFIGURAZIONE ENABLE BANKING NECESSARIA"
    status_class = "ok" if configured else "wait"
    connect = (
        f"""
        <form class="inline" method="post" action="/connect">
          <input type="hidden" name="csrf_token" value="{html.escape(csrf)}">
          <button type="submit">Collega Banco BPM reale</button>
        </form>
        """
        if configured
        else ""
    )
    content = f"""
      <h1>GestionaleCloud · Banco BPM Real Probe</h1>
      <p>Servizio isolato per una prova PSD2 reale tramite Enable Banking.</p>
      <div class="card">
        <p class="{status_class}">{status}</p>
        <b>Ambiente:</b> <code>PRODUCTION limitata al conto autorizzato</code><br>
        <b>Credenziali bancarie:</b> <code>solo Banco BPM / Enable Banking</code><br>
        <b>Persistenza locale:</b> <code>nessuna</code><br>
        <b>Supabase:</b> <code>non collegato</code>
      </div>
      {connect}
      <a class="button" href="/result">Ultimo risultato</a>
      <p><small>Durante il collegamento verrai reindirizzato alla banca. Password, PIN e OTP non transitano da questo servizio.</small></p>
    """
    response = HTMLResponse(_page("Banco BPM Real Probe", content))
    response.set_cookie(
        "__Host-banco_bpm_probe_csrf",
        csrf,
        max_age=CSRF_TTL_SECONDS,
        secure=True,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return response


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "banco-bpm-real-probe",
        "version": "1.0.0",
        "provider": "Enable Banking",
        "provider_api": API_ORIGIN,
        "configured": _configured(),
        "application_id_present": bool(APPLICATION_ID),
        "private_key_present": bool(PRIVATE_KEY_PEM),
        "session_present_in_memory": bool(_session_id),
        "supabase_connected": False,
    }


@app.get("/privacy", response_class=HTMLResponse)
async def privacy() -> str:
    content = """
      <h1>Informativa privacy · prova Banco BPM</h1>
      <div class="card">
        <p>Questa applicazione è una prova tecnica interna di Ceraldi Group SRL per
        leggere, con consenso esplicito, i propri conti Banco BPM tramite Enable Banking.</p>
        <p>Le credenziali bancarie, i PIN e i codici OTP non sono raccolti
        dall'applicazione. L'autenticazione avviene sui sistemi di Banco BPM ed Enable Banking.</p>
        <p>Il probe non utilizza Supabase o il database di GestionaleCloud. Identificativi
        di sessione e conto restano nella memoria volatile del processo e vengono eliminati
        al riavvio. La pagina diagnostica espone soltanto esiti e conteggi.</p>
        <p>Il contatto per la protezione dei dati è quello indicato nella registrazione
        dell'applicazione Enable Banking.</p>
      </div>
      <a class="button" href="/">Home</a>
    """
    return _page("Privacy · Banco BPM Real Probe", content)


@app.get("/terms", response_class=HTMLResponse)
async def terms() -> str:
    content = """
      <h1>Condizioni d'uso · prova Banco BPM</h1>
      <div class="card">
        <p>Servizio destinato esclusivamente alla verifica tecnica interna dei conti
        Banco BPM appartenenti all'organizzazione che gestisce l'applicazione.</p>
        <p>Il servizio è di sola lettura: non avvia pagamenti, bonifici o altre operazioni
        dispositive. Il collegamento può essere autorizzato soltanto dal titolare del conto
        attraverso il flusso ufficiale Banco BPM ed Enable Banking.</p>
        <p>L'accesso può essere interrotto chiudendo la sessione o revocando il consenso
        attraverso i canali messi a disposizione dal provider o dalla banca.</p>
      </div>
      <a class="button" href="/">Home</a>
    """
    return _page("Condizioni · Banco BPM Real Probe", content)


async def _parse_form(request: Request) -> dict[str, str]:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/x-www-form-urlencoded":
        raise HTTPException(status_code=415, detail="Form encoding required.")
    body = await request.body()
    if len(body) > 4096:
        raise HTTPException(status_code=413, detail="Form is too large.")
    from urllib.parse import parse_qs

    try:
        parsed = parse_qs(body.decode("utf-8"), strict_parsing=True, max_num_fields=2)
    except (UnicodeDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid form data.")
    return {key: values[0] for key, values in parsed.items() if values}


@app.post("/connect")
async def connect(request: Request) -> RedirectResponse:
    if not _configured():
        raise HTTPException(status_code=503, detail="Enable Banking is not configured.")
    fields = await _parse_form(request)
    cookie = request.cookies.get("__Host-banco_bpm_probe_csrf")
    if not _consume_csrf(cookie, fields.get("csrf_token", "")):
        raise HTTPException(status_code=400, detail="Invalid or expired form token.")
    try:
        authorization_url = await _start_authorization()
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    return RedirectResponse(authorization_url, status_code=303)


async def _probe_accounts(client: httpx.AsyncClient) -> dict[str, Any]:
    global _last_result
    accounts_total = len(_account_uids)
    balance_ok = 0
    transactions_ok = 0
    transactions_total = 0
    date_from = (datetime.now(timezone.utc) - timedelta(days=90)).date().isoformat()

    for account_uid in _account_uids[:10]:
        safe_uid = quote(account_uid, safe="")
        balance_response = await client.get(
            f"{API_ORIGIN}/accounts/{safe_uid}/balances",
            headers=_api_headers(),
        )
        if balance_response.status_code == 200:
            balance_ok += 1
        transactions_response = await client.get(
            f"{API_ORIGIN}/accounts/{safe_uid}/transactions",
            headers=_api_headers(),
            params={"date_from": date_from},
        )
        transactions_body = await _json_dict(transactions_response)
        transactions = transactions_body.get("transactions", []) if transactions_body else []
        if transactions_response.status_code == 200:
            transactions_ok += 1
        if isinstance(transactions, list):
            transactions_total += len(transactions)

    _last_result = {
        "connected": bool(_session_id),
        "session": {"ok": bool(_session_id)},
        "accounts": {"ok": accounts_total > 0, "count": accounts_total},
        "balances": {"ok": balance_ok == accounts_total and accounts_total > 0, "count": balance_ok},
        "transactions": {
            "ok": transactions_ok == accounts_total and accounts_total > 0,
            "accounts_checked": transactions_ok,
            "count": transactions_total,
            "period_days": 90,
        },
        "ready": bool(
            _session_id
            and accounts_total > 0
            and balance_ok == accounts_total
            and transactions_ok == accounts_total
        ),
    }
    return _last_result


@app.get("/callback")
async def callback(request: Request) -> RedirectResponse:
    global _session_id, _account_uids
    error = request.query_params.get("error")
    if error:
        raise HTTPException(status_code=400, detail="Bank authorization was not completed.")
    code = request.query_params.get("code", "")
    state = request.query_params.get("state", "")
    created = _pending_states.pop(state, None)
    if not code or created is None or time.monotonic() - created > STATE_TTL_SECONDS:
        raise HTTPException(status_code=400, detail="Invalid or expired bank callback.")

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
        response = await client.post(
            f"{API_ORIGIN}/sessions",
            headers=_api_headers(),
            json={"code": code},
        )
        body = await _json_dict(response)
        if response.status_code != 200 or not body or not body.get("session_id"):
            raise HTTPException(status_code=502, detail="Unable to create the banking session.")
        _session_id = str(body["session_id"])
        accounts = body.get("accounts", [])
        _account_uids = [
            str(account["uid"])
            for account in accounts
            if isinstance(account, dict) and account.get("uid")
        ]
        await _probe_accounts(client)
    return RedirectResponse("/result", status_code=303)


@app.post("/retest")
async def retest() -> RedirectResponse:
    if not _session_id:
        raise HTTPException(status_code=409, detail="No in-memory banking session.")
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
        await _probe_accounts(client)
    return RedirectResponse("/result", status_code=303)


@app.get("/probe")
async def probe() -> dict[str, Any]:
    return _safe_result()


@app.get("/result", response_class=HTMLResponse)
async def result() -> str:
    data = _safe_result()
    ready = bool(data.get("ready"))
    status = "VERIFICA REALE COMPLETATA" if ready else "COLLEGAMENTO NON ANCORA COMPLETATO"
    status_class = "ok" if ready else "wait"
    content = f"""
      <h1>Risultato Banco BPM</h1>
      <div class="card">
        <p class="{status_class}">{status}</p>
        <b>Sessione:</b> <code>{'OK' if data.get('connected') else 'NO'}</code><br>
        <b>Conti:</b> <code>{data.get('accounts', {}).get('count', 0)}</code><br>
        <b>Saldi verificati:</b> <code>{data.get('balances', {}).get('count', 0)}</code><br>
        <b>Movimenti letti:</b> <code>{data.get('transactions', {}).get('count', 0)}</code><br>
        <b>Sessione solo in memoria:</b> <code>{'SI' if data.get('session_present_in_memory') else 'NO'}</code>
      </div>
      <a class="button" href="/">Home</a>
      <form class="inline" method="post" action="/retest"><button type="submit">Ripeti lettura</button></form>
    """
    return _page("Risultato Banco BPM", content)
