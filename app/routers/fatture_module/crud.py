"""
Fatture Module - CRUD e Visualizzazione fatture.
"""
from fastapi import HTTPException, Query
from fastapi.responses import HTMLResponse, Response
from typing import Dict, Any, Optional
from datetime import datetime, timezone
import base64
import calendar

from app.database import Database
from .common import COL_FORNITORI, COL_FATTURE_RICEVUTE, COL_DETTAGLIO_RIGHE, COL_ALLEGATI
from .helpers import generate_invoice_html


async def get_archivio_fatture(
    anno: Optional[int] = Query(None),
    mese: Optional[int] = Query(None),
    fornitore_piva: Optional[str] = Query(None),
    fornitore_nome: Optional[str] = Query(None),
    stato: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(default=100, le=500),
    skip: int = Query(default=0)
) -> Dict[str, Any]:
    """Archivio Fatture Ricevute con filtri."""
    db = Database.get_db()
    
    query = {}
    
    if anno:
        # Supporta sia campo 'anno' diretto che filtro per data (diversi formati)
        anno_start = f"{anno}-01-01"
        anno_end = f"{anno}-12-31"
        query["$or"] = [
            {"anno": anno},
            {"data_fattura": {"$gte": anno_start, "$lte": anno_end + "T23:59:59"}},
            {"data_documento": {"$gte": anno_start, "$lte": anno_end + "T23:59:59"}},
            {"invoice_date": {"$gte": anno_start, "$lte": anno_end + "T23:59:59"}},
            {"data_fattura": {"$regex": f"^{anno}-"}},
            {"data_documento": {"$regex": f"^{anno}-"}}
        ]
    
    if mese and anno:
        mese_str = str(mese).zfill(2)
        last_day = calendar.monthrange(anno, mese)[1]
        mese_start = f"{anno}-{mese_str}-01"
        mese_end = f"{anno}-{mese_str}-{last_day:02d}"
        query["$or"] = [
            {"$and": [{"anno": anno}, {"$or": [
                {"data_fattura": {"$regex": f"^{anno}-{mese_str}"}},
                {"data_documento": {"$regex": f"^{anno}-{mese_str}"}}
            ]}]},
            {"data_fattura": {"$gte": mese_start, "$lte": mese_end + "T23:59:59"}},
            {"data_documento": {"$gte": mese_start, "$lte": mese_end + "T23:59:59"}},
            {"invoice_date": {"$gte": mese_start, "$lte": mese_end + "T23:59:59"}}
        ]
    
    if fornitore_piva:
        piva_norm = fornitore_piva.strip().upper()
        if "$or" in query:
            query["$and"] = [{"$or": query.pop("$or")}, {"$or": [{"fornitore_partita_iva": piva_norm}, {"supplier_vat": piva_norm}]}]
        else:
            query["$or"] = [{"fornitore_partita_iva": piva_norm}, {"supplier_vat": piva_norm}]
    
    if fornitore_nome:
        nome_filter = {"$or": [
            {"fornitore_ragione_sociale": {"$regex": fornitore_nome, "$options": "i"}},
            {"supplier_name": {"$regex": fornitore_nome, "$options": "i"}}
        ]}
        if "$and" in query:
            query["$and"].append(nome_filter)
        elif "$or" in query:
            query = {"$and": [{"$or": query.pop("$or")}, nome_filter]}
        else:
            query = nome_filter
    
    if stato:
        stato_filter = {"$or": [{"stato": stato}, {"stato_pagamento": stato}]}
        if "$and" in query:
            query["$and"].append(stato_filter)
        elif query:
            query = {"$and": [query, stato_filter]}
        else:
            query = stato_filter
    
    if search:
        search_filter = {"$or": [
            {"numero_documento": {"$regex": search, "$options": "i"}},
            {"invoice_number": {"$regex": search, "$options": "i"}},
            {"fornitore_ragione_sociale": {"$regex": search, "$options": "i"}},
            {"supplier_name": {"$regex": search, "$options": "i"}}
        ]}
        if "$and" in query:
            query["$and"].append(search_filter)
        elif query:
            query = {"$and": [query, search_filter]}
        else:
            query = search_filter
    
    projection = {
        "_id": 0,
        "id": 1,
        "numero_documento": 1, "invoice_number": 1, "numero_fattura": 1,
        "data_documento": 1, "invoice_date": 1, "data_fattura": 1,
        "importo_totale": 1, "total_amount": 1,
        "imponibile": 1, "iva": 1, "imposta": 1,
        "fornitore_ragione_sociale": 1, "supplier_name": 1, "fornitore_nome": 1,
        "fornitore_partita_iva": 1, "supplier_vat": 1, "fornitore_piva": 1,
        "stato": 1, "stato_pagamento": 1, "status": 1,
        "metodo_pagamento": 1, "metodo_pagamento_effettivo": 1,
        "fornitore_metodo_pagamento": 1,
        "pagato": 1,
        "riconciliato": 1,
        "prima_nota_cassa_id": 1, "prima_nota_banca_id": 1,
        "data_pagamento": 1,
        "has_pdf": 1,
        "created_at": 1,
        "anno": 1
    }
    
    fatture = await db[COL_FATTURE_RICEVUTE].find(query, projection).sort([
        ("data_documento", -1), ("invoice_date", -1), ("data_fattura", -1)
    ]).skip(skip).limit(limit).to_list(limit)
    
    total = await db[COL_FATTURE_RICEVUTE].count_documents(query)
    
    normalized = []
    for f in fatture:
        normalized.append({
            "id": f.get("id") or str(f.get("_id", "")),
            "numero_documento": f.get("numero_documento") or f.get("invoice_number") or f.get("numero_fattura"),
            "data_documento": f.get("data_documento") or f.get("invoice_date") or f.get("data_fattura"),
            "importo_totale": f.get("importo_totale") or f.get("total_amount", 0),
            "fornitore_ragione_sociale": f.get("fornitore_ragione_sociale") or f.get("supplier_name") or f.get("fornitore_nome"),
            "fornitore_partita_iva": f.get("fornitore_partita_iva") or f.get("supplier_vat") or f.get("fornitore_piva"),
            "stato": f.get("stato") or f.get("stato_pagamento", "importata"),
            "metodo_pagamento": f.get("metodo_pagamento"),
            "pagato": f.get("pagato", False),
            "riconciliato": f.get("riconciliato", False),
            "has_pdf": f.get("has_pdf", False),
            "created_at": f.get("created_at"),
            "anno": f.get("anno")
        })
    
    return {"fatture": normalized, "total": total, "limit": limit, "skip": skip}


