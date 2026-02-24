"""
Suppliers base CRUD operations.
List, get, update, delete suppliers.
"""
from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import uuid
import httpx
import re

from app.database import Database, Collections
from app.middleware.performance import cache
from .common import (
    PAYMENT_METHODS, PAYMENT_TERMS, SUPPLIERS_CACHE_KEY, SUPPLIERS_CACHE_TTL,
    logger
)

router = APIRouter()


@router.get("/search-piva/{partita_iva}")
async def search_by_piva(partita_iva: str) -> Dict[str, Any]:
    """
    Cerca informazioni aziendali partendo dalla Partita IVA.
    Utilizza: VIES, RegistroAziende, Database locale.
    """
    piva = re.sub(r'[^0-9]', '', partita_iva)
    
    if len(piva) != 11:
        raise HTTPException(status_code=400, detail="Partita IVA deve essere di 11 cifre")
    
    result = {
        "found": False,
        "partita_iva": piva,
        "ragione_sociale": None,
        "indirizzo": None,
        "cap": None,
        "comune": None,
        "provincia": None,
        "nazione": "IT",
        "pec": None,
        "source": None
    }
    
    db = Database.get_db()
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            # VIES
            try:
                vies_url = "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"
                vies_resp = await client.post(vies_url, json={"countryCode": "IT", "vatNumber": piva})
                
                if vies_resp.status_code == 200:
                    vies_data = vies_resp.json()
                    if vies_data.get("valid"):
                        result["found"] = True
                        result["source"] = "VIES"
                        name = vies_data.get("name", "")
                        if name and name != "---":
                            result["ragione_sociale"] = name.strip().title()
                        addr = vies_data.get("address", "")
                        if addr and addr != "---":
                            result["indirizzo"] = addr.strip()
                            addr_match = re.search(r'(\d{5})\s+([A-Za-z\s]+?)(?:\s+([A-Z]{2}))?$', addr)
                            if addr_match:
                                result["cap"] = addr_match.group(1)
                                result["comune"] = addr_match.group(2).strip().title()
                                if addr_match.group(3):
                                    result["provincia"] = addr_match.group(3)
            except Exception as e:
                logger.warning(f"VIES lookup failed: {e}")
            
            # Database locale
            if not result["ragione_sociale"]:
                invoice = await db["invoices"].find_one(
                    {"$or": [{"supplier_vat": piva}, {"cedente_piva": piva}]},
                    {"cedente_denominazione": 1, "supplier_name": 1, "supplier_address": 1}
                )
                if invoice:
                    name = invoice.get("cedente_denominazione") or invoice.get("supplier_name")
                    if name:
                        result["ragione_sociale"] = name
                        result["found"] = True
                        result["source"] = result["source"] or "Database locale"
            
            if not result["ragione_sociale"]:
                supplier = await db[Collections.SUPPLIERS].find_one(
                    {"partita_iva": piva},
                    {"_id": 0}
                )
                if supplier:
                    result["ragione_sociale"] = supplier.get("ragione_sociale") or supplier.get("denominazione")
                    result["indirizzo"] = result["indirizzo"] or supplier.get("indirizzo")
                    result["cap"] = result["cap"] or supplier.get("cap")
                    result["comune"] = result["comune"] or supplier.get("comune")
                    result["provincia"] = result["provincia"] or supplier.get("provincia")
                    result["pec"] = result["pec"] or supplier.get("pec")
                    if result["ragione_sociale"]:
                        result["found"] = True
                        result["source"] = result["source"] or "Database locale"
            
            if not result["found"]:
                result["message"] = "Partita IVA non trovata nelle fonti pubbliche"
            
            return result
                
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Timeout nella ricerca")
        except Exception as e:
            logger.error(f"Errore ricerca PIVA: {e}")
            raise HTTPException(status_code=500, detail=f"Errore nella ricerca: {str(e)}")


