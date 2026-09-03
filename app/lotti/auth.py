"""
auth.py — Autenticazione centralizzata Lotti.

Modello:
  - Il PIN non "apre" più nulla da solo: viene verificato dal server e in cambio
    si riceve un TOKEN firmato (JWT HS256) da allegare a ogni richiesta in
    `Authorization: Bearer <token>`. Doppio controllo = qualcosa che sai (PIN) +
    token firmato dal server (non falsificabile).
  - `auth_dependency` è agganciata a TUTTO l'api_router. Rollout sicuro: finché
    la env `AUTH_ENFORCE` non è "true" NON blocca nulla (così si allinea prima il
    frontend e poi si accende, senza rischio di chiudere fuori nessuno).
  - Google Sign-In: verifica l'ID token contro le chiavi pubbliche Google.
    Dormiente finché non è impostata la env `GOOGLE_CLIENT_ID`.
  - Anti brute-force: lockout in memoria per IP.

Env usate (tutte opzionali, con default sicuri):
  AUTH_SECRET          segreto per firmare i JWT (consigliato impostarlo)
  AUTH_ENFORCE         "true" per attivare il blocco (default: false)
  AUTH_TOKEN_TTL_H     durata token in ore (default 12)
  AUTH_MAX_FAILS       tentativi PIN prima del lock (default 8)
  AUTH_LOCK_SECONDS    durata lock in secondi (default 300)
  GOOGLE_CLIENT_ID     abilita il login Google
  AUTH_GOOGLE_EMAILS   email autorizzate al login Google (CSV)
"""

import os
import time
import hashlib
import hmac
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt
from jwt import PyJWKClient
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

ALG = "HS256"


def _ttl_hours() -> int:
    try:
        return int(os.environ.get("AUTH_TOKEN_TTL_H", "12"))
    except ValueError:
        return 12


_RUNTIME_SECRET = None


def _secret() -> str:
    # LOTTI_AUTH_SECRET ha la precedenza (namespace proprio dentro GestionaleCloud),
    # poi il nome storico AUTH_SECRET.
    s = os.environ.get("LOTTI_AUTH_SECRET") or os.environ.get("AUTH_SECRET")
    if s:
        return s
    # Su Supabase non esiste più il Mongo usato per persistere la chiave. Il
    # secret server-only del document store è già stabile tra i deploy: ne
    # deriviamo una chiave distinta (mai esponiamo o riusiamo il valore grezzo).
    db_secret = os.environ.get("LOTTI_DB_SECRET")
    if db_secret:
        return hmac.new(
            db_secret.encode("utf-8"), b"lotti-auth-jwt-v1", hashlib.sha256
        ).hexdigest()
    # Nessun segreto configurato: niente chiave derivabile dal codice pubblico
    # (forgiabile). Chiave casuale forte per processo (non e' nel codice, quindi
    # non forgiabile; i token pero' NON sopravvivono al riavvio).
    global _RUNTIME_SECRET
    if _RUNTIME_SECRET is None:
        _RUNTIME_SECRET = _load_or_create_persistent_secret()
    return _RUNTIME_SECRET


def _load_or_create_persistent_secret() -> str:
    """Chiave JWT casuale per processo.

    Storicamente veniva persistita su Mongo (pymongo sincrono): dentro
    GestionaleCloud non esiste alcun server Mongo, quindi non si apre mai una
    connessione. Per token stabili tra i deploy impostare LOTTI_AUTH_SECRET
    (o AUTH_SECRET / LOTTI_DB_SECRET)."""
    import secrets as _secrets
    try:
        import logging
        logging.getLogger("uvicorn.error").warning(
            "[AUTH] nessun LOTTI_AUTH_SECRET/AUTH_SECRET/LOTTI_DB_SECRET: uso una "
            "chiave JWT casuale per processo (i login non sopravvivono al riavvio)"
        )
    except Exception:
        pass
    return _secrets.token_hex(32)


def make_token(sub: str, nome: str, ruolo: str, via: str = "pin", ore: int = None) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "nome": nome,
        "ruolo": ruolo,
        "via": via,
        "iat": now,
        "exp": now + timedelta(hours=ore if ore else _ttl_hours()),
    }
    return jwt.encode(payload, _secret(), algorithm=ALG)


def verify_token(token: str):
    try:
        return jwt.decode(token, _secret(), algorithms=[ALG])
    except Exception:
        return None


