"""
Prima Nota Module - Sincronizzazione e Import.
Sync corrispettivi, fatture, import CSV/batch.
"""
from fastapi import HTTPException, Query, Body
from typing import Dict
from datetime import datetime, timezone
import uuid

from app.database import Database, Collections
from .common import (
    COLLECTION_PRIMA_NOTA_CASSA, COLLECTION_PRIMA_NOTA_BANCA
)


# Tipi documento fatture attive (vendite - ENTRATE)
TIPI_FATTURA_ATTIVA = ["TD24", "TD25", "TD26", "TD27"]
TIPI_NOTA_CREDITO = ["TD04", "TD08"]


def determina_tipo_movimento_fattura(fattura: Dict) -> tuple:
    """Determina tipo movimento (entrata/uscita) e categoria dalla fattura."""
    tipo_doc = fattura.get("tipo_documento", "TD01").upper()
    supplier_vat = fattura.get("supplier_vat") or fattura.get("cedente_piva") or ""
    
    is_nota_credito = tipo_doc in TIPI_NOTA_CREDITO
    is_fattura_attiva = tipo_doc in TIPI_FATTURA_ATTIVA
    
    if is_nota_credito:
        return ("entrata", "Nota credito fornitore", "Nota credito")
    elif is_fattura_attiva:
        return ("entrata", "Incasso cliente", "Incasso fattura")
    else:
        return ("uscita", "Pagamento fornitore", "Pagamento fattura")


async def registra_pagamento_fattura(
    fattura: Dict,
    metodo_pagamento: str,
    importo_cassa: float = 0,
    importo_banca: float = 0
) -> Dict:
    """Registra automaticamente il pagamento di una fattura."""
    db = Database.get_db()
    
    now = datetime.now(timezone.utc).isoformat()
    data_fattura = fattura.get("invoice_date") or fattura.get("data_fattura") or now[:10]
    importo_totale = fattura.get("total_amount") or fattura.get("importo_totale") or 0
    numero_fattura = fattura.get("invoice_number") or fattura.get("numero_fattura") or "N/A"
    fornitore = fattura.get("supplier_name") or fattura.get("cedente_denominazione") or "Fornitore"
    fornitore_piva = fattura.get("supplier_vat") or fattura.get("cedente_piva") or ""
    
    tipo_movimento, categoria, desc_prefisso = determina_tipo_movimento_fattura(fattura)
    
    risultato = {"cassa": None, "banca": None, "tipo_movimento": tipo_movimento}
    descrizione_base = f"{desc_prefisso} {numero_fattura} - {fornitore[:40]}"
    
    movimento_base = {
        "data": data_fattura,
        "tipo": tipo_movimento,
        "categoria": categoria,
        "riferimento": numero_fattura,
        "fornitore_piva": fornitore_piva,
        "fattura_id": fattura.get("id") or fattura.get("invoice_key"),
        "tipo_documento": fattura.get("tipo_documento"),
        "source": "fattura_pagata",
        "created_at": now
    }
    
    if metodo_pagamento.lower() in ["cassa", "contanti"]:
        mov = {**movimento_base, "id": str(uuid.uuid4()), "importo": importo_totale, "descrizione": descrizione_base}
        await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(mov.copy())
        risultato["cassa"] = mov["id"]
        
    elif metodo_pagamento.lower() in ["banca", "bonifico", "assegno", "riba", "carta", "sepa", "mav", "rav", "rid", "f24"]:
        mov = {**movimento_base, "id": str(uuid.uuid4()), "importo": importo_totale, "descrizione": descrizione_base}
        await db[COLLECTION_PRIMA_NOTA_BANCA].insert_one(mov.copy())
        risultato["banca"] = mov["id"]
        
    elif metodo_pagamento.lower() == "misto":
        if importo_cassa > 0:
            mov = {**movimento_base, "id": str(uuid.uuid4()), "importo": importo_cassa, "descrizione": f"{descrizione_base} (contanti)"}
            await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(mov.copy())
            risultato["cassa"] = mov["id"]
        if importo_banca > 0:
            mov = {**movimento_base, "id": str(uuid.uuid4()), "importo": importo_banca, "descrizione": f"{descrizione_base} (bonifico)"}
            await db[COLLECTION_PRIMA_NOTA_BANCA].insert_one(mov.copy())
            risultato["banca"] = mov["id"]
    
    return risultato


