"""
API Gestione IVA (SPECIFICA_IVA.md).

Fase 1: attribuzione del periodo IVA per competenza alle fatture di acquisto e
vista "IVA disponibile non ancora utilizzata". Montato sotto /api/iva.
Le liquidazioni persistite e il calcolo mensile anti-duplicazione arrivano
nelle fasi successive.
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query

from app.database import Database
from app.engines import iva_fatture

router = APIRouter()

COLL = "invoices"
# Note di credito: non sono acquisti detraibili in positivo
TIPI_NOTA_CREDITO = ("TD04", "TD08")


@router.post("/ricalcola-attribuzione")
async def ricalcola_attribuzione(
    anno: Optional[int] = Query(None, description="Limita al singolo anno (opzionale)"),
) -> Dict[str, Any]:
    """Ricalcola e salva i campi IVA (periodo attribuito, regola, stato) su
    tutte le fatture. Idempotente: non tocca l'IVA già utilizzata. Serve a
    popolare le fatture ESISTENTI (le nuove vengono arricchite all'import)."""
    db = Database.get_db()
    query: Dict[str, Any] = {}
    if anno:
        query["$or"] = [
            {"invoice_date": {"$regex": f"^{anno}"}},
            {"data_documento": {"$regex": f"^{anno}"}},
        ]

    aggiornate = 0
    esaminate = 0
    async for inv in db[COLL].find(query):
        esaminate += 1
        campi = iva_fatture.campi_iva_da_fattura(inv)
        await db[COLL].update_one({"_id": inv["_id"]}, {"$set": campi})
        aggiornate += 1

    return {"success": True, "esaminate": esaminate, "aggiornate": aggiornate}


@router.get("/fatture")
async def fatture_iva(
    periodo: Optional[str] = Query(None, description="Periodo IVA attribuito, 'YYYY-MM'"),
    anno: Optional[int] = Query(None),
    limit: int = Query(500, le=5000),
) -> Dict[str, Any]:
    """Elenco fatture con i dati IVA (periodo attribuito, regola, stato)."""
    db = Database.get_db()
    query: Dict[str, Any] = {}
    if periodo:
        query["periodo_iva_attribuito"] = periodo
    elif anno:
        query["periodo_iva_attribuito"] = {"$regex": f"^{anno}"}

    proj = {
        "_id": 0, "id": 1, "invoice_number": 1, "supplier_name": 1,
        "data_documento": 1, "data_operazione": 1, "data_ricezione": 1,
        "data_registrazione": 1, "periodo_iva_attribuito": 1,
        "periodo_iva_utilizzato": 1, "regola_iva_applicata": 1,
        "iva": 1, "iva_detraibile": 1, "iva_utilizzata": 1,
        "stato_detrazione_iva": 1, "tipo_documento": 1,
    }
    docs = await db[COLL].find(query, proj).sort("data_documento", -1).to_list(limit)
    return {"fatture": docs, "totale": len(docs)}


@router.get("/fatture/non-utilizzate")
async def fatture_non_utilizzate(
    anno: Optional[int] = Query(None),
    limit: int = Query(1000, le=5000),
) -> Dict[str, Any]:
    """IVA disponibile NON ancora utilizzata (SPECIFICA_IVA.md §14): fatture
    con IVA detraibile > 0 non ancora inserita in alcuna liquidazione."""
    db = Database.get_db()
    query: Dict[str, Any] = {
        "iva_utilizzata": {"$ne": True},
        "tipo_documento": {"$nin": list(TIPI_NOTA_CREDITO)},
    }
    if anno:
        query["periodo_iva_attribuito"] = {"$regex": f"^{anno}"}

    proj = {
        "_id": 0, "id": 1, "invoice_number": 1, "supplier_name": 1,
        "data_documento": 1, "data_ricezione": 1, "periodo_iva_attribuito": 1,
        "regola_iva_applicata": 1, "iva": 1, "iva_detraibile": 1,
        "stato_detrazione_iva": 1,
    }
    docs = await db[COLL].find(query, proj).sort("periodo_iva_attribuito", 1).to_list(limit)
    docs = [d for d in docs if float(d.get("iva_detraibile") or d.get("iva") or 0) > 0]
    totale_iva = round(sum(float(d.get("iva_detraibile") or d.get("iva") or 0) for d in docs), 2)
    return {"fatture": docs, "totale": len(docs), "totale_iva_disponibile": totale_iva}
