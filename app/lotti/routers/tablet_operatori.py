"""
tablet_operatori.py
-------------------
Operatori del tablet HACCP = anagrafica HR. Decisione del titolare 14/09/2026
(regole R1-R6):

* **R1 — l'anagrafica HR comanda, Lotti legge.** Lotti non tiene un proprio
  elenco di persone: la collezione ``tablet_operatori`` e' una PROIEZIONE
  dell'anagrafica HR (``hr.app_dipendenti``, letta in-process), rinfrescata
  all'avvio, ogni 10 minuti dallo scheduler, a ogni apertura della pagina
  Personale e a ogni login. Chi e' in forza in HR (stato attivo alla data di
  oggi) ed e' «operatore Lotti» nella scheda HR e' un operatore; chi non lo e'
  sparisce da solo. Una riga Lotti senza persona HR corrispondente resta nel
  database (i lotti gia' firmati restano a suo nome) ma ``attivo = false``.
* **R2/R3 — il PIN si imposta nella scheda HR**, uno per persona, e vale sia
  per il portale sia per firmare qui. Lotti non salva piu' nessun PIN: il
  login chiede a HR chi ha quel PIN (``auth_dipendenti.trova_dipendente_per_pin``).
  I PIN storici di Lotti (bcrypt) sono migrati UNA volta in HR
  (``migra_pin_in_hr``), senza mai passare in chiaro.
* **R4 — niente PIN condiviso** fra Vincenzo e Valerio: ognuno firma col PIN
  personale della propria scheda HR. Il PIN amministratore centrale
  (ERP/Menu/Lotti/HR, decisione 05/09/2026) continua a sbloccare le PAGINE
  amministrative (``pin_amministratore_valido``) ma non e' un'identita' di
  firma.
* **R6 — qui restano solo i dati HACCP** della persona: postazione (proposta
  dal ruolo HR, modificabile) e scadenza del libretto sanitario.
"""

import logging
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.lotti.auth import check_lock, clear_fails, ip_richiesta, make_token, register_fail, require_admin
from app.lotti.db import database as db
from app.services import pin_authentication

router = APIRouter(prefix="/tablet-operatori", tags=["tablet_operatori"])

_LOG = logging.getLogger("uvicorn.error")

POSTAZIONI = ("laboratorio", "pasticceria", "sala", "bar")

# Nomi con cui Lotti conosceva storicamente una persona che in HR si chiama
# diversamente (refusi): servono solo ad agganciare la riga esistente, cosi'
# lo storico HACCP resta attaccato alla persona giusta.
ALIAS_COGNOME = {"lisina": "lesina"}

_CAMPI_PIN_LEGACY = {"pin": "", "pin_lookup": "", "pin_chiaro": "", "pin_da_impostare": "",
                     "gruppo_pin": "", "pin_hash_riparato": "", "pin_recupero_emergenza": ""}


def postazione_da_ruolo(ruolo: str) -> str:
    """Postazione HACCP proposta dal ruolo/qualifica HR (CP2011 o testo libero)."""
    r = _norm(ruolo)
    if not r:
        return ""
    if any(k in r for k in ("pasticc", "cioccolat", "impastatore", "fornaio", "panett")):
        return "pasticceria"
    if any(k in r for k in ("cuoco", "rosticc", "cucina", "lavapiatti", "laborator", "operaio")):
        return "laboratorio"
    # "cameriere di bar" e' sala (serve ai tavoli), prima del controllo su "bar"
    if any(k in r for k in ("camerier", "sala", "tirocin")):
        return "sala"
    if any(k in r for k in ("barista", "banconi", "bancon", "cassier", "bar")):
        return "bar"
    return ""


def _norm(value: Any) -> str:
    clean = unicodedata.normalize("NFKD", str(value or ""))
    clean = "".join(c for c in clean if not unicodedata.combining(c))
    return " ".join(clean.casefold().split())


def _name_tokens(value: str) -> tuple:
    return tuple(sorted(re.findall(r"[a-z0-9']+", _norm(value))))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _db_hr():
    try:
        from app.hr.database import Database as DatabaseHR, DatabaseNonConfigurato
    except Exception:  # pragma: no cover - modulo HR assente
        return None
    try:
        db_hr = DatabaseHR.get_db()
    except Exception:
        return None
    if db_hr is None or isinstance(db_hr, DatabaseNonConfigurato):
        return None
    return db_hr


