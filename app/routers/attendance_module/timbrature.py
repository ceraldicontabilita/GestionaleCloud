"""
ATTENDANCE - Timbrature
=======================
Gestione timbrature dipendenti (entrata/uscita/pause).
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any
from datetime import datetime, timezone
import uuid
import logging

from app.database import Database
from .models import TipoTimbratura

logger = logging.getLogger(__name__)
router = APIRouter()


# =============================================================================
# COSTANTI
# =============================================================================

ORE_GIORNALIERE_STANDARD = 8
ORE_SETTIMANALI_STANDARD = 40
PAUSA_PRANZO_MINUTI = 60


# =============================================================================
# ENDPOINTS TIMBRATURE
# =============================================================================

@router.post("/timbratura")
async def registra_timbratura(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Registra una timbratura (entrata, uscita, pausa).
    
    Payload:
    {
        "employee_id": "uuid",
        "tipo": "entrata" | "uscita" | "pausa_inizio" | "pausa_fine",
        "data_ora": "2026-01-21T09:00:00" (opzionale, default: now),
        "note": "Note opzionali",
        "geolocation": {"lat": 41.9, "lng": 12.5} (opzionale)
    }
    """
    db = Database.get_db()
    
    employee_id = payload.get("employee_id")
    tipo = payload.get("tipo", "").lower()
    data_ora_str = payload.get("data_ora")
    note = payload.get("note", "")
    geolocation = payload.get("geolocation")
    
    if not employee_id:
        raise HTTPException(status_code=400, detail="employee_id obbligatorio")
    
    tipi_validi = [t.value for t in TipoTimbratura]
    if tipo not in tipi_validi:
        raise HTTPException(status_code=400, detail=f"tipo deve essere uno di: {tipi_validi}")
    
    # Verifica dipendente esiste
    employee = await db["dipendenti"].find_one({"id": employee_id}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1})
    if not employee:
        raise HTTPException(status_code=404, detail="Dipendente non trovato")
    
    # Data/ora
    if data_ora_str:
        try:
            data_ora = datetime.fromisoformat(data_ora_str.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato data_ora non valido")
    else:
        data_ora = datetime.now(timezone.utc)
    
    data_giorno = data_ora.strftime("%Y-%m-%d")
    
    # Verifica coerenza timbrature
    entrata_oggi = None
    if tipo == TipoTimbratura.USCITA.value:
        entrata_oggi = await db["attendance_timbrature"].find_one({
            "employee_id": employee_id,
            "data": data_giorno,
            "tipo": TipoTimbratura.ENTRATA.value,
            "uscita_id": {"$exists": False}
        })
        if not entrata_oggi:
            logger.warning(f"Uscita senza entrata per {employee_id} il {data_giorno}")
    
    # Crea timbratura
    timbratura_id = str(uuid.uuid4())
    timbratura = {
        "id": timbratura_id,
        "employee_id": employee_id,
        "employee_nome": f"{employee.get('nome', '')} {employee.get('cognome', '')}".strip(),
        "tipo": tipo,
        "data": data_giorno,
        "ora": data_ora.strftime("%H:%M:%S"),
        "data_ora": data_ora.isoformat(),
        "note": note,
        "geolocation": geolocation,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["attendance_timbrature"].insert_one(timbratura.copy())
    
    # Se è uscita, collega all'entrata e calcola ore
    ore_lavorate = None
    if tipo == TipoTimbratura.USCITA.value and entrata_oggi:
        await db["attendance_timbrature"].update_one(
            {"id": entrata_oggi["id"]},
            {"$set": {"uscita_id": timbratura_id}}
        )
        
        try:
            entrata_dt = datetime.fromisoformat(entrata_oggi["data_ora"].replace("Z", "+00:00"))
            delta = data_ora - entrata_dt
            ore_lavorate = round(delta.total_seconds() / 3600, 2)
        except Exception:
            pass
    
    logger.info(f"✅ Timbratura registrata: {employee.get('cognome')} - {tipo} - {data_ora.strftime('%H:%M')}")
    
    return {
        "success": True,
        "timbratura_id": timbratura_id,
        "tipo": tipo,
        "data_ora": data_ora.isoformat(),
        "ore_lavorate": ore_lavorate
    }


@router.get("/timbrature/{employee_id}")
async def get_timbrature_dipendente(
    employee_id: str,
    data_da: str = Query(None),
    data_a: str = Query(None),
    limit: int = Query(100, ge=1, le=1000)
) -> Dict[str, Any]:
    """Recupera le timbrature di un dipendente."""
    db = Database.get_db()
    
    query = {"employee_id": employee_id}
    
    if data_da:
        query["data"] = {"$gte": data_da}
    if data_a:
        if "data" in query:
            query["data"]["$lte"] = data_a
        else:
            query["data"] = {"$lte": data_a}
    
    timbrature = await db["attendance_timbrature"].find(
        query,
        {"_id": 0}
    ).sort("data_ora", -1).limit(limit).to_list(limit)
    
    return {
        "success": True,
        "employee_id": employee_id,
        "totale": len(timbrature),
        "timbrature": timbrature
    }


@router.get("/timbrature-giornaliere")
async def get_timbrature_giornaliere(
    data: str = Query(None, description="Data in formato YYYY-MM-DD")
) -> Dict[str, Any]:
    """Recupera tutte le timbrature di un giorno."""
    db = Database.get_db()
    
    if not data:
        data = datetime.now().strftime("%Y-%m-%d")
    
    timbrature = await db["attendance_timbrature"].find(
        {"data": data},
        {"_id": 0}
    ).sort([("employee_nome", 1), ("data_ora", 1)]).to_list(1000)
    
    # Raggruppa per dipendente
    per_dipendente = {}
    for t in timbrature:
        emp_id = t["employee_id"]
        if emp_id not in per_dipendente:
            per_dipendente[emp_id] = {
                "employee_id": emp_id,
                "employee_nome": t.get("employee_nome", ""),
                "timbrature": []
            }
        per_dipendente[emp_id]["timbrature"].append(t)
    
    return {
        "success": True,
        "data": data,
        "totale_timbrature": len(timbrature),
        "dipendenti": list(per_dipendente.values())
    }


@router.delete("/timbratura/{timbratura_id}")
async def elimina_timbratura(timbratura_id: str) -> Dict[str, Any]:
    """Elimina una timbratura."""
    db = Database.get_db()
    
    result = await db["attendance_timbrature"].delete_one({"id": timbratura_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Timbratura non trovata")
    
    return {"success": True, "message": "Timbratura eliminata"}
