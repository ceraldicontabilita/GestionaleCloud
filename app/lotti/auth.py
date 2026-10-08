"""
auth.py — Autenticazione centralizzata Lotti.

Modello:
  - Il PIN personale viene verificato dal server nel solo ingresso
    `/tablet-operatori/login`; il JWT risultante si allega alle richieste in
    `Authorization: Bearer <token>`. PIN e token non sono due fattori distinti.
  - `auth_dependency` è agganciata a TUTTO l'api_router. `AUTH_ENFORCE` è
    attivo per default; le scritture non-tablet richiedono sempre un token.
  - L'amministratore entra dal Gestionale (`/auth/session`, cookie ERP) oppure
    dal tablet con il proprio PIN personale registrato in HR. La sessione ERP
    porta il `sid` e viene revocata dal logout del Gestionale; la sessione PIN
    resta legata all'identita' HR e alla versione del PIN. Il PIN centrale di
    amministrazione non e' un'identita' tablet e non viene accettato qui.
  - Anti brute-force: tentativi persistiti su Supabase, per client e globali.

Env usate (tutte opzionali, con default sicuri):
  AUTH_SECRET          segreto per firmare i JWT (consigliato impostarlo)
  AUTH_ENFORCE         "false" per disattivare l'enforcement delle letture in emergenza (default: true)
  AUTH_TOKEN_TTL_H     durata token in ore (default 12)
  LOTTI_SESSIONE_MAX_ORE / _ADMIN  durata massima dei rinnovi dal PIN (default 168 / 24)
  AUTH_MAX_FAILS       tentativi PIN prima del lock (default 8)
  AUTH_LOCK_SECONDS    durata lock in secondi (default 300)
  AUTH_MAX_FAILS_GLOBALI  PIN sbagliati da qualunque client in 15 minuti prima del blocco di tutti (default 40)
"""

import functools
import os
import time
import hashlib
import hmac
from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request
from app.services.workforce_tokens import create_workforce_token

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


def make_token(sub: str, nome: str, ruolo: str, via: str = "pin", ore: int = None, sid: str = "",
               auth_at: int = None, pin_version: str = None) -> str:
    return create_workforce_token(
        sub=sub,
        name=nome,
        role=ruolo,
        secret=_secret(),
        algorithm=ALG,
        expires_in=timedelta(hours=ore if ore else _ttl_hours()),
        auth_method=via,
        sid=sid,
        auth_at=auth_at,
        pin_version=pin_version,
    )


def _sessione_max_ore(ruolo: str) -> int:
    """Durata massima di una sessione dal PIN (o dall'ingresso admin): oltre,
    il rinnovo automatico si ferma e serve rientrare. Il tablet di reparto
    resta aperto una settimana; l'amministratore un giorno."""
    nome = "LOTTI_SESSIONE_MAX_ORE_ADMIN" if ruolo == "amministratore" else "LOTTI_SESSIONE_MAX_ORE"
    predefinito = 24 if ruolo == "amministratore" else 168
    try:
        return int(os.environ.get(nome, str(predefinito)))
    except ValueError:
        return predefinito


def verify_token(token: str):
    """Accetta i token di TUTTE le app del gruppo, non solo quelli di Lotti.

    Il PIN si inserisce per entrare, non per passare da una sezione all'altra:
    lo stesso operatore che apre il magazzino col suo PIN deve poter aprire il
    portale dipendenti senza rifarlo. La verifica condivisa prova entrambi i
    segreti (vedi `app/services/workforce_tokens.py`); un token scaduto o
    manomesso resta rifiutato come prima.
    """
    from app.services.workforce_tokens import verifica_token_condiviso

    return verifica_token_condiviso(token)


# ── Rotte sempre pubbliche (non richiedono token) ──────────────────────────
PUBLIC_PREFIXES = (
    "/api/health",
    "/api/auth/config",
    "/api/auth/me",
    "/api/auth/session",  # la sessione del Gestionale (cookie ERP) apre Lotti
    "/api/tablet-operatori/login",
    "/api/foto",  # immagini servite da Mongo: i tag <img> non mandano il token
)

