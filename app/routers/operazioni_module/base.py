"""
Operazioni Module - CRUD base e conferma operazioni.
"""
from fastapi import HTTPException
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import uuid

from app.database import Database
from .common import (
    COL_EMAIL_DOCS, 
    COL_PRIMA_NOTA_BANCA, COL_PRIMA_NOTA_CASSA
)


async def lista_operazioni(
    stato: Optional[str] = None,
    anno: Optional[int] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """Lista operazioni da confermare."""
    db = Database.get_db()
    
    fornitori_cursor = await db["fornitori"].find(
        {"metodo_pagamento": {"$exists": True, "$nin": [None, "", "da_confermare", "cassa_da_confermare"]}},
        {"_id": 0, "partita_iva": 1, "vat_number": 1, "metodo_pagamento": 1}
    ).to_list(10000)
    
    piva_configurate = set()
    for f in fornitori_cursor:
        piva = f.get("partita_iva") or f.get("vat_number")
        if piva:
            piva_configurate.add(piva)
    
    query_fatture = {}
    if anno:
        query_fatture["invoice_date"] = {"$regex": f"^{anno}"}
    
    fatture = await db["invoices"].find(query_fatture, {"_id": 0}).sort("invoice_date", -1).to_list(5000)
    
    operazioni = []
    for f in fatture:
        supplier_vat = f.get("supplier_vat") or f.get("cedente_piva") or ""
        
        if supplier_vat and supplier_vat in piva_configurate:
            continue
        
        operazioni.append({
            "id": f.get("id"),
            "fattura_id": f.get("id"),
            "fornitore": f.get("supplier_name") or f.get("cedente_denominazione") or "N/A",
            "fornitore_piva": supplier_vat,
            "numero_fattura": f.get("invoice_number") or f.get("numero_fattura") or "N/A",
            "data": f.get("invoice_date") or f.get("data_fattura"),
            "importo": float(f.get("total_amount", 0) or f.get("importo_totale", 0) or 0),
            "stato": "da_confermare",
            "anno": int((f.get("invoice_date") or "2000")[:4])
        })
        
        if len(operazioni) >= limit:
            break
    
    totale = len(operazioni)
    totale_importo = sum(op["importo"] for op in operazioni)
    
    anni_count = {}
    for op in operazioni:
        a = op.get("anno")
        if a:
            anni_count[a] = anni_count.get(a, 0) + 1
    
    return {
        "operazioni": operazioni,
        "stats": {
            "totale": totale,
            "da_confermare": totale,
            "confermate": 0,
            "totale_importo_da_confermare": totale_importo,
            "anno_filtro": anno,
            "fornitori_nel_dizionario": len(piva_configurate)
        },
        "stats_per_anno": [{"anno": a, "totale": c, "da_confermare": c} for a, c in sorted(anni_count.items(), reverse=True)]
    }


async def conferma_operazione(
    operazione_id: str,
    metodo_pagamento: str,
    crea_movimento: bool = False,
    crea_scadenza: bool = False
) -> Dict[str, Any]:
    """Conferma una singola operazione."""
    db = Database.get_db()
    
    fattura = await db["invoices"].find_one({"id": operazione_id})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    update_fields = {
        "metodo_pagamento": metodo_pagamento,
        "metodo_pagamento_confermato": True,
        "stato": "confermata",
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db["invoices"].update_one({"id": operazione_id}, {"$set": update_fields})
    
    # Aggiorna anche il fornitore nel dizionario
    supplier_vat = fattura.get("supplier_vat") or fattura.get("cedente_piva")
    if supplier_vat:
        await db["fornitori"].update_one(
            {"partita_iva": supplier_vat},
            {"$set": {
                "metodo_pagamento": metodo_pagamento,
                "metodo_pagamento_predefinito": metodo_pagamento,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }},
            upsert=False
        )
    
    movimento_id = None
    if crea_movimento:
        importo = float(fattura.get("total_amount", 0) or fattura.get("importo_totale", 0) or 0)
        fornitore = fattura.get("supplier_name") or fattura.get("cedente_denominazione") or "Fornitore"
        numero = fattura.get("invoice_number") or fattura.get("numero_fattura") or "N/A"
        
        movimento_id = str(uuid.uuid4())
        movimento = {
            "id": movimento_id,
            "data": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "tipo": "uscita",
            "importo": importo,
            "descrizione": f"Pagamento fattura {numero} - {fornitore}",
            "categoria": "Pagamento fornitore",
            "fattura_id": operazione_id,
            "fornitore": fornitore,
            "provvisorio": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        collection = COL_PRIMA_NOTA_CASSA if metodo_pagamento.lower() in ["cassa", "contanti"] else COL_PRIMA_NOTA_BANCA
        await db[collection].insert_one(movimento.copy())
    
    return {
        "success": True,
        "operazione_id": operazione_id,
        "metodo_pagamento": metodo_pagamento,
        "movimento_creato": movimento_id
    }


async def elimina_operazione(operazione_id: str) -> Dict[str, Any]:
    """Elimina un'operazione/fattura."""
    db = Database.get_db()
    
    result = await db["invoices"].delete_one({"id": operazione_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Operazione non trovata")
    
    return {"success": True, "deleted": operazione_id}


async def lista_aruba_pendenti(
    tipo: Optional[str] = None,
    giorni: int = 30,
    limit: int = 100
) -> Dict[str, Any]:
    """Lista documenti Aruba pendenti."""
    db = Database.get_db()
    
    query = {"processed": {"$ne": True}}
    if tipo:
        query["category"] = tipo
    
    docs = await db[COL_EMAIL_DOCS].find(query, {"_id": 0}).sort("received_date", -1).limit(limit).to_list(limit)
    
    return {
        "pendenti": docs,
        "totale": len(docs)
    }


async def get_fornitore_preferenza(fornitore: str) -> Dict[str, Any]:
    """Ottiene preferenza metodo pagamento per fornitore."""
    db = Database.get_db()
    
    fornitore_doc = await db["fornitori"].find_one(
        {"$or": [
            {"ragione_sociale": {"$regex": fornitore, "$options": "i"}},
            {"denominazione": {"$regex": fornitore, "$options": "i"}},
            {"partita_iva": fornitore}
        ]},
        {"_id": 0}
    )
    
    if not fornitore_doc:
        return {"found": False, "fornitore": fornitore}
    
    return {
        "found": True,
        "fornitore": fornitore_doc.get("ragione_sociale") or fornitore_doc.get("denominazione"),
        "partita_iva": fornitore_doc.get("partita_iva"),
        "metodo_pagamento": fornitore_doc.get("metodo_pagamento"),
        "iban": fornitore_doc.get("iban")
    }


async def check_fattura_esistente(
    fornitore_piva: str,
    numero_fattura: str,
    importo: Optional[float] = None
) -> Dict[str, Any]:
    """Verifica se una fattura esiste già."""
    db = Database.get_db()
    
    query = {
        "$or": [
            {"supplier_vat": fornitore_piva},
            {"cedente_piva": fornitore_piva}
        ],
        "$or": [
            {"invoice_number": numero_fattura},
            {"numero_fattura": numero_fattura}
        ]
    }
    
    fattura = await db["invoices"].find_one(query, {"_id": 0, "id": 1, "invoice_number": 1, "total_amount": 1})
    
    return {
        "exists": fattura is not None,
        "fattura_id": fattura.get("id") if fattura else None,
        "numero": fattura.get("invoice_number") if fattura else None,
        "importo": fattura.get("total_amount") if fattura else None
    }
