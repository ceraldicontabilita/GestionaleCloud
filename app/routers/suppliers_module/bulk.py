"""
Suppliers bulk operations endpoints.
Operazioni massive su fornitori.
"""
from fastapi import APIRouter, Body
from typing import Dict, Any
from datetime import datetime, timezone
import uuid
import httpx
import re
import asyncio

from app.database import Database, Collections
from app.middleware.performance import cache
from .common import logger

router = APIRouter()


@router.post("/aggiorna-tutti-bulk")
async def aggiorna_fornitori_bulk() -> Dict[str, Any]:
    """
    Aggiorna TUTTI i fornitori con dati incompleti cercando P.IVA su fonti esterne.
    Usa: VIES, OpenCorporates, Database locale.
    """
    db = Database.get_db()
    
    fornitori = await db[Collections.SUPPLIERS].find({
        "partita_iva": {"$exists": True, "$ne": "", "$ne": None},
        "$or": [
            {"ragione_sociale": {"$in": [None, ""]}},
            {"comune": {"$in": [None, ""]}},
            {"indirizzo": {"$in": [None, ""]}},
        ]
    }, {"_id": 0, "id": 1, "partita_iva": 1, "ragione_sociale": 1}).to_list(500)
    
    risultato = {
        "totale_processati": 0,
        "aggiornati": 0,
        "non_trovati": 0,
        "errori": 0,
        "dettaglio": []
    }
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for fornitore in fornitori:
            piva = re.sub(r'[^0-9]', '', str(fornitore.get("partita_iva", "")))
            if len(piva) != 11:
                continue
                
            risultato["totale_processati"] += 1
            
            try:
                dati_trovati = {}
                source = None
                
                # === FONTE 1: VIES ===
                try:
                    vies_url = "https://ec.europa.eu/taxation_customs/vies/rest-api/check-vat-number"
                    vies_resp = await client.post(vies_url, json={"countryCode": "IT", "vatNumber": piva})
                    
                    if vies_resp.status_code == 200:
                        vies_data = vies_resp.json()
                        if vies_data.get("valid"):
                            name = vies_data.get("name", "")
                            addr = vies_data.get("address", "")
                            if name and name != "---":
                                dati_trovati["ragione_sociale"] = name.strip().title()
                                source = "VIES"
                            if addr and addr != "---":
                                dati_trovati["indirizzo"] = addr.strip()
                                addr_match = re.search(r'(\d{5})\s+([A-Za-z\s]+?)(?:\s+([A-Z]{2}))?$', addr)
                                if addr_match:
                                    dati_trovati["cap"] = addr_match.group(1)
                                    dati_trovati["comune"] = addr_match.group(2).strip().title()
                                    if addr_match.group(3):
                                        dati_trovati["provincia"] = addr_match.group(3)
                except Exception:
                    pass
                
                # === FONTE 2: OpenCorporates ===
                if not dati_trovati.get("ragione_sociale"):
                    try:
                        oc_url = f"https://api.opencorporates.com/v0.4/companies/search?q={piva}&jurisdiction_code=it"
                        oc_resp = await client.get(oc_url)
                        if oc_resp.status_code == 200:
                            oc_data = oc_resp.json()
                            companies = oc_data.get("results", {}).get("companies", [])
                            if companies:
                                comp = companies[0].get("company", {})
                                if comp.get("name"):
                                    dati_trovati["ragione_sociale"] = comp["name"].title()
                                    source = source or "OpenCorporates"
                                addr = comp.get("registered_address_in_full", "")
                                if addr and not dati_trovati.get("indirizzo"):
                                    dati_trovati["indirizzo"] = addr
                    except Exception:
                        pass
                
                # === FONTE 3: Database locale (fatture) ===
                if not dati_trovati.get("ragione_sociale"):
                    invoice = await db["invoices"].find_one(
                        {"$or": [{"supplier_vat": piva}, {"cedente_piva": piva}]},
                        {"cedente_denominazione": 1, "supplier_name": 1}
                    )
                    if invoice:
                        name = invoice.get("cedente_denominazione") or invoice.get("supplier_name")
                        if name:
                            dati_trovati["ragione_sociale"] = name.strip().title()
                            source = source or "Fatture"
                
                if dati_trovati:
                    dati_trovati["updated_at"] = datetime.now(timezone.utc).isoformat()
                    dati_trovati["dati_completati_da"] = source
                    
                    await db[Collections.SUPPLIERS].update_one(
                        {"id": fornitore["id"]},
                        {"$set": dati_trovati}
                    )
                    risultato["aggiornati"] += 1
                    risultato["dettaglio"].append({
                        "piva": piva,
                        "nome": dati_trovati.get("ragione_sociale", "N/A"),
                        "source": source,
                        "status": "aggiornato"
                    })
                else:
                    risultato["non_trovati"] += 1
                    
                await asyncio.sleep(0.3)
                
            except Exception as e:
                risultato["errori"] += 1
                logger.warning(f"Errore bulk update {piva}: {e}")
    
    return {
        "success": True,
        "message": f"Aggiornati {risultato['aggiornati']} fornitori su {risultato['totale_processati']}",
        **risultato
    }