def _percorso_api(request: Request) -> str:
    """Percorso della richiesta RELATIVO all'app Lotti.

    Montata come sotto-applicazione (``/lotti``) dentro GestionaleCloud,
    ``request.url.path`` contiene anche il prefisso del mount
    (``/lotti/api/tablet-operatori/login``): senza toglierlo nessuna rotta risulterebbe
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
    # Il token si accetta SOLO dall'header Authorization. Un JWT in query string
    # (?token=...) finisce nella cronologia del browser, nei log di accesso del
    # proxy, nell'header Referer e nella coda di stampa: non autentica più.
    # I documenti in nuova scheda il frontend li scarica con axios (header
    # Bearer) e li apre come blob (apriDocumentoAutenticato in auth.js).
    return verify_token(token) if token else None


async def _token_valido_e_non_revocato(request: Request):
    """Token firmato, non scaduto e, se nato dalla sessione del Gestionale,
    non revocato dal suo logout."""
    from app.services.group_session import token_di_gruppo_ammesso

    data = _ha_token_valido(request)
    if data and await token_di_gruppo_ammesso(data):
        return data
    # Il PIN personale HR del titolare e' emesso dal login tablet con ruolo
    # amministratore, ma non e' il vecchio PIN amministratore condiviso.
    # Eccezione SOLO Lotti: ruolo HR attuale, identita' canonica e versione
    # del PIN obbligatori, controllati anche sulle letture. HR/Menu/ERP
    # mantengono il loro confine di sessione amministrativa del Gestionale.
    if (data and data.get("ruolo") == "amministratore"
            and data.get("via") == "pin"
            and data.get("auth_method") == "pin"
            and isinstance(data.get("pin_version"), str) and data["pin_version"]):
        from app.hr.services.auth_dipendenti import sessione_pin_corrente

        dip = getattr(request.state, "dipendente_hr", None)
        if dip is None:
            dip = await _dipendente_hr_da_token(data)
        if (dip and dip.get("id") == data.get("sub")
                and dip.get("ruolo_app") == "admin"
                and dip.get("lotti_operatore") is not False
                and sessione_pin_corrente(dip, data)):
            request.state.dipendente_hr = dip
            return data
    return None


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
    """Gate unico dell'app Lotti:
      - preflight CORS e rotte pubbliche: passano
      - ogni scrittura esige sempre un token valido, anche se AUTH_ENFORCE è
        spento per un'emergenza sulle sole letture
      - se AUTH_ENFORCE è attivo: anche le letture esigono token

    Il frontend tablet installa l'interceptor Axios prima di mostrare le aree
    operative: non esiste più alcuna compatibilità che giustifichi mutazioni
    anonime. L'identità dell'operatore deve accompagnare ogni dato HACCP.
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

    data = await _token_valido_e_non_revocato(request)
    if data:
        if request.method in ("POST", "PUT", "DELETE", "PATCH") and (
            data.get("auth_method") or data.get("via")
        ) != "sessione_erp":
            from app.hr.services.auth_dipendenti import sessione_dipendente_corrente, sessione_pin_corrente

            dip = getattr(request.state, "dipendente_hr", None)
            if dip is None:
                dip = await _dipendente_hr_da_token(data)
            if not dip or dip.get("lotti_operatore") is False:
                raise HTTPException(401, "Sessione operatore revocata: rifare l'accesso")
            corrente = (
                await sessione_dipendente_corrente(data, dipendente=dip)
                if (data.get("auth_method") or data.get("via")) != "pin"
                else sessione_pin_corrente(dip, data)
            )
            if not corrente:
                raise HTTPException(401, "Sessione operatore revocata: rifare l'accesso")
            # Memoria limitata a QUESTA richiesta: il gate di ruolo puo'
            # riusare la stessa scheda senza una seconda lettura Supabase.
            request.state.dipendente_hr = dip
        request.state.user = data
        return  # autenticato: via libera

    metodo_di_scrittura = request.method in ("POST", "PUT", "DELETE", "PATCH")

    if metodo_di_scrittura:
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

    Richiede il token operativo con ruolo amministratore. Il PIN personale
    viene verificato al login tablet e non viene inviato di nuovo nelle API.
    """
    data = await _token_valido_e_non_revocato(request)
    if data and data.get("ruolo") == "amministratore":
        request.state.user = data
        return
    raise HTTPException(status_code=403, detail="Operazione riservata all'amministratore")


async def _dipendente_hr_da_token(data: dict) -> dict | None:
    """Identita' HR canonica; il tablet storico fornisce solo il collegamento."""
    sub = str(data.get("sub") or "")
    if not sub:
        return None
    from app.lotti.routers.tablet_operatori import _db_hr

    db_hr = _db_hr()
    if db_hr is None:
        raise HTTPException(503, "Anagrafica HR non disponibile: riprovare tra poco")
    try:
        from app.hr.services.auth_dipendenti import leggi_dipendente_per_sessione

        dip = await leggi_dipendente_per_sessione(sub, db=db_hr)
        if dip is None:
            # I JWT precedenti all'unificazione portavano l'id del tablet.
            # Nessun ruolo o flag attivo della proiezione autorizza la persona.
            from app.lotti.db import database as db_lotti

            op = await db_lotti.tablet_operatori.find_one(
                {"id": sub}, {"_id": 0, "hr_id": 1, "gestionale_dipendente_id": 1})
            identita = {str(v) for v in (
                (op or {}).get("hr_id"), (op or {}).get("gestionale_dipendente_id")
            ) if v}
            if len(identita) == 1:
                dip = await leggi_dipendente_per_sessione(identita.pop(), db=db_hr)
    except Exception:
        # La proiezione tablet puo' contenere un ruolo appena revocato in HR:
        # durante un guasto non puo' diventare una fonte di autorizzazione.
        raise HTTPException(503, "Anagrafica HR non disponibile: riprovare tra poco") from None
    return dip


