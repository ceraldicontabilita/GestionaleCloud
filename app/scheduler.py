"""
Scheduler per task automatici.
- Email Verbali: Scan automatico ogni ora
- Gmail/Aruba: Sync ogni 10 minuti
"""
import logging
import uuid
import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import random

logger = logging.getLogger(__name__)

# Scheduler instance
scheduler = AsyncIOScheduler()

async def pec_hourly_download_task():
    """
    Task eseguito ogni ora.
    Scarica le nuove fatture dalla casella PEC Aruba ed importa gli XML in MongoDB.
    Scansiona INBOX e INBOX.lette; supporta file .xml e .p7m (CAdES).
    """
    from app.database import Database
    from app.services.aruba_pec_downloader import download_pec_invoices

    logger.info("[SCHEDULER-PEC] Avvio download PEC orario...")
    try:
        db = Database.get_db()
        # Solo ultimi 7 giorni per il task orario (il full import manuale usa 365gg)
        result = await download_pec_invoices(db, since_days=7)
        stats = result.get("stats", {})
        new_inv = stats.get("new_invoices", 0)
        dup     = stats.get("duplicates_skipped", 0)
        xml_tot = stats.get("xml_found", 0)
        logger.info(
            f"[SCHEDULER-PEC] Completato: {xml_tot} XML, {new_inv} nuove fatture, "
            f"{dup} duplicati saltati"
        )
        if new_inv > 0:
            try:
                from app.services.websocket_manager import notify_data_change
                await notify_data_change("pec_sync", {
                    "new_invoices": new_inv,
                    "xml_found": xml_tot
                }, "notifications")
                logger.info("[SCHEDULER-PEC] Notifica WebSocket inviata")
            except Exception as ws_err:
                logger.debug(f"[SCHEDULER-PEC] WebSocket non disponibile: {ws_err}")
    except Exception as e:
        logger.error(f"[SCHEDULER-PEC] Errore download orario: {e}")


async def sync_gmail_aruba_task():
    """
    Task eseguito ogni 10 minuti.
    Scarica nuove fatture da Gmail/Aruba e notifica su Telegram.
    """
    from app.database import Database
    from app.services.aruba_invoice_parser import fetch_aruba_invoices
    from app.services.telegram_notifications import is_configured, send_notification
    
    logger.info("📧 [SCHEDULER] Avvio sync Gmail/Aruba...")
    
    try:
        db = Database.get_db()
        
        # Ottieni configurazione email
        email_config = await db["email_accounts"].find_one(
            {"tipo": "aruba"},
            {"_id": 0}
        )
        
        if not email_config:
            # Prova con config di default
            email_config = await db["email_accounts"].find_one({}, {"_id": 0})
        
        if not email_config:
            # Fallback: usa variabili d'ambiente PEC Aruba
            import os
            env_user = os.environ.get("ARUBA_PEC_USER") or os.environ.get("IMAP_USER") or os.environ.get("EMAIL_USER")
            env_pass = os.environ.get("ARUBA_PEC_PASSWORD") or os.environ.get("IMAP_PASSWORD") or os.environ.get("EMAIL_PASSWORD")
            env_host = os.environ.get("ARUBA_PEC_HOST", "imaps.pec.aruba.it")
            if env_user and env_pass:
                email_config = {"email": env_user, "password": env_pass, "imap_server": env_host}
        
        if not email_config:
            logger.warning("📧 [SCHEDULER] Nessun account email configurato per sync Aruba")
            return
        
        email_user = email_config.get("email") or email_config.get("username")
        email_password = email_config.get("password")
        imap_server = email_config.get("imap_server", "imap.gmail.com")
        
        if not email_user or not email_password:
            logger.warning("📧 [SCHEDULER] Credenziali email mancanti")
            return
        
        # Esegui sync
        result = await fetch_aruba_invoices(
            email_user=email_user,
            email_password=email_password,
            imap_server=imap_server,
            days_back=7,
            auto_import=True
        )
        
        nuove_operazioni = result.get("operazioni_create", 0)
        totale_processate = result.get("emails_processate", 0)
        
        logger.info(f"📧 [SCHEDULER] Sync completato: {nuove_operazioni} nuove operazioni da {totale_processate} email")
        
        # Notifica WebSocket real-time se ci sono nuove operazioni
        if nuove_operazioni > 0:
            try:
                from app.services.websocket_manager import notify_data_change
                await notify_data_change("email_sync", {
                    "nuove_operazioni": nuove_operazioni,
                    "emails_processate": totale_processate
                }, "notifications")
                logger.info("🔔 [SCHEDULER] WebSocket notifica email_sync inviata")
            except Exception as e:
                logger.warning(f"🔔 [SCHEDULER] WebSocket non disponibile: {e}")
        
        # Notifica Telegram se ci sono nuove operazioni
        if nuove_operazioni > 0 and is_configured():
            from datetime import datetime
            
            messaggio = f"""📬 *Nuove Operazioni Aruba*

{nuove_operazioni} nuove fatture da confermare!

📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}
📧 Email processate: {totale_processate}

👉 Vai su /operazioni-da-confermare per gestirle"""
            
            try:
                await send_notification(messaggio)
                logger.info("📱 [SCHEDULER] Notifica Telegram inviata")
            except Exception as e:
                logger.error(f"📱 [SCHEDULER] Errore notifica Telegram: {e}")
        
    except Exception as e:
        logger.error(f"📧 [SCHEDULER] Errore sync Gmail/Aruba: {e}")


