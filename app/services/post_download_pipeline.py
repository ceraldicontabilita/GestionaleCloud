"""
POST-DOWNLOAD PIPELINE — Ceraldi ERP
=====================================
Processa automaticamente i documenti scaricati da Gmail/PEC:

1. F24 → parse codici tributo → salva in f24_commercialista → riconcilia con banca
2. Cedolini → parse dati → link a dipendenti → visibili in sezione HR
3. Verbali → link a veicoli per targa → link a dipendente (driver) → trattenute busta paga
4. Quietanze → link a F24 → marca come pagato

REGOLE BUSINESS:
- Le FATTURE arrivano SOLO da Google Drive (`drive_invoice_ingest.py`):
  una fattura italiana trovata via email è un'anomalia, non una seconda fonte
- I verbali si associano al dipendente tramite: verbale → targa → veicolo → driver
- L'importo del verbale pagato diventa trattenuta sulla busta paga del driver
"""

import base64
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.services.archivio_documenti_memoria import ArchivioDocumenti

logger = logging.getLogger(__name__)


# ============================================================
# 1. PIPELINE F24
# ============================================================

async def processa_f24_da_email(db: ArchivioDocumenti) -> Dict[str, Any]:
    """
    Processa tutti gli F24 PDF scaricati da Gmail.
    Estrae codici tributo, periodi, importi e salva nella collezione canonica
    f24_unificato (scelta utente 13/07/2026: prima salvava in f24_commercialista
    e gli F24 email non comparivano nel modulo F24 principale).
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

                # Dedup per hash — collezione canonica f24_unificato
                existing = await db["f24_unificato"].find_one({"pdf_hash": doc.get("pdf_hash")})
                if not existing:
                    from app.services.f24_canonico import salva_f24

                    await salva_f24(db, f24_doc, source="gmail_scan")
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

async def processa_cedolini_da_email(db: ArchivioDocumenti) -> Dict[str, Any]:
    """Cedolini PDF scaricati dalla posta: li legge e li scrive il motore unico.

    Qui c'era un secondo lettore (modello AI con ripiego sul parser) e un
    secondo scrittore su ``cedolini`` con una sua chiave ``dedup_key``: la
    stessa busta poteva entrare due volte, una per strada, con numeri diversi.
    """
    from app.services.cedolini_manager import processa_tutti_cedolini_pdf

    stats = {"processati": 0, "errori": 0, "nuovi_cedolini": 0, "aggiornati": 0}

    cursor = db["cedolini_email_attachments"].find({"processed": {"$ne": True}})
    docs = await cursor.to_list(length=200)
    logger.info(f"[PIPELINE-CEDOLINI] {len(docs)} cedolini da processare")

    for doc in docs:
        pdf_data = doc.get("pdf_data")
        if not pdf_data:
            continue
        filename = doc.get("filename", "cedolino.pdf")
        try:
            esito = await processa_tutti_cedolini_pdf(
                db, pdf_data, filename,
                source_path=doc.get("source_path") or filename,
                source_file_hash=doc.get("file_hash") or doc.get("pdf_hash") or "",
            )
        except Exception as exc:
            logger.error("[PIPELINE-CEDOLINI] %s: %s: %s", filename, type(exc).__name__, exc)
            stats["errori"] += 1
            continue
        if not esito.get("success"):
            stats["errori"] += 1
            logger.warning("[PIPELINE-CEDOLINI] %s: %s", filename, esito.get("motivo") or esito.get("errori"))
            continue
        stats["nuovi_cedolini"] += esito.get("cedolini_processati", 0)
        await db["cedolini_email_attachments"].update_one(
            {"id": doc["id"]},
            {"$set": {"processed": True, "processed_at": datetime.now(timezone.utc).isoformat(),
                      "esito_motore": esito.get("esito")}},
        )
        stats["processati"] += 1

    logger.info(f"[PIPELINE-CEDOLINI] Completato: {stats}")
    return stats


# ============================================================
# 3. PIPELINE VERBALI → VEICOLO → DIPENDENTE
# ============================================================

async def processa_verbali_da_email(db: ArchivioDocumenti) -> Dict[str, Any]:
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

    logger.info(f"[PIPELINE-VERBALI] Completato: {stats}")
    return stats






# ============================================================
# 4. PIPELINE QUIETANZE → PROVA PAGAMENTO F24
# ============================================================

async def processa_quietanze_da_email(db: ArchivioDocumenti) -> Dict[str, Any]:
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

async def esegui_pipeline_completa(db: ArchivioDocumenti) -> Dict[str, Any]:
    """
    Esegue l'intero pipeline di processamento post-download.
    Chiamato automaticamente dopo ogni scansione Gmail.
    """
    logger.info("[PIPELINE] ▶️ Avvio pipeline post-download completa...")

    from app.config import settings

    risultati = {}

    # 1. F24 — gated da ENABLE_EMAIL_F24_SYNC (interruttore canale email F24)
    if getattr(settings, "ENABLE_EMAIL_F24_SYNC", True):
        try:
            risultati["f24"] = await processa_f24_da_email(db)
        except Exception as e:
            logger.error(f"[PIPELINE] Errore F24: {e}")
            risultati["f24"] = {"errore": str(e)}
    else:
        risultati["f24"] = {"saltato": "canale email F24 spento (ENABLE_EMAIL_F24_SYNC)"}

    # 2. Cedolini — gated da ENABLE_EMAIL_CEDOLINI_SYNC
    if getattr(settings, "ENABLE_EMAIL_CEDOLINI_SYNC", True):
        try:
            risultati["cedolini"] = await processa_cedolini_da_email(db)
        except Exception as e:
            logger.error(f"[PIPELINE] Errore Cedolini: {e}")
            risultati["cedolini"] = {"errore": str(e)}
    else:
        risultati["cedolini"] = {
            "saltato": "canale email cedolini spento (ENABLE_EMAIL_CEDOLINI_SYNC)"
        }

    # 3. Verbali — gated da ENABLE_EMAIL_VERBALI_SYNC
    if getattr(settings, "ENABLE_EMAIL_VERBALI_SYNC", True):
        try:
            risultati["verbali"] = await processa_verbali_da_email(db)
        except Exception as e:
            logger.error(f"[PIPELINE] Errore Verbali: {e}")
            risultati["verbali"] = {"errore": str(e)}
    else:
        risultati["verbali"] = {"saltato": "canale email verbali spento (ENABLE_EMAIL_VERBALI_SYNC)"}

    # 4. Quietanze
    try:
        risultati["quietanze"] = await processa_quietanze_da_email(db)
    except Exception as e:
        logger.error(f"[PIPELINE] Errore Quietanze: {e}")
        risultati["quietanze"] = {"errore": str(e)}

    # 5. Riconciliazione verbali con banca/PagoPA
    try:
        from app.services.verbali_pagamento_finder import riconcilia_verbali_strict
        risultati["riconciliazione_verbali"] = await riconcilia_verbali_strict(db)
    except Exception as e:
        logger.error(f"[PIPELINE] Errore Riconciliazione: {e}")
        risultati["riconciliazione_verbali"] = {"errore": str(e)}

    logger.info(f"[PIPELINE] ✅ Pipeline completata: {risultati}")
    return risultati









# ============================================================
# 5. SCARICA PDF MANCANTI DAI FOLDER GMAIL
# ============================================================

async def scarica_pdf_verbali_mancanti(db: ArchivioDocumenti) -> Dict[str, Any]:
    """
    Scarica i PDF dei verbali che hanno il numero (dalla cartella Gmail)
    ma non hanno il pdf_data. Va nella cartella Gmail specifica e scarica gli allegati.
    """
    import imaplib
    import email as email_mod
    from email.header import decode_header
    import base64

    stats = {"da_scaricare": 0, "scaricati": 0, "errori": 0}

    # Trova verbali senza PDF ma con nome cartella
    verbali = await db["verbali_noleggio"].find(
        {
            "$or": [{"pdf_data": None}, {"pdf_data": ""}, {"pdf_data": {"$exists": False}}],
            "cartella_email": {"$exists": True, "$ne": ""}
        },
        {"_id": 0}
    ).to_list(100)

    stats["da_scaricare"] = len(verbali)
    if not verbali:
        return stats

    logger.info(f"[SCARICA-PDF] {len(verbali)} verbali senza PDF da scaricare")

    # Connetti a Gmail
    from app.config import settings
    email_user = settings.EMAIL_USER or settings.IMAP_USER or ""
    email_pass = settings.EMAIL_PASSWORD or settings.IMAP_PASSWORD or ""

    if not email_user or not email_pass:
        logger.error("[SCARICA-PDF] Credenziali Gmail non configurate")
        return stats

    try:
        import asyncio

        def _download_pdfs_sync(verbali_list):
            results = {}
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(email_user, email_pass)

            for verbale in verbali_list:
                folder = verbale.get("cartella_email", "")
                if not folder:
                    continue

                try:
                    status, _ = mail.select(f'"{folder}"')
                    if status != "OK":
                        continue

                    # Cerca tutte le email nella cartella
                    status, msgs = mail.search(None, "ALL")
                    if status != "OK" or not msgs[0]:
                        continue

                    email_ids = msgs[0].split()
                    pdfs_found = []

                    for eid in email_ids:
                        st, data = mail.fetch(eid, "(RFC822)")
                        if st != "OK":
                            continue

                        msg = email_mod.message_from_bytes(data[0][1])

                        for part in msg.walk():
                            fn = part.get_filename()
                            if fn:
                                fn_decoded = fn
                                try:
                                    decoded = decode_header(fn)
                                    fn_decoded = decoded[0][0]
                                    if isinstance(fn_decoded, bytes):
                                        fn_decoded = fn_decoded.decode(decoded[0][1] or 'utf-8', errors='replace')
                                except Exception:
                                    pass

                                if fn_decoded.lower().endswith('.pdf'):
                                    payload = part.get_payload(decode=True)
                                    if payload and len(payload) > 500:
                                        pdfs_found.append({
                                            "filename": fn_decoded,
                                            "data": base64.b64encode(payload).decode('ascii'),
                                            "size": len(payload)
                                        })

                    if pdfs_found:
                        # Usa il PDF più grande (di solito il verbale, non la relata)
                        best_pdf = max(pdfs_found, key=lambda x: x["size"])
                        results[verbale["id"]] = best_pdf

                except Exception as e:
                    logger.debug(f"[SCARICA-PDF] Errore cartella {folder}: {e}")

            mail.logout()
            return results

        # Esegui in thread
        results = await asyncio.to_thread(_download_pdfs_sync, verbali)

        # Salva i PDF nel database
        for verbale in verbali:
            if verbale["id"] in results:
                pdf_info = results[verbale["id"]]
                await db["verbali_noleggio"].update_one(
                    {"id": verbale["id"]},
                    {"$set": {
                        "pdf_data": pdf_info["data"],
                        "pdf_filename": pdf_info["filename"],
                        "pdf_size": pdf_info["size"],
                    }}
                )
                stats["scaricati"] += 1
                logger.info(f"[SCARICA-PDF] {verbale.get('numero_verbale','')}: {pdf_info['filename']} ({pdf_info['size']} bytes)")

    except Exception as e:
        logger.error(f"[SCARICA-PDF] Errore: {e}")
        stats["errori"] += 1

    logger.info(f"[SCARICA-PDF] Completato: {stats}")
    return stats