async def profilo_da_token(data: dict, *, dipendente: dict | None = None) -> dict | None:
    """Ruolo e reparti attuali dalla scheda HR, senza cache di autorizzazioni."""
    from app.lotti.servizi import ruoli
    from app.hr.services.stato_rapporto import e_in_forza

    if not data:
        return None
    if data.get("ruolo") == ruoli.AMMINISTRATORE:
        return {"ruolo": ruoli.AMMINISTRATORE, "reparti": list(ruoli.REPARTI)}
    dip = dipendente if dipendente is not None else await _dipendente_hr_da_token(data)
    if not e_in_forza(dip) or dip.get("lotti_operatore") is False:
        return None
    return {"ruolo": ruoli.normalizza_ruolo(dip.get("lotti_ruolo")),
            "reparti": ruoli.normalizza_reparti(dip.get("lotti_reparti"))}


@functools.lru_cache(maxsize=None)
def require_permesso(permesso: str):
    """Gate di ruolo per le operazioni riservate (vedi ``servizi/ruoli.py``).

    Il titolare passa sempre; gli altri passano solo se il ruolo attuale
    della loro scheda HR ha quel permesso. 401 senza token valido, 403 con
    ``X-Error-Code: RUOLO_NON_AUTORIZZATO`` se il ruolo non basta. Per i
    permessi di reparto la rotta chiama poi ``verifica_reparto``. Una
    dipendenza per permesso (cache): si puo' sostituire nei test con
    ``app.dependency_overrides[require_permesso("ricette")]``."""
    from app.lotti.servizi import ruoli

    if permesso not in ruoli.PERMESSI:
        raise KeyError(f"Permesso sconosciuto: {permesso}")

    async def dipendenza(request: Request):
        data = await _token_valido_e_non_revocato(request)
        if not data:
            raise HTTPException(status_code=401, detail="Autenticazione richiesta per questa operazione")
        profilo = await profilo_da_token(data, dipendente=getattr(request.state, "dipendente_hr", None))
        if not profilo or not ruoli.ha_permesso(profilo["ruolo"], permesso):
            raise HTTPException(
                status_code=403,
                detail=f"Non puoi {ruoli.ETICHETTE_PERMESSO[permesso]}: serve il ruolo giusto nella scheda HR",
                headers={"X-Error-Code": "RUOLO_NON_AUTORIZZATO"},
            )
        request.state.user = data
        request.state.profilo = profilo
        return profilo

    dipendenza.__name__ = f"require_permesso_{permesso}"
    return dipendenza