async def _persone_hr() -> Optional[List[Dict[str, Any]]]:
    """Tutte le persone dell'anagrafica HR (non fuse), con stato normalizzato."""
    db_hr = _db_hr()
    if db_hr is None:
        return None
    from app.hr.services import stato_rapporto

    docs = await db_hr["dipendenti"].find(
        {"merged_into": {"$exists": False}},
        {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1, "codice_fiscale": 1,
         "ruolo": 1, "qualifica_unilav": 1, "mansione": 1, "qualifica": 1, "ruolo_app": 1,
         "attivo": 1, "in_carico": 1, "stato": 1, "data_fine_rapporto": 1, "data_cessazione": 1,
         "data_dimissione": 1, "data_cessazione_prevista": 1, "motivo_cessazione": 1,
         "riferimento_cessazione": 1, "dimissioni": 1, "lotti_operatore": 1, "pin_hash": 1},
    ).to_list(1000)
    persone = []
    for d in docs:
        if not d.get("id"):
            continue
        st = stato_rapporto.riepilogo_stato(d)
        cognome = str(d.get("cognome") or "").strip()
        nome = str(d.get("nome") or "").strip()
        if not cognome and not nome:
            nome_completo = str(d.get("nome_completo") or "").strip()
            cognome, _, nome = nome_completo.partition(" ")
        persone.append({
            "id": d["id"], "cognome": cognome, "nome": nome,
            "nome_completo": f"{cognome} {nome}".strip(),
            "codice_fiscale": str(d.get("codice_fiscale") or "").strip().upper(),
            "ruolo_testo": str(d.get("ruolo") or d.get("qualifica_unilav") or d.get("mansione") or d.get("qualifica") or "").strip(),
            "amministratore": d.get("ruolo_app") == "admin",
            "stato": st["stato"], "data_fine_rapporto": st["data_fine_rapporto"],
            "motivo_cessazione": st["motivo_cessazione"], "motivo_etichetta": st["motivo_cessazione_etichetta"],
            "operatore_lotti": d.get("lotti_operatore") is not False,
            "pin_impostato": bool(d.get("pin_hash")),
        })
    return persone


