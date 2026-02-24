"""
Sistema di Sincronizzazione Dati Relazionali
=============================================
Questo modulo gestisce la sincronizzazione automatica dei dati tra:
- Fatture XML (invoices)
- Prima Nota Cassa (prima_nota_cassa)
- Prima Nota Banca (prima_nota_banca)
- Corrispettivi (corrispettivi)
- Fornitori (suppliers)

REGOLE FONDAMENTALI:
1. Se modifico una fattura → aggiorno prima nota cassa/banca collegata
2. Se modifico prima nota → aggiorno fattura collegata
3. Se modifico corrispettivo → aggiorno prima nota cassa (entrata)
4. Entrate Cassa = Corrispettivi (imponibile + IVA = totale lordo)
"""
from fastapi import APIRouter, HTTPException, Body
from typing import Dict, Any
from datetime import datetime, timezone
import uuid
import logging

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sync", tags=["Sincronizzazione Dati"])


# ==================== COSTANTI ====================

COLLECTIONS = {
    "invoices": "invoices",
    "prima_nota_cassa": "prima_nota_cassa",
    "prima_nota_banca": "prima_nota_banca",
    "corrispettivi": "corrispettivi",
    "suppliers": "suppliers"
}


# ==================== FUNZIONI DI SINCRONIZZAZIONE ====================

