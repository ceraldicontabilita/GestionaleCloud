"""
Auto-Riparazione Globale
========================
Sistema di verifica e correzione automatica delle relazioni tra dati.
Collega: Verbali ↔ Veicoli ↔ Driver, Fatture ↔ Fornitori, Cedolini ↔ Dipendenti
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from datetime import datetime, timezone
import logging

from app.database import Database

router = APIRouter(prefix="/auto-repair", tags=["Auto Riparazione"])
logger = logging.getLogger(__name__)


@router.post("/globale")
async def auto_riparazione_globale() -> Dict[str, Any]:
    """
    Esegue auto-riparazione globale di tutte le relazioni nel sistema.
    """
    db = Database.get_db()
    
    results = {
        "verbali_sincronizzati": 0,
        "verbali_collegati_driver": 0,
        "cedolini_collegati_dipendenti": 0,
        "fatture_collegate_fornitori": 0,
        "veicoli_collegati_verbali": 0,
        "duplicati_rimossi": 0,
        "errori": [],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    try:
        # 0. SINCRONIZZA VERBALI da verbali_noleggio_completi (che hanno le targhe)
        results["verbali_sincronizzati"] = await _sincronizza_verbali_completi(db)
        
        # 1. COLLEGA VERBALI A DRIVER tramite TARGA
        results["verbali_collegati_driver"] = await _collega_verbali_driver(db)
        
        # 2. COLLEGA CEDOLINI A DIPENDENTI
        results["cedolini_collegati_dipendenti"] = await _collega_cedolini_dipendenti(db)
        
        # 3. COLLEGA FATTURE A FORNITORI
        results["fatture_collegate_fornitori"] = await _collega_fatture_fornitori(db)
        
        # 4. SINCRONIZZA VEICOLI CON VERBALI
        results["veicoli_collegati_verbali"] = await _sincronizza_veicoli_verbali(db)
        
    except Exception as e:
        results["errori"].append(str(e))
        logger.error(f"Errore auto-riparazione: {e}")
    
    return {"success": True, "results": results}


async def _sincronizza_verbali_completi(db) -> int:
    """
    Sincronizza i dati da verbali_noleggio_completi a verbali_noleggio.
    La collezione 'completi' contiene le targhe e altri dati estratti dai PDF.
    """
    sincronizzati = 0
    
    # Prendi tutti i verbali completi (hanno targa, importo, etc)
    completi = await db.verbali_noleggio_completi.find({}).to_list(500)
    
    for vc in completi:
        numero = vc.get("numero_verbale")
        targa = vc.get("targa")
        
        if not numero or not targa:
            continue
        
        # Cerca il verbale corrispondente in verbali_noleggio
        verbale = await db.verbali_noleggio.find_one({"numero_verbale": numero})
        
        update_data = {
            "targa": targa,
            "importo": vc.get("importo"),
            "stato_pagamento": vc.get("stato_pagamento"),
            "anno": vc.get("anno"),
            "descrizione": vc.get("descrizione"),
            "updated_at": datetime.now(timezone.utc)
        }
        # Rimuovi campi None
        update_data = {k: v for k, v in update_data.items() if v is not None}
        
        if verbale:
            # Aggiorna il verbale esistente con i dati completi
            await db.verbali_noleggio.update_one(
                {"_id": verbale["_id"]},
                {"$set": update_data}
            )
            sincronizzati += 1
        else:
            # Crea nuovo verbale dalla collezione completi
            nuovo_verbale = {
                "id": vc.get("id", f"verb_{numero}"),
                "numero_verbale": numero,
                "targa": targa,
                "importo": vc.get("importo"),
                "stato_pagamento": vc.get("stato_pagamento"),
                "anno": vc.get("anno"),
                "descrizione": vc.get("descrizione"),
                "fattura_id": vc.get("fattura_id"),
                "source": "verbali_noleggio_completi",
                "created_at": datetime.now(timezone.utc)
            }
            nuovo_verbale = {k: v for k, v in nuovo_verbale.items() if v is not None}
            await db.verbali_noleggio.insert_one(nuovo_verbale)
            sincronizzati += 1
    
    return sincronizzati


async def _collega_verbali_driver(db) -> int:
    """Collega verbali ai driver tramite targa del veicolo."""
    collegati = 0
    
    # Prendi tutti i veicoli con targa e driver
    veicoli = await db.veicoli_noleggio.find(
        {"targa": {"$exists": True, "$ne": None}, "driver_id": {"$exists": True}},
        {"_id": 0, "targa": 1, "driver": 1, "driver_id": 1}
    ).to_list(100)
    
    # Crea mappa targa -> driver
    targa_driver = {v["targa"].upper(): {"driver": v.get("driver"), "driver_id": v.get("driver_id")} for v in veicoli if v.get("targa")}
    
    # Aggiorna verbali senza driver (con targa presente)
    verbali = await db.verbali_noleggio.find(
        {"targa": {"$exists": True, "$ne": None, "$ne": ""}},
        {"_id": 1, "targa": 1, "driver_id": 1}
    ).to_list(1000)
    
    for verbale in verbali:
        targa = (verbale.get("targa") or "").upper()
        driver_id_esistente = verbale.get("driver_id")
        
        if targa and targa in targa_driver and not driver_id_esistente:
            driver_info = targa_driver[targa]
            await db.verbali_noleggio.update_one(
                {"_id": verbale["_id"]},
                {"$set": {
                    "driver": driver_info["driver"],
                    "driver_id": driver_info["driver_id"],
                    "driver_nome": driver_info["driver"],
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
            collegati += 1
    
    return collegati


async def _collega_cedolini_dipendenti(db) -> int:
    """Collega cedolini ai dipendenti tramite nome."""
    collegati = 0
    
    # Prendi tutti i dipendenti
    dipendenti = await db.employees.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
    
    # Crea mappa nome -> id (normalizzato)
    nome_to_id = {}
    for d in dipendenti:
        nome = (d.get("name") or "").strip().lower()
        if nome:
            nome_to_id[nome] = d.get("id")
            # Aggiungi anche varianti (cognome nome vs nome cognome)
            parts = nome.split()
            if len(parts) >= 2:
                nome_to_id[" ".join(reversed(parts))] = d.get("id")
    
    # Aggiorna cedolini senza dipendente_id
    cedolini = await db.cedolini.find(
        {"dipendente_id": {"$in": [None, ""]}, "employee_nome": {"$exists": True}},
        {"_id": 1, "employee_nome": 1}
    ).to_list(5000)
    
    for cedolino in cedolini:
        nome = (cedolino.get("employee_nome") or "").strip().lower()
        if nome and nome in nome_to_id:
            await db.cedolini.update_one(
                {"_id": cedolino["_id"]},
                {"$set": {
                    "dipendente_id": nome_to_id[nome],
                    "updated_at": datetime.now(timezone.utc)
                }}
            )
            collegati += 1
    
    return collegati


async def _collega_fatture_fornitori(db) -> int:
    """Collega fatture ai fornitori tramite P.IVA."""
    collegati = 0
    
    # Prendi tutti i fornitori
    fornitori = await db.suppliers.find({}, {"_id": 0, "id": 1, "partita_iva": 1}).to_list(1000)
    
    # Crea mappa P.IVA -> id
    piva_to_id = {}
    for f in fornitori:
        piva = (f.get("partita_iva") or "").strip().upper()
        if piva:
            piva_to_id[piva] = f.get("id")
    
    # Aggiorna fatture senza fornitore_id
    fatture = await db.invoices.find(
        {"fornitore_id": {"$in": [None, ""]}, "supplier_vat": {"$exists": True}},
        {"_id": 1, "supplier_vat": 1}
    ).to_list(5000)
    
    for fattura in fatture:
        piva = (fattura.get("supplier_vat") or "").strip().upper()
        if piva and piva in piva_to_id:
            await db.invoices.update_one(
                {"_id": fattura["_id"]},
                {"$set": {
                    "fornitore_id": piva_to_id[piva],
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            collegati += 1
    
    return collegati


async def _sincronizza_veicoli_verbali(db) -> int:
    """Crea record veicolo per targhe che esistono nei verbali ma non nei veicoli."""
    creati = 0
    
    # Prendi tutte le targhe dai verbali
    verbali = await db.verbali_noleggio.find(
        {"targa": {"$exists": True, "$ne": None}},
        {"_id": 0, "targa": 1, "fornitore": 1}
    ).to_list(1000)
    
    targhe_verbali = set(v.get("targa") for v in verbali if v.get("targa"))
    
    # Prendi targhe esistenti nei veicoli
    veicoli = await db.veicoli_noleggio.find({}, {"_id": 0, "targa": 1}).to_list(100)
    targhe_veicoli = set(v.get("targa") for v in veicoli if v.get("targa"))
    
    # Crea veicoli mancanti
    targhe_mancanti = targhe_verbali - targhe_veicoli
    
    for targa in targhe_mancanti:
        # Trova info dal verbale
        verbale = await db.verbali_noleggio.find_one({"targa": targa})
        
        nuovo_veicolo = {
            "id": f"auto_{targa.lower().replace(' ', '')}",
            "targa": targa,
            "fornitore": verbale.get("fornitore") if verbale else None,
            "driver": None,
            "driver_id": None,
            "note": "Creato automaticamente da verbale",
            "created_at": datetime.now(timezone.utc),
            "source": "auto_repair"
        }
        
        await db.veicoli_noleggio.insert_one(nuovo_veicolo)
        creati += 1
    
    return creati


@router.get("/verifica")
async def verifica_relazioni() -> Dict[str, Any]:
    """Verifica lo stato delle relazioni tra dati."""
    db = Database.get_db()
    
    # Verbali
    verbali_tot = await db.verbali_noleggio.count_documents({})
    verbali_con_driver = await db.verbali_noleggio.count_documents({"driver_id": {"$exists": True, "$ne": None}})
    verbali_con_targa = await db.verbali_noleggio.count_documents({"targa": {"$exists": True, "$ne": None, "$ne": ""}})
    
    # Verbali Completi (fonte dati targhe)
    verbali_completi_tot = await db.verbali_noleggio_completi.count_documents({})
    
    # Cedolini
    cedolini_tot = await db.cedolini.count_documents({})
    cedolini_con_dip = await db.cedolini.count_documents({"dipendente_id": {"$exists": True, "$ne": None}})
    
    # Payslips (altra collezione cedolini)
    payslips_tot = await db.payslips.count_documents({})
    payslips_con_dip = await db.payslips.count_documents({"employee_id": {"$exists": True, "$ne": None}})
    
    # Fatture
    fatture_tot = await db.invoices.count_documents({})
    fatture_con_forn = await db.invoices.count_documents({"fornitore_id": {"$exists": True, "$ne": None}})
    
    # Veicoli
    veicoli_tot = await db.veicoli_noleggio.count_documents({})
    veicoli_con_driver = await db.veicoli_noleggio.count_documents({"driver_id": {"$exists": True, "$ne": None}})
    
    return {
        "verbali": {
            "totale": verbali_tot,
            "con_driver": verbali_con_driver,
            "senza_driver": verbali_tot - verbali_con_driver,
            "con_targa": verbali_con_targa,
            "senza_targa": verbali_tot - verbali_con_targa,
            "percentuale_collegati": round(verbali_con_driver / verbali_tot * 100, 1) if verbali_tot > 0 else 0
        },
        "verbali_completi": {
            "totale": verbali_completi_tot,
            "nota": "Fonte dati targhe - da sincronizzare con verbali_noleggio"
        },
        "cedolini": {
            "totale": cedolini_tot,
            "con_dipendente": cedolini_con_dip,
            "senza_dipendente": cedolini_tot - cedolini_con_dip,
            "percentuale_collegati": round(cedolini_con_dip / cedolini_tot * 100, 1) if cedolini_tot > 0 else 0
        },
        "payslips": {
            "totale": payslips_tot,
            "con_employee": payslips_con_dip,
            "percentuale_collegati": round(payslips_con_dip / payslips_tot * 100, 1) if payslips_tot > 0 else 0
        },
        "fatture": {
            "totale": fatture_tot,
            "con_fornitore_id": fatture_con_forn,
            "senza_fornitore_id": fatture_tot - fatture_con_forn,
            "percentuale_collegati": round(fatture_con_forn / fatture_tot * 100, 1) if fatture_tot > 0 else 0
        },
        "veicoli": {
            "totale": veicoli_tot,
            "con_driver": veicoli_con_driver,
            "senza_driver": veicoli_tot - veicoli_con_driver
        }
    }


@router.post("/collega-targa-driver")
async def collega_targa_driver(targa: str, driver_id: str) -> Dict[str, Any]:
    """Collega manualmente una targa a un driver e aggiorna tutti i verbali."""
    db = Database.get_db()
    
    # Verifica driver
    driver = await db.employees.find_one({"id": driver_id}, {"_id": 0, "id": 1, "name": 1})
    if not driver:
        raise HTTPException(status_code=404, detail="Driver non trovato")
    
    # Aggiorna o crea veicolo
    await db.veicoli_noleggio.update_one(
        {"targa": targa},
        {"$set": {
            "driver": driver.get("name"),
            "driver_id": driver_id,
            "updated_at": datetime.now(timezone.utc)
        }},
        upsert=True
    )
    
    # Aggiorna tutti i verbali con questa targa
    result = await db.verbali_noleggio.update_many(
        {"targa": targa},
        {"$set": {
            "driver": driver.get("name"),
            "driver_id": driver_id,
            "updated_at": datetime.now(timezone.utc)
        }}
    )
    
    return {
        "success": True,
        "targa": targa,
        "driver": driver.get("name"),
        "verbali_aggiornati": result.modified_count
    }
