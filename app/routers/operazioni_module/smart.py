"""
Operazioni Module - Riconciliazione Smart (banca veloce, analisi, associazioni).
"""
from fastapi import HTTPException
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from app.database import Database
from .common import RiconciliaManuale, logger


async def banca_veloce(
    limit: int = 50,
    solo_non_riconciliati: bool = True
) -> Dict[str, Any]:
    """Endpoint veloce per tab Banca - movimenti + assegni + fatture da pagare."""
    db = Database.get_db()
    
    query = {}
    if solo_non_riconciliati:
        query["riconciliato"] = {"$ne": True}
    
    movimenti = await db.estratto_conto_movimenti.find(
        query,
        {"_id": 0, "id": 1, "data": 1, "importo": 1, "descrizione": 1, "descrizione_originale": 1, "riconciliato": 1}
    ).sort("data", -1).limit(limit).to_list(limit)
    
    assegni = await db.assegni.find(
        {"stato": {"$nin": ["incassato", "annullato"]}, "confermato": {"$ne": True}},
        {"_id": 0}
    ).sort("data_emissione", -1).limit(50).to_list(50)
    
    fatture_da_pagare = await db.invoices.find(
        {"pagata": {"$ne": True}, "metodo_pagamento": {"$nin": [None, "", "contanti"]}},
        {"_id": 0, "id": 1, "invoice_number": 1, "invoice_date": 1, "supplier_name": 1, "total_amount": 1}
    ).sort("invoice_date", -1).limit(50).to_list(50)
    
    tot_non_ric = await db.estratto_conto_movimenti.count_documents({"riconciliato": {"$ne": True}})
    tot_ric = await db.estratto_conto_movimenti.count_documents({"riconciliato": True})
    
    return {
        "movimenti": movimenti,
        "assegni": assegni,
        "fatture_da_pagare": fatture_da_pagare,
        "stats": {
            "totale": len(movimenti),
            "non_riconciliati": tot_non_ric,
            "riconciliati": tot_ric,
            "assegni_pendenti": len(assegni),
            "fatture_da_pagare": len(fatture_da_pagare)
        }
    }


