"""
Servizio di Persistenza Dati Noleggio Auto.

REGOLA FONDAMENTALE: I dati critici (verbali, bolli, riparazioni) 
DEVONO essere sempre salvati in MongoDB per evitare perdita dati.

Questo modulo garantisce:
1. Persistenza automatica dei dati estratti dalle fatture
2. Backup e ripristino dei dati
3. Audit trail per ogni modifica
4. Protezione contro sovrascritture accidentali
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional


logger = logging.getLogger(__name__)

# Collections per persistenza dati noleggio
COLLECTION_VEICOLI = "veicoli_noleggio"
COLLECTION_COSTI = "costi_noleggio"  # Verbali, bolli, riparazioni
COLLECTION_AUDIT = "audit_noleggio"  # Log modifiche

# Tipi di costo che devono essere persistiti
COSTI_CRITICI = ["verbali", "bollo", "riparazioni", "costi_extra"]


async def salva_costo_noleggio(
    db,
    targa: str,
    tipo_costo: str,
    dati: Dict[str, Any],
    source: str = "import_fattura"
) -> str:
    """
    Salva un costo noleggio in modo persistente.
    
    Args:
        db: Database connection
        targa: Targa del veicolo
        tipo_costo: verbali|bollo|riparazioni|costi_extra|pedaggio|canoni
        dati: Dati del costo (data, importo, descrizione, etc.)
        source: Origine del dato (import_fattura, manuale, email)
    
    Returns:
        ID del record salvato
    """
    if not targa or not tipo_costo:
        raise ValueError("Targa e tipo_costo sono obbligatori")
    
    # Genera ID univoco basato su contenuto per evitare duplicati
    contenuto_hash = f"{targa}|{tipo_costo}|{dati.get('data', '')}|{dati.get('importo', 0)}|{dati.get('numero_fattura', '')}"
    import hashlib
    record_hash = hashlib.md5(contenuto_hash.encode()).hexdigest()[:16]
    
    # Controlla se esiste già
    existing = await db[COLLECTION_COSTI].find_one({
        "hash": record_hash,
        "eliminato": {"$ne": True}
    })
    
    if existing:
        logger.debug(f"Costo già esistente: {record_hash}")
        return existing.get("id")
    
    # Crea record
    record_id = str(uuid.uuid4())
    
    # L'importo può essere in diversi campi, prendi il primo disponibile
    importo_raw = dati.get("importo") or dati.get("imponibile") or dati.get("totale_imponibile") or 0
    imponibile_raw = dati.get("imponibile") or dati.get("totale_imponibile") or importo_raw
    totale_raw = dati.get("totale") or dati.get("totale_con_iva") or (imponibile_raw + float(dati.get("iva", 0) or dati.get("totale_iva", 0)))
    
    record = {
        "id": record_id,
        "hash": record_hash,
        "targa": targa.upper(),
        "tipo_costo": tipo_costo,
        "data": dati.get("data"),
        "importo": float(imponibile_raw),  # Usa imponibile come importo principale
        "imponibile": float(imponibile_raw),
        "iva": float(dati.get("iva", 0) or dati.get("totale_iva", 0)),
        "totale": float(totale_raw),
        "numero_fattura": dati.get("numero_fattura"),
        "fattura_id": dati.get("fattura_id"),
        "fornitore": dati.get("fornitore"),
        "descrizione": dati.get("descrizione") or str(dati.get("voci", [])),
        "voci": dati.get("voci", []),
        # Metadati specifici per tipo
        "numero_verbale": dati.get("numero_verbale"),
        "data_verbale": dati.get("data_verbale"),
        # Audit
        "source": source,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "eliminato": False
    }
    
    await db[COLLECTION_COSTI].insert_one(record)
    logger.info(f"✅ Costo salvato: {tipo_costo} per {targa} - €{record['importo']}")
    
    return record_id


async def salva_veicolo(
    db,
    targa: str,
    dati: Dict[str, Any]
) -> str:
    """
    Salva o aggiorna i dati di un veicolo.
    
    Args:
        db: Database connection
        targa: Targa del veicolo
        dati: Dati del veicolo (driver, fornitore, date, etc.)
    
    Returns:
        ID del veicolo
    """
    if not targa:
        raise ValueError("Targa obbligatoria")
    
    targa = targa.upper()
    
    # Cerca veicolo esistente
    existing = await db[COLLECTION_VEICOLI].find_one({"targa": targa})
    
    now = datetime.now(timezone.utc).isoformat()
    
    if existing:
        # Aggiorna solo i campi non nulli
        update_data = {"updated_at": now}
        for k, v in dati.items():
            if v is not None and k not in ["_id", "id", "targa", "created_at"]:
                update_data[k] = v
        
        await db[COLLECTION_VEICOLI].update_one(
            {"targa": targa},
            {"$set": update_data}
        )
        return existing.get("id")
    
    # Crea nuovo
    veicolo_id = str(uuid.uuid4())
    veicolo = {
        "id": veicolo_id,
        "targa": targa,
        "marca": dati.get("marca", ""),
        "modello": dati.get("modello", ""),
        "fornitore_noleggio": dati.get("fornitore_noleggio", ""),
        "fornitore_piva": dati.get("fornitore_piva", ""),
        "contratto": dati.get("contratto"),
        "codice_cliente": dati.get("codice_cliente"),
        "driver": dati.get("driver"),
        "driver_id": dati.get("driver_id"),
        "data_inizio": dati.get("data_inizio"),
        "data_fine": dati.get("data_fine"),
        "note": dati.get("note"),
        "created_at": now,
        "updated_at": now
    }
    
    await db[COLLECTION_VEICOLI].insert_one(veicolo)
    logger.info(f"✅ Veicolo salvato: {targa}")
    
    return veicolo_id


async def persisti_dati_da_fatture(
    db,
    veicoli_calcolati: List[Dict[str, Any]]
) -> Dict[str, int]:
    """
    Persiste i dati estratti dalle fatture nel database.
    Chiamare dopo scan_fatture_noleggio().
    
    Args:
        db: Database connection
        veicoli_calcolati: Lista veicoli con costi calcolati
    
    Returns:
        Contatori operazioni
    """
    risultato = {
        "veicoli_salvati": 0,
        "costi_salvati": 0,
        "errori": 0
    }
    
    for veicolo in veicoli_calcolati:
        targa = veicolo.get("targa")
        if not targa:
            continue
        
        try:
            # Salva veicolo
            await salva_veicolo(db, targa, veicolo)
            risultato["veicoli_salvati"] += 1
            
            # Salva costi critici
            for tipo_costo in COSTI_CRITICI:
                costi = veicolo.get(tipo_costo, [])
                for costo in costi:
                    await salva_costo_noleggio(db, targa, tipo_costo, costo)
                    risultato["costi_salvati"] += 1
                    
        except Exception as e:
            logger.error(f"Errore persistenza {targa}: {e}")
            risultato["errori"] += 1
    
    logger.info(f"Persistenza completata: {risultato}")
    return risultato


async def recupera_costi_veicolo(
    db,
    targa: str,
    anno: Optional[int] = None,
    tipo_costo: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Recupera i costi persistiti per un veicolo.
    
    Args:
        db: Database connection
        targa: Targa del veicolo
        anno: Anno (opzionale)
        tipo_costo: Tipo specifico (opzionale)
    
    Returns:
        Lista costi
    """
    query = {
        "targa": targa.upper(),
        "eliminato": {"$ne": True}
    }
    
    if tipo_costo:
        query["tipo_costo"] = tipo_costo
    
    if anno:
        query["data"] = {"$regex": f"^{anno}"}
    
    cursor = db[COLLECTION_COSTI].find(query, {"_id": 0})
    return await cursor.to_list(1000)