@router.post("/aggiorna-metodi-bulk")
async def aggiorna_metodi_pagamento_bulk(
    data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Aggiorna in blocco i metodi di pagamento dei fornitori.
    
    Input:
    {
        "fornitori": [{"partita_iva": "...", "metodo_pagamento": "..."}],
        "default_per_mancanti": "bonifico"  // opzionale
    }
    """
    db = Database.get_db()
    
    risultato = {
        "aggiornati": 0,
        "errori": [],
        "gia_impostati": 0
    }
    
    fornitori_list = data.get("fornitori", [])
    default_mancanti = data.get("default_per_mancanti")
    
    for f in fornitori_list:
        piva = f.get("partita_iva")
        metodo = f.get("metodo_pagamento", "").lower().strip()
        
        if not piva or not metodo:
            continue
        
        if metodo in ["cassa", "cash"]:
            metodo = "contanti"
        elif metodo in ["banca", "bank", "bon"]:
            metodo = "bonifico"
        
        try:
            result = await db[Collections.SUPPLIERS].update_one(
                {"partita_iva": piva},
                {"$set": {
                    "metodo_pagamento": metodo,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            if result.modified_count > 0:
                risultato["aggiornati"] += 1
            elif result.matched_count > 0:
                risultato["gia_impostati"] += 1
        except Exception as e:
            risultato["errori"].append(f"{piva}: {str(e)}")
    
    if default_mancanti:
        metodo_default = default_mancanti.lower().strip()
        if metodo_default in ["cassa", "cash"]:
            metodo_default = "contanti"
        elif metodo_default in ["banca", "bank", "bon"]:
            metodo_default = "bonifico"
        
        result = await db[Collections.SUPPLIERS].update_many(
            {"$or": [
                {"metodo_pagamento": {"$exists": False}},
                {"metodo_pagamento": None},
                {"metodo_pagamento": ""},
                {"metodo_pagamento": "N/D"}
            ]},
            {"$set": {
                "metodo_pagamento": metodo_default,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        risultato["aggiornati"] += result.modified_count
        risultato["default_applicato"] = metodo_default
    
    try:
        await cache.delete("suppliers_list_default")
    except Exception:
        pass
    
    return risultato


@router.post("/correggi-nomi-mancanti")
async def correggi_nomi_fornitori_mancanti() -> Dict[str, Any]:
    """
    Corregge i fornitori senza nome cercando il nome dalle fatture.
    """
    db = Database.get_db()
    
    risultato = {
        "corretti": 0,
        "non_trovati": [],
        "gia_ok": 0,
        "errori": []
    }
    
    cursor = db[Collections.SUPPLIERS].find({
        "$or": [
            {"denominazione": {"$in": [None, ""]}},
            {"denominazione": {"$exists": False}},
            {"ragione_sociale": {"$in": [None, ""]}},
            {"ragione_sociale": {"$exists": False}}
        ]
    }, {"_id": 0})
    
    fornitori_senza_nome = await cursor.to_list(500)
    
    fornitori_senza_nome = [
        f for f in fornitori_senza_nome 
        if not (f.get("denominazione") or "").strip() and not (f.get("ragione_sociale") or "").strip()
    ]
    
    for fornitore in fornitori_senza_nome:
        piva = fornitore.get("partita_iva")
        cf = fornitore.get("codice_fiscale")
        
        if not piva and not cf:
            continue
        
        query = {}
        if piva:
            query = {"$or": [{"cedente_piva": piva}, {"supplier_vat": piva}]}
        elif cf:
            query = {"cedente_cf": cf}
        
        fattura = await db["invoices"].find_one(
            query,
            {"_id": 0, "cedente_denominazione": 1, "supplier_name": 1}
        )
        
        if fattura:
            nome = fattura.get("cedente_denominazione") or fattura.get("supplier_name")
            if nome and nome.strip():
                await db[Collections.SUPPLIERS].update_one(
                    {"partita_iva": piva} if piva else {"codice_fiscale": cf},
                    {"$set": {
                        "denominazione": nome.strip(),
                        "ragione_sociale": nome.strip(),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                risultato["corretti"] += 1
            else:
                risultato["non_trovati"].append({"piva": piva, "cf": cf})
        else:
            risultato["non_trovati"].append({"piva": piva, "cf": cf})
    
    try:
        await cache.delete("suppliers_list_default")
    except Exception:
        pass
    
    risultato["totale_senza_nome"] = len(fornitori_senza_nome)
    return risultato


@router.post("/sincronizza-da-fatture")
async def sincronizza_fornitori_da_fatture() -> Dict[str, Any]:
    """
    Sincronizza tutti i fornitori dalle fatture XML al database.
    """
    db = Database.get_db()
    
    risultato = {
        "nuovi": 0,
        "aggiornati": 0,
        "gia_completi": 0,
        "errori": []
    }
    
    pipeline = [
        {"$match": {"$or": [
            {"supplier_vat": {"$exists": True, "$ne": None, "$ne": ""}},
            {"fornitore.partita_iva": {"$exists": True, "$ne": None, "$ne": ""}}
        ]}},
        {"$project": {
            "piva": {"$ifNull": ["$supplier_vat", "$fornitore.partita_iva"]},
            "nome": {"$ifNull": ["$supplier_name", {"$ifNull": ["$fornitore.denominazione", ""]}]},
            "fornitore": 1
        }},
        {"$group": {
            "_id": "$piva",
            "denominazione": {"$first": "$nome"},
            "fornitore_data": {"$first": "$fornitore"},
            "count": {"$sum": 1}
        }}
    ]
    
    fornitori_fatture = await db["invoices"].aggregate(pipeline).to_list(1000)
    
    for f in fornitori_fatture:
        piva = f.get("_id")
        if not piva:
            continue
        
        nome = f.get("denominazione") or f.get("supplier_name") or ""
        if not nome.strip():
            continue
        
        esistente = await db[Collections.SUPPLIERS].find_one(
            {"partita_iva": piva},
            {"_id": 0, "denominazione": 1, "ragione_sociale": 1, "metodo_pagamento": 1}
        )
        
        if esistente:
            nome_esistente = esistente.get("denominazione") or esistente.get("ragione_sociale") or ""
            if nome_esistente.strip():
                risultato["gia_completi"] += 1
                continue
            
            await db[Collections.SUPPLIERS].update_one(
                {"partita_iva": piva},
                {"$set": {
                    "denominazione": nome.strip(),
                    "ragione_sociale": nome.strip(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            risultato["aggiornati"] += 1
        else:
            nuovo = {
                "id": str(uuid.uuid4()),
                "partita_iva": piva,
                "codice_fiscale": f.get("codice_fiscale") or piva,
                "denominazione": nome.strip(),
                "ragione_sociale": nome.strip(),
                "indirizzo": f.get("indirizzo") or "",
                "cap": f.get("cap") or "",
                "comune": f.get("comune") or "",
                "provincia": f.get("provincia") or "",
                "nazione": f.get("nazione") or "IT",
                "pec": f.get("pec") or "",
                "metodo_pagamento": "bonifico",
                "attivo": True,
                "source": "sincronizzazione_fatture",
                "fatture_count": f.get("count", 0),
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await db[Collections.SUPPLIERS].insert_one(nuovo.copy())
            risultato["nuovi"] += 1
    
    try:
        await cache.delete("suppliers_list_default")
    except Exception:
        pass
    
    return risultato