@router.get("")
async def list_suppliers(
    skip: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=1000),
    search: Optional[str] = Query(None),
    metodo_pagamento: Optional[str] = Query(None),
    attivo: Optional[bool] = Query(None),
    use_cache: bool = Query(True)
) -> List[Dict[str, Any]]:
    """Lista fornitori con filtri e statistiche fatture."""
    import time
    
    db = Database.get_db()
    t_start = time.time()
    
    cache_key = f"{SUPPLIERS_CACHE_KEY}:all"
    if use_cache and not search and not metodo_pagamento and attivo is None:
        cached_data = await cache.get(cache_key)
        if cached_data is not None:
            return cached_data[skip:skip+limit]
    
    suppliers_map = {}
    
    suppliers_query = {}
    if search and search.strip():
        search_lower = search.strip()
        suppliers_query["$or"] = [
            {"denominazione": {"$regex": search_lower, "$options": "i"}},
            {"ragione_sociale": {"$regex": search_lower, "$options": "i"}},
            {"partita_iva": {"$regex": search_lower, "$options": "i"}}
        ]
    if metodo_pagamento:
        suppliers_query["metodo_pagamento"] = metodo_pagamento
    
    saved_suppliers = await db[Collections.SUPPLIERS].find(suppliers_query, {"_id": 0}).to_list(1000)
    
    for supplier in saved_suppliers:
        piva = supplier.get("partita_iva")
        if piva:
            suppliers_map[piva] = {
                **supplier,
                "fatture_count": supplier.get("fatture_count", 0),
                "fatture_totale": 0,
                "fatture_non_pagate": 0,
                "source": "database"
            }
    
    if not search:
        stats_pipeline = [
            {"$match": {"$or": [
                {"supplier_vat": {"$exists": True, "$ne": None, "$ne": ""}},
                {"fornitore_partita_iva": {"$exists": True, "$ne": None, "$ne": ""}}
            ]}},
            {"$group": {
                "_id": {"$ifNull": ["$supplier_vat", "$fornitore_partita_iva"]},
                "fatture_count": {"$sum": 1},
                "fatture_totale": {"$sum": {"$toDouble": {"$ifNull": ["$importo_totale", {"$ifNull": ["$total_amount", 0]}]}}},
                "fatture_non_pagate": {"$sum": {"$cond": [{"$ne": ["$pagato", True]}, {"$toDouble": {"$ifNull": ["$importo_totale", {"$ifNull": ["$total_amount", 0]}]}}, 0]}}
            }}
        ]
        
        try:
            invoice_stats = await db["invoices"].aggregate(stats_pipeline, allowDiskUse=True).to_list(1000)
            
            for stat in invoice_stats:
                piva = stat.get("_id")
                if piva and piva in suppliers_map:
                    suppliers_map[piva]["fatture_count"] = stat.get("fatture_count", 0)
                    suppliers_map[piva]["fatture_totale"] = stat.get("fatture_totale", 0)
                    suppliers_map[piva]["fatture_non_pagate"] = stat.get("fatture_non_pagate", 0)
                    suppliers_map[piva]["source"] = "merged"
        except Exception as e:
            logger.warning(f"Error loading invoice stats: {e}")
    
    suppliers = list(suppliers_map.values())
    suppliers.sort(key=lambda x: x.get("fatture_count", 0), reverse=True)
    
    if use_cache and not search and not metodo_pagamento and attivo is None:
        await cache.set(cache_key, suppliers, SUPPLIERS_CACHE_TTL)
    
    return suppliers[skip:skip+limit]


@router.get("/stats")
async def get_suppliers_stats() -> Dict[str, Any]:
    """Statistiche fornitori aggregate."""
    db = Database.get_db()
    
    total = await db[Collections.SUPPLIERS].count_documents({})
    active = await db[Collections.SUPPLIERS].count_documents({"attivo": True})
    
    pipeline = [
        {"$group": {"_id": "$metodo_pagamento", "count": {"$sum": 1}}}
    ]
    by_method = await db[Collections.SUPPLIERS].aggregate(pipeline).to_list(100)
    
    return {
        "totale": total,
        "attivi": active,
        "inattivi": total - active,
        "per_metodo_pagamento": {item["_id"] or "non_definito": item["count"] for item in by_method}
    }