def verifica_reparto(profilo: dict, reparto) -> None:
    """Dopo ``require_permesso`` (che restituisce il profilo): 403 se il
    reparto non è di chi opera. Il titolare lavora su tutti."""
    from app.lotti.servizi import ruoli

    if not isinstance(profilo, dict):
        # Chiamata interna (non HTTP): il parametro e' ancora il ``Depends``
        # di default. Le rotte HTTP ricevono sempre il profilo dal gate.
        return
    if not ruoli.reparto_ammesso(profilo.get("ruolo", ""), profilo.get("reparti") or [], reparto):
        raise HTTPException(
            status_code=403,
            detail=f"Reparto «{reparto or 'non indicato'}» non tuo: lo può modificare il suo caporeparto o il titolare",
            headers={"X-Error-Code": "REPARTO_NON_AUTORIZZATO"},
        )


async def verifica_reparto_ricetta(profilo: dict, ricetta_id: str) -> None:
    """Come ``verifica_reparto``, col reparto letto dalla ricetta. Una
    ricetta che non esiste passa: la rotta risponde 404 da sé."""
    if not isinstance(profilo, dict) or profilo.get("ruolo") == "amministratore":
        return
    from app.lotti.db import database as db

    ricetta = await db.ricette.find_one({"id": ricetta_id}, {"_id": 0, "reparto": 1})
    if ricetta is not None:
        verifica_reparto(profilo, ricetta.get("reparto"))


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


# ── Anti brute-force (persistente, per client e globale) ────────────────────
# I tentativi falliti stanno nella collezione ``pin_tentativi`` (archivio
# Supabase di Lotti), non nella memoria del processo: un riavvio o un deploy
# non azzerano più il conto. Oltre al limite per client c'è un limite
# **globale**: il login di Lotti è solo PIN (nessun nome), e l'IP arriva da
# intestazioni che un client può scrivere da sé, quindi senza un tetto
# complessivo bastava cambiare intestazione a ogni tentativo.
COLL_TENTATIVI = "pin_tentativi"
CHIAVE_GLOBALE = "globale"
CHIAVE_SCONOSCIUTA = "sconosciuto"


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


def _max_fails_globali() -> int:
    try:
        return int(os.environ.get("AUTH_MAX_FAILS_GLOBALI", "40"))
    except ValueError:
        return 40


FINESTRA_GLOBALE_S = 900


def _tentativi():
    from app.lotti.db import database

    return database[COLL_TENTATIVI]


def ip_richiesta(request) -> str:
    """IP del client vero. Davanti al servizio ci sono Cloudflare e Render:
    `request.client.host` e' il proxy, e contare li' i tentativi bloccava
    tutti i tablet insieme (o nessuno). Cloudflare sovrascrive sempre
    `CF-Connecting-IP`, quindi il client non puo' falsificarlo."""
    if request is None:
        return ""
    h = request.headers
    ip = (h.get("cf-connecting-ip") or (h.get("x-forwarded-for") or "").split(",")[0]).strip()
    if ip:
        return ip
    return request.client.host if request.client else ""


async def check_lock(chiave: str):
    """429 se il client o l'intero login sono bloccati. Una chiave vuota non
    salta il controllo: conta come «sconosciuto»."""
    ora = time.time()
    for k in (chiave or CHIAVE_SCONOSCIUTA, CHIAVE_GLOBALE):
        rec = await _tentativi().find_one({"_id": k})
        fino = float((rec or {}).get("bloccato_fino") or 0)
        if fino > ora:
            raise HTTPException(status_code=429, detail=f"Troppi tentativi. Riprova tra {int(fino - ora)}s")


async def register_fail(chiave: str):
    ora = time.time()
    coll = _tentativi()
    k = chiave or CHIAVE_SCONOSCIUTA
    rec = await coll.find_one({"_id": k}) or {}
    conto = int(rec.get("conto") or 0) + 1
    fino = float(rec.get("bloccato_fino") or 0)
    if conto >= _max_fails():
        fino, conto = ora + _lock_seconds(), 0
    await coll.update_one({"_id": k}, {"$set": {"conto": conto, "bloccato_fino": fino, "ultimo": ora}},
                          upsert=True)

    glob = await coll.find_one({"_id": CHIAVE_GLOBALE}) or {}
    inizio = float(glob.get("inizio_finestra") or 0)
    conto_g = int(glob.get("conto") or 0)
    if ora - inizio > FINESTRA_GLOBALE_S:
        inizio, conto_g = ora, 0
    conto_g += 1
    fino_g = float(glob.get("bloccato_fino") or 0)
    if conto_g >= _max_fails_globali():
        fino_g, conto_g, inizio = ora + _lock_seconds(), 0, ora
        import logging
        logging.getLogger(__name__).warning(
            "[lotti auth] %s PIN sbagliati in %ss: login bloccato per tutti per %ss",
            _max_fails_globali(), FINESTRA_GLOBALE_S, _lock_seconds())
    await coll.update_one({"_id": CHIAVE_GLOBALE},
                          {"$set": {"conto": conto_g, "inizio_finestra": inizio, "bloccato_fino": fino_g}},
                          upsert=True)