def _abbina(persona: Dict[str, Any], operatori: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Riga Lotti della persona: per id HR, poi per codice fiscale, poi per
    nome storico (solo cognome, con gli alias) se univoco."""
    pid, cf = persona["id"], persona["codice_fiscale"]
    for op in operatori:
        if pid and pid in (op.get("hr_id"), op.get("gestionale_dipendente_id")):
            return op
    if cf:
        for op in operatori:
            if str(op.get("codice_fiscale") or "").strip().upper() == cf and not op.get("hr_id"):
                return op
    completo = _name_tokens(persona["nome_completo"])
    cognome = _norm(persona["cognome"])
    candidati = []
    for op in operatori:
        if op.get("hr_id"):
            continue
        nome_op = _norm(f"{op.get('nome') or ''} {op.get('cognome') or ''}")
        nome_op = " ".join(ALIAS_COGNOME.get(t, t) for t in nome_op.split())
        tok = _name_tokens(nome_op)
        if not tok:
            continue
        if tok == completo or (len(tok) == 1 and tok[0] == cognome and len(cognome) >= 4):
            candidati.append(op)
    return candidati[0] if len(candidati) == 1 else None


async def migra_pin_in_hr() -> Dict[str, int]:
    """R3: i PIN bcrypt gia' presenti in Lotti passano UNA volta nella scheda
    HR della stessa persona, come sono (hash), mai in chiaro. Se la persona ha
    gia' un PIN in HR quello vince (una persona = un PIN, e la scheda HR e'
    la fonte). Le righe del vecchio PIN condiviso fra amministratori NON si
    migrano (R4: ognuno usa il proprio)."""
    esito = {"migrati": 0, "gia_in_hr": 0, "senza_persona": 0, "condivisi_scartati": 0}
    db_hr = _db_hr()
    persone = await _persone_hr()
    if db_hr is None or persone is None:
        return esito
    operatori = await db.tablet_operatori.find(
        {"pin": {"$regex": r"^\$2"}, "attivo": {"$ne": False}},
        {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "pin": 1,
                                       "gruppo_pin": 1, "hr_id": 1, "gestionale_dipendente_id": 1,
                                       "codice_fiscale": 1, "pin_da_impostare": 1}).to_list(500)
    per_operatore: Dict[str, Dict[str, Any]] = {}
    for p in persone:
        op = _abbina(p, operatori)
        if op:
            per_operatore[op["id"]] = p
    for op in operatori:
        if op.get("pin_da_impostare"):
            continue
        if op.get("gruppo_pin"):
            esito["condivisi_scartati"] += 1
            continue
        p = per_operatore.get(op["id"])
        if not p:
            esito["senza_persona"] += 1
            continue
        if p["pin_impostato"]:
            esito["gia_in_hr"] += 1
            continue
        await db_hr["dipendenti"].update_one(
            {"id": p["id"]},
            {"$set": {"pin_hash": op["pin"], "pin_migrato_da_lotti": _now(),
                      "pin_updated_at": _now()},
             "$unset": {"pin_lookup": ""}})
        p["pin_impostato"] = True
        esito["migrati"] += 1
    if esito["migrati"]:
        _LOG.info("[personale] PIN migrati da Lotti alla scheda HR: %s", esito)
    return esito


async def sincronizza_operatori_da_hr() -> Dict[str, Any]:
    """Allinea ``tablet_operatori`` all'anagrafica HR (idempotente)."""
    persone = await _persone_hr()
    if persone is None:
        return {"esito": "hr_non_configurato", "aggiornati": 0, "creati": 0, "disattivati": 0}
    operatori = await db.tablet_operatori.find({}, {"_id": 0}).to_list(500)
    adesso = _now()
    esito = {"esito": "ok", "aggiornati": 0, "creati": 0, "disattivati": 0, "senza_persona_hr": 0}
    agganciati = set()
    for p in persone:
        op = _abbina(p, operatori)
        in_forza = p["stato"] == "attivo" and p["operatore_lotti"]
        valori = {
            "hr_id": p["id"], "gestionale_dipendente_id": p["id"],
            "codice_fiscale": p["codice_fiscale"],
            "nome": p["nome_completo"], "cognome": p["cognome"], "nome_proprio": p["nome"],
            "mansione": p["ruolo_testo"],
            "ruolo": "amministratore" if p["amministratore"] else "operatore",
            "attivo": in_forza, "in_carico": in_forza,
            "hr_stato": p["stato"], "operatore_lotti": p["operatore_lotti"],
            "data_fine_rapporto": p["data_fine_rapporto"], "motivo_fine_rapporto": p["motivo_cessazione"],
            "motivo_fine_rapporto_etichetta": p["motivo_etichetta"],
            "pin_impostato": p["pin_impostato"],
            "fonte": "hr", "sincronizzato_at": adesso,
        }
        if op:
            agganciati.add(op["id"])
            if not op.get("postazione"):
                valori["postazione"] = postazione_da_ruolo(p["ruolo_testo"])
            await db.tablet_operatori.update_one({"id": op["id"]}, {"$set": valori, "$unset": dict(_CAMPI_PIN_LEGACY)})
            esito["aggiornati"] += 1
        elif in_forza:
            await db.tablet_operatori.insert_one({
                "id": str(uuid.uuid4()), **valori,
                "postazione": postazione_da_ruolo(p["ruolo_testo"]),
                "libretto_sanitario_scadenza": "", "created_at": adesso,
            })
            esito["creati"] += 1
    for op in operatori:
        if op["id"] in agganciati:
            continue
        esito["senza_persona_hr"] += 1
        if op.get("attivo") is not False or op.get("pin"):
            await db.tablet_operatori.update_one(
                {"id": op["id"]},
                {"$set": {"attivo": False, "in_carico": False, "hr_stato": "non_in_hr",
                          "fonte": op.get("fonte") or "storico_lotti", "sincronizzato_at": adesso},
                 "$unset": dict(_CAMPI_PIN_LEGACY)})
            if op.get("attivo") is not False:
                esito["disattivati"] += 1
    return esito


async def seed_operatori():
    """All'avvio: migra i PIN residui in HR e allinea gli operatori. Non deve
    MAI impedire l'avvio (chiamato da server.py senza rete di sicurezza)."""
    try:
        await migra_pin_in_hr()
    except Exception as e:
        _LOG.warning("[personale] migrazione PIN in HR rimandata: %s", e)
    try:
        esito = await sincronizza_operatori_da_hr()
        if esito.get("esito") == "hr_non_configurato":
            _LOG.warning("[personale] anagrafica HR non configurata: nessun operatore sul tablet")
        else:
            _LOG.info("[personale] operatori allineati all'anagrafica HR: %s", esito)
    except Exception as e:
        _LOG.warning("[personale] allineamento operatori HR rimandato: %s", e)


