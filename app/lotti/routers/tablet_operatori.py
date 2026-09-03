"""
tablet_operatori.py
-------------------
Gestione accesso operatori tablet via PIN.

SICUREZZA — rifatta il 25/07/2026 dopo l'audit (decisione di Enzo: «procedi
per i pin, si usa la soluzione migliore»). Come stava prima:

  * il PIN di ogni dipendente era salvato IN CHIARO nel database (`pin_chiaro`)
    accanto a quello cifrato, e un comando lo restituiva all'amministratore:
    chi riusciva a leggere il database leggeva tutti i PIN, cifratura inutile;
  * i PIN erano scritti anche NEL CODICE (lista dei dipendenti di partenza),
    quindi finiti dentro la cronologia del repository;
  * peggio: a ogni riavvio del server la lista del codice RIMETTEVA il PIN di
    partenza dentro `pin_chiaro`. Siccome il login controllava prima quello,
    **un PIN cambiato dall'amministratore non revocava il vecchio**: quello
    vecchio tornava valido al primo riavvio.

Come sta adesso:

  * il PIN si verifica con bcrypt (`pin`), come prima;
  * per non dover provare bcrypt su tutti i dipendenti a ogni accesso c'è
    `pin_lookup`: un'impronta HMAC-SHA256 del PIN calcolata con il segreto
    dell'applicazione (che sta nelle variabili d'ambiente di Render, NON nel
    database). Serve solo a trovare la riga giusta in un colpo; da sola non
    permette di risalire al PIN, e il controllo vero resta bcrypt;
  * `pin_chiaro` non viene più scritto e viene CANCELLATO dai documenti
    esistenti all'avvio (dopo aver calcolato `pin_lookup`, così nessuno resta
    fuori);
  * nessun PIN è più scritto nel codice: alla prima installazione i
    dipendenti nascono SENZA PIN e l'amministratore glielo assegna;
  * al posto di «vedi i PIN» c'è «Reimposta PIN»: se un dipendente lo
    dimentica, l'amministratore gliene assegna uno nuovo.
"""

import hashlib
import hmac
import os
import re
import secrets
import unicodedata
import uuid
from datetime import datetime, timezone

import bcrypt
import httpx
from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import Optional
from app.lotti.db import database as db
from app.lotti.auth import make_token, check_lock, register_fail, clear_fails, require_admin, _secret

router = APIRouter(prefix="/tablet-operatori", tags=["tablet_operatori"])

_LOG_PIN = __import__("logging").getLogger("uvicorn.error")


def _hash_pin(pin: str) -> str:
    return bcrypt.hashpw(pin.encode(), bcrypt.gensalt()).decode()


def _verify_pin(pin: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pin.encode(), hashed.encode())
    except Exception:
        return False


def _pin_lookup(pin: str) -> str:
    """Impronta del PIN per ritrovare la riga in un colpo solo, SENZA tenerlo
    in chiaro. È un HMAC col segreto dell'applicazione: chi legge il database
    non ha il segreto, quindi non può risalire al PIN. Non sostituisce bcrypt:
    dopo la ricerca il PIN viene comunque verificato."""
    return hmac.new(_secret().encode(), pin.encode(), hashlib.sha256).hexdigest()


# Nomi dei dipendenti storici, SENZA PIN: i PIN non stanno più nel codice
# (finivano nella cronologia del repository). Alla prima installazione queste
# persone nascono senza PIN e l'amministratore glielo assegna dalla pagina
# Personale. In produzione il database è già popolato: questa lista non tocca
# niente.
NOMI_DEFAULT = [
    "Pocci", "Moscato", "Parisi", "Vespa", "Capezzuto", "Carotenuto",
    "Murolo", "Lisina", "Russo", "Viviana", "Guarino", "Taiano",
    "Kikko", "Thimira",
]

# Vincenzo e Valerio sono due persone distinte (e devono quindi produrre log,
# registrazioni e cedolini distinti), ma per scelta aziendale condividono la
# stessa credenziale di ingresso amministrativa. Il gruppo serve esclusivamente
# a sincronizzare il PIN: l'identita' viene sempre scelta dopo la verifica.
GRUPPO_PIN_ADMIN_CERALDI = "amministratori_ceraldi"
AMMINISTRATORI_CERALDI = (
    ("Ceraldi Vincenzo", {"ceraldi vincenzo", "vincenzo ceraldi"}),
    ("Ceraldi Valerio", {"ceraldi valerio", "valerio ceraldi"}),
)


def _nome_normalizzato(nome: str) -> str:
    return " ".join(str(nome or "").strip().casefold().split())


