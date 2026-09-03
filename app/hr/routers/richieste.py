"""
Richieste dei dipendenti, instradate al destinatario giusto.

  → Luigi (responsabile_turni):  indisponibilita, cambio_turno
  → Enzo  (admin):               acconto_stipendio, acconto_tfr,
                                 anticipo_retribuzione, cambio_mansione,
                                 reclamo, contestazione_busta, ferie_programmate

Una richiesta 'ferie_programmate' approvata dall'admin genera automaticamente
un blocco di indisponibilità per il generatore turni (collegamento ferie→turni).
"""
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Body, Query, Depends, BackgroundTasks

from app.hr.database import Database, Collections
from app.hr.utils.identity import get_identity, require_roles
from app.hr.services.notifiche import crea_notifica

logger = logging.getLogger(__name__)
router = APIRouter()

COLL = "richieste"
COLL_INDISP = "turni_indisponibilita"

# tipo richiesta -> destinatario competente
DESTINATARIO = {
    "indisponibilita": "responsabile_turni",
    "cambio_turno": "responsabile_turni",
    "acconto_stipendio": "admin",
    "acconto_tfr": "admin",
    "anticipo_retribuzione": "admin",
    "cambio_mansione": "admin",
    "reclamo": "admin",
    "contestazione_busta": "admin",
    "ferie_programmate": "admin",
}

# etichette leggibili per avvisi/email
LABEL = {
    "indisponibilita": "Indisponibilità",
    "cambio_turno": "Cambio turno",
    "acconto_stipendio": "Acconto stipendio",
    "acconto_tfr": "Acconto TFR",
    "anticipo_retribuzione": "Anticipo retribuzione",
    "cambio_mansione": "Cambio mansione",
    "reclamo": "Reclamo",
    "contestazione_busta": "Contestazione busta paga",
    "ferie_programmate": "Ferie programmate",
}


