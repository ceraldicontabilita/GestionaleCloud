"""
Dipendenti in Cloud - Router Module
Sistema HR completo per gestione personale
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Body, Form, Request
from fastapi.responses import Response
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uuid
import re
import os
import io
import zipfile
import hashlib
import base64
import tempfile
import logging
import unicodedata
import json
import calendar
from datetime import datetime, timezone, timedelta, date
from decimal import Decimal, InvalidOperation

from app.constants.stati_associazione_bonifico import (
    STATI_PAGA_APERTI, STATO_PAGA_IN_ATTESA_BUSTA, STATO_PAGA_IN_ATTESA_PAGAMENTO,
    STATO_PAGA_PAGATO, STATO_PAGA_PARZIALE, stato_paga_mese,
)
from app.hr.database import Database
from app.hr.services import stato_rapporto
from app.services.cedolini_pagamento import allinea_cedolino_gestionale_da_paghe
from app.hr.utils.dependencies import require_staff

logger = logging.getLogger(__name__)

# Il responsabile turni dispone soltanto delle operazioni usate dalla pagina
# Turni. La UI non costituisce un confine di autorizzazione: nuove rotte e
# gestione anagrafica/PIN/paghe/documenti restano riservate all'amministratore.
_ROTTE_RESPONSABILE_TURNI = {
    ("GET", "/dipendenti"), ("GET", "/dipendenti/{dipendente_id}"),
    ("GET", "/ordine-dipendenti"), ("POST", "/ordine-dipendenti"),
    ("GET", "/ferie"),
    ("GET", "/turni"), ("POST", "/turni"),
    ("PUT", "/turni/{turno_id}"), ("DELETE", "/turni/{turno_id}"),
    ("GET", "/assegnazioni-turni"), ("POST", "/assegnazioni-turni"),
    ("GET", "/turni-config"), ("POST", "/turni-config"),
    ("GET", "/turni-disponibilita-bar"), ("GET", "/turni-preferenze"),
    ("GET", "/turni-chiusura-pomeridiana"), ("POST", "/turni-chiusura-pomeridiana"),
    ("GET", "/onomastici"), ("POST", "/onomastici"),
    ("GET", "/onomastici/settimana"),
    ("POST", "/presenze/batch"),
}


async def require_gestione_hr(request: Request, identity=Depends(require_staff)):
    if identity.get("role") == "admin":
        return identity
    # Usa il template della rotta risolta, non un startswith sul percorso
    # fornito dal client: /dipendenti/{id}/pin non e' /dipendenti/{id}.
    percorso = request.scope["route"].path.split("/dipendenti-cloud", 1)[-1]
    if (request.method, percorso) not in _ROTTE_RESPONSABILE_TURNI:
        raise HTTPException(403, "Accesso riservato all'amministratore")
    return identity


router = APIRouter(prefix="/dipendenti-cloud", tags=["Dipendenti Cloud"],
                   dependencies=[Depends(require_gestione_hr)])

# ============ HELPERS ============

def get_db():
    """Get database instance"""
    return Database.get_db()

def generate_id():
    return str(uuid.uuid4())

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def serialize_doc(doc):
    if doc and '_id' in doc:
        del doc['_id']
    return doc

# ============ MODELS ============

class DipendenteCloud(BaseModel):
    nome: str
    cognome: str
    matricola: Optional[str] = None
    codice_fiscale: Optional[str] = None
    data_nascita: Optional[str] = None
    codice_fiscale_azienda: Optional[str] = None
    sesso: Optional[str] = None
    regione_residenza: Optional[str] = None
    provincia_residenza: Optional[str] = None
    comune_residenza: Optional[str] = None
    regione_domicilio: Optional[str] = None
    provincia_domicilio: Optional[str] = None
    comune_domicilio: Optional[str] = None
    cittadinanza: Optional[str] = None
    titolo_studio: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    indirizzo: Optional[str] = None
    ruolo: Optional[str] = None
    luogo_lavoro: Optional[str] = None
    gruppo: Optional[str] = None
    note: Optional[str] = None
    contratto: str = "Indeterminato"
    data_assunzione: Optional[str] = None
    data_fine_contratto: Optional[str] = None
    iban: Optional[str] = None
    livello: Optional[str] = None
    ore_settimanali: Optional[float] = None
    # 14/09/2026: lo stato NON si modifica da qui (solo con "Cessa rapporto" /
    # "Riattiva", con data e motivo). Il campo resta accettato per
    # compatibilita' ma viene ignorato in PUT.
    stato: Optional[str] = None
    # Chi puo' firmare in Lotti (HACCP): l'anagrafica HR comanda (R1).
    lotti_operatore: Optional[bool] = None


class CessazioneCloud(BaseModel):
    data_cessazione: str
    motivo: str = "altro"
    riferimento: Optional[str] = ""
    note: Optional[str] = ""


class PinCloud(BaseModel):
    pin: str

class PresenzaCloud(BaseModel):
    dipendente_id: str
    data: str
    entrata: Optional[str] = None
    uscita: Optional[str] = None
    stato: str = "presente"
    giustificativo: Optional[str] = None
    ore_lavorate: float = 0
    note: Optional[str] = None

class FerieCloud(BaseModel):
    dipendente_id: str
    tipo: str  # Ferie, Permesso, Malattia, ROL
    data_inizio: str
    data_fine: str
    giorni: int = 1
    stato: str = "in_attesa"
    nota: Optional[str] = None

class TurnoCloud(BaseModel):
    nome: str
    orario_inizio: str
    orario_fine: str
    colore: str = "#5b7a6b"

class BustaPagaCloud(BaseModel):
    dipendente_id: str
    mese: int
    anno: int
    lordo: float
    netto: float
    inps: float = 0
    irpef: float = 0
    trattenute: float = 0
    stato: str = "DA_PAGARE"
    data_pagamento: Optional[str] = None

class MissioneCloud(BaseModel):
    dipendente_id: str
    destinazione: str
    data_inizio: str
    data_fine: str
    scopo: str
    rimborso: float = 0
    stato: str = "in_attesa"

class DocumentoCloud(BaseModel):
    dipendente_id: str
    titolo: str
    tipo: str
    scadenza: Optional[str] = None
    file_url: Optional[str] = None

# ============ DIPENDENTI ============

def _vista_dipendente(d: dict) -> dict:
    """Forma unica del dipendente per la UI: stato normalizzato (attivo/cessato
    con data e motivo), tutti i campi anagrafici, MAI il PIN (solo se e' impostato)."""
    st = stato_rapporto.riepilogo_stato(d)
    nome_completo = d.get("nome_completo") or f"{d.get('nome', '')} {d.get('cognome', '')}".strip()
    return {
        "id": d.get("id") or str(d.get("_id", "")),
        "nome": d.get("nome", ""),
        "cognome": d.get("cognome", ""),
        "nome_completo": nome_completo,
        "codice_fiscale": d.get("codice_fiscale", ""),
        "matricola": d.get("matricola") or "",
        "data_nascita": d.get("data_nascita") or "",
        "codice_fiscale_azienda": d.get("codice_fiscale_azienda") or "",
        "sesso": d.get("sesso") or "",
        "regione_residenza": d.get("regione_residenza") or "",
        "provincia_residenza": d.get("provincia_residenza") or "",
        "comune_residenza": d.get("comune_residenza") or "",
        "regione_domicilio": d.get("regione_domicilio") or "",
        "provincia_domicilio": d.get("provincia_domicilio") or "",
        "comune_domicilio": d.get("comune_domicilio") or "",
        "cittadinanza": d.get("cittadinanza") or "",
        "titolo_studio": d.get("titolo_studio") or "",
        "indirizzo": d.get("indirizzo") or "",
        # ruolo/contratto: prima il valore inserito a mano, poi quello letto
        # dall'UNILAV (qualifica_unilav / tipo_contratto) — MAI un default fisso:
        # "Indeterminato" per chi non lo sappiamo e' un dato inventato, non ignoto.
        "ruolo": d.get("ruolo") or d.get("qualifica_unilav") or d.get("mansione") or "",
        "mansione": d.get("mansione") or "",
        "iban": d.get("iban", ""),
        "email": d.get("email", ""),
        "telefono": d.get("telefono", ""),
        "contratto": d.get("contratto") or d.get("tipo_contratto") or "",
        "data_assunzione": d.get("data_assunzione", ""),
        "data_fine_contratto": d.get("data_fine_contratto") or "",
        "data_cessazione": st["data_fine_rapporto"] or "",
        "luogo_lavoro": d.get("luogo_lavoro", ""),
        "gruppo": d.get("gruppo") or "",
        "note": d.get("note") or "",
        "importo_stipendio": d.get("importo_stipendio", 0),
        "livello": d.get("livello", ""),
        "ore_settimanali": d.get("ore_settimanali"),
        "ruolo_app": d.get("ruolo_app") or "dipendente",
        "pin_impostato": bool(d.get("pin_hash")),
        "lotti_operatore": d.get("lotti_operatore") is not False,
        "dimissioni": {k: (d.get("dimissioni") or {}).get(k) for k in
                       ("codice_modulo", "data_decorrenza", "data_trasmissione", "scadenza_unilav")}
        if d.get("dimissioni") else None,
        "created_at": d.get("created_at", ""),
        **st,
    }


# 18/09/2026: il responsabile turni entra con lo stesso `require_staff` di un
# admin (gli serve per la pagina Turni, che legge da questo stesso router) ma
# vedeva anche IBAN, stipendio, email, telefono, indirizzo, data di nascita e
# codice fiscale di tutta l'azienda — dati che la pagina Turni (l'unica che
# vede: `App.jsx` lo forza su quella) non usa mai. Non e' un giro di privilegi
# aggiuntivo: e' lo stesso `require_staff` gia' sulla rotta, solo passato alla
# funzione per poter filtrare la risposta invece di limitarsi ad aprire o
# chiudere la porta.
_CAMPI_RISERVATI_TURNI = (
    "iban", "email", "telefono", "importo_stipendio",
    "data_nascita", "indirizzo", "codice_fiscale",
)


def _per_responsabile_turni(identity: Any) -> bool:
    # isinstance, non solo "truthy": chiamando la funzione fuori dalla
    # richiesta FastAPI (com'e' nei test) il parametro resta il sentinella
    # Depends(require_staff) non risolto, non un dict — mai un ruolo da
    # confrontare, quindi mai un filtro applicato per errore.
    return isinstance(identity, dict) and identity.get("role") == "responsabile_turni"


def _senza_campi_riservati(vista: dict) -> dict:
    return {k: v for k, v in vista.items() if k not in _CAMPI_RISERVATI_TURNI}


@router.get("/dipendenti")
async def get_dipendenti(identity: Dict[str, Any] = Depends(require_staff)):
    """Anagrafica HR: la fonte unica di chi lavora in azienda (anche per Lotti)."""
    dipendenti = await get_db().dipendenti.find(
        {"merged_into": {"$exists": False}}, {"_id": 0, "pdf_data": 0}).to_list(1000)
    viste = [_vista_dipendente(d) for d in dipendenti]
    if _per_responsabile_turni(identity):
        return [_senza_campi_riservati(v) for v in viste]
    return viste

@router.get("/dipendenti/{dipendente_id}")
async def get_dipendente(dipendente_id: str, identity: Dict[str, Any] = Depends(require_staff)):
    dip = await get_db().dipendenti.find_one({"id": dipendente_id}, {"_id": 0})
    if not dip:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    dip.pop("pin_hash", None)
    dip.pop("pin_lookup", None)
    if _per_responsabile_turni(identity):
        return _senza_campi_riservati(dip)
    return dip


def _campi_anagrafici(dip: DipendenteCloud, esclusi=("stato",)) -> dict:
    """Solo i campi realmente inviati (mai sovrascrivere matricola, nascita,
    indirizzo... con None perche' il modale non li mostrava: e' successo a
    Moscato il 14/09/2026)."""
    dati = dip.model_dump(exclude_unset=True)
    for k in esclusi:
        dati.pop(k, None)
    if "codice_fiscale" in dati and dati["codice_fiscale"]:
        dati["codice_fiscale"] = str(dati["codice_fiscale"]).strip().upper()
    if "codice_fiscale_azienda" in dati and dati["codice_fiscale_azienda"]:
        dati["codice_fiscale_azienda"] = str(dati["codice_fiscale_azienda"]).strip().upper()
    if "sesso" in dati and dati["sesso"]:
        dati["sesso"] = str(dati["sesso"]).strip().upper()
    if "nome" in dati or "cognome" in dati:
        dati["nome"] = str(dati.get("nome") or "").strip()
        dati["cognome"] = str(dati.get("cognome") or "").strip()
    return dati


async def _crea_anagrafica(dati: Dict[str, Any], *, attivo: bool = True):
    """Writer unico per scheda manuale e nuove persone confermate da Excel."""
    dip_dict = dict(dati)
    if not dip_dict.get("nome") and not dip_dict.get("cognome"):
        raise HTTPException(status_code=400, detail="Nome e cognome obbligatori")
    cf = re.sub(r"\s+", "", str(dip_dict.get("codice_fiscale") or "")).upper()
    if cf:
        dip_dict["codice_fiscale"] = cf
        if await get_db().dipendenti.find_one({"codice_fiscale": cf}):
            raise HTTPException(409, "Codice fiscale già presente in anagrafica: aggiorna la scheda esistente")
    dip_dict["nome_completo"] = f"{dip_dict.get('cognome', '')} {dip_dict.get('nome', '')}".strip()
    ident = str(uuid.uuid5(uuid.NAMESPACE_URL, f"GestionaleCloud:HR:dipendente:{cf}")) if cf else generate_id()
    dip_dict.update({"id": ident, "created_at": now_iso(),
                     "stato": "attivo" if attivo else "cessato", "attivo": attivo,
                     "in_carico": attivo, "ruolo_app": "dipendente"})
    dip_dict.setdefault("lotti_operatore", True)
    await get_db().dipendenti.insert_one(dict(dip_dict))
    return _vista_dipendente(dip_dict)


@router.post("/dipendenti")
async def create_dipendente(dip: DipendenteCloud):
    return await _crea_anagrafica(_campi_anagrafici(dip))

@router.put("/dipendenti/{dipendente_id}")
async def update_dipendente(dipendente_id: str, dip: DipendenteCloud):
    """Aggiorna SOLO i campi inviati. Lo stato del rapporto non passa da qui:
    si usa /cessa (con data e motivo) o /riattiva."""
    db = get_db()
    esistente = await db.dipendenti.find_one({"id": dipendente_id}, {"_id": 0})
    if not esistente:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    dati = _campi_anagrafici(dip)
    nome = dati.get("nome", esistente.get("nome") or "")
    cognome = dati.get("cognome", esistente.get("cognome") or "")
    if "nome" in dati or "cognome" in dati:
        dati["nome_completo"] = f"{cognome} {nome}".strip()
    if dati:
        await db.dipendenti.update_one({"id": dipendente_id}, {"$set": dati})
    aggiornato = await db.dipendenti.find_one({"id": dipendente_id}, {"_id": 0})
    return {"message": "Dipendente aggiornato", "dipendente": _vista_dipendente(aggiornato)}

@router.delete("/dipendenti/{dipendente_id}")
async def delete_dipendente(dipendente_id: str):
    result = await get_db().dipendenti.delete_one({"id": dipendente_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    return {"message": "Dipendente eliminato"}

@router.post("/dipendenti/{dipendente_id}/cessa")
async def cessa_dipendente(dipendente_id: str, data: CessazioneCloud):
    """Cessa il rapporto CON data e motivo (dimissioni, licenziamento, fine
    contratto, risoluzione consensuale, altro) e riferimento (modulo
    dimissioni / UNILAV); innesca l'iter completo di chiusura (termina
    contratti, rifiuta assenze future, annulla partite, revoca il PIN, risolve
    alert) tramite l'evento DIPENDENTE_CESSATO. Lotti si adegua da solo."""
    db = get_db()
    dip = await db.dipendenti.find_one({"id": dipendente_id}, {"_id": 0})
    if not dip:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    try:
        campi = stato_rapporto.campi_cessazione(data.data_cessazione, data.motivo, data.riferimento or "",
                                                data.note or "", fonte="anagrafica")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if data.motivo not in stato_rapporto.MOTIVI_CESSAZIONE:
        raise HTTPException(status_code=400, detail="Motivo non valido: " + ", ".join(stato_rapporto.MOTIVI_CESSAZIONE))
    nome = dip.get("nome_completo") or f"{dip.get('cognome','')} {dip.get('nome','')}".strip()
    await db.dipendenti.update_one({"id": dipendente_id}, {"$set": campi})
    # Il PIN si spegne subito con la cessazione (R3), anche se l'iter
    # automatico a valle dovesse fallire.
    try:
        from app.hr.services.auth_dipendenti import rimuovi_pin
        await rimuovi_pin(dipendente_id)
    except Exception as e:
        logger.warning("revoca PIN alla cessazione non riuscita per %s: %s", dipendente_id, e)
    try:
        from app.hr.services.event_bus import propagate_event, EventTypes
        risultati = await propagate_event(EventTypes.DIPENDENTE_CESSATO, {
            "dipendente_id": dipendente_id, "nome_completo": nome,
            "data_cessazione": campi["data_fine_rapporto"], "motivo": campi["motivo_cessazione"],
        }, db, source_module="gestione", user="admin")
    except Exception as e:
        risultati = [{"error": str(e)}]
    aggiornato = await db.dipendenti.find_one({"id": dipendente_id}, {"_id": 0})
    return {"ok": True, "stato": "cessato", "data_cessazione": campi["data_fine_rapporto"],
            "automazioni": risultati, "dipendente": _vista_dipendente(aggiornato)}

@router.post("/dipendenti/{dipendente_id}/riattiva")
async def riattiva_dipendente(dipendente_id: str):
    """Rimette in forza un cessato (errore o riassunzione): la cessazione
    precedente resta nello storico della scheda."""
    db = get_db()
    dip = await db.dipendenti.find_one({"id": dipendente_id}, {"_id": 0})
    if not dip:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    st = stato_rapporto.riepilogo_stato(dip)
    upd = stato_rapporto.campi_riattivazione()
    if st["stato"] == "cessato":
        storico = list(dip.get("cessazioni_precedenti") or [])
        storico.append({"data_fine_rapporto": st["data_fine_rapporto"], "motivo": st["motivo_cessazione_originale"],
                        "riferimento": st["riferimento_cessazione"], "riattivato_il": now_iso()})
        upd["$set"]["cessazioni_precedenti"] = storico
    await db.dipendenti.update_one({"id": dipendente_id}, upd)
    aggiornato = await db.dipendenti.find_one({"id": dipendente_id}, {"_id": 0})
    return {"ok": True, "stato": "attivo", "dipendente": _vista_dipendente(aggiornato)}

@router.post("/dipendenti/{dipendente_id}/pin")
async def imposta_pin_dipendente(dipendente_id: str, payload: PinCloud):
    """PIN personale (R2): uno per persona, vale per il portale e per firmare
    in Lotti. Mai mostrato; qui si puo' solo impostare o reimpostare."""
    from app.hr.services import auth_dipendenti
    try:
        ok = await auth_dipendenti.imposta_pin(dipendente_id, str(payload.pin or "").strip())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    return {"ok": True, "pin_impostato": True}

@router.delete("/dipendenti/{dipendente_id}/pin")
async def rimuovi_pin_dipendente(dipendente_id: str):
    from app.hr.services import auth_dipendenti
    if not await auth_dipendenti.rimuovi_pin(dipendente_id):
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    return {"ok": True, "pin_impostato": False}

@router.get("/ordine-dipendenti")
async def get_ordine_dipendenti():
    doc = await get_db().dipendenti_ordine.find_one({"id": "ordine"}, {"_id": 0})
    return {"ordine": (doc or {}).get("lista", [])}

@router.post("/ordine-dipendenti")
async def set_ordine_dipendenti(data: dict):
    lista = data.get("ordine", [])
    await get_db().dipendenti_ordine.update_one(
        {"id": "ordine"}, {"$set": {"lista": lista}}, upsert=True)
    return {"ok": True}

# ============ PAGHE MENSILI (importo busta + bonifico + acconti) ============

async def _ricalcola_bonifico_periodo(db, dip, anno, mese):
    """bonifico_importo della busta = somma degli esiti del periodo (anche 0),
    poi il motore unico. Stessa sequenza dell'importatore Drive e del ponte
    del gestionale: cosi' un pagamento spostato di mese aggiorna entrambi i
    mesi senza lasciare importi fantasma."""
    anno, mese = int(anno), int(mese)
    tot = 0.0
    async for e in db.pagamenti_esiti.find({"dipendente_id": dip, "mese": mese, "anno": anno},
                                            {"_id": 0, "importo": 1}):
        tot += float(e.get("importo") or 0)
    await db.paghe_mensili.update_one(
        {"dipendente_id": dip, "anno": anno, "mese": mese},
        {"$set": {"dipendente_id": dip, "anno": anno, "mese": mese,
                  "bonifico_importo": round(tot, 2), "bonifico_ricevuto": tot > 0,
                  "bonifico_da_esiti": True, "updated_at": now_iso()}}, upsert=True)
    return await _ricalcola_stato_paga(db, dip, anno, mese)


@router.put("/paghe/pagamento-esito/{key}")
async def modifica_pagamento_esito(key: str, data: dict = Body(...)):
    """Sposta un pagamento a un altro periodo e/o ne corregge l'importo
    (titolare 14/09/2026: "bonifico dell'1/1/2026, io lo sposto a dicembre
    2025: per pagare devo prima aspettare il cedolino"). Il pagamento resta
    UNO (stessa chiave, stesso PDF/CRO); cambiano competenza e importo, con
    traccia di cosa c'era prima. Entrambi i mesi vengono ricalcolati dal
    motore unico."""
    db = get_db()
    esito = await db.pagamenti_esiti.find_one({"key": key}, {"_id": 0, "pdf_data": 0})
    if not esito:
        raise HTTPException(status_code=404, detail="Pagamento non trovato")
    dip = esito.get("dipendente_id")
    if not dip:
        raise HTTPException(status_code=400, detail="Pagamento senza dipendente: assegnalo prima dalla coda")
    try:
        mese = int(data.get("mese") or esito.get("mese"))
        anno = int(data.get("anno") or esito.get("anno"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="mese/anno non validi") from exc
    if not (1 <= mese <= 14) or anno < 2000:
        raise HTTPException(status_code=400, detail="mese deve essere 1-14, anno >= 2000")
    importo = esito.get("importo")
    if data.get("importo") not in (None, ""):
        try:
            importo = round(float(data["importo"]), 2)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="importo non valido") from exc
        if importo <= 0:
            raise HTTPException(status_code=400, detail="importo deve essere positivo")
    vecchio = (int(esito.get("anno") or 0), int(esito.get("mese") or 0))
    storia = list(esito.get("modifiche_manuali") or [])
    storia.append({"da_mese": esito.get("mese"), "da_anno": esito.get("anno"),
                   "da_importo": esito.get("importo"), "a_mese": mese, "a_anno": anno,
                   "a_importo": importo, "nota": str(data.get("nota") or ""), "at": now_iso()})
    await db.pagamenti_esiti.update_one({"key": key}, {"$set": {
        "mese": mese, "anno": anno, "importo": importo,
        "modificato_manualmente": True, "modifiche_manuali": storia[-20:],
        "nota_modifica": str(data.get("nota") or ""), "updated_at": now_iso()}})
    stati = {}
    for a, m in {vecchio, (anno, mese)}:
        if a and m:
            stati[f"{a}-{m:02d}"] = await _ricalcola_bonifico_periodo(db, dip, a, m)
    return {"ok": True, "key": key, "dipendente_id": dip, "mese": mese, "anno": anno,
            "importo": importo, "stati": stati}


@router.put("/paghe/importo-busta")
async def modifica_importo_busta(data: dict = Body(...)):
    """Corregge l'importo della busta di un mese quando non torna col cedolino
    (titolare 14/09/2026). Il valore manuale vince sulla sincronizzazione dai
    cedolini (`origine: manuale`, stessa regola dell'inserimento a mano) e
    resta tracciato con l'importo precedente e la nota."""
    dip = data.get("dipendente_id"); anno = data.get("anno"); mese = data.get("mese")
    if not dip or not anno or not mese:
        raise HTTPException(status_code=400, detail="dipendente_id, anno, mese obbligatori")
    try:
        anno, mese = int(anno), int(mese)
        importo = round(float(data.get("importo_busta")), 2)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="importo_busta non valido") from exc
    if importo < 0:
        raise HTTPException(status_code=400, detail="importo_busta non puo' essere negativo")
    db = get_db()
    paga = await db.paghe_mensili.find_one({"dipendente_id": dip, "anno": anno, "mese": mese}, {"_id": 0}) or {}
    set_doc = {"dipendente_id": dip, "anno": anno, "mese": mese, "importo_busta": importo,
               "netto_confermato": None,
               "origine": "manuale", "importo_busta_manuale": True,
               "importo_busta_nota": str(data.get("nota") or ""),
               "importo_busta_modificato_il": now_iso(), "updated_at": now_iso()}
    if "importo_busta_originale" not in paga:
        set_doc["importo_busta_originale"] = paga.get("importo_busta")
    await db.paghe_mensili.update_one({"dipendente_id": dip, "anno": anno, "mese": mese},
                                      {"$set": set_doc}, upsert=True)
    stato = await _ricalcola_stato_paga(db, dip, anno, mese)
    return {"ok": True, "dipendente_id": dip, "anno": anno, "mese": mese,
            "importo_busta": importo, "importo_busta_originale": set_doc.get("importo_busta_originale", paga.get("importo_busta_originale")),
            "stato": stato}


@router.post("/paghe/sincronizza")
async def sincronizza_paghe_da_cedolini(anno: Optional[int] = None):
    """Popola il registro paghe dai cedolini e dai bonifici reali gia' in
    archivio, invece di lasciarlo alla compilazione manuale. Non tocca un mese
    che qualcuno ha gia' modificato a mano."""
    from app.hr.services.sincronizza_paghe_mensili import sincronizza
    return await sincronizza(get_db(), anno)


@router.post("/paghe/sincronizza-bonifici-storici")
async def sincronizza_bonifici_storici():
    """Ponte una tantum (ma ripetibile: idempotente) tra la collezione `bonifici`
    (dove un import passato dei PDF storici ha salvato ~800 bonifici reali con
    dipendente_id + competenza "YYYY-MM", ma NESSUN cedolino_id) e il motore unico
    di "Cedolini & Bonifici" / stato paga, che legge solo `pagamenti_esiti`.
    Senza questo ponte quei bonifici — già nell'archivio, già con il PDF allegato —
    restavano invisibili nella pagina di riconciliazione e le buste corrispondenti
    risultavano ancora "da pagare". Non tocca i pagamenti "una_tantum" (TFR/
    transazioni di fine rapporto: competenza non è un mese di stipendio)."""
    db = get_db()
    # Esclude i bonifici già scritti a mano dalla coda "Bonifici da associare"
    # (associa_bonifico li ha già messi in pagamenti_esiti con la chiave
    # "beneficiari-diversi:*"): reimportarli qui creerebbe una seconda riga in
    # pagamenti_esiti per lo stesso pagamento, raddoppiando il bonifico del mese.
    # pdf_data ESCLUSO dal caricamento in blocco (05/09/2026): 805 degli 887
    # bonifici hanno il PDF allegato, 180 MB di base64 in tutto. Caricarli
    # interi per leggerne solo dipendente/data/importo/competenza ha mandato
    # in 503 continuo l'AppDipendenti standalone (piano free, 512 MB): qui il
    # processo e' condiviso con tutto il gestionale, non c'e' motivo di
    # occupare quella memoria ogni 6 ore. Il PDF viene letto piu' sotto, uno
    # alla volta, solo per i bonifici che vengono davvero importati.
    bonifici = await db.bonifici.find(
        {"categoria": "DIPENDENTE", "dipendente_id": {"$ne": None}, "competenza": {"$ne": None},
         "assegnato_da_bonifico_diversi": {"$exists": False}},
        {"_id": 0, "pdf_data": 0}).to_list(5000)

    # Prefetch in blocco (stesso motivo delle altre correzioni in questo file):
    # un find_one per bonifico dentro il ciclo, su una tabella non indicizzata,
    # è di nuovo un incrocio N×M — con ~800 bonifici storici è la stessa causa
    # dei 502 già visti in produzione. pdf_data escluso: qui serve solo la
    # tripletta dipendente/data/importo per il controllo duplicati.
    pagamenti_esistenti = set()
    async for p in db.pagamenti_esiti.find({}, {"_id": 0, "pdf_data": 0, "causale": 0, "beneficiario": 0}):
        pagamenti_esistenti.add((p.get("dipendente_id"), p.get("data"), p.get("importo")))

    affected = set()
    importati = duplicati = 0
    for b in bonifici:
        competenza = str(b.get("competenza") or "")
        m = re.match(r"^(\d{4})-(\d{1,2})$", competenza)
        if not m:
            continue
        anno, mese = int(m.group(1)), int(m.group(2))
        dip_id = b.get("dipendente_id")
        importo = b.get("importo")
        data_pag = b.get("data")
        if not dip_id or not importo:
            continue
        # Difesa aggiuntiva: stesso dipendente/data/importo già presente in
        # pagamenti_esiti (da CSV, da un'altra corsa di questo stesso ponte, o
        # da un altro percorso) -> non è un nuovo pagamento, salta.
        if (dip_id, data_pag, importo) in pagamenti_esistenti:
            duplicati += 1
            continue
        pagamenti_esistenti.add((dip_id, data_pag, importo))
        key = f"bonifici-coll:{b.get('id')}"
        doc = {"key": key, "cro": None, "dipendente_id": dip_id,
               "data": data_pag, "importo": importo,
               "causale": b.get("fonte") or "Archivio bonifici PDF",
               "beneficiario": b.get("dipendente_nome"),
               "mese": mese, "anno": anno, "origine": "bonifici-storico"}
        # Il PDF si legge solo qui, per il singolo bonifico che entra davvero
        # (il caricamento in blocco sopra lo esclude per non saturare la memoria).
        con_pdf = await db.bonifici.find_one({"id": b.get("id")}, {"_id": 0, "pdf_data": 1})
        if con_pdf and con_pdf.get("pdf_data"):
            doc["pdf_data"] = con_pdf["pdf_data"]
            doc["ha_pdf"] = True
        await db.pagamenti_esiti.update_one({"key": key}, {"$set": doc}, upsert=True)
        await db.paghe_mensili.update_one(
            {"dipendente_id": dip_id, "anno": anno, "mese": mese},
            {"$set": {"dipendente_id": dip_id, "anno": anno, "mese": mese,
                      "updated_at": now_iso()}}, upsert=True)
        affected.add((dip_id, mese, anno))
        importati += 1

    for dip_id, mese, anno in affected:
        tot = 0.0
        async for p in db.pagamenti_esiti.find({"dipendente_id": dip_id, "mese": mese, "anno": anno}, {"_id": 0, "importo": 1}):
            tot += p.get("importo") or 0
        await db.paghe_mensili.update_one(
            {"dipendente_id": dip_id, "anno": anno, "mese": mese},
            {"$set": {"bonifico_importo": round(tot, 2), "bonifico_ricevuto": tot > 0,
                      "bonifico_da_esiti": True, "updated_at": now_iso()}})
        await _ricalcola_stato_paga(db, dip_id, anno, mese)

    return {"bonifici_esaminati": len(bonifici), "importati_in_pagamenti_esiti": importati,
            "duplicati_saltati": duplicati, "mesi_aggiornati": len(affected)}


class AccontiCloud(BaseModel):
    dipendente_id: str
    anno: int
    mese: int
    acconti: List[Dict[str, Any]] = []


@router.put("/paghe/acconti")
async def imposta_acconti(payload: AccontiCloud):
    """Acconti in contanti del mese (max 3, importo + data): l'UNICA cosa che
    si inserisce a mano oltre alle correzioni; busta e bonifici arrivano dai
    cedolini e dalla banca. Tocca solo il campo ``acconti`` e ricalcola lo
    stato col motore unico (14/09/2026: la vecchia pagina «Buste Paga»
    riscriveva busta e bonifico a mano, da qui i dati discordanti)."""
    acconti = []
    for a in (payload.acconti or [])[:3]:
        try:
            importo = round(float(str(a.get("importo")).replace(",", ".")), 2)
        except (TypeError, ValueError):
            continue
        if importo <= 0:
            continue
        acconti.append({"importo": importo, "data": (a.get("data") or None)})
    db = get_db()
    dipendente = await db.dipendenti.find_one(
        {"id": payload.dipendente_id},
        {"_id": 0, "stato": 1, "attivo": 1, "in_carico": 1,
         "data_fine_rapporto": 1, "data_cessazione": 1,
         "data_dimissione": 1, "data_cessazione_prevista": 1},
    )
    if not dipendente:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    from app.hr.services.regole_pagamenti_dipendenti import filtra_acconti_contanti

    acconti, non_ammessi = filtra_acconti_contanti(dipendente, acconti)
    if non_ammessi:
        primo = non_ammessi[0]
        raise HTTPException(
            status_code=422,
            detail={
                "codice": "CONTANTI_NON_AMMESSI",
                "messaggio": ("Dal 1 luglio 2018 i contanti sono ammessi solo dopo la cessazione "
                              "del rapporto, con data di cessazione salvata"),
                "data_pagamento": primo.get("data"),
                "data_cessazione": primo.get("data_cessazione_rapporto"),
                "motivo": primo.get("dettaglio_motivo"),
            },
        )
    await db.paghe_mensili.update_one(
        {"dipendente_id": payload.dipendente_id, "anno": int(payload.anno), "mese": int(payload.mese)},
        {"$set": {"acconti": acconti, "updated_at": now_iso()},
         "$setOnInsert": {"dipendente_id": payload.dipendente_id, "anno": int(payload.anno), "mese": int(payload.mese)}},
        upsert=True)
    stato = await _ricalcola_stato_paga(db, payload.dipendente_id, int(payload.anno), int(payload.mese))
    return {"ok": True, "acconti": acconti, "stato": stato}


async def _ricalcola_stato_paga(db, dip, anno, mese):
    """MOTORE UNICO buste↔bonifici. Aggancia i pagamenti bancari già arrivati
    (pagamenti_esiti) come bonifico del mese e ricalcola lo stato:
    in_attesa_pagamento (busta senza pagamento) / parziale / pagato / vuoto.
    Chiamato da OGNI ingresso (busta da LUL/email, prima nota, CSV, modifica manuale),
    così il popolamento di un dato aggiorna automaticamente gli altri."""
    anno, mese = int(anno), int(mese)
    p = await db.paghe_mensili.find_one({"dipendente_id": dip, "anno": anno, "mese": mese})
    if not p:
        return None
    # Importi in Decimal e confronto al centesimo (titolare 02/10/2026: niente
    # tolleranza). Una busta non ancora in archivio e' ``None``, mai 0: il
    # bonifico arrivato prima della busta resta «in attesa della busta».
    from app.services import posizione_dipendente as pos

    from app.constants.stati_associazione_bonifico import esiti_riconciliati, esiti_confermati, ha_riscontro_bancario
    from app.services.pagamenti_mensilita import periodi_saldati
    tot_esiti, n_esiti, esiti = pos.ZERO, 0, []
    async for e in db.pagamenti_esiti.find({"dipendente_id": dip, "mese": mese, "anno": anno}, {"_id": 0, "pdf_data": 0}):
        if periodi_saldati(e):
            continue
        tot_esiti += pos.importo(e.get("importo")) or pos.ZERO
        n_esiti += 1
        esiti.append(e)
    bonifico = tot_esiti if n_esiti else (pos.ZERO if p.get("bonifico_da_esiti") else (pos.importo(p.get("bonifico_importo")) or pos.ZERO))
    busta = pos.importo(p.get("importo_busta"))
    from app.hr.services.regole_pagamenti_dipendenti import filtra_acconti_contanti

    acconti_salvati = p.get("acconti") or []
    dipendente = {}
    if acconti_salvati:
        dipendente = await db.dipendenti.find_one(
            {"id": dip},
            {"_id": 0, "stato": 1, "attivo": 1, "in_carico": 1,
             "data_fine_rapporto": 1, "data_cessazione": 1,
             "data_dimissione": 1, "data_cessazione_prevista": 1},
        ) or {}
    acconti_validi, _ = filtra_acconti_contanti(dipendente, acconti_salvati)
    acc = sum((pos.importo(a.get("importo")) or pos.ZERO for a in acconti_validi), pos.ZERO)
    # Gli acconti del registro unico (anche quelli nati da «Bonifici da associare»)
    # sono pagamenti sulla busta come per la posizione dipendente: lo stesso conto.
    acconti_registro = await db.acconti_dipendenti.find(
        {"dipendente_id": dip}, {"_id": 0}).to_list(2000)
    acc += pos.acconti_registro_del_mese(acconti_registro, anno, mese, p.get("acconti") or [])
    erogato = bonifico + acc
    stato = stato_paga_mese(busta, erogato)
    automatico = esiti_riconciliati(esiti)
    riconciliato = p.get("bonifico_riconciliato") is True or esiti_confermati(esiti)
    if bonifico > 0 and busta is not None and not riconciliato:
        stato = "da_verificare"
    upd = {"stato_pagamento": stato,
           "saldo": float(busta - erogato) if busta is not None else None,
           "pagamenti_copertura": [],
           "updated_at": now_iso()}
    if n_esiti or p.get("bonifico_da_esiti"):
        upd["bonifico_importo"] = float(bonifico)
        upd["bonifico_da_esiti"] = True
        upd["bonifico_ricevuto"] = bonifico > 0 and all(ha_riscontro_bancario(e) for e in esiti)
        upd["bonifico_riconciliato_auto"] = automatico
    await db.paghe_mensili.update_one({"dipendente_id": dip, "anno": anno, "mese": mese}, {"$set": upd})
    from app.services.pagamenti_mensilita import indice_coperture, stato_copertura
    tutte_prove = await db.pagamenti_esiti.find({"dipendente_id": dip}, {"_id": 0, "pdf_data": 0}).to_list(None)
    copertura = indice_coperture(tutte_prove).get((dip, anno, mese))
    if copertura:
        await db.paghe_mensili.update_one({"dipendente_id": dip, "anno": anno, "mese": mese},
                                         {"$set": stato_copertura(copertura)})
        return "pagato_documentato"
    return stato

# ============ BONIFICI DA ASSOCIARE ============
# Bonifici bancari "BENEFICIARI DIVERSI": la banca li emette come un unico
# addebito cumulativo su piu' persone, senza nominarne nessuna nel documento.
# Non c'e' modo di attribuirli automaticamente: qui restano in coda, con
# menu a tendina dipendente + periodo, finche' qualcuno non li assegna a mano.

@router.get("/bonifici-da-associare")
async def lista_bonifici_da_associare():
    """Pagina unica delle assegnazioni manuali, comprese le distinte."""
    from app.database import Database as DatabaseGestionale
    from app.services.candidati_bonifico import arricchisci_coda, integra_dettagli_distinta
    from app.services.distinte_bonifici import elenco_distinte

    db = get_db()
    righe = await db.bonifici_da_associare.find(
        {"stato": "da_associare"}, {"_id": 0, "pdf_data": 0}).to_list(500)
    righe.sort(key=lambda r: r.get("data") or "", reverse=True)
    # «Distinte bonifici» era una seconda pagina sulla stessa coda. I dettagli
    # specifici (estratto, ricevuta, commissione e suggerimenti) entrano ora
    # nella pagina unica, riusando le righe gia' lette da Supabase.
    distinte = await elenco_distinte(DatabaseGestionale.get_db(), db, coda=righe)
    distinte_per_id = {r["id"]: r.get("distinta") for r in distinte}
    # Ogni riga porta i candidati (fino a 10, mai applicati), l'avviso
    # multi-dipendente, `rif_banca` e `cro`: chi sceglie vede da dove viene il bonifico.
    arricchite = await arricchisci_coda(db, righe)
    for riga in arricchite:
        if riga.get("id") in distinte_per_id:
            integra_dettagli_distinta(riga, distinte_per_id[riga["id"]])
    return arricchite


@router.get("/bonifici-da-associare/distinte")
async def distinte_da_associare():
    """Alias API compatibile: la logica vive nella pagina unica."""
    return [r for r in await lista_bonifici_da_associare() if r.get("distinta")]


@router.get("/paghe/pagamento-esito/{key}/pdf")
async def pdf_pagamento_esito(key: str):
    """PDF sorgente di un bonifico già associato a una busta (pagamenti_esiti),
    per verificarlo prima di premere Conferma — solo se è stato importato con
    l'allegato (Drive o ponte bonifici storici; i CSV banca non hanno PDF)."""
    doc = await get_db().pagamenti_esiti.find_one(
        {"key": key}, {"_id": 0, "pdf_data": 1})
    if not doc or not doc.get("pdf_data"):
        raise HTTPException(404, "PDF non disponibile per questo pagamento")
    pdf_bytes = base64.b64decode(doc["pdf_data"])
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": 'inline; filename="bonifico.pdf"'})


@router.get("/bonifici-da-associare/{bonifico_id}/pdf")
async def pdf_bonifico_da_associare(bonifico_id: str):
    doc = await get_db().bonifici_da_associare.find_one(
        {"id": bonifico_id}, {"_id": 0, "pdf_data": 1, "pdf_filename": 1})
    if not doc or not doc.get("pdf_data"):
        raise HTTPException(404, "PDF non trovato")
    pdf_bytes = base64.b64decode(doc["pdf_data"])
    fname = doc.get("pdf_filename") or "bonifico.pdf"
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{fname}"'})


def _attore(utente: Optional[Dict[str, Any]]) -> str:
    """Chi conferma: il nome nel token, altrimenti il ruolo."""
    utente = utente if isinstance(utente, dict) else {}
    return str(utente.get("name") or utente.get("sub") or utente.get("role") or "admin")


def _riferimento_coda(bonifico_id: str) -> str:
    """Il riferimento con cui un bonifico associato a mano compare in ``cedolini.pagamenti``."""
    return f"hr:bonifici_da_associare:{bonifico_id}"


def _db_gestionale():
    """L'archivio del gestionale, o None se non raggiungibile (si dice nel log)."""
    try:
        from app.database import Database as DatabaseGestionale

        return DatabaseGestionale.get_db()
    except Exception as exc:  # noqa: BLE001 - il segno HR e' gia' scritto
        logger.warning("Conferma bonifico: archivio gestionale non raggiungibile (%s: %s)",
                       type(exc).__name__, exc)
        return None


async def _segna_conferma(db, in_coda: Dict[str, Any], attore: str, evento: Dict[str, Any]) -> Dict[str, Any]:
    """Il bonifico associato a mano porta ``confermato_manuale`` (campi + storico
    sulla riga in coda) e lo stesso segno sul movimento e sulla ricevuta del
    gestionale da cui nasce. Restituisce i campi, da riusare su bonifico ed esito."""
    from app.services.conferma_bonifico import campi_conferma, imposta_conferma_gestionale

    campi = campi_conferma(attore)
    await db.bonifici_da_associare.update_one(
        {"id": in_coda["id"]},
        {"$set": campi,
         "$push": {"storico": {"azione": "conferma_manuale", "da": attore,
                               "il": campi["confermato_il"], **evento}}})
    await imposta_conferma_gestionale(_db_gestionale(), in_coda, campi)
    return campi


@router.post("/bonifici-da-associare/{bonifico_id}/associa")
async def associa_bonifico(bonifico_id: str, data: Dict[str, Any] = Body(...),
                           utente: Dict[str, Any] = Depends(require_staff)):
    """Assegna un bonifico in coda a un dipendente, scelto a mano, e dice che
    cosa e' (``tipo``):

    * ``stipendio`` (difetto): diventa un bonifico vero del periodo (stessa
      collezione degli altri, stessa riconciliazione) col PDF come prova;
    * ``acconto``: va nel registro unico degli acconti, come pagamento sulla
      posizione del dipendente; non si somma a nessun netto;
    * ``conciliazione`` / ``bonus``: pagamento della parte ordinaria o del
      bonus di una conciliazione del dipendente (``conciliazione_id``).

    Il mese della busta deve essere esplicito per uno stipendio. Un acconto
    puo' restare senza competenza e riduce il saldo alla data del pagamento.
    Un bonifico gia' associato non si associa una seconda volta."""
    from app.services import posizione_dipendente as pos

    dipendente_id = data.get("dipendente_id")
    tipo = str(data.get("tipo") or "stipendio").strip().lower()
    if tipo not in pos.TIPI_BONIFICO_CODA:
        raise HTTPException(400, {"code": "TIPO_NON_AMMESSO", "message": "Tipo: stipendio, acconto, conciliazione o bonus",
                                  "details": {"ammessi": list(pos.TIPI_BONIFICO_CODA)}})
    if not dipendente_id:
        raise HTTPException(400, "dipendente_id obbligatorio")

    db = get_db()
    in_coda = await db.bonifici_da_associare.find_one({"id": bonifico_id}, {"_id": 0})
    if not in_coda:
        raise HTTPException(404, "Bonifico non trovato in coda")
    if in_coda.get("stato") not in (None, "da_associare"):
        raise HTTPException(409, {"code": "GIA_ASSOCIATO", "message": "Bonifico gia' uscito dalla coda",
                                  "details": {"stato": in_coda.get("stato")}})
    # Lo stesso bonifico visto da un'altra riga (ricevuta ed estratto hanno lo
    # stesso «MB…») gia' confermato a mano e' consumato: non si associa due volte.
    from app.services.conferma_bonifico import chiavi_confermate, e_consumato

    if e_consumato(in_coda, await chiavi_confermate(db)):
        raise HTTPException(409, {"code": "GIA_ASSOCIATO",
                                  "message": "Questo bonifico e' gia' stato confermato a mano da un'altra riga",
                                  "details": {"stato": "confermato_altrove"}})
    attore = _attore(utente)
    dip = await db.dipendenti.find_one({"id": dipendente_id}, {"_id": 0})
    if not dip:
        raise HTTPException(404, "Dipendente non trovato")
    # La data dell'addebito non prova quale mensilita' si sta pagando.
    anno = mese = None
    try:
        if data.get("anno") not in (None, "") or data.get("mese") not in (None, ""):
            anno = int(data.get("anno"))
            mese = int(data.get("mese"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, "Indica sia mese sia anno di competenza, oppure lasciali entrambi vuoti per un acconto") from exc
    if anno is not None and (not (1 <= mese <= 14) or anno < 2000):
        raise HTTPException(400, "mese deve essere 1-14, anno >= 2000")
    if tipo == "stipendio" and anno is None:
        raise HTTPException(400, "Scegli la competenza del cedolino oppure Acconto / pagamento da attribuire")
    competenza = "%s-%02d" % (anno, mese) if anno is not None else None

    if tipo != "stipendio":
        try:
            if tipo == "acconto":
                esito = await pos.registra_acconto_da_coda(db, in_coda, dip, anno, mese)
                rif = {"acconto_id": esito["id"]}
            else:
                if not data.get("conciliazione_id"):
                    raise pos.ErrorePosizione("CONCILIAZIONE_MANCANTE", "Scegli la conciliazione del dipendente")
                esito = await pos.aggiungi_pagamento(db, data["conciliazione_id"], {
                    "dipendente_id": dipendente_id, "data": in_coda.get("data"),
                    "importo": in_coda.get("importo"), "modalita": "bonifico",
                    "parte": "bonus" if tipo == "bonus" else "conciliazione",
                    "origine": "bonifici_da_associare", "bonifico_da_associare_id": bonifico_id,
                })
                rif = {"conciliazione_id": data["conciliazione_id"]}
        except pos.ErrorePosizione as exc:
            raise HTTPException(400, exc.come_dict()) from exc
        await db.bonifici_da_associare.update_one(
            {"id": bonifico_id},
            {"$set": {"stato": "associato", "associato_a": dipendente_id, "associato_tipo": tipo,
                      "associato_competenza": competenza, "associato_il": now_iso(), **rif}})
        await _segna_conferma(db, in_coda, attore, {"dipendente_id": dipendente_id, "tipo": tipo,
                                                    "competenza": competenza})
        if tipo == "acconto" and anno is not None:
            # l'acconto e' un pagamento sulla busta del mese: lo stato del mese lo conta
            await _ricalcola_stato_paga(db, dipendente_id, anno, mese)
        return {"ok": True, "tipo": tipo, **rif}

    nuovo = {
        "id": str(uuid.uuid4()), "dipendente_id": dipendente_id,
        "dipendente_nome": dip.get("nome_completo"),
        "data": in_coda.get("data"), "importo": in_coda.get("importo"),
        "competenza": "%s-%02d" % (int(anno), int(mese)),
        "categoria": "DIPENDENTE",
        "pdf_filename": in_coda.get("pdf_filename"), "pdf_data": in_coda.get("pdf_data"),
        "fonte": in_coda.get("fonte"),
        "assegnato_manualmente": True,
        "assegnato_da_bonifico_diversi": bonifico_id,
        "created_at": now_iso(),
    }
    await db.bonifici.insert_one(nuovo)
    await db.bonifici_da_associare.update_one(
        {"id": bonifico_id},
        {"$set": {"stato": "associato", "associato_a": dipendente_id, "associato_tipo": "stipendio",
                  "associato_competenza": nuovo["competenza"], "associato_il": now_iso()}})
    campi = await _segna_conferma(db, in_coda, attore, {"dipendente_id": dipendente_id, "tipo": "stipendio",
                                                        "competenza": nuovo["competenza"]})
    # Il bonifico e l'esito di pagamento portano lo stesso segno e le stesse
    # chiavi d'identita' (MB…, CRO, hash): nessun'altra riga li riassegna.
    identita = {k: in_coda.get(k) for k in ("rif_banca", "cro", "hash",
                                            "gestionale_movimento_id", "gestionale_transfer_id")
                if in_coda.get(k)}
    await db.bonifici.update_one({"id": nuovo["id"]}, {"$set": {**campi, **identita,
                                                               "bonifico_da_associare_id": bonifico_id}})

    # Aggancia anche al MOTORE UNICO paghe (pagamenti_esiti + paghe_mensili):
    # senza questo passo l'associazione restava confinata alla collezione
    # `bonifici` e non si vedeva mai né in "Cedolini & Bonifici" né sulla busta
    # come pagata, perché quella vista/lo stato paga leggono solo pagamenti_esiti.
    anno_i, mese_i = int(anno), int(mese)
    key = f"beneficiari-diversi:{bonifico_id}"
    await db.pagamenti_esiti.update_one(
        {"key": key},
        {"$set": {"key": key, "cro": in_coda.get("cro"), "dipendente_id": dipendente_id,
                  "data": in_coda.get("data"), "importo": in_coda.get("importo") or 0,
                  "causale": in_coda.get("causale") or "Bonifico beneficiari diversi",
                  "beneficiario": dip.get("nome_completo"),
                  "mese": mese_i, "anno": anno_i,
                  "bonifico_da_associare_id": bonifico_id, **campi, **identita}}, upsert=True)
    await db.paghe_mensili.update_one(
        {"dipendente_id": dipendente_id, "anno": anno_i, "mese": mese_i},
        {"$set": {"dipendente_id": dipendente_id, "anno": anno_i, "mese": mese_i,
                  "updated_at": now_iso()}}, upsert=True)
    await _ricalcola_stato_paga(db, dipendente_id, anno_i, mese_i)
    # Lo stato del mese (motore unico) si riflette sul cedolino del gestionale
    # (`pagato`, `importo_pagato`, `pagamenti[]`): un solo scrittore, lo stesso
    # della riconciliazione automatica. `ritira-conferma` lo riapre.
    cedolino_gest = await allinea_cedolino_gestionale_da_paghe(
        db, _db_gestionale(), dipendente_id, anno_i, mese_i,
        riferimento=_riferimento_coda(bonifico_id), importo=in_coda.get("importo"), data=in_coda.get("data"))
    return {"ok": True, "bonifico": nuovo, "cedolino_gestionale": cedolino_gest}


@router.post("/bonifici-da-associare/{bonifico_id}/ritira-conferma")
async def ritira_conferma_bonifico(bonifico_id: str, utente: Dict[str, Any] = Depends(require_staff)):
    """Annulla l'associazione a mano di un bonifico di tipo stipendio: il
    bonifico torna in coda, il pagamento esce dalla busta e il segno
    ``confermato_manuale`` si spegne (con chi e quando nello ``storico``).
    Acconti e conciliazioni si correggono dalla posizione del dipendente."""
    from app.services.conferma_bonifico import campi_ritiro, imposta_conferma_gestionale

    db = get_db()
    riga = await db.bonifici_da_associare.find_one({"id": bonifico_id}, {"_id": 0, "pdf_data": 0})
    if not riga:
        raise HTTPException(404, "Bonifico non trovato in coda")
    if riga.get("stato") != "associato" or riga.get("confermato_manuale") is not True:
        raise HTTPException(409, {"code": "NON_CONFERMATO", "message": "Il bonifico non e' confermato a mano",
                                  "details": {"stato": riga.get("stato")}})
    if riga.get("associato_tipo") != "stipendio":
        raise HTTPException(409, {"code": "NON_ANNULLABILE_QUI",
                                  "message": "Acconti e conciliazioni si correggono dalla posizione del dipendente",
                                  "details": {"tipo": riga.get("associato_tipo")}})
    attore = _attore(utente)
    dip_id = riga.get("associato_a")
    try:
        anno_i, mese_i = (int(x) for x in str(riga.get("associato_competenza") or "").split("-"))
    except ValueError:
        anno_i = mese_i = None
    bonifico = await db.bonifici.find_one({"assegnato_da_bonifico_diversi": bonifico_id}, {"_id": 0, "id": 1})
    if bonifico:
        await db.bonifici.delete_one({"id": bonifico["id"]})
    await db.pagamenti_esiti.delete_one({"key": f"beneficiari-diversi:{bonifico_id}"})
    if dip_id and anno_i:
        tot = 0.0
        async for e in db.pagamenti_esiti.find({"dipendente_id": dip_id, "mese": mese_i, "anno": anno_i},
                                               {"_id": 0, "importo": 1}):
            tot += float(e.get("importo") or 0)
        await db.paghe_mensili.update_one(
            {"dipendente_id": dip_id, "anno": anno_i, "mese": mese_i},
            {"$set": {"bonifico_importo": round(tot, 2), "bonifico_ricevuto": tot > 0, "updated_at": now_iso()}})
        await _ricalcola_stato_paga(db, dip_id, anno_i, mese_i)
        # il cedolino del gestionale perde questo pagamento e si riapre se non resta altro
        await allinea_cedolino_gestionale_da_paghe(
            db, _db_gestionale(), dip_id, anno_i, mese_i,
            riferimento=_riferimento_coda(bonifico_id), ritira=True)
    campi = campi_ritiro()
    await db.bonifici_da_associare.update_one(
        {"id": bonifico_id},
        {"$set": {"stato": "da_associare", "associato_a": None, "associato_tipo": None,
                  "associato_competenza": None, "associato_il": None, **campi},
         "$push": {"storico": {"azione": "ritira_conferma", "da": attore, "il": now_iso(),
                               "dipendente_id": dip_id}}})
    await imposta_conferma_gestionale(_db_gestionale(), riga, campi)
    return {"ok": True}


@router.post("/bonifici-da-associare/{bonifico_id}/ignora")
async def ignora_bonifico_da_associare(bonifico_id: str):
    """Non e' un pagamento a un dipendente (es. lotto di fornitori): esce
    dalla coda senza creare nulla."""
    res = await get_db().bonifici_da_associare.update_one(
        {"id": bonifico_id}, {"$set": {"stato": "ignorato", "ignorato_il": now_iso()}})
    if res.matched_count == 0:
        raise HTTPException(404, "Bonifico non trovato in coda")
    return {"ok": True}


_MOVIMENTO_NON_STIPENDIO_RE = re.compile(
    r"MUTUO|FINANZIAMENTO|QUIETANZA DI PAGAMENTO|CONTABILE DI FILIALE|"
    r"VERSAMENTO|UFFICIO SERVIZI VARI|AGENZIA DELLE ENTRATE|REGIONE \w+|"
    r"COMUNE DI |SPESE LIBR|ADDEBITO DIRETTO|SDD\b|INC\.?POS|"
    r"COMM\.?\s*SU BONIFICI|\bS\.?R\.?L\.?\b|\bS\.?P\.?A\.?\b|\bS\.?N\.?C\.?\b|\bS\.?A\.?S\.?\b",
    re.IGNORECASE)


def _e_movimento_non_stipendio(text: str) -> bool:
    """La cartella Drive dei bonifici (estratto conto aziendale) contiene di tutto:
    mutui, fornitori, tasse, versamenti contanti, utenze — non solo stipendi. Questi
    movimenti non vanno importati né messi in coda di revisione: inquinerebbero
    "Bonifici da associare" con roba che non è mai stata uno stipendio."""
    return bool(_MOVIMENTO_NON_STIPENDIO_RE.search(text or ""))


# [14/09/2026] Rimossi `_parse_bonifico_pdf` e `POST /paghe/importa-bonifici-drive`
# (lettura diretta della cartella Drive dei bonifici da questa app): i bonifici
# entrano ORA da un solo sistema, il ponte del gestionale
# (app/services/hr_pagamenti_deposito.py) che legge i fascicoli Drive
# DIPENDENTI/<persona>/BONIFICI e l'estratto conto e deposita in
# pagamenti_esiti/paghe_mensili/bonifici_da_associare ogni 15 minuti.
# `_e_movimento_non_stipendio` resta: e' riusato dal ponte.


_MESI_IMPORT_SALARI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
    "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}


def _mese_import_salari(value):
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        numeric = Decimal(str(value))
        return int(numeric) if numeric == numeric.to_integral_value() and 1 <= numeric <= 12 else None
    text = str(value).strip().lower()
    if text in _MESI_IMPORT_SALARI:
        return _MESI_IMPORT_SALARI[text]
    try:
        numeric = Decimal(text)
    except InvalidOperation:
        return None
    return int(numeric) if numeric == numeric.to_integral_value() and 1 <= numeric <= 12 else None


def _importo_import_salari(value):
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    text = str(value).strip().replace(" ", "")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


@router.post("/paghe/importa-excel-salari")
async def importa_excel_salari(file: UploadFile = File(...)):
    """Importa l'Excel 'prima nota salari' (colonne: DIPENDENTE, MESE, ANNO,
    STIPENDIO NETTO, IMPORTO EROGATO). Il netto fissa il valore atteso della busta,
    l'erogato il valore atteso del bonifico. I flag di riconciliazione partono a False
    e diventano True quando arriva il PDF (busta o ricevuta bonifico) con importo che
    combacia. I dipendenti non presenti in anagrafica vengono solo segnalati."""
    import openpyxl
    nome_file = (file.filename or "").lower()
    if not nome_file.endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=400, detail="Serve un file Excel (.xlsx)")

    data = await file.read()
    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Excel non leggibile: {e}") from e
    ws = wb.active

    dips = await get_db().dipendenti.find({}, {"_id": 0}).to_list(1000)
    from app.hr.services.identita_dipendente import indicizza_alias_univoci
    aliases = []
    for d in dips:
        cg = (d.get("cognome") or "").upper().strip()
        nm = (d.get("nome") or "").upper().strip()
        if cg or nm:
            aliases.extend([(f"{cg} {nm}".strip(), d), (f"{nm} {cg}".strip(), d)])
    anag = indicizza_alias_univoci(aliases)

    try:
        await get_db().paghe_mensili.create_index(
            [("dipendente_id", 1), ("anno", 1), ("mese", 1)], unique=True, name="uniq_dip_anno_mese")
    except Exception:
        pass

    importati, mesi_set, righe_lette = 0, set(), 0
    non_trovati, scartati = {}, []
    aggregati = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[0]:
            continue
        righe_lette += 1
        nome = str(row[0]).strip()
        mese = _mese_import_salari(row[1]) if len(row) > 1 else None
        try:
            anno_value = Decimal(str(row[2])) if len(row) > 2 and row[2] not in (None, "") else None
            anno = int(anno_value) if anno_value is not None and anno_value == anno_value.to_integral_value() else None
        except Exception:
            anno = None
        netto = _importo_import_salari(row[3]) if len(row) > 3 else None
        erogato = _importo_import_salari(row[4]) if len(row) > 4 else None

        dip = anag.get(nome.upper())
        if not dip:
            non_trovati[nome] = non_trovati.get(nome, 0) + 1
            continue
        if not mese or not anno or anno not in ANNI_AMMESSI:
            scartati.append({"nome": nome, "motivo": f"periodo non valido ({row[1]} {row[2]})"})
            continue

        key = (dip["id"], anno, mese)
        aggregato = aggregati.setdefault(key, {
            "netto": None,
            "erogato": Decimal("0"),
            "erogato_presente": False,
        })
        if netto is not None:
            if aggregato["netto"] is None:
                aggregato["netto"] = netto
            elif aggregato["netto"] != netto:
                scartati.append({
                    "nome": nome,
                    "motivo": f"stipendio netto incoerente nello stesso periodo ({aggregato['netto']} / {netto})",
                })
        if erogato is not None:
            aggregato["erogato"] += erogato
            aggregato["erogato_presente"] = True

    for (dipendente_id, anno, mese), aggregato in aggregati.items():
        netto = aggregato["netto"]
        erogato = aggregato["erogato"]
        set_doc = {
            "dipendente_id": dipendente_id,
            "anno": anno,
            "mese": mese,
            "fonte_excel": True,
            "updated_at": now_iso(),
        }
        if netto is not None:
            set_doc["importo_busta"] = float(netto)
            set_doc["netto_atteso"] = float(netto)
        if aggregato["erogato_presente"]:
            set_doc["bonifico_importo"] = float(erogato)
            set_doc["erogato_atteso"] = float(erogato)
            set_doc["bonifico_da_prima_nota"] = erogato > 0
        await get_db().paghe_mensili.update_one(
            {"dipendente_id": dipendente_id, "anno": anno, "mese": mese},
            {"$set": set_doc,
             "$setOnInsert": {"busta_riconciliata": False, "bonifico_riconciliato": False}},
            upsert=True)
        await _ricalcola_stato_paga(get_db(), dipendente_id, anno, mese)
        importati += 1
        mesi_set.add((anno, mese))

    mesi = sorted([{"anno": y, "mese": m} for (y, m) in mesi_set], key=lambda x: (x["anno"], x["mese"]))
    return {"importati": importati,
            "righe_lette": righe_lette,
            "righe_aggregate": len(aggregati),
            "mesi": mesi,
            "dipendenti_non_in_anagrafica": [{"nome": k, "righe": v} for k, v in sorted(non_trovati.items())],
            "scartati": scartati}


# --- Import automatico Libro Unico (PDF) → divide per dipendente e memorizza i netti ---

_CF_RE = re.compile(r'\b([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b')
_MESI = {"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
         "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12}
# Regola atomica: si importano SOLO questi anni. Tutto il resto è bloccato.
ANNI_AMMESSI = {2023, 2024, 2025, 2026}

def _lul_netto(text):
    m = re.findall(r'([\d]{1,3}(?:\.\d{3})*,\d{2})\s*€', text)
    return m[-1] if m else None

def _lul_acconto(text):
    """Rileva acconti/anticipi erogati durante il mese e trattenuti nel cedolino
    (righe con 'acconto', 'anticipo', 'rec. acconto', escluso il TFR). Serve a sapere
    quanto è già stato dato, così il bonifico del solo saldo chiude comunque la busta.
    Ritorna l'importo totale o None."""
    tot = 0.0
    for line in text.split("\n"):
        low = line.lower()
        if ("acconto" in low or "anticipo" in low) and "tfr" not in low and "trattamento fine" not in low:
            nums = re.findall(r'([\d]{1,3}(?:\.\d{3})*,\d{2})', line)
            if nums:
                tot += _to_float(nums[-1]) or 0
    return round(tot, 2) if tot > 0 else None

def _acconto_cedolino_plausibile(acconto, netto_totale):
    """Filtro anti-falso-positivo: '_lul_acconto' può intercettare per errore una
    trattenuta minima non correlata (es. quota associativa, conguaglio di pochi
    euro) che contiene la parola 'acconto'/'anticipo' ma non è un vero anticipo
    già erogato al dipendente. Un acconto reale è una cifra significativa
    rispetto al netto, non poche decine di euro: sotto soglia lo scartiamo
    invece di mostrare un 'saldo da pagare' sbagliato per pochi euro di
    differenza (stessa soglia usata in services/libro_unico_parser.py)."""
    if not acconto or acconto <= 0 or not netto_totale:
        return False
    soglia = max(80.0, netto_totale * 0.10)
    return acconto >= soglia

def _lul_periodo(text):
    m = re.search(r'(Gennaio|Febbraio|Marzo|Aprile|Maggio|Giugno|Luglio|Agosto|Settembre|Ottobre|Novembre|Dicembre)\s+(\d{4})', text, re.I)
    if m:
        return _MESI[m.group(1).lower()], int(m.group(2))
    return None, None

_LUL_NUM = re.compile(r'-?\d{1,3}(?:\.\d{3})*,\d{2,6}|-?\d+,\d{2,6}')


def _lul_dati_busta(text: str) -> dict:
    """Estrae dal testo della busta i dati chiave (per codice voce o descrizione).
    Robusto sul prefisso (C/F/Z…). L'ultimo numero della riga voce = importo competenza."""
    voci = []
    voci_obj = []
    for line in text.split("\n"):
        m = re.match(r'^\s*([A-Z]\d{4,5})\b\s*(.*)$', line)
        if m:
            resto, valori = m.group(2), _LUL_NUM.findall(m.group(2))
            voci.append((m.group(1), resto, valori))
            voci_obj.append({"codice": m.group(1),
                             "descrizione": _LUL_NUM.split(resto)[0].strip(' .-'),
                             "valori": valori})

    def find(codici=None, testo=None):
        for codice, resto, valori in voci:
            if (codici and codice in codici) or (testo and testo.lower() in resto.lower()):
                return valori[-1] if valori else None
        return None

    dati = {
        "rateo_13ma": find(codici={"C50000", "Z50000"}, testo="13ma Mensilit"),
        "rateo_14ma": find(codici={"C50022", "Z50022"}, testo="14ma Mensilit"),
        "indennita_l207_24": find(codici={"F02703"}),
        "indennita_l207_24_cng_ann": find(codici={"F09088"}),
        "tratt_integrativo_l21": find(codici={"F09081"}),
        "tratt_integrativo_l21_rata": find(codici={"F09083"}),
        "tratt_integrativo_l21_cng": find(codici={"F09084"}),
        # tutte le voci del cedolino (codici+descrizione+importi) per il motore di ricerca
        "voci": voci_obj or None,
    }
    # Rimborso da 730 (residuo + importo del mese)
    for codice, resto, valori in voci:
        if "730" in resto:
            dati["rimborso_730"] = valori[-1] if valori else None
            if len(valori) >= 2:
                dati["rimborso_730_residuo"] = valori[0]
            break
    # Ore lavorate + giorni retribuiti (riquadro 'Lavorato', best effort)
    lav = re.search(r'(?:Lavorato|Ore\s*lavorat\w*)\D{0,15}?(\d{1,3},\d{2})\s+(\d{1,2})\b', text, re.IGNORECASE)
    if lav:
        dati["ore_lavorate"] = lav.group(1)
        dati["giorni_retribuiti"] = lav.group(2)
    # Giorni effettivamente lavorati: righe del foglio presenze con ore (LU 19 6,40 ...)
    gg = set()
    for line in text.split("\n"):
        pm = re.search(r'\b(LU|MA|ME|GI|VE|SA|DO)\s+(\d{1,2})\s+\d{1,2},\d{2}\b', line)
        if pm:
            gg.add(pm.group(2))
    if gg:
        dati["giorni_lavorati"] = len(gg)
    return {k: v for k, v in dati.items() if v is not None}


def _parse_lul(pdf_path):
    """Raggruppa le pagine per codice fiscale (gestisce 1, 2 o 3 pagine a dipendente).
    Tiene anche traccia degli indici di pagina di ciascun dipendente, così l'import
    può ritagliare il PDF reale del suo cedolino."""
    import pdfplumber
    ced = {}
    page_count = 0
    with pdfplumber.open(pdf_path) as pdf:
        page_count = len(pdf.pages)
        cur = None
        for idx, page in enumerate(pdf.pages):
            t = page.extract_text() or ""
            cfs = _CF_RE.findall(t)
            mese, anno = _lul_periodo(t)
            if cfs:
                cur = cfs[0]
                d = ced.setdefault(cur, {"nome": None, "netto": None, "mese": None, "anno": None, "pagine": []})
                if mese:
                    d["mese"], d["anno"] = mese, anno
                for line in t.split("\n"):
                    mm = re.search(r'\b0[0-9]{6}\b\s+([A-ZÀ-Ù\' ]{4,}?)\s+[A-Z]{6}\d{2}[A-Z]', line)
                    if mm:
                        d["nome"] = mm.group(1).strip()
                        break
            if cur:
                ced[cur].setdefault("pagine", []).append(idx)
                n = _lul_netto(t)
                if n:
                    ced[cur]["netto"] = n
                acc = _lul_acconto(t)
                if acc:
                    ced[cur]["acconto"] = round((ced[cur].get("acconto") or 0) + acc, 2)
                if not ced[cur].get("mese") and mese:
                    ced[cur]["mese"], ced[cur]["anno"] = mese, anno
                # Dati chiave della busta (rateo 13/14, indennità L.207/24, tratt. integ. L.21, giorni)
                for k, v in _lul_dati_busta(t).items():
                    ced[cur][k] = v
    if len(ced) <= 1 and (not ced or not next(iter(ced.values())).get("netto")):
        try:
            from app.hr.parsers.busta_paga_multi_template import parse_busta_paga_multi
            parsed = parse_busta_paga_multi(pdf_path)
            dipendente = parsed.get("dipendente") or {}
            periodo = parsed.get("periodo") or {}
            totali = parsed.get("totali") or {}
            tax_code = (dipendente.get("codice_fiscale") or "").upper()
            if ced:
                record = next(iter(ced.values()))
            elif tax_code:
                record = ced.setdefault(tax_code, {
                    "nome": None, "netto": None, "mese": None, "anno": None,
                    "pagine": list(range(page_count)),
                })
            else:
                record = None
            if record is not None and parsed.get("parse_success"):
                if totali.get("netto") is not None:
                    record["netto"] = f"{float(totali['netto']):.2f}".replace(".", ",")
                record["nome"] = record.get("nome") or dipendente.get("nome_completo")
                record["mese"] = record.get("mese") or periodo.get("mese")
                record["anno"] = record.get("anno") or periodo.get("anno")
        except Exception:
            pass
    return ced

def _to_float(s):
    if isinstance(s, (int, float)):
        return float(s)
    return float(s.replace(".", "").replace(",", ".")) if s else None


def _ritaglia_pdf(pdf_path, pagine):
    """Estrae le pagine indicate dal PDF originale e le restituisce come bytes:
    è il cedolino reale del singolo dipendente dentro il Libro Unico."""
    import fitz
    src = fitz.open(pdf_path)
    out = fitz.open()
    for i in sorted(set(pagine)):
        if 0 <= i < src.page_count:
            out.insert_pdf(src, from_page=i, to_page=i)
    data = out.tobytes()
    out.close(); src.close()
    return data

def _estrai_testo(pdf_path):
    import pdfplumber
    parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts)

def _classifica_doc(text):
    """Distingue: bonifico (ricevuta bancaria), presenze (LUL ore/timbrature),
    cedolino (busta paga con netto). Default: cedolino (per il Libro Unico multi-dipendente)."""
    T = (text or "").upper()
    if "RICEVUTA PER ORDINANTE" in T or "A VOSTRO DEBITO A FAVORE DI" in T or ("BONIFICO" in T and "IBAN BENEFICIARIO" in T):
        return "bonifico"
    ha_netto = "NETTO DEL MESE" in T or "NETTOSDELSMESE" in T
    if ha_netto:
        return "cedolino"
    if ("PERIODO DI RIFERIMENTO" in T or "TIMBRATURE" in T or "ORE ORDINARIE" in T):
        return "presenze"
    return "cedolino"

def _competenza_da_causale(causale):
    """Estrae mese/anno SOLO se dichiarati esplicitamente nella causale."""
    c = (causale or "").lower()
    m = re.search(r'(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\s*(\d{4})?', c)
    if m:
        return _MESI[m.group(1)], (int(m.group(2)) if m.group(2) else None), True
    m = re.search(r'\b(0?[1-9]|1[0-2])[-/](\d{4})\b', c)
    if m:
        return int(m.group(1)), int(m.group(2)), True
    return None, None, False

def _parse_bonifico(text):
    imp = None
    m = re.search(r'EUR\s+([\d.]+,\d{2})', text) or re.search(r'IMPORTO\s+([\d.]+,\d{2})', text)
    if m:
        imp = _to_float(m.group(1))
    data = None
    md = re.search(r'DATA\s+(\d{2})/(\d{2})/(\d{4})', text)
    if md:
        data = f"{md.group(3)}-{md.group(2)}-{md.group(1)}"
    caus = None
    mc = re.search(r'CAUSALE\s*\n\s*([^\n]+)', text)
    if mc:
        caus = mc.group(1).strip()
    cro = None
    mr = re.search(r'(MB0B\w+)', text)
    if mr:
        cro = mr.group(1).strip()
    mese_c, anno_c, esplicita = _competenza_da_causale(caus)
    is_tfr = bool(re.search(r'\btfr\b|trattamento fine rapporto|anticipo\s+t\.?f\.?r', (caus or "").lower()))
    return {"importo": imp, "data": data, "causale": caus, "cro": cro,
            "mese_causale": mese_c, "anno_causale": anno_c, "esplicita": esplicita, "is_tfr": is_tfr}


async def _importa_documenti(pdf_items, errori_iniziali=None, forza=False):
    """Pipeline condivisa: riceve una lista di (origine, pdf_bytes) già espansi (da upload
    file o da posta elettronica), li classifica e li importa in paghe_mensili / prestiti.
    L'anti-duplicazione per hash evita di re-importare gli stessi documenti."""
    dips = await get_db().dipendenti.find({}, {"_id": 0}).to_list(1000)
    from app.hr.services.identita_dipendente import indicizza_alias_univoci, dipendente_unico
    by_cf = indicizza_alias_univoci((d.get("codice_fiscale"), d) for d in dips)
    aliases = []
    for d in dips:
        cg = (d.get("cognome") or "").upper().strip()
        nm = (d.get("nome") or "").upper().strip()
        if cg or nm:
            aliases.extend([(f"{cg} {nm}".strip(), d), (f"{nm} {cg}".strip(), d)])
    by_nome = indicizza_alias_univoci(aliases)

    # Vincolo: una sola busta per (dipendente, anno, mese) — i duplicati diventano impossibili
    try:
        await get_db().paghe_mensili.create_index(
            [("dipendente_id", 1), ("anno", 1), ("mese", 1)], unique=True, name="uniq_dip_anno_mese")
    except Exception:
        pass
    # Registro documenti importati (anti-duplicazione): impronta del file + chiave logica
    try:
        await get_db().documenti_importati.create_index([("hash", 1)], unique=True, name="uniq_hash")
        await get_db().documenti_importati.create_index([("chiave", 1)], name="idx_chiave")
    except Exception:
        pass

    async def _registra_doc(h, tipo, chiave, origine):
        await get_db().documenti_importati.update_one(
            {"hash": h},
            {"$set": {"hash": h, "tipo": tipo, "chiave": chiave, "file": origine,
                      "imported_at": now_iso()}}, upsert=True)

    async def _imputa_competenza(dip_id, b):
        """Solo la competenza esplicita autorizza l'imputazione automatica.

        Importi uguali o una data di disposizione non provano il mese della
        retribuzione: il documento resta da verificare, senza scegliere una busta.
        """
        if b["esplicita"] and b["mese_causale"]:
            return b["mese_causale"], b["anno_causale"], "causale"
        return None, None, "competenza non esplicita"

    async def _processa_pdf(pdfbytes, origine):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(pdfbytes)
            path = tmp.name
        ass, dac, bon, pres, dup, tfr, prestiti = [], [], [], [], [], [], []
        # Anti-duplicazione 1: stesso file già importato (impronta del contenuto)
        h = hashlib.sha256(pdfbytes).hexdigest()
        try:
            if not forza and await get_db().documenti_importati.find_one({"hash": h}):
                dup.append({"file": origine, "motivo": "documento già importato (stesso file)"})
                try: os.unlink(path)
                except Exception: pass
                return ass, dac, bon, pres, dup, tfr, prestiti
        except Exception:
            pass
        try:
            text = _estrai_testo(path)
            tipo = _classifica_doc(text)

            # ---- BONIFICO (ricevuta bancaria) ----
            if tipo == "bonifico":
                b = _parse_bonifico(text)
                # match dipendente: "COGNOME NOME" presente nel testo; fallback cognome nella causale
                T = text.upper()
                candidati = []
                for cand in dips:
                    cg = (cand.get("cognome") or "").upper().strip()
                    nm = (cand.get("nome") or "").upper().strip()
                    if cg and nm and any(re.search(r"\b" + re.escape(nome) + r"\b", T)
                                         for nome in (f"{cg} {nm}", f"{nm} {cg}")):
                        candidati.append(cand)
                dip = dipendente_unico(candidati)
                if not candidati:
                    cau = (b.get("causale") or "").upper()
                    candidati = []
                    for cand in dips:
                        cg = (cand.get("cognome") or "").upper().strip()
                        if cg and re.search(r"\b" + re.escape(cg) + r"\b", cau):
                            candidati.append(cand)
                    dip = dipendente_unico(candidati)
                manca = []
                if not dip: manca.append("dipendente non riconosciuto")
                if not b.get("importo"): manca.append("importo")
                if manca:
                    dac.append({"nome": (b.get("causale") or "?")[:30], "origine": origine,
                                "motivo": "bonifico: " + ", ".join(manca)})
                else:
                    caus_low = (b.get("causale") or "").lower()
                    if "prestito" in caus_low:
                        # PRESTITO: non imputare a buste paga; mastrino prestiti con saldo progressivo
                        data = b.get("data")
                        if not data:
                            dac.append({"nome": (b.get("causale") or "?")[:30], "origine": origine,
                                        "motivo": "prestito: data assente"})
                        elif int(data[:4]) not in ANNI_AMMESSI:
                            dac.append({"nome": (b.get("causale") or "?")[:30], "origine": origine,
                                        "motivo": f"anno {data[:4]} non ammesso — bloccato (solo 2023-2026)"})
                        else:
                            pa, pm = int(data[:4]), int(data[5:7])
                            cro = b.get("cro")
                            gia = await get_db().documenti_importati.find_one({"chiave": f"cro:{cro}"}) if cro else None
                            if gia:
                                dup.append({"file": origine, "motivo": f"prestito già importato (CRO {cro})"})
                            else:
                                await get_db().prestiti_dipendenti.insert_one({
                                    "id": str(uuid.uuid4()), "dipendente_id": dip["id"],
                                    "importo": b["importo"], "data": data, "mese": pm, "anno": pa,
                                    "causale": b.get("causale"), "cro": cro, "pdf": origine,
                                    "created_at": now_iso()})
                                saldo = await _ricalcola_saldo_prestiti(dip["id"])
                                await _registra_doc(h, "prestito",
                                    f"cro:{cro}" if cro else f"pre:{dip['id']}:{pa}:{pm}:{b['importo']}", origine)
                                prestiti.append({"dipendente": f"{dip.get('cognome')} {dip.get('nome')}".strip(),
                                                 "importo": b["importo"], "mese": pm, "anno": pa,
                                                 "data": data, "saldo": saldo})
                        return ass, dac, bon, pres, dup, tfr, prestiti
                    mese, anno, fonte = await _imputa_competenza(dip["id"], b)
                    if not mese or not anno:
                        dac.append({"nome": (b.get("causale") or "?")[:30], "origine": origine,
                                    "motivo": "bonifico: competenza non determinabile"})
                    elif anno not in ANNI_AMMESSI:
                        dac.append({"nome": (b.get("causale") or "?")[:30], "origine": origine,
                                    "motivo": f"anno {anno} non ammesso — bloccato (solo 2023-2026)"})
                    else:
                        cro = b.get("cro")
                        gia = await get_db().documenti_importati.find_one({"chiave": f"cro:{cro}"}) if cro else None
                        if gia:
                            dup.append({"file": origine, "motivo": f"bonifico già importato (CRO {cro})"})
                        elif b.get("is_tfr"):
                            # Anticipo TFR: fuori dal saldo stipendi
                            await get_db().paghe_mensili.update_one(
                                {"dipendente_id": dip["id"], "anno": anno, "mese": mese},
                                {"$set": {"dipendente_id": dip["id"], "anno": anno, "mese": mese,
                                          "tfr_anticipo_importo": b["importo"], "tfr_anticipo_data": b.get("data"),
                                          "tfr_anticipo_pdf": origine, "updated_at": now_iso()},
                                 "$setOnInsert": {"busta_riconciliata": False, "bonifico_riconciliato": False}},
                                upsert=True)
                            await _registra_doc(h, "tfr", f"cro:{cro}" if cro else f"tfr:{dip['id']}:{anno}:{mese}", origine)
                            tfr.append({"dipendente": f"{dip.get('cognome')} {dip.get('nome')}".strip(),
                                        "importo": b["importo"], "mese": mese, "anno": anno, "data": b.get("data")})
                        else:
                            from app.services.hr_pagamenti_deposito import (
                                ORIGINE_PDF, _deposita, _ricalcola_periodi, carica_contesto_hr,
                            )
                            ctx = await carica_contesto_hr()
                            if ctx is None:
                                raise HTTPException(503, "Archivio pagamenti HR non disponibile")
                            marca = await _deposita(
                                ctx, key=f"gc:{h}", testo=text, data=b.get("data"),
                                importo=b["importo"], hash_pdf=h, cro=cro,
                                causale=b.get("causale") or "", pdf_filename=origine,
                                pdf_data=base64.b64encode(pdfbytes).decode(), origine=ORIGINE_PDF,
                                mese_dichiarato=mese, anno_dichiarato=anno,
                                riferimento={}, dry_run=False,
                            )
                            await _ricalcola_periodi(ctx)
                            await _registra_doc(h, "bonifico", f"cro:{cro}" if cro else f"bon:{dip['id']}:{anno}:{mese}", origine)
                            bon.append({"dipendente": f"{dip.get('cognome')} {dip.get('nome')}".strip(),
                                        "importo": b["importo"], "mese": mese, "anno": anno,
                                        "causale": b.get("causale"), "data": b.get("data"),
                                        "riconciliato": False, "esito_deposito": marca["esito"],
                                        "discrepanza": None, "fonte": fonte})
                return ass, dac, bon, pres, dup, tfr, prestiti

            # ---- FOGLIO PRESENZE (ore/timbrature, non è una busta) ----
            if tipo == "presenze":
                cf = (_CF_RE.findall(text) or [None])[0]
                mese, anno = _lul_periodo(text)
                if anno and anno not in ANNI_AMMESSI:
                    dac.append({"nome": cf or "?", "origine": origine,
                                "motivo": f"presenze anno {anno} non ammesso — bloccato (solo 2023-2026)"})
                    return ass, dac, bon, pres, dup, tfr, prestiti
                dip = by_cf.get((cf or "").upper())
                await _registra_doc(h, "presenze", f"pres:{cf}:{anno}:{mese}", origine)
                pres.append({"dipendente": (f"{dip.get('cognome')} {dip.get('nome')}".strip() if dip else (cf or "?")),
                             "mese": mese, "anno": anno, "origine": origine})
                return ass, dac, bon, pres, dup, tfr, prestiti

            # ---- CEDOLINO / LIBRO UNICO multi-dipendente (netti) ----
            ced = _parse_lul(path)
            for cf, info in ced.items():
                dip = by_cf.get(cf)
                metodo = "codice fiscale"
                if not dip and cf not in by_cf:
                    dip = by_nome.get((info.get("nome") or "").upper())
                    metodo = "nome (CF non combacia)"
                netto = _to_float(info.get("netto"))
                mese, anno = info.get("mese"), info.get("anno")
                if not dip or not mese:
                    dac.append({"nome": info.get("nome"), "cf": cf, "netto": netto, "origine": origine,
                                "motivo": "dipendente non trovato" if not dip else "periodo non rilevato"})
                    continue
                if not netto or netto <= 0:
                    dac.append({"nome": info.get("nome"), "cf": cf, "netto": netto, "origine": origine,
                                "motivo": "netto non rilevato (non salvato)"})
                    continue
                if anno not in ANNI_AMMESSI:
                    dac.append({"nome": info.get("nome"), "cf": cf, "netto": netto, "origine": origine,
                                "motivo": f"anno {anno} non ammesso — bloccato (solo 2023-2026)"})
                    continue
                esistente = await get_db().paghe_mensili.find_one(
                    {"dipendente_id": dip["id"], "anno": anno, "mese": mese}, {"netto_atteso": 1})
                atteso = (esistente or {}).get("netto_atteso")
                discrep = atteso if (atteso is not None and abs(atteso - netto) > 1) else None
                acconto = info.get("acconto")
                acconto_valido = _acconto_cedolino_plausibile(acconto, netto)
                set_doc = {"dipendente_id": dip["id"], "anno": anno, "mese": mese,
                           "importo_busta": netto, "busta_da_lul": True,
                           "busta_riconciliata": True, "updated_at": now_iso()}
                if acconto_valido:
                    set_doc["acconto_cedolino"] = acconto
                    set_doc["saldo_residuo"] = round(netto - acconto, 2)
                await get_db().paghe_mensili.update_one(
                    {"dipendente_id": dip["id"], "anno": anno, "mese": mese},
                    {"$set": set_doc}, upsert=True)
                # Motore unico: busta arrivata → aggancia il pagamento o la mette in attesa
                await _ricalcola_stato_paga(get_db(), dip["id"], anno, mese)
                # Cedolino (fonte del portale): salvo il PDF REALE ritagliato dal Libro
                # Unico + il netto, così il dipendente scarica la sua busta vera.
                ced_set = {"dipendente_id": dip["id"], "anno": anno, "mese": mese,
                           "netto": netto,
                           "dipendente_nome": f"{dip.get('cognome','')} {dip.get('nome','')}".strip(),
                           "updated_at": now_iso()}
                if acconto_valido:
                    ced_set["acconto_cedolino"] = acconto
                    ced_set["saldo_residuo"] = round(netto - acconto, 2)
                # Dati chiave estratti dalla busta (salvati nel cedolino)
                for k in ("rateo_13ma", "rateo_14ma", "indennita_l207_24",
                          "indennita_l207_24_cng_ann", "tratt_integrativo_l21",
                          "tratt_integrativo_l21_rata", "tratt_integrativo_l21_cng",
                          "rimborso_730", "rimborso_730_residuo",
                          "ore_lavorate", "giorni_retribuiti", "giorni_lavorati", "voci"):
                    if info.get(k) is not None:
                        ced_set[k] = info[k]
                try:
                    if info.get("pagine"):
                        ced_set["pdf_data"] = base64.b64encode(_ritaglia_pdf(path, info["pagine"])).decode()
                        ced_set["filename"] = f"busta_{anno}_{str(mese).zfill(2)}.pdf"
                except Exception:
                    pass
                await get_db().cedolini.update_one(
                    {"dipendente_id": dip["id"], "anno": anno, "mese": mese},
                    {"$set": ced_set,
                     "$setOnInsert": {"id": generate_id(), "created_at": now_iso(), "stato": "importato"}},
                    upsert=True)
                ass.append({"dipendente_id": dip["id"],
                            "dipendente": f"{dip.get('cognome')} {dip.get('nome')}".strip(),
                            "netto": netto, "metodo": metodo, "mese": mese, "anno": anno,
                            "riconciliata": True, "discrepanza": discrep,
                            "acconto": acconto, "saldo_residuo": (round(netto - acconto, 2) if acconto else None)})
            if ass:
                await _registra_doc(h, "cedolino", f"file:{origine}", origine)
        finally:
            try:
                os.unlink(path)
            except Exception:
                pass
        return ass, dac, bon, pres, dup, tfr, prestiti

    associati, da_controllare, errori, bonifici, presenze, duplicati, tfr_list, prestiti_list = [], [], [], [], [], [], [], []
    errori = list(errori_iniziali or [])
    file_pdf = 0
    for (nome, data) in pdf_items:
        try:
            a, d, b, p, du, tf, pr = await _processa_pdf(data, nome)
            associati += a; da_controllare += d; bonifici += b; presenze += p; duplicati += du; tfr_list += tf; prestiti_list += pr; file_pdf += 1
        except Exception as e:
            errori.append(f"{nome}: {e}")

    if file_pdf == 0:
        raise HTTPException(status_code=400, detail="Nessun PDF elaborabile. " + ("; ".join(errori) if errori else ""))

    # Dedup: se lo stesso dipendente/mese è arrivato da più file, tieni una riga sola
    visti = {}
    for a in associati:
        visti[(a["dipendente_id"], a["anno"], a["mese"])] = a
    associati = list(visti.values())

    mesi_set = sorted({(a["anno"], a["mese"]) for a in associati})
    mesi = [{"anno": y, "mese": m, "n": sum(1 for a in associati if a["anno"] == y and a["mese"] == m)}
            for (y, m) in mesi_set]
    associati.sort(key=lambda x: (x["anno"], x["mese"], x["dipendente"]))
    bonifici.sort(key=lambda x: (x["anno"], x["mese"], x["dipendente"]))
    return {"associati": associati, "da_controllare": da_controllare,
            "totale_associati": len(associati), "file_pdf": file_pdf,
            "mesi": mesi, "errori": errori,
            "bonifici": bonifici, "presenze": presenze, "duplicati": duplicati, "tfr": tfr_list, "prestiti": prestiti_list}


async def _ricalcola_saldo_prestiti(dip_id):
    """Riporto continuo: azzera i campi prestito da tutti i mesi del dipendente, poi somma
    i movimenti in ordine cronologico riscrivendo erogato del mese e saldo cumulativo.
    Ritorna il saldo totale corrente."""
    await get_db().paghe_mensili.update_many(
        {"dipendente_id": dip_id},
        {"$unset": {"prestito_importo": "", "prestito_saldo": ""}})
    movs = await get_db().prestiti_dipendenti.find({"dipendente_id": dip_id}).to_list(2000)
    erog = {}
    for mv in movs:
        k = (mv["anno"], mv["mese"])
        erog[k] = erog.get(k, 0) + (mv.get("importo") or 0)
    saldo = 0
    for (a, m) in sorted(erog.keys()):
        saldo += erog[(a, m)]
        await get_db().paghe_mensili.update_one(
            {"dipendente_id": dip_id, "anno": a, "mese": m},
            {"$set": {"dipendente_id": dip_id, "anno": a, "mese": m,
                      "prestito_importo": erog[(a, m)], "prestito_saldo": saldo,
                      "updated_at": now_iso()},
             "$setOnInsert": {"busta_riconciliata": False, "bonifico_riconciliato": False}},
            upsert=True)
    return saldo


@router.get("/_unif_diag")
async def diagnostica_unificazione():
    """SOLA LETTURA. Fotografa cedolini vs paghe_mensili per pianificare l'unificazione:
    conteggi, sovrapposizioni per (dipendente_id, anno, mese), confronto netto vs importo_busta,
    record presenti solo in paghe_mensili, e dump completo di paghe_mensili per backup."""
    db = get_db()
    ced = await db.cedolini.find({}, {"_id": 0, "pdf_data": 0}).to_list(5000)
    pm = await db.paghe_mensili.find({}, {"_id": 0}).to_list(5000)
    ced_idx = {}
    for c in ced:
        ced_idx.setdefault((c.get("dipendente_id"), c.get("anno"), c.get("mese")), c)
    solo_in_pm, con_match, mismatch_netto = [], 0, []
    for p in pm:
        k = (p.get("dipendente_id"), p.get("anno"), p.get("mese"))
        c = ced_idx.get(k)
        if not c:
            solo_in_pm.append({"dipendente_id": p.get("dipendente_id"), "anno": p.get("anno"), "mese": p.get("mese")})
        else:
            con_match += 1
            nb = p.get("importo_busta") or p.get("netto_atteso")
            nc = c.get("netto")
            if nb is not None and nc is not None and abs(float(nb) - float(nc)) > 1:
                mismatch_netto.append({"dipendente_id": p.get("dipendente_id"), "anno": p.get("anno"),
                                       "mese": p.get("mese"), "paghe_mensili": nb, "cedolini": nc})
    # campi accessori presenti in paghe_mensili (riconciliazione)
    campi = set()
    for p in pm:
        campi.update(p.keys())
    pm_con_riconciliazione = [p for p in pm if any(p.get(k) for k in
        ("bonifico_importo", "acconti", "prestito_importo", "tfr_anticipo_importo",
         "busta_riconciliata", "bonifico_riconciliato"))]
    return {
        "cedolini_totali": len(ced),
        "paghe_mensili_totali": len(pm),
        "paghe_mensili_con_match_in_cedolini": con_match,
        "paghe_mensili_solo_loro": solo_in_pm,
        "mismatch_netto": mismatch_netto,
        "campi_presenti_in_paghe_mensili": sorted(campi),
        "paghe_mensili_con_dati_riconciliazione": len(pm_con_riconciliazione),
        "backup_paghe_mensili": pm,
    }


_RICON_FIELDS = ["bonifico_importo", "bonifico_data", "bonifico_ricevuto", "bonifico_causale",
                 "bonifico_cro", "bonifico_pdf", "bonifico_riconciliato", "busta_riconciliata",
                 "busta_da_lul", "acconti", "acconto_cedolino", "saldo_residuo", "netto_atteso",
                 "erogato_atteso", "fonte_excel", "tfr_anticipo_importo", "tfr_anticipo_data",
                 "tfr_anticipo_pdf", "prestito_importo", "prestito_saldo"]


@router.post("/_unif_esegui")
async def esegui_unificazione(dry_run: bool = True, limit: int = 25):
    """Unifica paghe_mensili dentro cedolini, A PICCOLI BATCH leggeri: processa solo i record
    non ancora migrati (flag _migrato sul documento paghe_mensili), così ogni chiamata è veloce.
    Chiamare ripetutamente finché completato=True. NON cancella paghe_mensili."""
    db = get_db()
    pendenti = await db.paghe_mensili.find({"_migrato": {"$ne": True}}).to_list(limit)
    if not pendenti:
        return {"dry_run": dry_run, "fatti_ora": 0, "restanti_da_fare": 0, "completato": True}
    arricchiti = creati = saltati = 0
    for p in pendenti:
        k = {"dipendente_id": p.get("dipendente_id"), "anno": p.get("anno"), "mese": p.get("mese")}
        ricon = {f: p[f] for f in _RICON_FIELDS if f in p and p[f] is not None}
        c = await db.cedolini.find_one(k, {"_id": 0, "id": 1})
        if dry_run:
            if c: arricchiti += 1
            elif (p.get("importo_busta") or p.get("netto_atteso") or 0) > 0: creati += 1
            else: saltati += 1
            continue
        if c:
            upd = dict(ricon); upd["unif_arricchito"] = True
            await db.cedolini.update_one({"id": c["id"]}, {"$set": upd})
            arricchiti += 1
        else:
            netto = p.get("importo_busta") or p.get("netto_atteso")
            if not netto or float(netto) <= 0:
                saltati += 1
            else:
                dip = await db.dipendenti.find_one({"id": p.get("dipendente_id")},
                                                   {"_id": 0, "nome": 1, "cognome": 1, "nome_completo": 1})
                nome = (dip or {}).get("nome_completo") or (f"{(dip or {}).get('cognome','')} {(dip or {}).get('nome','')}".strip() if dip else "")
                nuovo = {"id": str(uuid.uuid4()), "dipendente_id": p.get("dipendente_id"),
                         "dipendente_nome": nome, "anno": p.get("anno"), "mese": p.get("mese"),
                         "netto": float(netto), "stato": "importato",
                         "origine_unificazione": True, "unif_arricchito": True, "created_at": now_iso()}
                nuovo.update(ricon)
                await db.cedolini.insert_one(nuovo)
                creati += 1
        await db.paghe_mensili.update_one(
            {"dipendente_id": p.get("dipendente_id"), "anno": p.get("anno"), "mese": p.get("mese")},
            {"$set": {"_migrato": True}})
    restanti = await db.paghe_mensili.count_documents({"_migrato": {"$ne": True}})
    return {"dry_run": dry_run, "arricchiti_ora": arricchiti, "creati_ora": creati,
            "saltati_ora": saltati, "restanti_da_fare": restanti, "completato": restanti == 0}


@router.get("/prestiti")
async def lista_prestiti(dipendente_id: Optional[str] = None):
    """Mastrino prestiti: movimenti con saldo progressivo. Filtrabile per dipendente."""
    q = {"dipendente_id": dipendente_id} if dipendente_id else {}
    movs = await get_db().prestiti_dipendenti.find(q, {"_id": 0}).to_list(2000)
    movs.sort(key=lambda x: (x.get("anno", 0), x.get("mese", 0), x.get("data") or ""))
    # saldo progressivo per dipendente
    saldi = {}
    for mv in movs:
        d = mv["dipendente_id"]
        saldi[d] = saldi.get(d, 0) + (mv.get("importo") or 0)
        mv["saldo"] = saldi[d]
    return movs


@router.delete("/prestiti/{prestito_id}")
async def elimina_prestito(prestito_id: str):
    """Elimina un movimento di prestito e ricalcola il saldo progressivo del dipendente."""
    mv = await get_db().prestiti_dipendenti.find_one({"id": prestito_id})
    if not mv:
        raise HTTPException(status_code=404, detail="Prestito non trovato")
    await get_db().prestiti_dipendenti.delete_one({"id": prestito_id})
    # libera anche l'anti-dup così un eventuale re-import è possibile
    if mv.get("cro"):
        await get_db().documenti_importati.delete_many({"chiave": f"cro:{mv['cro']}"})
    saldo = await _ricalcola_saldo_prestiti(mv["dipendente_id"])
    return {"ok": True, "saldo_aggiornato": saldo}


def _espandi_in_pdf(nome, data):
    """Espande un allegato/file in lista di (origine, pdf_bytes): PDF diretto, oppure
    PDF contenuti in uno ZIP. Ritorna (items, errori)."""
    items, errori = [], []
    low = (nome or "").lower()
    if low.endswith(".pdf"):
        items.append((nome, data))
    elif low.endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                interni = [n for n in z.namelist() if n.lower().endswith(".pdf") and "__MACOSX" not in n]
                if not interni:
                    errori.append(f"{nome}: ZIP senza PDF")
                for zi in interni:
                    items.append((f"{nome} › {zi}", z.read(zi)))
        except zipfile.BadZipFile:
            errori.append(f"{nome}: ZIP non valido")
        except Exception as e:
            errori.append(f"{nome}: {e}")
    else:
        errori.append(f"{nome}: tipo non supportato (servono PDF o ZIP)")
    return items, errori


@router.post("/paghe/importa-lul")
async def importa_libro_unico(files: List[UploadFile] = File(...), forza: bool = False):
    """Importa uno o più PDF (anche dentro ZIP) caricati dall'utente: buste paga,
    fogli presenze, bonifici (acconti, saldi, TFR, prestiti). Vedi _importa_documenti."""
    pdf_items, errori = [], []
    for uf in files:
        nome = uf.filename or ""
        try:
            data = await uf.read()
        except Exception:
            errori.append(f"{nome}: lettura fallita")
            continue
        its, err = _espandi_in_pdf(nome, data)
        pdf_items += its
        errori += err
    if not pdf_items:
        raise HTTPException(status_code=400,
            detail="Nessun PDF valido trovato. " + ("; ".join(errori) if errori else ""))
    return await _importa_documenti(pdf_items, errori, forza=forza)


@router.post("/paghe/importa-libro-unico-canonico")
async def importa_libro_unico_canonico(files: List[UploadFile] = File(...)):
    """Importa Libri Unici col motore cedolini canonico e aggiorna Paghe.

    Questo e' il percorso della voce UI «Libro Unico»: conserva buste distinte
    dello stesso periodo (ordinaria, 13a e 14a), continuazioni multipagina e
    PDF ritagliati. Dopo il deposito sincronizza il registro, che resta in
    attesa finche' non esiste un pagamento reale collegato.
    """
    from app.hr.services import libro_unico_bundle, sincronizza_paghe_mensili

    pdf_items, errori = [], []
    riferimenti_drive = {}
    for uf in files:
        nome = uf.filename or ""
        try:
            data = await uf.read()
        except Exception:
            errori.append(f"{nome}: lettura fallita")
            continue
        items, err = _espandi_in_pdf(nome, data)
        pdf_items.extend(items)
        errori.extend(err)
        if nome.lower().endswith('.pdf') and getattr(uf, 'drive_file_id', None):
            riferimenti_drive[hashlib.sha256(data).hexdigest()] = uf.drive_file_id
    if not pdf_items:
        raise HTTPException(
            status_code=400,
            detail="Nessun PDF valido trovato. " + ("; ".join(errori) if errori else ""),
        )

    db = get_db()
    associati, duplicati, da_controllare = [], [], []
    saltati_presenze = []
    esiti_lettura = []
    sincronizzazione = None
    da_sincronizzare = False
    for nome, pdf_bytes in pdf_items:
        try:
            esito = await libro_unico_bundle.dividi_e_registra(
                db, pdf_bytes, nome, drive_file_id=riferimenti_drive.get(hashlib.sha256(pdf_bytes).hexdigest()),
            )
        except Exception as exc:
            errori.append(f"{nome}: {exc}")
            continue
        errori.extend(f"{nome}: {errore}" for errore in esito.get("errori") or [])
        esiti_lettura.append(esito.get("esito"))
        if esito.get("sincronizzazione_paghe") is not None:
            sincronizzazione = esito["sincronizzazione_paghe"]
        elif esito.get("inseriti") or esito.get("gia_presenti"):
            da_sincronizzare = True
        for record in esito.get("inseriti") or []:
            tipo = record.get("tipo_cedolino") or "ordinario"
            mese = 13 if tipo == "tredicesima" else 14 if tipo == "quattordicesima" else None
            anno, mese_competenza = (record.get("competenza") or "-").split("-", 1)
            associati.append({
                "dipendente": record.get("dipendente"),
                "netto": record.get("netto"),
                "tipo_cedolino": tipo,
                "anno": int(anno) if anno.isdigit() else None,
                "mese": mese or (int(mese_competenza) if mese_competenza.isdigit() else None),
                "mese_competenza": int(mese_competenza) if mese_competenza.isdigit() else None,
                "metodo": "codice fiscale",
            })
        duplicati.extend(esito.get("gia_presenti") or [])
        if esito.get("esito") == "presenze" and not esito.get("errori"):
            saltati_presenze.append({"file": nome, "motivo": "Foglio presenze, nessuna pagina retributiva"})
        else:
            da_controllare.extend(esito.get("senza_pagina_retributiva") or [])
        da_controllare.extend(esito.get("senza_anagrafica") or [])

    if da_sincronizzare:
        try:
            sincronizzazione = await sincronizza_paghe_mensili.sincronizza(db)
        except Exception as exc:
            errori.append(f"Buste archiviate, aggiornamento Paghe non completato: {exc}")
    mesi_set = sorted({(a["anno"], a["mese"]) for a in associati if a.get("anno") and a.get("mese")})
    mesi = [
        {"anno": anno, "mese": mese, "n": sum(1 for a in associati if a.get("anno") == anno and a.get("mese") == mese)}
        for anno, mese in mesi_set
    ]
    return {
        "associati": associati,
        "esito": "solo_presenze" if not errori and len(esiti_lettura) == len(pdf_items) and all(e == "presenze" for e in esiti_lettura) else "buste",
        "success": bool(associati or duplicati or saltati_presenze) and not errori,
        "partial": bool(associati or duplicati) and bool(errori),
        "da_controllare": da_controllare,
        "saltati_presenze": saltati_presenze,
        "totale_associati": len(associati),
        "file_pdf": len(pdf_items),
        "mesi": mesi,
        "errori": errori,
        "duplicati": duplicati,
        "sincronizzazione_paghe": sincronizzazione,
        "bonifici": [],
        "presenze": [],
        "tfr": [],
        "prestiti": [],
    }


@router.post("/paghe/importa-libro-unico-coda", status_code=202)
async def accoda_libro_unico(file: UploadFile = File(...)):
    from app.database import Database as ERPDatabase
    from app.routers.documenti import _importa_libro_unico_hr, MAX_UPLOAD_BYTES, MAX_ZIP_UPLOAD_BYTES
    from app.services.document_import_jobs import enqueue_import
    from app.utils.upload_validation import verifica_pdf_reale

    nome = os.path.basename(file.filename or "libro_unico.pdf")
    data = await file.read()
    if not data or len(data) > (MAX_ZIP_UPLOAD_BYTES if nome.lower().endswith('.zip') else MAX_UPLOAD_BYTES):
        raise HTTPException(413, "File vuoto o oltre il limite di caricamento")
    if nome.lower().endswith('.pdf'):
        verifica_pdf_reale(data, nome)
    elif not nome.lower().endswith('.zip'):
        raise HTTPException(400, "Seleziona un PDF o un archivio ZIP")
    return await enqueue_import(ERPDatabase.get_db(), content=data, filename=nome,
                                document_type="hr_libro_unico", process=_importa_libro_unico_hr)


@router.get("/paghe/importa-libro-unico-coda/{job_id}")
async def stato_import_libro_unico(job_id: str):
    from app.database import Database as ERPDatabase
    from app.services.document_import_jobs import get_import_job

    job = await get_import_job(ERPDatabase.get_db(), job_id)
    if not job or job.get("document_type") not in {"hr_libro_unico", "hr_importi_tabellari"}:
        raise HTTPException(404, "Import non trovato")
    return job


@router.post("/paghe/importa-email")
async def importa_da_email():
    """Usa la casella, i mittenti e gli originali del gestionale, poi il writer HR canonico."""
    from app.database import Database as ERPDatabase
    from app.services.email_monitor_service import (
        _build_gmail_credentials, _load_allowed_gmail_patterns, _download_email_batch,
    )
    from app.services.originale_documento import byte_dal_record

    erp = ERPDatabase.get_db()
    user, password, host = await _build_gmail_credentials(erp)
    if not user or not password:
        raise HTTPException(400, "Configura la casella di posta nelle Impostazioni del gestionale. Puoi comunque importare i PDF dal dispositivo o da Drive.")
    patterns = await _load_allowed_gmail_patterns(erp)
    if not patterns:
        raise HTTPException(400, "Nessun mittente autorizzato nella posta del gestionale. Aggiungi il mittente dei cedolini nelle Impostazioni.")
    try:
        download = await _download_email_batch(erp, user, password, host, 90, 200, patterns)
    except Exception as exc:
        logger.warning("Posta HR: download fallito (%s)", type(exc).__name__)
        raise HTTPException(502, "Lettura della posta non riuscita. Controlla il collegamento alla casella nelle Impostazioni del gestionale.") from exc
    if download.get("success") is False:
        raise HTTPException(502, "La casella del gestionale non ha completato la lettura. Controlla l'esito nella pagina Importa.")

    docs = await erp["documents_inbox"].find({"$or": [
        {"category": "busta_paga"}, {"tipo_documento": {"$in": ["busta_paga", "cedolino"]}},
    ]}, {"_id": 0}).to_list(200)
    files, errori = [], []
    for doc in docs:
        nome = doc.get("filename") or "cedolino.pdf"
        try:
            originale = await byte_dal_record(doc, [])
            if not originale:
                raise ValueError("Originale non disponibile")
            file = UploadFile(filename=nome, file=io.BytesIO(originale[0]))
            file.drive_file_id = doc.get("drive_file_id")
            files.append(file)
        except Exception as exc:
            errori.append(f"{nome}: {exc}")
    result = await importa_libro_unico_canonico(files=files) if files else {
        "file_pdf": 0, "totale_associati": 0, "associati": [], "duplicati": [], "errori": [], "mesi": [],
    }
    result.setdefault("errori", []).extend(errori)
    result["success"] = not result["errori"] and result.get("success", True)
    result["messaggio"] = "Posta del gestionale: ultimi 90 giorni, fino a 200 messaggi per lettura. Elaborati i cedolini presenti nell'archivio documenti."
    if not files:
        result["messaggio"] += " Nessun cedolino disponibile."
    return result


# ============ PRESENZE ============

@router.get("/presenze")
async def get_presenze(anno: Optional[int] = None, mese: Optional[int] = None, dipendente_id: Optional[str] = None):
    """
    Recupera presenze dalla collezione 'presenze' (dati storici dal Libro Unico).
    Le presenze sono raggruppate per mese con un array 'giorni'.
    """
    db = get_db()
    
    # Prima leggi da presenze_cloud (inserimenti manuali)
    query_cloud = {}
    if dipendente_id:
        query_cloud["dipendente_id"] = dipendente_id
    if anno and mese:
        query_cloud["data"] = {"$regex": f"^{anno}-{str(mese).zfill(2)}"}
    
    presenze_cloud = await db.presenze_cloud.find(query_cloud, {"_id": 0}).to_list(5000)
    
    # Poi leggi da presenze (dati storici dal LUL - struttura diversa)
    query_lul = {}
    if anno:
        query_lul["anno"] = anno
    if mese:
        query_lul["mese"] = mese
    
    presenze_lul = await db.presenze.find(query_lul, {"_id": 0}).to_list(500)
    
    # Converti presenze LUL in formato giornaliero
    result = list(presenze_cloud)
    cloud_keys = {(p.get("dipendente_id"), p.get("data")) for p in presenze_cloud}
    
    for p_lul in presenze_lul:
        cf = p_lul.get("codice_fiscale", "")
        anno_p = p_lul.get("anno", 2026)
        mese_p = p_lul.get("mese", 1)
        giorni = p_lul.get("giorni", [])
        
        # Trova l'ID dipendente dal codice fiscale
        dip = await db.dipendenti.find_one({"codice_fiscale": cf})
        dip_id = dip.get("id", cf) if dip else cf
        
        for g in giorni:
            giorno_num = g.get("giorno", 1)
            data_str = f"{anno_p}-{str(mese_p).zfill(2)}-{str(giorno_num).zfill(2)}"
            
            key = (dip_id, data_str)
            if key in cloud_keys:
                continue  # Già presente nei dati manuali
            
            # Determina lo stato dal giustificativo
            giust = g.get("giustificativo", "")
            ore = g.get("ore_ordinarie", 0)
            
            if giust:
                stato = giust  # AI, FE, MA, RL, etc.
            elif ore > 0:
                stato = "presente"
            else:
                stato = "assente"
            
            result.append({
                "id": f"{cf}_{data_str}",
                "dipendente_id": dip_id,
                "data": data_str,
                "entrata": None,
                "uscita": None,
                "stato": stato,
                "giustificativo": giust,
                "ore_lavorate": ore,
                "note": ""
            })
    
    return result

@router.post("/presenze")
async def create_presenza(presenza: PresenzaCloud):
    pres_dict = presenza.model_dump()
    pres_dict["id"] = generate_id()
    pres_dict["created_at"] = now_iso()
    
    # Calculate hours worked
    if pres_dict.get("entrata") and pres_dict.get("uscita"):
        try:
            ent = datetime.strptime(pres_dict["entrata"], "%H:%M")
            usc = datetime.strptime(pres_dict["uscita"], "%H:%M")
            pres_dict["ore_lavorate"] = round((usc - ent).seconds / 3600, 2)
        except ValueError as exc:
            # Senza ore_lavorate la presenza entra comunque, ma la paga di quel
            # giorno si calcola su un campo che non c'e': va detto.
            logger.warning(
                "[Presenze] orario non interpretabile (%s-%s): ore_lavorate non "
                "calcolate per il dipendente %s: %s",
                pres_dict.get("entrata"), pres_dict.get("uscita"),
                pres_dict.get("dipendente_id"), exc)
    
    await get_db().presenze_cloud.insert_one(pres_dict)
    return serialize_doc(pres_dict)

@router.put("/presenze/{presenza_id}")
async def update_presenza(presenza_id: str, presenza: PresenzaCloud):
    pres_dict = presenza.model_dump()
    
    if pres_dict.get("entrata") and pres_dict.get("uscita"):
        try:
            ent = datetime.strptime(pres_dict["entrata"], "%H:%M")
            usc = datetime.strptime(pres_dict["uscita"], "%H:%M")
            pres_dict["ore_lavorate"] = round((usc - ent).seconds / 3600, 2)
        except ValueError as exc:
            # Senza ore_lavorate la presenza entra comunque, ma la paga di quel
            # giorno si calcola su un campo che non c'e': va detto.
            logger.warning(
                "[Presenze] orario non interpretabile (%s-%s): ore_lavorate non "
                "calcolate per il dipendente %s: %s",
                pres_dict.get("entrata"), pres_dict.get("uscita"),
                pres_dict.get("dipendente_id"), exc)
    
    result = await get_db().presenze_cloud.update_one(
        {"id": presenza_id},
        {"$set": pres_dict}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Presenza non trovata")
    return {"message": "Presenza aggiornata"}

@router.delete("/presenze/{presenza_id}")
async def delete_presenza(presenza_id: str):
    result = await get_db().presenze_cloud.delete_one({"id": presenza_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Presenza non trovata")
    return {"message": "Presenza eliminata"}

@router.post("/presenze/batch")
async def create_presenze_batch(presenze: List[PresenzaCloud]):
    created = []
    for p in presenze:
        pres_dict = p.model_dump()
        pres_dict["id"] = generate_id()
        pres_dict["created_at"] = now_iso()
        
        existing = await get_db().presenze_cloud.find_one({
            "dipendente_id": pres_dict["dipendente_id"],
            "data": pres_dict["data"]
        })
        
        if existing:
            # L'id identifica la riga gia esistente e non deve mai finire nel
            # $set. In precedenza il nuovo UUID generato sopra sostituiva solo
            # doc.id, non la primary key Postgres, rendendo poi impossibili
            # aggiornamenti e cancellazioni affidabili dello stesso record.
            campi_aggiornabili = {
                k: v for k, v in pres_dict.items()
                if k not in {"id", "created_at"}
            }
            campi_aggiornabili["updated_at"] = now_iso()
            await get_db().presenze_cloud.update_one(
                {"id": existing["id"]},
                {"$set": campi_aggiornabili}
            )
        else:
            await get_db().presenze_cloud.insert_one(pres_dict)
        created.append(pres_dict)

    return {"message": f"Inserite/aggiornate {len(created)} presenze"}


@router.post("/presenze/importa-excel")
async def importa_presenze_excel(
    file: UploadFile = File(...),
    applica: bool = False,
    conferma_hash: Optional[str] = None,
    sempre_presenti_ids: str = Form("[]"),
    sostituzioni_nomi: str = Form("{}"),
    sostituisci_mese: bool = Form(False),
):
    """Importa il foglio mensile XLSX o CSV con anteprima obbligatoria.

    Le righe del file sono associate tramite codice fiscale. Le integrazioni
    "sempre presente" sono dipendenti scelti esplicitamente dall'interfaccia e
    vengono risolte tramite il loro ID HR. Una cella gia' compilata con un codice
    diverso resta un conflitto, salvo la scelta esplicita ``sostituisci_mese``:
    in quel caso l'anteprima conta separatamente le celle da aggiornare e la
    conferma le riallinea al file.
    """
    import openpyxl
    from app.hr.services.presenze_excel import (
        analizza_presenze_csv, analizza_presenze_workbook,
        indicizza_dipendenti_per_nome, nome_norm,
    )

    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "Il file supera 10 MB")
    impronta = hashlib.sha256(raw).hexdigest()
    if applica and conferma_hash != impronta:
        raise HTTPException(409, "Il file non coincide con l'anteprima confermata")
    try:
        ids_aggiuntivi = json.loads(sempre_presenti_ids or "[]")
        if not isinstance(ids_aggiuntivi, list) or not all(isinstance(x, str) for x in ids_aggiuntivi):
            raise ValueError
        ids_aggiuntivi = list(dict.fromkeys(x.strip() for x in ids_aggiuntivi if x.strip()))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "Elenco 'sempre presenti' non valido") from exc
    try:
        sostituzioni = json.loads(sostituzioni_nomi or "{}")
        if not isinstance(sostituzioni, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in sostituzioni.items()
        ):
            raise ValueError
        sostituzioni = {nome_norm(k): v.strip() for k, v in sostituzioni.items() if k.strip() and v.strip()}
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "Associazioni nominativi non valide") from exc
    try:
        if raw[:2] == b"PK":
            wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
            try:
                analisi = analizza_presenze_workbook(wb, file.filename or "")
            finally:
                wb.close()
        else:
            analisi = analizza_presenze_csv(raw, file.filename or "")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"Foglio presenze non valido: {exc}") from exc

    db = get_db()
    dipendenti = await db.dipendenti.find(
        {"merged_into": {"$exists": False}},
        {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1,
         "codice_fiscale": 1, "stato": 1, "attivo": 1},
    ).to_list(2000)
    per_cf: Dict[str, List[Dict[str, Any]]] = {}
    per_id = {d.get("id"): d for d in dipendenti if d.get("id")}
    per_nome = indicizza_dipendenti_per_nome(dipendenti)
    for dip in dipendenti:
        cf = re.sub(r"\s+", "", str(dip.get("codice_fiscale") or "")).upper()
        if cf:
            per_cf.setdefault(cf, []).append(dip)

    candidati: Dict[tuple, Dict[str, Any]] = {}
    nomi_risolti = {
        nome for nome, candidati_nome in per_nome.items()
        if len(candidati_nome) == 1
    }
    def _errore_identita_risolto(errore: Dict[str, Any]) -> bool:
        motivo = str(errore.get("motivo") or "").lower()
        riguarda_identita = (
            "codice fiscale mancante" in motivo
            or "nominativo giornaliero assente" in motivo
            or "nominativo senza codice fiscale" in motivo
        )
        nome = nome_norm(errore.get("nome"))
        return riguarda_identita and (nome in sostituzioni or nome in nomi_risolti)

    da_verificare = [e for e in analisi["errori"] if not _errore_identita_risolto(e)]
    associazioni_applicate = []
    nominativi_non_risolti = set()
    for voce in analisi["record"]:
        dip_sostitutivo = per_id.get(sostituzioni.get(nome_norm(voce.get("nome_file"))))
        if dip_sostitutivo:
            associati = [dip_sostitutivo]
        elif voce.get("codice_fiscale"):
            associati = per_cf.get(voce["codice_fiscale"], [])
        else:
            associati = per_nome.get(nome_norm(voce.get("nome_file")), [])
        if len(associati) != 1:
            prima_occorrenza = voce["nome_file"] not in nominativi_non_risolti
            nominativi_non_risolti.add(voce["nome_file"])
            if prima_occorrenza:
                da_verificare.append({
                    "nome": voce["nome_file"], "data": voce["data"],
                    "codice_fiscale": voce["codice_fiscale"],
                    "motivo": "dipendente non trovato" if not associati else "nominativo o codice fiscale duplicato in HR",
                })
            continue
        dip = associati[0]
        if not voce.get("codice_fiscale") and not any(a["nome_file"] == voce["nome_file"] for a in associazioni_applicate):
            associazioni_applicate.append({
                "nome_file": voce["nome_file"], "dipendente_id": dip["id"],
                "nome_hr": dip.get("nome_completo") or f"{dip.get('cognome', '')} {dip.get('nome', '')}".strip(),
            })
        item = dict(voce)
        item["dipendente_id"] = dip["id"]
        item["nome"] = dip.get("nome_completo") or f"{dip.get('cognome', '')} {dip.get('nome', '')}".strip()
        candidati[(dip["id"], voce["data"])] = item

    anno, mese = (int(x) for x in analisi["periodo"].split("-"))
    giorni_mese = calendar.monthrange(anno, mese)[1]
    integrazioni = []
    for dip_id in ids_aggiuntivi:
        dip = per_id.get(dip_id)
        if not dip:
            da_verificare.append({"dipendente_id": dip_id, "motivo": "dipendente aggiuntivo non trovato in HR"})
            continue
        nome = dip.get("nome_completo") or f"{dip.get('cognome', '')} {dip.get('nome', '')}".strip()
        integrazioni.append({"dipendente_id": dip_id, "nome": nome, "giorni": giorni_mese})
        for giorno in range(1, giorni_mese + 1):
            data_giorno = f"{anno:04d}-{mese:02d}-{giorno:02d}"
            key = (dip_id, data_giorno)
            if key in candidati:
                continue
            candidati[key] = {
                "dipendente_id": dip_id, "nome": nome, "nome_file": nome,
                "codice_fiscale": re.sub(r"\s+", "", str(dip.get("codice_fiscale") or "")).upper(),
                "data": data_giorno, "stato": "presente", "giustificativo": "P",
                "entrata": None, "note": "Sempre presente — correzione confermata nell'import Excel",
                "fonti": [{"foglio": "Correzioni import", "riga": None}],
            }

    esistenti = await db.presenze_cloud.find(
        {"data": {"$regex": f"^{anno:04d}-{mese:02d}"}}, {"_id": 0}
    ).to_list(10000)
    per_cella = {(p.get("dipendente_id"), p.get("data")): p for p in esistenti}
    righe = []
    da_inserire = []
    da_aggiornare = []
    per_dipendente: Dict[str, Dict[str, Any]] = {}
    for key, voce in sorted(candidati.items(), key=lambda kv: (kv[1]["nome"], kv[1]["data"])):
        esistente = per_cella.get(key)
        codice_esistente = None
        if esistente:
            codice_esistente = esistente.get("giustificativo") or (
                "P" if esistente.get("stato") == "presente" else "AS" if esistente.get("stato") == "assente" else None
            )
        if not esistente:
            stato_riga = "nuova"
            da_inserire.append(voce)
        elif codice_esistente == voce["giustificativo"]:
            stato_riga = "invariata"
        elif sostituisci_mese:
            stato_riga = "aggiornamento"
            da_aggiornare.append((esistente, voce))
        else:
            stato_riga = "conflitto"
        righe.append({
            "dipendente_id": voce["dipendente_id"], "nome": voce["nome"],
            "data": voce["data"], "codice": voce["giustificativo"],
            "stato": stato_riga, "codice_esistente": codice_esistente,
        })
        sintesi = per_dipendente.setdefault(voce["dipendente_id"], {
            "dipendente_id": voce["dipendente_id"], "nome": voce["nome"],
            "P": 0, "M": 0, "F": 0, "PE": 0, "R": 0, "AS": 0,
            "nuove": 0, "aggiornamenti": 0, "invariate": 0, "conflitti": 0,
        })
        sintesi[voce["giustificativo"]] = sintesi.get(voce["giustificativo"], 0) + 1
        sintesi[{"nuova": "nuove", "aggiornamento": "aggiornamenti",
                 "invariata": "invariate", "conflitto": "conflitti"}[stato_riga]] += 1

    inseriti = 0
    aggiornati = 0
    if applica:
        for voce in da_inserire:
            documento = {
                "id": generate_id(), "dipendente_id": voce["dipendente_id"],
                "data": voce["data"], "entrata": voce.get("entrata"), "uscita": None,
                "stato": voce["stato"], "giustificativo": voce["giustificativo"],
                "ore_lavorate": 0, "note": voce.get("note") or None,
                "origine": "import_excel_presenze", "import_hash": impronta,
                "created_at": now_iso(),
            }
            # Ultima barriera contro una scrittura concorrente tra anteprima e conferma.
            if await db.presenze_cloud.find_one({
                "dipendente_id": documento["dipendente_id"], "data": documento["data"]
            }):
                continue
            await db.presenze_cloud.insert_one(documento)
            inseriti += 1
        for esistente, voce in da_aggiornare:
            filtro = {"id": esistente["id"]} if esistente.get("id") else {
                "dipendente_id": voce["dipendente_id"], "data": voce["data"]}
            await db.presenze_cloud.update_one(filtro, {"$set": {
                "entrata": voce.get("entrata"), "uscita": None,
                "stato": voce["stato"], "giustificativo": voce["giustificativo"],
                "ore_lavorate": 0, "note": voce.get("note") or None,
                "origine": "import_excel_presenze", "import_hash": impronta,
                "updated_at": now_iso(),
            }})
            aggiornati += 1

    conteggi = {stato: sum(1 for r in righe if r["stato"] == stato)
                for stato in ("nuova", "aggiornamento", "invariata", "conflitto")}
    codici = {}
    for r in righe:
        codici[r["codice"]] = codici.get(r["codice"], 0) + 1
    return {
        "dry_run": not applica, "hash_sha256": impronta, "periodo": analisi["periodo"],
        "inseriti": inseriti, "aggiornati": aggiornati,
        "sostituisci_mese": sostituisci_mese, "conteggi": conteggi, "codici": codici,
        "dipendenti": sorted(per_dipendente.values(), key=lambda x: x["nome"]),
        "integrazioni": integrazioni, "associazioni_nomi": associazioni_applicate,
        "nominativi_da_associare": sorted(nominativi_non_risolti),
        "da_verificare": da_verificare,
        "conflitti": [r for r in righe if r["stato"] == "conflitto"],
        "regole": [
            "Le assenze certificate prevalgono sulle timbrature sovrapposte.",
            "Le festivita non vengono dedotte dal riepilogo mensile.",
            "Le celle esistenti con un codice diverso non vengono sovrascritte.",
        ],
    }


_MESI_PRES = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", "Luglio",
              "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
# Colori codici presenza (RGB 0-1) coerenti col frontend (niente blu/viola)
_COL_PRES = {
    "P": (0.24, 0.51, 0.41), "AS": (0.83, 0.37, 0.30), "F": (0.36, 0.48, 0.42),
    "PE": (0.49, 0.33, 0.15), "M": (0.96, 0.62, 0.04), "R": (0.54, 0.60, 0.36),
    "RS": (0.61, 0.64, 0.58), "CH": (0.42, 0.45, 0.50), "FNL": (0.65, 0.45, 0.29),
    "X": (0.22, 0.25, 0.20),
}


def _csv_presenze(anno, mese, giorni, righe):
    """CSV rettangolare e riconosciuto da Excel con tutte le colonne giorno."""
    giorni = calendar.monthrange(int(anno), int(mese))[1]
    sep = ";"
    intest = ["Dipendente"] + [str(i + 1) for i in range(giorni)]
    out = ["sep=;", sep.join(intest)]
    for r in righe:
        celle = list(r.get("celle") or [])[:giorni]
        celle.extend([""] * (giorni - len(celle)))
        values = [str(r.get("nome", ""))] + [str(c or "") for c in celle]
        out.append(sep.join('"' + v.replace('"', '""') + '"' if any(ch in v for ch in ';"\r\n') else v
                            for v in values))
    return "\ufeff" + "\r\n".join(out) + "\r\n"


def _pdf_presenze(anno, mese, giorni, righe):
    """Foglio presenze del mese in PDF, UNA SOLA PAGINA orizzontale (A4 landscape)."""
    import fitz
    W, H = 842, 595  # A4 orizzontale in punti
    pdf = fitz.open()
    page = pdf.new_page(width=W, height=H)
    mL, mR, mT, mB = 24, 24, 60, 60
    page.insert_text((mL, 34), f"Presenze {_MESI_PRES[mese - 1]} {anno}", fontsize=15, fontname="hebo")
    page.insert_text((mL, 50), "Ceraldi Group S.r.l.", fontsize=9, fontname="helv", color=(0.4, 0.4, 0.4))

    n = max(1, len(righe))
    name_w = 120
    grid_w = W - mL - mR - name_w
    col_w = grid_w / max(1, giorni)
    grid_h = H - mT - mB
    row_h = min(22, grid_h / (n + 1))
    fs = max(4.5, min(8, row_h - 3))
    x0, y0 = mL, mT

    # Intestazione giorni
    page.insert_text((x0 + 4, y0 - 4), "Dipendente", fontsize=7, fontname="hebo")
    for g in range(giorni):
        cx = x0 + name_w + g * col_w
        page.insert_text((cx + col_w / 2 - 3, y0 - 4), str(g + 1), fontsize=6, fontname="helv", color=(0.4, 0.4, 0.4))

    for ri, r in enumerate(righe):
        ry = y0 + ri * row_h
        # nome
        nome = str(r.get("nome", ""))[:22]
        page.draw_rect(fitz.Rect(x0, ry, x0 + name_w, ry + row_h), color=(0.9, 0.88, 0.83), width=0.3)
        page.insert_text((x0 + 3, ry + row_h - 4), nome, fontsize=fs, fontname="helv")
        celle = r.get("celle") or []
        for g in range(giorni):
            code = str(celle[g]) if g < len(celle) and celle[g] else ""
            cx = x0 + name_w + g * col_w
            rect = fitz.Rect(cx, ry, cx + col_w, ry + row_h)
            col = _COL_PRES.get(code)
            if col:
                page.draw_rect(rect, color=col, fill=col, width=0)
                page.insert_text((cx + col_w / 2 - fs * 0.55, ry + row_h - 4), code, fontsize=fs, fontname="hebo", color=(1, 1, 1))
            else:
                page.draw_rect(rect, color=(0.9, 0.88, 0.83), width=0.3)

    # Legenda in fondo
    ly = H - mB + 16
    page.insert_text((mL, ly), "Legenda:", fontsize=7, fontname="hebo")
    lx = mL + 42
    for code, lab in [("P", "Presente"), ("AS", "Assente"), ("F", "Ferie"), ("PE", "Permesso"),
                      ("M", "Malattia"), ("R", "ROL"), ("RS", "Riposo"), ("CH", "Chiuso"), ("FNL", "Fest.")]:
        col = _COL_PRES.get(code, (0.6, 0.6, 0.6))
        page.draw_rect(fitz.Rect(lx, ly - 7, lx + 9, ly + 1), color=col, fill=col, width=0)
        page.insert_text((lx + 12, ly), f"{code} {lab}", fontsize=6, fontname="helv")
        lx += 62
    return pdf.tobytes()


# ---- Opzione C: documento combinato per il commercialista ----
# (riepilogo totali per dipendente + dettaglio periodi con le date) — vedi
# mockup discusso col titolare: più leggero della griglia giorno-per-giorno,
# che resta per l'uso interno.
_MAPPA_RIEPILOGO = {"P": "lav", "F": "ferie", "PE": "perm", "M": "malat", "R": "rol", "RS": "riposi"}
_CODICI_EVENTO = {"F": "Ferie", "PE": "Permesso", "M": "Malattia", "R": "ROL",
                  "AS": "Assenza", "CH": "Chiusura", "FNL": "Festività"}


def _riepilogo_da_celle(celle):
    cont = {"lav": 0, "ferie": 0, "perm": 0, "malat": 0, "rol": 0, "riposi": 0, "altro": 0}
    for c in celle:
        chiave = _MAPPA_RIEPILOGO.get(c)
        if chiave:
            cont[chiave] += 1
        else:
            cont["altro"] += 1  # AS, CH, FNL, X, cella vuota…
    cont["tot"] = len(celle)
    return cont


def _periodi_da_celle(celle, note=None):
    """Raggruppa le celle in periodi consecutivi per i codici che meritano
    annotazione (il riposo settimanale e la presenza normale sono routine,
    non compaiono)."""
    note = note or []
    eventi, i, n = [], 0, len(celle)
    while i < n:
        code = celle[i] or ""
        if code not in _CODICI_EVENTO:
            i += 1
            continue
        j = i
        while j + 1 < n and (celle[j + 1] or "") == code:
            j += 1
        nota = next((note[k] for k in range(i, j + 1) if k < len(note) and note[k]), "")
        eventi.append({"tipo": code, "label": _CODICI_EVENTO[code],
                       "dal": i + 1, "al": j + 1, "giorni": j - i + 1, "nota": nota})
        i = j + 1
    return eventi


def _pdf_riepilogo_periodi(anno, mese, giorni, righe):
    """Documento 'per il commercialista' (Opzione C): riepilogo totali per
    dipendente + dettaglio dei periodi di assenza con le date, su una o più
    pagine A4 verticali (si estende da sola se i periodi sono tanti)."""
    import fitz
    W, H = 595, 842  # A4 verticale
    mL, mT, mB = 32, 70, 40
    pdf = fitz.open()
    page = pdf.new_page(width=W, height=H)
    y = [mT]

    def intestazione(continua=False):
        page.insert_text((mL, 34), f"Presenze {_MESI_PRES[mese - 1]} {anno}"
                         + (" (continua)" if continua else ""), fontsize=15, fontname="hebo")
        page.insert_text((mL, 50), "Ceraldi Group S.r.l.", fontsize=9, fontname="helv", color=(0.4, 0.4, 0.4))

    def nuova_pagina(continua=True):
        nonlocal page
        page = pdf.new_page(width=W, height=H)
        intestazione(continua)
        y[0] = mT

    def spazio(h):
        if y[0] + h > H - mB:
            nuova_pagina()

    intestazione()

    # ---- Sezione 1: riepilogo totali ----
    page.insert_text((mL, y[0]), "1 · RIEPILOGO DEL MESE", fontsize=9.5, fontname="hebo", color=(0.36, 0.48, 0.42))
    y[0] += 16
    cols = [("Dipendente", 150), ("Lav.", 44), ("Ferie", 44), ("Perm.", 44),
            ("Malat.", 46), ("ROL", 40), ("Riposi", 44), ("Altro", 42), ("Tot.", 40)]
    x = mL
    for lab, w in cols:
        page.insert_text((x + (0 if lab == "Dipendente" else w - 4 - len(lab) * 3.2), y[0]),
                         lab, fontsize=7.5, fontname="hebo", color=(0.42, 0.45, 0.4))
        x += w
    y[0] += 4
    page.draw_line((mL, y[0]), (mL + sum(w for _, w in cols), y[0]), color=(0.85, 0.82, 0.76), width=0.6)
    y[0] += 12
    totali = {"lav": 0, "ferie": 0, "perm": 0, "malat": 0, "rol": 0, "riposi": 0, "altro": 0, "tot": 0}
    riepiloghi = {}
    for r in righe:
        celle = r.get("celle") or []
        rp = _riepilogo_da_celle(celle)
        riepiloghi[r.get("nome", "")] = rp
        for k in totali:
            totali[k] += rp[k]
        spazio(14)
        x = mL
        vals = [r.get("nome", ""), rp["lav"], rp["ferie"], rp["perm"], rp["malat"], rp["rol"], rp["riposi"], rp["altro"], rp["tot"]]
        for (lab, w), v in zip(cols, vals):
            testo = str(v)
            if lab == "Dipendente":
                page.insert_text((x, y[0]), testo[:26], fontsize=8, fontname="helv")
            else:
                page.insert_text((x + w - 4 - len(testo) * 4, y[0]), testo, fontsize=8, fontname="helv")
            x += w
        y[0] += 14
    # riga totale
    spazio(18)
    page.draw_line((mL, y[0] - 4), (mL + sum(w for _, w in cols), y[0] - 4), color=(0.85, 0.82, 0.76), width=0.6)
    x = mL
    vals = ["Totale azienda", totali["lav"], totali["ferie"], totali["perm"], totali["malat"],
            totali["rol"], totali["riposi"], totali["altro"], totali["tot"]]
    for (lab, w), v in zip(cols, vals):
        testo = str(v)
        if lab == "Dipendente":
            page.insert_text((x, y[0]), testo, fontsize=8, fontname="hebo")
        else:
            page.insert_text((x + w - 4 - len(testo) * 4, y[0]), testo, fontsize=8, fontname="hebo")
        x += w
    y[0] += 26

    # ---- Sezione 2: dettaglio periodi ----
    spazio(20)
    page.insert_text((mL, y[0]), "2 · DETTAGLIO DEI PERIODI", fontsize=9.5, fontname="hebo", color=(0.65, 0.45, 0.29))
    y[0] += 6
    page.insert_text((mL, y[0] + 10), "Il riposo settimanale non compare: è regolare e non richiede annotazione.",
                     fontsize=7, fontname="helv", color=(0.5, 0.5, 0.5))
    y[0] += 22
    qualcuno = False
    for r in righe:
        eventi = _periodi_da_celle(r.get("celle") or [], r.get("note") or [])
        if not eventi:
            continue
        qualcuno = True
        # Riservo lo spazio per il nome + almeno il primo evento, così il nome
        # non resta da solo in fondo pagina separato dai suoi eventi.
        spazio(16 + 13)
        page.insert_text((mL, y[0]), str(r.get("nome", "")), fontsize=8.5, fontname="hebo")
        y[0] += 13
        for e in eventi:
            spazio(13)
            col = _COL_PRES.get(e["tipo"], (0.6, 0.6, 0.6))
            page.draw_rect(fitz.Rect(mL + 4, y[0] - 6, mL + 14, y[0] + 1), color=col, fill=col, width=0)
            # Il font base PyMuPDF (helv) non ha il glifo "→": uso un trattino ASCII.
            periodo = f"{e['dal']:02d}" if e["dal"] == e["al"] else f"{e['dal']:02d}-{e['al']:02d}"
            testo = f"{e['label']}: {periodo}/{mese:02d} ({e['giorni']} gg)"
            if e["nota"]:
                testo += f" — {e['nota'][:60]}"
            page.insert_text((mL + 18, y[0]), testo, fontsize=7.5, fontname="helv")
            y[0] += 13
        y[0] += 6
    if not qualcuno:
        page.insert_text((mL, y[0]), "Nessuna assenza da segnalare questo mese.", fontsize=8, fontname="helv", color=(0.5, 0.5, 0.5))
    return pdf.tobytes()


@router.post("/presenze/riepilogo-dati")
async def presenze_riepilogo_dati(data: dict = Body(...)):
    """Stessi dati dell'Opzione C (riepilogo totali + periodi) ma in JSON, per
    l'anteprima diretta in pagina — senza dover scaricare il PDF."""
    righe = data.get("righe") or []
    out_righe, out_periodi = [], []
    totali = {"lav": 0, "ferie": 0, "perm": 0, "malat": 0, "rol": 0, "riposi": 0, "altro": 0, "tot": 0}
    for r in righe:
        celle = r.get("celle") or []
        rp = _riepilogo_da_celle(celle)
        out_righe.append({"nome": r.get("nome", ""), **rp})
        for k in totali:
            totali[k] += rp[k]
        eventi = _periodi_da_celle(celle, r.get("note") or [])
        if eventi:
            out_periodi.append({"nome": r.get("nome", ""), "eventi": eventi})
    return {"righe": out_righe, "totali": totali, "periodi": out_periodi}


@router.post("/presenze/pdf-riepilogo")
async def presenze_pdf_riepilogo(data: dict = Body(...)):
    """Opzione C: documento 'per il commercialista' — riepilogo totali +
    dettaglio periodi, al posto della griglia giorno-per-giorno."""
    from fastapi.responses import StreamingResponse
    import io as _io
    anno = int(data.get("anno") or datetime.now().year)
    mese = int(data.get("mese") or datetime.now().month)
    giorni = int(data.get("giorni") or 31)
    righe = data.get("righe") or []
    try:
        pdf_bytes = _pdf_riepilogo_periodi(anno, mese, giorni, righe)
    except Exception as e:
        raise HTTPException(500, f"Errore generazione documento: {e}") from e
    fname = f"presenze_riepilogo_{anno}_{str(mese).zfill(2)}.pdf"
    return StreamingResponse(_io.BytesIO(pdf_bytes), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.post("/presenze/pdf")
async def presenze_pdf(data: dict = Body(...)):
    """Genera il PDF del foglio presenze del mese (una pagina), dai dati passati dal frontend."""
    from fastapi.responses import StreamingResponse
    import io as _io
    anno = int(data.get("anno") or datetime.now().year)
    mese = int(data.get("mese") or datetime.now().month)
    giorni = int(data.get("giorni") or 31)
    righe = data.get("righe") or []
    try:
        pdf_bytes = _pdf_presenze(anno, mese, giorni, righe)
    except Exception as e:
        raise HTTPException(500, f"Errore generazione PDF: {e}") from e
    fname = f"presenze_{anno}_{str(mese).zfill(2)}.pdf"
    return StreamingResponse(_io.BytesIO(pdf_bytes), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/presenze/email-commercialista")
async def get_email_commercialista():
    """Email del commercialista salvata in app: 'Invia' la usa in automatico,
    senza doverla ridigitare ogni volta."""
    doc = await get_db().impostazioni.find_one({"id": "email_commercialista"}, {"_id": 0}) or {}
    return {"email": doc.get("email") or os.getenv("COMMERCIALISTA_EMAIL") or None}


@router.post("/presenze/email-commercialista")
async def salva_email_commercialista(data: dict = Body(...)):
    """Body: {email: str|null}. null = torna a chiedere/usare l'env."""
    email = (data.get("email") or "").strip() or None
    await get_db().impostazioni.update_one(
        {"id": "email_commercialista"},
        {"$set": {"id": "email_commercialista", "email": email, "updated_at": now_iso()}},
        upsert=True)
    return {"ok": True, "email": email}


@router.get("/presenze/invii")
async def lista_invii_presenze(anno: Optional[int] = None, mese: Optional[int] = None):
    """Storico degli invii del foglio presenze: a chi e quando."""
    q = {}
    if anno:
        q["anno"] = int(anno)
    if mese:
        q["mese"] = int(mese)
    invii = await get_db().presenze_invii.find(q, {"_id": 0}).sort("data_invio", -1).to_list(500)
    return {"invii": invii, "totale": len(invii)}


@router.post("/presenze/invia-commercialista")
async def invia_presenze_commercialista(data: dict = Body(...)):
    """Invia via email al commercialista il foglio presenze del mese (allegati PDF
    completo giorno-per-giorno + CSV). Salva lo storico dell'invio (destinatario + data).
    Destinatario dal body o dalla env COMMERCIALISTA_EMAIL. Credenziali email da
    services/email_smtp.py (SMTP_*/PEC_*/GMAIL_APP_PASSWORD — punto unico)."""
    from app.hr.services.email_smtp import credenziali_smtp, invia_email
    anno = int(data.get("anno") or datetime.now().year)
    mese = int(data.get("mese") or datetime.now().month)
    giorni = int(data.get("giorni") or 31)
    righe = data.get("righe") or []
    csv = data.get("csv") or (_csv_presenze(anno, mese, giorni, righe) if righe else "")
    if not csv.strip() and not righe:
        raise HTTPException(400, "Nessun dato presenze da inviare")
    dest_salvato = (await get_db().impostazioni.find_one(
        {"id": "email_commercialista"}, {"_id": 0, "email": 1}) or {}).get("email")
    dest = (data.get("destinatario") or dest_salvato or os.getenv("COMMERCIALISTA_EMAIL") or "").strip()
    if not dest:
        raise HTTPException(400, "Manca l'email del commercialista (impostala o inseriscila).")
    if not credenziali_smtp():
        raise HTTPException(400, "Email non configurata su Render (manca SMTP_HOST/PEC_HOST oppure "
                                 "GMAIL_APP_PASSWORD + ADMIN_EMAIL).")

    periodo = f"{_MESI_PRES[mese - 1]} {anno}"
    base = f"presenze_{anno}_{str(mese).zfill(2)}"
    # Il PDF inviato è il foglio completo giorno-per-giorno: il consulente vede
    # subito tutte le colonne del mese senza dover aprire il CSV.
    pdf_bytes = None
    if righe:
        try:
            giorni = calendar.monthrange(anno, mese)[1]
            pdf_bytes = _pdf_presenze(anno, mese, giorni, righe)
        except Exception:
            pdf_bytes = None

    allegati = []
    if pdf_bytes:
        allegati.append((pdf_bytes, "application", "pdf", f"{base}.pdf"))
    if csv.strip():
        allegati.append((csv.encode("utf-8"), "text", "csv", f"{base}.csv"))
    # Le note per il consulente (trattenute dei verbali pagati) partono con le presenze.
    from app.hr.services import presenze_consulente as pc
    note_mese = await pc.note_consulente_mese(anno, mese)
    allegati += pc.allegato_note(anno, mese, note_mese)
    blocco_note = pc.testo_note(note_mese)

    try:
        import asyncio
        await asyncio.to_thread(
            invia_email, dest, f"Presenze {periodo} — Ceraldi Group S.r.l.",
            f"In allegato il riepilogo presenze di {periodo} (PDF + CSV).\n\n"
            + (blocco_note + "\n\n" if blocco_note else "")
            + "Messaggio generato automaticamente dal gestionale Ceraldi Group.",
            allegati)
    except Exception as e:
        # Log con traceback completo: l'errore esatto (auth Gmail, porta SMTP
        # bloccata dall'hosting, timeout...) va nei log di Render, il messaggio
        # corto va all'utente.
        logger.exception("Invio presenze al commercialista fallito")
        raise HTTPException(502, f"Invio email fallito: {type(e).__name__}: {e}") from e

    # Registro unico degli invii (lo legge anche il Pacchetto dell'Area Commercialista)
    from app.hr.services.presenze_consulente import registra_invio
    rec = await registra_invio(anno, mese, dest, n_dipendenti=len(righe),
                               con_pdf=bool(pdf_bytes), origine="hr")
    return {"ok": True, "destinatario": dest, "periodo": periodo, "invio": rec}


@router.post("/presenze/consolida-da-turni")
async def consolida_presenze_da_turni(data: dict = Body(default={})):
    """Crea le presenze REALI a partire dai turni assegnati, per il mese indicato e SOLO
    per i giorni fino a oggi (i futuri non si segnano presenti). Mappa: turno di lavoro→
    presente (P), Riposo→RS, Ferie→F, Malattia→M. NON sovrascrive le presenze già inserite
    a mano. Serve ad avere le presenze pronte per export/buste partendo dai turni."""
    import calendar
    db = get_db()
    anno = int(data.get("anno") or datetime.now().year)
    mese = int(data.get("mese") or datetime.now().month)
    turni = await db.turni_cloud.find({}, {"_id": 0, "id": 1, "nome": 1}).to_list(200)
    nome_turno = {t["id"]: (t.get("nome") or "") for t in turni}
    GIORNI = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]  # 0=lunedì
    ndays = calendar.monthrange(anno, mese)[1]
    oggi = datetime.now().date()
    settimane = set()
    for g in range(1, ndays + 1):
        dt = datetime(anno, mese, g).date()
        settimane.add((dt - timedelta(days=dt.weekday())).isoformat())
    ass = await db.assegnazioni_turni_cloud.find({"settimana": {"$in": list(settimane)}}, {"_id": 0}).to_list(8000)
    ass_by_day = {}
    for a in ass:
        ass_by_day.setdefault((a.get("settimana"), a.get("giorno")), []).append((a.get("dipendente_id"), a.get("turno_id")))
    creati, saltati = 0, 0
    for g in range(1, ndays + 1):
        dt = datetime(anno, mese, g).date()
        if dt > oggi:
            break
        lun = (dt - timedelta(days=dt.weekday())).isoformat()
        gname = GIORNI[dt.weekday()]
        dstr = dt.isoformat()
        for dip_id, turno_id in ass_by_day.get((lun, gname), []):
            n = nome_turno.get(turno_id, "")
            if not n or not dip_id:
                continue
            if await db.presenze_cloud.find_one({"dipendente_id": dip_id, "data": dstr}):
                saltati += 1
                continue
            if n == "Riposo":
                stato, giust = "giustificato", "RS"
            elif n == "Ferie":
                stato, giust = "giustificato", "F"
            elif n == "Malattia":
                stato, giust = "giustificato", "M"
            else:
                stato, giust = "presente", "P"
            await db.presenze_cloud.insert_one({
                "id": generate_id(), "dipendente_id": dip_id, "data": dstr,
                "stato": stato, "giustificativo": giust,
                "origine": "consolidamento_turni", "created_at": now_iso()})
            creati += 1
    return {"ok": True, "anno": anno, "mese": mese, "creati": creati, "saltati": saltati}

# ============ FERIE E PERMESSI ============

@router.get("/ferie")
async def get_ferie(dipendente_id: Optional[str] = None, stato: Optional[str] = None):
    query = {}
    if dipendente_id:
        query["dipendente_id"] = dipendente_id
    if stato:
        query["stato"] = stato
    ferie = await get_db().ferie_cloud.find(query, {"_id": 0}).to_list(1000)
    return ferie

@router.post("/ferie")
async def create_ferie(ferie: FerieCloud):
    ferie_dict = ferie.model_dump()
    ferie_dict["id"] = generate_id()
    ferie_dict["created_at"] = now_iso()
    await get_db().ferie_cloud.insert_one(ferie_dict)
    return serialize_doc(ferie_dict)

@router.post("/ferie-giorno")
async def set_ferie_giorno(data: dict):
    """Assegna/aggiorna/rimuove un'assenza di un singolo giorno dal calendario.
    tipo=None rimuove. Usato dalla vista calendario di Ferie & Permessi."""
    dip = data.get("dipendente_id")
    giorno = data.get("data")
    tipo = data.get("tipo")
    if not dip or not giorno:
        raise HTTPException(status_code=400, detail="dipendente_id e data obbligatori")
    existing = await get_db().ferie_cloud.find_one({
        "dipendente_id": dip, "data_inizio": giorno, "data_fine": giorno
    })
    if tipo:
        if existing:
            await get_db().ferie_cloud.update_one({"id": existing["id"]}, {"$set": {"tipo": tipo}})
        else:
            await get_db().ferie_cloud.insert_one({
                "id": generate_id(), "dipendente_id": dip, "tipo": tipo,
                "data_inizio": giorno, "data_fine": giorno, "giorni": 1,
                "stato": "approvata", "created_at": now_iso()
            })
    elif existing:
        await get_db().ferie_cloud.delete_one({"id": existing["id"]})
    return {"ok": True}

@router.put("/ferie/{ferie_id}/approva")
async def approva_ferie(ferie_id: str):
    result = await get_db().ferie_cloud.update_one(
        {"id": ferie_id},
        {"$set": {"stato": "approvata"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Richiesta non trovata")
    return {"message": "Richiesta approvata"}

@router.put("/ferie/{ferie_id}/rifiuta")
async def rifiuta_ferie(ferie_id: str):
    result = await get_db().ferie_cloud.update_one(
        {"id": ferie_id},
        {"$set": {"stato": "rifiutata"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Richiesta non trovata")
    return {"message": "Richiesta rifiutata"}

@router.delete("/ferie/{ferie_id}")
async def delete_ferie(ferie_id: str):
    result = await get_db().ferie_cloud.delete_one({"id": ferie_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Richiesta non trovata")
    return {"message": "Richiesta eliminata"}

# ============ TURNI ============

@router.get("/turni")
async def get_turni():
    turni = await get_db().turni_cloud.find({}, {"_id": 0}).to_list(100)
    return turni

@router.post("/turni")
async def create_turno(turno: TurnoCloud):
    turno_dict = turno.model_dump()
    turno_dict["id"] = generate_id()
    await get_db().turni_cloud.insert_one(turno_dict)
    return serialize_doc(turno_dict)

@router.put("/turni/{turno_id}")
async def update_turno(turno_id: str, turno: TurnoCloud):
    result = await get_db().turni_cloud.update_one(
        {"id": turno_id},
        {"$set": turno.model_dump()}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Turno non trovato")
    return {"message": "Turno aggiornato"}

@router.delete("/turni/{turno_id}")
async def delete_turno(turno_id: str):
    await get_db().turni_cloud.delete_one({"id": turno_id})
    await get_db().assegnazioni_turni_cloud.delete_many({"turno_id": turno_id})
    return {"message": "Turno eliminato"}

@router.get("/assegnazioni-turni")
async def get_assegnazioni(settimana: Optional[str] = None):
    query = {"settimana": settimana} if settimana else {}
    assegnazioni = await get_db().assegnazioni_turni_cloud.find(query, {"_id": 0}).to_list(2000)
    return assegnazioni

@router.post("/assegnazioni-turni/migra")
async def migra_settimana_assegnazioni(data: dict):
    """Una-tantum: assegna una settimana ai record che non ce l'hanno."""
    settimana = data.get("settimana")
    if not settimana:
        raise HTTPException(status_code=400, detail="settimana obbligatoria")
    res = await get_db().assegnazioni_turni_cloud.update_many(
        {"$or": [{"settimana": {"$exists": False}}, {"settimana": None}]},
        {"$set": {"settimana": settimana}}
    )
    return {"migrati": res.modified_count}

@router.post("/assegnazioni-turni")
async def create_or_update_assegnazione(data: dict):
    dipendente_id = data.get("dipendente_id")
    giorno = data.get("giorno")
    turno_id = data.get("turno_id")
    settimana = data.get("settimana")
    
    if not dipendente_id or not giorno:
        raise HTTPException(status_code=400, detail="dipendente_id e giorno sono obbligatori")
    
    motivo = data.get("motivo")  # es. "onomastico" → reso visibile nei turni
    match = {"dipendente_id": dipendente_id, "giorno": giorno}
    if settimana:
        match["settimana"] = settimana
    existing = await get_db().assegnazioni_turni_cloud.find_one(match)

    if turno_id:
        if existing:
            upd = {"$set": {"turno_id": turno_id}}
            if motivo:
                upd["$set"]["motivo"] = motivo
            else:
                upd["$unset"] = {"motivo": ""}
            await get_db().assegnazioni_turni_cloud.update_one({"id": existing["id"]}, upd)
        else:
            ass = {
                "id": generate_id(),
                "dipendente_id": dipendente_id,
                "giorno": giorno,
                "turno_id": turno_id,
                "settimana": settimana,
            }
            if motivo:
                ass["motivo"] = motivo
            await get_db().assegnazioni_turni_cloud.insert_one(ass)
    else:
        if existing:
            await get_db().assegnazioni_turni_cloud.delete_one({"id": existing["id"]})
    
    return {"message": "Assegnazione salvata"}

# ============ CONFIG TURNI PER DIPENDENTE ============
# Per ogni dipendente: turno abituale (turno_id) + giorno di riposo fisso
# settimanale (riposo_giorno, nome italiano). Usati da "Genera settimana".
def _nome_norm_cfg(s) -> str:
    return re.sub(r"[^a-z]", "", str(s or "").lower())


@router.get("/turni-config")
async def get_turni_config():
    """Vista in sola lettura delle configurazioni turni.

    Un riferimento orfano si risolve nella vista solo con un unico candidato
    in forza e senza configurazione propria. La relazione persistita cambia
    soltanto con il comando esplicito ``save_turni_config``.
    """
    db = get_db()
    configs = await db.turni_config.find({}, {"_id": 0}).to_list(1000)
    dips = await db.dipendenti.find({"merged_into": {"$exists": False}},
                                    {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1,
                                     "stato": 1, "attivo": 1, "in_carico": 1}).to_list(1000)
    ids_validi = {d["id"] for d in dips}
    con_config = {c["dipendente_id"] for c in configs}
    per_nome = {}
    for d in dips:
        if not stato_rapporto.e_in_forza(d):
            continue
        for k in {_nome_norm_cfg(f"{d.get('cognome','')}{d.get('nome','')}"),
                  _nome_norm_cfg(f"{d.get('nome','')}{d.get('cognome','')}"),
                  _nome_norm_cfg(d.get("nome_completo"))}:
            if k:
                per_nome.setdefault(k, {})[d["id"]] = d
    risolvibili = {}
    for c in configs:
        if c["dipendente_id"] in ids_validi:
            continue
        k = _nome_norm_cfg(c.get("nome_riferimento"))
        candidati = list(per_nome.get(k, {}).values()) if k else []
        d = candidati[0] if len(candidati) == 1 else None
        if d and d["id"] not in con_config:
            risolvibili.setdefault(d["id"], []).append(c)
    for dipendente_id, riferimenti in risolvibili.items():
        if len(riferimenti) > 1:
            for c in riferimenti:
                c["riferimento_conflitto"] = "Configurazioni orfane multiple: scegliere quella corretta"
            continue
        c = riferimenti[0]
        c["riferimento_risolto_da"] = c["dipendente_id"]
        c["dipendente_id"] = dipendente_id
    return configs


@router.post("/turni-config")
async def save_turni_config(data: dict = Body(...)):
    """Body: {voci: [{dipendente_id, turno_id, riposo_giorno}]}. Salva anche il nome
    del dipendente (nome_riferimento) per poter riparare la relazione se in futuro
    l'anagrafica venisse reimportata con id nuovi."""
    db = get_db()
    dips = await db.dipendenti.find({}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1,
                                         "nome_completo": 1}).to_list(1000)
    nomi = {d["id"]: (d.get("nome_completo") or f"{d.get('cognome', '')} {d.get('nome', '')}".strip())
            for d in dips}
    for v in (data.get("voci") or []):
        if not v.get("dipendente_id"):
            continue
        await db.turni_config.update_one(
            {"dipendente_id": v["dipendente_id"]},
            {"$set": {"dipendente_id": v["dipendente_id"],
                      "nome_riferimento": nomi.get(v["dipendente_id"]) or None,
                      "turno_id": v.get("turno_id") or None,
                      "riposo_giorno": v.get("riposo_giorno") or None,
                      "lunga_giorni": v.get("lunga_giorni") or [],
                      "rotazione": v.get("rotazione") or None,
                      # lunedì della settimana in cui la fase è stata impostata:
                      # "inizia mattina" = mattina in QUELLA settimana, poi si
                      # inverte ogni lunedì (ancora per-dipendente, niente base globale)
                      "rotazione_ancora": v.get("rotazione_ancora") or None,
                      "sala": bool(v.get("sala")),
                      # abilitato a coprire il bar nelle sostituzioni (es. Taiano, Russo)
                      "sostituto_bar": bool(v.get("sostituto_bar")),
                      "updated_at": now_iso()}}, upsert=True)
    return {"ok": True, "salvati": len(data.get("voci") or [])}

@router.get("/turni-disponibilita-bar")
async def get_turni_disponibilita_bar(settimana: Optional[str] = None):
    """Disponibilità a coprire il bar (dal portale) che toccano la settimana
    indicata: 'Genera settimana' le applica (sostituto al bar nella sua fascia,
    sala coperta con una Lunga)."""
    q = {}
    if settimana:
        try:
            lun = datetime.strptime(settimana, "%Y-%m-%d").date()
            q = {"dal": {"$lte": (lun + timedelta(days=6)).isoformat()},
                 "al": {"$gte": settimana}}
        except ValueError:
            pass
    return await get_db().turni_disponibilita_bar.find(
        q, {"_id": 0}).sort("dal", 1).to_list(200)


@router.get("/turni-preferenze")
async def get_turni_preferenze(settimana: Optional[str] = None):
    """Preferenze del giorno di riposo inviate dai dipendenti dal portale
    (collezione `turni_preferenze_riposo`): chi compone i turni le vede
    nella pagina Turni della settimana corrispondente."""
    q = {"settimana": settimana} if settimana else {}
    return await get_db().turni_preferenze_riposo.find(
        q, {"_id": 0}).sort("aggiornata_il", -1).to_list(500)


@router.get("/turni-chiusura-pomeridiana")
async def get_chiusura_pomeridiana():
    """Periodo in cui il bar resta chiuso di pomeriggio (impostato nel modale
    Configura turni): in quelle settimane tutti i baristi in rotazione fanno la
    mattina e riposano la domenica, come il resto della squadra."""
    doc = await get_db().impostazioni.find_one({"id": "chiusura_pomeridiana"}, {"_id": 0}) or {}
    return {"attiva": bool(doc.get("attiva")), "dal": doc.get("dal"), "al": doc.get("al")}


@router.post("/turni-chiusura-pomeridiana")
async def save_chiusura_pomeridiana(data: dict = Body(...)):
    """Body: {attiva: bool, dal: YYYY-MM-DD, al: YYYY-MM-DD}."""
    await get_db().impostazioni.update_one(
        {"id": "chiusura_pomeridiana"},
        {"$set": {"id": "chiusura_pomeridiana", "attiva": bool(data.get("attiva")),
                  "dal": data.get("dal") or None, "al": data.get("al") or None,
                  "updated_at": now_iso()}}, upsert=True)
    return {"ok": True}


# ============ ONOMASTICI (riposo per onomastico nei turni) ============
# Date standard italiane (mese, giorno) per nome proprio. Prefillate e
# MODIFICABILI in gestione. I nomi non presenti sono "stranieri" → esclusi.
ONOMASTICI_DEFAULT = {
    "angela": (1, 27), "angelo": (10, 2), "anna": (7, 26), "antonella": (6, 13),
    "antonietta": (6, 13), "antonio": (6, 13), "carmela": (7, 16), "carmine": (7, 16),
    "caterina": (11, 25), "ciro": (1, 31), "domenico": (8, 8), "elena": (8, 18),
    "emanuele": (3, 26), "fabio": (5, 11), "francesca": (3, 9), "francesco": (10, 4),
    "gaetano": (8, 7), "gennaro": (9, 19), "giorgio": (4, 23), "giovanna": (5, 30),
    "giovanni": (6, 24), "giulia": (5, 22), "giuliano": (1, 9), "giuseppa": (3, 19),
    "giuseppe": (3, 19), "ignazio": (7, 31), "liliana": (7, 27), "lucia": (12, 13),
    "luigi": (6, 21), "luigia": (6, 21), "marcella": (1, 31), "marco": (4, 25),
    "margherita": (2, 22), "maria": (9, 12), "mariano": (8, 19), "marina": (7, 17),
    "mario": (1, 19), "michele": (9, 29), "ottavio": (11, 20), "pasquale": (5, 17),
    "paolo": (6, 29), "pietro": (6, 29), "raffaele": (9, 29), "rosa": (8, 23),
    "salvatore": (8, 6), "simone": (10, 28), "stefano": (12, 26), "teresa": (10, 15),
    "valerio": (1, 29), "vincenzo": (1, 22), "vincenza": (1, 22),
}
NOMI_GIORNO_IT = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
# Dipendenti che NON seguono i turni → niente riposo onomastico (decisione titolare).
NON_TURNI = [("vincenzo", "ceraldi"), ("valerio", "ceraldi"),
             ("antonietta", "ceraldi"), ("marina", "liuzza")]


def _non_turni(d: dict) -> bool:
    f = f"{d.get('nome','')} {d.get('cognome','')} {d.get('nome_completo','')}".lower()
    return any(a in f and b in f for a, b in NON_TURNI)


def _nome_proprio(dip: dict) -> str:
    n = (dip.get("nome") or "").strip()
    if not n and dip.get("nome_completo"):
        n = dip["nome_completo"].split()[0]
    return n.split()[0].lower() if n else ""


@router.get("/onomastici")
async def get_onomastici():
    """Onomastico per ogni dipendente attivo: data (prefillata dal nome o salvata),
    attivo e flag 'straniero' (nome senza onomastico italiano)."""
    db = get_db()
    dips = await db.dipendenti.find(
        {"merged_into": {"$exists": False}}, {"_id": 0}).to_list(1000)
    salvati = {o["dipendente_id"]: o async for o in db.onomastici.find({}, {"_id": 0})}
    out = []
    for d in dips:
        if d.get("attivo") is False or (d.get("stato") or "attivo") in ("cessato", "dimesso", "archiviato"):
            continue
        nome = _nome_proprio(d)
        default = ONOMASTICI_DEFAULT.get(nome)
        straniero = default is None
        s = salvati.get(d.get("id"))
        if s:
            mese, giorno, attivo = s.get("mese"), s.get("giorno"), s.get("attivo", True)
        else:
            mese, giorno = (default if default else (None, None))
            attivo = (not straniero) and (not _non_turni(d))
        out.append({
            "dipendente_id": d.get("id"),
            "nome": d.get("nome_completo") or f"{d.get('cognome','')} {d.get('nome','')}".strip(),
            "mese": mese, "giorno": giorno, "attivo": bool(attivo), "straniero": straniero,
            "non_turni": _non_turni(d),
        })
    out.sort(key=lambda x: (x["nome"] or "").lower())
    return out


@router.post("/onomastici")
async def save_onomastici(data: dict = Body(...)):
    """Salva le date/attivo onomastico. Body: {voci: [{dipendente_id, mese, giorno, attivo}]}."""
    db = get_db()
    for v in (data.get("voci") or []):
        if not v.get("dipendente_id"):
            continue
        await db.onomastici.update_one(
            {"dipendente_id": v["dipendente_id"]},
            {"$set": {"dipendente_id": v["dipendente_id"],
                      "mese": v.get("mese"), "giorno": v.get("giorno"),
                      "attivo": bool(v.get("attivo", True)),
                      "updated_at": now_iso()}}, upsert=True)
    return {"ok": True, "salvati": len(data.get("voci") or [])}


@router.get("/onomastici/settimana")
async def onomastici_settimana(settimana: str):
    """Onomastici (idonei al riposo) che cadono nella settimana indicata (lunedì
    ISO). Esclude stranieri, esclusi (attivo=False) e la domenica (bar chiuso)."""
    try:
        lun = datetime.strptime(settimana, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="settimana deve essere YYYY-MM-DD (lunedì)") from exc
    voci = await get_onomastici()
    giorni_sett = [(lun + timedelta(days=i)) for i in range(7)]
    out = []
    for v in voci:
        if not v["attivo"] or v["straniero"] or not v["mese"] or not v["giorno"]:
            continue
        for i, gd in enumerate(giorni_sett):
            if gd.month == v["mese"] and gd.day == v["giorno"] and i < 6:  # esclude domenica
                out.append({
                    "dipendente_id": v["dipendente_id"], "nome": v["nome"],
                    "data": gd.strftime("%Y-%m-%d"), "giorno_nome": NOMI_GIORNO_IT[i],
                    "data_label": gd.strftime("%d/%m"),
                })
    return out

# ============ MOTORE DI INTERROGAZIONE CEDOLINI ============

@router.get("/cedolini/cerca-voce")
async def cerca_voce(codice: Optional[str] = None, testo: Optional[str] = None,
                     anno: Optional[int] = None, dipendente_id: Optional[str] = None):
    """Cerca una voce in TUTTI i cedolini salvati (campo voci). Per codice (es. F09081)
    o per testo della descrizione (es. '730', '13ma'). Filtrabile per anno/dipendente."""
    if not codice and not testo:
        raise HTTPException(status_code=400, detail="Indica 'codice' (es. F09081) o 'testo' (es. 730) da cercare")
    q: dict = {}
    if anno:
        q["anno"] = anno
    if dipendente_id:
        q["dipendente_id"] = dipendente_id
    cod = (codice or "").upper().strip()
    txt = (testo or "").lower().strip()
    out = []
    async for c in get_db().cedolini.find(q, {"_id": 0, "dipendente_id": 1, "dipendente_nome": 1, "anno": 1, "mese": 1, "voci": 1}):
        for v in (c.get("voci") or []):
            if (cod and v.get("codice") == cod) or (txt and txt in (v.get("descrizione") or "").lower()):
                out.append({"dipendente_id": c.get("dipendente_id"), "dipendente": c.get("dipendente_nome"),
                            "anno": c.get("anno"), "mese": c.get("mese"),
                            "codice": v.get("codice"), "descrizione": v.get("descrizione"),
                            "importo": (v.get("valori") or [None])[-1], "valori": v.get("valori")})
    out.sort(key=lambda x: (x.get("anno") or 0, x.get("mese") or 0))
    return {"risultati": out, "totale": len(out)}


@router.post("/paghe/correggi-acconti-cedolino")
async def correggi_acconti_cedolino():
    """Una tantum: toglie gli 'acconto dal cedolino' già salvati che sono
    implausibili (poche decine di euro — trattenute minime non correlate
    intercettate per errore dal parser, non veri anticipi). Ricalcola il saldo
    residuo di conseguenza. Non tocca gli acconti registrati a mano
    (acconti_dipendenti) né quelli plausibili."""
    db = get_db()
    corretti = []
    for coll_name in ("paghe_mensili", "cedolini"):
        async for doc in db[coll_name].find(
                {"acconto_cedolino": {"$gt": 0}},
                {"_id": 0, "id": 1, "dipendente_id": 1, "anno": 1, "mese": 1,
                 "importo_busta": 1, "netto": 1, "acconto_cedolino": 1}):
            netto = doc.get("importo_busta") if doc.get("importo_busta") is not None else doc.get("netto")
            if _acconto_cedolino_plausibile(doc.get("acconto_cedolino"), netto):
                continue
            filtro = {"id": doc["id"]} if doc.get("id") else \
                     {"dipendente_id": doc["dipendente_id"], "anno": doc["anno"], "mese": doc["mese"]}
            await db[coll_name].update_one(filtro, {"$unset": {"acconto_cedolino": "", "saldo_residuo": ""}})
            corretti.append({"collezione": coll_name, "dipendente_id": doc.get("dipendente_id"),
                             "anno": doc.get("anno"), "mese": doc.get("mese"),
                             "acconto_scartato": doc.get("acconto_cedolino")})
    return {"corretti": len(corretti), "dettaglio": corretti}


@router.post("/cedolini/riscansiona")
async def riscansiona_cedolini(anno: Optional[int] = None, dipendente_id: Optional[str] = None,
                               dopo_id: str = ""):
    """Rilegge le componenti documentali senza modificare netti o pagamenti."""
    from app.services.cedolini_hr_riverifica import riscansiona_componenti
    return await riscansiona_componenti(get_db(), anno=anno, dipendente_id=dipendente_id, dopo_id=dopo_id)


# ============ IMPORT PRIMA NOTA SALARI (Excel) ============

@router.post("/paghe/importa-prima-nota")
async def importa_prima_nota(file: UploadFile = File(...), applica: bool = False):
    """Excel/CSV/testo: anteprima e confronto; conferma in coda persistente."""
    from app.hr.services import importi_paghe_tabellari as tabellari
    from app.services.document_import_jobs import enqueue_import
    from app.database import Database as ERPDatabase
    raw = await file.read()
    nome = os.path.basename(file.filename or "importi.txt")
    try:
        preview = await tabellari.importa(get_db(), raw, nome, applica=False)
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(400, str(exc)) from exc
    if not applica:
        return preview
    return await enqueue_import(ERPDatabase.get_db(), content=raw, filename=nome,
                                document_type="hr_importi_tabellari", process=tabellari.elabora_file)


@router.post("/paghe/verifica-importo-excel")
async def verifica_importo_excel(data: dict = Body(...)):
    """Conferma la verifica del confronto senza modificare importi o pagamenti."""
    from app.hr.services.sincronizza_paghe_mensili import _SYNC_LOCK
    from app.hr.services.importi_paghe_tabellari import euro, intero
    from app.hr.db_supabase import SupabaseDatabase
    try:
        key = {"dipendente_id": str(data.get("dipendente_id") or ""),
               "anno": intero(data.get("anno")), "mese": intero(data.get("mese"))}
        expected = euro(data.get("busta_attuale"), allow_negative=True)
        if not key["dipendente_id"] or not 1 <= key["mese"] <= 14 or not data.get("confronto_id"):
            raise ValueError("Dipendente, periodo e confronto obbligatori")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    async with _SYNC_LOCK:
        db = get_db()
        if isinstance(db, SupabaseDatabase):
            await db.refresh_collections("paghe_mensili")
        paga = await db.paghe_mensili.find_one(key, {"_id": 0})
        if not paga:
            raise HTTPException(404, "Periodo non trovato")
        if paga.get("importo_busta") is None:
            raise HTTPException(409, "Controlla il cedolino e inserisci il netto prima di confermare la verifica")
        if expected != euro(paga.get("importo_busta"), allow_negative=True):
            raise HTTPException(409, "Importo cambiato: aggiorna la pagina e ricontrolla")
        entries = list(paga.get("importi_excel") or [])
        entry = next((e for e in entries if e.get("id") == data.get("confronto_id")), None)
        if not entry:
            raise HTTPException(404, "Confronto non trovato")
        entry.update(verificato=True, verificato_il=now_iso(), verificato_importo=paga.get("importo_busta"),
                     verificato_netto=paga.get("netto_stampato"))
        await db.paghe_mensili.update_one(key, {"$set": {"importi_excel": entries}})
    return {"ok": True}


@router.post("/paghe/importa-storico-pagamenti")
async def importa_storico_pagamenti(file: UploadFile = File(...)):
    """Importa l'archivio storico dei pagamenti (un foglio Excel per dipendente: data del
    pagamento in colonna A, nome in colonna B, importo di busta in colonna C, importo
    effettivamente pagato in colonna D — le intestazioni di questi fogli sono spesso
    disallineate rispetto ai dati, quindi il formato si riconosce dal TIPO di dato in
    colonna A, non dal testo dell'header).
    Le righe finiscono in 'pagamenti_storico', un registro di SOLA CONSULTAZIONE per il
    periodo precedente all'app: non tocca 'paghe_mensili' né lo stato di pagamento dei
    cedolini correnti, perché qui si conosce solo la data del bonifico e non il mese di
    competenza della busta (attribuirlo al mese del bonifico rischierebbe di sfalsare il
    saldo di un mese). Import idempotente: le righe già presenti (stesso dipendente, data,
    busta, pagato) non vengono duplicate."""
    import io
    import openpyxl
    raw = await file.read()
    if raw[:2] != b"PK":
        raise HTTPException(400, "Il file deve essere un .xlsx")
    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
    except Exception as e:
        raise HTTPException(400, f"Excel non valido: {e}") from e

    def norm(s):
        return re.sub(r"\s+", " ", str(s or "").strip()).lower()

    def fnum(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0

    righe = []
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        start = 0 if (rows[0] and isinstance(rows[0][0], (datetime, date))) else 1
        for r in rows[start:]:
            if not r or not isinstance(r[0], (datetime, date)):
                continue
            nome = r[1] if len(r) > 1 else None
            busta = fnum(r[2]) if len(r) > 2 else 0.0
            pagato = fnum(r[3]) if len(r) > 3 else 0.0
            if not nome or (busta <= 0 and pagato <= 0):
                continue
            d = r[0]
            data_iso = d.date().isoformat() if isinstance(d, datetime) else d.isoformat()
            righe.append({"nome": str(nome).strip(), "data": data_iso,
                          "busta": round(busta, 2), "pagato": round(pagato, 2)})

    if not righe:
        raise HTTPException(400, "Nessuna riga riconosciuta: attesa una data in colonna A per ogni pagamento")

    db = get_db()
    dips = await db.dipendenti.find({"merged_into": {"$exists": False}},
                                    {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1}).to_list(1000)
    by_nome = {}
    for dd in dips:
        n, c = norm(dd.get("nome")), norm(dd.get("cognome"))
        for v in {norm(dd.get("nome_completo")), f"{c} {n}".strip(), f"{n} {c}".strip()}:
            if v:
                by_nome[v] = dd

    try:
        await db.pagamenti_storico.create_index(
            [("dipendente_id", 1), ("data", 1), ("busta", 1), ("pagato", 1)],
            unique=True, name="uniq_storico_riga")
    except Exception:
        pass

    importati, gia_presenti, non_trovati = 0, 0, {}
    for r in righe:
        dip = by_nome.get(norm(r["nome"]))
        if not dip:
            non_trovati[r["nome"]] = non_trovati.get(r["nome"], 0) + 1
            continue
        doc = {"id": generate_id(), "dipendente_id": dip["id"], "data": r["data"],
               "busta": r["busta"], "pagato": r["pagato"], "fonte": "excel_storico", "created_at": now_iso()}
        res = await db.pagamenti_storico.update_one(
            {"dipendente_id": dip["id"], "data": r["data"], "busta": r["busta"], "pagato": r["pagato"]},
            {"$setOnInsert": doc}, upsert=True)
        if res.upserted_id:
            importati += 1
        else:
            gia_presenti += 1

    return {"righe_lette": len(righe), "importati": importati, "gia_presenti": gia_presenti,
            "dipendenti_non_in_anagrafica": [{"nome": k, "righe": v} for k, v in sorted(non_trovati.items())]}


@router.get("/paghe/storico-pagamenti")
async def storico_pagamenti(dipendente_id: str):
    """Registro storico dei pagamenti ante-app (da Excel), in sola lettura, per data."""
    db = get_db()
    righe = await db.pagamenti_storico.find(
        {"dipendente_id": dipendente_id}, {"_id": 0}).sort("data", 1).to_list(2000)
    return {"righe": righe,
            "totale_busta": round(sum(r.get("busta", 0) for r in righe), 2),
            "totale_pagato": round(sum(r.get("pagato", 0) for r in righe), 2)}


_MESI_IT = {"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
            "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
            "tredicesima": 13, "13ma": 13, "13a": 13,
            "quattordicesima": 14, "14ma": 14, "14a": 14}


_ANAGRAFICA_HEADER = {
    "nome": {"nome"},
    "cognome": {"cognome"},
    "nome_file": {"dipendente", "nome completo", "nominativo"},
    "codice_fiscale": {"cf", "codice fiscale", "codice fiscale lavoratore"},
    "data_nascita": {"data nascita", "data di nascita", "nascita"},
    "codice_fiscale_azienda": {"cf azienda", "codice fiscale azienda"},
    "sesso": {"sesso"},
    "regione_residenza": {"regione di residenza", "regione residenza"},
    "provincia_residenza": {"provincia di residenza", "provincia residenza"},
    "comune_residenza": {"comune di residenza", "comune residenza"},
    "regione_domicilio": {"regione di domicilio compilare se diversa da regione di residenza", "regione di domicilio", "regione domicilio"},
    "provincia_domicilio": {"provincia di domicilio compilare se diversa da regione di residenza", "provincia di domicilio", "provincia domicilio"},
    "comune_domicilio": {"comune di domicilio compilare se diversa da regione di residenza", "comune di domicilio", "comune domicilio"},
    "cittadinanza": {"cittadinanza"},
    "titolo_studio": {"titolo studio", "titolo di studio"},
    "mansione": {"mansione", "ruolo"},
    "matricola": {"matricola", "codice dipendente"},
    "gruppo": {"gruppo", "reparto"},
    "luogo_lavoro": {"luogo di lavoro", "luogo lavoro", "sede"},
    "note": {"note"},
    "attivo": {"attivo", "in forza"},
    "telefono": {"telefono", "cellulare", "cell"},
    "email": {"email", "e mail", "mail"},
    "indirizzo": {"indirizzo", "residenza"},
    "iban": {"iban", "iban per il bonifico"},
    "data_assunzione": {"data assunzione", "data di assunzione", "assunzione"},
}
_ANAGRAFICA_CAMPI_SCRIVIBILI = (
    "nome", "cognome", "codice_fiscale", "data_nascita", "mansione",
    "telefono", "email", "indirizzo", "iban", "data_assunzione",
    "codice_fiscale_azienda", "sesso", "regione_residenza", "provincia_residenza",
    "comune_residenza", "regione_domicilio", "provincia_domicilio", "comune_domicilio",
    "cittadinanza", "titolo_studio",
    "matricola", "gruppo", "luogo_lavoro", "note", "attivo",
)


def _testo_header(value: Any) -> str:
    testo = unicodedata.normalize("NFKD", str(value or ""))
    testo = "".join(c for c in testo if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", testo).split())


def _mappa_header_anagrafica(row: tuple) -> Dict[str, int]:
    mappa: Dict[str, int] = {}
    normalizzati = [_testo_header(c) for c in row]
    for campo, aliases in _ANAGRAFICA_HEADER.items():
        aliases_norm = {_testo_header(a) for a in aliases}
        for i, valore in enumerate(normalizzati):
            if valore in aliases_norm:
                mappa[campo] = i
                break
    return mappa


def _trova_foglio_anagrafica(wb):
    """Sceglie il foglio esplicito o un riepilogo consolidato identificabile.

    Il riepilogo e' ammesso soltanto se ogni riga porta il codice fiscale e
    almeno un campo anagrafico aggiornabile (IBAN o data di assunzione). Gli
    importi di paga, ferie e ratei restano colonne ignorate: non identificano
    la persona e hanno fonti canoniche diverse nell'HR.
    """
    preferiti = [ws for ws in wb.worksheets if _testo_header(ws.title) == "anagrafiche dipendenti"]
    candidati = preferiti or list(wb.worksheets)
    for ws in candidati:
        # Alcuni esportatori dichiarano erroneamente una sola cella nel file.
        if hasattr(ws, "reset_dimensions"):
            ws.reset_dimensions()
        for numero, row in enumerate(ws.iter_rows(min_row=1, max_row=12, values_only=True), start=1):
            mappa = _mappa_header_anagrafica(row)
            if "codice_fiscale" not in mappa:
                continue
            identificazione_visibile = "nome_file" in mappa or ("nome" in mappa and "cognome" in mappa)
            campo_aggiornabile = "iban" in mappa or "data_assunzione" in mappa
            if preferiti or (identificazione_visibile and campo_aggiornabile):
                return ws, numero, mappa, row
    raise HTTPException(
        400,
        "Foglio anagrafico non trovato: usa 'Anagrafiche Dipendenti' oppure un riepilogo con Dipendente, Codice fiscale e IBAN/Data assunzione.",
    )


def _valore_riga(row: tuple, indice: Optional[int]):
    if indice is None or indice >= len(row):
        return None
    valore = row[indice]
    if valore is None:
        return None
    if isinstance(valore, str):
        valore = valore.strip()
        return valore or None
    return valore


def _data_iso_anagrafica(value: Any) -> Optional[str]:
    if value in (None, "", "-") or str(value).strip() in {"—", "-"}:
        return None
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    testo = str(value).strip()[:10]
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(testo, formato).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise ValueError("data non valida")


def _iban_valido(value: str) -> bool:
    iban = re.sub(r"\s+", "", value or "").upper()
    if not re.fullmatch(r"IT\d{2}[A-Z]\d{10}[A-Z0-9]{12}", iban):
        return False
    numerico = "".join(str(ord(c) - 55) if c.isalpha() else c for c in iban[4:] + iban[:4])
    resto = 0
    for c in numerico:
        resto = (resto * 10 + int(c)) % 97
    return resto == 1


def _normalizza_riga_anagrafica(row: tuple, mappa: Dict[str, int]) -> tuple[Dict[str, Any], List[str]]:
    errori: List[str] = []
    out: Dict[str, Any] = {}
    for campo in _ANAGRAFICA_CAMPI_SCRIVIBILI:
        valore = _valore_riga(row, mappa.get(campo))
        if valore in (None, ""):
            continue
        if campo == "codice_fiscale":
            valore = re.sub(r"\s+", "", str(valore)).upper()
            if not re.fullmatch(r"[A-Z0-9]{16}", valore):
                errori.append("codice fiscale non valido")
        elif campo == "iban":
            valore = re.sub(r"\s+", "", str(valore)).upper()
            if not _iban_valido(valore):
                errori.append("IBAN non valido")
        elif campo in ("data_nascita", "data_assunzione"):
            try:
                valore = _data_iso_anagrafica(valore)
            except ValueError:
                errori.append(f"{campo.replace('_', ' ')} non valida")
                continue
        elif campo == "sesso":
            valore = str(valore).strip().upper()
            if valore not in {"M", "F"}:
                errori.append("sesso non valido (atteso M o F)")
        elif campo == "codice_fiscale_azienda":
            valore = re.sub(r"\s+", "", str(valore)).upper()
            if not re.fullmatch(r"(?:\d{11}|[A-Z0-9]{16})", valore):
                errori.append("codice fiscale azienda non valido")
        elif campo == "attivo":
            normalizzato = _testo_header(str(valore))
            if normalizzato in {"true", "1", "si", "vero", "attivo"}:
                valore = True
            elif normalizzato in {"false", "0", "no", "falso", "inattivo", "cessato"}:
                valore = False
            else:
                errori.append("Attivo non valido: usare vero/falso, sì/no o 1/0")
                continue
        else:
            valore = str(valore).strip()
        if valore not in (None, ""):
            out[campo] = valore
    return out, errori


def _valore_anagrafico_vuoto(value: Any) -> bool:
    return value is None or value == "" or value == []


def _valori_anagrafici_equivalenti(campo: str, corrente: Any, nuovo: Any) -> bool:
    """Confronta il significato, evitando conflitti dovuti al solo formato."""
    if _valore_anagrafico_vuoto(corrente) or _valore_anagrafico_vuoto(nuovo):
        return corrente == nuovo
    if campo == "iban":
        return re.sub(r"\s+", "", str(corrente)).upper() == re.sub(r"\s+", "", str(nuovo)).upper()
    if campo in ("data_nascita", "data_assunzione"):
        try:
            return _data_iso_anagrafica(corrente) == _data_iso_anagrafica(nuovo)
        except ValueError:
            return False
    if isinstance(corrente, str) or isinstance(nuovo, str):
        return _testo_header(corrente) == _testo_header(nuovo)
    return corrente == nuovo


@router.post("/dipendenti/importa-anagrafica")
async def importa_anagrafica(
    file: UploadFile = File(...), applica: bool = False, conferma_hash: Optional[str] = None,
    crea_mancanti: bool = False,
):
    """Anteprima per difetto; applica soltanto aggiornamenti confermati allo stesso file.

    Identita' = codice fiscale esatto. Nomi, importi o posizione nel foglio non
    creano mai un'associazione. Le persone nuove richiedono l'opzione esplicita
    crea_mancanti, nome/cognome, CF e stato Attivo leggibile nell'originale.
    """
    import openpyxl
    raw = await file.read()
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "Il file supera 10 MB")
    if raw[:2] != b"PK":
        raise HTTPException(400, "Il file deve essere un .xlsx")
    impronta = hashlib.sha256(raw).hexdigest()
    if applica and conferma_hash != impronta:
        raise HTTPException(409, "Il file non coincide con l'anteprima confermata")
    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
    except Exception as exc:
        raise HTTPException(400, f"Excel non valido: {exc}") from exc
    ws, header_row, mappa, header_originale = _trova_foglio_anagrafica(wb)

    colonne_riconosciute = {i for i in mappa.values()}
    colonne_ignorate = [str(v).strip() for i, v in enumerate(header_originale)
                        if v not in (None, "") and i not in colonne_riconosciute]
    db = get_db()
    esistenti = await db.dipendenti.find(
        {"merged_into": {"$exists": False}}, {"_id": 0, "pdf_data": 0}).to_list(2000)
    per_cf: Dict[str, List[Dict[str, Any]]] = {}
    for dip in esistenti:
        cf = re.sub(r"\s+", "", str(dip.get("codice_fiscale") or "")).upper()
        if cf:
            per_cf.setdefault(cf, []).append(dip)

    righe = []
    righe_sorgente = []
    occorrenze_cf: Dict[str, List[int]] = {}
    for numero, row in enumerate(ws.iter_rows(min_row=header_row + 1, values_only=True), start=header_row + 1):
        dati, errori = _normalizza_riga_anagrafica(row, mappa)
        cf = dati.get("codice_fiscale")
        nominativo = _valore_riga(row, mappa.get("nome_file"))
        if not dati and not nominativo:
            continue
        righe_sorgente.append((numero, dati, errori, nominativo))
        if cf:
            occorrenze_cf.setdefault(cf, []).append(numero)

    wb.close()
    for numero, dati, errori, nominativo in righe_sorgente:
        cf = dati.get("codice_fiscale")
        if not cf:
            righe.append({"riga": numero, "stato": "da_verificare", "motivi": errori or ["codice fiscale mancante"]})
            continue
        if len(occorrenze_cf[cf]) > 1:
            righe.append({"riga": numero, "codice_fiscale": cf, "stato": "conflitto",
                          "motivi": ["codice fiscale duplicato nel file alle righe " +
                                      ", ".join(str(riga) for riga in occorrenze_cf[cf])]})
            continue
        if errori:
            righe.append({"riga": numero, "codice_fiscale": cf, "stato": "da_verificare", "motivi": errori})
            continue
        candidati = per_cf.get(cf, [])
        if not candidati and crea_mancanti:
            mancanti = [campo for campo in ("nome", "cognome", "attivo") if campo not in dati]
            if mancanti:
                righe.append({"riga": numero, "codice_fiscale": cf, "stato": "da_verificare",
                              "motivi": ["Nuova scheda: completare " + ", ".join(mancanti)]})
                continue
            voce = {"riga": numero, "codice_fiscale": cf,
                    "nome": f"{dati['cognome']} {dati['nome']}", "stato": "creabile",
                    "campi": sorted(dati), "attivo": dati["attivo"]}
            if not dati["attivo"]:
                voce["avvisi"] = ["Non in forza; data e motivo della cessazione non presenti nel file"]
            if applica:
                nuova = await _crea_anagrafica(
                    {**dati, "import_anagrafica_hash": impronta, "import_anagrafica_riga": numero},
                    attivo=dati["attivo"],
                )
                voce["dipendente_id"] = nuova["id"]
            righe.append(voce)
            continue
        if len(candidati) != 1:
            motivo = "dipendente non presente in anagrafica" if not candidati else "codice fiscale duplicato in anagrafica"
            righe.append({"riga": numero, "codice_fiscale": cf, "stato": "da_verificare", "motivi": [motivo]})
            continue
        dip = candidati[0]
        modifiche: Dict[str, Any] = {}
        conflitti_campo: List[str] = []
        for campo, valore in dati.items():
            if campo == "codice_fiscale":
                continue
            if campo == "attivo":
                # Un foglio non puo' riattivare o cessare un rapporto esistente.
                if stato_rapporto.e_in_forza(dip) != valore:
                    conflitti_campo.append("attivo")
                continue
            corrente = dip.get(campo)
            if _valore_anagrafico_vuoto(corrente):
                modifiche[campo] = valore
            elif not _valori_anagrafici_equivalenti(campo, corrente, valore):
                conflitti_campo.append(campo)
        if "nome" in modifiche or "cognome" in modifiche:
            nome = modifiche.get("nome", dip.get("nome") or "")
            cognome = modifiche.get("cognome", dip.get("cognome") or "")
            nome_completo = f"{cognome} {nome}".strip()
            if nome_completo and _valore_anagrafico_vuoto(dip.get("nome_completo")):
                modifiche["nome_completo"] = nome_completo
        stato = "aggiornabile" if modifiche else "invariato"
        if conflitti_campo and not modifiche:
            stato = "conflitto"
        voce = {"riga": numero, "dipendente_id": dip.get("id"), "codice_fiscale": cf,
                "nome": dip.get("nome_completo") or nominativo or "", "stato": stato,
                "campi": sorted(modifiche)}
        if conflitti_campo:
            voce["conflitti"] = sorted(conflitti_campo)
            voce["motivi"] = ["valori HR gia' presenti e diversi: " + ", ".join(sorted(conflitti_campo))]
        righe.append(voce)
        if applica and modifiche:
            await db.dipendenti.update_one(
                {"id": dip["id"]},
                {"$set": {**modifiche, "updated_at": now_iso()}},
            )

    conteggi = {stato: sum(1 for r in righe if r["stato"] == stato)
                for stato in ("creabile", "aggiornabile", "invariato", "da_verificare")}
    conteggi["conflitto"] = sum(
        1 for r in righe if r["stato"] == "conflitto" or r.get("conflitti")
    )
    return {
        "dry_run": not applica, "hash_sha256": impronta, "foglio": ws.title,
        "crea_mancanti": crea_mancanti,
        "riga_intestazioni": header_row, "righe_lette": len(righe),
        "aggiornati": conteggi["aggiornabile"] if applica else 0,
        "creati": conteggi["creabile"] if applica else 0,
        "conteggi": conteggi, "righe": righe, "colonne_ignorate": colonne_ignorate,
    }


@router.post("/riduzioni-orario")
async def save_riduzioni_orario(data: dict = Body(...)):
    """Salva la riduzione oraria per dipendente: ore/giorno ridotte, paga oraria,
    data inizio e data fine (scadenza sorvegliata). Body: {voci:[{dipendente_id,...}]}."""
    db = get_db()
    n = 0
    for v in (data.get("voci") or []):
        did = v.get("dipendente_id")
        if not did:
            continue

        def num(x):
            try:
                return float(str(x).replace(",", ".")) if x not in (None, "") else None
            except (TypeError, ValueError):
                return None
        rid = {"attiva": bool(v.get("attiva")),
               "ore_giorno": num(v.get("ore_giorno")),
               "paga_oraria": num(v.get("paga_oraria")),
               "data_inizio": v.get("data_inizio") or None,
               "data_fine": v.get("data_fine") or None,
               "note": (v.get("note") or "").strip(),
               "updated_at": now_iso()}
        await db.dipendenti.update_one({"id": did}, {"$set": {"riduzione_orario": rid}})
        n += 1
    return {"salvati": n}


@router.get("/riduzioni-orario/scadenze")
async def riduzioni_in_scadenza(giorni: int = 30):
    """Riduzioni attive con scadenza entro N giorni (o già scadute) — vigilanza contratto."""
    db = get_db()
    oggi = datetime.now(timezone.utc).date()
    out = []
    async for d in db.dipendenti.find({"riduzione_orario.attiva": True}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "riduzione_orario": 1}):
        rid = d.get("riduzione_orario") or {}
        df = rid.get("data_fine")
        if not df:
            continue
        try:
            scad = datetime.strptime(df[:10], "%Y-%m-%d").date()
        except ValueError:
            continue
        gg = (scad - oggi).days
        if gg <= giorni:
            out.append({"dipendente_id": d.get("id"),
                        "nome": f"{d.get('cognome','')} {d.get('nome','')}".strip(),
                        "data_fine": df, "giorni_alla_scadenza": gg,
                        "scaduta": gg < 0, "ore_giorno": rid.get("ore_giorno")})
    out.sort(key=lambda x: x["giorni_alla_scadenza"])
    return out


@router.post("/paghe/importa-pagamenti")
async def importa_pagamenti(file: UploadFile = File(...)):
    """Importa i bonifici/pagamenti dal CSV banca. Riconosce due formati dall'intestazione:
    1) ESITI bonifici (Esecuzione;Ordinante;Beneficiario;Importo;Div;Causale;CRO);
    2) ANDAMENTO conto (Ragione Sociale;Data contabile;Data valuta;Banca;Rapporto;Importo;
       Divisa;Descrizione;Categoria;Hashtag): tiene solo le USCITE (importo negativo),
       scarta commissioni bancarie, estrae il nominativo dal 'FAVORE <Nome>' nella descrizione.
    In entrambi i casi aggancia solo chi è in anagrafica (fornitori esclusi automaticamente).
    Mese di competenza dalla causale (es. '9-2025', 'luglio') o, in mancanza, dalla data del
    movimento. Idempotente (dedup per CRO o hash riga). Aggiorna il bonifico del mese = somma
    dei pagamenti di quel mese e ricalcola lo stato paga (alimenta la prima nota)."""
    import io
    import csv as _csv
    raw = await file.read()
    text = raw.decode("utf-8", errors="ignore")
    reader = _csv.reader(io.StringIO(text), delimiter=";")
    righe = list(reader)
    if not righe:
        raise HTTPException(400, "CSV vuoto")
    db = get_db()
    dips = await db.dipendenti.find({"merged_into": {"$exists": False}},
                                    {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1}).to_list(1000)

    def norm(s):
        return re.sub(r"\s+", " ", str(s or "").strip()).lower()
    by_nome, by_cogn = {}, {}
    for d in dips:
        n, c = norm(d.get("nome")), norm(d.get("cognome"))
        for v in {norm(d.get("nome_completo")), f"{c} {n}".strip(), f"{n} {c}".strip()}:
            if v and len(v) > 5:
                by_nome[v] = d
        if len(c) >= 4:
            by_cogn.setdefault(c, []).append(d)

    def trova_dip(beneficiario):
        b = norm(beneficiario)
        for nome_n, d in by_nome.items():
            if nome_n in b or b in nome_n:
                return d
        for cogn, lst in by_cogn.items():
            if cogn in b and len(lst) == 1:
                return lst[0]
        return None

    def to_float(s):
        try:
            return float(str(s).replace(".", "").replace(",", "."))
        except (TypeError, ValueError):
            return None

    def mese_anno(causale, data_dt):
        c = norm(causale)
        m = re.search(r'\b(\d{1,2})[-/](20\d{2})\b', c)
        if m:
            return int(m.group(1)), int(m.group(2))
        for nome, n in _MESI_IT.items():
            if nome in c:
                y = re.search(r'(20\d{2})', c)
                return n, int(y.group(1)) if y else data_dt.year
        return data_dt.month, data_dt.year

    def favore(s):
        m = re.search(r'favore\s+(.+?)(?:\s+-|\s+notprovide|$)', norm(s))
        return (m.group(1) if m else norm(s))[:50]

    # Rileva il formato dall'intestazione: ESITI bonifici o ESTRATTO CONTO (entrate/uscite)
    hdr = [norm(c) for c in (righe[0] if righe else [])]

    def col(*names):
        return next((i for i, h in enumerate(hdr) if any(n in h for n in names)), None)
    i_ben = col("beneficiario")
    if i_ben is not None:
        formato = "esiti"
        i_data = col("esecuzione", "data") if col("esecuzione", "data") is not None else 0
        i_imp = col("importo") if col("importo") is not None else 3
        i_caus = col("causale", "descrizione")
        i_cro = col("cro")
        i_cat = None
    else:
        formato = "andamento"
        i_data = col("data contabile", "data valuta", "data")
        i_imp = col("importo")
        i_caus = col("descrizione")
        i_cat = col("categoria")
        i_cro = None
        i_ben = i_caus

    importati, non_trovati, affected = 0, [], set()
    for r in righe[1:]:
        if i_imp is None or i_imp >= len(r) or i_data is None or i_data >= len(r):
            continue
        importo = to_float(r[i_imp])
        if importo is None:
            continue
        try:
            data_dt = datetime.strptime(str(r[i_data]).strip()[:10], "%d/%m/%Y")
        except (ValueError, TypeError):
            continue
        causale = (r[i_caus] if i_caus is not None and i_caus < len(r) else "") or ""
        if formato == "andamento":
            if importo >= 0:  # solo uscite = pagamenti
                continue
            cat = (r[i_cat] if i_cat is not None and i_cat < len(r) else "") or ""
            if "commission" in norm(cat) or norm(causale).startswith("comm"):
                continue  # niente commissioni bancarie
            importo = -importo
            beneficiario = favore(causale)
        else:
            if importo <= 0:
                continue
            beneficiario = (r[i_ben] if i_ben is not None and i_ben < len(r) else "") or ""
        if importo < 5:
            continue
        d = trova_dip(beneficiario if formato == "esiti" else causale)
        if not d:
            non_trovati.append(beneficiario or favore(causale))
            continue
        mese, anno = mese_anno(causale, data_dt)
        cro = (r[i_cro].strip() if i_cro is not None and i_cro < len(r) and r[i_cro] else "")
        key = cro or hashlib.sha1(f"{d['id']}|{r[i_data]}|{importo}|{causale}".encode()).hexdigest()
        await db.pagamenti_esiti.update_one(
            {"key": key},
            {"$set": {"key": key, "cro": cro, "dipendente_id": d["id"], "data": data_dt.strftime("%Y-%m-%d"),
                      "importo": importo, "causale": causale, "beneficiario": beneficiario,
                      "mese": mese, "anno": anno}}, upsert=True)
        affected.add((d["id"], mese, anno))
        importati += 1
    # ricalcola il bonifico del mese = somma dei pagamenti di quel mese
    for dip_id, mese, anno in affected:
        tot = 0.0
        async for p in db.pagamenti_esiti.find({"dipendente_id": dip_id, "mese": mese, "anno": anno}, {"_id": 0, "importo": 1}):
            tot += p.get("importo") or 0
        await db.paghe_mensili.update_one(
            {"dipendente_id": dip_id, "anno": anno, "mese": mese},
            {"$set": {"dipendente_id": dip_id, "anno": anno, "mese": mese,
                      "bonifico_importo": round(tot, 2), "bonifico_ricevuto": tot > 0,
                      "bonifico_da_esiti": True, "updated_at": now_iso()}}, upsert=True)
        await _ricalcola_stato_paga(db, dip_id, anno, mese)
    return {"importati": importati, "mesi_aggiornati": len(affected),
            "non_trovati": sorted(set(non_trovati))}


@router.get("/paghe/in-attesa")
async def paghe_in_attesa():
    """Buste in attesa di pagamento (o parziali): elenco per il pannello/avvisi."""
    db = get_db()
    dip_map = {d["id"]: f"{d.get('cognome','')} {d.get('nome','')}".strip()
               async for d in db.dipendenti.find({}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1})}
    out = []
    async for p in db.paghe_mensili.find(
            {"stato_pagamento": {"$in": list(STATI_PAGA_APERTI)}}, {"_id": 0}):
        saldo = p.get("saldo")
        if saldo is None:
            saldo = round(float(p.get("importo_busta") or 0) - float(p.get("bonifico_importo") or 0), 2)
        if not saldo or saldo <= 0:   # al centesimo: anche 0,01 € e' un residuo
            continue
        out.append({"dipendente_id": p.get("dipendente_id"),
                    "dipendente": dip_map.get(p.get("dipendente_id"), p.get("dipendente_id")),
                    "anno": p.get("anno"), "mese": p.get("mese"),
                    "stato": p.get("stato_pagamento"),
                    "busta": round(float(p.get("importo_busta") or 0), 2),
                    "saldo": round(saldo, 2)})
    # 14/09/2026 (titolare): 809 righe dal 2018 sommate come "da erogare" erano
    # fuorvianti — quasi tutte buste storiche gia' pagate con bonifici non
    # agganciati. Prima l'anno corrente (da pagare davvero), poi lo storico
    # ("pagamento non ancora agganciato"), ognuno col suo totale.
    anno_corrente = datetime.now().year
    for x in out:
        x["storico"] = (x["anno"] or 0) < anno_corrente
    out.sort(key=lambda x: (x["storico"], -(x["anno"] or 0), -(x["mese"] or 0)))
    correnti = [x for x in out if not x["storico"]]
    storiche = [x for x in out if x["storico"]]
    return {"righe": out, "totale": len(out), "importo": round(sum(x["saldo"] for x in out), 2),
            "anno_corrente": anno_corrente,
            "da_pagare": {"totale": len(correnti), "importo": round(sum(x["saldo"] for x in correnti), 2)},
            "non_agganciate": {"totale": len(storiche), "importo": round(sum(x["saldo"] for x in storiche), 2)}}


@router.get("/paghe/prima-nota")
async def prima_nota(dipendente_id: str):
    """Prima nota salari di un dipendente per data del movimento: dovuto (busta,
    con l'acconto recuperato in busta), erogato (bonifici e acconti) e saldo
    progressivo (>0 = ancora da pagare). E' la vista cronologica della posizione
    dare/avere (``app/services/posizione_dipendente.py``): un solo registro."""
    from app.services.posizione_dipendente import prima_nota_dipendente
    return await prima_nota_dipendente(get_db(), dipendente_id)


@router.get("/paghe/associazioni-bonifici")
async def associazioni_bonifici(anno: Optional[int] = None, mese: Optional[int] = None,
                                stato: Optional[str] = None):
    """Vista UNICA cedolino↔bonifico. Per ogni busta del periodo mostra l'importo busta,
    i bonifici REALMENTE pagati (collezione pagamenti_esiti: data, importo, causale, riferimento/CRO),
    gli acconti, il saldo e lo stato di associazione:
      - pagato            = erogato (bonifici+acconti) ≥ busta al centesimo, con prova confermata
      - parziale          = erogato > 0 ma < busta, con prova confermata
      - da_verificare     = importo candidato presente, ma prova non confermata
      - da_pagare         = busta presente, nessun pagamento
      - in_attesa_busta   = pagamento presente ma la busta non e' ancora arrivata (saldo sconosciuto)
    Inoltre indica la 'fonte' del bonifico (banca/prima_nota/manuale), la 'qualita' del match
    (esatto/per_importo/aggregato/da_verificare) e se esiste il PDF del cedolino.
    Sorgente dati = sistema vivo paghe_mensili + pagamenti_esiti (nessun sistema parallelo)."""
    return await _calcola_associazioni_bonifici(get_db(), anno, mese, stato)


@router.post("/paghe/bonifica-regole-pagamento")
async def bonifica_regole_pagamento(dry_run: bool = True, force: bool = False):
    """Bonifica reversibile dello storico: anteprima per difetto.

    Rimuove dal saldo (conservandoli nello storico della riga) i contanti non
    ammessi dal 01/07/2018 e rende certe le prove documentali/bancarie che
    citano un solo dipendente. ``force`` serve solo a ripetere una migrazione
    gia' completata dopo l'arrivo di dati storici ulteriori.
    """
    from app.hr.services.regole_pagamenti_dipendenti import bonifica_storico

    return await bonifica_storico(get_db(), dry_run=dry_run, force=force)


async def _calcola_associazioni_bonifici(db, anno: Optional[int] = None, mese: Optional[int] = None,
                                         stato: Optional[str] = None):
    from app.hr.db_supabase import SupabaseDatabase

    if isinstance(db, SupabaseDatabase):
        await db.refresh_collections("cedolini", "paghe_mensili", "dipendenti", "pagamenti_esiti")
    q = {}
    if anno:
        q["anno"] = int(anno)
    if mese:
        q["mese"] = int(mese)

    dip_map = {}
    async for d in db.dipendenti.find({}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1,
                                            "codice_fiscale": 1, "stato": 1, "attivo": 1,
                                            "in_carico": 1, "data_fine_rapporto": 1,
                                            "data_cessazione": 1, "data_dimissione": 1,
                                            "data_cessazione_prevista": 1}):
        dip_map[d["id"]] = d

    # Prefetch in blocco (UNA lettura per tabella) invece che una query per ogni
    # riga di paghe_mensili: l'adattatore Supabase non ha indici, ogni find/
    # find_one legge l'intera tabella e filtra in Python — con centinaia/migliaia
    # di buste, farlo dentro il ciclo era un incrocio N×M che portava la risposta
    # a decine o centinaia di secondi (e in produzione ha saturato il pool di
    # connessioni, con 502 a cascata anche su endpoint scollegati). Qui si legge
    # ogni tabella una sola volta e si indicizza in memoria.
    # pdf_data escluso qui per lo stesso motivo dei cedolini più sotto: alcuni
    # pagamenti (import da Drive, ponte bonifici storici) ora portano il PDF
    # allegato, un'inclusione lo trasferirebbe comunque per intero per ogni riga.
    esiti_idx: Dict[tuple, List[Dict[str, Any]]] = {}
    from app.services.pagamenti_mensilita import indice_coperture, periodi_saldati
    tutte_prove = []
    async for e in db.pagamenti_esiti.find({}, {"_id": 0, "pdf_data": 0}):
        tutte_prove.append(e)
        if periodi_saldati(e):
            continue
        esiti_idx.setdefault((e.get("dipendente_id"), e.get("mese"), e.get("anno")), []).append(e)
    coperture = indice_coperture(tutte_prove)
    for lst in esiti_idx.values():
        lst.sort(key=lambda e: e.get("data") or "")

    # NON includere pdf_data qui: l'adattatore Supabase ottimizza solo le
    # proiezioni "ad esclusione" (campo: 0) — una proiezione a inclusione
    # come questa arriverebbe comunque per intero, PDF in base64 compresi
    # (anche centinaia di MB su ~1500 cedolini). Il PDF si scarica a parte,
    # l'esistenza del record da sola non prova però la presenza dell'originale.
    pdf_incorporati = {c.get("id") async for c in db.cedolini.find(
        {"pdf_data": {"$exists": True}}, {"_id": 0, "pdf_data": 0})}

    def ha_originale(c):
        return bool(c and (c.get("blob_key") or c.get("drive_file_id") or c.get("ha_pdf")
                          or ((c.get("_drive_payloads") or {}).get("pdf_data") or {}).get("drive_file_id")
                          or c.get("id") in pdf_incorporati))
    cedolini_lista: List[Dict[str, Any]] = []
    ced_by_periodo: Dict[tuple, Dict[str, Any]] = {}
    ced_by_id = {}
    from app.hr.services.sincronizza_paghe_mensili import _mese_registro
    from app.services.cedolini_rapporti import raggruppa_cedolini
    cedolini_lista = await db.cedolini.find({}, {"_id": 0, "pdf_data": 0}).to_list(None)
    for c in raggruppa_cedolini(cedolini_lista).values():
        ced_by_id[c.get("id")] = c
        try:
            mese_cedolino = _mese_registro(c)
        except (KeyError, TypeError, ValueError):
            continue
        chiave = (c.get("dipendente_id"), mese_cedolino, c.get("anno"))
        ced_by_periodo.setdefault(chiave, c)

    def trova_cedolino(dip_id, cognome, mese_p, anno_p):
        c = ced_by_periodo.get((dip_id, mese_p, anno_p))
        if c:
            return c
        # Non collegare un PDF tramite il solo cognome: l'omonimia rischia di
        # mostrare il cedolino di un'altra persona. Serve l'id canonico.
        return None

    righe = []
    tot = {"buste": 0.0, "bonifici": 0.0, "acconti": 0.0, "saldo": 0.0,
           "pagati": 0, "parziali": 0, "da_pagare": 0, "senza_busta": 0,
           "associati": 0, "da_verificare": 0}

    from app.services.posizione_dipendente import ZERO, dovuto_busta, importo as _dec
    from app.hr.services import stato_rapporto as stato_rapporto_service
    from app.hr.services.regole_pagamenti_dipendenti import filtra_acconti_contanti

    paghe = await db.paghe_mensili.find(q, {"_id": 0}).to_list(None)
    chiavi_paghe = {(p.get("dipendente_id"), p.get("anno"), p.get("mese")) for p in paghe}
    for dip_id, anno_c, mese_c in coperture:
        if (dip_id, anno_c, mese_c) not in chiavi_paghe and (not anno or anno_c == int(anno)) and (not mese or mese_c == int(mese)):
            paghe.append({"dipendente_id": dip_id, "anno": anno_c, "mese": mese_c})
    for p in paghe:
        dip_id = p.get("dipendente_id")
        copertura = coperture.get((dip_id, p.get("anno"), p.get("mese")), [])
        dip = dip_map.get(dip_id) or {}
        ced = trova_cedolino(dip_id, dip.get("cognome"), p.get("mese"), p.get("anno"))
        if not ced:
            ced = ced_by_id.get(p.get("cedolino_id"))
        if ced and ced.get("dipendente_id") != dip_id:
            ced = None
        dovuto = dovuto_busta(p, ced)
        # busta assente (``None``) = non ancora arrivata, non uno zero
        busta_dec = dovuto["dovuto"]
        busta = float(busta_dec or ZERO)
        bon_dec = _dec(p.get("bonifico_importo")) or ZERO
        bon = float(bon_dec)
        acc_list, acc_scartati = filtra_acconti_contanti(dip, p.get("acconti") or [])
        acc_dec = sum((_dec(a.get("importo")) or ZERO for a in acc_list), ZERO)
        acc = float(acc_dec)
        if busta_dec is None and bon <= 0 and acc <= 0 and not p.get("importi_excel") and not copertura:
            continue

        nome = f"{dip.get('cognome', '')} {dip.get('nome', '')}".strip() or dip_id

        # Bonifici reali pagati (esiti banca) per questo dipendente/mese/anno
        esiti = [{
            "key": e.get("key"),
            "data": e.get("data"),
            "importo": round(float(e.get("importo") or 0), 2),
            "modificato": bool(e.get("modificato_manualmente")),
            "causale": e.get("causale") or "",
            "beneficiario": e.get("beneficiario") or "",
            "riferimento": e.get("cro") or e.get("key") or "",
            "pdf_key": e.get("key") if e.get("ha_pdf") else None,
        } for e in esiti_idx.get((dip_id, p.get("mese"), p.get("anno")), [])]

        erogato_dec = bon_dec + acc_dec
        erogato = float(erogato_dec)
        # Stesso motore dello stato del mese (al centesimo); qui «in attesa del
        # pagamento» si chiama ``da_pagare`` e una busta assente e' «in attesa della busta».
        stato_importo = stato_paga_mese(busta_dec, erogato_dec)
        if stato_importo == STATO_PAGA_IN_ATTESA_PAGAMENTO:
            stato_importo = "da_pagare"
        senza_busta = busta_dec is None

        # Fonte del bonifico
        from app.constants.stati_associazione_bonifico import esiti_confermati, ha_riscontro_bancario
        prove = esiti_idx.get((dip_id, p.get("mese"), p.get("anno")), [])
        if prove:
            fonte = ("banca" if all(ha_riscontro_bancario(e) for e in prove)
                     else "conferma_titolare" if esiti_confermati(prove) else "documento_da_verificare")
        elif p.get("bonifico_da_prima_nota"):
            fonte = "prima_nota"
        elif bon > 0:
            fonte = "manuale"
        else:
            fonte = None

        # Qualità dell'associazione (quanto è affidabile il legame busta↔bonifico).
        # Importo, nome e periodo sono indizi: anche quando coincidono non
        # confermano da soli il collegamento. Solo la conferma esplicita e
        # reversibile ``bonifico_riconciliato`` trasforma il candidato in un
        # legame verificato.
        riconciliato = p.get("bonifico_riconciliato") is True or esiti_confermati(prove)
        # Lo stato contabile effettivo non può derivare dal solo quadramento
        # numerico. Conserviamo quel calcolo come candidato, ma finché manca
        # una conferma reversibile della prova bancaria/assegno esponiamo
        # DA_VERIFICARE e non PAGATO/PARZIALE.
        # Senza busta non c'e' niente da verificare: resta «in attesa della busta».
        if erogato > 0 and not riconciliato and not senza_busta:
            st = "da_verificare"
        else:
            st = stato_importo

        from app.hr.services.importi_paghe_tabellari import avvisi
        avvisi_excel = avvisi({**p, "importo_busta": float(busta_dec) if busta_dec is not None else None,
                               "netto_stampato": float(dovuto["netto_busta"]) if dovuto["netto_busta"] is not None else None})
        acconto_da_verificare = bool(((ced or {}).get("dati_chiave") or {}).get("acconto_recuperato_da_verificare"))
        if avvisi_excel or acconto_da_verificare:
            st = "da_verificare"
        if copertura:
            st = "pagato_documentato"

        if stato and st != stato:
            continue

        if st in (STATO_PAGA_PAGATO, "pagato_documentato"):
            tot["pagati"] += 1
        elif st == STATO_PAGA_PARZIALE:
            tot["parziali"] += 1
        elif st == "da_pagare":
            tot["da_pagare"] += 1
        elif st == STATO_PAGA_IN_ATTESA_BUSTA:
            tot["senza_busta"] += 1
        elif st == "da_verificare":
            tot["da_verificare"] += 1
        if bon <= 0:
            qualita = None
        elif not riconciliato:
            qualita = "da_verificare"
        elif esiti:
            # confronti al centesimo: nessuna tolleranza (titolare 02/10/2026)
            if len(esiti) == 1 and busta_dec and busta_dec > 0 and _dec(esiti[0]["importo"]) == busta_dec:
                qualita = "esatto"          # un solo bonifico che combacia con la busta
            elif busta_dec and busta_dec > 0 and bon_dec == busta_dec:
                qualita = "per_importo"     # somma bonifici = busta
            elif len(esiti) > 1:
                qualita = "aggregato"       # più bonifici nello stesso mese
            else:
                qualita = "per_importo"
        else:
            qualita = "da_verificare"       # importo inserito a mano / da prima nota, senza prova banca

        associato = riconciliato
        if st in (STATO_PAGA_PAGATO, STATO_PAGA_PARZIALE, STATO_PAGA_IN_ATTESA_BUSTA):
            if associato:
                tot["associati"] += 1

        # Presenza del riferimento all'originale, senza scaricare il PDF.
        has_pdf = ha_originale(ced)
        cedolino_id = ced.get("id") if ced else None

        tot["buste"] += busta
        tot["bonifici"] += bon
        tot["acconti"] += acc
        if not senza_busta and not copertura:
            tot["saldo"] += (busta - erogato)

        righe.append({
            "dipendente_id": dip_id,
            "dipendente": nome,
            "anno": p.get("anno"),
            "mese": p.get("mese"),
            "busta": round(busta, 2) if busta_dec is not None else None,
            "netto_stampato": float(dovuto["netto_busta"]) if dovuto["netto_busta"] is not None else None,
            "acconto_recuperato": float(dovuto["acconto"]),
            "fonte_acconto_recuperato": dovuto["fonte_acconto"],
            "acconto_da_verificare": acconto_da_verificare,
            "netto_confermato": p.get("netto_confermato"),
            "avvisi_importo": avvisi_excel,
            "bonifico": round(bon, 2),
            "acconti": round(acc, 2),
            "acconti_dettaglio": [{"importo": round(float(a.get("importo") or 0), 2), "data": a.get("data")} for a in acc_list],
            "acconti_non_ammessi": len(acc_scartati),
            "data_cessazione_rapporto": stato_rapporto_service.data_fine_rapporto(dip),
            "erogato": round(erogato, 2),
            # senza busta il saldo non si conosce: mai uno zero o un negativo di comodo
            "saldo": 0.0 if copertura else None if senza_busta else round(busta - erogato, 2),
            "pagamenti_copertura": copertura,
            "stato": st,
            "stato_importo": stato_importo,
            "fonte": fonte,
            "qualita": qualita,
            "associato": associato,
            "riconciliato": riconciliato,
            "riconciliato_auto": bool(p.get("bonifico_riconciliato_auto")),
            "bonifico_data": p.get("bonifico_data"),
            "bonifici": esiti,
            "n_bonifici": len(esiti),
            "busta_manuale": bool(p.get("importo_busta_manuale")),
            "busta_originale": p.get("importo_busta_originale"),
            "busta_nota": p.get("importo_busta_nota"),
            "cedolino_pdf": has_pdf,
            "cedolino_id": cedolino_id,
            "cedolini": [{"cedolino_id": c.get("id"), "cedolino_pdf": ha_originale(c),
                          "netto": c.get("netto"), "rapporto": c.get("rapporto_lavoro") or {}}
                         for c in ((ced or {}).get("cedolini_componenti") or ([ced] if ced else []))],
        })

    # La prova di un pagamento cumulativo compare su ogni mese, il denaro una volta sola.
    cumulativi = {p["id"]: p for r in righe for p in r.get("pagamenti_copertura", [])}
    tot["bonifici"] += sum(float(p["importo"]) for p in cumulativi.values())
    righe.sort(key=lambda r: ((r["anno"] or 0), (r["mese"] or 0), r["dipendente"]), reverse=True)
    for k in ("buste", "bonifici", "acconti", "saldo"):
        tot[k] = round(tot[k], 2)
    # Un PDF acquisito senza netto leggibile rimane visibile, ma non crea
    # una busta da zero euro né un debito inventato.
    da_leggere = []
    for c in cedolini_lista:
        if c.get("netto") is not None or not ha_originale(c):
            continue
        if anno and c.get("anno") != int(anno):
            continue
        if stato and stato != "da_verificare":
            continue
        try:
            mese_cedolino = _mese_registro(c)
        except (KeyError, TypeError, ValueError):
            continue
        if mese and mese_cedolino != int(mese):
            continue
        dip = dip_map.get(c.get("dipendente_id")) or {}
        da_leggere.append({
            "cedolino_id": c.get("id"), "dipendente_id": c.get("dipendente_id"),
            "dipendente": f"{dip.get('cognome', '')} {dip.get('nome', '')}".strip()
                or c.get("nome_dipendente") or "Dipendente da associare",
            "anno": c.get("anno"), "mese": mese_cedolino,
        })
    return {"righe": righe, "totali": tot, "count": len(righe), "cedolini_da_verificare": da_leggere}


@router.get("/paghe/associazioni-bonifici/export-excel")
async def associazioni_bonifici_export_excel(anno: Optional[int] = None, mese: Optional[int] = None,
                                              stato: Optional[str] = None):
    """Esporta documenti, pagamenti, PDF non collegati e mesi riconciliati separatamente."""
    from fastapi.responses import StreamingResponse
    from app.hr.services.export_paghe import workbook_paghe

    dati = await _calcola_associazioni_bonifici(get_db(), anno, mese, stato)
    wb = workbook_paghe(dati)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    nome_file = "cedolini_bonifici"
    if anno:
        nome_file += f"_{anno}"
    if mese:
        nome_file += f"_{int(mese):02d}"
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nome_file}.xlsx"'})


@router.post("/paghe/conferma-associazione")
async def conferma_associazione(data: dict):
    """Conferma/annulla manualmente l'associazione bonifico↔cedolino di una busta.
    Imposta bonifico_riconciliato e traccia data/nota. Non crea record nuovi:
    agisce sul record paghe_mensili esistente (sistema unico)."""
    dip = data.get("dipendente_id")
    anno = data.get("anno")
    mese = data.get("mese")
    if not dip or not anno or not mese:
        raise HTTPException(status_code=400, detail="dipendente_id, anno, mese obbligatori")
    val = bool(data.get("riconciliato", True))
    set_doc = {"bonifico_riconciliato": val, "updated_at": now_iso()}
    if val:
        set_doc["associazione_confermata_at"] = now_iso()
    if data.get("nota") is not None:
        set_doc["associazione_nota"] = str(data.get("nota"))
    db = get_db()
    res = await db.paghe_mensili.update_one(
        {"dipendente_id": dip, "anno": int(anno), "mese": int(mese)}, {"$set": set_doc})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Busta non trovata per quel dipendente/mese")
    # La conferma porta sul cedolino del gestionale lo stato del mese (il bonifico
    # ricevuto del registro paghe come pagamento); l'annullo lo toglie.
    paga = await db.paghe_mensili.find_one(
        {"dipendente_id": dip, "anno": int(anno), "mese": int(mese)}, {"_id": 0, "bonifico_importo": 1})
    cedolino_gest = await allinea_cedolino_gestionale_da_paghe(
        db, _db_gestionale(), dip, int(anno), int(mese),
        riferimento=f"hr:conferma_associazione:{dip}:{int(anno)}-{int(mese):02d}",
        importo=(paga or {}).get("bonifico_importo"), data=set_doc.get("associazione_confermata_at"),
        ritira=not val)
    return {"ok": True, "riconciliato": val, "cedolino_gestionale": cedolino_gest}


# ============ BUSTE PAGA ============

@router.get("/buste-paga")
async def get_buste_paga(anno: Optional[int] = None, mese: Optional[int] = None, dipendente_id: Optional[str] = None):
    """
    Recupera cedolini dalla collezione 'cedolini' (dati storici dal 2014).
    Se dipendente_id è fornito, cerca anche per nome del dipendente in dipendenti_cloud.
    """
    query = {}
    if anno:
        query["anno"] = anno
    if mese:
        query["mese"] = mese
    
    # Se abbiamo un dipendente_id, dobbiamo trovare il nome per cercare nei cedolini
    if dipendente_id:
        dip = await get_db().dipendenti_cloud.find_one({"id": dipendente_id})
        if dip:
            query["$or"] = [
                {"dipendente_id": dipendente_id},
                {"nome_dipendente": {"$regex": dip.get('cognome', ''), "$options": "i"}}
            ]
    
    # Leggi dalla collezione cedolini (dati storici)
    cedolini = await get_db().cedolini.find(query, {"_id": 0}).sort([("anno", -1), ("mese", -1)]).to_list(1000)
    
    # Normalizza i campi per compatibilità con il frontend
    result = []
    for c in cedolini:
        result.append({
            "id": c.get("id", str(c.get("_id", ""))),
            "dipendente_id": c.get("dipendente_id", ""),
            "dipendente_nome": c.get("nome_dipendente") or c.get("dipendente_nome") or "",
            "mese": c.get("mese"),
            "anno": c.get("anno"),
            "lordo": c.get("lordo", 0),
            "netto": c.get("netto", 0),
            "inps": c.get("inps_dipendente", 0),
            "irpef": c.get("irpef", 0),
            "trattenute": c.get("trattenute", 0),
            "stato": c.get("stato_pagamento") or c.get("stato") or "DA_PAGARE",
            "created_at": c.get("created_at", "")
        })
    
    return result

@router.post("/buste-paga")
async def create_busta_paga(busta: BustaPagaCloud):
    busta_dict = busta.model_dump()
    busta_dict["id"] = generate_id()
    busta_dict["created_at"] = now_iso()
    await get_db().buste_paga_cloud.insert_one(busta_dict)
    return serialize_doc(busta_dict)

@router.post("/buste-paga/genera")
async def genera_buste_paga(data: dict):
    """Genera buste paga per tutti i dipendenti attivi per un mese specifico"""
    mese = data.get("mese")
    anno = data.get("anno")
    lordo_default = data.get("lordo", 1500)
    
    if not mese or not anno:
        raise HTTPException(status_code=400, detail="mese e anno sono obbligatori")
    
    dipendenti = await get_db().dipendenti_cloud.find({"stato": "attivo"}, {"_id": 0}).to_list(1000)
    created = 0
    
    for dip in dipendenti:
        existing = await get_db().buste_paga_cloud.find_one({
            "dipendente_id": dip["id"],
            "mese": mese,
            "anno": anno
        })
        
        if not existing:
            inps = round(lordo_default * 0.0919, 2)
            irpef = round((lordo_default - inps) * 0.23, 2)
            netto = round(lordo_default - inps - irpef, 2)
            
            busta = {
                "id": generate_id(),
                "dipendente_id": dip["id"],
                "mese": mese,
                "anno": anno,
                "lordo": lordo_default,
                "inps": inps,
                "irpef": irpef,
                "trattenute": 0,
                "netto": netto,
                "stato": "DA_PAGARE",
                "created_at": now_iso()
            }
            await get_db().buste_paga_cloud.insert_one(busta)
            created += 1
    
    return {"message": f"Generate {created} buste paga"}

@router.put("/buste-paga/{busta_id}/paga")
async def paga_busta(busta_id: str):
    result = await get_db().buste_paga_cloud.update_one(
        {"id": busta_id},
        {"$set": {"stato": "PAGATO", "data_pagamento": now_iso()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Busta paga non trovata")
    return {"message": "Busta paga marcata come pagata"}

# ============ MISSIONI ============

@router.get("/missioni")
async def get_missioni(dipendente_id: Optional[str] = None, stato: Optional[str] = None):
    query = {}
    if dipendente_id:
        query["dipendente_id"] = dipendente_id
    if stato:
        query["stato"] = stato
    missioni = await get_db().missioni_cloud.find(query, {"_id": 0}).to_list(1000)
    return missioni

@router.post("/missioni")
async def create_missione(missione: MissioneCloud):
    miss_dict = await _dati_missione(missione)
    miss_dict["id"] = generate_id()
    miss_dict["created_at"] = now_iso()
    await get_db().missioni_cloud.insert_one(miss_dict)
    return serialize_doc(miss_dict)


async def _dati_missione(missione: MissioneCloud):
    from datetime import date
    import math

    dati = missione.model_dump()
    try:
        inizio = date.fromisoformat(dati["data_inizio"])
        fine = date.fromisoformat(dati["data_fine"])
    except ValueError as exc:
        raise HTTPException(400, "Inserisci date valide per la missione") from exc
    if fine < inizio:
        raise HTTPException(400, "La data fine non può precedere la data inizio")
    if not math.isfinite(dati["rimborso"]) or dati["rimborso"] < 0:
        raise HTTPException(400, "Il rimborso deve essere un importo non negativo")
    for campo in ("destinazione", "scopo"):
        dati[campo] = dati[campo].strip()
        if not dati[campo]:
            raise HTTPException(400, "Destinazione e scopo sono obbligatori")
    if not await get_db().dipendenti.find_one({"id": dati["dipendente_id"]}, {"_id": 0, "id": 1}):
        raise HTTPException(404, "Dipendente non trovato")
    dati["stato"] = "in_attesa"
    return dati


@router.put("/missioni/{missione_id}")
async def update_missione(missione_id: str, missione: MissioneCloud):
    db = get_db()
    corrente = await db.missioni_cloud.find_one({"id": missione_id}, {"_id": 0})
    if not corrente:
        raise HTTPException(404, "Missione non trovata")
    if corrente.get("stato") != "in_attesa":
        raise HTTPException(409, "Una missione già approvata non può essere modificata da questa pagina")
    dati = await _dati_missione(missione)
    dati["updated_at"] = now_iso()
    result = await db.missioni_cloud.update_one({"id": missione_id, "stato": "in_attesa"}, {"$set": dati})
    if not result.matched_count:
        raise HTTPException(409, "La missione è cambiata: aggiorna la pagina")
    return {**corrente, **dati}

@router.put("/missioni/{missione_id}/approva")
async def approva_missione(missione_id: str):
    db = get_db()
    miss = await db.missioni_cloud.find_one({"id": missione_id}, {"_id": 0})
    if not miss:
        raise HTTPException(status_code=404, detail="Missione non trovata")
    await db.missioni_cloud.update_one(
        {"id": missione_id}, {"$set": {"stato": "approvata", "approvata_il": now_iso()}})

    automazioni = []
    rimborso = float(miss.get("rimborso") or 0)
    dip_id = miss.get("dipendente_id")
    dip = await db.dipendenti.find_one({"id": dip_id}, {"_id": 0, "nome_completo": 1, "nome": 1, "cognome": 1}) if dip_id else None
    nome = (dip or {}).get("nome_completo") or (f"{(dip or {}).get('cognome','')} {(dip or {}).get('nome','')}".strip() if dip else "")

    # Rimborso missione → partita aperta (tracciamento finanziario)
    if rimborso > 0 and dip_id:
        try:
            from app.services.partite_aperte_engine import crea_partita, TipoPartita
            await crea_partita(
                tipo=TipoPartita.ALTRO, documento_id=missione_id,
                documento_collection="missioni_cloud", controparte_id=dip_id,
                controparte_nome=nome, importo=rimborso, db=db, data_documento=now_iso()[:10],
                extra={"categoria": "rimborso_missione", "destinazione": miss.get("destinazione")})
            automazioni.append("partita_rimborso")
        except Exception:
            pass
    # Notifica al dipendente
    if dip_id:
        try:
            from app.hr.services.notifiche import crea_notifica
            await crea_notifica(db, dip_id, "missione", "Missione approvata",
                                f"La missione a {miss.get('destinazione','')} è stata approvata"
                                + (f" · rimborso € {rimborso:.2f}" if rimborso > 0 else "") + ".",
                                extra={"missione_id": missione_id})
            automazioni.append("notifica_dipendente")
        except Exception:
            pass
    return {"message": "Missione approvata", "automazioni": automazioni}

@router.delete("/missioni/{missione_id}")
async def delete_missione(missione_id: str):
    corrente = await get_db().missioni_cloud.find_one({"id": missione_id}, {"_id": 0})
    if corrente and corrente.get("stato") != "in_attesa":
        raise HTTPException(409, "Una missione già approvata non può essere eliminata da questa pagina")
    result = await get_db().missioni_cloud.delete_one({"id": missione_id, "stato": "in_attesa"})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Missione non trovata")
    return {"message": "Missione eliminata"}

# ============ DOCUMENTI ============

@router.get("/documenti")
async def get_documenti(dipendente_id: Optional[str] = None):
    """Elenco SENZA il contenuto dei file (base64): prima ogni apertura
    dell'app scaricava tutti i PDF dell'archivio solo per la lista."""
    query = {}
    if dipendente_id:
        query["dipendente_id"] = dipendente_id
    documenti = await get_db().documenti_cloud.find(query, {"_id": 0, "file_data": 0}).to_list(2000)
    for d in documenti:
        d["ha_file"] = bool(d.get("hash") or d.get("file_size"))
    return documenti


TIPI_DOCUMENTO_MANUALE = {
    "Contratto": "CONTRATTO", "CUD": "CERTIFICAZIONE_UNICA", "Certificato": "CERTIFICATO",
    "Dimissioni / cessazione": "DIMISSIONI", "UNILAV": "UNILAV",
    "Lettera di licenziamento": "LICENZIAMENTO", "Attestato HACCP": "ATTESTATO_HACCP", "Altro": "ALTRO",
}


@router.post("/documenti")
async def create_documento(
    dipendente_id: str = Form(...), titolo: str = Form(...), tipo: str = Form("Altro"),
    scadenza: Optional[str] = Form(None), file: Optional[UploadFile] = File(None),
):
    """Nuovo documento con (facoltativo) il PDF allegato. Un modulo di
    dimissioni telematiche caricato qui passa anche dagli adempimenti del
    gestionale (alert HR + scadenza UNILAV), come se fosse arrivato per posta."""
    db = get_db()
    dip = await db.dipendenti.find_one({"id": dipendente_id}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "nome_completo": 1})
    if not dip:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    categoria = TIPI_DOCUMENTO_MANUALE.get(tipo) or (tipo.strip().upper().replace(" ", "_") if tipo else "ALTRO")
    doc_dict = {
        "id": generate_id(), "dipendente_id": dipendente_id, "titolo": titolo.strip(), "tipo": tipo,
        "categoria": categoria, "scadenza": scadenza or None, "data_caricamento": now_iso(),
        "dipendente_nome": dip.get("nome_completo") or f"{dip.get('cognome', '')} {dip.get('nome', '')}".strip(),
        "origine": "manuale",
    }
    raw = await file.read() if file is not None else b""
    esito_extra = {}
    if raw:
        h = hashlib.sha256(raw).hexdigest()
        if await db.documenti_cloud.find_one({"hash": h}, {"_id": 0, "id": 1}):
            raise HTTPException(status_code=409, detail="Questo file e' gia' in archivio")
        doc_dict.update({"filename": file.filename or f"{categoria.lower()}.pdf", "hash": h,
                         "file_size": len(raw), "file_data": base64.b64encode(raw).decode()})
        if categoria == "DIMISSIONI" and raw[:4] == b"%PDF":
            try:
                from app.services.administrative_document_parser import extract_administrative_metadata
                from app.services.dimissioni_adempimenti import registra_dimissioni
                from app.database import Database as DatabaseGestionale

                metadata = extract_administrative_metadata(content=raw, filename=doc_dict["filename"],
                                                           document_type="dimissioni_telematiche")
                esito_extra["adempimenti_dimissioni"] = await registra_dimissioni(
                    DatabaseGestionale.get_db(), metadata, documento_id=doc_dict["id"], filename=doc_dict["filename"])
            except Exception as e:  # mai bloccare l'archiviazione
                esito_extra["adempimenti_dimissioni"] = {"errore": str(e)[:200]}
    await db.documenti_cloud.insert_one(dict(doc_dict))
    doc_dict.pop("file_data", None)
    doc_dict["ha_file"] = bool(raw)
    return {**doc_dict, **esito_extra}

@router.delete("/documenti/{documento_id}")
async def delete_documento(documento_id: str):
    result = await get_db().documenti_cloud.delete_one({"id": documento_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Documento non trovato")
    return {"message": "Documento eliminato"}


_CF_DOC_RE = re.compile(r'\b([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b')
CATEGORIE_DOC = ["UNILAV", "CERTIFICAZIONE_UNICA", "CONTRATTO", "RIDUZIONE_ORARIO", "DIMISSIONI",
                 "LICENZIAMENTO", "BONIFICO", "CODICE_FISCALE", "CARTA_IDENTITA", "BUSTA_PAGA",
                 "CERTIFICATO", "ATTESTATO_HACCP", "ALTRO"]


def classifica_documento(text: str, filename: str = "") -> str:
    """Riconosce il tipo soltanto dal contenuto estratto.

    Il nome file non costituisce prova; una scansione senza testo resta ALTRO
    e richiede verifica invece di essere instradata per supposizione.
    """
    t = (text or "").lower()

    def H(s, *ks):
        return any(k in s for k in ks)
    # 1) Segnali forti dal TESTO
    if H(t, "modulo recesso rapporto di lavoro", "recesso dal rapporto di lavoro", "dimissioni volontarie",
         "dimissioni telematiche", "risoluzione consensuale"):
        return "DIMISSIONI"
    if H(t, "lettera di licenziamento", "licenziamento per", "intimazione di licenziamento"):
        return "LICENZIAMENTO"
    if H(t, "unilav", "comunicazione obbligatoria", "modello unificato lav", "centro per l'impiego"):
        return "UNILAV"
    if H(t, "certificazione unica", "redditi di lavoro dipendente e assimilati"):
        return "CERTIFICAZIONE_UNICA"
    if H(t, "contratto individuale di lavoro", "contratto di lavoro", "patto di prova", "lettera di assunzione"):
        return "CONTRATTO"
    if H(t, "bonifico", "ordinante", "beneficiario", "disposizione di pagamento", "sepa credit"):
        return "BONIFICO"
    if H(t, "busta paga", "cedolino", "netto in busta", "retribuzione lorda"):
        return "BUSTA_PAGA"
    if H(t, "carta di identità", "carta d'identità", "documento di identità", "carta d identita"):
        return "CARTA_IDENTITA"
    if H(t, "riduzione orario", "riduzione dell'orario", "riduzione dell orario", "trasformazione part-time", "riduzione part time"):
        return "RIDUZIONE_ORARIO"
    # Segnale debole dal testo
    if H(t, "tessera sanitaria", "servizio sanitario nazionale"):
        return "CODICE_FISCALE"
    return "ALTRO"


async def _indici_dipendenti(db):
    """Indici per riconoscere il dipendente da CF/nome nei documenti."""
    dips = await db.dipendenti.find({"merged_into": {"$exists": False}},
                                    {"_id": 0, "id": 1, "nome": 1, "cognome": 1,
                                     "nome_completo": 1, "codice_fiscale": 1,
                                     "stato": 1, "attivo": 1, "in_carico": 1,
                                     "data_fine_rapporto": 1, "data_cessazione": 1,
                                     "data_dimissione": 1,
                                     "data_cessazione_prevista": 1}).to_list(1000)
    return indici_da_dipendenti(dips)


def indici_da_dipendenti(dips):
    """Gli stessi indici da un elenco gia' letto (la banca lo carica da se')."""
    def norm(s):
        return re.sub(r"\s+", " ", str(s or "").strip()).lower()
    coppie_cf, coppie_nome, by_cogn = [], [], {}
    for d in dips:
        cf = (d.get("codice_fiscale") or "").upper().strip()
        if cf:
            coppie_cf.append((cf, d))
        n, c = norm(d.get("nome")), norm(d.get("cognome"))
        for v in {norm(d.get("nome_completo")), f"{c} {n}".strip(), f"{n} {c}".strip()}:
            if v and len(v) > 6:
                coppie_nome.append((v, d))
        if len(c) >= 4:
            by_cogn.setdefault(c, []).append(d)
    from app.hr.services.identita_dipendente import indicizza_alias_univoci
    return {"cf": indicizza_alias_univoci(coppie_cf),
            "nome": {k.lower(): v for k, v in indicizza_alias_univoci(coppie_nome).items()},
            "cogn": by_cogn}


async def _archivia_documento_cloud(db, filename, raw, contesto="", indici=None, origine="upload_massivo"):
    """Classifica un PDF (UNILAV, C.U., contratto, CF, busta…), trova il dipendente dal
    codice fiscale o dal nome, e lo archivia nella sua cartella (documenti_cloud).
    Anti-duplicati per hash. Riusato da upload massivo E import da email/Gmail.
    Ritorna (esito, categoria, dipendente_nome) con esito in
    'caricato'|'non_assegnato'|'duplicato'|'vuoto'."""
    import io
    if not raw:
        return ("vuoto", None, None)
    h = hashlib.sha256(raw).hexdigest()
    if await db.documenti_cloud.find_one({"hash": h}):
        return ("duplicato", None, None)
    text = ""
    if raw[:4] == b"%PDF":
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                for p in pdf.pages[:6]:
                    text += (p.extract_text() or "") + "\n"
        except Exception:
            text = ""
    if indici is None:
        indici = await _indici_dipendenti(db)
    categoria = classifica_documento(text)
    from app.services.hr_pagamenti_deposito import risolvi_dipendente
    d, livello = risolvi_dipendente(indici, text)
    if livello not in {"cf", "nome"}:
        d = None
    doc = {"id": generate_id(),
           "dipendente_id": (d or {}).get("id"),
           "dipendente_nome": (f"{d.get('cognome','')} {d.get('nome','')}".strip() if d else None),
           "titolo": filename, "filename": filename,
           "tipo": categoria, "categoria": categoria, "hash": h,
           "file_data": base64.b64encode(raw).decode(),
           "assegnato": bool(d), "origine": origine, "data_caricamento": now_iso()}
    await db.documenti_cloud.insert_one(doc)
    return ("caricato" if d else "non_assegnato", categoria, doc["dipendente_nome"])


@router.post("/documenti/upload-massivo")
async def upload_documenti_massivo(files: List[UploadFile] = File(...)):
    """Carica più documenti insieme: per ognuno riconosce il tipo (UNILAV, C.U., contratto,
    bonifico, codice fiscale…), trova il dipendente dal codice fiscale (o dal nome) nel testo,
    e lo archivia nella sua cartella. Anti-duplicati per hash del file."""
    import io
    db = get_db()
    indici = await _indici_dipendenti(db)

    import zipfile
    caricati, duplicati, non_assegnati, per_categoria = [], [], [], {}

    async def processa(filename, raw, contesto=""):
        esito, categoria, nome = await _archivia_documento_cloud(db, filename, raw, contesto=contesto, indici=indici)
        if esito == "duplicato":
            duplicati.append(filename)
        elif esito in ("caricato", "non_assegnato"):
            per_categoria[categoria] = per_categoria.get(categoria, 0) + 1
            (caricati if esito == "caricato" else non_assegnati).append({"file": filename, "categoria": categoria, "dipendente": nome})

    for f in files:
        raw = await f.read()
        fn = f.filename or ""
        if fn.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                    for nm in zf.namelist():
                        if nm.endswith("/"):
                            continue
                        await processa(nm.split("/")[-1], zf.read(nm), contesto=fn)
            except zipfile.BadZipFile:
                non_assegnati.append({"file": fn, "categoria": "ALTRO"})
        else:
            await processa(fn, raw, contesto="")
    return {"caricati": len(caricati), "duplicati": duplicati,
            "non_assegnati": non_assegnati, "per_categoria": per_categoria,
            "dettaglio": caricati[:300]}


@router.get("/documenti/{documento_id}/file")
async def download_documento(documento_id: str):
    from fastapi.responses import Response
    doc = await get_db().documenti_cloud.find_one({"id": documento_id}, {"_id": 0})
    if not doc or not doc.get("file_data"):
        raise HTTPException(status_code=404, detail="File non disponibile")
    data = base64.b64decode(doc["file_data"])
    fn = doc.get("filename") or "documento.pdf"
    media = "application/pdf" if fn.lower().endswith(".pdf") else "application/octet-stream"
    return Response(content=data, media_type=media, headers={"Content-Disposition": f'inline; filename="{fn}"'})

# ============ DASHBOARD STATS ============

@router.get("/dashboard/stats")
async def get_dashboard_stats():
    dipendenti = await get_db().dipendenti.find({"merged_into": {"$exists": False}}, {"_id": 0, "pdf_data": 0}).to_list(1000)
    attivi = [d for d in dipendenti if stato_rapporto.e_in_forza(d)]

    ferie_pending = await get_db().ferie_cloud.count_documents({"stato": "in_attesa"})
    missioni_pending = await get_db().missioni_cloud.count_documents({"stato": "in_attesa"})
    
    # Presenze oggi
    today = datetime.now().strftime("%Y-%m-%d")
    presenze_oggi = await get_db().presenze_cloud.count_documents({"data": today, "stato": "presente"})

    # Solo alert HR: la collezione `alerts` è condivisa con l'ERP contabile, qui
    # mostriamo soltanto i moduli del personale (niente fatture/fornitori/banca…).
    alert_aperti = await get_db().alerts.count_documents(
        {"stato": "aperto", "modulo": {"$in": MODULI_HR}})

    # Buste in attesa di pagamento (motore unico): busta presente ma non ancora pagata
    # "In attesa" = anno corrente (da pagare davvero); le buste storiche con
    # bonifico non agganciato sono contate a parte (vedi /paghe/in-attesa).
    buste_attesa = 0
    importo_attesa = 0.0
    buste_storiche = 0
    importo_storico = 0.0
    anno_corrente = datetime.now().year
    async for p in get_db().paghe_mensili.find(
            {"stato_pagamento": {"$in": list(STATI_PAGA_APERTI)}},
            {"_id": 0, "saldo": 1, "importo_busta": 1, "bonifico_importo": 1, "anno": 1}):
        saldo = p.get("saldo")
        if saldo is None:
            saldo = float(p.get("importo_busta") or 0) - float(p.get("bonifico_importo") or 0)
        if saldo and saldo > 0:   # al centesimo, nessuna tolleranza
            if int(p.get("anno") or 0) >= anno_corrente:
                buste_attesa += 1
                importo_attesa += saldo
            else:
                buste_storiche += 1
                importo_storico += saldo

    return {
        "totale_dipendenti": len(dipendenti),
        "dipendenti_attivi": len(attivi),
        "ferie_in_attesa": ferie_pending,
        "missioni_in_attesa": missioni_pending,
        "presenze_oggi": presenze_oggi,
        "alert_aperti": alert_aperti,
        "buste_in_attesa": buste_attesa,
        "importo_in_attesa": round(importo_attesa, 2),
        "buste_storiche_non_agganciate": buste_storiche,
        "importo_storico_non_agganciato": round(importo_storico, 2),
    }


# Moduli di competenza HR (gli altri appartengono all'ERP contabile OpenClaw).
MODULI_HR = ["dipendenti", "cedolini"]

# ID interni (UUID) dentro i messaggi degli alert: vanno tradotti in testo
# leggibile per il titolare (data, importo e descrizione del movimento banca).
_UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def _data_it(iso: str) -> str:
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return iso or "?"


async def _uuid_in_testo_leggibile(mov_id: str) -> Optional[str]:
    """Se l'UUID corrisponde a un movimento bancario, ritorna «descrizione»
    con data e importo; altrimenti None (l'ID resta com'è)."""
    for coll, campo_desc in (("estratto_conto_movimenti", "descrizione_originale"),
                             ("prima_nota_banca", "descrizione")):
        m = await get_db()[coll].find_one({"id": mov_id}, {"_id": 0})
        if m:
            desc = (m.get(campo_desc) or m.get("descrizione") or "").strip()
            importo = m.get("importo")
            pezzi = [f"bancario del {_data_it(m.get('data', ''))}"]
            if importo is not None:
                pezzi.append(f"di € {abs(float(importo)):.2f}")
            if desc:
                pezzi.append(f"«{desc[:120]}»")
            return " ".join(pezzi)
    return None


async def _messaggio_leggibile(messaggio: str) -> str:
    """Sostituisce gli UUID nel messaggio con i dati veri del movimento banca."""
    if not messaggio:
        return messaggio
    for mov_id in set(_UUID_RE.findall(messaggio)):
        leggibile = await _uuid_in_testo_leggibile(mov_id)
        if leggibile:
            messaggio = messaggio.replace(mov_id, leggibile)
    return messaggio


@router.get("/alerts")
async def lista_alert(modulo: str = "", severita: str = "", stato: str = "aperto"):
    """Elenco degli alert HR (scadenze contratti/prova, contestazioni…).
    La collezione `alerts` è condivisa con la contabilità: qui filtriamo ai soli
    moduli del personale. `stato`: 'aperto' (default), 'risolto' (archivio),
    'tutti' (entrambi). Gli alert risolti NON vengono cancellati: restano in archivio."""
    q = {}
    if stato and stato != "tutti":
        q["stato"] = stato
    if modulo:
        if modulo not in MODULI_HR:
            return {"totale": 0, "alerts": []}
        q["modulo"] = modulo
    else:
        q["modulo"] = {"$in": MODULI_HR}
    if severita:
        q["severita"] = severita
    sort_field = "resolved_at" if stato == "risolto" else "created_at"
    alerts = await get_db().alerts.find(q, {"_id": 0}).sort(sort_field, -1).to_list(500)
    # Traduzione a lettura: anche gli alert vecchi già salvati con l'ID interno
    # diventano leggibili, senza toccare il dato in archivio.
    for a in alerts:
        try:
            a["messaggio"] = await _messaggio_leggibile(a.get("messaggio", ""))
        except Exception:
            pass
    return {"totale": len(alerts), "alerts": alerts}


@router.post("/alerts/{alert_id}/risolvi")
async def risolvi_alert_id(alert_id: str):
    """Segna un alert come risolto (manuale)."""
    r = await get_db().alerts.update_one(
        {"id": alert_id, "stato": "aperto"},
        {"$set": {"stato": "risolto", "risolto": True,
                  "resolved_at": now_iso(), "resolved_by": "admin"}})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Alert non trovato o già risolto")
    return {"ok": True, "stato": "risolto"}

# ============ SEED DATA ============

@router.post("/seed-data")
async def seed_data():
    """Crea dati di esempio se non esistono"""
    existing = await get_db().dipendenti_cloud.count_documents({})
    if existing > 0:
        return {"message": "Dati già presenti"}
    
    # Crea dipendenti di esempio
    dipendenti_sample = [
        {"nome": "Mario", "cognome": "Rossi", "ruolo": "Responsabile", "stato": "attivo", "contratto": "Indeterminato"},
        {"nome": "Lucia", "cognome": "Bianchi", "ruolo": "Cameriere", "stato": "attivo", "contratto": "Determinato"},
        {"nome": "Giuseppe", "cognome": "Verdi", "ruolo": "Barista", "stato": "attivo", "contratto": "Indeterminato"},
    ]
    
    for d in dipendenti_sample:
        d["id"] = generate_id()
        d["created_at"] = now_iso()
        await get_db().dipendenti_cloud.insert_one(d)
    
    # Crea turni di esempio
    turni_sample = [
        {"nome": "Mattina", "orario_inizio": "06:00", "orario_fine": "14:00", "colore": "#3b82f6"},
        {"nome": "Pomeriggio", "orario_inizio": "14:00", "orario_fine": "22:00", "colore": "#10b981"},
        {"nome": "Notte", "orario_inizio": "22:00", "orario_fine": "06:00", "colore": "#8b5cf6"},
    ]
    
    for t in turni_sample:
        t["id"] = generate_id()
        await get_db().turni_cloud.insert_one(t)
    
    return {"message": "Dati di esempio creati"}
