"""
Router Attrezzature — gestione dinamica di frigoriferi e congelatori.

GET  /api/attrezzature/                      — lista unificata (legge da config o defaults HACCP)
GET  /api/attrezzature/frigo                 — solo frigoriferi
GET  /api/attrezzature/congelatori           — solo congelatori

POST /api/attrezzature/frigo                 — aggiunge nuovo frigorifero
POST /api/attrezzature/congelatore           — aggiunge nuovo congelatore

PUT  /api/attrezzature/frigo/{numero}/rinomina    — rinomina frigorifero
PUT  /api/attrezzature/congelatore/{numero}/rinomina — rinomina congelatore

DELETE /api/attrezzature/frigo/{numero}      — elimina frigorifero
DELETE /api/attrezzature/congelatore/{numero} — elimina congelatore

I nomi personalizzati vengono salvati nella collection `attrezzature_config`:
  { tipo: "frigo"|"congelatore", numero: int, nome: str, attivo: bool }

Questi nomi vengono propagati automaticamente ai dropdown di:
  - SchedaProdottoView (Calcolatore)
  - LottiList (form nuovo lotto)
  - TemperaturePositiveView / TemperatureNegativeView (colonne tabella)
"""
from fastapi import APIRouter, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel
from datetime import datetime, timezone
from pathlib import Path
import os


router = APIRouter(prefix="/attrezzature", tags=["Attrezzature"])

_client = AsyncIOMotorClient(os.environ.get('MONGO_URL'))
db = _client[os.environ.get('DB_NAME', 'test_database')]

# ─── Modello ──────────────────────────────────────────────────────────────────
class NuovaAttrezzatura(BaseModel):
    nome: str
    numero: int | None = None  # se None, viene auto-assegnato

# ─── Helper ───────────────────────────────────────────────────────────────────
async def _get_config(tipo: str) -> list[dict]:
    """Legge la config dalla collection dedicata, ordinata per numero."""
    docs = await db.attrezzature_config.find(
        {"tipo": tipo, "attivo": {"$ne": False}},
        {"_id": 0}
    ).sort("numero", 1).to_list(50)
    return docs


async def _next_numero(tipo: str) -> int:
    """Calcola il prossimo numero disponibile per il tipo indicato."""
    docs = await db.attrezzature_config.find(
        {"tipo": tipo, "attivo": {"$ne": False}},
        {"_id": 0, "numero": 1}
    ).to_list(50)
    usati = {d["numero"] for d in docs}
    n = 1
    while n in usati:
        n += 1
    return n


def _label_default(tipo: str, numero: int) -> str:
    return f"Frigorifero N°{numero}" if tipo == "frigo" else f"Congelatore N°{numero}"


async def _build_list(tipo: str, fallback_tipo: str) -> list[dict]:
    """
    Restituisce la lista degli elementi del tipo indicato.
    Se non ci sono record personalizzati, genera defaults dai documenti HACCP.
    In ogni caso, aggiunge automaticamente tutti i numeri presenti in HACCP
    che non siano già nella config (sync automatico).
    """
    # Sync automatico: importa da HACCP quelli non ancora in config
    coll = db.temperature_positive if tipo == "frigo" else db.temperature_negative
    campo_num = "frigorifero_numero" if tipo == "frigo" else "congelatore_numero"
    campo_nome = "frigorifero_nome" if tipo == "frigo" else "congelatore_nome"
    haccp_docs = await coll.find({}, {"_id": 0, campo_num: 1, campo_nome: 1}).to_list(200)
    haccp_numeri = {}
    for d in haccp_docs:
        n = d.get(campo_num)
        if n and n not in haccp_numeri:
            haccp_numeri[n] = d.get(campo_nome) or _label_default(tipo, n)

    existing = await db.attrezzature_config.find({"tipo": tipo}, {"_id": 0, "numero": 1}).to_list(50)
    existing_numeri = {d["numero"] for d in existing}
    for n, nome in haccp_numeri.items():
        if n not in existing_numeri:
            await db.attrezzature_config.insert_one({
                "tipo": tipo, "numero": n, "nome": nome, "attivo": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            })

    docs = await _get_config(tipo)
    if docs:
        return [{"tipo": tipo, "numero": d["numero"], "nome": d["nome"], "label": d["nome"]} for d in docs]

    # Fallback finale se nessuna config
    numeri = sorted(haccp_numeri.keys()) or list(range(1, 3))
    return [{"tipo": tipo, "numero": n, "nome": _label_default(tipo, n), "label": _label_default(tipo, n)} for n in numeri]


# ─── GET principale ───────────────────────────────────────────────────────────
@router.get("/")
async def get_attrezzature():
    """Restituisce lista unificata frigoriferi + congelatori."""
    frigoriferi = await _build_list("frigo", "frigo")
    congelatori = await _build_list("congelatore", "congelatore")
    return {
        "frigoriferi": frigoriferi,
        "congelatori": congelatori,
        "tutti": frigoriferi + congelatori
    }


