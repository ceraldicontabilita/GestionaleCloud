"""
Documenti Module - Monitor email e sync.
"""
from fastapi import Query
from typing import Dict, Any

from app.database import Database
from app.services.email_monitor_service import (
    start_monitor, stop_monitor, get_monitor_status, run_full_sync
)


async def avvia_monitor(
    intervallo_minuti: int = Query(10, ge=1, le=60)
) -> Dict[str, Any]:
    """Avvia il monitoraggio automatico della posta."""
    db = Database.get_db()
    intervallo_secondi = intervallo_minuti * 60
    
    started = start_monitor(db, intervallo_secondi)
    
    return {
        "success": started,
        "message": f"Monitor avviato (ogni {intervallo_minuti} minuti)" if started else "Monitor già in esecuzione",
        "status": get_monitor_status()
    }


async def ferma_monitor() -> Dict[str, Any]:
    """Ferma il monitoraggio automatico della posta."""
    stopped = stop_monitor()
    return {
        "success": stopped,
        "message": "Monitor fermato" if stopped else "Monitor non era in esecuzione"
    }


async def stato_monitor() -> Dict[str, Any]:
    """Stato del monitor email."""
    status = get_monitor_status()
    return {
        "running": status.get("running", False),
        "last_check": status.get("last_check"),
        "next_check": status.get("next_check"),
        "interval_seconds": status.get("interval_seconds"),
        "errors": status.get("errors", [])
    }


async def sync_immediato() -> Dict[str, Any]:
    """Esegue un sync immediato."""
    db = Database.get_db()
    
    result = await run_full_sync(db)
    return {
        "success": True,
        "message": "Sync completato",
        "result": result
    }


async def telegram_status() -> Dict[str, Any]:
    """Stato connessione Telegram."""
    return {
        "configured": False,
        "message": "Telegram non configurato"
    }


async def telegram_test() -> Dict[str, Any]:
    """Test invio Telegram."""
    return {
        "success": False,
        "message": "Telegram non configurato"
    }


async def get_ultimo_sync() -> Dict[str, Any]:
    """Ultimo sync email eseguito."""
    db = Database.get_db()
    
    ultimo = await db.email_sync_status.find_one(
        {"tipo": "email_download"},
        sort=[("timestamp", -1)]
    )
    
    if not ultimo:
        return {"ultimo_sync": None, "message": "Nessun sync eseguito"}
    
    return {
        "ultimo_sync": ultimo.get("timestamp"),
        "documenti_scaricati": ultimo.get("documenti_scaricati", 0),
        "errori": ultimo.get("errori", 0),
        "durata_secondi": ultimo.get("durata_secondi")
    }


async def get_cartelle_email() -> Dict[str, Any]:
    """Lista cartelle email disponibili."""
    return {
        "cartelle": [
            {"nome": "INBOX", "descrizione": "Posta in arrivo"},
            {"nome": "Fatture", "descrizione": "Fatture ricevute"},
            {"nome": "F24", "descrizione": "Modelli F24"},
            {"nome": "Estratti", "descrizione": "Estratti conto"}
        ],
        "cartella_default": "INBOX"
    }
