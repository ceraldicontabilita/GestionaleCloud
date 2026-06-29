"""
Router per operazioni di manutenzione dati.
Contiene endpoint per ricostruzione, pulizia e validazione dati.
"""
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from datetime import datetime, timezone
import logging
import re

from app.database import Database

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/ricostruisci-assegni")
async def ricostruisci_dati_assegni() -> Dict[str, Any]:
    """
    Ricostruisce dati mancanti negli assegni:
    - Trova beneficiari da fatture associate
    - Associa fatture per importo
    - Aggiorna date fattura
    """
    db = Database.get_db()
    
    risultato = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "beneficiari_trovati": 0,
        "fatture_associate": 0,
        "date_aggiornate": 0,
        "errori": []
    }
    
    try:
        # 1. Trova beneficiari da numero fattura
        assegni_senza_ben = await db.assegni.find({
            "$or": [
                {"beneficiario": None},
                {"beneficiario": ""},
                {"beneficiario": "-"}
            ],
            "numero_fattura": {"$exists": True, "$nin": [None, ""]}
        }).to_list(1000)
        
        for ass in assegni_senza_ben:
            num_fatt = ass.get("numero_fattura")
            fattura = await db.invoices.find_one({
                "$or": [
                    {"invoice_number": num_fatt},
                    {"numero_fattura": str(num_fatt)}
                ]
            })
            
            if fattura:
                fornitore = fattura.get("supplier_name") or fattura.get("fornitore") or ""
                if isinstance(fornitore, dict):
                    fornitore = fornitore.get("name", "")
                
                if fornitore:
                    await db.assegni.update_one(
                        {"id": ass["id"]},
                        {"$set": {
                            "beneficiario": fornitore,
                            "fattura_id": fattura.get("id"),
                            "data_fattura": fattura.get("invoice_date") or fattura.get("data_fattura"),
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    risultato["beneficiari_trovati"] += 1
        
        # 2. Associa fatture per importo esatto
        assegni_senza_fatt = await db.assegni.find({
            "fattura_id": {"$in": [None, ""]},
            "importo": {"$gt": 0}
        }).to_list(1000)
        
        for ass in assegni_senza_fatt:
            importo = round(float(ass.get("importo") or 0), 2)
            
            fattura = await db.invoices.find_one({
                "total_amount": {"$gte": importo - 0.5, "$lte": importo + 0.5}
            })
            
            if fattura:
                fornitore = fattura.get("supplier_name") or fattura.get("fornitore") or ""
                if isinstance(fornitore, dict):
                    fornitore = fornitore.get("name", "")
                
                await db.assegni.update_one(
                    {"id": ass["id"]},
                    {"$set": {
                        "fattura_id": fattura.get("id"),
                        "numero_fattura": fattura.get("invoice_number"),
                        "beneficiario": ass.get("beneficiario") or fornitore,
                        "data_fattura": fattura.get("invoice_date"),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                risultato["fatture_associate"] += 1
        
        # 3. Aggiorna date fattura mancanti
        assegni_senza_data = await db.assegni.find({
            "fattura_id": {"$exists": True, "$nin": [None, ""]},
            "$or": [
                {"data_fattura": None},
                {"data_fattura": ""},
                {"data_fattura": {"$exists": False}}
            ]
        }).to_list(1000)
        
        for ass in assegni_senza_data:
            fattura = await db.invoices.find_one({"id": ass.get("fattura_id")})
            if fattura:
                data_fatt = fattura.get("invoice_date") or fattura.get("data_fattura")
                if data_fatt:
                    await db.assegni.update_one(
                        {"id": ass["id"]},
                        {"$set": {
                            "data_fattura": data_fatt,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    risultato["date_aggiornate"] += 1
        
        logger.info(f"✅ Ricostruzione assegni completata: {risultato}")
        
    except Exception as e:
        logger.error(f"Errore ricostruzione assegni: {e}")
        risultato["errori"].append(str(e))
    
    return risultato


@router.post("/ricostruisci-f24")
async def ricostruisci_dati_f24() -> Dict[str, Any]:
    """
    Ricostruisce dati F24:
    - Corregge codici tributo malformati
    - Associa movimenti bancari
    - Riconcilia automaticamente
    """
    db = Database.get_db()
    
    risultato = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "f24_corretti": 0,
        "riconciliazioni_auto": 0,
        "errori": []
    }
    
    try:
        # Correggi F24 con dati mancanti
        f24_list = await db.f24.find({}).to_list(5000)
        
        for f24 in f24_list:
            updates = {}
            
            # Calcola totale se mancante
            if not f24.get("totale") and f24.get("tributi"):
                totale = sum(float(t.get("importo", 0)) for t in f24.get("tributi", []))
                updates["totale"] = totale
            
            # Normalizza data
            if f24.get("data_scadenza") and not f24.get("data"):
                updates["data"] = f24.get("data_scadenza")
            
            if updates:
                await db.f24.update_one(
                    {"id": f24.get("id")},
                    {"$set": {**updates, "updated_at": datetime.now(timezone.utc).isoformat()}}
                )
                risultato["f24_corretti"] += 1
        
        # Riconcilia F24 con movimenti bancari
        f24_non_ric = await db.f24.find({
            "$or": [
                {"riconciliato": False},
                {"riconciliato": {"$exists": False}}
            ],
            "totale": {"$gt": 0}
        }).to_list(1000)
        
        for f24 in f24_non_ric:
            importo = float(f24.get("totale") or 0)
            data = f24.get("data") or f24.get("data_scadenza")
            
            # Cerca movimento bancario corrispondente
            movimento = await db.estratto_conto_movimenti.find_one({
                "importo": {"$gte": -importo - 1, "$lte": -importo + 1},
                "$or": [
                    {"descrizione": {"$regex": "F24", "$options": "i"}},
                    {"causale": {"$regex": "F24", "$options": "i"}},
                    {"descrizione_originale": {"$regex": "F24", "$options": "i"}}
                ]
            })
            
            if movimento:
                await db.f24.update_one(
                    {"id": f24.get("id")},
                    {"$set": {
                        "riconciliato": True,
                        "movimento_id": movimento.get("id"),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                risultato["riconciliazioni_auto"] += 1
        
        logger.info(f"✅ Ricostruzione F24 completata: {risultato}")
        
    except Exception as e:
        logger.error(f"Errore ricostruzione F24: {e}")
        risultato["errori"].append(str(e))
    
    return risultato


@router.post("/ricostruisci-fatture")
async def ricostruisci_dati_fatture() -> Dict[str, Any]:
    """
    Ricostruisce dati fatture:
    - Corregge campi mancanti (date, importi)
    - Associa fornitori da P.IVA o nome
    - Imposta metodo pagamento a "Bonifico" se mancante
    - Rimuove duplicati
    """
    db = Database.get_db()
    
    risultato = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "campi_corretti": 0,
        "fornitori_associati": 0,
        "metodo_pagamento_impostato": 0,
        "duplicati_rimossi": 0,
        "errori": []
    }
    
    try:
        # 0. Imposta metodo pagamento = "Bonifico" per fatture senza metodo
        fatture_senza_metodo = await db.invoices.find({
            "$or": [
                {"metodo_pagamento": None},
                {"metodo_pagamento": ""},
                {"metodo_pagamento": {"$exists": False}},
                {"payment_method": None},
                {"payment_method": ""},
                {"payment_method": {"$exists": False}}
            ]
        }).to_list(10000)
        
        for f in fatture_senza_metodo:
            await db.invoices.update_one(
                {"id": f.get("id")},
                {"$set": {
                    "metodo_pagamento": "Bonifico",
                    "payment_method": "bank_transfer",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            risultato["metodo_pagamento_impostato"] += 1
        
        # 1. Correggi campi mancanti
        fatture = await db.invoices.find({
            "$or": [
                {"total_amount": None},
                {"total_amount": 0},
                {"supplier_name": None},
                {"supplier_name": ""}
            ]
        }).to_list(5000)
        
        for f in fatture:
            updates = {}
            
            # Calcola totale da imponibile + IVA
            if not f.get("total_amount") or f.get("total_amount") == 0:
                imponibile = float(f.get("imponibile") or f.get("taxable_amount") or 0)
                iva = float(f.get("iva") or f.get("vat_amount") or 0)
                if imponibile > 0:
                    updates["total_amount"] = imponibile + iva
            
            # Trova fornitore da P.IVA
            if not f.get("supplier_name") and f.get("supplier_vat"):
                fornitore = await db.fornitori.find_one({
                    "$or": [
                        {"partita_iva": f.get("supplier_vat")},
                        {"piva": f.get("supplier_vat")}
                    ]
                })
                if fornitore:
                    updates["supplier_name"] = fornitore.get("nome") or fornitore.get("ragione_sociale")
                    updates["supplier_id"] = fornitore.get("id")
            
            if updates:
                await db.invoices.update_one(
                    {"id": f.get("id")},
                    {"$set": {**updates, "updated_at": datetime.now(timezone.utc).isoformat()}}
                )
                risultato["campi_corretti"] += 1
        
        # 2. Associa fornitori mancanti
        fatture_senza_forn = await db.invoices.find({
            "supplier_id": {"$in": [None, ""]},
            "supplier_name": {"$exists": True, "$nin": [None, ""]}
        }).to_list(5000)
        
        for f in fatture_senza_forn:
            nome = f.get("supplier_name", "")
            if isinstance(nome, dict):
                nome = nome.get("name", "")
            
            if nome:
                fornitore = await db.fornitori.find_one({
                    "$or": [
                        {"nome": {"$regex": nome[:20], "$options": "i"}},
                        {"ragione_sociale": {"$regex": nome[:20], "$options": "i"}}
                    ]
                })
                
                if fornitore:
                    await db.invoices.update_one(
                        {"id": f.get("id")},
                        {"$set": {
                            "supplier_id": fornitore.get("id"),
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                    risultato["fornitori_associati"] += 1
        
        logger.info(f"✅ Ricostruzione fatture completata: {risultato}")
        
    except Exception as e:
        logger.error(f"Errore ricostruzione fatture: {e}")
        risultato["errori"].append(str(e))
    
    return risultato


@router.post("/ricostruisci-corrispettivi")
async def ricostruisci_corrispettivi() -> Dict[str, Any]:
    """
    Ricostruisce dati corrispettivi:
    - Ricalcola IVA mancante
    - Normalizza date
    - Rimuove duplicati
    """
    db = Database.get_db()
    
    risultato = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "iva_ricalcolata": 0,
        "duplicati_rimossi": 0,
        "errori": []
    }
    
    try:
        # Ricalcola IVA mancante
        corr_senza_iva = await db.corrispettivi.find({
            "$or": [
                {"iva": None},
                {"iva": 0},
                {"iva": {"$exists": False}}
            ],
            "imponibile": {"$gt": 0}
        }).to_list(5000)
        
        for c in corr_senza_iva:
            imponibile = float(c.get("imponibile") or 0)
            aliquota = float(c.get("aliquota_iva") or 22)  # Default 22%
            
            iva = round(imponibile * aliquota / 100, 2)
            totale = imponibile + iva
            
            await db.corrispettivi.update_one(
                {"id": c.get("id")},
                {"$set": {
                    "iva": iva,
                    "totale": totale,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            risultato["iva_ricalcolata"] += 1
        
        # Trova e rimuovi duplicati (stesso importo, stessa data)
        pipeline = [
            {"$group": {
                "_id": {"data": "$data", "imponibile": "$imponibile"},
                "count": {"$sum": 1},
                "ids": {"$push": "$id"}
            }},
            {"$match": {"count": {"$gt": 1}}}
        ]
        
        duplicati = await db.corrispettivi.aggregate(pipeline).to_list(1000)
        
        for dup in duplicati:
            ids_da_eliminare = dup["ids"][1:]  # Mantieni il primo
            for did in ids_da_eliminare:
                await db.corrispettivi.delete_one({"id": did})
                risultato["duplicati_rimossi"] += 1
        
        logger.info(f"✅ Ricostruzione corrispettivi completata: {risultato}")
        
    except Exception as e:
        logger.error(f"Errore ricostruzione corrispettivi: {e}")
        risultato["errori"].append(str(e))
    
    return risultato


@router.post("/ricostruisci-salari")
async def ricostruisci_salari() -> Dict[str, Any]:
    """
    Ricostruisce dati salari/cedolini:
    - Associa dipendenti mancanti
    - Corregge importi netti
    - Valida date
    """
    db = Database.get_db()
    
    risultato = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dipendenti_associati": 0,
        "netti_corretti": 0,
        "errori": []
    }
    
    try:
        # Associa dipendenti da codice fiscale
        cedolini_senza_dip = await db.cedolini.find({
            "$or": [
                {"dipendente_id": None},
                {"dipendente_id": ""},
                {"dipendente_id": {"$exists": False}}
            ],
            "codice_fiscale": {"$exists": True, "$nin": [None, ""]}
        }).to_list(5000)
        
        for c in cedolini_senza_dip:
            cf = c.get("codice_fiscale", "").upper().strip()
            
            dipendente = await db.employees.find_one({
                "codice_fiscale": {"$regex": f"^{cf}$", "$options": "i"}
            })
            
            if dipendente:
                await db.cedolini.update_one(
                    {"id": c.get("id")},
                    {"$set": {
                        "dipendente_id": dipendente.get("id"),
                        "dipendente_nome": dipendente.get("nome_completo") or f"{dipendente.get('cognome', '')} {dipendente.get('nome', '')}",
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                risultato["dipendenti_associati"] += 1
        
        # Correggi netti mancanti (lordo - trattenute)
        cedolini_senza_netto = await db.cedolini.find({
            "$or": [
                {"netto": None},
                {"netto": 0},
                {"netto": {"$exists": False}}
            ],
            "lordo": {"$gt": 0}
        }).to_list(5000)
        
        for c in cedolini_senza_netto:
            lordo = float(c.get("lordo") or 0)
            trattenute = float(c.get("trattenute") or c.get("ritenute") or 0)
            netto = lordo - trattenute
            
            if netto > 0:
                await db.cedolini.update_one(
                    {"id": c.get("id")},
                    {"$set": {
                        "netto": netto,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                risultato["netti_corretti"] += 1
        
        logger.info(f"✅ Ricostruzione salari completata: {risultato}")
        
    except Exception as e:
        logger.error(f"Errore ricostruzione salari: {e}")
        risultato["errori"].append(str(e))
    
    return risultato


@router.get("/stato-collezioni")
async def get_stato_collezioni() -> Dict[str, Any]:
    """
    Ritorna lo stato di tutte le collezioni con statistiche.
    """
    db = Database.get_db()
    
    collezioni = {
        "assegni": {"collection": "assegni", "tipo": "pagamenti"},
        "bonifici": {"collection": "bonifici", "tipo": "pagamenti"},
        "cedolini": {"collection": "cedolini", "tipo": "hr"},
        "corrispettivi": {"collection": "corrispettivi", "tipo": "vendite"},
        "dipendenti": {"collection": "employees", "tipo": "hr"},
        "estratto_conto": {"collection": "estratto_conto_movimenti", "tipo": "banca"},
        "f24": {"collection": "f24", "tipo": "fisco"},
        "fatture": {"collection": "invoices", "tipo": "acquisti"},
        "fornitori": {"collection": "suppliers", "tipo": "anagrafiche"},
        "verbali": {"collection": "verbali_noleggio", "tipo": "noleggio"},
        "veicoli": {"collection": "veicoli_noleggio", "tipo": "noleggio"},
    }
    
    stato = {}
    
    for nome, config in collezioni.items():
        try:
            count = await db[config["collection"]].count_documents({})
            stato[nome] = {
                "collection": config["collection"],
                "tipo": config["tipo"],
                "documenti": count
            }
        except Exception as e:
            stato[nome] = {"error": str(e)}
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "collezioni": stato,
        "totale_collezioni": len(stato)
    }