async def _assicura_amministratori_ceraldi() -> int:
    """Migrazione idempotente dell'accesso condiviso Vincenzo/Valerio.

    Copia hash bcrypt e impronta HMAC gia' presenti, quindi non richiede e non
    espone il PIN leggibile. Le due righe restano separate e ricevono ID/token
    diversi. La vecchia riga generica ``Amministratore`` viene disattivata per
    evitare una terza identita' fittizia nei log.
    """
    docs = await db.tablet_operatori.find(
        {},
        {
            "_id": 0, "id": 1, "nome": 1, "ruolo": 1, "attivo": 1,
            "pin": 1, "pin_lookup": 1, "pin_da_impostare": 1,
        },
    ).to_list(500)

    per_nome = {_nome_normalizzato(d.get("nome")): d for d in docs}
    nomi_ceraldi = set().union(*(varianti for _, varianti in AMMINISTRATORI_CERALDI))
    nominativi = [d for d in docs if _nome_normalizzato(d.get("nome")) in nomi_ceraldi]

    def ha_credenziale(d):
        return bool(d and d.get("pin")) and not d.get("pin_da_impostare")

    # Vincenzo e' la fonte preferita per mantenere il PIN gia' funzionante in
    # produzione. Le alternative coprono installazioni storiche differenti.
    fonte = next(
        (d for nome in ("ceraldi vincenzo", "vincenzo ceraldi")
         if ha_credenziale(d := per_nome.get(nome))),
        None,
    )
    if fonte is None:
        fonte = next((d for d in nominativi if ha_credenziale(d)), None)
    if fonte is None:
        fonte = next(
            (d for d in docs if _nome_normalizzato(d.get("nome")) == "amministratore"
             and d.get("attivo") is not False and ha_credenziale(d)),
            None,
        )

    credenziale = {}
    if fonte:
        credenziale = {
            "pin": fonte.get("pin"),
            "pin_da_impostare": False,
        }
        if fonte.get("pin_lookup"):
            credenziale["pin_lookup"] = fonte["pin_lookup"]

    aggiornati = 0
    for nome_canonico, varianti in AMMINISTRATORI_CERALDI:
        esistente = next(
            (d for d in docs if _nome_normalizzato(d.get("nome")) in varianti),
            None,
        )
        valori = {
            "nome": nome_canonico,
            "ruolo": "amministratore",
            "attivo": True,
            "gruppo_pin": GRUPPO_PIN_ADMIN_CERALDI,
            "identita_dipendente": True,
            **credenziale,
        }
        if esistente and esistente.get("id"):
            await db.tablet_operatori.update_one(
                {"id": esistente["id"]},
                {"$set": valori, "$unset": {"pin_chiaro": ""}},
            )
        else:
            await db.tablet_operatori.insert_one({
                "id": str(uuid.uuid4()),
                "pin": "",
                "pin_da_impostare": not bool(credenziale),
                **valori,
            })
        aggiornati += 1

    # Non cancelliamo la riga storica: la rendiamo inattiva e quindi il
    # ripristino resta reversibile. I due nominativi reali la sostituiscono.
    await db.tablet_operatori.update_many(
        {
            "nome": {"$regex": r"^\s*amministratore\s*$", "$options": "i"},
            "gruppo_pin": {"$ne": GRUPPO_PIN_ADMIN_CERALDI},
        },
        {"$set": {
            "attivo": False,
            "sostituito_da_gruppo": GRUPPO_PIN_ADMIN_CERALDI,
        }},
    )
    return aggiornati


async def _migra_via_pin_chiaro() -> int:
    """UNA TANTUM: calcola `pin_lookup` dal vecchio `pin_chiaro` e poi lo
    CANCELLA. Fatto in quest'ordine nessuno resta fuori: chi entrava prima
    entra anche dopo, ma il PIN sparisce dal database."""
    ripuliti = 0
    docs = await db.tablet_operatori.find(
        {"pin_chiaro": {"$exists": True}},
        {"_id": 1, "pin": 1, "pin_chiaro": 1, "pin_lookup": 1},
    ).to_list(500)
    for d in docs:
        pin = str(d.get("pin_chiaro") or "").strip()
        upd = {"$unset": {"pin_chiaro": ""}}
        if pin:
            valori = {}
            if not d.get("pin_lookup"):
                valori["pin_lookup"] = _pin_lookup(pin)
            # Alcuni backup storici avevano il PIN leggibile ma non il relativo
            # hash bcrypt (o conservavano un hash vecchio). Cancellare il campo
            # leggibile senza rigenerare bcrypt rendeva il PIN irrecuperabile.
            if not _verify_pin(pin, d.get("pin", "")):
                valori["pin"] = _hash_pin(pin)
            if valori:
                upd["$set"] = valori
        await db.tablet_operatori.update_one({"_id": d["_id"]}, upd)
        ripuliti += 1
    if ripuliti:
        _LOG_PIN.warning(
            f"[sicurezza] rimossi {ripuliti} PIN in chiaro dal database "
            "(sostituiti da un'impronta non reversibile)"
        )
    return ripuliti


