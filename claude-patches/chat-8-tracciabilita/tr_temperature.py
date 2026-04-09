"""
Router Temperature HACCP — Positive (Frigoriferi) e Negative (Congelatori).
Adattato da tracciabilita/backend/routers/temperature_positive.py e temperature_negative.py
Prefix: /api/tr/temperature-positive e /api/tr/temperature-negative
"""
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
import uuid, random

from app.database import get_database
from app.tr_utils import oggi_iso, get_chiusure_obbligatorie, genera_stati_speciali_random

router = APIRouter(tags=["Tracciabilità - Temperature"])

OPERATORI_DEFAULT = ["Pocci Salvatore", "Vincenzo Ceraldi"]
RIFERIMENTI_NORMATIVI = {
    "reg_852_2004": "Reg. CE 852/2004 - Igiene dei prodotti alimentari",
    "reg_853_2004": "Reg. CE 853/2004 - Norme specifiche alimenti origine animale",
    "dlgs_193_2007": "D.Lgs. 193/2007 - Attuazione direttive CE",
    "reg_2017_625": "Reg. UE 2017/625 - Controlli ufficiali",
}
MESI_IT = ["GENNAIO","FEBBRAIO","MARZO","APRILE","MAGGIO","GIUGNO",
           "LUGLIO","AGOSTO","SETTEMBRE","OTTOBRE","NOVEMBRE","DICEMBRE"]

class AggiornaTemperatureRequest(BaseModel):
    temperature: Dict[str, Dict[str, dict]]
    nome: Optional[str] = None
    operatore: Optional[str] = None

# ── HELPER generico per positive/negative ──────────────────────────────────