# ── Rotte sempre pubbliche (non richiedono token) ──────────────────────────
PUBLIC_PREFIXES = (
    "/api/health",
    "/api/auth/login",
    "/api/auth/google",
    "/api/auth/config",
    "/api/auth/me",
    "/api/tablet-operatori/login",
    "/api/tablet-operatori/logout",
    "/api/tablet-operatori/verifica",  # keep-warm / verifica sessione kiosk
    "/api/foto",  # immagini servite da Mongo: i tag <img> non mandano il token
)

# Scritture che gli operatori fanno DA TABLET senza login JWT (entrano col PIN
# del kiosk, non con token). Restano aperte finché il fronte non propaga il
# token anche lì; tutte le ALTRE scritture invece esigono token da subito.
# Solo il GESTO OPERATIVO del tablet, non l'amministrazione delle schede.
# (es: /scheda/.../registra apre il singolo timbro; il PUT /scheda/... che
#  riscrive l'intero registro, la config e il DELETE lotto esigono token.)
def _scrittura_tablet_consentita(path: str, method: str) -> bool:
    P = "/api"
    # timbro singolo temperatura/sanificazione del giorno
    if path.endswith("/registra") and (
        path.startswith(P + "/temperature-positive/scheda")
        or path.startswith(P + "/temperature-negative/scheda")
        or path.startswith(P + "/sanificazione/scheda")
    ):
        return True
    if path.startswith(P + "/sanificazione/scheda") and path.endswith("/giorno-completo"):
        return True
    if path.startswith(P + "/temperature-cottura") and method == "POST":
        return True
    # richiesta bar -> lavagna magazzino: crea(POST), evadi(PUT .../ok), cancella(DELETE)
    if path.startswith(P + "/magazzino-bar/richieste"):
        return True
    # creazione lotto / produzione da tablet (POST puro, NON delete/put admin)
    if path == P + "/lotti" and method == "POST":
        return True
    if path == P + "/gelati/produzioni" and method == "POST":
        return True
    if path.startswith(P + "/vendita-banco") and method == "POST":
        return True
    return False


def _percorso_api(request: Request) -> str:
    """Percorso della richiesta RELATIVO all'app Lotti.

    Montata come sotto-applicazione (``/lotti``) dentro GestionaleCloud,
    ``request.url.path`` contiene anche il prefisso del mount
    (``/lotti/api/auth/login``): senza toglierlo nessuna rotta risulterebbe
    pubblica e il login sarebbe impossibile. Standalone ``root_path`` e' vuoto
    e il percorso resta identico a prima."""
    path = request.url.path
    scope = getattr(request, "scope", None) or {}
    root = (scope.get("root_path") or "").rstrip("/")
    if root and path.startswith(root):
        path = path[len(root):] or "/"
    return path


def _enforce() -> bool:
    # DEFAULT acceso: anche le letture richiedono login (la porta e' chiusa davvero).
    # Disattivabile solo esplicitamente con AUTH_ENFORCE=false in caso di emergenza.
    return os.environ.get("AUTH_ENFORCE", "true").strip().lower() in ("1", "true", "yes", "on")


def _ha_token_valido(request: Request):
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    # I documenti aperti in una nuova scheda (window.open: report HACCP, stampa
    # lotto, registri PDF) non possono inviare l'header Authorization. Per loro si
    # accetta lo stesso token JWT passato come query string (?token=...): resta
    # un token valido, quindi la sicurezza è preservata.
    if not token:
        token = (
            request.query_params.get("token")
            or request.query_params.get("access_token")
            or ""
        ).strip()
    return verify_token(token) if token else None


def request_actor(request: Request | None) -> dict | None:
    """Restituisce esclusivamente l'identità verificata dal server."""
    if request is None:
        return None
    actor = getattr(getattr(request, "state", None), "user", None) or _ha_token_valido(request)
    if not actor:
        return None
    return {
        "id": actor.get("sub") or actor.get("id") or "",
        "nome": actor.get("nome") or "Operatore",
        "ruolo": actor.get("ruolo") or "operatore",
        "via": actor.get("via") or "pin",
    }


def automation_secret_valid(request: Request) -> bool:
    expected = os.environ.get("AUTOMATION_SECRET", "").strip()
    supplied = (request.headers.get("X-Automation-Key") or "").strip()
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