async def _applica_recupero_admin_da_env() -> bool:
    """Ripristina una sola volta il PIN di Ceraldi Vincenzo da Render.

    ``ADMIN_PIN_RECOVERY`` è un segreto operativo temporaneo: non viene mai
    salvato in chiaro nel database. Ogni suo valore può essere applicato una
    sola volta, così lasciarlo accidentalmente configurato non resuscita il
    PIN dopo una successiva modifica fatta dall'amministratore.
    """
    pin = (os.environ.get("ADMIN_PIN_RECOVERY") or "").strip()
    if not pin:
        return False
    if not pin.isdigit() or not 4 <= len(pin) <= 6:
        _LOG_PIN.error(
            "[sicurezza] ADMIN_PIN_RECOVERY ignorato: deve contenere da 4 a 6 cifre"
        )
        return False

    fingerprint = hmac.new(
        _secret().encode(), f"admin-recovery:{pin}".encode(), hashlib.sha256
    ).hexdigest()
    chiave_marker = f"admin_pin_recovery:{fingerprint}"
    gia_applicato = await db.sistema_stato.find_one(
        {"chiave": chiave_marker, "stato": "applicato"}, {"_id": 1}
    )
    if gia_applicato:
        return False

    operatore = await db.tablet_operatori.find_one(
        {
            "nome": {"$regex": r"^\s*(ceraldi\s+vincenzo|vincenzo\s+ceraldi)\s*$", "$options": "i"}
        },
        {"_id": 0, "id": 1},
    )
    valori = {
        "nome": "Ceraldi Vincenzo",
        "ruolo": "amministratore",
        "attivo": True,
        "pin": _hash_pin(pin),
        "pin_lookup": _pin_lookup(pin),
        "pin_da_impostare": False,
        "pin_recupero_emergenza": True,
    }
    if operatore and operatore.get("id"):
        await db.tablet_operatori.update_one(
            {"id": operatore["id"]},
            {"$set": valori, "$unset": {"pin_chiaro": ""}},
        )
    else:
        await db.tablet_operatori.insert_one({"id": str(uuid.uuid4()), **valori})

    await db.sistema_stato.update_one(
        {"chiave": chiave_marker},
        {"$set": {
            "chiave": chiave_marker,
            "stato": "applicato",
            "applicato_at": datetime.now(timezone.utc),
            "operatore": "Ceraldi Vincenzo",
        }},
        upsert=True,
    )
    _LOG_PIN.warning(
        "[sicurezza] recupero PIN amministratore applicato a Ceraldi Vincenzo; "
        "rimuovere ADMIN_PIN_RECOVERY da Render"
    )
    return True


async def seed_operatori():
    """Alla PRIMA installazione crea le persone senza PIN + un amministratore
    con un PIN iniziale preso da ADMIN_PIN_INIZIALE (variabile d'ambiente
    Render); se non c'è, ne genera uno a caso e lo scrive UNA VOLTA nel log del
    server, così non finisce né nel codice né nel database in chiaro.
    Se il database è già popolato NON tocca nulla, si limita alla bonifica dei
    PIN in chiaro: prima invece rimetteva i PIN di partenza a ogni riavvio,
    facendo tornare valido un PIN che l'amministratore aveva cambiato."""
    # La bonifica non deve MAI impedire l'avvio: `seed_operatori()` è chiamato
    # da server.py senza rete di sicurezza, e un intoppo del database qui
    # terrebbe l'app spenta. Se fallisce si riprova al riavvio dopo; nel
    # frattempo l'accesso funziona lo stesso (bcrypt).
    try:
        await _migra_via_pin_chiaro()
    except Exception as e:
        _LOG_PIN.warning(f"[sicurezza] bonifica PIN in chiaro rimandata: {e}")

    count = await db.tablet_operatori.count_documents({})
    if count > 0:
        await _applica_recupero_admin_da_env()
        await _assicura_amministratori_ceraldi()
        return

    docs = [
        {"id": str(uuid.uuid4()), "nome": nome, "pin": "", "ruolo": "operatore",
         "attivo": True, "pin_da_impostare": True}
        for nome in NOMI_DEFAULT
    ]
    pin_admin = (os.environ.get("ADMIN_PIN_INIZIALE") or "").strip()
    generato = False
    if len(pin_admin) < 4:
        pin_admin = "".join(secrets.choice("0123456789") for _ in range(6))
        generato = True
    docs.append({
        "id": str(uuid.uuid4()), "nome": "Amministratore",
        "pin": _hash_pin(pin_admin), "pin_lookup": _pin_lookup(pin_admin),
        "ruolo": "amministratore", "attivo": True,
    })
    await db.tablet_operatori.insert_many(docs)
    await _applica_recupero_admin_da_env()
    await _assicura_amministratori_ceraldi()
    if generato:
        _LOG_PIN.warning(
            "[sicurezza] primo avvio: creato l'amministratore con un PIN "
            f"generato a caso: {pin_admin} — cambialo subito dalla pagina "
            "Personale. Questo messaggio non verrà più ripetuto."
        )


