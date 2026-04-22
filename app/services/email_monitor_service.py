"""
Servizio di Monitoraggio Email Automatico
=========================================

Questo servizio:
1. Scarica nuovi documenti dalla posta ogni 10 minuti
2. NON sovrascrive mai i dati esistenti (skip duplicati)
3. Ricategorizza automaticamente i documenti
4. Processa automaticamente i nuovi documenti (buste paga, estratti conto)
5. Salva SEMPRE nel database MongoDB configurato

IMPORTANTE:
- I duplicati vengono SEMPRE saltati (controllo hash file)
- I dati esistenti NON vengono MAI persi
- Ogni operazione è atomica e sicura
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
import os

logger = logging.getLogger(__name__)

# Stato del monitor
_monitor_task: Optional[asyncio.Task] = None
_is_running = False
_last_sync: Optional[str] = None
_sync_stats = {
    "total_syncs": 0,
    "documents_downloaded": 0,
    "documents_processed": 0,
    "last_error": None
}


async def _check_mittente(db, from_addr: str, canale: str) -> Optional[Dict]:
    """
    Verifica se un mittente è attendibile via pattern matching (if pattern in from_addr).
    Restituisce il documento mittente se trovato, None altrimenti.
    """
    from_lower = from_addr.lower()
    mittenti = await db["mittenti_email"].find(
        {"canale": canale, "attivo": True}, {"_id": 0}
    ).to_list(200)
    for m in mittenti:
        pattern = m.get("pattern", "").lower()
        if pattern and pattern in from_lower:
            return m
    return None


async def _salva_documento_generico(db, from_addr: str, subject: str, tipo: str, attachments: list, email_date: str = None):
    """
    Salva in documents_inbox i documenti non-XML (pagopa, inps, inail, paypal, cartella_esattoriale, cedolino).
    """
    import uuid, hashlib
    from datetime import datetime, timezone
    for att in attachments:
        content = att.get("content") or b""
        filename = att.get("filename", "allegato")
        content_hash = hashlib.md5(content).hexdigest() if content else None

        if content_hash:
            existing = await db["documents_inbox"].find_one({"file_hash": content_hash}, {"_id": 0, "id": 1})
            if existing:
                continue

        doc = {
            "id":           str(uuid.uuid4()),
            "filename":     filename,
            "file_hash":    content_hash,
            "tipo_documento": tipo,
            "email_from":   from_addr,
            "email_subject": subject,
            "email_date":   email_date,
            "fonte":        "gmail_monitor",
            "stato":        "importato",
            "categoria":    tipo,
            "created_at":   datetime.now(timezone.utc).isoformat(),
        }
        if content:
            import base64
            doc["pdf_data"] = base64.b64encode(content).decode()

        await db["documents_inbox"].insert_one(doc)
        logger.info(f"[Gmail] Salvato documento {tipo}: {filename} da {from_addr}")

        # --- EVENT BUS: propaga evento documento acquisito ---
        try:
            from app.services.event_bus import propagate_event, EventTypes
            await propagate_event(EventTypes.DOCUMENTO_ACQUISITO, {
                "documento_id": doc.get("id") or doc.get("_id"),
                "filename": filename,
                "origine": "gmail",
                "mime_type": "application/pdf",
                "hash_file": doc.get("file_hash") or doc.get("hash_file"),
                "mittente": from_addr,
                "category": tipo,
            }, db, source_module="email_monitor_service")
        except Exception:
            logger.exception("Errore propagazione evento documento.acquisito (monitor)")


async def sync_email_documents(db, giorni: int = 30) -> Dict[str, Any]:
    """
    Scarica documenti dalla Gmail con routing intelligente per tipo_documento.
    
    Flusso:
    1. Scarica email dai mittenti attendibili (pattern matching canale=gmail)
    2. Per ogni email → check mittente → tipo_documento
    3. fattura_xml → parser XML → invoices
    4. cedolino → salva PDF in documents_inbox (no parser auto)
    5. pagopa/inps/inail/paypal/cartella_esattoriale → documento generico/alert

    IMAP sincrono girato in asyncio.to_thread() per non bloccare il server.
    """
    from app.services.email_document_downloader import download_documents_from_email
    from app.config import settings

    # ── Credenziali Gmail ────────────────────────────────────────────────────
    email_user = None
    email_password = None
    imap_host = settings.IMAP_HOST or "imap.gmail.com"

    try:
        gmail_cfg = await db["settings"].find_one({"chiave": "gmail"}, {"_id": 0})
        if gmail_cfg and gmail_cfg.get("gmail_app_password") and gmail_cfg.get("imap_user"):
            email_user = gmail_cfg["imap_user"]
            email_password = gmail_cfg["gmail_app_password"]
            imap_host = gmail_cfg.get("imap_host", imap_host)
    except Exception:
        pass

    if not email_user:
        email_user = settings.IMAP_USER or settings.EMAIL_USER
    if not email_password:
        email_password = settings.IMAP_PASSWORD or settings.EMAIL_PASSWORD

    if not email_user or not email_password:
        return {"success": False, "error": "Credenziali Gmail non configurate"}

    # ── Carica mittenti Gmail attivi ─────────────────────────────────────────
    mittenti_gmail = await db["mittenti_email"].find(
        {"canale": "gmail", "attivo": True}, {"_id": 0}
    ).to_list(200)

    if not mittenti_gmail:
        return {"success": False, "error": "Nessun mittente Gmail configurato"}

    # Per il downloader usiamo i pattern come allowed_senders (match parziale)
    allowed_patterns = [m["pattern"] for m in mittenti_gmail]
    logger.info(f"[Gmail] Sync con {len(allowed_patterns)} pattern mittenti")

    # ── Download IMAP (in thread, non blocca) ───────────────────────────────
    try:
        result = await download_documents_from_email(
            db=db,
            email_user=email_user,
            email_password=email_password,
            since_days=giorni,
            max_emails=200,
            allowed_senders=allowed_patterns,
        )
    except Exception as e:
        logger.error(f"[Gmail] Errore download: {e}")
        return {"success": False, "error": str(e)}

    stats = result.get("stats", {})
    new_docs = stats.get("new_documents", 0)
    xml_processed = 0

    # ── Routing documenti per tipo ───────────────────────────────────────────
    # Recupera documenti non ancora processati dal download appena avvenuto
    unprocessed = await db["documents_inbox"].find(
        {"xml_processed": {"$ne": True}, "fonte": {"$in": ["gmail_monitor", "email_sync", None]}},
        {"_id": 0, "id": 1, "filename": 1, "file_path": 1, "content": 1,
         "pdf_data": 1, "email_from": 1, "email_subject": 1, "tipo_documento": 1}
    ).to_list(200)

    for doc in unprocessed:
        from_addr = doc.get("email_from", "")
        mittente = await _check_mittente(db, from_addr, "gmail")

        if not mittente:
            # Mittente non riconosciuto → skip silenzioso
            await db["documents_inbox"].update_one(
                {"id": doc["id"]},
                {"$set": {"xml_processed": True, "xml_result": {"skipped": True, "reason": "mittente_non_riconosciuto"}}}
            )
            continue

        tipo = mittente.get("tipo_documento", "generico")

        if tipo == "fattura_xml":
            # ── Processo XML FatturaPA ────────────────────────────────────────
            fname = doc.get("filename", "")
            try:
                from app.services.xml_invoice_processor import process_xml_invoice, is_fatturapa_filename, decode_content
                if not is_fatturapa_filename(fname):
                    await db["documents_inbox"].update_one(
                        {"id": doc["id"]},
                        {"$set": {"xml_processed": True, "xml_result": {"skipped": True, "reason": "non_fatturapa"}}}
                    )
                    continue

                content = doc.get("content")
                if not content and doc.get("file_path"):
                    import pathlib
                    fp = pathlib.Path(doc["file_path"])
                    if fp.exists():
                        content = fp.read_bytes()
                if not content and doc.get("pdf_data"):
                    content = decode_content(doc["pdf_data"])
                if content:
                    if isinstance(content, str):
                        content = content.encode("utf-8")
                    res = await process_xml_invoice(db, content, fname)
                    if res.get("success"):
                        xml_processed += 1
                    await db["documents_inbox"].update_one(
                        {"id": doc["id"]},
                        {"$set": {"xml_processed": True, "xml_result": res, "tipo_documento": "fattura_xml"}}
                    )
            except Exception as ex:
                logger.debug(f"[Gmail] Errore XML {fname}: {ex}")

        else:
            # ── cedolino / pagopa / inps / inail / paypal / cartella ──────────
            await db["documents_inbox"].update_one(
                {"id": doc["id"]},
                {"$set": {
                    "xml_processed": True,
                    "tipo_documento": tipo,
                    "categoria": tipo,
                    "mittente_pattern": mittente.get("pattern"),
                    "xml_result": {"routed": True, "tipo": tipo}
                }}
            )
            logger.info(f"[Gmail] Documento {tipo}: {doc.get('filename','?')} da {from_addr}")

    logger.info(f"[Gmail] Sync OK: {new_docs} nuovi, {xml_processed} XML processati")
    return {
        "success": True,
        "new_documents": new_docs,
        "duplicates_skipped": stats.get("duplicates_skipped", 0),
        "xml_processed": xml_processed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def ricategorizza_documenti(db) -> Dict[str, Any]:
    """
    Ricategorizza i documenti in base al nome file.
    Sposta documenti dalla categoria errata a quella corretta.
    """
    # Trova documenti in "altro" che potrebbero essere categorizzati meglio
    docs = await db["documents_inbox"].find(
        {"category": "altro"},
        {"_id": 0, "id": 1, "filename": 1}
    ).to_list(1000)
    
    ricategorizzati = 0
    
    for doc in docs:
        filename = doc.get("filename", "").lower()
        new_category = None
        
        # Regole di categorizzazione
        if "bnl" in filename:
            new_category = "estratto_conto"
        elif "nexi" in filename:
            new_category = "estratto_conto"
        elif "paypal" in filename:
            new_category = "estratto_conto"
        elif "estratto" in filename or "conto" in filename:
            new_category = "estratto_conto"
        elif "paga" in filename or "cedolino" in filename or "lul" in filename:
            new_category = "busta_paga"
        elif "f24" in filename:
            new_category = "f24"
        
        if new_category:
            await db["documents_inbox"].update_one(
                {"id": doc["id"]},
                {"$set": {
                    "category": new_category,
                    "ricategorizzato_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            ricategorizzati += 1
    
    if ricategorizzati > 0:
        logger.info(f"📂 Ricategorizzati {ricategorizzati} documenti")
    
    return {"ricategorizzati": ricategorizzati}


async def processa_nuovi_documenti(db) -> Dict[str, Any]:
    """
    Processa automaticamente i documenti non ancora elaborati.
    
    FLUSSO COMPLETO CEDOLINI:
    1. Parsing PDF
    2. Crea/aggiorna anagrafica dipendente
    3. Salva in riepilogo_cedolini
    4. Crea movimento prima_nota_salari
    5. Riconcilia automaticamente con estratto conto
    """
    results = {
        "buste_paga": 0,
        "anagrafiche_create": 0,
        "prima_nota_create": 0,
        "riconciliati": 0,
        "estratti_nexi": 0,
        "estratti_bnl": 0,
        "errori": []
    }
    
    # 1. Processa buste paga con FLUSSO COMPLETO (MongoDB-only)
    try:
        from app.services.cedolini_manager import processa_tutti_cedolini_pdf
        
        docs = await db["documents_inbox"].find(
            {
                "category": "busta_paga", 
                "processed": {"$ne": True},
                "pdf_data": {"$exists": True, "$nin": [None, ""]}
            },
            {"_id": 0}
        ).to_list(100)
        
        for doc in docs:
            pdf_data = doc.get("pdf_data")
            filename = doc.get("filename", "")
            
            if not pdf_data:
                continue
            
            try:
                # Usa il nuovo manager completo con architettura MongoDB-only
                res = await processa_tutti_cedolini_pdf(
                    db=db,
                    pdf_data=pdf_data,
                    filename=filename
                )
                
                if res.get("success"):
                    results["buste_paga"] += res.get("cedolini_processati", 0)
                    results["anagrafiche_create"] += res.get("anagrafiche_create", 0)
                    results["prima_nota_create"] += res.get("prima_nota_create", 0)
                    results["riconciliati"] += res.get("riconciliati", 0)
                    
                    # Marca come processato
                    await db["documents_inbox"].update_one(
                        {"id": doc["id"]},
                        {"$set": {
                            "processed": True,
                            "processed_at": datetime.now(timezone.utc).isoformat(),
                            "cedolini_estratti": res.get("cedolini_processati", 0)
                        }}
                    )
                else:
                    for err in res.get("errori", []):
                        results["errori"].append(f"{filename}: {err}")
                        
            except Exception as e:
                results["errori"].append(f"Busta paga {filename}: {e}")
                
    except Exception as e:
        results["errori"].append(f"Errore buste paga: {e}")
    
    # 2. Processa estratti conto Nexi (MongoDB-only)
    try:
        from app.parsers.estratto_conto_nexi_parser import parse_estratto_conto_nexi
        import uuid
        import base64
        
        docs = await db["documents_inbox"].find(
            {
                "category": "estratto_conto",
                "processed": {"$ne": True},
                "filename": {"$regex": "Estratto_conto|Nexi", "$options": "i"},
                "pdf_data": {"$exists": True, "$nin": [None, ""]}
            },
            {"_id": 0}
        ).to_list(100)
        
        for doc in docs:
            pdf_data = doc.get("pdf_data")
            if not pdf_data:
                continue
            
            # Salta se è BNL
            if "bnl" in doc.get("filename", "").lower():
                continue
            
            try:
                pdf_content = base64.b64decode(pdf_data)
                result = parse_estratto_conto_nexi(pdf_content)
                
                if result.get("success"):
                    transactions = result.get("transactions", [])
                    estratto_id = str(uuid.uuid4())
                    
                    # Salva estratto
                    estratto_doc = {
                        "id": estratto_id,
                        "filename": doc.get("filename"),
                        "totale_transazioni": len(transactions),
                        "import_date": datetime.now(timezone.utc).isoformat()
                    }
                    await db["estratto_conto_nexi"].insert_one(estratto_doc.copy())
                    
                    # Salva transazioni
                    for idx, t in enumerate(transactions):
                        trans_doc = {
                            "id": f"{estratto_id}_{idx}",
                            "estratto_id": estratto_id,
                            "data": t.get("data"),
                            "descrizione": t.get("descrizione", ""),
                            "importo": t.get("importo", 0),
                            "banca": "Nexi",
                            "created_at": datetime.now(timezone.utc).isoformat()
                        }
                        await db["estratto_conto_movimenti"].insert_one(trans_doc.copy())
                    
                    results["estratti_nexi"] += 1
                    
                    await db["documents_inbox"].update_one(
                        {"id": doc["id"]},
                        {"$set": {"processed": True, "processed_at": datetime.now(timezone.utc).isoformat()}}
                    )
            except Exception as e:
                results["errori"].append(f"Nexi {doc.get('filename')}: {e}")
                
    except Exception as e:
        results["errori"].append(f"Errore Nexi: {e}")
    
    # 3. Processa estratti conto BNL (MongoDB-only)
    try:
        from app.parsers.estratto_conto_bnl_parser import parse_estratto_conto_bnl
        import uuid
        import base64
        
        docs = await db["documents_inbox"].find(
            {
                "category": "estratto_conto",
                "processed": {"$ne": True},
                "filename": {"$regex": "BNL", "$options": "i"},
                "pdf_data": {"$exists": True, "$nin": [None, ""]}
            },
            {"_id": 0}
        ).to_list(100)
        
        for doc in docs:
            pdf_data = doc.get("pdf_data")
            if not pdf_data:
                continue
            
            try:
                pdf_content = base64.b64decode(pdf_data)
                result = parse_estratto_conto_bnl(pdf_content)
                
                if result.get("success"):
                    transactions = result.get("transazioni", [])
                    estratto_id = str(uuid.uuid4())
                    
                    # Salva estratto
                    estratto_bnl_doc = {
                        "id": estratto_id,
                        "filename": doc.get("filename"),
                        "tipo": result.get("tipo_documento"),
                        "totale_transazioni": len(transactions),
                        "metadata": result.get("metadata", {}),
                        "import_date": datetime.now(timezone.utc).isoformat()
                    }
                    await db["estratto_conto_bnl"].insert_one(estratto_bnl_doc.copy())
                    
                    # Salva transazioni
                    for idx, t in enumerate(transactions):
                        trans_bnl_doc = {
                            "id": f"{estratto_id}_{idx}",
                            "estratto_id": estratto_id,
                            "data": t.get("data_contabile", t.get("data")),
                            "descrizione": t.get("descrizione", ""),
                            "importo": t.get("importo", 0),
                            "banca": "BNL",
                            "created_at": datetime.now(timezone.utc).isoformat()
                        }
                        await db["estratto_conto_movimenti"].insert_one(trans_bnl_doc.copy())
                    
                    results["estratti_bnl"] += 1
                    
                    await db["documents_inbox"].update_one(
                        {"id": doc["id"]},
                        {"$set": {"processed": True, "processed_at": datetime.now(timezone.utc).isoformat()}}
                    )
            except Exception as e:
                results["errori"].append(f"BNL {doc.get('filename')}: {e}")
                
    except Exception as e:
        results["errori"].append(f"Errore BNL: {e}")
    
    total = results["buste_paga"] + results["estratti_nexi"] + results["estratti_bnl"]
    if total > 0:
        logger.info(f"📄 Processati {total} documenti (BP:{results['buste_paga']}, Nexi:{results['estratti_nexi']}, BNL:{results['estratti_bnl']})")
    
    return results


async def run_full_sync(db) -> Dict[str, Any]:
    """
    Esegue un ciclo completo di sincronizzazione:
    1. Scarica nuovi documenti dalla posta (ultimo 1 giorno)
    2. Scarica notifiche fatture Aruba → operazioni da confermare
    3. Scarica F24 automatici (se configurati)
    4. Ricategorizza documenti
    5. Processa nuovi documenti
    6. Aggiorna ricette con nuovi prezzi
    
    IMPORTANTE: I duplicati vengono SEMPRE saltati (controllo hash file)
    """
    global _last_sync, _sync_stats
    
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "email_sync": None,
        "aruba_sync": None,
        "f24_sync": None,
        "ricategorizzazione": None,
        "processamento": None,
        "ricette_aggiornate": None
    }
    
    try:
        # 1. Scarica email documenti (ultimo 1 giorno - i duplicati vengono saltati)
        results["email_sync"] = await sync_email_documents(db, giorni=1)

        # 2. Scarica F24 automatici (se auto_scan_attivo)
        try:
            settings = await db["f24_email_settings"].find_one({"tipo": "f24_settings"})
            if settings and settings.get("auto_scan_attivo", False):
                giorni = settings.get("giorni_indietro", 7)
                from app.routers.f24.email_f24 import scarica_e_processa
                f24_result = await scarica_e_processa(giorni=giorni)
                results["f24_sync"] = f24_result
                
                # Log della scansione automatica
                await db["f24_scan_log"].insert_one({
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "tipo": "automatica",
                    "risultato": f24_result,
                    "success": f24_result.get("success", False)
                })
                
                f24_inseriti = f24_result.get("processamento", {}).get("f24_inseriti", 0)
                if f24_inseriti > 0:
                    logger.info(f"📄 F24 sync automatico: {f24_inseriti} nuovi F24 inseriti")
        except Exception as e:
            logger.warning(f"F24 sync automatico non eseguito: {e}")
            results["f24_sync"] = {"success": False, "error": str(e)}
        
        # 4. Ricategorizza
        results["ricategorizzazione"] = await ricategorizza_documenti(db)
        
        # 5. Processa documenti
        results["processamento"] = await processa_nuovi_documenti(db)

        # Step 7 (I): Alert fatture scadute
        try:
            from datetime import date as _date
            oggi_str = _date.today().isoformat()
            scadute = await db["scadenziario_fornitori"].count_documents({
                "pagato": {"$ne": True}, "data_scadenza": {"$lt": oggi_str}
            })
            if scadute > 0:
                await db["scadenziario_fornitori"].update_many(
                    {"pagato": {"$ne": True}, "data_scadenza": {"$lt": oggi_str}},
                    {"$set": {"stato": "scaduta", "urgente": True}}
                )
                results["fatture_scadute"] = scadute
                logger.warning(f"⚠️ {scadute} fatture scadute non pagate")
        except Exception as e:
            logger.error(f"Errore controllo scadenze: {e}")
        
        # Step 8 (I): Riconcilia POS Nexi con accrediti bancari (±3 giorni, ±1€)
        try:
            from datetime import date as _date2, timedelta, datetime as _dt
            pos_pendenti = await db["prima_nota_banca"].find({
                "source": "corrispettivo_pos",
                "riconciliato": {"$ne": True},
                "data": {"$gte": (_date2.today() - timedelta(days=7)).isoformat()}
            }, {"_id": 0}).to_list(100)
            pos_ric = 0
            for pos in pos_pendenti:
                importo = float(pos.get("importo", 0))
                data_pos = pos.get("data", "")
                if not importo or not data_pos:
                    continue
                data_base = _dt.strptime(data_pos, "%Y-%m-%d")
                data_min = (data_base - timedelta(days=1)).strftime("%Y-%m-%d")
                data_max = (data_base + timedelta(days=4)).strftime("%Y-%m-%d")
                accredito = await db["estratto_conto_movimenti"].find_one({
                    "data": {"$gte": data_min, "$lte": data_max},
                    "importo": {"$gte": importo - 1, "$lte": importo + 1},
                    "riconciliato": {"$ne": True},
                    "descrizione": {"$regex": "NEXI|POS|PAGAMENTI ELETTRONICI", "$options": "i"}
                })
                if accredito:
                    await db["prima_nota_banca"].update_one(
                        {"id": pos["id"]},
                        {"$set": {"riconciliato": True,
                                  "data_riconciliazione": _date2.today().isoformat(),
                                  "movimento_estratto_conto_id": str(accredito.get("id", ""))}}
                    )
                    await db["estratto_conto_movimenti"].update_one(
                        {"_id": accredito["_id"]},
                        {"$set": {"riconciliato": True, "riconciliato_con": "pos_nexi",
                                  "prima_nota_id": pos["id"]}}
                    )
                    pos_ric += 1
            if pos_ric > 0:
                results["pos_riconciliati"] = pos_ric
                logger.info(f"📱 POS riconciliati automaticamente: {pos_ric}")
        except Exception as e:
            logger.error(f"Errore riconciliazione POS: {e}")
        
        _last_sync = results["timestamp"]
        _sync_stats["total_syncs"] += 1
        _sync_stats["documents_downloaded"] += results["email_sync"].get("new_documents", 0)
        _sync_stats["documents_processed"] += (
            results["processamento"].get("buste_paga", 0) +
            results["processamento"].get("estratti_nexi", 0) +
            results["processamento"].get("estratti_bnl", 0)
        )
        
        aruba_new = results.get("aruba_sync", {}).get("stats", {}).get("new_invoices", 0)
        f24_new = results.get("f24_sync", {}).get("processamento", {}).get("f24_inseriti", 0) if results.get("f24_sync") else 0
        logger.info(f"✅ Sync completo - Doc: {results['email_sync'].get('new_documents', 0)}, Aruba: {aruba_new}, F24: {f24_new}, Processati: {_sync_stats['documents_processed']}")
        
        # Passo finale: esegui agenti AI
        try:
            from app.agents.orchestrator import run_agenti
            await run_agenti(db)
        except Exception as e:
            logger.error(f"Errore agenti AI: {e}")
        
        # 7. NOTIFICA TELEGRAM se ci sono novità
        
        # 7. NOTIFICA TELEGRAM se ci sono novità
        try:
            from app.services.telegram_notifications import notifica_sync_completato
            nuovi_doc = results["email_sync"].get("new_documents", 0)
            if nuovi_doc > 0 or aruba_new > 0 or f24_new > 0:
                # Prepara stats per notifica
                notifica_stats = {
                    "email_sync": results["email_sync"],
                    "aruba_sync": results.get("aruba_sync", {}),
                    "f24_sync": results.get("f24_sync", {})
                }
                await notifica_sync_completato(notifica_stats)
        except Exception as e:
            logger.debug(f"Notifica Telegram non inviata: {e}")
        
    except Exception as e:
        logger.error(f"❌ Errore sync: {e}")
        _sync_stats["last_error"] = str(e)
        results["error"] = str(e)
    
    return results


async def monitor_loop(db, interval_seconds: int = 600):
    """
    Loop di monitoraggio che esegue sync ogni N secondi (default 10 minuti).
    """
    global _is_running
    
    logger.info(f"🚀 Avvio monitor email (intervallo: {interval_seconds}s)")
    _is_running = True
    
    while _is_running:
        try:
            await run_full_sync(db)
        except Exception as e:
            logger.error(f"Errore nel monitor loop: {e}")
        
        # Attendi prima del prossimo ciclo
        await asyncio.sleep(interval_seconds)


def start_monitor(db, interval_seconds: int = 3600):
    """
    Avvia il monitor in background.
    """
    global _monitor_task
    
    if _monitor_task and not _monitor_task.done():
        logger.warning("Monitor già in esecuzione")
        return False
    
    _monitor_task = asyncio.create_task(monitor_loop(db, interval_seconds))
    return True


def stop_monitor():
    """
    Ferma il monitor.
    """
    global _is_running, _monitor_task
    
    _is_running = False
    if _monitor_task:
        _monitor_task.cancel()
        _monitor_task = None
    
    logger.info("🛑 Monitor email fermato")
    return True


def get_monitor_status() -> Dict[str, Any]:
    """
    Ritorna lo stato corrente del monitor.
    """
    return {
        "is_running": _is_running,
        "last_sync": _last_sync,
        "stats": _sync_stats
    }
