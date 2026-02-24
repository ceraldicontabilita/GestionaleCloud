"""
Suppliers IBAN management endpoints.
Ricerca e sincronizzazione IBAN da fatture.
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from datetime import datetime, timezone
import re
import asyncio
import httpx

from app.database import Database, Collections
from app.middleware.performance import cache
from .common import SUPPLIERS_CACHE_KEY, METODI_BANCARI, logger

router = APIRouter()


@router.post("/ricerca-iban-web")
async def ricerca_iban_fornitori_web() -> Dict[str, Any]:
    """
    Cerca gli IBAN dei fornitori utilizzando TUTTE le fonti disponibili:
    1. Fatture XML già importate (fonte primaria - dati reali)
    2. API pubbliche (VIES, OpenCorporates)
    3. Database locale
    
    Questo è l'endpoint principale per risolvere i fornitori senza IBAN.
    """
    db = Database.get_db()
    
    # Trova fornitori con metodo bancario ma senza IBAN
    fornitori_senza_iban = await db[Collections.SUPPLIERS].find({
        "metodo_pagamento": {"$in": METODI_BANCARI},
        "$or": [
            {"iban": None},
            {"iban": ""},
            {"iban": {"$exists": False}}
        ],
        "partita_iva": {"$exists": True, "$ne": "", "$ne": None}
    }, {"_id": 0, "id": 1, "partita_iva": 1, "ragione_sociale": 1, "denominazione": 1}).to_list(500)
    
    risultato = {
        "totale_fornitori": len(fornitori_senza_iban),
        "iban_trovati": 0,
        "iban_da_fatture": 0,
        "iban_da_api": 0,
        "non_trovati": 0,
        "errori": 0,
        "dettaglio_trovati": [],
        "dettaglio_non_trovati": []
    }
    
    if not fornitori_senza_iban:
        return {
            "success": True,
            "message": "Tutti i fornitori con metodo bancario hanno già un IBAN configurato",
            **risultato
        }
    
    # Regex per IBAN italiano
    iban_pattern = re.compile(r'IT\d{2}[A-Z]?\d{5}\d{5}[A-Z0-9]{12}', re.IGNORECASE)
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        for fornitore in fornitori_senza_iban:
            piva = fornitore.get("partita_iva", "")
            nome = fornitore.get("ragione_sociale") or fornitore.get("denominazione") or ""
            fornitore_id = fornitore.get("id")
            
            # Salta P.IVA non italiane (non 11 cifre)
            piva_clean = re.sub(r'[^0-9]', '', str(piva))
            if len(piva_clean) != 11:
                risultato["non_trovati"] += 1
                continue
            
            iban_trovato = None
            fonte = None
            
            try:
                # === FONTE 1: Fatture XML già importate (fonte più affidabile) ===
                fattura_con_iban = await db["invoices"].find_one(
                    {
                        "$or": [{"cedente_piva": piva}, {"supplier_vat": piva}],
                        "pagamento.iban": {"$exists": True, "$ne": "", "$ne": None}
                    },
                    {"pagamento.iban": 1}
                )
                
                if fattura_con_iban and fattura_con_iban.get("pagamento", {}).get("iban"):
                    iban_candidato = fattura_con_iban["pagamento"]["iban"].upper().strip()
                    if iban_pattern.match(iban_candidato) and len(iban_candidato) == 27:
                        iban_trovato = iban_candidato
                        fonte = "fatture_xml"
                        risultato["iban_da_fatture"] += 1
                
                # === FONTE 2: OpenCorporates API (gratuita) ===
                if not iban_trovato:
                    try:
                        oc_url = f"https://api.opencorporates.com/v0.4/companies/search?q={piva}&jurisdiction_code=it"
                        oc_resp = await client.get(oc_url)
                        if oc_resp.status_code == 200:
                            oc_data = oc_resp.json()
                            companies = oc_data.get("results", {}).get("companies", [])
                            if companies:
                                comp = companies[0].get("company", {})
                                if comp.get("name") and not nome:
                                    await db[Collections.SUPPLIERS].update_one(
                                        {"id": fornitore_id},
                                        {"$set": {"ragione_sociale": comp["name"].title()}}
                                    )
                    except Exception as e:
                        logger.debug(f"OpenCorporates error for {piva}: {e}")
                
                # === FONTE 3: Cerca in altre fatture dello stesso fornitore ===
                if not iban_trovato:
                    fatture_alt = await db["invoices"].find(
                        {"$or": [{"cedente_piva": piva}, {"supplier_vat": piva}]},
                        {"raw_xml": 0}
                    ).limit(10).to_list(10)
                    
                    for fat in fatture_alt:
                        for campo in ["pagamento", "dati_pagamento", "payment_data"]:
                            dati = fat.get(campo, {})
                            if isinstance(dati, dict):
                                for k, v in dati.items():
                                    if v and isinstance(v, str) and "IT" in v.upper():
                                        match = iban_pattern.search(v.upper())
                                        if match:
                                            iban_candidato = match.group(0)
                                            if len(iban_candidato) == 27:
                                                iban_trovato = iban_candidato
                                                fonte = "fatture_xml_alt"
                                                risultato["iban_da_fatture"] += 1
                                                break
                            if iban_trovato:
                                break
                        if iban_trovato:
                            break
                
                # Aggiorna fornitore se trovato IBAN
                if iban_trovato:
                    await db[Collections.SUPPLIERS].update_one(
                        {"id": fornitore_id},
                        {"$set": {
                            "iban": iban_trovato,
                            "iban_fonte": fonte,
                            "iban_data_ricerca": datetime.now(timezone.utc).isoformat(),
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    
                    risultato["iban_trovati"] += 1
                    risultato["dettaglio_trovati"].append({
                        "partita_iva": piva,
                        "nome": nome,
                        "iban": iban_trovato,
                        "fonte": fonte
                    })
                    logger.info(f"IBAN trovato per {nome}: {iban_trovato[:10]}... (fonte: {fonte})")
                else:
                    risultato["non_trovati"] += 1
                    if len(risultato["dettaglio_non_trovati"]) < 50:
                        risultato["dettaglio_non_trovati"].append({
                            "partita_iva": piva,
                            "nome": nome,
                            "motivo": "Non presente nelle fatture importate"
                        })
                
                await asyncio.sleep(0.1)
                
            except Exception as e:
                risultato["errori"] += 1
                logger.warning(f"Errore ricerca IBAN {piva}: {e}")
    
    await cache.clear_pattern(SUPPLIERS_CACHE_KEY)
    
    return {
        "success": True,
        "message": f"Ricerca completata: {risultato['iban_trovati']} IBAN trovati su {risultato['totale_fornitori']} fornitori",
        "nota": "Gli IBAN sono stati estratti principalmente dalle fatture XML già importate. Per i fornitori rimanenti, l'IBAN deve essere inserito manualmente o recuperato dalle prossime fatture.",
        **risultato
    }


@router.post("/ricerca-iban-singolo/{supplier_id}")
async def ricerca_iban_singolo_web(supplier_id: str) -> Dict[str, Any]:
    """
    Cerca l'IBAN di un singolo fornitore nelle fatture XML importate.
    """
    db = Database.get_db()
    
    fornitore = await db[Collections.SUPPLIERS].find_one(
        {"$or": [{"id": supplier_id}, {"partita_iva": supplier_id}]},
        {"_id": 0}
    )
    
    if not fornitore:
        raise HTTPException(status_code=404, detail="Fornitore non trovato")
    
    piva = fornitore.get("partita_iva", "")
    nome = fornitore.get("ragione_sociale") or fornitore.get("denominazione") or ""
    
    if not piva:
        raise HTTPException(status_code=400, detail="Fornitore senza Partita IVA")
    
    iban_pattern = re.compile(r'IT\d{2}[A-Z]?\d{5}\d{5}[A-Z0-9]{12}', re.IGNORECASE)
    
    fattura_con_iban = await db["invoices"].find_one(
        {
            "$or": [{"cedente_piva": piva}, {"supplier_vat": piva}],
            "pagamento.iban": {"$exists": True, "$ne": "", "$ne": None}
        },
        {"pagamento.iban": 1}
    )
    
    if fattura_con_iban and fattura_con_iban.get("pagamento", {}).get("iban"):
        iban = fattura_con_iban["pagamento"]["iban"].upper().strip()
        
        if iban_pattern.match(iban) and len(iban) == 27:
            await db[Collections.SUPPLIERS].update_one(
                {"$or": [{"id": supplier_id}, {"partita_iva": supplier_id}]},
                {"$set": {
                    "iban": iban,
                    "iban_fonte": "fatture_xml",
                    "iban_data_ricerca": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            return {
                "success": True,
                "trovato": True,
                "iban": iban,
                "fornitore": nome,
                "partita_iva": piva,
                "fonte": "fatture_xml",
                "message": f"IBAN trovato e salvato per {nome}"
            }
    
    fatture_count = await db["invoices"].count_documents({
        "$or": [{"cedente_piva": piva}, {"supplier_vat": piva}]
    })
    
    return {
        "success": True,
        "trovato": False,
        "iban": None,
        "fornitore": nome,
        "partita_iva": piva,
        "fatture_presenti": fatture_count,
        "message": f"IBAN non trovato nelle {fatture_count} fatture di questo fornitore."
    }


@router.post("/sync-iban")
async def sync_iban_from_invoices() -> Dict[str, Any]:
    """
    Sincronizza gli IBAN dalle fatture ai fornitori.
    Per ogni fornitore, estrae tutti gli IBAN unici presenti nelle sue fatture
    e li aggiunge alla lista iban_lista.
    """
    db = Database.get_db()
    
    pipeline = [
        {
            "$match": {
                "pagamento.iban": {"$exists": True, "$ne": "", "$ne": None}
            }
        },
        {
            "$group": {
                "_id": "$cedente_piva",
                "iban_set": {"$addToSet": "$pagamento.iban"},
                "fornitore_nome": {"$first": "$cedente_denominazione"}
            }
        }
    ]
    
    results = await db[Collections.INVOICES].aggregate(pipeline).to_list(1000)
    
    updated = 0
    fornitori_aggiornati = []
    
    for item in results:
        piva = item.get("_id")
        ibans = item.get("iban_set", [])
        
        if not piva or not ibans:
            continue
        
        supplier = await db[Collections.SUPPLIERS].find_one({"partita_iva": piva})
        
        if not supplier:
            supplier = await db["suppliers"].find_one({"partita_iva": piva})
            if supplier:
                supplier["source"] = "fornitori"
        
        if supplier:
            existing_iban = supplier.get("iban", "")
            existing_list = supplier.get("iban_lista", [])
            
            all_ibans = set(existing_list)
            all_ibans.update(ibans)
            
            if existing_iban:
                all_ibans.discard(existing_iban)
            
            if not existing_iban and all_ibans:
                existing_iban = list(all_ibans)[0]
                all_ibans.discard(existing_iban)
            
            update_data = {
                "iban_lista": list(all_ibans),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            if not supplier.get("iban") and existing_iban:
                update_data["iban"] = existing_iban
            
            result = await db[Collections.SUPPLIERS].update_one(
                {"partita_iva": piva},
                {"$set": update_data}
            )
            
            if result.modified_count > 0:
                updated += 1
                fornitori_aggiornati.append({
                    "partita_iva": piva,
                    "nome": item.get("fornitore_nome", ""),
                    "iban_count": len(all_ibans) + (1 if existing_iban else 0)
                })
    
    await cache.clear_pattern(SUPPLIERS_CACHE_KEY)
    
    return {
        "success": True,
        "fornitori_aggiornati": updated,
        "dettaglio": fornitori_aggiornati[:30]
    }