@router.get("/scadenze")
async def get_payment_deadlines(days_ahead: int = Query(30, ge=1, le=365)) -> Dict[str, Any]:
    """Ritorna le fatture in scadenza nei prossimi N giorni."""
    db = Database.get_db()
    
    today = datetime.now(timezone.utc)
    deadline = today + timedelta(days=days_ahead)
    
    pipeline = [
        {
            "$match": {
                "pagato": {"$ne": True},
                "data_scadenza": {"$gte": today.isoformat(), "$lte": deadline.isoformat()}
            }
        },
        {"$sort": {"data_scadenza": 1}},
        {"$project": {"_id": 0}}
    ]
    
    invoices = await db[Collections.INVOICES].aggregate(pipeline).to_list(1000)
    
    by_supplier = {}
    for inv in invoices:
        piva = inv.get("cedente_piva", "sconosciuto")
        if piva not in by_supplier:
            by_supplier[piva] = {"fornitore": inv.get("cedente_denominazione", ""), "fatture": [], "totale": 0}
        by_supplier[piva]["fatture"].append(inv)
        by_supplier[piva]["totale"] += inv.get("importo_totale", 0)
    
    critical_deadline = today + timedelta(days=7)
    critical = [inv for inv in invoices if inv.get("data_scadenza", "") <= critical_deadline.isoformat()]
    
    return {
        "totale_fatture": len(invoices),
        "totale_importo": sum(inv.get("importo_totale", 0) for inv in invoices),
        "critiche_7gg": len(critical),
        "per_fornitore": by_supplier,
        "fatture": invoices
    }


@router.post("/unifica-collection")
async def unifica_fornitori_collection() -> Dict[str, Any]:
    """Unifica le collection 'fornitori' e 'suppliers'."""
    from app.scripts.unifica_fornitori_suppliers import unifica_fornitori_suppliers
    return await unifica_fornitori_suppliers()


@router.get("/verifica-unificazione")
async def verifica_unificazione_stato() -> Dict[str, Any]:
    """Verifica lo stato dell'unificazione delle collection."""
    from app.scripts.unifica_fornitori_suppliers import verifica_unificazione
    return await verifica_unificazione()


@router.get("/{supplier_id}")
async def get_supplier(supplier_id: str) -> Dict[str, Any]:
    """Dettaglio singolo fornitore."""
    db = Database.get_db()
    
    supplier = await db[Collections.SUPPLIERS].find_one(
        {"$or": [{"id": supplier_id}, {"partita_iva": supplier_id}]},
        {"_id": 0}
    )
    
    if not supplier:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    
    piva = supplier.get("partita_iva")
    if piva:
        invoices = await db[Collections.INVOICES].find(
            {"cedente_piva": piva},
            {"_id": 0}
        ).sort("data_fattura", -1).limit(20).to_list(20)
        supplier["fatture_recenti"] = invoices
    
    return supplier