async def registra_fattura_prima_nota(
    fattura_id: str = Body(...),
    metodo_pagamento: str = Body(None),
    importo_cassa: float = Body(0),
    importo_banca: float = Body(0)
) -> Dict:
    """Registra manualmente il pagamento di una fattura."""
    db = Database.get_db()
    
    fattura = await db[Collections.INVOICES].find_one(
        {"$or": [{"id": fattura_id}, {"invoice_key": fattura_id}]}
    )
    
    if not fattura:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    if not metodo_pagamento:
        fornitore_piva = fattura.get("supplier_vat") or fattura.get("cedente_piva")
        if fornitore_piva:
            fornitore = await db[Collections.SUPPLIERS].find_one({"partita_iva": fornitore_piva}, {"_id": 0})
            if fornitore:
                metodo_fornitore = (fornitore.get("metodo_pagamento") or "").lower()
                metodo_pagamento = "cassa" if metodo_fornitore in ["contanti", "cassa", "cash"] else "banca"
            else:
                metodo_pagamento = "banca"
        else:
            metodo_pagamento = "banca"
    
    risultato = await registra_pagamento_fattura(
        fattura=fattura,
        metodo_pagamento=metodo_pagamento,
        importo_cassa=importo_cassa,
        importo_banca=importo_banca
    )
    
    await db[Collections.INVOICES].update_one(
        {"_id": fattura["_id"]},
        {"$set": {
            "pagato": True,
            "data_pagamento": datetime.now(timezone.utc).isoformat()[:10],
            "metodo_pagamento": metodo_pagamento,
            "prima_nota_cassa_id": risultato.get("cassa"),
            "prima_nota_banca_id": risultato.get("banca")
        }}
    )
    
    return {
        "message": "Pagamento registrato",
        "prima_nota_cassa": risultato.get("cassa"),
        "prima_nota_banca": risultato.get("banca")
    }


async def sync_corrispettivi_to_prima_nota() -> Dict:
    """Sincronizza corrispettivi in Prima Nota Cassa."""
    return await _sync_corrispettivi_impl()


async def sync_corrispettivi_anno(anno: int = Query(...)) -> Dict:
    """Sincronizza corrispettivi dell'anno specificato nella Prima Nota Cassa."""
    return await _sync_corrispettivi_impl(anno)