async def clear_fails(chiave: str):
    await _tentativi().delete_one({"_id": chiave or CHIAVE_SCONOSCIUTA})


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/refresh")
async def refresh_token(request: Request):
    """Un token ancora valido viene rinnovato senza re-inserire il PIN.
    Cosi' il kiosk sempre acceso non butta fuori l'operatore allo scadere."""
    data = await _token_valido_e_non_revocato(request)
    if not data:
        raise HTTPException(401, "Token assente o scaduto")
    # La catena dei rinnovi ha una fine: si misura dal momento dell'ingresso
    # vero (``auth_at``; per i token nati prima, il loro ``iat``).
    ruolo = data.get("ruolo", "operatore")
    auth_at = int(data.get("auth_at") or data.get("iat") or 0)
    if not auth_at or time.time() - auth_at > _sessione_max_ore(ruolo) * 3600:
        raise HTTPException(401, "Sessione scaduta: rientra col PIN")
    # Il rinnovo conserva il legame con la sessione del Gestionale: senza
    # `sid` un token rinnovato sopravviverebbe al logout.
    nuovo = make_token(sub=data.get("sub", "op"), nome=data.get("nome", "Operatore"),
                       ruolo=ruolo, via=data.get("via", "pin"),
                       sid=data.get("sid", ""), auth_at=auth_at,
                       pin_version=data.get("pin_version"))
    return {"ok": True, "token": nuovo}


@router.get("/session")
async def sessione_dal_gestionale(request: Request):
    """L'amministratore gia' entrato nel Gestionale apre Lotti senza PIN.

    La prova e' il cookie di sessione dell'ERP (vedi
    `app/services/group_session.py`). Lotti restituisce un proprio token, mai
    quello dell'ERP. Il titolare e' l'unico operatore amministratore attivo
    (anagrafica HR): con lui il token porta la sua identita' e vale anche per
    firmare. Se non e' univoco, il token apre le pagine ma non firma."""
    from app.lotti.db import database as db
    from app.services.group_session import sessione_erp

    identita = await sessione_erp(request)
    if not identita:
        raise HTTPException(status_code=401, detail="Nessuna sessione del Gestionale")
    titolari = await db.tablet_operatori.find(
        {"ruolo": "amministratore", "attivo": True}, {"_id": 0, "hr_id": 1, "nome": 1}
    ).to_list(5)
    if len(titolari) == 1 and titolari[0].get("hr_id"):
        sub, nome, dipendente_id = titolari[0]["hr_id"], titolari[0].get("nome") or identita["name"], titolari[0]["hr_id"]
    else:
        sub, nome, dipendente_id = f"erp:{identita['user_id']}", identita["name"], None
    return {
        "token": make_token(sub, nome, "amministratore", via="sessione_erp", sid=identita["sid"]),
        "operatore": {"nome": nome, "ruolo": "amministratore", "dipendente_id": dipendente_id},
    }


@router.get("/me")
async def me(request: Request):
    data = await _token_valido_e_non_revocato(request)
    if not data:
        raise HTTPException(401, "Token assente o non valido")
    from app.lotti.servizi import ruoli

    profilo = await profilo_da_token(data)
    return {"ok": True,
            "user": {"dipendente_id": data.get("sub"), "nome": data.get("nome"), "ruolo": data.get("ruolo"), "via": data.get("via")},
            "profilo": ruoli.profilo_ruolo(profilo["ruolo"], profilo["reparti"]) if profilo else None}


@router.get("/config")
async def auth_config():
    """Il frontend lo chiama per sapere se l'enforcement delle letture è attivo."""
    return {"enforce": _enforce()}
