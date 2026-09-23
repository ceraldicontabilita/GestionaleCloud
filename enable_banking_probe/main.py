import html
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import quote

import httpx
import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from enable_banking_probe import lettura

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
CSRF_TTL_SECONDS = 30 * 60
STATE_TTL_SECONDS = 15 * 60

PERIODO_GIORNI_DEFAULT = 90
PERIODO_GIORNI_MAX = 730
CSV_MAX_BYTES = 5 * 1024 * 1024
VIEWER_COOKIE = "__Host-banco_bpm_probe_viewer"

_pending_states: dict[str, float] = {}
_session_id: str | None = None
_account_uids: list[str] = []
_accounts_meta: dict[str, dict[str, str]] = {}
_consent_valid_until: str | None = None
# Chi ha completato l'autorizzazione in banca riceve questo token in un
# cookie: saldi e movimenti si vedono e si rileggono solo da quel browser.
_viewer_token: str | None = None
# Movimenti normalizzati dell'ultima lettura e ultimo confronto col CSV:
# solo in memoria, spariscono al riavvio come la sessione.
_letture: dict[str, dict[str, Any]] = {}
_confronto: dict[str, Any] | None = None
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
        table {{ width:100%;border-collapse:collapse;margin:8px 0; }}
        th,td {{ border-bottom:1px solid #d8dee4;padding:6px 4px;text-align:left;vertical-align:top;overflow-wrap:anywhere; }}
        input {{ padding:8px;margin:6px 0; }}
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
    return secrets.token_urlsafe(32)


def _consume_csrf(cookie_token: str | None, form_token: str) -> bool:
    return bool(
        cookie_token
        and form_token
        and secrets.compare_digest(cookie_token, form_token)
    )


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
        di sessione e conto, movimenti letti ed eventuale CSV di confronto restano nella
        memoria volatile del processo e vengono eliminati al riavvio. Saldi e movimenti si
        vedono solo dal browser che ha completato l'autorizzazione in banca; le pagine
        pubbliche espongono soltanto esiti e conteggi.</p>
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


def _psu_headers(request: Request | None) -> dict[str, str]:
    """Con l'utente presente la banca non conta la lettura nel limite
    giornaliero delle letture in background (PSD2)."""
    if request is None:
        return {}
    inoltrato = request.headers.get("x-forwarded-for", "")
    ip = inoltrato.split(",")[0].strip() or (request.client.host if request.client else "")
    headers = {}
    if ip:
        headers["Psu-Ip-Address"] = ip
    agente = request.headers.get("user-agent")
    if agente:
        headers["Psu-User-Agent"] = agente[:512]
    return headers


def _saldi(body: dict[str, Any] | None) -> list[dict[str, str]]:
    saldi = []
    for item in (body or {}).get("balances") or []:
        if not isinstance(item, dict):
            continue
        importo = item.get("balance_amount") or {}
        saldi.append({
            "tipo": str(item.get("balance_type") or ""),
            "nome": str(item.get("name") or ""),
            "importo": str(importo.get("amount") or ""),
            "divisa": str(importo.get("currency") or ""),
            "data": str(item.get("reference_date") or ""),
        })
    return saldi


async def _probe_accounts(
    client: httpx.AsyncClient, request: Request | None = None, giorni: int = PERIODO_GIORNI_DEFAULT,
) -> dict[str, Any]:
    global _last_result, _confronto
    accounts_total = len(_account_uids)
    balance_ok = 0
    transactions_ok = 0
    transactions_total = 0
    pagine_totali = 0
    esiti: list[str] = []
    date_from = (datetime.now(timezone.utc) - timedelta(days=giorni)).date().isoformat()
    psu = _psu_headers(request)
    acquisito_il = lettura.oggi_iso()
    _letture.clear()
    _confronto = None

    for account_uid in _account_uids:
        safe_uid = quote(account_uid, safe="")
        meta = _accounts_meta.get(account_uid, {})
        conto = meta.get("iban_mascherato") or f"conto {len(_letture) + 1}"
        esito: dict[str, Any] = {"conto": conto, "nome": meta.get("nome", ""), "stato": "ok"}
        balance_response = await client.get(
            f"{API_ORIGIN}/accounts/{safe_uid}/balances",
            headers={**_api_headers(), **psu},
        )
        if balance_response.status_code == 200:
            balance_ok += 1
            esito["saldi"] = _saldi(await _json_dict(balance_response))
        else:
            esito["saldi"] = []
            esito["stato_saldi"] = lettura.classifica_errore(
                balance_response.status_code, await _json_dict(balance_response)
            )
        try:
            letti = await lettura.leggi_transazioni(
                client,
                f"{API_ORIGIN}/accounts/{safe_uid}/transactions",
                headers=lambda: {**_api_headers(), **psu},
                date_from=date_from,
            )
        except lettura.ErroreLettura as exc:
            esito.update({"stato": exc.stato, "http": exc.http, "codice": exc.codice, "movimenti": []})
            esiti.append(exc.stato)
            _letture[account_uid] = esito
            continue
        normalizzati, scartati = [], 0
        for tx in letti["movimenti"]:
            mov = lettura.normalizza_api(tx, conto, acquisito_il)
            if mov is None:
                scartati += 1
            else:
                normalizzati.append(mov)
        transactions_ok += 1
        transactions_total += len(normalizzati)
        pagine_totali += letti["pagine"]
        esito.update({
            "pagine": letti["pagine"],
            "altri_stati": letti["altri_stati"],
            "senza_importo_o_data": scartati,
            "movimenti": normalizzati,
            "riepilogo": lettura.riepilogo_periodo(normalizzati),
        })
        _letture[account_uid] = esito

    _last_result = {
        "connected": bool(_session_id),
        "session": {"ok": bool(_session_id)},
        "accounts": {"ok": accounts_total > 0, "count": accounts_total},
        "balances": {"ok": balance_ok == accounts_total and accounts_total > 0, "count": balance_ok},
        "transactions": {
            "ok": transactions_ok == accounts_total and accounts_total > 0,
            "accounts_checked": transactions_ok,
            "count": transactions_total,
            "pages": pagine_totali,
            "period_days": giorni,
            "errors": sorted(set(esiti)),
        },
        "ready": bool(
            _session_id
            and accounts_total > 0
            and balance_ok == accounts_total
            and transactions_ok == accounts_total
        ),
    }
    return _last_result


def _is_viewer(request: Request) -> bool:
    token = request.cookies.get(VIEWER_COOKIE, "")
    return bool(_viewer_token and token and secrets.compare_digest(token, _viewer_token))


def _require_viewer(request: Request) -> None:
    if not _is_viewer(request):
        raise HTTPException(
            status_code=403,
            detail="Solo il browser che ha collegato il conto puo' vedere o rileggere i dati.",
        )


def _account_meta(account: dict[str, Any]) -> dict[str, str]:
    ident = account.get("account_id") or {}
    iban = ident.get("iban") if isinstance(ident, dict) else None
    return {
        "iban_mascherato": lettura.maschera_iban(iban or ""),
        "nome": str(account.get("name") or account.get("product") or "")[:80],
    }


@app.get("/callback")
async def callback(request: Request) -> RedirectResponse:
    global _session_id, _account_uids, _accounts_meta, _consent_valid_until, _viewer_token
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
        accounts = [a for a in body.get("accounts", []) if isinstance(a, dict) and a.get("uid")]
        _account_uids = [str(account["uid"]) for account in accounts]
        _accounts_meta = {str(account["uid"]): _account_meta(account) for account in accounts}
        access = body.get("access") or {}
        _consent_valid_until = str(access.get("valid_until") or "") or None
        _viewer_token = secrets.token_urlsafe(32)
        try:
            await _probe_accounts(client, request)
        except httpx.HTTPError as exc:
            # La sessione c'e': la lettura si ripete con «Rileggi».
            logging.getLogger(__name__).warning(
                "Prima lettura Banco BPM non riuscita: %s", type(exc).__name__
            )
    redirect = RedirectResponse("/result", status_code=303)
    # Lax e non Strict: il ritorno dalla banca e' una navigazione da un altro
    # sito, e con Strict la prima pagina non riceverebbe il cookie. Lax non
    # viaggia sui POST da altri siti, quindi protegge «Rileggi» e il CSV.
    redirect.set_cookie(
        VIEWER_COOKIE, _viewer_token, secure=True, httponly=True, samesite="lax", path="/",
    )
    return redirect


@app.post("/retest")
async def retest(request: Request) -> RedirectResponse:
    _require_viewer(request)
    if not _session_id:
        raise HTTPException(status_code=409, detail="No in-memory banking session.")
    giorni = PERIODO_GIORNI_DEFAULT
    if request.headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
        fields = await _parse_form(request)
        try:
            giorni = int(fields.get("giorni", giorni))
        except ValueError:
            raise HTTPException(status_code=400, detail="Periodo non valido.")
    giorni = min(max(giorni, 1), PERIODO_GIORNI_MAX)
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
        await _probe_accounts(client, request, giorni)
    return RedirectResponse("/result", status_code=303)


def _file_da_multipart(request_content_type: str, body: bytes) -> bytes:
    """Il file del form, letto con la libreria standard (il probe non
    installa python-multipart)."""
    from email.parser import BytesParser
    from email.policy import default

    messaggio = BytesParser(policy=default).parsebytes(
        b"Content-Type: " + request_content_type.encode("latin-1") + b"\r\n\r\n" + body
    )
    if not messaggio.is_multipart():
        raise HTTPException(status_code=400, detail="Form non valido.")
    for parte in messaggio.iter_parts():
        if parte.get_param("name", header="content-disposition") == "csv":
            return parte.get_payload(decode=True) or b""
    raise HTTPException(status_code=400, detail="Nessun file CSV nel form.")


@app.post("/confronta-csv")
async def confronta_csv(request: Request) -> RedirectResponse:
    global _confronto
    _require_viewer(request)
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith("multipart/form-data"):
        raise HTTPException(status_code=415, detail="Carica il file dal form.")
    body = await request.body()
    if len(body) > CSV_MAX_BYTES:
        raise HTTPException(status_code=413, detail="File oltre 5 MB.")
    try:
        letto = lettura.leggi_csv_bpm(_file_da_multipart(content_type, body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    api = [m for esito in _letture.values() for m in esito.get("movimenti", [])]
    _confronto = {
        **lettura.confronta(api, letto["movimenti"]),
        "csv_movimenti": len(letto["movimenti"]),
        "csv_illeggibili": letto["illeggibili"],
        "api_movimenti": len(api),
        "csv_periodo": lettura.riepilogo_periodo(letto["movimenti"]),
    }
    return RedirectResponse("/result#confronto", status_code=303)


@app.get("/probe")
async def probe() -> dict[str, Any]:
    return _safe_result()


def _euro(valore: Any) -> str:
    try:
        numero = f"{Decimal(str(valore)).quantize(Decimal('0.01')):,}"
    except (InvalidOperation, ValueError):
        return html.escape(str(valore))
    return numero.replace(",", "X").replace(".", ",").replace("X", ".")


def _righe(movimenti: list[dict[str, Any]], limite: int = 200) -> str:
    if not movimenti:
        return "<p><small>Nessuno.</small></p>"
    righe = "".join(
        f"<tr><td>{lettura.data_it(m.get('data'))}</td>"
        f"<td style='text-align:right;font-variant-numeric:tabular-nums'>{_euro(m.get('importo'))}</td>"
        f"<td>{html.escape(str(m.get('descrizione_originale') or ''))[:140]}</td></tr>"
        for m in movimenti[:limite]
    )
    altre = f"<p><small>… e altri {len(movimenti) - limite}.</small></p>" if len(movimenti) > limite else ""
    return (
        "<table><tr><th>Data</th><th>Importo</th><th>Descrizione</th></tr>"
        f"{righe}</table>{altre}"
    )


def _righe_coppie(coppie: list[dict[str, Any]], limite: int = 200) -> str:
    if not coppie:
        return "<p><small>Nessuno.</small></p>"
    righe = "".join(
        f"<tr><td>{lettura.data_it(c['api'].get('data'))}</td>"
        f"<td style='text-align:right;font-variant-numeric:tabular-nums'>{_euro(c['api'].get('importo'))}</td>"
        f"<td><b>API:</b> {html.escape(str(c['api'].get('descrizione_originale') or ''))[:120]}<br>"
        f"<b>CSV:</b> {html.escape(str(c['csv'].get('descrizione_originale') or ''))[:120]}</td></tr>"
        for c in coppie[:limite]
    )
    altre = f"<p><small>… e altri {len(coppie) - limite}.</small></p>" if len(coppie) > limite else ""
    return (
        "<table><tr><th>Data</th><th>Importo</th><th>Descrizioni</th></tr>"
        f"{righe}</table>{altre}"
    )


STATI_LETTURA = {
    "ok": "Letto per intero",
    "consenso_scaduto": "Consenso scaduto o revocato: ricollega il conto",
    "limite_banca": "La banca ha raggiunto il limite di letture di oggi: riprova domani",
    "temporaneo": "Banca non raggiungibile dopo tre tentativi: riprova piu' tardi",
    "periodo_non_disponibile": "La banca non fornisce un periodo cosi' lungo: riduci i giorni",
    "cursore_bloccato": "Paginazione interrotta: la banca ripete la stessa pagina",
    "rifiutato": "Richiesta rifiutata dalla banca",
}


def _dettaglio_conti() -> str:
    blocchi = []
    for esito in _letture.values():
        saldi = "".join(
            f"<li>{html.escape(s['nome'] or s['tipo'])} ({html.escape(s['tipo'])}): "
            f"<b>{_euro(s['importo'])} {html.escape(s['divisa'])}</b> al {lettura.data_it(s['data'])}</li>"
            for s in esito.get("saldi", [])
        ) or "<li>Nessun saldo restituito</li>"
        riepilogo = esito.get("riepilogo") or {}
        altri = esito.get("altri_stati") or {}
        altri_testo = ", ".join(f"{html.escape(k)}: {v}" for k, v in sorted(altri.items())) or "nessuno"
        stato = esito.get("stato", "ok")
        blocchi.append(f"""
        <div class="card">
          <b>Conto:</b> <code>{html.escape(esito.get('conto', ''))}</code> {html.escape(esito.get('nome', ''))}<br>
          <b>Esito:</b> <span class="{'ok' if stato == 'ok' else 'wait'}">{html.escape(STATI_LETTURA.get(stato, stato))}</span><br>
          <b>Pagine lette:</b> <code>{esito.get('pagine', 0)}</code><br>
          <b>Movimenti contabilizzati:</b> <code>{riepilogo.get('conteggio', 0)}</code>
          dal <code>{lettura.data_it(riepilogo.get('dal'))}</code> al <code>{lettura.data_it(riepilogo.get('al'))}</code><br>
          <b>Entrate:</b> <code>{_euro(riepilogo.get('entrate', 0))}</code>
          <b>Uscite:</b> <code>{_euro(riepilogo.get('uscite', 0))}</code><br>
          <b>Non contabilizzati (esclusi):</b> <code>{altri_testo}</code><br>
          <b>Senza importo o data (esclusi):</b> <code>{esito.get('senza_importo_o_data', 0)}</code>
          <p><b>Saldi della banca</b></p><ul>{saldi}</ul>
        </div>""")
    return "".join(blocchi)


def _sezione_confronto() -> str:
    form = """
      <form method="post" action="/confronta-csv" enctype="multipart/form-data">
        <p>Carica l'export Banco BPM «Elenco entrate/uscite» (CSV) dello stesso periodo.
        Resta solo in memoria, non viene salvato.</p>
        <input type="file" name="csv" accept=".csv,text/csv" required>
        <button type="submit">Confronta</button>
      </form>
    """
    if not _confronto:
        return f'<div class="card" id="confronto"><h2>Confronto con il CSV</h2>{form}</div>'
    c = _confronto
    periodo = c.get("periodo_comune")
    periodo_testo = (
        f"dal {lettura.data_it(periodo[0])} al {lettura.data_it(periodo[1])}" if periodo
        else "nessun giorno in comune"
    )
    return f"""
    <div class="card" id="confronto">
      <h2>Confronto con il CSV</h2>
      <b>Periodo confrontato:</b> <code>{periodo_testo}</code><br>
      <b>Movimenti API:</b> <code>{c['api_movimenti']}</code> ·
      <b>righe CSV:</b> <code>{c['csv_movimenti']}</code>
      (illeggibili <code>{c['csv_illeggibili']}</code>)<br>
      <b>Fuori dal periodo comune:</b> API <code>{c['fuori_periodo_api']}</code>, CSV <code>{c['fuori_periodo_csv']}</code>
      <table>
        <tr><th>Nuovi (solo API)</th><td><b>{len(c['nuovi'])}</b></td></tr>
        <tr><th>Gia' presenti (stessa descrizione o assegno)</th><td><b>{len(c['gia_presenti'])}</b></td></tr>
        <tr><th>Ambigui, DA_VERIFICARE (solo data e importo)</th><td><b>{len(c['ambigui'])}</b></td></tr>
        <tr><th>Solo nel CSV (mancano dall'API)</th><td><b>{len(c['solo_nel_csv'])}</b></td></tr>
      </table>
      <h3>Nuovi</h3>{_righe(c['nuovi'])}
      <h3>Ambigui</h3>{_righe_coppie(c['ambigui'])}
      <h3>Solo nel CSV</h3>{_righe(c['solo_nel_csv'])}
      {form}
    </div>"""


@app.get("/result", response_class=HTMLResponse)
async def result(request: Request) -> str:
    data = _safe_result()
    ready = bool(data.get("ready"))
    status = "VERIFICA REALE COMPLETATA" if ready else "COLLEGAMENTO NON ANCORA COMPLETATO"
    status_class = "ok" if ready else "wait"
    transazioni = data.get("transactions", {})
    content = f"""
      <h1>Risultato Banco BPM</h1>
      <div class="card">
        <p class="{status_class}">{status}</p>
        <b>Sessione:</b> <code>{'OK' if data.get('connected') else 'NO'}</code><br>
        <b>Conti:</b> <code>{data.get('accounts', {}).get('count', 0)}</code><br>
        <b>Saldi verificati:</b> <code>{data.get('balances', {}).get('count', 0)}</code><br>
        <b>Movimenti letti:</b> <code>{transazioni.get('count', 0)}</code>
        in <code>{transazioni.get('pages', 0)}</code> pagine,
        ultimi <code>{transazioni.get('period_days', PERIODO_GIORNI_DEFAULT)}</code> giorni<br>
        <b>Sessione solo in memoria:</b> <code>{'SI' if data.get('session_present_in_memory') else 'NO'}</code>
      </div>
      <a class="button" href="/">Home</a>
    """
    if _is_viewer(request):
        content += f"""
      <div class="card">
        <b>Consenso valido fino al:</b> <code>{lettura.data_it(_consent_valid_until)}</code>
        <form method="post" action="/retest">
          <label>Periodo da leggere (giorni, max {PERIODO_GIORNI_MAX}):
            <input type="number" name="giorni" min="1" max="{PERIODO_GIORNI_MAX}"
                   value="{transazioni.get('period_days', PERIODO_GIORNI_DEFAULT)}"></label>
          <button type="submit">Rileggi</button>
        </form>
      </div>
      {_dettaglio_conti()}
      {_sezione_confronto()}
        """
    elif data.get("connected"):
        content += """
      <p><small>Saldi, movimenti e confronto si vedono solo dal browser che ha collegato il conto.</small></p>
        """
    return _page("Risultato Banco BPM", content)
