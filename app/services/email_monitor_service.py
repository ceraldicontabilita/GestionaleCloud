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


async def sync_email_documents(db, giorni: int = 30) -> Dict[str, Any]:
    """
    Scarica documenti dalla posta in modo SICURO.
    - Filtra solo mittenti configurati
    - NON sovrascrive mai documenti esistenti
    - Salta sempre i duplicati
    - Processa fatture XML e inserisce in Prima Nota Banca se metodo SEPA/banca/carta
    """
    from app.services.email_document_downloader import download_documents_from_email
    
    # Leggi credenziali email da ambiente
    email_user = os.environ.get("EMAIL_USER") or os.environ.get("IMAP_USER")
    email_password = os.environ.get("EMAIL_PASSWORD") or os.environ.get("IMAP_PASSWORD")
    
    if not email_user or not email_password:
        logger.warning("Credenziali email non configurate")
        return {"success": False, "error": "Credenziali email non configurate"}
    
    # Carica mittenti autorizzati dal DB
    mittenti = await db["mittenti_email"].find(
        {"attivo": True}, {"_id": 0, "email": 1}
    ).to_list(100)
    mittenti_emails = [m["email"] for m in mittenti]
    
    if not mittenti_emails:
        logger.warning("Nessun mittente configurato")
        return {"success": False, "error": "Nessun mittente configurato"}
    
    try:
        result = await download_documents_from_email(
            db=db,
            email_user=email_user,
            email_password=email_password,
            since_days=giorni,
            max_emails=200,
            allowed_senders=mittenti_emails
        )
        
        stats = result.get("stats", {})
        new_docs = stats.get("new_documents", 0)
        duplicates = stats.get("duplicates_skipped", 0)
        
        logger.info(f"Email sync: {new_docs} nuovi, {duplicates} duplicati saltati")
        
        # Processa automaticamente fatture XML scaricate
        xml_processed = 0
        try:
            from app.services.xml_invoice_processor import process_xml_invoice
            xml_docs = await db["documents_inbox"].find(
                {"filename": {"$regex": r"\.(xml|p7m)$", "$options": "i"}, "xml_processed": {"$ne": True}},
                {"_id": 0, "id": 1, "filename": 1, "file_path": 1, "content": 1}
            ).to_list(100)
            
            for doc in xml_docs:
                try:
                    content = doc.get("content")
                    if not content and doc.get("file_path"):
                        import pathlib
                        fp = pathlib.Path(doc["file_path"])
                        if fp.exists():
                            content = fp.read_bytes()
                    if content:
                        if isinstance(content, str):
                            content = content.encode("utf-8")
                        res = await process_xml_invoice(db, content, doc.get("filename", ""))
                        if res.get("success"):
                            xml_processed += 1
                            await db["documents_inbox"].update_one(
                                {"id": doc["id"]},
                                {"$set": {"xml_processed": True, "xml_result": res}}
                            )
                except Exception as ex:
                    logger.debug(f"Errore XML {doc.get('filename')}: {ex}")
            
            if xml_processed > 0:
                logger.info(f"Processate {xml_processed} fatture XML")
        except Exception as e:
            logger.debug(f"Errore processing XML: {e}")
        
        return {
            "success": True,
            "new_documents": new_docs,
            "duplicates_skipped": duplicates,
            "xml_processed": xml_processed,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Errore sync email: {e}")
        return {"success": False, "error": str(e)}


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
        
        # 2. Scarica notifiche Aruba → operazioni da confermare
        try:
            from app.services.automazione_completa import fetch_aruba_emails_to_operazioni
            results["aruba_sync"] = await fetch_aruba_emails_to_operazioni(db, giorni=7)
        except Exception as e:
            logger.error(f"Errore sync Aruba: {e}")
            results["aruba_sync"] = {"success": False, "error": str(e)}
        
        # 3. Scarica F24 automatici (se auto_scan_attivo)
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
        
        # 6. Aggiorna ricette se ci sono stati aggiornamenti al magazzino
        try:
            proc = results.get("processamento", {})
            if proc.get("buste_paga", 0) > 0 or proc.get("estratti_nexi", 0) > 0 or proc.get("estratti_bnl", 0) > 0:
                from app.services.automazione_completa import aggiorna_prezzi_ricette
                results["ricette_aggiornate"] = await aggiorna_prezzi_ricette(db)
        except Exception as e:
            logger.error(f"Errore aggiornamento ricette: {e}")
        
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