async def view_fattura_assoinvoice(fattura_id: str) -> HTMLResponse:
    """Visualizza fattura in stile AssoInvoice."""
    from bson import ObjectId
    from bson.errors import InvalidId
    db = Database.get_db()
    
    # Cerca prima per id (UUID), poi per _id (ObjectId)
    fattura = await db[COL_FATTURE_RICEVUTE].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        # Prova con ObjectId
        try:
            fattura = await db[COL_FATTURE_RICEVUTE].find_one({"_id": ObjectId(fattura_id)})
            if fattura:
                fattura_id = fattura.get("id", fattura_id)
                fattura.pop("_id", None)
        except Exception:
            pass
    
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    righe = await db[COL_DETTAGLIO_RIGHE].find({"fattura_id": fattura_id}, {"_id": 0}).to_list(1000)
    
    # Se non ci sono righe in dettaglio_righe, usa le linee dalla fattura stessa
    if not righe and fattura.get("linee"):
        righe = fattura.get("linee", [])
    
    html = generate_invoice_html(fattura, righe)
    return HTMLResponse(content=html)


async def download_pdf_allegato(fattura_id: str, allegato_id: str) -> Response:
    """Download PDF allegato fattura."""
    db = Database.get_db()
    
    allegato = await db[COL_ALLEGATI].find_one({"id": allegato_id, "fattura_id": fattura_id})
    if not allegato:
        raise HTTPException(status_code=404, detail="Allegato non trovato")
    
    try:
        pdf_data = base64.b64decode(allegato["base64_data"])
    except Exception:
        raise HTTPException(status_code=500, detail="Errore decodifica PDF")
    
    filename = allegato.get("nome_file", f"allegato_{allegato_id}.pdf")
    
    return Response(
        content=pdf_data,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


async def get_fattura_dettaglio(fattura_id: str) -> Dict[str, Any]:
    """Dettaglio singola fattura con righe e allegati."""
    db = Database.get_db()
    
    fattura = await db[COL_FATTURE_RICEVUTE].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    righe = await db[COL_DETTAGLIO_RIGHE].find({"fattura_id": fattura_id}, {"_id": 0}).to_list(1000)
    allegati = await db[COL_ALLEGATI].find({"fattura_id": fattura_id}, {"_id": 0, "base64_data": 0}).to_list(10)
    
    return {"fattura": fattura, "righe": righe, "allegati": allegati}


async def update_fattura(fattura_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Aggiorna una fattura."""
    db = Database.get_db()
    
    fattura = await db[COL_FATTURE_RICEVUTE].find_one({"id": fattura_id})
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    update_fields = {}
    for field in ["pagato", "data_pagamento", "metodo_pagamento", "riconciliato", "note"]:
        if field in data:
            update_fields[field] = data[field]
    
    if update_fields:
        update_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db[COL_FATTURE_RICEVUTE].update_one({"id": fattura_id}, {"$set": update_fields})
    
    return {"success": True, "updated": list(update_fields.keys())}


async def get_fornitori(
    search: Optional[str] = Query(None),
    con_fatture: bool = Query(default=False),
    limit: int = Query(default=100, le=500)
) -> Dict[str, Any]:
    """Lista fornitori con filtri."""
    db = Database.get_db()
    
    query = {}
    if search:
        query["$or"] = [
            {"ragione_sociale": {"$regex": search, "$options": "i"}},
            {"partita_iva": {"$regex": search, "$options": "i"}}
        ]
    if con_fatture:
        query["fatture_count"] = {"$gt": 0}
    
    fornitori = await db[COL_FORNITORI].find(query, {"_id": 0}).sort("ragione_sociale", 1).limit(limit).to_list(limit)
    return {"items": fornitori, "total": len(fornitori)}


async def get_statistiche(anno: Optional[int] = Query(None)) -> Dict[str, Any]:
    """Statistiche fatture ricevute."""
    db = Database.get_db()
    
    query = {}
    if anno:
        # Supporta tutti i formati di data e campo anno diretto
        query["$or"] = [
            {"anno": anno},
            {"data_documento": {"$regex": f"^{anno}"}},
            {"invoice_date": {"$regex": f"^{anno}"}},
            {"data_fattura": {"$regex": f"^{anno}"}}
        ]
    
    pipeline = [
        {"$match": query} if query else {"$match": {}},
        {"$group": {
            "_id": None,
            "totale_fatture": {"$sum": 1},
            "importo_totale": {"$sum": {"$ifNull": ["$importo_totale", {"$ifNull": ["$total_amount", 0]}]}},
            "pagate": {"$sum": {"$cond": [{"$eq": ["$pagato", True]}, 1, 0]}},
            "importo_pagato": {"$sum": {"$cond": [{"$eq": ["$pagato", True]}, {"$ifNull": ["$importo_totale", {"$ifNull": ["$total_amount", 0]}]}, 0]}}
        }}
    ]
    
    result = await db[COL_FATTURE_RICEVUTE].aggregate(pipeline).to_list(1)
    stats = result[0] if result else {"totale_fatture": 0, "importo_totale": 0, "pagate": 0, "importo_pagato": 0}
    
    # Rimuovi _id se presente
    stats.pop("_id", None)
    
    stats["da_pagare"] = stats["totale_fatture"] - stats["pagate"]
    stats["importo_da_pagare"] = round(stats["importo_totale"] - stats["importo_pagato"], 2)
    stats["anno"] = anno
    
    # Alias per compatibilità frontend
    stats["totale_importo"] = stats["importo_totale"]
    stats["fornitori_unici"] = 0  # Da calcolare separatamente se necessario
    stats["fatture_anomale"] = 0  # Da calcolare separatamente se necessario
    
    return stats
