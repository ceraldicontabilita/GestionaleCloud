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
    limit: int = Query(default=100, le=6000),
    skip: int = Query(default=0)
) -> Dict[str, Any]:
    """Archivio Fatture Ricevute — legge da indice_documenti (tipo=fattura_ricevuta)."""
    db = Database.get_db()

    # Filtro base: solo fatture ricevute
    query: dict = {"tipo": "fattura_ricevuta"}

    if anno:
        anno_start = f"{anno}-01-01"
        anno_end = f"{anno}-12-31"
        query["data"] = {"$gte": anno_start, "$lte": anno_end}

    if mese and anno:
        mese_str = str(mese).zfill(2)
        last_day = calendar.monthrange(anno, mese)[1]
        query["data"] = {
            "$gte": f"{anno}-{mese_str}-01",
            "$lte": f"{anno}-{mese_str}-{last_day:02d}"
        }

    if fornitore_piva:
        query["fornitore_piva"] = {"$regex": fornitore_piva.strip(), "$options": "i"}

    if fornitore_nome:
        query["fornitore"] = {"$regex": fornitore_nome.strip(), "$options": "i"}

    if search:
        query["$or"] = [
            {"numero": {"$regex": search, "$options": "i"}},
            {"fornitore": {"$regex": search, "$options": "i"}},
            {"fornitore_piva": {"$regex": search, "$options": "i"}},
        ]

    projection = {
        "_id": 0,
        "id": 1, "tipo": 1,
        "numero": 1, "data": 1,
        "importo": 1,
        "fornitore": 1, "fornitore_piva": 1,
        "email_associata": 1, "pdf_associati": 1,
        "updated_at": 1,
        # Campi pagamento (aggiornati da paga_fattura_manuale)
        "pagato": 1,
        "status": 1,
        "stato_pagamento": 1,
        "riconciliato": 1,
        "prima_nota_cassa_id": 1,
        "prima_nota_banca_id": 1,
        "metodo_pagamento": 1,
        "metodo_pagamento_effettivo": 1,
        "data_pagamento": 1,
    }

    fatture = await db[COL_FATTURE_RICEVUTE].find(query, projection).sort(
        "data", -1
    ).skip(skip).limit(limit).to_list(limit)

    total = await db[COL_FATTURE_RICEVUTE].count_documents(query)

    normalized = []
    for f in fatture:
        try:
            importo_totale = float(f.get("importo") or 0)
        except (ValueError, TypeError):
            importo_totale = 0
        imponibile = round(importo_totale / 1.22, 2) if importo_totale > 0 else 0
        iva = round(importo_totale - imponibile, 2) if importo_totale > 0 else 0
        # Determina stato pagamento dai campi reali nel DB
        pagato = bool(f.get("pagato") or f.get("status") == "paid" or f.get("stato_pagamento") == "pagata")
        normalized.append({
            "id": f.get("id", ""),
            "numero_documento": f.get("numero"),
            "data_documento": f.get("data"),
            "importo_totale": importo_totale,
            "imponibile": imponibile,
            "iva": iva,
            "fornitore_ragione_sociale": f.get("fornitore"),
            "fornitore_partita_iva": f.get("fornitore_piva"),
            "stato": "pagata" if pagato else "importata",
            "metodo_pagamento": f.get("metodo_pagamento_effettivo") or f.get("metodo_pagamento"),
            "metodo_pagamento_effettivo": f.get("metodo_pagamento_effettivo") or f.get("metodo_pagamento"),
            "pagato": pagato,
            "riconciliato": bool(f.get("riconciliato")),
            "prima_nota_cassa_id": f.get("prima_nota_cassa_id"),
            "prima_nota_banca_id": f.get("prima_nota_banca_id"),
            "has_pdf": bool(f.get("pdf_associati") and f.get("pdf_associati") != "[]"),
            "email_associata": f.get("email_associata"),
            "anno": int(str(f.get("data", ""))[:4]) if f.get("data") else None,
            "created_at": f.get("updated_at"),
            "data_pagamento": f.get("data_pagamento"),
        })

    return {"fatture": normalized, "total": total, "limit": limit, "skip": skip}


async def view_fattura_assoinvoice(fattura_id: str) -> HTMLResponse:
    """Visualizza fattura in stile AssoInvoice."""
    from bson import ObjectId
    from bson.errors import InvalidId
    db = Database.get_db()
    
    # 1. Cerca in indice_documenti per id (UUID)
    fattura = await db[COL_FATTURE_RICEVUTE].find_one({"id": fattura_id}, {"_id": 0})
    
    # 2. Fallback: cerca in invoices (le scadenze dashboard vengono da lì)
    if not fattura:
        fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    
    # 3. Fallback ObjectId
    if not fattura:
        try:
            fattura = await db[COL_FATTURE_RICEVUTE].find_one({"_id": ObjectId(fattura_id)})
            if not fattura:
                fattura = await db["invoices"].find_one({"_id": ObjectId(fattura_id)})
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
    """Statistiche fatture ricevute da indice_documenti."""
    db = Database.get_db()

    query: dict = {"tipo": "fattura_ricevuta"}
    if anno:
        query["data"] = {"$gte": f"{anno}-01-01", "$lte": f"{anno}-12-31"}

    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": None,
            "totale_fatture": {"$sum": 1},
            "importo_totale": {"$sum": {"$toDouble": {"$ifNull": ["$importo", "0"]}}},
            "fornitori_unici": {"$addToSet": "$fornitore_piva"},
        }}
    ]

    result = await db[COL_FATTURE_RICEVUTE].aggregate(pipeline).to_list(1)
    stats = result[0] if result else {}
    stats.pop("_id", None)

    totale = stats.get("totale_fatture", 0)
    importo = round(stats.get("importo_totale", 0), 2)
    fornitori = len(stats.get("fornitori_unici", []))

    return {
        "totale_fatture": totale,
        "importo_totale": importo,
        "totale_importo": importo,
        "pagate": 0,
        "importo_pagato": 0,
        "da_pagare": totale,
        "importo_da_pagare": importo,
        "fornitori_unici": fornitori,
        "fatture_anomale": 0,
        "anno": anno,
    }