async def _get_or_create_scheda(db, collection: str, anno: int, numero: int,
                                  default_nome: str, temp_min: float, temp_max: float) -> dict:
    coll = db[collection]
    scheda = await coll.find_one({"anno": anno, "frigorifero_numero": numero}, {"_id": 0})
    if not scheda:
        scheda = {
            "id": str(uuid.uuid4()), "anno": anno,
            "frigorifero_numero": numero,
            "frigorifero_nome": default_nome,
            "azienda": "Ceraldi Group S.R.L.",
            "indirizzo": "Piazza Carità 14, 80134 Napoli (NA)",
            "piva": "04523831214",
            "temperature": {str(m): {} for m in range(1, 13)},
            "temp_min": temp_min, "temp_max": temp_max,
            "riferimenti_normativi": RIFERIMENTI_NORMATIVI,
            "operatori": OPERATORI_DEFAULT.copy(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await coll.insert_one(scheda)
    if "_id" in scheda:
        del scheda["_id"]
    return scheda

# ══════════════════════════════════════════════════════════════════════════════
#  TEMPERATURE POSITIVE (Frigoriferi) — range 0°C / +4°C
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/temperature-positive")
async def tp_lista(db: AsyncIOMotorDatabase = Depends(get_database)):
    anno = datetime.now().year
    schede = await db["temperature_positive"].find({"anno": anno}, {"_id": 0}).to_list(50)
    return schede

@router.get("/temperature-positive/scheda/{anno}/{frigorifero}")
async def tp_scheda(anno: int, frigorifero: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    return await _get_or_create_scheda(db, "temperature_positive", anno, frigorifero,
                                        f"Frigorifero N°{frigorifero}", 0.0, 4.0)

@router.get("/temperature-positive/schede/{anno}")
async def tp_tutte(anno: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    return [await _get_or_create_scheda(db, "temperature_positive", anno, i,
            f"Frigorifero N°{i}", 0.0, 4.0) for i in range(1, 13)]

@router.post("/temperature-positive/scheda/{anno}/{frigorifero}/registra")
async def tp_registra(anno: int, frigorifero: int, mese: int, giorno: int,
                       temperatura: float = None, operatore: str = Query(default=""),
                       note: str = Query(default=""),
                       db: AsyncIOMotorDatabase = Depends(get_database)):
    scheda = await _get_or_create_scheda(db, "temperature_positive", anno, frigorifero,
                                          f"Frigorifero N°{frigorifero}", 0.0, 4.0)
    mese_str, giorno_str = str(mese), str(giorno)
    if mese_str not in scheda["temperature"]:
        scheda["temperature"][mese_str] = {}
    op = operatore or random.choice(OPERATORI_DEFAULT)
    scheda["temperature"][mese_str][giorno_str] = {
        "temp": temperatura, "operatore": op, "note": note,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()
    allarme = temperatura is not None and (temperatura > scheda["temp_max"] or temperatura < scheda["temp_min"])
    await db["temperature_positive"].update_one(
        {"anno": anno, "frigorifero_numero": frigorifero}, {"$set": scheda})
    return {"success": True, "message": f"Temperatura {temperatura}°C registrata", "allarme": allarme}

@router.put("/temperature-positive/scheda/{anno}/{frigorifero}")
async def tp_aggiorna(anno: int, frigorifero: int, data: AggiornaTemperatureRequest,
                       db: AsyncIOMotorDatabase = Depends(get_database)):
    scheda = await _get_or_create_scheda(db, "temperature_positive", anno, frigorifero,
                                          f"Frigorifero N°{frigorifero}", 0.0, 4.0)
    scheda["temperature"] = data.temperature
    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()
    if data.nome:
        scheda["frigorifero_nome"] = data.nome
    await db["temperature_positive"].update_one(
        {"anno": anno, "frigorifero_numero": frigorifero}, {"$set": scheda})
    return {"success": True, "message": "Scheda aggiornata"}

@router.put("/temperature-positive/scheda/{anno}/{frigorifero}/config")
async def tp_config(anno: int, frigorifero: int, nome: str = None,
                     temp_min: float = None, temp_max: float = None,
                     db: AsyncIOMotorDatabase = Depends(get_database)):
    scheda = await _get_or_create_scheda(db, "temperature_positive", anno, frigorifero,
                                          f"Frigorifero N°{frigorifero}", 0.0, 4.0)
    if nome: scheda["frigorifero_nome"] = nome
    if temp_min is not None: scheda["temp_min"] = temp_min
    if temp_max is not None: scheda["temp_max"] = temp_max
    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db["temperature_positive"].update_one(
        {"anno": anno, "frigorifero_numero": frigorifero}, {"$set": scheda})
    return {"success": True, "message": "Configurazione salvata"}

@router.get("/temperature-positive/allarmi/{anno}")
async def tp_allarmi(anno: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    schede = await db["temperature_positive"].find({"anno": anno}, {"_id": 0}).to_list(100)
    allarmi = []
    for s in schede:
        for mese, giorni in s.get("temperature", {}).items():
            for giorno, rec in giorni.items():
                if isinstance(rec, dict):
                    temp = rec.get("temp")
                    if rec.get("is_chiuso") or rec.get("is_manutenzione") or rec.get("is_non_usato"):
                        continue
                else:
                    temp = rec
                if temp is not None and (temp > s.get("temp_max", 4) or temp < s.get("temp_min", 0)):
                    allarmi.append({"frigorifero": s["frigorifero_numero"],
                                    "nome": s.get("frigorifero_nome", ""), "mese": int(mese),
                                    "giorno": int(giorno), "temperatura": temp,
                                    "range": f"{s.get('temp_min',0)}°C / {s.get('temp_max',4)}°C"})
    return allarmi

# ══════════════════════════════════════════════════════════════════════════════
#  TEMPERATURE NEGATIVE (Congelatori) — range -22°C / -18°C
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/temperature-negative")
async def tn_lista(db: AsyncIOMotorDatabase = Depends(get_database)):
    anno = datetime.now().year
    return await db["temperature_negative"].find({"anno": anno}, {"_id": 0}).to_list(50)

@router.get("/temperature-negative/scheda/{anno}/{congelatore}")
async def tn_scheda(anno: int, congelatore: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    return await _get_or_create_scheda(db, "temperature_negative", anno, congelatore,
                                        f"Congelatore N°{congelatore}", -22.0, -18.0)

@router.get("/temperature-negative/schede/{anno}")
async def tn_tutte(anno: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    return [await _get_or_create_scheda(db, "temperature_negative", anno, i,
            f"Congelatore N°{i}", -22.0, -18.0) for i in range(1, 13)]

@router.post("/temperature-negative/scheda/{anno}/{congelatore}/registra")
async def tn_registra(anno: int, congelatore: int, mese: int, giorno: int,
                       temperatura: float = None, operatore: str = Query(default=""),
                       note: str = Query(default=""),
                       db: AsyncIOMotorDatabase = Depends(get_database)):
    scheda = await _get_or_create_scheda(db, "temperature_negative", anno, congelatore,
                                          f"Congelatore N°{congelatore}", -22.0, -18.0)
    mese_str, giorno_str = str(mese), str(giorno)
    if mese_str not in scheda["temperature"]:
        scheda["temperature"][mese_str] = {}
    op = operatore or random.choice(OPERATORI_DEFAULT)
    scheda["temperature"][mese_str][giorno_str] = {
        "temp": temperatura, "operatore": op, "note": note,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()
    allarme = temperatura is not None and (temperatura > scheda["temp_max"] or temperatura < scheda["temp_min"])
    await db["temperature_negative"].update_one(
        {"anno": anno, "frigorifero_numero": congelatore}, {"$set": scheda})
    return {"success": True, "message": f"Temperatura {temperatura}°C registrata", "allarme": allarme}

@router.put("/temperature-negative/scheda/{anno}/{congelatore}")
async def tn_aggiorna(anno: int, congelatore: int, data: AggiornaTemperatureRequest,
                       db: AsyncIOMotorDatabase = Depends(get_database)):
    scheda = await _get_or_create_scheda(db, "temperature_negative", anno, congelatore,
                                          f"Congelatore N°{congelatore}", -22.0, -18.0)
    scheda["temperature"] = data.temperature
    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()
    if data.nome:
        scheda["frigorifero_nome"] = data.nome
    await db["temperature_negative"].update_one(
        {"anno": anno, "frigorifero_numero": congelatore}, {"$set": scheda})
    return {"success": True, "message": "Scheda aggiornata"}

@router.put("/temperature-negative/scheda/{anno}/{congelatore}/config")
async def tn_config(anno: int, congelatore: int, nome: str = None,
                     temp_min: float = None, temp_max: float = None,
                     db: AsyncIOMotorDatabase = Depends(get_database)):
    scheda = await _get_or_create_scheda(db, "temperature_negative", anno, congelatore,
                                          f"Congelatore N°{congelatore}", -22.0, -18.0)
    if nome: scheda["frigorifero_nome"] = nome
    if temp_min is not None: scheda["temp_min"] = temp_min
    if temp_max is not None: scheda["temp_max"] = temp_max
    scheda["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db["temperature_negative"].update_one(
        {"anno": anno, "frigorifero_numero": congelatore}, {"$set": scheda})
    return {"success": True, "message": "Configurazione salvata"}

@router.get("/temperature-negative/allarmi/{anno}")
async def tn_allarmi(anno: int, db: AsyncIOMotorDatabase = Depends(get_database)):
    schede = await db["temperature_negative"].find({"anno": anno}, {"_id": 0}).to_list(100)
    allarmi = []
    for s in schede:
        for mese, giorni in s.get("temperature", {}).items():
            for giorno, rec in giorni.items():
                if isinstance(rec, dict):
                    temp = rec.get("temp")
                    if rec.get("is_chiuso") or rec.get("is_manutenzione") or rec.get("is_non_usato"):
                        continue
                else:
                    temp = rec
                if temp is not None and (temp > s.get("temp_max", -18) or temp < s.get("temp_min", -22)):
                    allarmi.append({"frigorifero": s["frigorifero_numero"],
                                    "nome": s.get("frigorifero_nome", ""), "mese": int(mese),
                                    "giorno": int(giorno), "temperatura": temp,
                                    "range": f"{s.get('temp_min',-22)}°C / {s.get('temp_max',-18)}°C"})
    return allarmi

# ── Endpoint comuni ────────────────────────────────────────────────────────
@router.get("/temperature/mesi")
async def get_mesi():
    return [{"numero": i+1, "nome": m} for i, m in enumerate(MESI_IT)]

@router.get("/temperature/operatori")
async def get_operatori():
    return {"operatori": OPERATORI_DEFAULT}