class PinLogin(BaseModel):
    pin: str
    operatore_id: Optional[str] = None


class NuovoDipendente(BaseModel):
    nome: str
    pin: str
    ruolo: Optional[str] = "operatore"
    mansione: Optional[str] = ""
    postazione: Optional[str] = ""
    libretto_sanitario_scadenza: Optional[str] = ""
    cognome: Optional[str] = ""
    codice_fiscale: Optional[str] = ""


class AggiornaDipendente(BaseModel):
    mansione: Optional[str] = None
    postazione: Optional[str] = None
    libretto_sanitario_scadenza: Optional[str] = None
    cognome: Optional[str] = None
    nome: Optional[str] = None
    ruolo: Optional[str] = None
    codice_fiscale: Optional[str] = None
    pin: Optional[str] = None


class AbilitaDipendente(BaseModel):
    gestionale_dipendente_id: Optional[str] = ""
    codice_fiscale: str
    nome: str
    pin: str
    cognome: Optional[str] = ""
    mansione: Optional[str] = ""
    postazione: Optional[str] = ""
    libretto_sanitario_scadenza: Optional[str] = ""


class CollegaDipendente(BaseModel):
    operatore_id: str
    gestionale_dipendente_id: str
    codice_fiscale: Optional[str] = ""


def _name_tokens(value: str) -> tuple[str, ...]:
    clean = unicodedata.normalize("NFKD", str(value or ""))
    clean = "".join(c for c in clean if not unicodedata.combining(c))
    return tuple(sorted(re.findall(r"[a-z0-9]+", clean.casefold())))


class PinAdmin(BaseModel):
    pin: str


async def pin_amministratore_valido(pin: str) -> bool:
    """Il PIN dato appartiene a un amministratore attivo? Unico punto in cui
    si risponde a questa domanda: prima la stessa verifica era ripetuta in tre
    file diversi, tutti e tre leggendo il PIN in chiaro dal database."""
    pin = (pin or "").strip()
    if len(pin) < 4:
        return False
    return any(
        d.get("ruolo") == "amministratore"
        for d in await trova_operatori_per_pin(pin)
    )


async def _richiedi_pin_amministratore(
    pin: str, request: Request = None, dettaglio: str = "PIN amministratore non valido"
) -> None:
    """Verifica amministratore mantenendo il blocco anti tentativi ripetuti."""
    ip = request.client.host if (request and request.client) else None
    if ip:
        check_lock(ip)
    if await pin_amministratore_valido(pin):
        if ip:
            clear_fails(ip)
        return
    if ip:
        register_fail(ip)
    raise HTTPException(403, dettaglio)


def _op_response(doc):
    op = {"id": doc.get("id") or str(uuid.uuid4()), "nome": doc.get("nome", "Operatore"), "ruolo": doc.get("ruolo", "operatore")}
    token = make_token(sub=op["id"], nome=op["nome"], ruolo=op["ruolo"], via="pin")
    return {"ok": True, "token": token, "operatore": op}


