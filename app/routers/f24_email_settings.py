"""
Router Impostazioni Email F24
Gestisce la configurazione dei mittenti e parole chiave per il download automatico F24
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from app.database import Database
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

COLL_EMAIL_SETTINGS = "f24_email_settings"
COLL_SCAN_LOG = "f24_scan_log"


class MittenteConfig(BaseModel):
    email: str
    nome: str
    tipo: str = "commercialista"  # commercialista, consulente_lavoro, altro
    categoria_f24: str = "fiscale"  # fiscale, contributivo, altro
    parole_chiave: List[str] = []
    attivo: bool = True


class EmailSettingsUpdate(BaseModel):
    mittenti: List[MittenteConfig]
    scan_interval_minuti: int = 10
    giorni_indietro: int = 7
    auto_scan_attivo: bool = True


@router.get("/impostazioni")
async def get_impostazioni() -> Dict[str, Any]:
    """Recupera le impostazioni email F24."""
    db = Database.get_db()
    
    settings = await db[COLL_EMAIL_SETTINGS].find_one(
        {"tipo": "f24_settings"},
        {"_id": 0}
    )
    
    if not settings:
        # Impostazioni di default
        settings = {
            "tipo": "f24_settings",
            "mittenti": [
                {
                    "email": "rosaria.marotta@email.it",
                    "nome": "Rosaria Marotta",
                    "tipo": "commercialista",
                    "categoria_f24": "fiscale",
                    "parole_chiave": ["f24", "tributi", "irpef", "iva", "irap"],
                    "attivo": True
                },
                {
                    "email": "grazia.studioferrantini@email.it",
                    "nome": "Grazia Ferrantini",
                    "tipo": "consulente_lavoro",
                    "categoria_f24": "contributivo",
                    "parole_chiave": ["f24", "inps", "inail", "contributi"],
                    "attivo": True
                },
                {
                    "email": "f.ferrantini@email.it",
                    "nome": "F. Ferrantini",
                    "tipo": "consulente_lavoro",
                    "categoria_f24": "contributivo",
                    "parole_chiave": ["f24", "inps", "contributi"],
                    "attivo": True
                }
            ],
            "scan_interval_minuti": 10,
            "giorni_indietro": 7,
            "auto_scan_attivo": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        await db[COLL_EMAIL_SETTINGS].insert_one(settings.copy())
    
    return settings


@router.post("/impostazioni")
async def update_impostazioni(data: EmailSettingsUpdate) -> Dict[str, Any]:
    """Aggiorna le impostazioni email F24."""
    db = Database.get_db()
    
    settings = {
        "tipo": "f24_settings",
        "mittenti": [m.model_dump() for m in data.mittenti],
        "scan_interval_minuti": data.scan_interval_minuti,
        "giorni_indietro": data.giorni_indietro,
        "auto_scan_attivo": data.auto_scan_attivo,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db[COLL_EMAIL_SETTINGS].update_one(
        {"tipo": "f24_settings"},
        {"$set": settings},
        upsert=True
    )
    
    return {"success": True, "message": "Impostazioni aggiornate", "settings": settings}


@router.post("/aggiungi-mittente")
async def aggiungi_mittente(mittente: MittenteConfig) -> Dict[str, Any]:
    """Aggiunge un nuovo mittente alla lista."""
    db = Database.get_db()
    
    settings = await db[COLL_EMAIL_SETTINGS].find_one({"tipo": "f24_settings"})
    
    if not settings:
        settings = {"tipo": "f24_settings", "mittenti": []}
    
    mittenti = settings.get("mittenti", [])
    
    # Verifica se esiste già
    for m in mittenti:
        if m.get("email", "").lower() == mittente.email.lower():
            raise HTTPException(status_code=400, detail="Mittente già esistente")
    
    mittenti.append(mittente.model_dump())
    
    await db[COLL_EMAIL_SETTINGS].update_one(
        {"tipo": "f24_settings"},
        {
            "$set": {
                "mittenti": mittenti,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        },
        upsert=True
    )
    
    return {"success": True, "message": f"Mittente {mittente.email} aggiunto"}


@router.delete("/rimuovi-mittente/{email}")
async def rimuovi_mittente(email: str) -> Dict[str, Any]:
    """Rimuove un mittente dalla lista."""
    db = Database.get_db()
    
    settings = await db[COLL_EMAIL_SETTINGS].find_one({"tipo": "f24_settings"})
    
    if not settings:
        raise HTTPException(status_code=404, detail="Impostazioni non trovate")
    
    mittenti = settings.get("mittenti", [])
    mittenti_filtrati = [m for m in mittenti if m.get("email", "").lower() != email.lower()]
    
    if len(mittenti_filtrati) == len(mittenti):
        raise HTTPException(status_code=404, detail="Mittente non trovato")
    
    await db[COLL_EMAIL_SETTINGS].update_one(
        {"tipo": "f24_settings"},
        {
            "$set": {
                "mittenti": mittenti_filtrati,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {"success": True, "message": f"Mittente {email} rimosso"}


@router.post("/toggle-auto-scan")
async def toggle_auto_scan(attivo: bool) -> Dict[str, Any]:
    """Attiva/disattiva la scansione automatica."""
    db = Database.get_db()
    
    await db[COLL_EMAIL_SETTINGS].update_one(
        {"tipo": "f24_settings"},
        {
            "$set": {
                "auto_scan_attivo": attivo,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        },
        upsert=True
    )
    
    return {"success": True, "auto_scan_attivo": attivo}


@router.get("/log-scansioni")
async def get_log_scansioni(limit: int = 20) -> Dict[str, Any]:
    """Log delle ultime scansioni automatiche."""
    db = Database.get_db()
    
    logs = await db[COLL_SCAN_LOG].find(
        {}, {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    
    return {"logs": logs}


@router.post("/scan-manuale")
async def esegui_scan_manuale() -> Dict[str, Any]:
    """Esegue una scansione manuale immediata."""
    from app.routers.f24.email_f24 import scarica_e_processa
    
    try:
        result = await scarica_e_processa(giorni=7)
        
        # Log della scansione
        db = Database.get_db()
        await db[COLL_SCAN_LOG].insert_one({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tipo": "manuale",
            "risultato": result,
            "success": True
        })
        
        return result
    except Exception as e:
        logger.error(f"Errore scan manuale: {e}")
        
        db = Database.get_db()
        await db[COLL_SCAN_LOG].insert_one({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tipo": "manuale",
            "errore": str(e),
            "success": False
        })
        
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stato-sistema")
async def get_stato_sistema() -> Dict[str, Any]:
    """Restituisce lo stato del sistema di scansione F24."""
    db = Database.get_db()
    
    settings = await db[COLL_EMAIL_SETTINGS].find_one(
        {"tipo": "f24_settings"},
        {"_id": 0}
    )
    
    # Ultima scansione
    ultima_scansione = await db[COLL_SCAN_LOG].find_one(
        {}, {"_id": 0},
        sort=[("timestamp", -1)]
    )
    
    # Conteggi F24
    f24_da_pagare = await db["f24_commercialista"].count_documents({"status": "da_pagare"})
    f24_pagati = await db["f24_commercialista"].count_documents({"status": "pagato"})
    allegati_da_processare = await db["email_allegati"].count_documents({"processato": False})
    
    return {
        "auto_scan_attivo": settings.get("auto_scan_attivo", False) if settings else False,
        "scan_interval_minuti": settings.get("scan_interval_minuti", 10) if settings else 10,
        "mittenti_configurati": len(settings.get("mittenti", [])) if settings else 0,
        "ultima_scansione": ultima_scansione,
        "statistiche": {
            "f24_da_pagare": f24_da_pagare,
            "f24_pagati": f24_pagati,
            "allegati_da_processare": allegati_da_processare
        }
    }