async def auth_dependency(request: Request):
    """Gate selettivo:
      - preflight CORS e rotte pubbliche: passano
      - GET (letture): passano (nessuno resta chiuso fuori)
      - scritture nelle aree-tablet (WRITE_PUBLIC): passano finché il fronte non
        propaga il token, ma SOLO quelle
      - ogni ALTRA scrittura (POST/PUT/DELETE): esige token valido SEMPRE,
        anche se AUTH_ENFORCE è spento -> la porta è chiusa a chiave da subito
      - se AUTH_ENFORCE è attivo: anche le letture esigono token
    """
    if request.method == "OPTIONS":
        return
    path = _percorso_api(request)
    for p in PUBLIC_PREFIXES:
        if path == p or path.startswith(p + "/"):
            return

    automation_paths = {
        "/api/scheduler/morning/run",
        "/api/ricette/deduplica-basi",
    }
    if request.method == "POST" and path in automation_paths and automation_secret_valid(request):
        request.state.user = {
            "sub": "github-scheduler",
            "nome": "Workflow mattutino Lotti",
            "ruolo": "automazione",
            "via": "automation_secret",
        }
        return

    data = _ha_token_valido(request)
    if data:
        request.state.user = data
        return  # autenticato: via libera

    metodo_di_scrittura = request.method in ("POST", "PUT", "DELETE", "PATCH")

    if metodo_di_scrittura:
        # scrittura senza token: ammessa solo per il gesto operativo del tablet
        if _scrittura_tablet_consentita(path, request.method):
            return
        # tutto il resto delle scritture è BLINDATO subito
        raise HTTPException(status_code=401, detail="Autenticazione richiesta per questa operazione")

    # è una lettura (GET/HEAD): blocca solo se l'enforcement è acceso
    if _enforce():
        raise HTTPException(status_code=401, detail="Autenticazione richiesta")
    return


async def require_admin(request: Request):
    """Gate di RUOLO per le operazioni riservate al titolare (ripristino/azzeramento
    dati, gestione personale/PIN, drop collezioni, backup).

    auth_dependency verifica solo che il token esista: NON guarda il ruolo, quindi
    un token dipendente supera il gate globale su TUTTE le rotte. Questa dipendenza
    va aggiunta esplicitamente agli endpoint distruttivi/di configurazione.

    Accetta due prove di identità admin:
      1. token JWT centrale con ruolo == amministratore (login col PIN admin);
      2. fallback header X-Admin-Pin (flussi tablet senza login centrale).
    """
    data = _ha_token_valido(request)
    if data and data.get("ruolo") == "amministratore":
        request.state.user = data
        return
    pin = (request.headers.get("X-Admin-Pin") or "").strip()
    if pin:
        try:
            from app.lotti.server import db  # import ritardato: evita ciclo all'avvio
            from app.lotti.routers.tablet_operatori import pin_amministratore_valido
            if await pin_amministratore_valido(pin):
                return
        except Exception:
            pass
    raise HTTPException(status_code=403, detail="Operazione riservata all'amministratore")


async def require_automation_or_admin(request: Request):
    if automation_secret_valid(request):
        return {
            "id": "github-scheduler",
            "nome": "Workflow mattutino Lotti",
            "ruolo": "automazione",
            "via": "automation_secret",
        }
    await require_admin(request)
    return request_actor(request)


# ── Anti brute-force (in memoria, per IP) ──────────────────────────────────
_FAILS: dict = {}


def _max_fails() -> int:
    try:
        return int(os.environ.get("AUTH_MAX_FAILS", "8"))
    except ValueError:
        return 8


def _lock_seconds() -> int:
    try:
        return int(os.environ.get("AUTH_LOCK_SECONDS", "300"))
    except ValueError:
        return 300


def check_lock(ip: str):
    rec = _FAILS.get(ip)
    if rec and rec[1] > time.time():
        wait = int(rec[1] - time.time())
        raise HTTPException(status_code=429, detail=f"Troppi tentativi. Riprova tra {wait}s")


def register_fail(ip: str):
    rec = _FAILS.get(ip, [0, 0.0])
    rec[0] += 1
    if rec[0] >= _max_fails():
        rec[1] = time.time() + _lock_seconds()
        rec[0] = 0
    _FAILS[ip] = rec


def clear_fails(ip: str):
    _FAILS.pop(ip, None)


# ── Google Sign-In (dormiente finché manca GOOGLE_CLIENT_ID) ───────────────
_GOOGLE_JWKS = None


def _google_jwks():
    global _GOOGLE_JWKS
    if _GOOGLE_JWKS is None:
        _GOOGLE_JWKS = PyJWKClient("https://www.googleapis.com/oauth2/v3/certs")
    return _GOOGLE_JWKS