async def trova_operatori_per_pin(pin: str):
    """Trova tutti gli operatori attivi associati al PIN verificato.

    La riparazione usa esclusivamente il PIN appena digitato: se la sua HMAC
    coincide con ``pin_lookup`` già presente, ricrea l'hash bcrypt mancante o
    rimasto disallineato dalla vecchia migrazione. Il PIN non viene registrato
    in chiaro e il percorso normale continua a richiedere anche bcrypt. Il
    risultato multiplo e' intenzionale per il gruppo amministratori Ceraldi:
    il client dovra' scegliere la persona prima di ricevere il token.
    """
    lookup = _pin_lookup(pin)
    docs = await db.tablet_operatori.find(
        {"attivo": True, "pin_lookup": lookup},
        {"_id": 0, "id": 1, "nome": 1, "ruolo": 1, "pin": 1,
         "pin_lookup": 1, "gruppo_pin": 1},
    ).to_list(200)
    trovati = []
    ids = set()
    # Nel gruppo amministratori Vincenzo e Valerio condividono volutamente lo
    # stesso hash. Verificare due volte lo stesso bcrypt raddoppia il tempo di
    # accesso; inoltre, dopo aver gia' trovato il PIN tramite la sua impronta,
    # scandire tutti gli altri dipendenti portava il tablet oltre il timeout di
    # 15 secondi. Ogni hash distinto si verifica una sola volta e il fallback
    # globale si usa soltanto quando l'impronta non ha prodotto alcun risultato.
    verifiche_hash = {}
    for doc in docs:
        pin_hash = doc.get("pin", "")
        if pin_hash not in verifiche_hash:
            verifiche_hash[pin_hash] = _verify_pin(pin, pin_hash)
        if verifiche_hash[pin_hash]:
            trovati.append(doc)
            ids.add(doc.get("id"))
            continue

        # ``pin_lookup`` è stato creato dal PIN in chiaro prima di cancellarlo.
        # Una corrispondenza HMAC col segreto del server prova che il valore
        # appena inserito è proprio quello migrato: possiamo ricreare bcrypt una
        # sola volta senza conoscere, esporre o salvare il PIN leggibile.
        if hmac.compare_digest(str(doc.get("pin_lookup") or ""), lookup):
            nuovo_hash = _hash_pin(pin)
            await db.tablet_operatori.update_one(
                {"id": doc.get("id"), "attivo": True, "pin_lookup": lookup},
                {"$set": {
                    "pin": nuovo_hash,
                    "pin_da_impostare": False,
                    "pin_hash_riparato": True,
                }},
            )
            doc["pin"] = nuovo_hash
            trovati.append(doc)
            ids.add(doc.get("id"))

    if trovati:
        return trovati

    # Compatibilità con operatori che hanno bcrypt ma non ancora l'impronta,
    # oppure con un AUTH_SECRET ruotato: bcrypt resta la fonte di verità.
    dipendenti = await db.tablet_operatori.find(
        {"attivo": True}, {"_id": 0, "id": 1, "nome": 1, "pin": 1, "ruolo": 1}
    ).to_list(200)
    for d in dipendenti:
        if d.get("id") not in ids and d.get("pin") and _verify_pin(pin, d["pin"]):
            await db.tablet_operatori.update_one(
                {"id": d.get("id")}, {"$set": {"pin_lookup": lookup}}
            )
            d["pin_lookup"] = lookup
            trovati.append(d)
            ids.add(d.get("id"))
    return trovati


async def trova_operatore_per_pin(pin: str):
    """Compatibilita' interna: restituisce solo se il PIN identifica una persona."""
    trovati = await trova_operatori_per_pin(pin)
    return trovati[0] if len(trovati) == 1 else None


@router.post("/login")
async def login_pin(payload: PinLogin, request: Request = None):
    ip = (request.client.host if (request and request.client) else None)
    if ip:
        check_lock(ip)
    pin = (payload.pin or "").strip()
    if len(pin) < 4:
        raise HTTPException(400, "PIN non valido")

    docs = await trova_operatori_per_pin(pin)
    if docs:
        if ip:
            clear_fails(ip)
        if payload.operatore_id:
            doc = next((d for d in docs if d.get("id") == payload.operatore_id), None)
            if not doc:
                raise HTTPException(403, "Identita' non associata a questo PIN")
            return _op_response(doc)
        if len(docs) == 1:
            return _op_response(docs[0])
        return {
            "ok": True,
            "scelta_operatore": True,
            "operatori": [
                {"id": d.get("id"), "nome": d.get("nome", "Operatore"),
                 "ruolo": d.get("ruolo", "operatore")}
                for d in docs
            ],
        }

    if ip:
        register_fail(ip)
    raise HTTPException(401, "PIN non riconosciuto")


class LogoutPayload(BaseModel):
    nome: Optional[str] = ""
    reparto: Optional[str] = ""


@router.post("/logout")
async def logout(payload: LogoutPayload):
    return {"ok": True}


@router.get("")
async def lista_dipendenti():
    docs = await db.tablet_operatori.find({"attivo": True}, {"_id": 0, "pin": 0, "pin_lookup": 0}).to_list(200)
    return docs