def _invia_email_richiesta(nome: str, label: str, doc: Dict[str, Any]) -> None:
    """Avvisa l'azienda via email di una nuova richiesta. Credenziali da
    services/email_smtp.py (punto unico: SMTP_*/PEC_*/GMAIL_APP_PASSWORD)."""
    from app.hr.services.email_smtp import credenziali_smtp, invia_email
    cred = credenziali_smtp()
    dest = os.getenv("REQUEST_NOTIFY_EMAIL") or (cred["user"] if cred else None)
    if not (cred and dest):
        logger.warning("Email richiesta non inviata: email non configurata su Render")
        return
    dati = doc.get("dati") or {}
    righe = "\n".join(f"  {k}: {v}" for k, v in dati.items()) if dati else ""
    corpo = (
        f"Il dipendente {nome} ha inviato una richiesta dal Portale Dipendenti.\n\n"
        f"Tipo: {label}\n"
        f"Dettaglio: {doc.get('dettaglio') or '-'}\n"
        f"{righe}\n\n"
        f"Data: {doc.get('creato_il')}\n\n"
        f"Accedi alla gestione per approvarla o rifiutarla.")
    try:
        invia_email(dest, f"Nuova richiesta dal portale: {label} — {nome}", corpo)
    except Exception as e:
        logger.warning(f"Email richiesta non inviata: {e}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_float(v):
    try:
        return float(str(v).replace("€", "").replace(",", ".").strip())
    except (ValueError, TypeError, AttributeError):
        return None


_TIPO_FERIE = {"ferie_programmate": "Ferie", "permesso": "Permesso",
               "malattia": "Malattia", "rol": "ROL"}


async def _registra_ferie_cloud(db, req: Dict[str, Any], richiesta_id: str):
    """Ferie/permesso approvati dal portale → record in Ferie & Permessi
    (collezione ferie_cloud). Così compaiono sia in Ferie sia, in automatico,
    nel calendario Presenze (che sovrappone già le ferie). Niente doppioni con
    le presenze: il giorno viene derivato dalla logica esistente.
    """
    dati = req.get("dati", {})
    dal, al = dati.get("dal"), dati.get("al") or dati.get("dal")
    if not dal:
        return
    # idempotenza: non duplicare se già registrato per questa richiesta
    if await db["ferie_cloud"].find_one({"richiesta_id": richiesta_id}, {"_id": 1}):
        return
    try:
        d0 = datetime.fromisoformat(str(dal)[:10])
        d1 = datetime.fromisoformat(str(al)[:10])
        giorni = (d1 - d0).days + 1
    except (ValueError, TypeError):
        giorni = 1
    await db["ferie_cloud"].insert_one({
        "id": f"fer_{uuid.uuid4().hex[:12]}",
        "dipendente_id": req["dipendente_id"],
        "tipo": _TIPO_FERIE.get(req["tipo"], "Ferie"),
        "data_inizio": str(dal)[:10],
        "data_fine": str(al)[:10],
        "giorni": max(1, giorni),
        "stato": "approvata",
        "nota": req.get("dettaglio", ""),
        "origine": "portale",
        "richiesta_id": richiesta_id,
        "created_at": _now(),
    })


@router.post("", summary="Crea una richiesta (dipendente)")
async def crea_richiesta(
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any] = Body(..., example={"tipo": "ferie_programmate",
                                                 "dettaglio": "Ferie estive",
                                                 "dati": {"dal": "2026-08-01", "al": "2026-08-10"}}),
    identity: Dict[str, Any] = Depends(get_identity),
):
    tipo = str(payload.get("tipo", "")).strip()
    if tipo not in DESTINATARIO:
        raise HTTPException(400, f"Tipo richiesta non valido: {tipo}")

    db = Database.get_db()
    nome = identity.get("name")
    if not nome:
        dip = await db[Collections.EMPLOYEES].find_one({"id": identity["id"]}, {"nome_completo": 1})
        nome = dip.get("nome_completo", "") if dip else ""

    doc = {
        "id": f"req_{uuid.uuid4().hex[:12]}",
        "dipendente_id": identity["id"],
        "dipendente_nome": nome,
        "tipo": tipo,
        "destinatario": DESTINATARIO[tipo],
        "dettaglio": str(payload.get("dettaglio", "")).strip(),
        "dati": payload.get("dati", {}) or {},
        "stato": "aperta",
        "nota_risposta": None,
        "risolto_da": None,
        "creato_il": _now(),
        "risolto_il": None,
    }
    await db[COLL].insert_one(doc.copy())
    doc.pop("_id", None)

    # Avviso nell'app (visibile al dipendente e all'azienda) + email all'azienda
    label = LABEL.get(tipo, tipo)
    try:
        await crea_notifica(
            db, identity["id"], "richiesta",
            f"Richiesta: {label}",
            f"{nome} · {doc['dettaglio'] or 'in attesa di risposta'}",
            extra={"richiesta_id": doc["id"], "tipo": tipo, "dipendente_nome": nome})
    except Exception:
        logger.exception("notifica richiesta")
    # L'email va in background: _invia_email_richiesta puo' restare bloccata
    # sull'SMTP anche per piu' round-trip (connessione/TLS/auth/invio, ognuno
    # col proprio timeout — un timeout sul socket non e' una scadenza totale,
    # trovato dalla review su questa stessa PR). L'inserimento in DB e' gia'
    # avvenuto sopra: se restasse in `await` qui, un SMTP lento farebbe
    # scadere il timeout scrittura del client (portale mobile) mentre la
    # richiesta e' gia' salvata, inducendo un secondo tentativo duplicato.
    background_tasks.add_task(_invia_email_richiesta, nome, label, doc)
    # Contestazione busta → alert tracciato per l'azienda
    if tipo == "contestazione_busta":
        try:
            from app.hr.services.alert_engine import genera_alert
            await genera_alert("CED_CONTESTATA", doc["id"], "richieste",
                               f"Contestazione busta da {nome}: {doc['dettaglio'] or 's.d.'}",
                               db, extra={"dipendente_id": identity["id"]})
        except Exception:
            logger.exception("alert contestazione")
    return doc


@router.get("/mie", summary="Le mie richieste (dipendente)")
async def mie_richieste(
    stato: Optional[str] = Query(None),
    identity: Dict[str, Any] = Depends(get_identity),
):
    db = Database.get_db()
    q: Dict[str, Any] = {"dipendente_id": identity["id"]}
    if stato:
        q["stato"] = stato
    return await db[COLL].find(q, {"_id": 0}).sort("creato_il", -1).to_list(500)


@router.get("", summary="Richieste in entrata (admin / responsabile_turni)")
async def lista_richieste(
    stato: Optional[str] = Query(None),
    tipo: Optional[str] = Query(None),
    identity: Dict[str, Any] = Depends(require_roles("admin", "responsabile_turni")),
):
    db = Database.get_db()
    q: Dict[str, Any] = {}
    # admin vede tutto; il responsabile turni solo ciò che gli compete
    if identity["role"] == "responsabile_turni":
        q["destinatario"] = "responsabile_turni"
    if stato:
        q["stato"] = stato
    if tipo:
        q["tipo"] = tipo
    return await db[COLL].find(q, {"_id": 0}).sort("creato_il", -1).to_list(1000)


