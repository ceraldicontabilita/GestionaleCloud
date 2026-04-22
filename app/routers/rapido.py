"""
Inserimento Rapido — endpoint per operazioni quick-entry dalla pagina InserimentoRapido.
"""
from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any
from datetime import datetime, timezone
import uuid
import logging

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/dipendenti-attivi")
async def dipendenti_attivi() -> list:
    db = Database.get_db()
    dips = await db["dipendenti"].find(
        {"$or": [{"attivo": True}, {"attivo": {"$exists": False}}], "merged_into": {"$exists": False}},
        {"_id": 0, "id": 1, "nome_completo": 1, "nome": 1, "cognome": 1}
    ).sort("nome_completo", 1).to_list(200)
    return dips


@router.get("/ultimi-inserimenti")
async def ultimi_inserimenti(limit: int = 5) -> list:
    db = Database.get_db()
    recenti = await db["prima_nota_cassa"].find(
        {"source": {"$regex": "rapido"}},
        {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return recenti


@router.post("/corrispettivo")
async def rapido_corrispettivo(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    db = Database.get_db()
    importo = float(data.get("importo", 0))
    if importo <= 0:
        raise HTTPException(status_code=400, detail="Importo deve essere > 0")

    mov_id = str(uuid.uuid4())
    movimento = {
        "id": mov_id,
        "data": data.get("data", datetime.now().strftime("%Y-%m-%d")),
        "tipo": "entrata",
        "importo": importo,
        "descrizione": data.get("descrizione", f"Corrispettivo rapido {data.get('data', '')}"),
        "categoria": "Corrispettivi",
        "source": "rapido_corrispettivo",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db["prima_nota_cassa"].insert_one(movimento)
    return {"success": True, "id": mov_id, "message": "Corrispettivo registrato in cassa"}


@router.post("/versamento-banca")
async def rapido_versamento(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    db = Database.get_db()
    importo = float(data.get("importo", 0))
    if importo <= 0:
        raise HTTPException(status_code=400, detail="Importo deve essere > 0")

    mov_id = str(uuid.uuid4())
    # Uscita cassa
    await db["prima_nota_cassa"].insert_one({
        "id": mov_id,
        "data": data.get("data", datetime.now().strftime("%Y-%m-%d")),
        "tipo": "uscita", "importo": importo,
        "descrizione": data.get("descrizione", "Versamento in banca"),
        "categoria": "Versamento", "source": "rapido_versamento",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    return {"success": True, "id": mov_id, "message": "Versamento registrato"}


@router.post("/apporto-soci")
async def rapido_apporto(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    db = Database.get_db()
    importo = float(data.get("importo", 0))
    if importo <= 0:
        raise HTTPException(status_code=400, detail="Importo deve essere > 0")

    mov_id = str(uuid.uuid4())
    await db["prima_nota_cassa"].insert_one({
        "id": mov_id,
        "data": data.get("data", datetime.now().strftime("%Y-%m-%d")),
        "tipo": "entrata", "importo": importo,
        "descrizione": data.get("descrizione", "Finanziamento soci"),
        "categoria": "Finanziamento soci", "source": "rapido_apporto_soci",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    return {"success": True, "id": mov_id, "message": "Apporto soci registrato"}


@router.post("/paga-fattura")
async def rapido_paga_fattura(
    invoice_id: str = "", metodo_pagamento: str = "cassa", importo: float = 0
) -> Dict[str, Any]:
    db = Database.get_db()
    if not invoice_id:
        raise HTTPException(status_code=400, detail="invoice_id richiesto")

    fattura = await db["invoices"].find_one({"id": invoice_id}, {"_id": 0})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")

    imp = importo or float(fattura.get("total_amount", 0) or fattura.get("importo_totale", 0) or 0)
    collection = "prima_nota_cassa" if metodo_pagamento == "cassa" else "prima_nota_banca"

    # Anti-duplicato
    existing = await db[collection].find_one({"fattura_id": invoice_id})
    if existing:
        return {"success": True, "message": "Già pagata", "movimento_id": existing.get("id")}

    mov_id = str(uuid.uuid4())
    await db[collection].insert_one({
        "id": mov_id, "data": datetime.now().strftime("%Y-%m-%d"),
        "tipo": "uscita", "importo": abs(imp),
        "descrizione": f"Pagamento fattura {fattura.get('invoice_number', '')}",
        "categoria": "fornitori", "fattura_id": invoice_id,
        "source": "rapido_paga_fattura",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    await db["invoices"].update_one({"id": invoice_id}, {"$set": {"pagato": True, "stato_pagamento": "pagata"}})
    return {"success": True, "id": mov_id, "message": f"Fattura pagata ({metodo_pagamento})"}


@router.post("/acconto-dipendente")
async def rapido_acconto(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    db = Database.get_db()
    importo = float(data.get("importo", 0))
    dip_id = data.get("dipendente_id", "")
    if importo <= 0 or not dip_id:
        raise HTTPException(status_code=400, detail="dipendente_id e importo richiesti")

    mov_id = str(uuid.uuid4())
    await db["prima_nota_cassa"].insert_one({
        "id": mov_id, "data": data.get("data", datetime.now().strftime("%Y-%m-%d")),
        "tipo": "uscita", "importo": importo,
        "descrizione": f"Acconto a dipendente {data.get('nome', '')}",
        "categoria": "Acconti dipendenti", "dipendente_id": dip_id,
        "source": "rapido_acconto",
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    return {"success": True, "id": mov_id, "message": "Acconto registrato"}


@router.post("/presenza")
async def rapido_presenza(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    db = Database.get_db()
    dip_id = data.get("dipendente_id", "")
    if not dip_id:
        raise HTTPException(status_code=400, detail="dipendente_id richiesto")

    doc = {
        "id": str(uuid.uuid4()),
        "dipendente_id": dip_id,
        "data": data.get("data", datetime.now().strftime("%Y-%m-%d")),
        "tipo": data.get("tipo", "presente"),
        "ore": float(data.get("ore", 8)),
        "note": data.get("note", ""),
        "source": "rapido",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db["presenze_giornaliere"].insert_one(doc)
    return {"success": True, "id": doc["id"], "message": "Presenza registrata"}
