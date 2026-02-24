"""
F24 Tributi Router - Gestione modelli F24 e tributi.
Refactored from public_api.py
"""
from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid
import logging

from app.database import Database, Collections

logger = logging.getLogger(__name__)
router = APIRouter()

CODICI_TRIBUTO_F24 = {
    "1001": {"sezione": "erario", "descrizione": "Ritenute su retribuzioni, pensioni, trasferte", "tipo": "misto"},
    "1627": {"sezione": "erario", "descrizione": "Ritenute su redditi lavoro autonomo", "tipo": "misto"},
    "1631": {"sezione": "erario", "descrizione": "Credito d'imposta per ritenute IRPEF", "tipo": "credito"},
    "6001": {"sezione": "erario", "descrizione": "IVA - Versamento mensile Gennaio", "tipo": "debito"},
    "6002": {"sezione": "erario", "descrizione": "IVA - Versamento mensile Febbraio", "tipo": "debito"},
    "6003": {"sezione": "erario", "descrizione": "IVA - Versamento mensile Marzo", "tipo": "debito"},
    "6004": {"sezione": "erario", "descrizione": "IVA - Versamento mensile Aprile", "tipo": "debito"},
    "6005": {"sezione": "erario", "descrizione": "IVA - Versamento mensile Maggio", "tipo": "debito"},
    "6006": {"sezione": "erario", "descrizione": "IVA - Versamento mensile Giugno", "tipo": "debito"},
    "6007": {"sezione": "erario", "descrizione": "IVA - Versamento mensile Luglio", "tipo": "debito"},
    "6008": {"sezione": "erario", "descrizione": "IVA - Versamento mensile Agosto", "tipo": "debito"},
    "6009": {"sezione": "erario", "descrizione": "IVA - Versamento mensile Settembre", "tipo": "debito"},
    "6010": {"sezione": "erario", "descrizione": "IVA - Versamento mensile Ottobre", "tipo": "debito"},
    "6011": {"sezione": "erario", "descrizione": "IVA - Versamento mensile Novembre", "tipo": "debito"},
    "6012": {"sezione": "erario", "descrizione": "IVA - Versamento mensile Dicembre", "tipo": "debito"},
    "6099": {"sezione": "erario", "descrizione": "IVA - Versamento annuale", "tipo": "debito"},
    "5100": {"sezione": "inps", "descrizione": "Contributi INPS lavoratori dipendenti", "tipo": "debito"},
    "3802": {"sezione": "regioni", "descrizione": "Addizionale regionale IRPEF", "tipo": "debito"},
    "3847": {"sezione": "imu", "descrizione": "Addizionale comunale IRPEF - acconto", "tipo": "debito"},
    "3848": {"sezione": "imu", "descrizione": "Addizionale comunale IRPEF - saldo", "tipo": "debito"},
}


@router.get("")
async def list_f24(skip: int = 0, limit: int = 10000) -> List[Dict[str, Any]]:
    """Lista modelli F24."""
    db = Database.get_db()
    return await db[Collections.F24_MODELS].find({}, {"_id": 0}).skip(skip).limit(limit).to_list(limit)


