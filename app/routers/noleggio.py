"""
Router Gestione Noleggio Auto
Endpoint API per gestione flotta veicoli a noleggio.

Questo file contiene solo gli endpoint REST API.
La business logic è in /app/services/noleggio/
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import APIRouter, Query, Body, HTTPException

from app.database import Database

# Import dal modulo noleggio services
from app.services.noleggio import (
    FORNITORI_NOLEGGIO,
    COLLECTION,
    scan_fatture_noleggio,
    categorizza_spesa
)

from app.utils.error_handler import handle_errors

# Import servizio persistenza dati
from app.services.noleggio.data_persistence import (
    persisti_dati_da_fatture,
    recupera_costi_veicolo,
    migra_dati_esistenti,
    COLLECTION_COSTI,
    COLLECTION_VEICOLI,
    COLLECTION_AUDIT
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/veicoli")
@handle_errors
async def get_veicoli(
    anno: Optional[int] = Query(None, description="Filtra per anno")
) -> Dict[str, Any]:
    """
    Lista tutti i veicoli a noleggio con i relativi costi.
    Combina dati estratti dalle fatture con dati salvati (driver, date).
    """
    db = Database.get_db()
    
    # Scansiona fatture
    veicoli_fatture, fatture_senza_targa = await scan_fatture_noleggio(anno)
    
    # Carica dati salvati
    veicoli_salvati = {}
    cursor = db[COLLECTION].find({}, {"_id": 0})
    async for v in cursor:
        veicoli_salvati[v["targa"]] = v
    
    # Associa fatture senza targa ai veicoli salvati
    for fattura in fatture_senza_targa:
        piva = fattura["supplier_vat"]
        tipo_doc = fattura.get("tipo_documento", "").lower()
        is_nota_credito = "nota" in tipo_doc or tipo_doc == "td04"
        fattura_id = fattura.get("invoice_id", "")
        
        # Trova tutti i veicoli di questo fornitore
        veicoli_fornitore = [
            (targa, salvato) for targa, salvato in veicoli_salvati.items()
            if salvato.get("fornitore_piva") == piva
        ]
        
        if not veicoli_fornitore:
            continue
        
        # Scegli il veicolo giusto
        target_targa = None
        oggi = datetime.now().strftime('%Y-%m-%d')
        
        # Prima cerca veicoli non presenti in veicoli_fatture
        for targa, salvato in veicoli_fornitore:
            if targa not in veicoli_fatture:
                target_targa = targa
                break
        
        # Se tutti i veicoli sono presenti, cerca quello con contratto scaduto
        if not target_targa:
            for targa, salvato in veicoli_fornitore:
                data_fine = salvato.get("data_fine", "")
                if data_fine and data_fine < oggi:
                    target_targa = targa
                    break
        
        if not target_targa:
            target_targa = veicoli_fornitore[0][0]
        
        salvato = veicoli_salvati[target_targa]
        
        # Aggiungi le spese a questo veicolo
        if target_targa not in veicoli_fatture:
            veicoli_fatture[target_targa] = {
                "targa": target_targa,
                "fornitore_noleggio": fattura["supplier"],
                "fornitore_piva": piva,
                "codice_cliente": fattura.get("codice_cliente"),
                "modello": salvato.get("modello", ""),
                "marca": salvato.get("marca", ""),
                "driver": salvato.get("driver"),
                "driver_id": salvato.get("driver_id"),
                "contratto": salvato.get("contratto"),
                "data_inizio": salvato.get("data_inizio"),
                "data_fine": salvato.get("data_fine"),
                "note": salvato.get("note"),
                "canoni": [],
                "pedaggio": [],
                "verbali": [],
                "bollo": [],
                "costi_extra": [],
                "riparazioni": [],
                "totale_canoni": 0,
                "totale_pedaggio": 0,
                "totale_verbali": 0,
                "totale_bollo": 0,
                "totale_costi_extra": 0,
                "totale_riparazioni": 0,
                "totale_generale": 0
            }
        
        # Raggruppa linee per categoria
        linee_per_cat: Dict[str, Any] = {}
        for linea in fattura.get("linee", []):
            desc = linea.get("descrizione", "")
            prezzo = float(linea.get("prezzo_totale") or linea.get("prezzo_unitario") or 0)
            categoria, importo, metadata = categorizza_spesa(desc, prezzo, is_nota_credito)
            
            if categoria not in linee_per_cat:
                linee_per_cat[categoria] = {"voci": [], "imponibile": 0, "metadata": {}}
            linee_per_cat[categoria]["voci"].append({"descrizione": desc, "importo": round(importo, 2)})
            linee_per_cat[categoria]["imponibile"] += importo
            for k, v in metadata.items():
                if k not in linee_per_cat[categoria]["metadata"]:
                    linee_per_cat[categoria]["metadata"][k] = v
        
        for categoria, dati in linee_per_cat.items():
            imponibile = round(dati["imponibile"], 2)
            iva = 0 if categoria == "bollo" else round(imponibile * 0.22, 2)
            record = {
                "data": fattura["invoice_date"],
                "numero_fattura": fattura["invoice_number"],
                "fattura_id": fattura_id,
                "fornitore": fattura["supplier"],
                "voci": dati["voci"],
                "imponibile": imponibile,
                "iva": iva,
                "totale": round(imponibile + iva, 2),
                "pagato": fattura.get("pagato", False)
            }
            if categoria == "verbali" and dati["metadata"]:
                record["numero_verbale"] = dati["metadata"].get("numero_verbale")
                record["data_verbale"] = dati["metadata"].get("data_verbale")
            
            veicoli_fatture[target_targa][categoria].append(record)
            veicoli_fatture[target_targa][f"totale_{categoria}"] += round(imponibile + iva, 2)
        
        # Ricalcola totale
        veicoli_fatture[target_targa]["totale_generale"] = round(sum(
            veicoli_fatture[target_targa][f"totale_{cat}"] 
            for cat in ["canoni", "pedaggio", "verbali", "bollo", "costi_extra", "riparazioni"]
        ), 2)
    
    # Merge con dati salvati
    risultato = []
    for targa, dati in veicoli_fatture.items():
        veicolo = {**dati}
        
        if targa in veicoli_salvati:
            salvato = veicoli_salvati[targa]
            veicolo["driver"] = salvato.get("driver")
            veicolo["driver_id"] = salvato.get("driver_id")
            veicolo["modello"] = salvato.get("modello") or veicolo.get("modello", "")
            veicolo["marca"] = salvato.get("marca") or veicolo.get("marca", "")
            veicolo["contratto"] = salvato.get("contratto") or veicolo.get("contratto")
            veicolo["codice_cliente"] = salvato.get("codice_cliente") or veicolo.get("codice_cliente")
            veicolo["centro_fatturazione"] = salvato.get("centro_fatturazione")
            veicolo["data_inizio"] = salvato.get("data_inizio")
            veicolo["data_fine"] = salvato.get("data_fine")
            veicolo["note"] = salvato.get("note")
            veicolo["id"] = salvato.get("id")
        
        risultato.append(veicolo)
    
    # Aggiungi veicoli salvati non presenti nelle fatture dell'anno
    for targa, salvato in veicoli_salvati.items():
        if targa not in veicoli_fatture:
            risultato.append({
                **salvato,
                "canoni": [],
                "pedaggio": [],
                "verbali": [],
                "bollo": [],
                "costi_extra": [],
                "riparazioni": [],
                "totale_canoni": 0,
                "totale_pedaggio": 0,
                "totale_verbali": 0,
                "totale_bollo": 0,
                "totale_costi_extra": 0,
                "totale_riparazioni": 0,
                "totale_generale": 0
            })
    
    # ── ARRICCHISCI CON VERBALI DAL DB verbali_noleggio ──────────────────────
    # I verbali/multe vengono anche dalla collection verbali_noleggio
    # (scaricati dalla PEC/Gmail), non solo dalle fatture XML
    verbali_query = {}
    if anno:
        verbali_query["$or"] = [
            {"data_verbale": {"$regex": f"^{anno}"}},
            {"created_at": {"$regex": f"^{anno}"}}
        ]
    
    verbali_db = await db["verbali_noleggio"].find(
        {**verbali_query, "targa": {"$ne": None, "$ne": ""}},
        {"_id": 0, "pdf_data": 0, "quietanza_pdf": 0}
    ).to_list(500)
    
    # Aggiungi verbali come costi ai veicoli
    for verbale in verbali_db:
        targa = (verbale.get("targa") or "").upper()
        importo = float(verbale.get("importo") or 0)
        
        # Trova il veicolo nel risultato
        veicolo_target = None
        for v in risultato:
            if (v.get("targa") or "").upper() == targa:
                veicolo_target = v
                break
        
        if veicolo_target:
            # Aggiungi come costo verbale
            verbale_record = {
                "data": verbale.get("data_verbale") or verbale.get("created_at", "")[:10],
                "numero_verbale": verbale.get("numero_verbale"),
                "descrizione": f"Verbale {verbale.get('numero_verbale', '')}",
                "importo": importo,
                "iva": 0,
                "totale": importo,
                "stato": verbale.get("stato"),
                "pagato": verbale.get("stato") == "pagato",
                "fattura_id": verbale.get("fattura_id"),
                "fattura_numero": verbale.get("fattura_numero"),
            }
            
            # Evita duplicati (se il verbale è già in fattura)
            existing_nums = [v.get("numero_verbale") for v in veicolo_target.get("verbali", [])]
            if verbale.get("numero_verbale") not in existing_nums:
                veicolo_target.setdefault("verbali", []).append(verbale_record)
                veicolo_target["totale_verbali"] = veicolo_target.get("totale_verbali", 0) + importo
                veicolo_target["totale_generale"] = veicolo_target.get("totale_generale", 0) + importo
    
    # Conta fatture davvero non associate
    fornitori_con_veicoli = set(v.get("fornitore_piva") for v in veicoli_salvati.values())
    fatture_davvero_non_associate = [
        f for f in fatture_senza_targa 
        if f.get("supplier_vat") not in fornitori_con_veicoli
    ]
    
    # Statistiche (DOPO arricchimento con verbali DB)
    statistiche = {
        "totale_canoni": round(sum(v.get("totale_canoni", 0) for v in risultato), 2),
        "totale_pedaggio": round(sum(v.get("totale_pedaggio", 0) for v in risultato), 2),
        "totale_verbali": round(sum(v.get("totale_verbali", 0) for v in risultato), 2),
        "totale_bollo": round(sum(v.get("totale_bollo", 0) for v in risultato), 2),
        "totale_costi_extra": round(sum(v.get("totale_costi_extra", 0) for v in risultato), 2),
        "totale_riparazioni": round(sum(v.get("totale_riparazioni", 0) for v in risultato), 2),
        "totale_generale": round(sum(v.get("totale_generale", 0) for v in risultato), 2)
    }
    
    return {
        "veicoli": sorted(risultato, key=lambda x: x.get("totale_generale", 0), reverse=True),
        "statistiche": statistiche,
        "count": len(risultato),
        "fatture_non_associate": len(fatture_davvero_non_associate),
        "anno": anno
    }


@router.get("/fatture-non-associate")
@handle_errors
async def get_fatture_non_associate(
    anno: Optional[int] = Query(None, description="Filtra per anno")
) -> Dict[str, Any]:
    """
    Restituisce le fatture di fornitori noleggio che non hanno targa.
    Utile per LeasePlan che richiede associazione manuale.
    """
    db = Database.get_db()
    _, fatture_senza_targa = await scan_fatture_noleggio(anno)
    
    # Carica veicoli salvati per filtrare
    veicoli_salvati = {}
    cursor = db[COLLECTION].find()
    async for v in cursor:
        veicoli_salvati[v["targa"]] = v
    
    # Filtra solo fatture di fornitori SENZA veicoli salvati o non ancora associate
    fornitori_con_veicoli = set(v.get("fornitore_piva") for v in veicoli_salvati.values())
    
    # Formatta correttamente le fatture per il frontend
    fatture_formattate = []
    for f in fatture_senza_targa:
        fatture_formattate.append({
            "id": f.get("invoice_id"),
            "numero": f.get("invoice_number"),
            "data": f.get("invoice_date"),
            "fornitore": f.get("supplier"),
            "piva": f.get("supplier_vat"),
            "importo": f.get("total", 0),
            "descrizione": ", ".join([l.get("descrizione", "")[:50] for l in f.get("linee", [])[:2]]),
            "tipo": f.get("tipo_documento"),
            "codice_cliente": f.get("codice_cliente")
        })
    
    return {
        "fatture": fatture_formattate,
        "count": len(fatture_formattate),
        "nota": "Queste fatture richiedono associazione manuale ad un veicolo"
    }


@router.get("/fornitori")
@handle_errors
async def get_fornitori() -> Dict[str, Any]:
    """Restituisce la lista dei fornitori noleggio supportati."""
    return {
        "fornitori": [
            {"nome": "ALD Automotive Italia S.r.l.", "piva": "01924961004", "targa_in_fattura": True, "contratto_in_fattura": True},
            {"nome": "ARVAL SERVICE LEASE ITALIA SPA", "piva": "04911190488", "targa_in_fattura": True, "contratto_in_fattura": True},
            {"nome": "Leasys Italia S.p.A", "piva": "06714021000", "targa_in_fattura": True, "contratto_in_fattura": False},
            {"nome": "LeasePlan Italia S.p.A.", "piva": "02615080963", "targa_in_fattura": False, "contratto_in_fattura": False}
        ]
    }


@router.get("/drivers")
@handle_errors
async def get_drivers() -> Dict[str, Any]:
    """Lista dipendenti disponibili come driver."""
    db = Database.get_db()
    
    dipendenti = []
    cursor = db["dipendenti"].find({}, {"_id": 0, "id": 1, "nome": 1, "cognome": 1})
    async for d in cursor:
        dipendenti.append({
            "id": d.get("id"),
            "nome_completo": f"{d.get('nome', '')} {d.get('cognome', '')}".strip()
        })
    
    return {"drivers": dipendenti}


@router.post("/veicoli")
@handle_errors
async def create_veicolo(data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Crea un nuovo veicolo a noleggio."""
    db = Database.get_db()
    targa = (data.get("targa") or "").upper().strip()
    if not targa:
        raise HTTPException(status_code=400, detail="Targa obbligatoria")

    existing = await db[COLLECTION].find_one({"targa": targa})
    if existing:
        raise HTTPException(status_code=409, detail=f"Veicolo {targa} già esistente")

    veicolo = {
        "targa": targa,
        "marca": data.get("marca", ""),
        "modello": data.get("modello", ""),
        "driver_id": data.get("driver_id"),
        "driver_nome": data.get("driver_nome", ""),
        "fornitore_piva": data.get("fornitore_piva", ""),
        "data_inizio": data.get("data_inizio"),
        "data_fine": data.get("data_fine"),
        "canone_mensile": float(data.get("canone_mensile", 0) or 0),
        "note": data.get("note", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db[COLLECTION].insert_one(veicolo.copy())
    veicolo.pop("_id", None)
    return veicolo


@router.put("/veicoli/{targa}")
@handle_errors
async def update_veicolo(
    targa: str,
    data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """Aggiorna i dati di un veicolo (driver, date noleggio, marca, modello, contratto)."""
    db = Database.get_db()
    
    # Verifica driver se passato
    if data.get("driver_id"):
        dipendente = await db["dipendenti"].find_one(
            {"id": data["driver_id"]}, 
            {"_id": 0, "id": 1, "nome": 1, "cognome": 1}
        )
        if not dipendente:
            raise HTTPException(status_code=400, detail=f"Dipendente con ID {data['driver_id']} non trovato")
        data["driver"] = f"{dipendente.get('nome', '')} {dipendente.get('cognome', '')}".strip()
    
    update_data = {
        "targa": targa.upper(),
        "updated_at": datetime.now(timezone.utc)
    }
    
    # Campi aggiornabili
    for campo in ["driver", "driver_id", "marca", "modello", "contratto", 
                  "codice_cliente", "centro_fatturazione",
                  "data_inizio", "data_fine", "note", "fornitore_noleggio", "fornitore_piva"]:
        if campo in data:
            update_data[campo] = data[campo]
    
    result = await db[COLLECTION].update_one(
        {"targa": targa.upper()},
        {"$set": update_data, "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc)}},
        upsert=True
    )
    
    return {
        "success": True,
        "targa": targa.upper(),
        "message": "Veicolo aggiornato" if result.modified_count else "Veicolo creato"
    }


@router.delete("/veicoli/{targa}")
@handle_errors
async def delete_veicolo(targa: str) -> Dict[str, Any]:
    """Elimina un veicolo dalla gestione (non elimina le fatture)."""
    db = Database.get_db()
    
    result = await db[COLLECTION].delete_one({"targa": targa.upper()})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Veicolo non trovato")
    
    return {"success": True, "message": f"Veicolo {targa} rimosso dalla gestione"}


@router.post("/associa-fornitore")
@handle_errors
async def associa_fornitore(
    data: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Associa manualmente un fornitore (es: LeasePlan) ad una targa.
    Necessario per fornitori che non includono la targa nelle fatture.
    """
    db = Database.get_db()
    
    targa = data.get("targa", "").upper()
    fornitore_piva = data.get("fornitore_piva")
    
    if not targa or not fornitore_piva:
        raise HTTPException(status_code=400, detail="Targa e fornitore_piva sono obbligatori")
    
    if fornitore_piva not in FORNITORI_NOLEGGIO.values():
        raise HTTPException(status_code=400, detail=f"Fornitore non riconosciuto. Validi: {list(FORNITORI_NOLEGGIO.values())}")
    
    fornitore_nome = next((k for k, v in FORNITORI_NOLEGGIO.items() if v == fornitore_piva), "")
    
    update_data = {
        "targa": targa,
        "fornitore_piva": fornitore_piva,
        "fornitore_noleggio": fornitore_nome,
        "marca": data.get("marca", ""),
        "modello": data.get("modello", ""),
        "contratto": data.get("contratto", ""),
        "updated_at": datetime.now(timezone.utc)
    }
    
    result = await db[COLLECTION].update_one(
        {"targa": targa},
        {"$set": update_data, "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": datetime.now(timezone.utc)}},
        upsert=True
    )
    
    _ = result  # Upsert always succeeds
    
    return {
        "success": True,
        "targa": targa,
        "fornitore": fornitore_nome,
        "message": f"Targa {targa} associata a {fornitore_nome}"
    }



@router.post("/migra-dati")
@handle_errors
async def migra_dati() -> Dict[str, Any]:
    """
    Migra tutti i dati estratti dalle fatture nel database persistente.
    Esegue scansione di tutti gli anni (2018-2026) e salva in MongoDB.
    
    OPERAZIONE SICURA: Non elimina dati esistenti, solo aggiunge.
    """
    db = Database.get_db()
    
    try:
        risultato = await migra_dati_esistenti(db)
        
        return {
            "success": True,
            "message": "Migrazione completata con successo",
            "anni_elaborati": risultato.get("anni_elaborati", []),
            "totale_veicoli": risultato.get("totale_veicoli", 0),
            "totale_costi": risultato.get("totale_costi", 0)
        }
    except Exception as e:
        logger.error(f"Errore migrazione: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/persisti-anno/{anno}")
@handle_errors
async def persisti_anno(anno: int) -> Dict[str, Any]:
    """
    Persiste i dati di un anno specifico nel database.
    Utile per aggiornare solo dati recenti.
    """
    db = Database.get_db()
    
    if anno < 2018 or anno > 2030:
        raise HTTPException(status_code=400, detail="Anno non valido (2018-2030)")
    
    try:
        # Scansiona fatture dell'anno
        veicoli_fatture, _ = await scan_fatture_noleggio(anno)
        
        if not veicoli_fatture:
            return {
                "success": True,
                "message": f"Nessun veicolo trovato per {anno}",
                "veicoli_salvati": 0,
                "costi_salvati": 0
            }
        
        # Persisti nel database
        risultato = await persisti_dati_da_fatture(db, list(veicoli_fatture.values()))
        
        return {
            "success": True,
            "anno": anno,
            "veicoli_salvati": risultato.get("veicoli_salvati", 0),
            "costi_salvati": risultato.get("costi_salvati", 0),
            "errori": risultato.get("errori", 0)
        }
    except Exception as e:
        logger.error(f"Errore persistenza anno {anno}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/costi-persistiti/{targa}")
@handle_errors
async def get_costi_persistiti(
    targa: str,
    anno: Optional[int] = Query(None),
    tipo_costo: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """
    Recupera i costi persistiti per un veicolo dal database.
    I dati persistiti sono la fonte di verità per verbali, bolli, riparazioni.
    """
    db = Database.get_db()
    
    costi = await recupera_costi_veicolo(db, targa, anno, tipo_costo)
    
    # Raggruppa per tipo
    raggruppati = {}
    for c in costi:
        tipo = c.get("tipo_costo", "altro")
        if tipo not in raggruppati:
            raggruppati[tipo] = []
        raggruppati[tipo].append(c)
    
    return {
        "targa": targa.upper(),
        "anno": anno,
        "totale_costi": len(costi),
        "costi_per_tipo": raggruppati,
        "totale_importo": sum(c.get("importo", 0) for c in costi)
    }


@router.get("/statistiche-persistenza")
@handle_errors
async def get_statistiche_persistenza() -> Dict[str, Any]:
    """
    Statistiche sulla persistenza dati per verificare integrità.
    """
    db = Database.get_db()
    
    # Conta documenti per collection
    veicoli_count = await db[COLLECTION_VEICOLI].count_documents({})
    costi_count = await db[COLLECTION_COSTI].count_documents({"eliminato": {"$ne": True}})
    audit_count = await db[COLLECTION_AUDIT].count_documents({})
    
    # Statistiche per tipo costo
    pipeline = [
        {"$match": {"eliminato": {"$ne": True}}},
        {"$group": {
            "_id": "$tipo_costo",
            "count": {"$sum": 1},
            "totale_importo": {"$sum": "$importo"}
        }}
    ]
    tipo_stats = await db[COLLECTION_COSTI].aggregate(pipeline).to_list(100)
    
    return {
        "veicoli_salvati": veicoli_count,
        "costi_salvati": costi_count,
        "audit_logs": audit_count,
        "costi_per_tipo": {s["_id"]: {"count": s["count"], "totale": s["totale_importo"]} for s in tipo_stats}
    }



@router.get("/verbali-dipendente")
@handle_errors
async def get_verbali_dipendente(
    dipendente_id: str = Query(default="", description="ID dipendente"),
    codice_fiscale: str = Query(default="", description="Codice fiscale dipendente")
) -> Dict[str, Any]:
    """
    Lista verbali/multe associati a un dipendente (tramite driver_id o driver_cf).
    Usato nella sezione HR → Tab Verbali del dipendente.
    """
    db = Database.get_db()
    
    if not dipendente_id and not codice_fiscale:
        return {"verbali": [], "totale": 0}
    
    # Cerca verbali per driver_id, driver_cf, o codice_fiscale
    query_conditions = []
    if dipendente_id:
        query_conditions.append({"driver_id": dipendente_id})
    if codice_fiscale:
        query_conditions.append({"driver_cf": codice_fiscale})
    
    if not query_conditions:
        return {"verbali": [], "totale": 0}
    
    cursor = db["verbali_noleggio"].find(
        {"$or": query_conditions},
        {"_id": 0, "pdf_data": 0, "quietanza_pdf": 0}
    ).sort("created_at", -1)
    
    verbali = await cursor.to_list(500)
    
    return {
        "verbali": verbali,
        "totale": len(verbali),
        "pagati": sum(1 for v in verbali if v.get("stato") == "pagato"),
        "da_pagare": sum(1 for v in verbali if v.get("stato") != "pagato"),
        "importo_totale": sum(float(v.get("importo", 0) or 0) for v in verbali)
    }