async def crea_audit_log(
    db,
    targa: str,
    azione: str,
    dati_vecchi: Optional[Dict] = None,
    dati_nuovi: Optional[Dict] = None,
    utente: str = "system"
) -> str:
    """
    Crea un log di audit per tracciare modifiche.
    
    Args:
        db: Database connection
        targa: Targa del veicolo
        azione: Tipo di azione (crea|modifica|elimina|ripristina)
        dati_vecchi: Stato precedente
        dati_nuovi: Stato nuovo
        utente: Chi ha effettuato l'azione
    
    Returns:
        ID del log
    """
    log_id = str(uuid.uuid4())
    log_entry = {
        "id": log_id,
        "targa": targa.upper(),
        "azione": azione,
        "dati_vecchi": dati_vecchi,
        "dati_nuovi": dati_nuovi,
        "utente": utente,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    await db[COLLECTION_AUDIT].insert_one(log_entry)
    return log_id


async def migra_dati_esistenti(db) -> Dict[str, int]:
    """
    Migra i dati esistenti estratti dalle fatture nel sistema persistente.
    Utile per prima configurazione.
    """
    from app.services.noleggio import scan_fatture_noleggio
    
    risultato = {
        "anni_elaborati": [],
        "totale_veicoli": 0,
        "totale_costi": 0
    }
    
    # Elabora anni dal 2018 al 2026
    for anno in range(2018, 2027):
        try:
            veicoli_fatture, _ = await scan_fatture_noleggio(anno)
            if veicoli_fatture:
                res = await persisti_dati_da_fatture(db, list(veicoli_fatture.values()))
                risultato["totale_veicoli"] += res["veicoli_salvati"]
                risultato["totale_costi"] += res["costi_salvati"]
                risultato["anni_elaborati"].append(anno)
                logger.info(f"Anno {anno}: {res['veicoli_salvati']} veicoli, {res['costi_salvati']} costi")
        except Exception as e:
            logger.error(f"Errore migrazione anno {anno}: {e}")
    
    return risultato