def _google_allowed_emails():
    raw = os.environ.get("AUTH_GOOGLE_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def verify_google_id_token(id_token: str):
    cid = os.environ.get("GOOGLE_CLIENT_ID")
    if not cid:
        raise HTTPException(503, "Login Google non configurato (manca GOOGLE_CLIENT_ID)")
    try:
        signing_key = _google_jwks().get_signing_key_from_jwt(id_token).key
        data = jwt.decode(
            id_token,
            signing_key,
            algorithms=["RS256"],
            audience=cid,
            issuer=["https://accounts.google.com", "accounts.google.com"],
        )
    except Exception:
        raise HTTPException(401, "Token Google non valido")
    if not data.get("email_verified"):
        raise HTTPException(401, "Email Google non verificata")
    allow = _google_allowed_emails()
    email = (data.get("email") or "").lower()
    if allow and email not in allow:
        raise HTTPException(403, "Questa email Google non è autorizzata")
    return data


router = APIRouter(prefix="/auth", tags=["auth"])


class PinLoginReq(BaseModel):
    pin: str
    operatore_id: Optional[str] = None


@router.post("/login")
async def login_pin_jwt(payload: PinLoginReq, request: Request):
    """PIN -> token firmato. Verifica il PIN contro gli operatori reali."""
    from app.lotti.server import db  # import locale: evita cicli all'avvio
    ip = request.client.host if request.client else None
    if ip:
        check_lock(ip)
    pin = (payload.pin or "").strip()
    if len(pin) < 4:
        raise HTTPException(400, "PIN non valido")
    # 25/07/2026: il PIN non è più salvato in chiaro. Si cerca l'IMPRONTA
    # (HMAC col segreto dell'applicazione) e si conferma comunque con bcrypt.
    from app.lotti.routers.tablet_operatori import trova_operatori_per_pin
    docs = await trova_operatori_per_pin(pin)
    if not docs:
        if ip:
            register_fail(ip)
        raise HTTPException(401, "PIN non riconosciuto")
    if ip:
        clear_fails(ip)
    if payload.operatore_id:
        doc = next((d for d in docs if d.get("id") == payload.operatore_id), None)
        if not doc:
            raise HTTPException(403, "Identita' non associata a questo PIN")
    elif len(docs) == 1:
        doc = docs[0]
    else:
        return {
            "ok": True,
            "scelta_operatore": True,
            "operatori": [
                {"id": d.get("id"), "nome": d.get("nome"),
                 "ruolo": d.get("ruolo", "operatore")}
                for d in docs
            ],
        }
    token = make_token(sub=doc.get("id", "op"), nome=doc.get("nome", "Operatore"), ruolo=doc.get("ruolo", "operatore"), via="pin")
    return {"ok": True, "token": token, "operatore": {"id": doc.get("id"), "nome": doc.get("nome"), "ruolo": doc.get("ruolo")}}


class GoogleLogin(BaseModel):
    credential: str  # ID token restituito da Google Identity Services


@router.post("/google")
async def login_google(payload: GoogleLogin):
    data = verify_google_id_token(payload.credential)
    email = data.get("email")
    nome = data.get("name") or email
    token = make_token(sub=email, nome=nome, ruolo="amministratore", via="google")
    return {"ok": True, "token": token, "operatore": {"nome": nome, "ruolo": "amministratore", "email": email}}


@router.post("/refresh")
async def refresh_token(request: Request):
    """Un token ancora valido viene rinnovato senza re-inserire il PIN.
    Cosi' il kiosk sempre acceso non butta fuori l'operatore allo scadere."""
    data = _ha_token_valido(request)
    if not data:
        raise HTTPException(401, "Token assente o scaduto")
    nuovo = make_token(sub=data.get("sub", "op"), nome=data.get("nome", "Operatore"),
                       ruolo=data.get("ruolo", "operatore"), via=data.get("via", "pin"))
    return {"ok": True, "token": nuovo}


@router.get("/me")
async def me(request: Request):
    header = request.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    data = verify_token(token) if token else None
    if not data:
        raise HTTPException(401, "Token assente o non valido")
    return {"ok": True, "user": {"nome": data.get("nome"), "ruolo": data.get("ruolo"), "via": data.get("via")}}


@router.get("/config")
async def auth_config():
    """Il frontend lo chiama per sapere se mostrare il bottone Google e se
    l'enforcement è attivo. Il client_id Google è per natura pubblico."""
    return {
        "google_enabled": bool(os.environ.get("GOOGLE_CLIENT_ID")),
        "google_client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
        "enforce": _enforce(),
    }