async def analizza_movimenti_smart(
    limit: int = 100,
    solo_non_riconciliati: bool = True
) -> Dict[str, Any]:
    """Analizza movimenti estratto conto con suggerimenti riconciliazione."""
    from app.services.riconciliazione_smart import analizza_estratto_conto_batch
    
    try:
        risultati = await analizza_estratto_conto_batch(limit, solo_non_riconciliati)
        return risultati
    except Exception as e:
        logger.error(f"Errore analisi smart: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def analizza_singolo_movimento(movimento_id: str) -> Dict[str, Any]:
    """Analizza un singolo movimento."""
    from app.services.riconciliazione_smart import analizza_singolo_movimento as analyze
    
    try:
        return await analyze(movimento_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def riconcilia_automatico(
    tipo: Optional[str] = None,
    limit: int = 100
) -> Dict[str, Any]:
    """Riconciliazione automatica dei movimenti."""
    db = Database.get_db()
    
    query = {"riconciliato": {"$ne": True}}
    if tipo:
        query["tipo_suggerito"] = tipo
    
    movimenti = await db.estratto_conto_movimenti.find(query, {"_id": 0}).limit(limit).to_list(limit)
    
    riconciliati = 0
    errori = []
    
    for mov in movimenti:
        try:
            importo = abs(float(mov.get("importo", 0)))
            descrizione = (mov.get("descrizione") or mov.get("descrizione_originale") or "").upper()
            
            match_found = False
            
            # Match fatture per importo esatto
            fattura = await db.invoices.find_one({
                "pagata": {"$ne": True},
                "$or": [
                    {"total_amount": {"$gte": importo * 0.99, "$lte": importo * 1.01}},
                    {"importo_totale": {"$gte": importo * 0.99, "$lte": importo * 1.01}}
                ]
            }, {"_id": 0, "id": 1, "supplier_name": 1})
            
            if fattura:
                await db.estratto_conto_movimenti.update_one(
                    {"id": mov["id"]},
                    {"$set": {
                        "riconciliato": True,
                        "fattura_id": fattura["id"],
                        "tipo_riconciliazione": "auto_importo",
                        "data_riconciliazione": datetime.now(timezone.utc).isoformat()
                    }}
                )
                await db.invoices.update_one(
                    {"id": fattura["id"]},
                    {"$set": {"pagata": True, "movimento_bancario_id": mov["id"]}}
                )
                riconciliati += 1
                match_found = True
            
            if not match_found and "I24" in descrizione:
                # Match F24
                f24 = await db.f24_commercialista.find_one({
                    "importo_totale": {"$gte": importo * 0.99, "$lte": importo * 1.01}
                }, {"_id": 0, "id": 1})
                
                if f24:
                    await db.estratto_conto_movimenti.update_one(
                        {"id": mov["id"]},
                        {"$set": {
                            "riconciliato": True,
                            "f24_id": f24["id"],
                            "tipo_riconciliazione": "auto_f24",
                            "data_riconciliazione": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    riconciliati += 1
                    
        except Exception as e:
            errori.append({"movimento_id": mov.get("id"), "error": str(e)})
    
    return {
        "success": True,
        "riconciliati": riconciliati,
        "analizzati": len(movimenti),
        "errori": errori[:10]
    }


async def riconcilia_manuale(request: RiconciliaManuale) -> Dict[str, Any]:
    """Riconciliazione manuale movimento con entità."""
    db = Database.get_db()
    
    movimento = await db.estratto_conto_movimenti.find_one({"id": request.movimento_id})
    if not movimento:
        raise HTTPException(status_code=404, detail="Movimento non trovato")
    
    update_fields = {
        "riconciliato": True,
        "tipo_riconciliazione": "manuale",
        "data_riconciliazione": datetime.now(timezone.utc).isoformat(),
        "note_riconciliazione": request.note
    }
    
    if request.tipo_operazione == "fattura":
        fattura = await db.invoices.find_one({"id": request.entita_id})
        if not fattura:
            raise HTTPException(status_code=404, detail="Fattura non trovata")
        
        update_fields["fattura_id"] = request.entita_id
        await db.invoices.update_one(
            {"id": request.entita_id},
            {"$set": {"pagata": True, "movimento_bancario_id": request.movimento_id}}
        )
        
    elif request.tipo_operazione == "stipendio":
        update_fields["stipendio_id"] = request.entita_id
        
    elif request.tipo_operazione == "f24":
        update_fields["f24_id"] = request.entita_id
    
    await db.estratto_conto_movimenti.update_one(
        {"id": request.movimento_id},
        {"$set": update_fields}
    )
    
    return {"success": True, "movimento_id": request.movimento_id, "tipo": request.tipo_operazione}


async def cerca_fatture_per_associazione(
    importo: Optional[float] = None,
    fornitore: Optional[str] = None,
    data: Optional[str] = None,
    limit: int = 20
) -> Dict[str, Any]:
    """Cerca fatture per associazione manuale."""
    db = Database.get_db()
    
    query = {"pagata": {"$ne": True}}
    
    if importo:
        tolleranza = importo * 0.05
        query["$or"] = [
            {"total_amount": {"$gte": importo - tolleranza, "$lte": importo + tolleranza}},
            {"importo_totale": {"$gte": importo - tolleranza, "$lte": importo + tolleranza}}
        ]
    
    if fornitore:
        query["$or"] = query.get("$or", []) + [
            {"supplier_name": {"$regex": fornitore, "$options": "i"}},
            {"cedente_denominazione": {"$regex": fornitore, "$options": "i"}}
        ]
    
    fatture = await db.invoices.find(query, {"_id": 0}).sort("invoice_date", -1).limit(limit).to_list(limit)
    
    return {"fatture": fatture, "totale": len(fatture)}


async def cerca_stipendi_per_associazione(
    importo: Optional[float] = None,
    dipendente: Optional[str] = None,
    limit: int = 20
) -> Dict[str, Any]:
    """Cerca stipendi per associazione manuale."""
    db = Database.get_db()
    
    query = {"riconciliato": {"$ne": True}}
    
    if importo:
        tolleranza = importo * 0.05
        query["importo"] = {"$gte": importo - tolleranza, "$lte": importo + tolleranza}
    
    if dipendente:
        query["$or"] = [
            {"nome_dipendente": {"$regex": dipendente, "$options": "i"}},
            {"dipendente": {"$regex": dipendente, "$options": "i"}}
        ]
    
    stipendi = await db.prima_nota_salari.find(query, {"_id": 0}).sort("data", -1).limit(limit).to_list(limit)
    
    return {"stipendi": stipendi, "totale": len(stipendi)}


async def cerca_f24_per_associazione(
    importo: Optional[float] = None,
    data: Optional[str] = None,
    limit: int = 20
) -> Dict[str, Any]:
    """Cerca F24 per associazione manuale."""
    db = Database.get_db()
    
    query = {"riconciliato": {"$ne": True}}
    
    if importo:
        tolleranza = importo * 0.05
        query["importo_totale"] = {"$gte": importo - tolleranza, "$lte": importo + tolleranza}
    
    if data:
        query["data_scadenza"] = {"$regex": f"^{data[:7]}"}
    
    f24_list = await db.f24_commercialista.find(query, {"_id": 0}).sort("data_scadenza", -1).limit(limit).to_list(limit)
    
    return {"f24": f24_list, "totale": len(f24_list)}