@router.post("")
async def crea_dipendente(payload: NuovoDipendente, _admin=Depends(require_admin)):
    pin = (payload.pin or "").strip()
    if len(pin) < 4:
        raise HTTPException(400, "PIN minimo 4 cifre")
    doc = {
        "id": str(uuid.uuid4()),
        "nome": payload.nome.strip(),
        "cognome": (payload.cognome or "").strip(),
        "codice_fiscale": (payload.codice_fiscale or "").strip().upper(),
        "pin": _hash_pin(pin),
        "pin_lookup": _pin_lookup(pin),
        "ruolo": payload.ruolo or "operatore",
        "mansione": (payload.mansione or "").strip(),
        "postazione": (payload.postazione or "").strip(),
        "libretto_sanitario_scadenza": (payload.libretto_sanitario_scadenza or "").strip(),
        "attivo": True,
    }
    await db.tablet_operatori.insert_one(doc)
    doc.pop("pin", None); doc.pop("pin_lookup", None); doc.pop("_id", None)
    return doc


@router.get("/nuovi-dipendenti")
async def nuovi_dipendenti():
    base_url = (os.environ.get("GESTIONALECLOUD_API_URL") or "").strip().rstrip("/")
    secret = (os.environ.get("LOTTI_INTEGRATION_KEY") or "").strip()
    if not base_url or not secret:
        return {"nuovi": [], "totale": 0, "configurato": False,
                "messaggio": "Collegamento al GestionaleCloud non configurato"}
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(
                f"{base_url}/api/integrations/lotti/employees",
                headers={"X-Lotti-Key": secret},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        _LOG_PIN.warning("[personale] elenco GestionaleCloud non disponibile: %s", exc)
        return {"nuovi": [], "totale": 0, "configurato": True,
                "messaggio": "GestionaleCloud non raggiungibile"}

    sorgente = payload.get("data") if isinstance(payload, dict) else []
    sorgente = sorgente if isinstance(sorgente, list) else []
    operatori = await db.tablet_operatori.find(
        {"attivo": True},
        {"_id": 0, "id": 1, "nome": 1, "cognome": 1,
         "codice_fiscale": 1, "gestionale_dipendente_id": 1},
    ).to_list(500)
    ignorati = await db.tablet_operatori_ignorati.find(
        {"ignorato": True}, {"_id": 0, "codice_fiscale": 1,
                             "gestionale_dipendente_id": 1}
    ).to_list(500)
    ids_esistenti = {str(o.get("gestionale_dipendente_id") or "") for o in operatori}
    cf_esistenti = {str(o.get("codice_fiscale") or "").strip().upper() for o in operatori}
    ids_ignorati = {str(o.get("gestionale_dipendente_id") or "") for o in ignorati}
    cf_ignorati = {str(o.get("codice_fiscale") or "").strip().upper() for o in ignorati}

    nuovi = []
    for dip in sorgente:
        source_id = str(dip.get("source_id") or "").strip()
        cf = str(dip.get("codice_fiscale") or "").strip().upper()
        if not source_id or source_id in ids_esistenti or source_id in ids_ignorati:
            continue
        if cf and (cf in cf_esistenti or cf in cf_ignorati):
            continue
        item = {
            "gestionale_dipendente_id": source_id,
            "nome": str(dip.get("nome") or dip.get("nome_completo") or "").strip(),
            "cognome": str(dip.get("cognome") or "").strip(),
            "codice_fiscale": cf,
            "mansione": str(dip.get("mansione") or "").strip(),
            "matricola": str(dip.get("matricola") or "").strip(),
        }
        dip_tokens = _name_tokens(f"{item['nome']} {item['cognome']}")
        cognome_tokens = _name_tokens(item["cognome"])
        candidati = []
        for operatore in operatori:
            if operatore.get("gestionale_dipendente_id"):
                continue
            nome_operatore = f"{operatore.get('nome') or ''} {operatore.get('cognome') or ''}"
            op_tokens = _name_tokens(nome_operatore)
            if not op_tokens:
                continue
            stessa_persona = op_tokens == dip_tokens
            solo_nome_presente = (
                len(op_tokens) == 1
                and (op_tokens == cognome_tokens or op_tokens[0] in dip_tokens)
            )
            if stessa_persona or solo_nome_presente:
                candidati.append(operatore)
        if len(candidati) == 1:
            candidato = candidati[0]
            item["candidato_operatore"] = {
                "id": candidato.get("id"),
                "nome": f"{candidato.get('nome') or ''} {candidato.get('cognome') or ''}".strip(),
            }
        nuovi.append(item)
    return {"nuovi": nuovi, "totale": len(nuovi), "configurato": True}


@router.post("/collega-dipendente")
async def collega_dipendente(payload: CollegaDipendente, _admin=Depends(require_admin)):
    source_id = (payload.gestionale_dipendente_id or "").strip()
    cf = (payload.codice_fiscale or "").strip().upper()
    if not source_id:
        raise HTTPException(400, "Identificativo GestionaleCloud mancante")
    operatore = await db.tablet_operatori.find_one({
        "id": payload.operatore_id, "attivo": True
    })
    if not operatore:
        raise HTTPException(404, "Operatore Lotti non trovato")
    gia_sorgente = await db.tablet_operatori.find_one({
        "gestionale_dipendente_id": source_id, "attivo": True
    })
    if gia_sorgente and gia_sorgente.get("id") != payload.operatore_id:
        raise HTTPException(409, "Dipendente GestionaleCloud già collegato")
    if cf:
        gia_cf = await db.tablet_operatori.find_one({"codice_fiscale": cf, "attivo": True})
        if gia_cf and gia_cf.get("id") != payload.operatore_id:
            raise HTTPException(409, "Codice fiscale già collegato a un altro operatore")
    await db.tablet_operatori.update_one(
        {"id": payload.operatore_id},
        {"$set": {"gestionale_dipendente_id": source_id, "codice_fiscale": cf}},
    )
    return {"ok": True, "operatore_id": payload.operatore_id,
            "gestionale_dipendente_id": source_id}


@router.post("/abilita-dipendente")
async def abilita_dipendente(payload: AbilitaDipendente, _admin=Depends(require_admin)):
    pin = (payload.pin or "").strip()
    if len(pin) < 4:
        raise HTTPException(400, "PIN minimo 4 cifre")
    cf = (payload.codice_fiscale or "").strip().upper()
    source_id = (payload.gestionale_dipendente_id or "").strip()
    if source_id:
        gia_sorgente = await db.tablet_operatori.find_one({
            "gestionale_dipendente_id": source_id, "attivo": True
        })
        if gia_sorgente:
            raise HTTPException(409, "Dipendente già abilitato")
    gia = await db.tablet_operatori.find_one({"codice_fiscale": cf, "attivo": True}) if cf else None
    if gia:
        raise HTTPException(409, "Dipendente già abilitato")
    doc = {"id": str(uuid.uuid4()), "nome": payload.nome.strip(), "cognome": (payload.cognome or "").strip(), "codice_fiscale": cf, "pin": _hash_pin(pin), "pin_lookup": _pin_lookup(pin), "ruolo": "operatore", "mansione": payload.mansione or "", "postazione": payload.postazione or "", "libretto_sanitario_scadenza": payload.libretto_sanitario_scadenza or "", "attivo": True}
    doc["gestionale_dipendente_id"] = source_id
    await db.tablet_operatori.insert_one(doc)
    doc.pop("pin", None); doc.pop("pin_lookup", None); doc.pop("_id", None)
    return doc


@router.post("/verifica-admin")
async def verifica_admin(payload: PinAdmin, request: Request = None):
    await _richiedi_pin_amministratore(payload.pin, request)
    return {"ok": True}


class ReimpostaPin(BaseModel):
    pin_nuovo: str


@router.post("/pin-operatori")
async def pin_operatori(payload: PinAdmin, request: Request = None):
    """Elenco degli operatori per la gestione dei PIN.

    25/07/2026 — NON restituisce più i PIN: non esistono più in chiaro da
    nessuna parte. Se un dipendente dimentica il PIN si usa «Reimposta PIN»
    (qui sotto) e gliene si assegna uno nuovo. La rotta resta viva per non
    rompere una pagina rimasta aperta da prima dell'aggiornamento."""
    await _richiedi_pin_amministratore(
        payload.pin, request, "Solo l'amministratore può gestire i PIN"
    )
    docs = await db.tablet_operatori.find(
        {"attivo": True},
        {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "ruolo": 1, "postazione": 1,
         "pin": 1, "pin_da_impostare": 1, "gruppo_pin": 1},
    ).to_list(200)
    operatori = [
        {
            "id": d.get("id"),
            "nome": d.get("nome", ""),
            "cognome": d.get("cognome", ""),
            "ruolo": d.get("ruolo", "operatore"),
            "postazione": d.get("postazione", ""),
            "gruppo_pin": d.get("gruppo_pin", ""),
            "pin_condiviso": bool(d.get("gruppo_pin")),
            # niente PIN: si dice solo SE ne ha uno impostato
            "pin_impostato": bool(d.get("pin")) and not d.get("pin_da_impostare"),
        }
        for d in docs
    ]
    return {
        "ok": True,
        "operatori": operatori,
        "pin_visibili": False,
        "messaggio": "I PIN non sono più leggibili da nessuno, nemmeno da qui: "
                     "se un dipendente lo dimentica, usa «Reimposta PIN».",
    }


@router.post("/{op_id}/reimposta-pin")
async def reimposta_pin(op_id: str, payload: ReimpostaPin, _admin=Depends(require_admin)):
    """Assegna un PIN nuovo a un dipendente. Da questo momento vale SOLO il
    nuovo: il vecchio non funziona più (prima invece tornava valido al primo
    riavvio del server)."""
    pin = (payload.pin_nuovo or "").strip()
    if len(pin) < 4 or not pin.isdigit():
        raise HTTPException(400, "Il PIN deve essere di almeno 4 cifre")
    operatore = await db.tablet_operatori.find_one(
        {"id": op_id, "attivo": True}, {"_id": 0, "id": 1, "gruppo_pin": 1}
    )
    if not operatore:
        raise HTTPException(404, "Operatore non trovato")
    gruppo = operatore.get("gruppo_pin")
    filtro_altri = {"attivo": True, "pin_lookup": _pin_lookup(pin), "id": {"$ne": op_id}}
    if gruppo:
        filtro_altri["gruppo_pin"] = {"$ne": gruppo}
    altro = await db.tablet_operatori.find_one(filtro_altri, {"_id": 1})
    if altro:
        raise HTTPException(409, "Questo PIN è già di un altro dipendente: scegline un altro")
    nuovo_hash = _hash_pin(pin)
    filtro = {"attivo": True, "gruppo_pin": gruppo} if gruppo else {"id": op_id}
    res = await db.tablet_operatori.update_many(
        filtro,
        {"$set": {"pin": nuovo_hash, "pin_lookup": _pin_lookup(pin),
                  "pin_da_impostare": False},
         "$unset": {"pin_chiaro": ""}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Operatore non trovato")
    ids_aggiornati = [op_id]
    if gruppo:
        ids_aggiornati = [
            d.get("id") for d in await db.tablet_operatori.find(
                {"attivo": True, "gruppo_pin": gruppo}, {"_id": 0, "id": 1}
            ).to_list(50)
        ]
    return {
        "ok": True,
        "operatori_aggiornati": ids_aggiornati,
        "messaggio": (
            "PIN condiviso aggiornato per Vincenzo e Valerio"
            if gruppo else "PIN aggiornato: da adesso vale solo quello nuovo"
        ),
    }


@router.patch("/{op_id}")
async def aggiorna_dipendente(op_id: str, payload: AggiornaDipendente, _admin=Depends(require_admin)):
    """Aggiorna i campi di un operatore. Se arriva 'pin' aggiorna l'hash e
    l'impronta di ricerca: da qui in poi vale SOLO il PIN nuovo — prima il
    vecchio tornava valido al primo riavvio del server."""
    upd = {}
    for campo in ("mansione", "postazione", "libretto_sanitario_scadenza", "cognome", "nome", "ruolo", "codice_fiscale"):
        val = getattr(payload, campo, None)
        if val is not None:
            upd[campo] = val.strip().upper() if campo == "codice_fiscale" else val
    if payload.pin is not None:
        pin = payload.pin.strip()
        if len(pin) < 4:
            raise HTTPException(400, "PIN minimo 4 cifre")
        upd["pin"] = _hash_pin(pin)
        upd["pin_lookup"] = _pin_lookup(pin)
        upd["pin_da_impostare"] = False
    if not upd:
        return {"ok": True, "modificato": False}
    res = await db.tablet_operatori.update_one({"id": op_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Operatore non trovato")
    return {"ok": True, "modificato": True}


class IgnoraDipendente(BaseModel):
    codice_fiscale: Optional[str] = ""
    gestionale_dipendente_id: Optional[str] = ""


@router.post("/ignora-dipendente")
async def ignora_dipendente(payload: IgnoraDipendente, _admin=Depends(require_admin)):
    cf = (payload.codice_fiscale or "").strip().upper()
    source_id = (payload.gestionale_dipendente_id or "").strip()
    if cf or source_id:
        filtro = {"gestionale_dipendente_id": source_id} if source_id else {"codice_fiscale": cf}
        await db.tablet_operatori_ignorati.update_one(
            filtro,
            {"$set": {"codice_fiscale": cf,
                      "gestionale_dipendente_id": source_id, "ignorato": True}},
            upsert=True,
        )
    return {"ok": True}


@router.get("/verifica")
async def verifica():
    return {"ok": True, "servizio": "tablet_operatori"}