# ── Modelli ────────────────────────────────────────────────────────────────
class PinLogin(BaseModel):
    pin: str


class AggiornaDipendente(BaseModel):
    postazione: Optional[str] = None
    libretto_sanitario_scadenza: Optional[str] = None


class PinAdmin(BaseModel):
    pin: str


# ── Identita' e PIN ────────────────────────────────────────────────────────
async def _richiedi_pin_amministratore(
    pin: str, request: Request = None, dettaglio: str = "PIN amministratore non valido"
) -> None:
    ip = ip_richiesta(request) or None
    if ip:
        check_lock(ip)
    if pin_authentication.admin_pin_matches(pin):
        if ip:
            clear_fails(ip)
        return
    if ip:
        register_fail(ip)
    raise HTTPException(403, dettaglio)


def _op_response(doc):
    if not doc.get("dipendente_id"):
        raise HTTPException(401, "Identita' dipendente HR non disponibile")
    op = {"dipendente_id": doc["dipendente_id"], "nome": doc.get("nome", "Operatore"), "ruolo": doc.get("ruolo", "operatore")}
    token = make_token(sub=op["dipendente_id"], nome=op["nome"], ruolo=op["ruolo"], via="pin")
    return {"ok": True, "token": token, "operatore": op}


async def trova_operatori_per_pin(pin: str) -> List[Dict[str, Any]]:
    """Identita' HR con ``dipendente_id`` e attributi HACCP del tablet.

    La proiezione ``tablet_operatori`` viene allineata se manca; non entra mai
    un cessato o chi non e' autorizzato a operare in Lotti.
    """
    if _db_hr() is None:
        return []
    from app.hr.services.auth_dipendenti import trova_dipendente_per_pin

    persone = await trova_dipendente_per_pin(pin, solo_operatori_lotti=True)
    if not persone:
        return []
    trovati = []
    for tentativo in (0, 1):
        trovati = []
        for p in persone:
            op = await db.tablet_operatori.find_one(
                {"attivo": True, "$or": [{"hr_id": p["id"]}, {"gestionale_dipendente_id": p["id"]}]},
                {"_id": 0, "nome": 1, "ruolo": 1})
            if op:
                trovati.append({"dipendente_id": p["id"], "nome": op.get("nome"), "ruolo": op.get("ruolo")})
        if len(trovati) == len(persone) or tentativo:
            break
        await sincronizza_operatori_da_hr()
    return trovati


@router.post("/login")
async def login_pin(payload: PinLogin, request: Request = None):
    ip = ip_richiesta(request) or None
    if ip:
        check_lock(ip)
    pin = (payload.pin or "").strip()
    if len(pin) < 4:
        raise HTTPException(400, "PIN non valido")
    docs = await trova_operatori_per_pin(pin)
    if docs:
        if ip:
            clear_fails(ip)
        if len(docs) > 1:
            raise HTTPException(409, "PIN associato a piu' dipendenti: correggere gli accessi HR")
        return _op_response(docs[0])
    if ip:
        register_fail(ip)
    if pin_authentication.admin_pin_matches(pin):
        raise HTTPException(401, "Il PIN amministratore apre le pagine riservate ma non firma: "
                                 "per entrare sul tablet usa il tuo PIN personale (scheda HR)")
    raise HTTPException(401, "PIN non riconosciuto")


@router.post("/verifica-admin")
async def verifica_admin(payload: PinAdmin, request: Request = None):
    await _richiedi_pin_amministratore(payload.pin, request)
    return {"ok": True}


# ── Elenco e dati HACCP ────────────────────────────────────────────────────
_CAMPI_PUBBLICI = {"_id": 0, "pin": 0, "pin_lookup": 0, "pin_chiaro": 0}


@router.get("")
async def lista_dipendenti(tutti: bool = False):
    """Operatori in carico (= in forza in HR). Con ``tutti=1`` anche chi non
    e' piu' in carico (cessati in HR o righe storiche senza persona HR), per
    la sezione «Non piu' in carico» della pagina Personale."""
    filtro: Dict[str, Any] = {} if tutti else {"attivo": True}
    docs = await db.tablet_operatori.find(filtro, _CAMPI_PUBBLICI).to_list(500)
    if tutti:
        # la vecchia riga generica "Amministratore" non e' una persona
        docs = [d for d in docs if not d.get("sostituito_da_gruppo")]
    for d in docs:
        dipendente_id = d.get("hr_id")
        if not dipendente_id or d.get("gestionale_dipendente_id") != dipendente_id:
            dipendente_id = None
        d.pop("id", None)
        d.pop("hr_id", None)
        d.pop("gestionale_dipendente_id", None)
        d["dipendente_id"] = dipendente_id
        d["in_carico"] = d.get("attivo") is not False and bool(dipendente_id)
        if d.get("attivo") is not False and not d.get("postazione"):
            d["postazione_proposta"] = postazione_da_ruolo(d.get("mansione") or "")
    docs.sort(key=lambda d: (d.get("in_carico") is False, _norm(d.get("nome"))))
    return docs


