"""
Audit Logger — Gestionale Ceraldi Group
=========================================
Logger unificato per ogni cambio di stato nel gestionale.
Registra chi ha fatto cosa, quando e su quale entità.

Utilizzo:
    from app.services.audit_logger import log_evento

    await log_evento(
        modulo="fatture",
        azione="stato_aggiornato",
        entita_id=fattura_id,
        entita_collection="invoices",
        vecchio_stato={"stato": "acquisita"},
        nuovo_stato={"stato": "pagata"},
        fonte="riconciliazione_automatica",
        utente="sistema",
        db=db
    )
"""
import logging
import uuid
from typing import Dict, Any, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

COLL_AUDIT_LOG = "audit_log"


async def log_evento(
    modulo: str,
    azione: str,
    entita_id: str,
    entita_collection: str,
    db,
    vecchio_stato: Optional[Dict[str, Any]] = None,
    nuovo_stato: Optional[Dict[str, Any]] = None,
    fonte: str = "manuale",
    utente: str = "sistema",
    dettaglio: str = "",
    extra: Optional[Dict[str, Any]] = None
) -> str:
    """
    Registra un evento di audit nel log unificato.

    Args:
        modulo: modulo sorgente (fatture, fornitori, f24, cedolini, ...)
        azione: tipo azione (creato, aggiornato, stato_aggiornato, eliminato,
                riconciliato, match_confermato, alert_generato, ...)
        entita_id: id dell'entità coinvolta
        entita_collection: nome foglio Sheets
        db: istanza database Motor
        vecchio_stato: stato prima della modifica (campi rilevanti)
        nuovo_stato: stato dopo la modifica
        fonte: chi/cosa ha generato la modifica
        utente: utente umano o "sistema"
        dettaglio: descrizione leggibile facoltativa
        extra: dati aggiuntivi liberi

    Returns:
        id del record audit creato
    """
    audit_id = f"audit_{uuid.uuid4().hex[:12]}"

    record = {
        "id": audit_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "modulo": modulo,
        "azione": azione,
        "entita_id": entita_id,
        "entita_collection": entita_collection,
        "vecchio_stato": vecchio_stato,
        "nuovo_stato": nuovo_stato,
        "fonte": fonte,
        "utente": utente,
        "dettaglio": dettaglio,
    }

    if extra:
        record["extra"] = extra

    try:
        await db[COLL_AUDIT_LOG].insert_one(record)
    except Exception as e:
        # L'audit log non deve mai bloccare le operazioni principali
        logger.error(f"Errore scrittura audit log: {e}")

    return audit_id


async def log_sicurezza(
    db,
    azione: str,
    dettaglio: str = "",
    utente: str = "sconosciuto",
    ip: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """Scorciatoia per eventi di sicurezza (login, logout, operazioni distruttive).

    azione: es. 'login_ok', 'login_fallito', 'delete_massivo'.
    Non deve mai bloccare il flusso chiamante (best-effort come log_evento).
    """
    dati = dict(extra or {})
    if ip:
        dati["ip"] = ip
    return await log_evento(
        modulo="sicurezza",
        azione=azione,
        entita_id=utente or "sconosciuto",
        entita_collection="auth",
        db=db,
        fonte="auth",
        utente=utente or "sconosciuto",
        dettaglio=dettaglio,
        extra=dati or None,
    )


async def get_storia_entita(
    entita_id: str,
    db,
    limit: int = 50
) -> list:
    """Ritorna la storia completa di un'entità ordinata per tempo."""
    records = await db[COLL_AUDIT_LOG].find(
        {"entita_id": entita_id},
        {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    return records


async def get_audit_per_modulo(
    modulo: str,
    db,
    da: Optional[str] = None,
    a: Optional[str] = None,
    limit: int = 100
) -> list:
    """Ritorna gli audit di un modulo in un periodo."""
    query: Dict[str, Any] = {"modulo": modulo}
    if da or a:
        query["timestamp"] = {}
        if da:
            query["timestamp"]["$gte"] = da
        if a:
            query["timestamp"]["$lte"] = a

    records = await db[COLL_AUDIT_LOG].find(
        query, {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    return records
