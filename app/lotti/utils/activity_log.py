"""Registro attività operatori — log unificato (login/logout/magazzino/produzione).
Scrittura best-effort: non solleva mai, per non bloccare l'operazione principale.
"""
from datetime import datetime, timezone
from app.lotti.db import database as db


async def registra_attivita(operatore_nome, tipo, descrizione, reparto="", extra=None):
    try:
        doc = {
            "operatore": (operatore_nome or "?").strip() or "?",
            "tipo": tipo,            # login | logout | magazzino | produzione
            "descrizione": descrizione,
            "reparto": reparto or "",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            doc.update(extra)
        await db.log_attivita.insert_one(doc)
    except Exception:
        pass
