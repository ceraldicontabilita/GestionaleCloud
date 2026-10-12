"""
POST-DOWNLOAD PIPELINE — Ceraldi ERP
=====================================
Processa automaticamente i documenti scaricati da Gmail/PEC:

1. F24 → parse codici tributo → salva in f24_commercialista → riconcilia con banca
2. Cedolini → parse dati → link a dipendenti → visibili in sezione HR
3. Verbali → link a veicoli per targa → link a dipendente (driver) → trattenute busta paga
4. Quietanze → link a F24 → marca come pagato

REGOLE BUSINESS:
- Le FATTURE arrivano SOLO da Google Drive (cartella unica, `drive_cartella_unica.py`):
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

async def processa_f24_da_email(db: ArchivioDocumenti, *, defer_controparti: bool = False) -> Dict[str, Any]:
    """
    Processa tutti gli F24 PDF scaricati da Gmail.
    Ogni allegato passa da ``importa_modello_bytes``, l'ingresso unico dei
    modelli, che scrive nella collezione canonica ``f24_unificato``.
    """
    stats = {"processati": 0, "errori": 0, "gia_processati": 0, "nuovi": 0}

    docs = []
    for collection in ("f24_email_attachments", "documents_inbox"):
        query = {"processed": {"$ne": True}}
        if collection == "documents_inbox":
            query["$or"] = [{key: "f24"} for key in ("tipo_documento", "categoria", "category")]
        docs.extend({**d, "_collection": collection} for d in await db[collection].find(query).to_list(500))
    logger.info(f"[PIPELINE-F24] {len(docs)} F24 da processare")

    from app.services.f24_canonico import importa_modello_bytes

    for doc in docs:
        try:
            pdf_data = doc.get("pdf_data")
            if not pdf_data:
                continue

            pdf_bytes = base64.b64decode(pdf_data)
            filename = doc.get("filename", "f24.pdf")

            # Un solo ingresso F24: stesso lettore, stessa quadratura, stessa
            # dedup per contenuto e stessa ricerca di quietanza e addebito degli
            # altri canali (Documenti > Import, Drive). Niente parser proprio.
            esito = await importa_modello_bytes(
                db, pdf_bytes, filename, source="gmail_scan",
                source_metadata={
                    "email_subject": doc.get("email_subject", ""),
                    "email_from": doc.get("email_from", ""),
                    "email_date": doc.get("email_date", ""),
                    "attachment_id": doc.get("id"),
                },
                **({"defer_controparti": True} if defer_controparti else {}),
            )
            if esito.get("success"):
                stats["gia_processati" if esito.get("duplicate") else "nuovi"] += 1
                marca = {"esito": "duplicato" if esito.get("duplicate") else "importato",
                         "f24_id": esito.get("f24_id")}
            else:
                # L'allegato resta in archivio col motivo scritto: non si scarta.
                logger.warning("[PIPELINE-F24] %s non importato: %s", filename, esito.get("error"))
                stats["errori"] += 1
                marca = {"esito": esito.get("stato_modello") or "errore_lettura",
                         "errore": esito.get("error")}
            await db[doc["_collection"]].update_one(
                {"id": doc["id"]},
                {"$set": {"processed": True, **marca,
                          "processed_at": datetime.now(timezone.utc).isoformat()}},
            )
            stats["processati"] += 1

        except Exception as e:
            logger.error("[PIPELINE-F24] Errore (%s): %s", type(e).__name__, e)
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
                fonte="posta",
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
    """Importa i PDF con il writer canonico e conserva la notifica separata."""
    import asyncio
    from app.services.verbali_document_import import process_verbale_document, _extract_text
    from app.services.notifiche_pec_verbali import aggancia_notifiche_pec, metadati_notifica

    stats = {"processati": 0, "errori": 0, "nuovi_verbali": 0}
    docs = []
    for collection in ("verbali_email_attachments", "documents_inbox"):
        query = {"processed": {"$ne": True}}
        if collection == "documents_inbox":
            query["$or"] = [{key: "verbale"} for key in ("tipo_documento", "categoria", "category")]
        rows = await db[collection].find(query).to_list(length=500)
        docs.extend({**row, "_collection": collection} for row in rows)
    for doc in docs:
        try:
            if not doc.get("pdf_data"):
                continue
            content = base64.b64decode(doc["pdf_data"], validate=True)
            text = await asyncio.to_thread(_extract_text, content)
            # La relata prova la notificazione, non e' un secondo verbale.
            if "relazione di notificazione" in re.sub(r"\s+", " ", text).casefold():
                continue
            meta = metadati_notifica(doc.get("email_subject"), doc.get("email_from"), doc.get("email_date"))
            result = await process_verbale_document(
                db, document_id=doc["id"], content=content,
                filename=doc.get("filename") or "documento.pdf", source="email_verbale",
                parsed_metadata={"data_notifica": meta["data_notifica"]} if meta["data_notifica"] else None,
            )
            if result.get("verbale_id"):
                verbale = await db["verbali_noleggio"].find_one(
                    {"id": result["verbale_id"]}, {"_id": 0, "data_verbale": 1}) or {}
                fields = {
                    "processed": True, "status": "processato", "verbale_id": result["verbale_id"],
                    "documento_associato_id": result["verbale_id"],
                    "documento_associato_collection": "verbali_noleggio", "associato": True,
                }
                # Il periodo del documento deriva dall'atto, non dalla data della legge citata.
                date_verbale = verbale.get("data_verbale")
                if date_verbale:
                    day = datetime.fromisoformat(date_verbale)
                    fields.update(periodo_anno=day.year, periodo_mese=day.month,
                                  periodo_raw=f"{day.month:02d}/{day.year}",
                                  identificatore_periodo=f"{day.year}_{day.month:02d}")
                await db[doc["_collection"]].update_one(
                    {"id": doc["id"]}, {"$set": fields, "$unset": {"ai_parsing_error": ""}},
                )
                stats["processati"] += 1
        except Exception as exc:
            logger.error("[PIPELINE-VERBALI] %s: %s: %s", doc.get("id"), type(exc).__name__, exc)
            stats["errori"] += 1
    stats["notifiche_pec"] = await aggancia_notifiche_pec(db, dry_run=False)
    from app.services.verbali_document_import import associa_comunicazioni_conducente
    stats["comunicazioni_conducente"] = await associa_comunicazioni_conducente(db)
    return stats


async def processa_quietanze_da_email(db: ArchivioDocumenti) -> Dict[str, Any]:
    """
    Processa quietanze PDF scaricate da Gmail.
    Ogni allegato passa da ``importa_quietanza`` (ingresso unico), che cerca il
    modello corrispondente e la prova bancaria.
    """
    stats = {"processati": 0, "errori": 0, "f24_pagati": 0}

    docs = []
    for collection in ("quietanze_email_attachments", "bonifici_email_attachments", "documents_inbox"):
        query = {"processed": {"$ne": True}}
        if collection == "documents_inbox":
            query["$or"] = [{key: {"$in": ["quietanza", "quietanza_f24", "ricevuta_pagopa", "pagopa", "bonifico"]}}
                            for key in ("tipo_documento", "categoria", "category")]
        docs.extend({**d, "_collection": collection} for d in await db[collection].find(query).to_list(200))
    logger.info(f"[PIPELINE-QUIETANZE] {len(docs)} quietanze da processare")

    for doc in docs:
        try:
            pdf_data = doc.get("pdf_data")
            if not pdf_data:
                continue

            filename = doc.get("filename", "quietanza.pdf")
            if not filename.lower().endswith(".pdf"):
                continue  # CSV, Excel e script non sono quietanze PDF.
            pdf_bytes = base64.b64decode(pdf_data)

            from app.services.verbali_document_import import leggi_documento_verbale, process_verbale_document
            receipt = await leggi_documento_verbale(pdf_bytes, filename)
            if receipt["is_receipt"] and (receipt["numero"] or receipt["iuv"]):
                linked = await process_verbale_document(db, document_id=doc["id"], content=pdf_bytes,
                                                      filename=filename, source="email_quietanza")
                await db[doc["_collection"]].update_one({"id": doc["id"]}, {"$set": {
                    "processed": True, "esito": linked["status"], "verbale_id": linked.get("verbale_id")}})
                stats["processati"] += 1
                continue

            if (doc.get("category") == "bonifico" or doc.get("tipo_documento") == "bonifico") and not re.search(
                r"\bf[\s_-]?24\b", receipt["text"], re.I
            ):
                continue  # Un bonifico generico appartiene al suo dominio.

            # Stesso ingresso di Documenti > Import e di Drive: lettura, quadratura,
            # dedup per protocollo e contenuto, abbinamento al modello e alla banca.
            from app.services.f24_canonico import importa_quietanza

            esito = await importa_quietanza(
                db, pdf_bytes, filename, source="gmail_scan",
                source_metadata={"attachment_id": doc.get("id")},
            )
            if esito.get("success"):
                if not esito.get("duplicate"):
                    stats["f24_pagati"] += len(esito.get("f24_matchati") or [])
                marca = {"esito": "duplicato" if esito.get("duplicate") else "importata",
                         "quietanza_id": esito.get("quietanza_id")}
            else:
                # L'allegato resta in archivio col motivo scritto: non si scarta.
                logger.warning("[PIPELINE-QUIETANZE] %s non importata: %s", filename, esito.get("error"))
                stats["errori"] += 1
                marca = {"esito": esito.get("stato_quietanza") or "errore_lettura",
                         "errore": esito.get("error")}

            await db[doc["_collection"]].update_one(
                {"id": doc["id"]},
                {"$set": {"processed": True, **marca,
                          "processed_at": datetime.now(timezone.utc).isoformat()}}
            )
            stats["processati"] += 1

        except Exception as e:
            logger.error("[PIPELINE-QUIETANZE] Errore (%s): %s", type(e).__name__, e)
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