@router.post("")
async def create_f24(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea F24."""
    db = Database.get_db()
    f24 = {
        "id": str(uuid.uuid4()),
        "tipo": data.get("tipo", "F24"),
        "descrizione": data.get("descrizione", ""),
        "importo": float(data.get("importo", 0) or 0),
        "scadenza": data.get("scadenza", ""),
        "periodo_riferimento": data.get("periodo_riferimento", ""),
        "codici_tributo": data.get("codici_tributo", []),
        "sezione": data.get("sezione", "erario"),
        "status": data.get("status", "pending"),
        "notes": data.get("notes", ""),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db[Collections.F24_MODELS].insert_one(f24.copy())
    f24.pop("_id", None)
    return f24


@router.get("/alerts")
async def get_alerts() -> List[Dict[str, Any]]:
    """Alert scadenze F24."""
    db = Database.get_db()
    alerts = []
    today = datetime.now(timezone.utc).date()
    
    f24_list = await db[Collections.F24_MODELS].find({"status": {"$ne": "paid"}}, {"_id": 0}).to_list(1000)
    
    for f24 in f24_list:
        try:
            scadenza_str = f24.get("scadenza") or f24.get("data_versamento")
            if not scadenza_str:
                continue
            
            if isinstance(scadenza_str, str):
                scadenza_str = scadenza_str.replace("Z", "+00:00")
                if "T" in scadenza_str:
                    scadenza = datetime.fromisoformat(scadenza_str).date()
                else:
                    try:
                        scadenza = datetime.strptime(scadenza_str, "%d/%m/%Y").date()
                    except ValueError:
                        scadenza = datetime.strptime(scadenza_str, "%Y-%m-%d").date()
            elif isinstance(scadenza_str, datetime):
                scadenza = scadenza_str.date()
            else:
                continue
            
            giorni = (scadenza - today).days
            
            if giorni < 0:
                severity, msg = "critical", f"⚠️ SCADUTO da {abs(giorni)} giorni!"
            elif giorni == 0:
                severity, msg = "high", "⏰ SCADE OGGI!"
            elif giorni <= 3:
                severity, msg = "high", f"⚡ Scade tra {giorni} giorni"
            elif giorni <= 7:
                severity, msg = "medium", f"📅 Scade tra {giorni} giorni"
            else:
                continue
            
            alerts.append({
                "f24_id": f24.get("id"), "tipo": f24.get("tipo", "F24"),
                "descrizione": f24.get("descrizione", ""), "importo": float(f24.get("importo", 0) or 0),
                "scadenza": scadenza.isoformat(), "giorni_mancanti": giorni,
                "severity": severity, "messaggio": msg
            })
        except Exception as e:
            logger.error(f"Error F24: {e}")
    
    return sorted(alerts, key=lambda x: x["giorni_mancanti"])


@router.get("/dashboard")
async def get_dashboard() -> Dict[str, Any]:
    """Dashboard F24."""
    db = Database.get_db()
    today = datetime.now(timezone.utc).date()
    
    all_f24 = await db[Collections.F24_MODELS].find({}, {"_id": 0}).to_list(10000)
    pagati = [f for f in all_f24 if f.get("status") == "paid"]
    non_pagati = [f for f in all_f24 if f.get("status") != "paid"]
    
    per_codice = {}
    for f24 in all_f24:
        for codice in f24.get("codici_tributo", []):
            cod = codice.get("codice", "ALTRO")
            if cod not in per_codice:
                info = CODICI_TRIBUTO_F24.get(cod, {"descrizione": "Altro"})
                per_codice[cod] = {"codice": cod, "descrizione": info.get("descrizione", ""), "count": 0, "totale": 0, "pagato": 0, "da_pagare": 0}
            per_codice[cod]["count"] += 1
            imp = float(codice.get("importo", 0) or f24.get("importo", 0) or 0)
            per_codice[cod]["totale"] += imp
            if f24.get("status") == "paid":
                per_codice[cod]["pagato"] += imp
            else:
                per_codice[cod]["da_pagare"] += imp
    
    alert_attivi = sum(1 for f24 in non_pagati if _days_to_scadenza(f24.get("scadenza"), today) <= 7)
    
    return {
        "totale_f24": len(all_f24),
        "pagati": {"count": len(pagati), "totale": round(sum(float(f.get("importo", 0) or 0) for f in pagati), 2)},
        "da_pagare": {"count": len(non_pagati), "totale": round(sum(float(f.get("importo", 0) or 0) for f in non_pagati), 2)},
        "alert_attivi": alert_attivi,
        "per_codice_tributo": list(per_codice.values())
    }


def _days_to_scadenza(scadenza_str, today):
    """Calcola giorni alla scadenza."""
    try:
        if not scadenza_str:
            return 999
        if isinstance(scadenza_str, str):
            if "T" in scadenza_str:
                scadenza = datetime.fromisoformat(scadenza_str.replace("Z", "+00:00")).date()
            else:
                try:
                    scadenza = datetime.strptime(scadenza_str, "%d/%m/%Y").date()
                except ValueError:
                    scadenza = datetime.strptime(scadenza_str, "%Y-%m-%d").date()
        elif isinstance(scadenza_str, datetime):
            scadenza = scadenza_str.date()
        else:
            return 999
        return (scadenza - today).days
    except (ValueError, TypeError):
        return 999


@router.get("/codici")
async def get_codici() -> Dict[str, Any]:
    """Codici tributo F24."""
    return {
        "codici": CODICI_TRIBUTO_F24,
        "sezioni": {"erario": "Erario", "inps": "INPS", "regioni": "Regioni", "imu": "IMU e tributi locali"}
    }


@router.post("/{f24_id}/mark-paid")
async def mark_paid(f24_id: str, paid_date: Optional[str] = None) -> Dict[str, Any]:
    """Marca F24 come pagato."""
    db = Database.get_db()
    now = datetime.now(timezone.utc).isoformat()
    
    result = await db[Collections.F24_MODELS].update_one(
        {"id": f24_id},
        {"$set": {"status": "paid", "paid_date": paid_date or now, "updated_at": now}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="F24 non trovato")
    return {"success": True, "message": "F24 marcato come pagato"}


@router.delete("/{f24_id}")
async def delete_f24(f24_id: str) -> Dict[str, Any]:
    """Elimina F24."""
    db = Database.get_db()
    result = await db[Collections.F24_MODELS].delete_one({"id": f24_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="F24 non trovato")
    return {"success": True, "deleted_id": f24_id}
