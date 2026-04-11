"""
POST-DOWNLOAD PIPELINE — Ceraldi ERP
=====================================
Processa automaticamente i documenti scaricati da Gmail/PEC:

1. F24 → parse codici tributo → salva in f24_commercialista → riconcilia con banca
2. Cedolini → parse dati → link a dipendenti → visibili in sezione HR
3. Verbali → link a veicoli per targa → link a dipendente (driver) → trattenute busta paga
4. Quietanze → link a F24 → marca come pagato

REGOLE BUSINESS:
- Le FATTURE arrivano SOLO via PEC o import manuale XML
- I verbali si associano al dipendente tramite: verbale → targa → veicolo → driver
- L'importo del verbale pagato diventa trattenuta sulla busta paga del driver
"""

import asyncio
import base64
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)


# ============================================================
# 1. PIPELINE F24
# ============================================================

async def processa_f24_da_email(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Processa tutti gli F24 PDF scaricati da Gmail.
    Estrae codici tributo, periodi, importi e salva in f24_commercialista.
    """
    stats = {"processati": 0, "errori": 0, "gia_processati": 0, "nuovi": 0}
    
    cursor = db["f24_email_attachments"].find({"processed": {"$ne": True}})
    docs = await cursor.to_list(length=500)
    logger.info(f"[PIPELINE-F24] {len(docs)} F24 da processare")
    
    for doc in docs:
        try:
            pdf_data = doc.get("pdf_data")
            if not pdf_data:
                continue
            
            pdf_bytes = base64.b64decode(pdf_data)
            filename = doc.get("filename", "f24.pdf")
            
            # Prova parser enhanced (con LLM)
            parsed = None
            try:
                from app.services.enhanced_document_parser import parse_f24_enhanced
                parsed = await parse_f24_enhanced(pdf_bytes, "application/pdf")
            except Exception as e:
                logger.debug(f"[PIPELINE-F24] Enhanced parser non disponibile: {e}")
            
            # Fallback: parser base (PyMuPDF)
            if not parsed or not parsed.get("success"):
                try:
                    from app.services.f24_parser import parse_quietanza_f24
                    parsed = parse_quietanza_f24(pdf_content=pdf_bytes)
                except Exception as e:
                    logger.debug(f"[PIPELINE-F24] Base parser fallito: {e}")
            
            if parsed and (parsed.get("success") or parsed.get("sezione_erario")):
                # Salva in f24_commercialista
                f24_doc = {
                    "id": str(uuid.uuid4()),
                    "filename": filename,
                    "pdf_data": pdf_data,
                    "pdf_hash": doc.get("pdf_hash"),
                    "email_subject": doc.get("email_subject", ""),
                    "email_from": doc.get("email_from", ""),
                    "email_date": doc.get("email_date", ""),
                    "source_folder": doc.get("email_info", {}).get("source_folder", ""),
                    
                    # Dati estratti
                    "sezione_erario": parsed.get("sezione_erario", []),
                    "sezione_inps": parsed.get("sezione_inps", []),
                    "sezione_regioni": parsed.get("sezione_regioni", []),
                    "sezione_tributi_locali": parsed.get("sezione_imu_tributi_locali", []),
                    "totali": parsed.get("totali", {}),
                    "contribuente": parsed.get("contribuente", {}),
                    "data_pagamento": parsed.get("data_pagamento"),
                    "periodo": parsed.get("periodo"),
                    
                    "status": "da_pagare",
                    "riconciliato": False,
                    "source": "gmail_scan",
                    "imported_at": datetime.now(timezone.utc).isoformat(),
                    "anno": doc.get("anno"),
                    "mese": doc.get("mese"),
                }
                
                # Dedup per hash
                existing = await db["f24_commercialista"].find_one({"pdf_hash": doc.get("pdf_hash")})
                if not existing:
                    await db["f24_commercialista"].insert_one(f24_doc)
                    stats["nuovi"] += 1
                    logger.info(f"[PIPELINE-F24] Salvato: {filename}")
                else:
                    stats["gia_processati"] += 1
            
            # Marca come processato
            await db["f24_email_attachments"].update_one(
                {"id": doc["id"]},
                {"$set": {"processed": True, "processed_at": datetime.now(timezone.utc).isoformat()}}
            )
            stats["processati"] += 1
            
        except Exception as e:
            logger.error(f"[PIPELINE-F24] Errore: {e}")
            stats["errori"] += 1
    
    logger.info(f"[PIPELINE-F24] Completato: {stats}")
    return stats


# ============================================================
# 2. PIPELINE CEDOLINI → DIPENDENTI
# ============================================================

async def processa_cedolini_da_email(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Processa cedolini PDF scaricati da Gmail.
    Estrae dati dipendente (nome, CF, netto, lordo, mese/anno).
    Aggiorna/crea record in 'cedolini' e li linka ai dipendenti.
    """
    stats = {"processati": 0, "errori": 0, "nuovi_cedolini": 0, "aggiornati": 0}
    
    cursor = db["cedolini_email_attachments"].find({"processed": {"$ne": True}})
    docs = await cursor.to_list(length=200)
    logger.info(f"[PIPELINE-CEDOLINI] {len(docs)} cedolini da processare")
    
    for doc in docs:
        try:
            pdf_data = doc.get("pdf_data")
            if not pdf_data:
                continue
            
            pdf_bytes = base64.b64decode(pdf_data)
            filename = doc.get("filename", "cedolino.pdf")
            
            # Parse con enhanced parser
            parsed = None
            try:
                from app.services.enhanced_document_parser import parse_cedolino_enhanced
                parsed = await parse_cedolino_enhanced(pdf_bytes, "application/pdf")
            except Exception as e:
                logger.debug(f"[PIPELINE-CEDOLINI] Parser: {e}")
            
            # Fallback: parse base da testo
            if not parsed or not parsed.get("success"):
                try:
                    from app.services.cedolini_manager import processa_tutti_cedolini_pdf
                    parsed = await processa_tutti_cedolini_pdf(db, pdf_data, filename)
                except Exception as e:
                    logger.debug(f"[PIPELINE-CEDOLINI] Base parser: {e}")
            
            if parsed and parsed.get("success"):
                cedolini_data = parsed.get("cedolini", [parsed.get("data", {})])
                
                for ced_data in cedolini_data:
                    cf = ced_data.get("codice_fiscale", "")
                    mese = ced_data.get("mese") or doc.get("mese")
                    anno = ced_data.get("anno") or doc.get("anno")
                    
                    if cf and mese and anno:
                        # Cerca cedolino esistente
                        dedup_key = f"{cf}_{mese:02d}_{anno}" if isinstance(mese, int) else f"{cf}_{mese}_{anno}"
                        existing = await db["cedolini"].find_one({"dedup_key": dedup_key})
                        
                        if existing:
                            # Aggiorna con PDF
                            await db["cedolini"].update_one(
                                {"dedup_key": dedup_key},
                                {"$set": {
                                    "pdf_data": pdf_data,
                                    "pdf_filename": filename,
                                    "pdf_hash": doc.get("pdf_hash"),
                                    "updated_at": datetime.now(timezone.utc).isoformat()
                                }}
                            )
                            stats["aggiornati"] += 1
                        else:
                            stats["nuovi_cedolini"] += 1
                    
                    # Aggiorna dipendente con ultimo cedolino
                    if cf:
                        await db["dipendenti"].update_one(
                            {"codice_fiscale": cf},
                            {"$set": {
                                "ultimo_cedolino": f"{mese:02d}/{anno}" if isinstance(mese, int) else f"{mese}/{anno}",
                                "ultimo_netto": ced_data.get("netto"),
                                "updated_at": datetime.now(timezone.utc).isoformat()
                            }}
                        )
            
            # Marca come processato
            await db["cedolini_email_attachments"].update_one(
                {"id": doc["id"]},
                {"$set": {"processed": True, "processed_at": datetime.now(timezone.utc).isoformat()}}
            )
            stats["processati"] += 1
            
        except Exception as e:
            logger.error(f"[PIPELINE-CEDOLINI] Errore: {e}")
            stats["errori"] += 1
    
    logger.info(f"[PIPELINE-CEDOLINI] Completato: {stats}")
    return stats


# ============================================================
# 3. PIPELINE VERBALI → VEICOLO → DIPENDENTE → TRATTENUTE
# ============================================================

async def processa_verbali_da_email(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Processa verbali PDF scaricati da Gmail.
    
    Flusso:
    1. Estrae targa dal PDF/filename/subject/folder
    2. Collega al veicolo in veicoli_noleggio
    3. Collega al dipendente (driver del veicolo)
    4. Cerca quietanza pagamento (PagoPA, PayPal, bonifico)
    5. Se pagato → registra trattenuta su busta paga del driver
    """
    stats = {
        "processati": 0, "errori": 0, "nuovi_verbali": 0,
        "con_targa": 0, "con_driver": 0, "pagati": 0, "trattenute_create": 0
    }
    
    cursor = db["verbali_email_attachments"].find({"processed": {"$ne": True}})
    docs = await cursor.to_list(length=500)
    logger.info(f"[PIPELINE-VERBALI] {len(docs)} verbali da processare")
    
    # Carica veicoli per lookup targa → driver
    veicoli_by_targa = {}
    async for v in db["veicoli_noleggio"].find({}, {"_id": 0}):
        if v.get("targa"):
            veicoli_by_targa[v["targa"].upper()] = v
    
    for doc in docs:
        try:
            filename = doc.get("filename", "")
            subject = doc.get("email_subject", "")
            source_folder = doc.get("email_info", {}).get("source_folder", "") if isinstance(doc.get("email_info"), dict) else ""
            
            # Estrai targa da: filename, subject, folder, PDF content
            targa = _extract_targa_from_text(f"{filename} {subject} {source_folder}")
            
            # Estrai numero verbale dal nome cartella email o filename
            numero_verbale = _extract_numero_verbale(filename, subject, source_folder)
            
            if not numero_verbale:
                numero_verbale = f"VERB-{doc['id'][:8]}"
            
            # Dedup
            existing = await db["verbali_noleggio"].find_one({
                "$or": [
                    {"numero_verbale": numero_verbale},
                    {"pdf_hash": doc.get("pdf_hash")}
                ]
            })
            
            if existing:
                # Aggiorna con PDF se mancante
                if not existing.get("pdf_data"):
                    await db["verbali_noleggio"].update_one(
                        {"id": existing["id"]},
                        {"$set": {
                            "pdf_data": doc.get("pdf_data"),
                            "pdf_filename": filename,
                            "pdf_hash": doc.get("pdf_hash"),
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
            else:
                # Cerca veicolo e driver
                veicolo_info = {}
                driver_id = None
                driver_nome = None
                
                if targa:
                    stats["con_targa"] += 1
                    veicolo = veicoli_by_targa.get(targa.upper())
                    if veicolo:
                        veicolo_info = veicolo
                        driver_id = veicolo.get("driver_id")
                        driver_nome = veicolo.get("driver")
                        if driver_id:
                            stats["con_driver"] += 1
                
                # Crea record verbale
                verbale_doc = {
                    "id": str(uuid.uuid4()),
                    "numero_verbale": numero_verbale,
                    "targa": targa,
                    "driver": driver_nome,
                    "driver_id": driver_id,
                    
                    "pdf_data": doc.get("pdf_data"),
                    "pdf_filename": filename,
                    "pdf_hash": doc.get("pdf_hash"),
                    
                    "email_subject": subject,
                    "email_from": doc.get("email_from", ""),
                    "email_date": doc.get("email_date", ""),
                    "cartella_email": source_folder,
                    
                    "veicolo_marca": veicolo_info.get("marca"),
                    "veicolo_modello": veicolo_info.get("modello"),
                    "fornitore_noleggio": veicolo_info.get("fornitore_noleggio"),
                    "contratto": veicolo_info.get("contratto"),
                    
                    "importo": None,  # Sarà estratto dal PDF con parser
                    "data_verbale": None,
                    "stato": "da_scaricare" if not doc.get("pdf_data") else "salvato",
                    "quietanza_ricevuta": False,
                    "quietanza_pdf": None,
                    "data_pagamento": None,
                    "metodo_pagamento": None,
                    
                    "trattenuta_cedolino": False,
                    "trattenuta_mese": None,
                    "trattenuta_anno": None,
                    
                    "source": "gmail_scan",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                
                await db["verbali_noleggio"].insert_one(verbale_doc)
                stats["nuovi_verbali"] += 1
                logger.info(f"[PIPELINE-VERBALI] Nuovo: {numero_verbale} | Targa: {targa} | Driver: {driver_nome or 'N/A'}")
            
            # Marca come processato
            await db["verbali_email_attachments"].update_one(
                {"id": doc["id"]},
                {"$set": {"processed": True, "processed_at": datetime.now(timezone.utc).isoformat()}}
            )
            stats["processati"] += 1
            
        except Exception as e:
            logger.error(f"[PIPELINE-VERBALI] Errore: {e}")
            stats["errori"] += 1
    
    # FASE 2: Cerca quietanze per verbali non pagati
    stats_quietanze = await _cerca_quietanze_verbali(db)
    stats.update(stats_quietanze)
    
    logger.info(f"[PIPELINE-VERBALI] Completato: {stats}")
    return stats


async def _cerca_quietanze_verbali(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Cerca quietanze di pagamento per verbali non ancora pagati.
    Controlla: quietanze_email_attachments, estratto_conto_movimenti, PagoPA.
    """
    stats = {"quietanze_trovate": 0, "trattenute_create": 0}
    
    # Verbali da pagare
    verbali_da_pagare = await db["verbali_noleggio"].find(
        {"quietanza_ricevuta": False, "stato": {"$in": ["salvato", "da_pagare", "identificato"]}},
        {"_id": 0}
    ).to_list(500)
    
    if not verbali_da_pagare:
        return stats
    
    logger.info(f"[PIPELINE-VERBALI] Cercando quietanze per {len(verbali_da_pagare)} verbali...")
    
    for verbale in verbali_da_pagare:
        numero = verbale.get("numero_verbale", "")
        
        # 1. Cerca nelle quietanze email (PayPal, bonifici, PagoPA)
        quietanza = await db["quietanze_email_attachments"].find_one({
            "$or": [
                {"email_subject": {"$regex": numero, "$options": "i"}},
                {"filename": {"$regex": numero, "$options": "i"}},
            ]
        })
        
        # 2. Cerca nell'estratto conto (movimenti bancari)
        if not quietanza and verbale.get("importo"):
            mov = await db["estratto_conto_movimenti"].find_one({
                "importo": -abs(verbale["importo"]),
                "descrizione": {"$regex": f"verbal|multa|sanzione", "$options": "i"}
            })
            if mov:
                quietanza = {"source": "estratto_conto", "id": mov.get("id"), "data": mov.get("data")}
        
        if quietanza:
            data_pagamento = quietanza.get("email_date") or quietanza.get("data") or datetime.now(timezone.utc).isoformat()
            
            await db["verbali_noleggio"].update_one(
                {"id": verbale["id"]},
                {"$set": {
                    "stato": "pagato",
                    "quietanza_ricevuta": True,
                    "quietanza_pdf": quietanza.get("pdf_data"),
                    "quietanza_filename": quietanza.get("filename"),
                    "data_pagamento": data_pagamento,
                    "metodo_pagamento": quietanza.get("source", "email"),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            stats["quietanze_trovate"] += 1
            
            # Crea trattenuta sulla busta paga del driver
            if verbale.get("driver_id") and verbale.get("importo"):
                await _crea_trattenuta_verbale(db, verbale, data_pagamento)
                stats["trattenute_create"] += 1
    
    return stats


async def _crea_trattenuta_verbale(
    db: AsyncIOMotorDatabase, 
    verbale: dict,
    data_pagamento: str
) -> None:
    """
    Crea una trattenuta sulla busta paga del dipendente driver per il verbale pagato.
    """
    try:
        # Determina mese/anno della trattenuta (mese successivo al pagamento)
        try:
            dt = datetime.fromisoformat(data_pagamento.replace('Z', '+00:00'))
        except:
            dt = datetime.now(timezone.utc)
        
        mese_trattenuta = dt.month + 1 if dt.month < 12 else 1
        anno_trattenuta = dt.year if dt.month < 12 else dt.year + 1
        
        trattenuta = {
            "id": str(uuid.uuid4()),
            "dipendente_id": verbale["driver_id"],
            "dipendente_nome": verbale.get("driver", ""),
            "tipo": "verbale_multa",
            "descrizione": f"Verbale {verbale.get('numero_verbale', '')} - Targa {verbale.get('targa', '')}",
            "importo": abs(verbale.get("importo", 0)),
            "mese": mese_trattenuta,
            "anno": anno_trattenuta,
            "verbale_id": verbale["id"],
            "numero_verbale": verbale.get("numero_verbale"),
            "data_verbale": verbale.get("data_verbale"),
            "data_pagamento": data_pagamento,
            "targa": verbale.get("targa"),
            "stato": "da_applicare",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        
        await db["trattenute_dipendenti"].insert_one(trattenuta)
        
        # Aggiorna verbale
        await db["verbali_noleggio"].update_one(
            {"id": verbale["id"]},
            {"$set": {
                "trattenuta_cedolino": True,
                "trattenuta_mese": mese_trattenuta,
                "trattenuta_anno": anno_trattenuta,
            }}
        )
        
        logger.info(
            f"[PIPELINE-VERBALI] Trattenuta creata: {verbale.get('numero_verbale')} "
            f"→ {verbale.get('driver')} | €{verbale.get('importo',0)} | {mese_trattenuta}/{anno_trattenuta}"
        )
    except Exception as e:
        logger.error(f"[PIPELINE-VERBALI] Errore creazione trattenuta: {e}")


# ============================================================
# 4. PIPELINE QUIETANZE → PROVA PAGAMENTO F24
# ============================================================

async def processa_quietanze_da_email(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Processa quietanze PDF scaricate da Gmail.
    Cerca il F24 corrispondente e lo marca come pagato.
    """
    stats = {"processati": 0, "errori": 0, "f24_pagati": 0}
    
    cursor = db["quietanze_email_attachments"].find({"processed": {"$ne": True}})
    docs = await cursor.to_list(length=200)
    logger.info(f"[PIPELINE-QUIETANZE] {len(docs)} quietanze da processare")
    
    for doc in docs:
        try:
            pdf_data = doc.get("pdf_data")
            if not pdf_data:
                continue
            
            pdf_bytes = base64.b64decode(pdf_data)
            filename = doc.get("filename", "quietanza.pdf")
            
            # Parse quietanza per estrarre codici tributo pagati
            parsed = None
            try:
                from app.services.f24_parser import parse_quietanza_f24
                parsed = parse_quietanza_f24(pdf_content=pdf_bytes)
            except Exception as e:
                logger.debug(f"[PIPELINE-QUIETANZE] Parser: {e}")
            
            if parsed and parsed.get("success"):
                # Salva in f24_quietanze
                quietanza_doc = {
                    "id": str(uuid.uuid4()),
                    "filename": filename,
                    "pdf_data": pdf_data,
                    "pdf_hash": doc.get("pdf_hash"),
                    "sezione_erario": parsed.get("sezione_erario", []),
                    "sezione_inps": parsed.get("sezione_inps", []),
                    "sezione_regioni": parsed.get("sezione_regioni", []),
                    "totali": parsed.get("totali", {}),
                    "data_pagamento": parsed.get("data_pagamento"),
                    "source": "gmail_scan",
                    "f24_associati": [],
                    "imported_at": datetime.now(timezone.utc).isoformat(),
                }
                
                existing = await db["f24_quietanze"].find_one({"pdf_hash": doc.get("pdf_hash")})
                if not existing:
                    await db["f24_quietanze"].insert_one(quietanza_doc)
                    logger.info(f"[PIPELINE-QUIETANZE] Salvata: {filename}")
            
            await db["quietanze_email_attachments"].update_one(
                {"id": doc["id"]},
                {"$set": {"processed": True, "processed_at": datetime.now(timezone.utc).isoformat()}}
            )
            stats["processati"] += 1
            
        except Exception as e:
            logger.error(f"[PIPELINE-QUIETANZE] Errore: {e}")
            stats["errori"] += 1
    
    logger.info(f"[PIPELINE-QUIETANZE] Completato: {stats}")
    return stats


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def _extract_targa_from_text(text: str) -> Optional[str]:
    """Estrae targa italiana dal testo (formato: XX000XX)."""
    if not text:
        return None
    match = re.search(r'\b([A-Z]{2}\d{3}[A-Z]{2})\b', text, re.IGNORECASE)
    return match.group(1).upper() if match else None


def _extract_numero_verbale(filename: str, subject: str, folder: str) -> Optional[str]:
    """
    Estrae numero verbale da filename, subject o nome cartella.
    Pattern comuni: A25110648977, T23260465978, S22280043251, ZL18173182511
    """
    text = f"{filename} {subject} {folder}"
    
    # Pattern verbali italiani
    patterns = [
        r'\b([A-Z]\d{11,14})\b',           # A25110648977
        r'\b([A-Z]{2}\d{10,14})\b',         # ZL18173182511
        r'\b(\d{7,10})\b',                   # 0007016241
        r'verbale\s*(?:n\.?|nr\.?|numero)?\s*(\S+)',  # Verbale N. XXXX
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    
    # Usa il nome della cartella se sembra un numero verbale
    folder_clean = folder.strip()
    if folder_clean and re.match(r'^[A-Z0-9]', folder_clean) and len(folder_clean) > 5:
        if not any(c in folder_clean.lower() for c in ['inbox', 'gmail', 'sent', 'draft', 'spam']):
            return folder_clean
    
    return None


# ============================================================
# PIPELINE MASTER — Esegue tutto in sequenza
# ============================================================

async def esegui_pipeline_completa(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Esegue l'intero pipeline di processamento post-download.
    Chiamato automaticamente dopo ogni scansione Gmail.
    """
    logger.info("[PIPELINE] ▶️ Avvio pipeline post-download completa...")
    
    risultati = {}
    
    # 1. F24
    try:
        risultati["f24"] = await processa_f24_da_email(db)
    except Exception as e:
        logger.error(f"[PIPELINE] Errore F24: {e}")
        risultati["f24"] = {"errore": str(e)}
    
    # 2. Cedolini
    try:
        risultati["cedolini"] = await processa_cedolini_da_email(db)
    except Exception as e:
        logger.error(f"[PIPELINE] Errore Cedolini: {e}")
        risultati["cedolini"] = {"errore": str(e)}
    
    # 3. Verbali
    try:
        risultati["verbali"] = await processa_verbali_da_email(db)
    except Exception as e:
        logger.error(f"[PIPELINE] Errore Verbali: {e}")
        risultati["verbali"] = {"errore": str(e)}
    
    # 4. Quietanze
    try:
        risultati["quietanze"] = await processa_quietanze_da_email(db)
    except Exception as e:
        logger.error(f"[PIPELINE] Errore Quietanze: {e}")
        risultati["quietanze"] = {"errore": str(e)}
    
    # 5. Riconciliazione verbali con banca/PagoPA
    try:
        risultati["riconciliazione_verbali"] = await riconcilia_verbali_con_banca(db)
    except Exception as e:
        logger.error(f"[PIPELINE] Errore Riconciliazione: {e}")
        risultati["riconciliazione_verbali"] = {"errore": str(e)}
    
    logger.info(f"[PIPELINE] ✅ Pipeline completata: {risultati}")
    return risultati


# ============================================================
# 5. RICONCILIAZIONE VERBALI → BANCA / PagoPA / PayPal
# ============================================================

async def riconcilia_verbali_con_banca(db: AsyncIOMotorDatabase) -> Dict[str, Any]:
    """
    Riconcilia verbali con movimenti bancari, PagoPA e PayPal.
    
    ALGORITMO:
    1. Carica verbali non pagati con importo
    2. Carica movimenti bancari con keyword "comune", "verbale", "multa", "sanzione"
    3. Match per importo (tolleranza ±0.05€)
    4. Se match → marca verbale come pagato, salva data/metodo pagamento
    5. Cerca anche nelle quietanze email (PagoPA, PayPal)
    6. Se verbale pagato + driver assegnato → crea trattenuta busta paga
    """
    stats = {
        "verbali_da_riconciliare": 0,
        "riconciliati_banca": 0,
        "riconciliati_quietanza": 0,
        "riconciliati_pagopa": 0,
        "trattenute_create": 0,
        "non_riconciliati": 0,
        "errori": 0
    }
    
    # 1. Carica verbali non pagati
    verbali = await db["verbali_noleggio"].find(
        {"stato": {"$nin": ["pagato", "riconciliato"]}, "importo": {"$gt": 0}},
        {"_id": 0}
    ).to_list(500)
    
    stats["verbali_da_riconciliare"] = len(verbali)
    if not verbali:
        # Prova anche quelli senza importo ma con numero verbale
        verbali = await db["verbali_noleggio"].find(
            {"stato": {"$nin": ["pagato", "riconciliato"]}},
            {"_id": 0}
        ).to_list(500)
        stats["verbali_da_riconciliare"] = len(verbali)
    
    logger.info(f"[RICONCILIAZIONE] {len(verbali)} verbali da riconciliare")
    
    # 2. Carica movimenti bancari potenzialmente legati a verbali
    movimenti_verbali = await db["estratto_conto_movimenti"].find(
        {"$or": [
            {"descrizione": {"$regex": "comune|verbale|multa|sanzione|pagopa|polizia|infrazione|contravvenzione|MBVT|FAVORE.*[Cc]omune", "$options": "i"}},
            {"categoria": {"$regex": "multa|sanzione|verbal|tasse", "$options": "i"}},
            {"causale": {"$regex": "verbal|multa|sanzione", "$options": "i"}},
        ]},
        {"_id": 0}
    ).to_list(1000)
    
    logger.info(f"[RICONCILIAZIONE] {len(movimenti_verbali)} movimenti bancari candidati")
    
    # 3. Carica quietanze email (PagoPA, PayPal, ricevute)
    quietanze = await db["quietanze_email_attachments"].find(
        {},
        {"_id": 0, "pdf_data": 0}
    ).to_list(200)
    
    # Indice movimenti per importo (con tolleranza)
    movimenti_usati = set()
    
    for verbale in verbali:
        try:
            numero = verbale.get("numero_verbale", "")
            importo = float(verbale.get("importo") or 0)
            matched = False
            
            # --- STRATEGIA 1: Match per numero verbale nella descrizione bancaria ---
            if numero and len(numero) > 5:
                for mov in movimenti_verbali:
                    if mov.get("id") in movimenti_usati:
                        continue
                    desc = (mov.get("descrizione", "") + " " + mov.get("causale", "")).lower()
                    if numero.lower() in desc:
                        await _marca_verbale_pagato(
                            db, verbale, 
                            data_pagamento=mov.get("data_contabile") or mov.get("data_valuta") or mov.get("data"),
                            metodo="bonifico_bancario",
                            riferimento_banca=mov.get("id"),
                            importo_pagato=abs(float(mov.get("importo", 0)))
                        )
                        movimenti_usati.add(mov.get("id"))
                        stats["riconciliati_banca"] += 1
                        matched = True
                        break
            
            # --- STRATEGIA 2: Match per importo esatto (±0.05€) ---
            if not matched and importo > 0:
                for mov in movimenti_verbali:
                    if mov.get("id") in movimenti_usati:
                        continue
                    mov_importo = abs(float(mov.get("importo", 0)))
                    if abs(mov_importo - importo) <= 0.05:
                        await _marca_verbale_pagato(
                            db, verbale,
                            data_pagamento=mov.get("data_contabile") or mov.get("data_valuta") or mov.get("data"),
                            metodo="bonifico_bancario",
                            riferimento_banca=mov.get("id"),
                            importo_pagato=mov_importo
                        )
                        movimenti_usati.add(mov.get("id"))
                        stats["riconciliati_banca"] += 1
                        matched = True
                        break
            
            # --- STRATEGIA 3: Match con quietanze email (PagoPA/PayPal) ---
            if not matched:
                for q in quietanze:
                    q_subject = (q.get("email_subject", "") + " " + q.get("filename", "")).lower()
                    if numero and numero.lower() in q_subject:
                        await _marca_verbale_pagato(
                            db, verbale,
                            data_pagamento=q.get("email_date") or q.get("created_at"),
                            metodo="pagopa" if "pagopa" in q_subject else "email_quietanza",
                            riferimento_banca=q.get("id"),
                            importo_pagato=importo
                        )
                        stats["riconciliati_pagopa" if "pagopa" in q_subject else "riconciliati_quietanza"] += 1
                        matched = True
                        break
            
            if not matched:
                stats["non_riconciliati"] += 1
                
        except Exception as e:
            logger.error(f"[RICONCILIAZIONE] Errore verbale {numero}: {e}")
            stats["errori"] += 1
    
    logger.info(f"[RICONCILIAZIONE] Completato: {stats}")
    return stats


async def _marca_verbale_pagato(
    db: AsyncIOMotorDatabase,
    verbale: dict,
    data_pagamento: str,
    metodo: str,
    riferimento_banca: str = None,
    importo_pagato: float = 0
) -> None:
    """Marca un verbale come pagato e crea trattenuta se ha driver."""
    
    update = {
        "stato": "pagato",
        "quietanza_ricevuta": True,
        "data_pagamento": data_pagamento,
        "metodo_pagamento": metodo,
        "riferimento_banca": riferimento_banca,
        "importo_pagato": importo_pagato,
        "riconciliato_at": datetime.now(timezone.utc).isoformat()
    }
    
    if importo_pagato > 0 and not verbale.get("importo"):
        update["importo"] = importo_pagato
    
    await db["verbali_noleggio"].update_one(
        {"id": verbale["id"]},
        {"$set": update}
    )
    
    logger.info(
        f"[RICONCILIAZIONE] ✅ Verbale {verbale.get('numero_verbale','')} → PAGATO "
        f"| €{importo_pagato} | {metodo} | {data_pagamento}"
    )
    
    # Crea trattenuta busta paga se ha driver
    if verbale.get("driver_id") and (importo_pagato > 0 or float(verbale.get("importo", 0) or 0) > 0):
        importo_trattenuta = importo_pagato if importo_pagato > 0 else float(verbale.get("importo", 0))
        await _crea_trattenuta_verbale(db, {**verbale, "importo": importo_trattenuta}, data_pagamento)