async def scan_verbali_email_task():
    """
    Task eseguito ogni ora.
    Scansiona le email per trovare nuovi verbali e completare quelli sospesi.
    """
    from app.database import Database
    from app.services.verbali_email_scanner import esegui_scan_verbali_email
    
    logger.info("🚗 [SCHEDULER] Avvio scan email verbali...")
    
    try:
        db = Database.get_db()
        
        # Esegui scan completo con priorità
        result = await esegui_scan_verbali_email(db, days_back=30)
        
        fase1 = result.get("fase1", {})
        fase2 = result.get("fase2", {})
        
        logger.info(f"🚗 [SCHEDULER] Scan verbali completato:")
        logger.info(f"   - Quietanze trovate: {fase1.get('quietanze_trovate', 0)}/{fase1.get('quietanze_cercate', 0)}")
        logger.info(f"   - PDF trovati: {fase1.get('pdf_trovati', 0)}/{fase1.get('pdf_cercati', 0)}")
        logger.info(f"   - Nuovi verbali: {fase2.get('verbali_nuovi', 0)}")
        
        verbali_nuovi = fase2.get("verbali_nuovi", 0)
        
        # Notifica WebSocket real-time se ci sono nuovi verbali
        if verbali_nuovi > 0:
            try:
                from app.services.websocket_manager import notify_data_change
                await notify_data_change("verbali_scan", {
                    "verbali_nuovi": verbali_nuovi,
                    "quietanze_trovate": fase1.get("quietanze_trovate", 0)
                }, "notifications")
                logger.info("🔔 [SCHEDULER] WebSocket notifica verbali_scan inviata")
            except Exception as e:
                logger.warning(f"🔔 [SCHEDULER] WebSocket non disponibile: {e}")
        
        # Se ci sono nuovi verbali, prova a inviarli via Telegram
        if verbali_nuovi > 0:
            try:
                from app.services.telegram_notifications import is_configured, send_notification
                
                if is_configured():
                    messaggio = f"""🚗 *Nuovi Verbali Trovati*

{fase2.get('verbali_nuovi', 0)} nuovi verbali da verificare!

📅 {datetime.now().strftime('%d/%m/%Y %H:%M')}

👉 Vai su /verbali-riconciliazione per gestirli"""
                    
                    await send_notification(messaggio)
                    logger.info("📱 [SCHEDULER] Notifica Telegram verbali inviata")
            except Exception as e:
                logger.warning(f"📱 [SCHEDULER] Notifica Telegram non inviata: {e}")
        
    except Exception as e:
        logger.error(f"🚗 [SCHEDULER] Errore scan verbali: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def check_scadenze_partite_task():
    """
    Task eseguito ogni giorno alle 7:00.
    Scansiona partite_aperte con stato 'aperta' o 'parziale' e data_scadenza < oggi,
    e genera gli alert relazionali appropriati in base al tipo di partita:
      - fattura_fornitore → FAT_DA_PAGARE_SCADUTA
      - f24               → F24_SCADUTO (+ F24_NON_PAGATO se non riconciliato)
      - stipendio         → CED_NON_PAGATO
      - pos_atteso        → BNK_POS_NON_RICONCILIATO

    L'alert_engine.genera_alert() è idempotente: non ricrea alert già aperti,
    quindi il task può girare ogni giorno senza duplicare.
    """
    from app.database import Database
    from app.services.alert_engine import genera_alert

    logger.info("📅 [SCHEDULER] Controllo scadenze partite aperte...")

    try:
        db = Database.get_db()
        oggi = datetime.now().date().isoformat()

        # Tipi di partita → codice alert associato
        mapping_alert = {
            "fattura_fornitore": "FAT_DA_PAGARE_SCADUTA",
            "f24": "F24_SCADUTO",
            "stipendio": "CED_NON_PAGATO",
            "pos_atteso": "BNK_POS_NON_RICONCILIATO",
        }

        stats = {t: 0 for t in mapping_alert}
        stats["totale_analizzate"] = 0
        stats["senza_mapping"] = 0
        stats["errori"] = 0

        # Query partite scadute aperte o parziali
        cursor = db["partite_aperte"].find(
            {
                "stato": {"$in": ["aperta", "parziale"]},
                "data_scadenza": {"$lt": oggi, "$ne": None},
            },
            {"_id": 0, "id": 1, "tipo": 1, "documento_id": 1,
             "documento_collection": 1, "controparte_nome": 1,
             "residuo": 1, "data_scadenza": 1}
        )

        async for partita in cursor:
            stats["totale_analizzate"] += 1
            tipo = partita.get("tipo", "")
            codice_alert = mapping_alert.get(tipo)
            if not codice_alert:
                stats["senza_mapping"] += 1
                continue

            documento_id = partita.get("documento_id") or partita.get("id")
            documento_coll = partita.get("documento_collection", "partite_aperte")
            controparte = partita.get("controparte_nome", "")
            residuo = partita.get("residuo", 0)
            data_scad = partita.get("data_scadenza", "")

            dettaglio = (
                f"Scaduta il {data_scad} — residuo €{residuo:.2f}"
                + (f" — {controparte}" if controparte else "")
            )

            try:
                created = await genera_alert(
                    codice_alert,
                    documento_id,
                    documento_coll,
                    dettaglio,
                    db,
                    extra={
                        "partita_id": partita.get("id"),
                        "residuo": residuo,
                        "data_scadenza": data_scad,
                    }
                )
                if created:
                    stats[tipo] += 1
            except Exception as e:
                stats["errori"] += 1
                logger.error(f"[SCHEDULER-SCADENZE] errore alert {codice_alert} per {documento_id}: {e}")

        logger.info(
            f"📅 [SCHEDULER] Scadenze partite: {stats['totale_analizzate']} analizzate, "
            f"fatture={stats['fattura_fornitore']}, f24={stats['f24']}, "
            f"stipendi={stats['stipendio']}, pos={stats['pos_atteso']}, "
            f"senza_mapping={stats['senza_mapping']}, errori={stats['errori']}"
        )

        # Notifica WebSocket se ci sono nuovi alert di scadenza
        totale_nuovi = sum(stats[t] for t in mapping_alert)
        if totale_nuovi > 0:
            try:
                from app.services.websocket_manager import notify_data_change
                await notify_data_change("scadenze_partite", {
                    "nuovi_alert": totale_nuovi,
                    "fatture": stats["fattura_fornitore"],
                    "f24": stats["f24"],
                    "stipendi": stats["stipendio"],
                    "pos": stats["pos_atteso"],
                }, "notifications")
                logger.info("🔔 [SCHEDULER] WebSocket notifica scadenze_partite inviata")
            except Exception as e:
                logger.debug(f"[SCHEDULER-SCADENZE] WebSocket non disponibile: {e}")

    except Exception as e:
        logger.error(f"📅 [SCHEDULER] Errore controllo scadenze partite: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def check_scadenze_f24_task():
    """
    Task eseguito ogni giorno alle 8:00.
    Controlla scadenze F24 imminenti e invia notifiche push (Telegram + Email).
    """
    logger.info("📅 [SCHEDULER] Controllo scadenze F24...")
    
    try:
        from app.services.f24_scadenze_notifiche import invia_notifiche_scadenze
        
        result = await invia_notifiche_scadenze()
        
        n_scadenze = result.get("scadenze_notificate", 0)
        n_telegram = result.get("notifiche_telegram", 0)
        n_email = result.get("notifiche_email", 0)
        
        if n_scadenze > 0:
            logger.info(f"📅 [SCHEDULER] Scadenze F24: {n_scadenze} trovate, "
                       f"Telegram: {n_telegram}, Email: {n_email}")
            # Notifica WebSocket real-time
            try:
                from app.services.websocket_manager import notify_data_change
                await notify_data_change("f24_scadenze", {
                    "scadenze_trovate": n_scadenze,
                    "notifiche_telegram": n_telegram
                }, "notifications")
                logger.info("🔔 [SCHEDULER] WebSocket notifica f24_scadenze inviata")
            except Exception as e:
                logger.warning(f"🔔 [SCHEDULER] WebSocket non disponibile: {e}")
        else:
            logger.info("📅 [SCHEDULER] Nessuna scadenza F24 imminente")
    
    except Exception as e:
        logger.error(f"📅 [SCHEDULER] Errore controllo scadenze F24: {e}")


async def gmail_full_scan_task():
    """
    Task eseguito ogni ora.
    Scansiona TUTTE le cartelle Gmail per documenti amministrativi.
    REGOLA: le fatture NON vengono scaricate da Gmail (solo PEC o import manuale).
    Dopo il download, esegue il pipeline di processamento automatico.
    """
    from app.database import Database
    from app.services.email_full_download import EmailFullDownloader

    logger.info("📧 [SCHEDULER-GMAIL] Avvio scansione multi-cartella Gmail...")
    try:
        db = Database.get_db()
        downloader = EmailFullDownloader(db)
        result = await downloader.download_all_emails(
            folder="ALL_FOLDERS",
            days_back=30,
            batch_size=50
        )
        stats = result.get("stats", {})
        logger.info(
            f"[SCHEDULER-GMAIL] Download: "
            f"{stats.get('cartelle_scansionate', 0)} cartelle, "
            f"{stats.get('pdfs_downloaded', 0)} PDF"
        )
        
        # Esegui pipeline post-download (F24, cedolini, verbali, quietanze)
        if stats.get("pdfs_downloaded", 0) > 0:
            try:
                from app.services.post_download_pipeline import esegui_pipeline_completa
                pipeline_result = await esegui_pipeline_completa(db)
                logger.info(f"[SCHEDULER-GMAIL] Pipeline: {pipeline_result}")
            except Exception as pipe_err:
                logger.error(f"[SCHEDULER-GMAIL] Pipeline errore: {pipe_err}")
        
        if stats.get("pdfs_downloaded", 0) > 0:
            try:
                from app.services.websocket_manager import notify_data_change
                await notify_data_change("gmail_scan", {
                    "pdfs_downloaded": stats.get("pdfs_downloaded", 0),
                    "cartelle": stats.get("cartelle_con_documenti", 0)
                }, "notifications")
            except Exception as ws_err:
                logger.debug(f"[SCHEDULER-GMAIL] WebSocket non disponibile: {ws_err}")
    except asyncio.CancelledError:
        logger.warning("[SCHEDULER-GMAIL] Scansione Gmail cancellata (timeout)")
    except Exception as e:
        logger.error(f"[SCHEDULER-GMAIL] Errore scansione Gmail: {e}")


def start_scheduler():
    """Avvia lo scheduler con i task programmati."""
    logger.info("🚀 [SCHEDULER] Configurazione scheduler...")

    # ── Gmail Verbali CdS: scan ogni 30 min ────────────────────────────────
    async def _scan_gmail_verbali_job():
        from app.database import Database
        from app.services.verbali_gmail_scanner import scan_gmail_verbali
        try:
            result = await scan_gmail_verbali(Database.get_db(), days_back=2)
            logger.info(f"[SCHEDULER-VERBALI-GMAIL] {result}")
        except Exception as e:
            logger.error(f"[SCHEDULER-VERBALI-GMAIL] errore: {e}")

    async def _link_verbali_fatture_job():
        from app.database import Database
        from app.services.verbali_fattura_linker import collega_verbali_a_fatture
        try:
            result = await collega_verbali_a_fatture(Database.get_db())
            logger.info(f"[SCHEDULER-VERBALI-LINK] {result}")
        except Exception as e:
            logger.error(f"[SCHEDULER-VERBALI-LINK] errore: {e}")

    scheduler.add_job(
        _scan_gmail_verbali_job,
        'interval', minutes=30,
        id="scan_gmail_verbali", name="Scan Gmail Verbali CdS (ogni 30 min)",
        replace_existing=True,
    )
    scheduler.add_job(
        _link_verbali_fatture_job,
        'interval', minutes=60,
        id="link_verbali_fatture", name="Link Verbali ↔ Fatture (ogni 60 min)",
        replace_existing=True,
    )

    # ── PEC: scarica nuove fatture ogni ora ────────────────────────────────
    scheduler.add_job(
        pec_hourly_download_task,
        'interval',
        hours=1,
        id="pec_hourly_download",
        name="Download PEC Fatture (ogni ora)",
        replace_existing=True
    )
    
    # Task Gmail/Aruba ogni 10 minuti
    scheduler.add_job(
        sync_gmail_aruba_task,
        'interval',
        minutes=10,
        id="gmail_aruba_sync",
        name="Sync Gmail/Aruba (ogni 10 min)",
        replace_existing=True
    )
    
    # Task Scan Verbali Email ogni ora
    scheduler.add_job(
        scan_verbali_email_task,
        'interval',
        hours=1,
        id="verbali_email_scan",
        name="Scan Email Verbali (ogni ora)",
        replace_existing=True
    )
    
    # Task Scadenze Partite Aperte (sistema relazionale) - ogni giorno alle 7:00
    scheduler.add_job(
        check_scadenze_partite_task,
        CronTrigger(hour=7, minute=0),
        id="scadenze_partite_check",
        name="Controllo Scadenze Partite Aperte (ogni giorno ore 7:00)",
        replace_existing=True
    )

    # Task Scadenze F24 - ogni giorno alle 8:00
    scheduler.add_job(
        check_scadenze_f24_task,
        CronTrigger(hour=8, minute=0),
        id="f24_scadenze_check",
        name="Controllo Scadenze F24 (ogni giorno ore 8:00)",
        replace_existing=True
    )
    
    # Task Scadenze F24 - anche alle 14:00 come reminder pomeridiano
    scheduler.add_job(
        check_scadenze_f24_task,
        CronTrigger(hour=14, minute=0),
        id="f24_scadenze_check_pm",
        name="Reminder Scadenze F24 (ogni giorno ore 14:00)",
        replace_existing=True
    )
    
    # Task Gmail Full Scan - ogni ora (tutte le cartelle)
    scheduler.add_job(
        gmail_full_scan_task,
        'interval',
        hours=1,
        id="gmail_full_scan",
        name="Gmail Full Scan Multi-Cartella (ogni ora)",
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("✅ [SCHEDULER] Scheduler avviato")
    logger.info("   - PEC Fatture: ogni ora")
    logger.info("   - Gmail/Aruba: ogni 10 minuti")
    logger.info("   - Gmail Full Scan (tutte cartelle): ogni ora")
    logger.info("   - Verbali Email: ogni ora")
    logger.info("   - Scadenze Partite Aperte: ogni giorno ore 7:00")
    logger.info("   - Scadenze F24: ogni giorno ore 8:00 e 14:00")


def stop_scheduler():
    """Ferma lo scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("🛑 [SCHEDULER] Scheduler fermato")