@router.get("/frigo")
async def get_frigoriferi():
    return await _build_list("frigo", "frigo")


@router.get("/congelatori")
async def get_congelatori():
    return await _build_list("congelatore", "congelatore")


# ─── AGGIUNGI ─────────────────────────────────────────────────────────────────
@router.post("/frigo")
async def aggiungi_frigo(body: NuovaAttrezzatura):
    """Aggiunge un nuovo frigorifero. Il numero viene auto-assegnato se non indicato."""
    numero = body.numero or await _next_numero("frigo")
    # Verifica duplicati
    existing = await db.attrezzature_config.find_one({"tipo": "frigo", "numero": numero, "attivo": {"$ne": False}})
    if existing:
        raise HTTPException(400, f"Frigorifero N°{numero} esiste già")
    nome = body.nome.strip() or f"Frigorifero N°{numero}"
    await db.attrezzature_config.insert_one({
        "tipo": "frigo", "numero": numero, "nome": nome, "attivo": True,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    return {"success": True, "tipo": "frigo", "numero": numero, "nome": nome}


@router.post("/congelatore")
async def aggiungi_congelatore(body: NuovaAttrezzatura):
    """Aggiunge un nuovo congelatore."""
    numero = body.numero or await _next_numero("congelatore")
    existing = await db.attrezzature_config.find_one({"tipo": "congelatore", "numero": numero, "attivo": {"$ne": False}})
    if existing:
        raise HTTPException(400, f"Congelatore N°{numero} esiste già")
    nome = body.nome.strip() or f"Congelatore N°{numero}"
    await db.attrezzature_config.insert_one({
        "tipo": "congelatore", "numero": numero, "nome": nome, "attivo": True,
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    return {"success": True, "tipo": "congelatore", "numero": numero, "nome": nome}


# ─── RINOMINA ─────────────────────────────────────────────────────────────────
@router.put("/frigo/{numero}/rinomina")
async def rinomina_frigo(numero: int, nome: str = Query(...)):
    """Rinomina un frigorifero (anche in temperature_positive per retrocompatibilità)."""
    nome = nome.strip()
    if not nome:
        raise HTTPException(400, "Il nome non può essere vuoto")
    await db.attrezzature_config.update_one(
        {"tipo": "frigo", "numero": numero},
        {"$set": {"nome": nome, "attivo": True, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    # Aggiorna anche i documenti HACCP per retrocompatibilità
    await db.temperature_positive.update_many(
        {"frigorifero_numero": numero},
        {"$set": {"frigorifero_nome": nome}}
    )
    return {"success": True, "message": f"Frigorifero N°{numero} rinominato in '{nome}'", "numero": numero, "nome": nome}


@router.put("/congelatore/{numero}/rinomina")
async def rinomina_congelatore(numero: int, nome: str = Query(...)):
    """Rinomina un congelatore."""
    nome = nome.strip()
    if not nome:
        raise HTTPException(400, "Il nome non può essere vuoto")
    await db.attrezzature_config.update_one(
        {"tipo": "congelatore", "numero": numero},
        {"$set": {"nome": nome, "attivo": True, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    await db.temperature_negative.update_many(
        {"congelatore_numero": numero},
        {"$set": {"congelatore_nome": nome}}
    )
    return {"success": True, "message": f"Congelatore N°{numero} rinominato in '{nome}'", "numero": numero, "nome": nome}


# ─── ELIMINA ──────────────────────────────────────────────────────────────────
@router.delete("/frigo/{numero}")
async def elimina_frigo(numero: int):
    """
    Elimina un frigorifero dalla lista (soft delete — mette attivo=False).
    I lotti già associati a questo frigo non vengono modificati.
    """
    result = await db.attrezzature_config.update_one(
        {"tipo": "frigo", "numero": numero},
        {"$set": {"attivo": False, "deleted_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        # Il frigo esiste solo come default (HACCP) — lo marchiamo come eliminato
        await db.attrezzature_config.insert_one({
            "tipo": "frigo", "numero": numero,
            "nome": f"Frigorifero N°{numero}", "attivo": False,
            "deleted_at": datetime.now(timezone.utc).isoformat()
        })
    return {"success": True, "message": f"Frigorifero N°{numero} rimosso dalla lista"}


@router.delete("/congelatore/{numero}")
async def elimina_congelatore(numero: int):
    """Elimina un congelatore dalla lista (soft delete)."""
    result = await db.attrezzature_config.update_one(
        {"tipo": "congelatore", "numero": numero},
        {"$set": {"attivo": False, "deleted_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.matched_count == 0:
        await db.attrezzature_config.insert_one({
            "tipo": "congelatore", "numero": numero,
            "nome": f"Congelatore N°{numero}", "attivo": False,
            "deleted_at": datetime.now(timezone.utc).isoformat()
        })
    return {"success": True, "message": f"Congelatore N°{numero} rimosso dalla lista"}