async def sync_fattura_to_prima_nota(fattura_id: str, db) -> Dict[str, Any]:
    """
    Sincronizza una fattura con la prima nota.
    Se metodo_pagamento = "Cassa" → prima_nota_cassa
    Se metodo_pagamento = "Bonifico" o altro → prima_nota_banca
    """
    fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
    if not fattura:
        return {"success": False, "error": "Fattura non trovata"}
    
    metodo = fattura.get("metodo_pagamento", "")
    importo = fattura.get("total_amount") or fattura.get("importo_totale") or 0
    fornitore = fattura.get("supplier_name") or fattura.get("cedente_denominazione") or ""
    numero = fattura.get("invoice_number") or fattura.get("numero_fattura") or ""
    data_pag = fattura.get("data_pagamento") or fattura.get("invoice_date") or ""
    
    if not metodo:
        return {"success": False, "error": "Metodo pagamento non specificato"}
    
    # Determina collection target
    if metodo.lower() in ["cassa", "contanti"]:
        collection = "prima_nota_cassa"
    else:
        collection = "prima_nota_banca"
    
    # Cerca movimento esistente collegato
    movimento_esistente = await db[collection].find_one({
        "fattura_id": fattura_id
    }, {"_id": 0})
    
    movimento_data = {
        "fattura_id": fattura_id,
        "data": data_pag[:10] if data_pag else datetime.now().strftime("%Y-%m-%d"),
        "tipo": "uscita",
        "importo": importo,
        "descrizione": f"Fattura {numero} - {fornitore}",
        "categoria": "Fornitori",
        "metodo": "contanti" if collection == "prima_nota_cassa" else "bonifico",
        "fornitore": fornitore,
        "numero_fattura": numero,
        "anno": int(data_pag[:4]) if data_pag else datetime.now().year,
        "mese": int(data_pag[5:7]) if data_pag else datetime.now().month,
        "riconciliato": True,
        "pagato": fattura.get("pagato", False),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if movimento_esistente:
        # Aggiorna
        await db[collection].update_one(
            {"fattura_id": fattura_id},
            {"$set": movimento_data}
        )
        return {"success": True, "action": "updated", "collection": collection}
    else:
        # Crea nuovo
        movimento_data["id"] = str(uuid.uuid4())
        movimento_data["created_at"] = datetime.now(timezone.utc).isoformat()
        await db[collection].insert_one(movimento_data.copy())
        return {"success": True, "action": "created", "collection": collection}


async def sync_corrispettivo_to_prima_nota(corrispettivo_id: str, db) -> Dict[str, Any]:
    """
    Sincronizza un corrispettivo con la prima nota cassa.
    ENTRATA = IMPONIBILE + IVA (totale lordo)
    """
    corr = await db["corrispettivi"].find_one({"id": corrispettivo_id}, {"_id": 0})
    if not corr:
        return {"success": False, "error": "Corrispettivo non trovato"}
    
    # Calcola totale entrata = imponibile + IVA
    totale_lordo = corr.get("totale_lordo") or (
        (corr.get("totale_imponibile") or 0) + (corr.get("totale_iva") or 0)
    )
    
    data_corr = corr.get("data", "")
    
    # Cerca movimento esistente collegato
    movimento_esistente = await db["prima_nota_cassa"].find_one({
        "corrispettivo_id": corrispettivo_id
    }, {"_id": 0})
    
    movimento_data = {
        "corrispettivo_id": corrispettivo_id,
        "data": data_corr,
        "tipo": "entrata",
        "importo": totale_lordo,  # IMPONIBILE + IVA
        "descrizione": f"Corrispettivi del {data_corr}",
        "categoria": "Corrispettivi",
        "metodo": "contanti",
        "anno": int(data_corr[:4]) if data_corr else datetime.now().year,
        "mese": int(data_corr[5:7]) if data_corr else datetime.now().month,
        "riconciliato": False,
        "dettaglio": {
            "imponibile": corr.get("totale_imponibile", 0),
            "iva": corr.get("totale_iva", 0),
            "num_scontrini": corr.get("numero_scontrini", 0)
        },
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    if movimento_esistente:
        await db["prima_nota_cassa"].update_one(
            {"corrispettivo_id": corrispettivo_id},
            {"$set": movimento_data}
        )
        return {"success": True, "action": "updated"}
    else:
        movimento_data["id"] = str(uuid.uuid4())
        movimento_data["created_at"] = datetime.now(timezone.utc).isoformat()
        await db["prima_nota_cassa"].insert_one(movimento_data.copy())
        return {"success": True, "action": "created"}


async def match_fatture_con_prima_nota_cassa(db) -> Dict[str, Any]:
    """
    Cerca fatture XML che corrispondono a movimenti in prima nota cassa.
    Match per: numero fattura + fornitore + importo
    Se trova match → associa metodo_pagamento = "Cassa" alla fattura
    """
    results = {
        "matched": 0,
        "not_matched": 0,
        "already_linked": 0,
        "details": []
    }
    
    # Prendi tutti i movimenti prima nota cassa - pagamenti fornitori
    # Categoria può essere "Pagamento fornitore" o "Fornitori"
    movimenti_cassa = await db["prima_nota_cassa"].find({
        "tipo": "uscita",
        "$or": [
            {"categoria": "Pagamento fornitore"},
            {"categoria": "Fornitori"},
            {"categoria": {"$regex": "fornitore", "$options": "i"}}
        ],
        "fattura_id": {"$exists": False}  # Solo quelli non ancora associati
    }, {"_id": 0}).to_list(10000)
    
    for mov in movimenti_cassa:
        # Prova a estrarre numero fattura dalla descrizione o dal campo riferimento
        riferimento = mov.get("riferimento", "")
        descrizione = mov.get("descrizione", "")
        importo = mov.get("importo", 0)
        
        # Estrai numero fattura
        numero = riferimento
        if not numero and "fattura" in descrizione.lower():
            # Prova a estrarre da descrizione tipo "Pagamento fattura 123 - Fornitore"
            import re
            match = re.search(r'fattura\s+(\S+)', descrizione, re.IGNORECASE)
            if match:
                numero = match.group(1)
        
        if not numero or not importo:
            results["not_matched"] += 1
            continue
        
        # Cerca fattura corrispondente
        fattura = await db["invoices"].find_one({
            "$and": [
                {"$or": [
                    {"invoice_number": {"$regex": numero, "$options": "i"}},
                    {"numero_fattura": {"$regex": numero, "$options": "i"}}
                ]},
                {"$or": [
                    {"total_amount": {"$gte": importo - 0.50, "$lte": importo + 0.50}},
                    {"importo_totale": {"$gte": importo - 0.50, "$lte": importo + 0.50}}
                ]}
            ]
        }, {"_id": 0})
        
        if fattura:
            # Trovato! Aggiorna fattura con metodo pagamento Cassa
            await db["invoices"].update_one(
                {"id": fattura["id"]},
                {"$set": {
                    "metodo_pagamento": "Cassa",
                    "pagato": True,
                    "paid": True,
                    "data_pagamento": mov.get("data"),
                    "prima_nota_cassa_id": mov.get("id"),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            # Aggiorna anche il movimento con riferimento fattura
            await db["prima_nota_cassa"].update_one(
                {"id": mov["id"]},
                {"$set": {
                    "fattura_id": fattura["id"],
                    "riconciliato": True,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            results["matched"] += 1
            results["details"].append({
                "movimento_id": mov.get("id"),
                "fattura_id": fattura["id"],
                "numero": numero,
                "importo": importo
            })
        else:
            results["not_matched"] += 1
    
    return results


# ELIMINATA: funzione set_fatture_non_cassa_to_banca - Pericolosa, impostava tutte le fatture a Bonifico


async def match_fatture_con_estratto_conto(db) -> Dict[str, Any]:
    """
    Cerca corrispondenze tra fatture e movimenti estratto conto bancario.
    Match per importo e fornitore nella descrizione.
    """
    results = {
        "matched": 0,
        "not_matched": 0,
        "already_matched": 0,
        "details": []
    }
    
    # Prendi fatture bonifico non ancora associate
    fatture = await db["invoices"].find({
        "$and": [
            {"$or": [
                {"metodo_pagamento": {"$regex": "bonifico", "$options": "i"}},
                {"metodo_pagamento": "Bonifico"}
            ]},
            {"$or": [
                {"estratto_conto_id": {"$exists": False}},
                {"estratto_conto_id": None}
            ]}
        ]
    }, {"_id": 0}).to_list(5000)
    
    for fattura in fatture:
        importo = fattura.get("total_amount") or fattura.get("importo_totale") or 0
        fornitore = (fattura.get("supplier_name") or fattura.get("cedente_denominazione") or "").upper()
        numero = fattura.get("invoice_number") or fattura.get("numero_fattura") or ""
        
        if not importo or importo <= 0:
            continue
        
        # Cerca in estratto conto per importo (negativo = uscita) e fornitore in descrizione
        # Tolleranza importo: ±1€
        movimento = await db["estratto_conto"].find_one({
            "$and": [
                {"tipo": "uscita"},
                {"importo": {"$gte": importo - 1, "$lte": importo + 1}},
                {"fattura_id": {"$exists": False}},  # Non già associato
                {"$or": [
                    {"descrizione": {"$regex": fornitore[:20], "$options": "i"}},
                    {"descrizione": {"$regex": numero, "$options": "i"}}
                ]}
            ]
        }, {"_id": 0})
        
        if movimento:
            # Trovato! Associa
            await db["invoices"].update_one(
                {"id": fattura["id"]},
                {"$set": {
                    "estratto_conto_id": movimento.get("id"),
                    "pagato": True,
                    "paid": True,
                    "data_pagamento": movimento.get("data"),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            await db["estratto_conto"].update_one(
                {"id": movimento["id"]},
                {"$set": {
                    "fattura_id": fattura["id"],
                    "riconciliato": True,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            results["matched"] += 1
            if len(results["details"]) < 20:
                results["details"].append({
                    "fattura": numero,
                    "fornitore": fornitore[:30],
                    "importo": importo,
                    "movimento_id": movimento.get("id")
                })
        else:
            results["not_matched"] += 1
    
    return results


# ==================== ENDPOINTS ====================

@router.post("/match-fatture-cassa")
async def api_match_fatture_cassa() -> Dict[str, Any]:
    """
    Cerca corrispondenze tra fatture XML e prima nota cassa.
    Le fatture trovate vengono marcate come pagate in Cassa.
    """
    db = Database.get_db()
    result = await match_fatture_con_prima_nota_cassa(db)
    return result


@router.post("/match-fatture-banca")
async def api_match_fatture_banca() -> Dict[str, Any]:
    """
    Cerca corrispondenze tra fatture e estratto conto bancario.
    Match per importo e fornitore nella descrizione.
    """
    db = Database.get_db()
    result = await match_fatture_con_estratto_conto(db)
    return result


# ELIMINATO: endpoint /fatture-to-banca - Funzione pericolosa che impostava tutte le fatture a Bonifico
# Se necessario, usare l'endpoint specifico per singola fattura


@router.get("/fatture-cassa-dettaglio")
async def api_fatture_cassa_dettaglio() -> Dict[str, Any]:
    """
    Restituisce dettaglio fatture associate a pagamenti in cassa.
    """
    db = Database.get_db()
    
    # Fatture con prima_nota_cassa_id popolato
    fatture_cassa = await db["invoices"].find({
        "prima_nota_cassa_id": {"$exists": True, "$ne": None}
    }, {"_id": 0, "id": 1, "invoice_number": 1, "supplier_name": 1, "total_amount": 1, "metodo_pagamento": 1}).to_list(1000)
    
    # Movimenti prima nota cassa con fattura_id
    movimenti_con_fattura = await db["prima_nota_cassa"].find({
        "fattura_id": {"$exists": True, "$ne": None}
    }, {"_id": 0, "id": 1, "descrizione": 1, "importo": 1, "fattura_id": 1}).to_list(1000)
    
    return {
        "fatture_associate_cassa": len(fatture_cassa),
        "movimenti_con_fattura": len(movimenti_con_fattura),
        "esempi_fatture": fatture_cassa[:10],
        "esempi_movimenti": movimenti_con_fattura[:10]
    }


@router.post("/sync-fattura/{fattura_id}")
async def api_sync_fattura(fattura_id: str) -> Dict[str, Any]:
    """
    Sincronizza una fattura con la prima nota corrispondente.
    """
    db = Database.get_db()
    result = await sync_fattura_to_prima_nota(fattura_id, db)
    return result


@router.post("/sync-corrispettivo/{corrispettivo_id}")
async def api_sync_corrispettivo(corrispettivo_id: str) -> Dict[str, Any]:
    """
    Sincronizza un corrispettivo con la prima nota cassa.
    Crea movimento di ENTRATA = imponibile + IVA.
    """
    db = Database.get_db()
    result = await sync_corrispettivo_to_prima_nota(corrispettivo_id, db)
    return result


@router.post("/sync-all-corrispettivi")
async def api_sync_all_corrispettivi(anno: int = Body(..., embed=True)) -> Dict[str, Any]:
    """
    Sincronizza tutti i corrispettivi di un anno con la prima nota cassa.
    """
    db = Database.get_db()
    
    corrispettivi = await db["corrispettivi"].find(
        {"data": {"$regex": f"^{anno}"}},
        {"_id": 0, "id": 1}
    ).to_list(1000)
    
    created = 0
    updated = 0
    errors = 0
    
    for corr in corrispettivi:
        try:
            result = await sync_corrispettivo_to_prima_nota(corr["id"], db)
            if result.get("action") == "created":
                created += 1
            elif result.get("action") == "updated":
                updated += 1
        except Exception as e:
            logger.error(f"Errore sync corrispettivo {corr['id']}: {e}")
            errors += 1
    
    return {
        "anno": anno,
        "totale_corrispettivi": len(corrispettivi),
        "created": created,
        "updated": updated,
        "errors": errors
    }


@router.put("/update-fattura-everywhere/{fattura_id}")
async def api_update_fattura_everywhere(
    fattura_id: str, 
    data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Aggiorna una fattura e propaga le modifiche in tutte le collection collegate.
    LOGICA RELAZIONALE: modifica una volta, aggiorna ovunque.
    """
    db = Database.get_db()
    
    # Campi aggiornabili
    allowed = ["metodo_pagamento", "pagato", "data_pagamento", "importo", "note"]
    update_data = {k: v for k, v in data.items() if k in allowed}
    
    if not update_data:
        raise HTTPException(status_code=400, detail="Nessun campo valido")
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    # Sincronizza pagato/paid
    if "pagato" in update_data:
        update_data["paid"] = update_data["pagato"]
    
    # 1. Aggiorna fattura
    result = await db["invoices"].update_one(
        {"id": fattura_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fattura non trovata")
    
    updates = {"invoices": 1}
    
    # 2. Aggiorna prima nota cassa se collegata
    pn_cassa = await db["prima_nota_cassa"].update_one(
        {"fattura_id": fattura_id},
        {"$set": {
            "importo": update_data.get("importo") if "importo" in update_data else None,
            "pagato": update_data.get("pagato"),
            "data": update_data.get("data_pagamento"),
            "updated_at": update_data["updated_at"]
        }}
    )
    if pn_cassa.modified_count > 0:
        updates["prima_nota_cassa"] = 1
    
    # 3. Aggiorna prima nota banca se collegata
    pn_banca = await db["prima_nota_banca"].update_one(
        {"fattura_id": fattura_id},
        {"$set": {
            "importo": update_data.get("importo") if "importo" in update_data else None,
            "pagato": update_data.get("pagato"),
            "data": update_data.get("data_pagamento"),
            "updated_at": update_data["updated_at"]
        }}
    )
    if pn_banca.modified_count > 0:
        updates["prima_nota_banca"] = 1
    
    # 4. Se cambia metodo pagamento, sposta tra cassa e banca
    if "metodo_pagamento" in update_data:
        metodo = update_data["metodo_pagamento"]
        fattura = await db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
        
        if metodo.lower() in ["cassa", "contanti"]:
            # Rimuovi da banca, aggiungi a cassa
            await db["prima_nota_banca"].delete_one({"fattura_id": fattura_id})
            await sync_fattura_to_prima_nota(fattura_id, db)
            updates["moved_to"] = "prima_nota_cassa"
        else:
            # Rimuovi da cassa, aggiungi a banca
            await db["prima_nota_cassa"].delete_one({"fattura_id": fattura_id})
            await sync_fattura_to_prima_nota(fattura_id, db)
            updates["moved_to"] = "prima_nota_banca"
    
    return {
        "success": True,
        "fattura_id": fattura_id,
        "updates": updates
    }


@router.get("/stato-sincronizzazione")
async def api_stato_sincronizzazione() -> Dict[str, Any]:
    """
    Restituisce lo stato di sincronizzazione del sistema.
    """
    db = Database.get_db()
    
    fatture_totali = await db["invoices"].count_documents({})
    fatture_cassa = await db["invoices"].count_documents({
        "$or": [
            {"metodo_pagamento": "Cassa"},
            {"metodo_pagamento": "cassa"},
            {"metodo_pagamento": {"$regex": "cassa", "$options": "i"}}
        ]
    })
    fatture_banca = await db["invoices"].count_documents({
        "$or": [
            {"metodo_pagamento": "Bonifico"},
            {"metodo_pagamento": "bonifico"}
        ]
    })
    fatture_pagate = await db["invoices"].count_documents({
        "$or": [{"pagato": True}, {"paid": True}]
    })
    fatture_senza_metodo = await db["invoices"].count_documents({
        "$or": [
            {"metodo_pagamento": {"$exists": False}},
            {"metodo_pagamento": None},
            {"metodo_pagamento": ""}
        ]
    })
    
    pn_cassa_uscite = await db["prima_nota_cassa"].count_documents({"tipo": "uscita"})
    pn_cassa_entrate = await db["prima_nota_cassa"].count_documents({"tipo": "entrata"})
    pn_cassa_con_fattura = await db["prima_nota_cassa"].count_documents({
        "fattura_id": {"$exists": True, "$ne": None}
    })
    pn_banca = await db["prima_nota_banca"].count_documents({})
    
    corrispettivi = await db["corrispettivi"].count_documents({})
    
    return {
        "fatture": {
            "totali": fatture_totali,
            "pagate": fatture_pagate,
            "cassa": fatture_cassa,
            "banca": fatture_banca,
            "senza_metodo": fatture_senza_metodo
        },
        "prima_nota_cassa": {
            "uscite": pn_cassa_uscite,
            "entrate": pn_cassa_entrate,
            "con_fattura": pn_cassa_con_fattura
        },
        "prima_nota_banca": pn_banca,
        "corrispettivi": corrispettivi
    }