async def _sync_corrispettivi_impl(anno: int = None) -> Dict:
    """Implementazione sync corrispettivi → prima nota cassa."""
    from .common import COLLECTION_PRIMA_NOTA_CASSA
    db = Database.get_db()
    
    query = {}
    if anno:
        query["anno"] = anno
    
    corrispettivi = await db["corrispettivi"].find(query, {"_id": 0}).to_list(5000)
    
    inseriti = 0
    duplicati = 0
    
    for c in corrispettivi:
        corr_id = c.get("id", "")
        
        # Check dedup
        existing = await db[COLLECTION_PRIMA_NOTA_CASSA].find_one({"corrispettivo_id": corr_id})
        if existing:
            duplicati += 1
            continue
        
        data = c.get("data", c.get("data_operazione", ""))
        totale = float(c.get("totale", 0) or c.get("totale_complessivo", 0) or c.get("importo", 0) or 0)
        
        if totale <= 0:
            continue
        
        movimento = {
            "id": str(__import__("uuid").uuid4()),
            "data": data,
            "tipo": "entrata",
            "categoria": "Corrispettivi",
            "descrizione": f"Corrispettivi {data}",
            "importo": totale,
            "corrispettivo_id": corr_id,
            "source": "corrispettivi_sync",
            "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }
        
        await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(movimento)
        inseriti += 1
    
    return {
        "message": f"Sincronizzati {inseriti} corrispettivi in Prima Nota Cassa",
        "inseriti": inseriti,
        "duplicati": duplicati,
        "anno": anno,
        "ok": True
    }


async def sync_fatture_pagate(anno: int = Query(...)) -> Dict:
    """Sincronizza fatture pagate nella Prima Nota."""
    db = Database.get_db()
    
    date_start = f"{anno}-01-01"
    date_end = f"{anno}-12-31"
    
    fatture = await db["invoices"].find(
        {"invoice_date": {"$gte": date_start, "$lte": date_end}, "stato_pagamento": "pagata"},
        {"_id": 0}
    ).to_list(10000)
    
    if not fatture:
        return {"message": "Nessuna fattura pagata trovata", "importati": 0}
    
    existing_cassa = await db[COLLECTION_PRIMA_NOTA_CASSA].find(
        {"categoria": "Fatture", "data": {"$gte": date_start, "$lte": date_end}},
        {"riferimento": 1, "_id": 0}
    ).to_list(10000)
    existing_banca = await db[COLLECTION_PRIMA_NOTA_BANCA].find(
        {"categoria": "Fatture", "data": {"$gte": date_start, "$lte": date_end}},
        {"riferimento": 1, "_id": 0}
    ).to_list(10000)
    existing_refs = set(e.get("riferimento") for e in existing_cassa + existing_banca if e.get("riferimento"))
    
    importati_cassa = 0
    importati_banca = 0
    totale_cassa = 0
    totale_banca = 0
    
    for fatt in fatture:
        ref = f"FATT-{fatt.get('id', '')}"
        
        if ref in existing_refs:
            continue
        
        totale = float(fatt.get("total_amount", 0) or 0)
        if totale <= 0:
            continue
        
        metodo = fatt.get("metodo_pagamento", "bonifico").lower()
        fornitore = fatt.get("supplier_name") or fatt.get("cedente_denominazione", "Fornitore")
        
        movimento = {
            "id": str(uuid.uuid4()),
            "data": fatt.get("invoice_date") or fatt.get("data_pagamento"),
            "tipo": "uscita",
            "importo": totale,
            "descrizione": f"Fattura {fatt.get('numero', '')} - {fornitore[:30]}",
            "categoria": "Fatture",
            "riferimento": ref,
            "source": "sync_fatture",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        if metodo in ["contanti", "cassa"]:
            await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(movimento.copy())
            importati_cassa += 1
            totale_cassa += totale
        else:
            await db[COLLECTION_PRIMA_NOTA_BANCA].insert_one(movimento.copy())
            importati_banca += 1
            totale_banca += totale
    
    return {
        "message": "Sincronizzazione completata",
        "importati_cassa": importati_cassa,
        "importati_banca": importati_banca,
        "totale_cassa": round(totale_cassa, 2),
        "totale_banca": round(totale_banca, 2),
        "fatture_pagate_anno": len(fatture)
    }


async def get_corrispettivi_sync_status() -> Dict:
    """Verifica stato sincronizzazione corrispettivi."""
    db = Database.get_db()
    
    total_corrispettivi = await db["corrispettivi"].count_documents({})
    synced = await db[COLLECTION_PRIMA_NOTA_CASSA].count_documents({"corrispettivo_id": {"$exists": True, "$ne": None}})
    
    pipeline = [{"$group": {"_id": None, "totale": {"$sum": "$totale"}}}]
    totals = await db["corrispettivi"].aggregate(pipeline).to_list(1)
    
    pipeline_pn = [
        {"$match": {"categoria": "Corrispettivi", "tipo": "entrata"}},
        {"$group": {"_id": None, "totale": {"$sum": "$importo"}}}
    ]
    totals_pn = await db[COLLECTION_PRIMA_NOTA_CASSA].aggregate(pipeline_pn).to_list(1)
    
    return {
        "corrispettivi_totali": total_corrispettivi,
        "corrispettivi_sincronizzati": synced,
        "da_sincronizzare": total_corrispettivi - synced,
        "totale_corrispettivi_euro": totals[0].get("totale", 0) if totals else 0,
        "totale_in_prima_nota_euro": totals_pn[0].get("totale", 0) if totals_pn else 0
    }



async def sync_estratto_conto_to_banca(anno: int = Query(...)) -> Dict:
    """
    Sincronizza movimenti dall'estratto conto bancario alla prima nota banca.
    Importa tutti i movimenti dell'anno specificato.
    """
    db = Database.get_db()
    
    # Trova movimenti dell'anno nell'estratto conto
    # Le date sono in formato DD/MM/YYYY
    anno_str = str(anno)
    
    # Query: data_contabile contiene l'anno (potrebbe essere DD/MM/YYYY o YYYY-MM-DD)
    query = {"$or": [
        {"data_contabile": {"$regex": f"/{anno_str}$"}},  # DD/MM/YYYY
        {"data_contabile": {"$regex": f"^{anno_str}-"}},   # YYYY-MM-DD
    ]}
    
    movimenti_ec = await db["estratto_conto_movimenti"].find(query, {"_id": 0}).to_list(15000)
    
    if not movimenti_ec:
        return {"message": f"Nessun movimento estratto conto per {anno}", "importati": 0}
    
    # Get existing prima nota banca for dedup
    existing_ids = set()
    async for pn in db[COLLECTION_PRIMA_NOTA_BANCA].find(
        {"data": {"$regex": f"^{anno_str}"}},
        {"_id": 0, "estratto_conto_id": 1, "id": 1}
    ):
        if pn.get("estratto_conto_id"):
            existing_ids.add(pn["estratto_conto_id"])
    
    importati = 0
    batch = []
    
    for mov in movimenti_ec:
        ec_id = mov.get("id", "")
        if ec_id in existing_ids:
            continue
        
        # Converti data DD/MM/YYYY → YYYY-MM-DD
        data_raw = mov.get("data_contabile", "")
        if "/" in data_raw:
            parts = data_raw.split("/")
            if len(parts) == 3:
                data_iso = f"{parts[2]}-{parts[1]}-{parts[0]}"
            else:
                data_iso = data_raw
        else:
            data_iso = data_raw
        
        importo = float(mov.get("importo", 0) or 0)
        if importo == 0:
            continue
        
        tipo = "entrata" if importo > 0 else "uscita"
        
        movimento_pn = {
            "id": str(uuid.uuid4()),
            "data": data_iso,
            "tipo": tipo,
            "importo": abs(importo),
            "descrizione": mov.get("descrizione", "")[:200],
            "categoria": mov.get("categoria", "Bancario"),
            "causale": mov.get("causale", ""),
            "beneficiario": mov.get("beneficiario", ""),
            "estratto_conto_id": ec_id,
            "source": "estratto_conto_sync",
            "created_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        }
        
        batch.append(movimento_pn)
        importati += 1
        
        # Insert in batches of 500
        if len(batch) >= 500:
            await db[COLLECTION_PRIMA_NOTA_BANCA].insert_many(batch)
            batch = []
    
    if batch:
        await db[COLLECTION_PRIMA_NOTA_BANCA].insert_many(batch)
    
    return {
        "message": f"Sincronizzati {importati} movimenti estratto conto → prima nota banca {anno}",
        "anno": anno,
        "movimenti_estratto_conto": len(movimenti_ec),
        "gia_sincronizzati": len(existing_ids),
        "importati": importati,
    }



async def import_prima_nota_batch(data: Dict = Body(...)) -> Dict:
    """Importa batch di movimenti."""
    db = Database.get_db()
    
    created_cassa = 0
    created_banca = 0
    errors = []
    
    for mov in data.get("cassa", []):
        try:
            movimento = {
                "id": str(uuid.uuid4()),
                "data": mov["data"],
                "tipo": mov["tipo"],
                "importo": float(mov["importo"]),
                "descrizione": mov.get("descrizione", ""),
                "categoria": mov.get("categoria", "Altro"),
                "riferimento": mov.get("riferimento"),
                "fornitore_piva": mov.get("fornitore_piva"),
                "fattura_id": mov.get("fattura_id"),
                "source": mov.get("source", "excel_import"),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db[COLLECTION_PRIMA_NOTA_CASSA].insert_one(movimento.copy())
            created_cassa += 1
        except Exception as e:
            errors.append(f"Cassa: {str(e)}")
    
    for mov in data.get("banca", []):
        try:
            movimento = {
                "id": str(uuid.uuid4()),
                "data": mov["data"],
                "tipo": mov["tipo"],
                "importo": float(mov["importo"]),
                "descrizione": mov.get("descrizione", ""),
                "categoria": mov.get("categoria", "Altro"),
                "riferimento": mov.get("riferimento"),
                "fornitore_piva": mov.get("fornitore_piva"),
                "fattura_id": mov.get("fattura_id"),
                "source": mov.get("source", "excel_import"),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db[COLLECTION_PRIMA_NOTA_BANCA].insert_one(movimento.copy())
            created_banca += 1
        except Exception as e:
            errors.append(f"Banca: {str(e)}")
    
    return {
        "message": "Import completato",
        "cassa_created": created_cassa,
        "banca_created": created_banca,
        "errors": errors[:10]
    }


async def create_movimento_generico(data: Dict = Body(...)) -> Dict:
    """Crea un movimento Prima Nota generico (cassa o banca)."""
    db = Database.get_db()
    
    tipo_nota = data.get("tipo", "banca")
    tipo_movimento = data.get("tipo_movimento", "entrata")
    
    required = ["data", "importo", "descrizione"]
    for field in required:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Campo obbligatorio mancante: {field}")
    
    movimento = {
        "id": str(uuid.uuid4()),
        "data": data["data"],
        "tipo": tipo_movimento,
        "importo": float(data["importo"]),
        "descrizione": data["descrizione"],
        "categoria": data.get("categoria", "Altro"),
        "riferimento": data.get("riferimento"),
        "fornitore_piva": data.get("fornitore_piva"),
        "fonte": data.get("fonte", "manual_entry"),
        "riconciliato": data.get("riconciliato", False),
        "note": data.get("note"),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    collection = COLLECTION_PRIMA_NOTA_BANCA if tipo_nota == "banca" else COLLECTION_PRIMA_NOTA_CASSA
    await db[collection].insert_one(movimento.copy())
    
    return {"message": f"Movimento {tipo_nota} creato", "id": movimento["id"]}


async def collega_fatture_movimenti() -> Dict:
    """Collega automaticamente fatture ai movimenti."""
    db = Database.get_db()
    
    collegati = 0
    
    for coll in [COLLECTION_PRIMA_NOTA_CASSA, COLLECTION_PRIMA_NOTA_BANCA]:
        cursor = db[coll].find({
            "numero_fattura": {"$exists": True, "$ne": None, "$ne": ""},
            "fattura_id": {"$in": [None, ""]}
        })
        
        async for mov in cursor:
            numero_fattura = mov.get("numero_fattura", "")
            if not numero_fattura:
                continue
            
            fattura = await db["invoices"].find_one({
                "$or": [
                    {"numero": numero_fattura},
                    {"invoice_number": numero_fattura},
                    {"numero_fattura": numero_fattura}
                ]
            }, {"_id": 0, "id": 1})
            
            if fattura:
                await db[coll].update_one(
                    {"id": mov["id"]},
                    {"$set": {"fattura_id": fattura["id"]}}
                )
                collegati += 1
    
    return {"success": True, "movimenti_collegati": collegati}