@router.post("/{richiesta_id}/risolvi", summary="Approva/rifiuta una richiesta")
async def risolvi_richiesta(
    richiesta_id: str,
    payload: Dict[str, Any] = Body(..., example={"esito": "approvata", "nota": ""}),
    identity: Dict[str, Any] = Depends(require_roles("admin", "responsabile_turni")),
):
    esito = str(payload.get("esito", "")).strip()
    if esito not in {"approvata", "rifiutata"}:
        raise HTTPException(400, "esito deve essere 'approvata' o 'rifiutata'")

    db = Database.get_db()
    req = await db[COLL].find_one({"id": richiesta_id}, {"_id": 0})
    if not req:
        raise HTTPException(404, "Richiesta non trovata")
    if req["stato"] != "aperta":
        raise HTTPException(409, f"Richiesta già {req['stato']}")
    # competenza: il responsabile turni risolve solo le sue
    if identity["role"] == "responsabile_turni" and req["destinatario"] != "responsabile_turni":
        raise HTTPException(403, "Non di tua competenza")

    await db[COLL].update_one(
        {"id": richiesta_id},
        {"$set": {"stato": esito, "nota_risposta": str(payload.get("nota", "")).strip(),
                  "risolto_da": identity["id"], "risolto_il": _now()}},
    )

    # Collegamento ferie→turni: ferie approvata = indisponibilità automatica
    if esito == "approvata" and req["tipo"] == "ferie_programmate":
        dati = req.get("dati", {})
        dal, al = dati.get("dal"), dati.get("al")
        if dal and al:
            await db[COLL_INDISP].insert_one({
                "id": f"indisp_{uuid.uuid4().hex[:12]}",
                "dipendente_id": req["dipendente_id"],
                "dal": dal, "al": al,
                "origine": "ferie",
                "richiesta_id": richiesta_id,
                "creato_il": _now(),
            })
            logger.info(f"Ferie approvate → indisponibilità {req['dipendente_id']} {dal}..{al}")

    # Indisponibilità inviata e approvata da Luigi = vincolo per il generatore
    if esito == "approvata" and req["tipo"] == "indisponibilita":
        dati = req.get("dati", {})
        dal = dati.get("dal") or dati.get("data")
        al = dati.get("al") or dati.get("data")
        if dal and al:
            await db[COLL_INDISP].insert_one({
                "id": f"indisp_{uuid.uuid4().hex[:12]}",
                "dipendente_id": req["dipendente_id"],
                "dal": dal, "al": al,
                "origine": "indisponibilita",
                "richiesta_id": richiesta_id,
                "creato_il": _now(),
            })

    # Ferie approvata → record in Ferie & Permessi (compare anche nelle Presenze)
    if esito == "approvata" and req["tipo"] == "ferie_programmate":
        try:
            await _registra_ferie_cloud(db, req, richiesta_id)
        except Exception:
            logger.exception("ferie_cloud da richiesta")

    # Acconto/anticipo approvato → partita aperta (tracciamento finanziario)
    if esito == "approvata" and req["tipo"] in ("acconto_stipendio", "acconto_tfr", "anticipo_retribuzione"):
        importo = _to_float(req.get("dati", {}).get("importo"))
        if importo and importo > 0:
            try:
                from app.hr.services.partite_aperte_engine import crea_partita, TipoPartita
                await crea_partita(
                    tipo=TipoPartita.ALTRO, documento_id=richiesta_id,
                    documento_collection="richieste", controparte_id=req["dipendente_id"],
                    controparte_nome=req.get("dipendente_nome", ""), importo=importo, db=db,
                    data_documento=_now()[:10],
                    extra={"tipo_richiesta": req["tipo"], "categoria": "acconto_dipendente"})
            except Exception:
                logger.exception("partita acconto")

    # Notifica al dipendente l'esito
    try:
        await crea_notifica(
            db, req["dipendente_id"], "richiesta_risolta",
            f"Richiesta {req['tipo']}: {esito}",
            (str(payload.get("nota", "")).strip()
             or f"La tua richiesta «{req['tipo']}» è stata {esito}."),
            extra={"richiesta_id": richiesta_id, "tipo": req["tipo"], "esito": esito},
        )
    except Exception:
        pass

    return {"ok": True, "id": richiesta_id, "stato": esito}
