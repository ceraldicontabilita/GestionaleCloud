"""
API Notifiche Scadenze F24 - Endpoint per gestire alert push.

Endpoint:
- GET /api/f24-notifiche/scadenze → scadenze imminenti
- POST /api/f24-notifiche/invia → forza invio notifiche
- GET /api/f24-notifiche/alert → alert attivi (per campanella frontend)
- POST /api/f24-notifiche/alert/{id}/letto → segna alert come letto
- GET /api/f24-notifiche/stats → statistiche notifiche
"""

from fastapi import APIRouter, Query
from typing import Dict, Any
import logging

from app.database import Database
from app.utils.error_handler import handle_errors

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/scadenze")
@handle_errors
async def get_scadenze_imminenti() -> Dict[str, Any]:
    """
    Controlla e restituisce le scadenze F24 imminenti (entro 15 giorni).
    Utile per dashboard e widget.
    """
    from app.services.f24_scadenze_notifiche import controlla_scadenze_f24
    return await controlla_scadenze_f24()


@router.post("/invia")
@handle_errors
async def forza_invio_notifiche() -> Dict[str, Any]:
    """
    Forza l'invio delle notifiche per scadenze F24 imminenti.
    Invia Telegram + Email se configurati.
    """
    from app.services.f24_scadenze_notifiche import invia_notifiche_scadenze
    return await invia_notifiche_scadenze()


@router.get("/alert")
@handle_errors
async def get_alert_attivi(
    solo_non_letti: bool = Query(True, description="Mostra solo alert non letti"),
    limite: int = Query(20, ge=1, le=100)
) -> Dict[str, Any]:
    """
    Restituisce gli alert F24 attivi per il frontend (campanella/badge).
    """
    db = Database.get_db()
    
    query = {"tipo": "SCADENZA_F24"}
    if solo_non_letti:
        query["letto"] = False
    
    alert = await db["alert_scadenze_f24"].find(
        query, {"_id": 0}
    ).sort("giorni_rimanenti", 1).to_list(limite)
    
    # Conta per livello
    conteggi = {}
    for a in alert:
        livello = a.get("livello", "BASSA")
        conteggi[livello] = conteggi.get(livello, 0) + 1
    
    return {
        "alert": alert,
        "totale": len(alert),
        "non_letti": len([a for a in alert if not a.get("letto")]),
        "per_livello": conteggi,
        "importo_totale": round(sum(a.get("importo", 0) for a in alert), 2)
    }


@router.post("/alert/{f24_id}/letto")
@handle_errors
async def segna_alert_letto(f24_id: str) -> Dict[str, Any]:
    """Segna un alert come letto."""
    db = Database.get_db()
    
    from datetime import datetime, timezone
    result = await db["alert_scadenze_f24"].update_one(
        {"f24_id": f24_id, "tipo": "SCADENZA_F24"},
        {"$set": {"letto": True, "letto_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        return {"success": False, "message": "Alert non trovato"}
    
    return {"success": True, "message": "Alert segnato come letto"}


@router.post("/alert/leggi-tutti")
@handle_errors
async def segna_tutti_letti() -> Dict[str, Any]:
    """Segna tutti gli alert come letti."""
    db = Database.get_db()
    
    from datetime import datetime, timezone
    result = await db["alert_scadenze_f24"].update_many(
        {"tipo": "SCADENZA_F24", "letto": False},
        {"$set": {"letto": True, "letto_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    return {
        "success": True,
        "alert_aggiornati": result.modified_count
    }


@router.get("/stats")
@handle_errors
async def get_stats_notifiche() -> Dict[str, Any]:
    """Statistiche sulle notifiche inviate."""
    db = Database.get_db()
    
    totale = await db["alert_scadenze_f24"].count_documents({"tipo": "SCADENZA_F24"})
    non_letti = await db["alert_scadenze_f24"].count_documents({"tipo": "SCADENZA_F24", "letto": False})
    telegram_ok = await db["alert_scadenze_f24"].count_documents({"notificato_telegram": True})
    email_ok = await db["alert_scadenze_f24"].count_documents({"notificato_email": True})
    
    # Prossima scadenza
    prossima = await db["alert_scadenze_f24"].find_one(
        {"tipo": "SCADENZA_F24", "giorni_rimanenti": {"$gte": 0}},
        {"_id": 0},
        sort=[("giorni_rimanenti", 1)]
    )
    
    return {
        "totale_alert": totale,
        "non_letti": non_letti,
        "notifiche_telegram": telegram_ok,
        "notifiche_email": email_ok,
        "prossima_scadenza": {
            "descrizione": prossima.get("descrizione") if prossima else None,
            "data": prossima.get("data_scadenza") if prossima else None,
            "importo": prossima.get("importo") if prossima else None,
            "giorni": prossima.get("giorni_rimanenti") if prossima else None
        } if prossima else None
    }