@router.post("/sincronizza-hr")
async def sincronizza_hr(_admin=Depends(require_admin)):
    """Riallinea subito gli operatori all'anagrafica HR (il job lo fa da solo ogni 10 minuti)."""
    migrazione = await migra_pin_in_hr()
    esito = await sincronizza_operatori_da_hr()
    return {**esito, "pin_migrati": migrazione}


class PinOperatore(BaseModel):
    pin: str


@router.post("/{dipendente_id}/pin")
async def imposta_pin_operatore(dipendente_id: str, payload: PinOperatore, _admin=Depends(require_admin)):
    """Il titolare imposta il PIN di un dipendente anche da qui. Il PIN resta
    UNO, nella scheda HR (stesso servizio del portale: bcrypt + impronta, mai
    due persone in forza con lo stesso PIN): questa non e' una seconda copia."""
    filtro = {"hr_id": dipendente_id, "gestionale_dipendente_id": dipendente_id, "attivo": True}
    if await db.tablet_operatori.count_documents(filtro) != 1:
        raise HTTPException(404, "Dipendente HR non trovato in una proiezione Lotti attiva e univoca")
    from app.hr.services import auth_dipendenti

    try:
        ok = await auth_dipendenti.imposta_pin(dipendente_id, str(payload.pin or "").strip())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not ok:
        raise HTTPException(404, "Dipendente non trovato nella scheda HR")
    await sincronizza_operatori_da_hr()
    return {"ok": True, "pin_impostato": True}


@router.patch("/{dipendente_id}")
async def aggiorna_dipendente(dipendente_id: str, payload: AggiornaDipendente, _admin=Depends(require_admin)):
    """Solo i dati HACCP (R6): postazione e scadenza libretto. Nome, ruolo,
    stato e PIN vivono nella scheda HR."""
    upd: Dict[str, Any] = {}
    if payload.postazione is not None:
        postazione = payload.postazione.strip().lower()
        if postazione and postazione not in POSTAZIONI:
            raise HTTPException(400, "Postazione non valida: " + ", ".join(POSTAZIONI))
        upd["postazione"] = postazione
    if payload.libretto_sanitario_scadenza is not None:
        scad = payload.libretto_sanitario_scadenza.strip()
        if scad:
            try:
                datetime.strptime(scad[:10], "%Y-%m-%d")
            except ValueError as exc:
                raise HTTPException(400, "Scadenza libretto non valida (aaaa-mm-gg)") from exc
            scad = scad[:10]
        upd["libretto_sanitario_scadenza"] = scad
    filtro = {"hr_id": dipendente_id, "gestionale_dipendente_id": dipendente_id, "attivo": True}
    if await db.tablet_operatori.count_documents(filtro) != 1:
        raise HTTPException(404, "Dipendente HR non trovato in una proiezione Lotti attiva e univoca")
    if not upd:
        return {"ok": True, "modificato": False}
    upd["aggiornato_at"] = _now()
    res = await db.tablet_operatori.update_one(filtro, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Operatore non trovato")
    return {"ok": True, "modificato": True, "salvato_alle": upd["aggiornato_at"]}


async def operatore_per_id(operatore_id: str) -> Optional[Dict[str, Any]]:
    """La persona dell'anagrafica HR per id, se e' ancora in forza.

    Serve a chi assegna un apparecchio o apre una rilevazione: il nome sul
    registro deve venire da HR, non essere scritto a mano. Un cessato non e'
    piu' assegnabile — la sua firma su un controllo di domani non avrebbe
    senso — e nemmeno un id che in anagrafica non esiste.
    """
    if not operatore_id:
        return None
    persone = await _persone_hr()
    if not persone:
        return None
    for persona in persone:
        if persona.get("id") == operatore_id:
            return persona if persona.get("stato") == "attivo" else None
    return None