@router.put("/{supplier_id}")
async def update_supplier(supplier_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Aggiorna dati fornitore incluso metodo pagamento."""
    db = Database.get_db()
    
    data.pop("id", None)
    data.pop("partita_iva", None)
    data.pop("created_at", None)
    
    metodo_configurato = False
    if "metodo_pagamento" in data:
        if data["metodo_pagamento"] not in PAYMENT_METHODS:
            raise HTTPException(status_code=400, detail="Metodo pagamento non valido")
        metodo_configurato = data["metodo_pagamento"] is not None and data["metodo_pagamento"] != ""
    
    if "termini_pagamento" in data:
        term = next((t for t in PAYMENT_TERMS if t["code"] == data["termini_pagamento"]), None)
        if term:
            data["giorni_pagamento"] = term["days"]
    
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    supplier = await db[Collections.SUPPLIERS].find_one(
        {"$or": [{"id": supplier_id}, {"partita_iva": supplier_id}]},
        {"partita_iva": 1}
    )
    
    if not supplier:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    
    result = await db[Collections.SUPPLIERS].update_one(
        {"$or": [{"id": supplier_id}, {"partita_iva": supplier_id}]},
        {"$set": data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    
    alerts_risolti = 0
    if metodo_configurato and supplier.get("partita_iva"):
        alert_result = await db["alerts"].update_many(
            {
                "tipo": "fornitore_senza_metodo_pagamento",
                "fornitore_piva": supplier["partita_iva"],
                "risolto": False
            },
            {"$set": {
                "risolto": True,
                "risolto_il": datetime.now(timezone.utc).isoformat(),
                "note_risoluzione": f"Metodo pagamento configurato: {data.get('metodo_pagamento')}"
            }}
        )
        alerts_risolti = alert_result.modified_count
    
    prodotti_rimossi = 0
    if data.get("esclude_magazzino") == True:
        piva = supplier.get("partita_iva")
        supplier_id_db = supplier.get("id") or supplier.get("_id")
        
        result_stocks = await db["warehouse_stocks"].delete_many({
            "$or": [{"supplier_piva": piva}, {"supplier_id": str(supplier_id_db)}, {"fornitore_piva": piva}]
        })
        prodotti_rimossi += result_stocks.deleted_count
        
        result_inv = await db["warehouse_inventory"].delete_many({
            "$or": [{"supplier_piva": piva}, {"supplier_id": str(supplier_id_db)}, {"fornitore_piva": piva}]
        })
        prodotti_rimossi += result_inv.deleted_count
    
    return {
        "message": "Fornitore aggiornato con successo",
        "alerts_risolti": alerts_risolti,
        "prodotti_rimossi_magazzino": prodotti_rimossi
    }


@router.post("/{supplier_id}/toggle-active")
async def toggle_supplier_active(supplier_id: str) -> Dict[str, Any]:
    """Attiva/disattiva fornitore."""
    db = Database.get_db()
    
    supplier = await db[Collections.SUPPLIERS].find_one(
        {"$or": [{"id": supplier_id}, {"partita_iva": supplier_id}]}
    )
    
    if not supplier:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    
    new_status = not supplier.get("attivo", True)
    
    await db[Collections.SUPPLIERS].update_one(
        {"_id": supplier["_id"]},
        {"$set": {"attivo": new_status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    await cache.clear_pattern(SUPPLIERS_CACHE_KEY)
    
    return {"message": f"Fornitore {'attivato' if new_status else 'disattivato'}", "attivo": new_status}


@router.delete("/{supplier_id}")
async def delete_supplier(supplier_id: str, force: bool = Query(False)) -> Dict[str, str]:
    """Elimina fornitore. Se force=False e ci sono fatture collegate, blocca."""
    db = Database.get_db()
    
    supplier = await db[Collections.SUPPLIERS].find_one(
        {"$or": [{"id": supplier_id}, {"partita_iva": supplier_id}]}
    )
    
    if not supplier:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    
    piva = supplier.get("partita_iva")
    if piva and not force:
        fatture_count = await db[Collections.INVOICES].count_documents({"cedente_piva": piva})
        if fatture_count > 0:
            raise HTTPException(
                status_code=400, 
                detail=f"Fornitore ha {fatture_count} fatture collegate. Usa force=true per eliminare comunque."
            )
    
    await db[Collections.SUPPLIERS].delete_one({"_id": supplier["_id"]})
    await cache.clear_pattern(SUPPLIERS_CACHE_KEY)
    
    return {"message": "Fornitore eliminato"}


@router.get("/{supplier_id}/fatturato")
async def get_supplier_fatturato(
    supplier_id: str,
    anno: int = Query(..., ge=2015, le=2030)
) -> Dict[str, Any]:
    """Calcola il fatturato totale di un fornitore per un anno."""
    db = Database.get_db()
    
    supplier = await db[Collections.SUPPLIERS].find_one(
        {"$or": [{"id": supplier_id}, {"partita_iva": supplier_id}]},
        {"_id": 0}
    )
    
    if not supplier:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    
    piva = supplier.get("partita_iva")
    if not piva:
        return {
            "fornitore": supplier.get("denominazione") or supplier.get("ragione_sociale", ""),
            "anno": anno,
            "totale_fatturato": 0,
            "numero_fatture": 0
        }
    
    data_inizio = f"{anno}-01-01"
    data_fine = f"{anno}-12-31"
    
    pipeline = [
        {
            "$match": {
                "$and": [
                    {"$or": [{"cedente_piva": piva}, {"supplier_vat": piva}]},
                    {"$or": [
                        {"data_fattura": {"$gte": data_inizio, "$lte": data_fine}},
                        {"data": {"$gte": data_inizio, "$lte": data_fine}}
                    ]}
                ]
            }
        },
        {
            "$addFields": {
                "mese": {
                    "$month": {
                        "$dateFromString": {
                            "dateString": {"$ifNull": ["$data_fattura", "$data"]},
                            "onError": None
                        }
                    }
                }
            }
        },
        {
            "$group": {
                "_id": "$mese",
                "totale": {"$sum": "$importo_totale"},
                "count": {"$sum": 1},
                "pagate": {"$sum": {"$cond": [{"$eq": ["$pagato", True]}, 1, 0]}}
            }
        },
        {"$sort": {"_id": 1}}
    ]
    
    try:
        result = await db[Collections.INVOICES].aggregate(pipeline).to_list(12)
    except Exception as e:
        logger.warning(f"Errore aggregation fatturato: {e}")
        result = []
    
    mesi_nomi = ["", "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", 
                 "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
    
    dettaglio_mensile = []
    totale_fatturato = 0
    totale_fatture = 0
    
    for item in result:
        mese_num = item.get("_id")
        if mese_num and 1 <= mese_num <= 12:
            dettaglio_mensile.append({
                "mese": mese_num,
                "mese_nome": mesi_nomi[mese_num],
                "totale": round(item.get("totale", 0), 2),
                "numero_fatture": item.get("count", 0)
            })
            totale_fatturato += item.get("totale", 0)
            totale_fatture += item.get("count", 0)
    
    return {
        "fornitore": supplier.get("denominazione") or supplier.get("ragione_sociale", ""),
        "partita_iva": piva,
        "anno": anno,
        "totale_fatturato": round(totale_fatturato, 2),
        "numero_fatture": totale_fatture,
        "dettaglio_mensile": dettaglio_mensile
    }


@router.get("/{supplier_id}/iban-from-invoices")
async def get_supplier_iban_from_invoices(supplier_id: str) -> Dict[str, Any]:
    """Ritorna tutti gli IBAN trovati nelle fatture di un fornitore."""
    db = Database.get_db()
    
    supplier = await db[Collections.SUPPLIERS].find_one(
        {"$or": [{"id": supplier_id}, {"partita_iva": supplier_id}]},
        {"_id": 0, "partita_iva": 1, "denominazione": 1, "ragione_sociale": 1, "iban": 1, "iban_lista": 1}
    )
    
    if not supplier:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    
    piva = supplier.get("partita_iva")
    
    pipeline = [
        {
            "$match": {
                "cedente_piva": piva,
                "pagamento.iban": {"$exists": True, "$ne": "", "$ne": None}
            }
        },
        {
            "$project": {
                "_id": 0,
                "iban": "$pagamento.iban",
                "data_fattura": 1,
                "numero_fattura": 1,
                "importo_totale": 1
            }
        },
        {"$sort": {"data_fattura": -1}}
    ]
    
    fatture_con_iban = await db[Collections.INVOICES].aggregate(pipeline).to_list(100)
    iban_unici = list(set([f.get("iban") for f in fatture_con_iban if f.get("iban")]))
    
    return {
        "fornitore": supplier.get("denominazione") or supplier.get("ragione_sociale", ""),
        "partita_iva": piva,
        "iban_principale": supplier.get("iban", ""),
        "iban_lista_salvata": supplier.get("iban_lista", []),
        "iban_da_fatture": iban_unici,
        "fatture_con_iban": fatture_con_iban[:20]
    }


@router.put("/{supplier_id}/metodo-pagamento")
async def update_supplier_payment_method(
    supplier_id: str,
    metodo_pagamento: str = Body(..., embed=True)
) -> Dict[str, Any]:
    """Aggiorna il metodo di pagamento di un fornitore."""
    db = Database.get_db()
    
    metodi_validi = ["contanti", "bonifico", "assegno", "rid", "riba", "cassa", "banca"]
    metodo_lower = metodo_pagamento.lower().strip()
    
    if metodo_lower in ["cassa", "cash"]:
        metodo_lower = "contanti"
    elif metodo_lower in ["banca", "bank", "bon"]:
        metodo_lower = "bonifico"
    
    if metodo_lower not in metodi_validi:
        raise HTTPException(status_code=400, detail=f"Metodo non valido. Ammessi: {metodi_validi}")
    
    result = await db[Collections.SUPPLIERS].update_one(
        {"$or": [{"id": supplier_id}, {"partita_iva": supplier_id}]},
        {"$set": {"metodo_pagamento": metodo_lower, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    
    try:
        await cache.delete("suppliers_list_default")
    except Exception:
        pass
    
    return {"success": True, "metodo_pagamento": metodo_lower}


@router.put("/{supplier_id}/nome")
async def update_supplier_nome(supplier_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Aggiorna il nome/denominazione di un fornitore."""
    db = Database.get_db()
    
    denominazione = data.get("denominazione") or data.get("nome")
    if not denominazione:
        raise HTTPException(status_code=400, detail="Denominazione richiesta")
    
    result = await db[Collections.SUPPLIERS].update_one(
        {"$or": [{"id": supplier_id}, {"partita_iva": supplier_id}]},
        {"$set": {
            "denominazione": denominazione,
            "ragione_sociale": denominazione,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    if result.matched_count == 0:
        nuovo = {
            "id": str(uuid.uuid4()),
            "partita_iva": supplier_id,
            "denominazione": denominazione,
            "ragione_sociale": denominazione,
            "metodo_pagamento": "bonifico",
            "attivo": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db[Collections.SUPPLIERS].insert_one(nuovo.copy())
        return {"success": True, "created": True, "denominazione": denominazione}
    
    return {"success": True, "updated": True, "denominazione": denominazione}


@router.get("/{supplier_id}/fatture")
async def get_fatture_fornitore(
    supplier_id: str,
    anno: Optional[int] = Query(None),
    data_da: Optional[str] = Query(None),
    data_a: Optional[str] = Query(None),
    importo_min: Optional[float] = Query(None),
    importo_max: Optional[float] = Query(None),
    tipo: Optional[str] = Query(None),
    limit: int = Query(100),
    skip: int = Query(0)
) -> Dict[str, Any]:
    """Restituisce l'estratto delle fatture di un fornitore."""
    db = Database.get_db()
    
    try:
        fornitore = await db[Collections.SUPPLIERS].find_one(
            {"$or": [{"id": supplier_id}, {"partita_iva": supplier_id}]},
            {"_id": 0}
        )
        
        if not fornitore:
            raise HTTPException(status_code=404, detail="Fornitore non trovato")
        
        partita_iva = fornitore.get("partita_iva")
        
        query = {
            "$or": [
                {"fornitore_partita_iva": partita_iva},
                {"supplier_vat": partita_iva},
                {"cedente_piva": partita_iva}
            ]
        }
        
        if anno:
            query["$or"] = [
                {"data_documento": {"$regex": f"^{anno}"}},
                {"invoice_date": {"$regex": f"^{anno}"}}
            ]
        
        if tipo and tipo != "tutti":
            if tipo == "nota_credito":
                query["tipo_documento"] = {"$in": ["TD04", "TD05", "NC"]}
            elif tipo == "fattura":
                query["tipo_documento"] = {"$nin": ["TD04", "TD05", "NC"]}
        
        fatture = await db["invoices"].find(query, {"_id": 0}).sort("data_documento", -1).skip(skip).limit(limit).to_list(limit)
        totale = await db["invoices"].count_documents(query)
        
        estratto = []
        totale_importo = 0
        for f in fatture:
            importo = f.get("importo_totale") or f.get("total_amount") or 0
            estratto.append({
                "id": f.get("id"),
                "data": f.get("data_documento") or f.get("invoice_date") or "",
                "numero": f.get("numero_documento") or f.get("invoice_number") or "",
                "importo_totale": importo,
                "pagato": f.get("pagato", False),
                "metodo_pagamento": f.get("metodo_pagamento") or fornitore.get("metodo_pagamento") or "-"
            })
            totale_importo += importo
        
        return {
            "fornitore": {
                "id": fornitore.get("id"),
                "partita_iva": partita_iva,
                "ragione_sociale": fornitore.get("ragione_sociale") or fornitore.get("denominazione")
            },
            "estratto": estratto,
            "totali": {
                "numero_documenti": totale,
                "importo_totale": round(totale_importo, 2)
            },
            "pagination": {"total": totale, "limit": limit, "skip": skip}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Errore recupero fatture fornitore {supplier_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
