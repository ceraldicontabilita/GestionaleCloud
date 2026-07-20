"""
Scheduler per task automatici.
- Email Verbali: Scan automatico ogni ora
"""
import logging
import uuid
import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import random

logger = logging.getLogger(__name__)

# Scheduler instance
scheduler = AsyncIOScheduler()

async def scan_verbali_email_task():
    """
    Task eseguito ogni ora.
    Scansiona le email per trovare nuovi verbali e completare quelli sospesi.
    Gated da ENABLE_EMAIL_VERBALI_SYNC (interruttore canale email verbali).
    """
    from app.config import settings
    if not getattr(settings, "ENABLE_EMAIL_VERBALI_SYNC", True):
        logger.info("🚗 [SCHEDULER] Scan email verbali saltato (canale spento).")
        return

    from app.database import Database
    from app.services.verbali_email_logic import scan_email_con_priorita

    logger.info("🚗 [SCHEDULER] Avvio scan email verbali...")

    try:
        db = Database.get_db()

        # Esegui scan completo con priorità (orchestratore verbali_email_logic:
        # FASE 1 quietanze via PayPal/PagoPA/EC + IMAP, PDF; FASE 2 nuovi)
        result = await scan_email_con_priorita(db, days_back=30)

        fase1 = result.get("fase_1_completamenti", {})
        fase2 = result.get("fase_2_nuovi", {})
        
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

📅 {datetime.now().strftime('%d-%m-%Y %H:%M')}

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

        # Partite scadute di tipo senza alert dedicato (nota_credito, trasferimento,
        # altro) — prima venivano solo contate in "senza_mapping" e non generavano
        # mai nessun alert, anche se scadute da mesi. RIC_PARTITA_VECCHIA fa da
        # rete di sicurezza generica (vedi memoria/moduli/RICONCILIAZIONE.md gap #6).
        stats["partita_vecchia_scaduta"] = 0
        cursor_scadute_senza_mapping = db["partite_aperte"].find(
            {
                "stato": {"$in": ["aperta", "parziale"]},
                "data_scadenza": {"$lt": oggi, "$ne": None},
                "tipo": {"$nin": list(mapping_alert.keys())},
            },
            {"_id": 0, "id": 1, "tipo": 1, "documento_id": 1,
             "documento_collection": 1, "controparte_nome": 1,
             "residuo": 1, "data_scadenza": 1}
        )
        async for partita in cursor_scadute_senza_mapping:
            documento_id = partita.get("documento_id") or partita.get("id")
            documento_coll = partita.get("documento_collection", "partite_aperte")
            controparte = partita.get("controparte_nome", "")
            residuo = partita.get("residuo", 0)
            data_scad = partita.get("data_scadenza", "")
            try:
                created = await genera_alert(
                    "RIC_PARTITA_VECCHIA",
                    documento_id,
                    documento_coll,
                    f"Partita '{partita.get('tipo')}' scaduta il {data_scad} — residuo €{residuo:.2f}"
                    + (f" — {controparte}" if controparte else ""),
                    db,
                    extra={"partita_id": partita.get("id"), "residuo": residuo, "data_scadenza": data_scad},
                )
                if created:
                    stats["partita_vecchia_scaduta"] += 1
            except Exception as e:
                stats["errori"] += 1
                logger.error(f"[SCHEDULER-SCADENZE] errore alert RIC_PARTITA_VECCHIA per {documento_id}: {e}")

        # Partite aperte SENZA data_scadenza esplicita ma vecchie (nessuna scadenza
        # nota per accorgersi che sono in sospeso) — soglia 90 giorni dalla
        # creazione, stesso gap #6: prima nessuna visibilità su queste partite
        # "orfane" perché la query sopra richiede sempre una data_scadenza.
        soglia_stale = (datetime.now() - timedelta(days=90)).isoformat()
        stats["partita_vecchia_senza_scadenza"] = 0
        cursor_senza_scadenza = db["partite_aperte"].find(
            {
                "stato": {"$in": ["aperta", "parziale"]},
                "$or": [{"data_scadenza": None}, {"data_scadenza": ""}],
                "created_at": {"$lt": soglia_stale},
            },
            {"_id": 0, "id": 1, "tipo": 1, "documento_id": 1,
             "documento_collection": 1, "controparte_nome": 1,
             "residuo": 1, "created_at": 1}
        )
        async for partita in cursor_senza_scadenza:
            documento_id = partita.get("documento_id") or partita.get("id")
            documento_coll = partita.get("documento_collection", "partite_aperte")
            controparte = partita.get("controparte_nome", "")
            residuo = partita.get("residuo", 0)
            creata_il = partita.get("created_at", "")[:10]
            try:
                created = await genera_alert(
                    "RIC_PARTITA_VECCHIA",
                    documento_id,
                    documento_coll,
                    f"Partita '{partita.get('tipo')}' senza scadenza, aperta dal {creata_il} "
                    f"(oltre 90 giorni) — residuo €{residuo:.2f}"
                    + (f" — {controparte}" if controparte else ""),
                    db,
                    extra={"partita_id": partita.get("id"), "residuo": residuo, "created_at": partita.get("created_at")},
                )
                if created:
                    stats["partita_vecchia_senza_scadenza"] += 1
            except Exception as e:
                stats["errori"] += 1
                logger.error(f"[SCHEDULER-SCADENZE] errore alert RIC_PARTITA_VECCHIA (no scadenza) per {documento_id}: {e}")

        logger.info(
            f"📅 [SCHEDULER] Scadenze partite: {stats['totale_analizzate']} analizzate, "
            f"fatture={stats['fattura_fornitore']}, f24={stats['f24']}, "
            f"stipendi={stats['stipendio']}, pos={stats['pos_atteso']}, "
            f"partita_vecchia_scaduta={stats['partita_vecchia_scaduta']}, "
            f"partita_vecchia_senza_scadenza={stats['partita_vecchia_senza_scadenza']}, "
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


async def check_fornitori_duplicati_task():
    """
    Task eseguito ogni giorno alle 6:00.
    Genera l'alert FORN_DUPLICATO per i gruppi di fornitori con la STESSA
    P.IVA (certezza "alta") trovati da fornitori_dedupe.py::trova_duplicati().
    La funzione di rilevamento esisteva già (usata dall'endpoint manuale di
    merge) ma non era mai schedulata — l'alert era definito in
    alert_engine.py ma mai generato, vedi memoria/moduli/FORNITORI.md.

    Solo i gruppi "alta" (stessa P.IVA, zero ambiguità) per evitare falsi
    positivi da un job automatico notturno — i gruppi "media" (nome simile,
    fuzzy) restano disponibili solo nel controllo manuale in Fornitori.
    """
    logger.info("👥 [SCHEDULER] Controllo fornitori duplicati...")
    try:
        from app.database import Database
        from app.services.alert_engine import genera_alert
        from app.services.fornitori_dedupe import trova_duplicati
        from app.database import Collections

        db = Database.get_db()
        risultato = await trova_duplicati()
        gruppi_alta = [g for g in risultato.get("gruppi", []) if g.get("certezza") == "alta"]

        nuovi = 0
        for gruppo in gruppi_alta:
            fornitori = gruppo.get("fornitori", [])
            if len(fornitori) < 2:
                continue
            nomi = ", ".join(f.get("nome", f.get("id", "?")) for f in fornitori[:5])
            primo_id = fornitori[0].get("id")
            try:
                created = await genera_alert(
                    "FORN_DUPLICATO", primo_id, Collections.SUPPLIERS,
                    f"{len(fornitori)} fornitori con stessa P.IVA {gruppo.get('chiave')}: {nomi}",
                    db, extra={"fornitori_ids": [f.get("id") for f in fornitori]},
                )
                if created:
                    nuovi += 1
            except Exception:
                logger.exception(f"Errore generazione alert FORN_DUPLICATO per gruppo P.IVA {gruppo.get('chiave')}")

        if gruppi_alta:
            logger.info(f"👥 [SCHEDULER] Fornitori duplicati: {len(gruppi_alta)} gruppi (P.IVA identica), {nuovi} nuovi alert")
        else:
            logger.info("👥 [SCHEDULER] Nessun fornitore duplicato (P.IVA identica) trovato")
    except Exception as e:
        logger.error(f"👥 [SCHEDULER] Errore controllo fornitori duplicati: {e}")


async def paypal_recupera_fatture_email_task():
    """
    Task eseguito ogni giorno alle 5:30.
    I fornitori PayPal non mappati sono tipicamente esteri (MongoDB, SaaS
    vari): non emettono mai fattura elettronica XML, quindi Drive/PEC-SDI
    non li troveranno mai, a prescindere da quanto tempo passa. Cerca da
    sola nella posta invece di aspettare un click manuale — vedi
    app/services/paypal_email_recovery.py.
    """
    logger.info("💳 [SCHEDULER] Recupero fatture PayPal mancanti dalla posta...")
    try:
        from app.database import Database
        from app.services.paypal_email_recovery import recupera_fatture_mancanti_email

        db = Database.get_db()
        result = await recupera_fatture_mancanti_email(db)
        logger.info(
            f"💳 [SCHEDULER] Recupero fatture PayPal: {result.get('cercati', 0)} fornitori "
            f"cercati, {result.get('documenti_trovati', 0)} documenti nuovi trovati"
        )
    except Exception as e:
        logger.error(f"💳 [SCHEDULER] Errore recupero fatture PayPal: {e}")


async def gmail_full_scan_task():
    """
    Task eseguito ogni ora.
    Scansiona TUTTE le cartelle Gmail per documenti amministrativi.
    REGOLA: le fatture NON vengono scaricate da Gmail (solo PEC o import manuale).
    Dopo il download, esegue il pipeline di processamento automatico.
    """
    from app.config import settings
    if not getattr(settings, "ENABLE_GMAIL_IMAP", True):
        logger.info("📧 [SCHEDULER-GMAIL] Scansione Gmail saltata (ENABLE_GMAIL_IMAP spento).")
        return

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
    # Tesoreria AI: solo lettura + decisioni shadow. Nessun pagamento,
    # movimento contabile o altra azione di business viene eseguita qui.
    async def _tesoreria_shadow_job():
        from app.agents.orchestrator import run_agenti
        from app.database import Database
        try:
            await run_agenti(Database.get_db(), agente_specifico="TesoreriaShadow")
            logger.info("[SCHEDULER-AI-TESORERIA] fotografia shadow completata")
        except RuntimeError as exc:
            logger.info("[SCHEDULER-AI-TESORERIA] sospeso: %s", exc)
        except Exception as exc:
            logger.error("[SCHEDULER-AI-TESORERIA] errore: %s", exc)

    async def _cash_flow_shadow_job():
        from app.agents.orchestrator import run_agenti
        from app.database import Database
        try:
            await run_agenti(Database.get_db(), agente_specifico="CashFlow13WShadow")
            logger.info("[SCHEDULER-AI-CASHFLOW] previsione shadow completata")
        except RuntimeError as exc:
            logger.info("[SCHEDULER-AI-CASHFLOW] sospeso: %s", exc)
        except Exception as exc:
            logger.error("[SCHEDULER-AI-CASHFLOW] errore: %s", exc)

    async def _contabile_shadow_job():
        from app.agents.orchestrator import run_agenti
        from app.database import Database
        try:
            await run_agenti(Database.get_db(), agente_specifico="ContabileShadow")
            logger.info("[SCHEDULER-AI-CONTABILE] fotografia shadow completata")
        except RuntimeError as exc:
            logger.info("[SCHEDULER-AI-CONTABILE] sospeso: %s", exc)
        except Exception as exc:
            logger.error("[SCHEDULER-AI-CONTABILE] errore: %s", exc)

    async def _fiscale_shadow_job():
        from app.agents.orchestrator import run_agenti
        from app.database import Database
        try:
            await run_agenti(Database.get_db(), agente_specifico="FiscaleShadow")
            logger.info("[SCHEDULER-AI-FISCALE] fotografia shadow completata")
        except RuntimeError as exc:
            logger.info("[SCHEDULER-AI-FISCALE] sospeso: %s", exc)
        except Exception as exc:
            logger.error("[SCHEDULER-AI-FISCALE] errore: %s", exc)

    async def _acquisti_shadow_job():
        from app.agents.orchestrator import run_agenti
        from app.database import Database
        try:
            await run_agenti(Database.get_db(), agente_specifico="AcquistiShadow")
            logger.info("[SCHEDULER-AI-ACQUISTI] fotografia shadow completata")
        except RuntimeError as exc:
            logger.info("[SCHEDULER-AI-ACQUISTI] sospeso: %s", exc)
        except Exception as exc:
            logger.error("[SCHEDULER-AI-ACQUISTI] errore: %s", exc)

    async def _crediti_shadow_job():
        from app.agents.orchestrator import run_agenti
        from app.database import Database
        try:
            await run_agenti(Database.get_db(), agente_specifico="CreditiShadow")
            logger.info("[SCHEDULER-AI-CREDITI] aging shadow completato")
        except RuntimeError as exc:
            logger.info("[SCHEDULER-AI-CREDITI] sospeso: %s", exc)
        except Exception as exc:
            logger.error("[SCHEDULER-AI-CREDITI] errore: %s", exc)

    async def _compliance_shadow_job():
        from app.agents.orchestrator import run_agenti
        from app.database import Database
        try:
            await run_agenti(Database.get_db(), agente_specifico="ComplianceShadow")
            logger.info("[SCHEDULER-AI-COMPLIANCE] fotografia shadow completata")
        except RuntimeError as exc:
            logger.info("[SCHEDULER-AI-COMPLIANCE] sospeso: %s", exc)
        except Exception as exc:
            logger.error("[SCHEDULER-AI-COMPLIANCE] errore: %s", exc)

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

    # ── Google Drive: import fatture XML ogni 15 min ───────────────────────
    async def _drive_ingest_job():
        from app.database import Database
        from app.services import drive_invoice_ingest
        try:
            result = await drive_invoice_ingest.sync(Database.get_db())
            logger.info(f"[SCHEDULER-DRIVE-FATTURE] {result}")
        except Exception as e:
            logger.error(f"[SCHEDULER-DRIVE-FATTURE] errore: {e}")

    # ── Google Drive: import cedolini paga (PDF) ogni ora ──────────────────
    async def _drive_cedolini_job():
        from app.database import Database
        from app.services import drive_cedolini_ingest
        try:
            result = await drive_cedolini_ingest.sync(Database.get_db())
            logger.info(f"[SCHEDULER-DRIVE-CEDOLINI] {result}")
        except Exception as e:
            logger.error(f"[SCHEDULER-DRIVE-CEDOLINI] errore: {e}")

    # ── Google Drive: import corrispettivi RT (XML) ogni ora ───────────────
    async def _drive_corrispettivi_job():
        from app.database import Database
        from app.services import drive_corrispettivi_ingest
        try:
            result = await drive_corrispettivi_ingest.sync(Database.get_db())
            logger.info(f"[SCHEDULER-DRIVE-CORRISPETTIVI] {result}")
        except Exception as e:
            logger.error(f"[SCHEDULER-DRIVE-CORRISPETTIVI] errore: {e}")

    # ── Google Drive: import quietanze F24 (PDF) ogni ora ──────────────────
    # Canale acceso su scelta esplicita dell'utente (10/07/2026): stesso
    # motore unico dell'upload manuale (parsing + matching automatico F24).
    async def _drive_quietanze_job():
        from app.database import Database
        from app.services import drive_quietanze_ingest
        try:
            result = await drive_quietanze_ingest.sync(Database.get_db())
            logger.info(f"[SCHEDULER-DRIVE-QUIETANZE] {result}")
        except Exception as e:
            logger.error(f"[SCHEDULER-DRIVE-QUIETANZE] errore: {e}")

    async def _drive_estratti_conto_job():
        from app.database import Database
        from app.services import drive_estratti_conto_ingest
        try:
            result = await drive_estratti_conto_ingest.sync(Database.get_db())
            logger.info(f"[SCHEDULER-DRIVE-ESTRATTI-CONTO] {result}")
        except Exception as e:
            logger.error(f"[SCHEDULER-DRIVE-ESTRATTI-CONTO] errore: {e}")

    async def _bonifici_pdf_inbox_job():
        """Elabora anche i PDF bonifico gia' caricati in Import documenti."""
        from app.database import Database
        from app.services.bonifici_pdf_ingest import (
            processa_inbox_bonifici,
            riprocessa_bonifici_pendenti,
        )
        try:
            result = await processa_inbox_bonifici(Database.get_db())
            if result.get("letti"):
                logger.info(
                    "[SCHEDULER-BONIFICI-PDF] letti=%s salvati=%s "
                    "duplicati=%s associati=%s errori=%s",
                    result.get("letti"), result.get("salvati"),
                    result.get("duplicati"), result.get("associati"),
                    result.get("errori"),
                )
            pendenti = await riprocessa_bonifici_pendenti(Database.get_db())
            if pendenti.get("letti"):
                logger.info(
                    "[SCHEDULER-BONIFICI-PDF-PENDENTI] letti=%s associati=%s "
                    "non_associati=%s errori=%s",
                    pendenti.get("letti"), pendenti.get("associati"),
                    pendenti.get("non_associati"), pendenti.get("errori"),
                )
        except Exception as e:
            logger.error(f"[SCHEDULER-BONIFICI-PDF] errore: {e}")

    # ── Automazioni Prima Nota: le ex funzioni "manuali" girano da sole ────
    # 1. corrispettivi → prima nota cassa (idempotente)
    # 2. fatture provvisorie → cassa/banca secondo il metodo fornitore
    # 3. riconciliazione automatica con l'estratto conto
    async def _automazioni_prima_nota_job():
        from datetime import datetime as _dt
        anno_corrente = _dt.now().year
        try:
            from app.routers.prima_nota_module.sync import _sync_corrispettivi_impl
            r = await _sync_corrispettivi_impl(anno_corrente)
            logger.info(f"[SCHEDULER-PN-CORRISPETTIVI] inseriti={r.get('inseriti')} duplicati={r.get('duplicati')}")
        except Exception as e:
            logger.error(f"[SCHEDULER-PN-CORRISPETTIVI] errore: {e}")
        try:
            from app.routers.prima_nota_module.sync import auto_conferma_provvisori_per_metodo
            r = await auto_conferma_provvisori_per_metodo(anno=anno_corrente)
            logger.info(f"[SCHEDULER-PN-AUTOCONFERMA] cassa={r.get('mosse_cassa')} banca={r.get('mosse_banca')}")
        except Exception as e:
            logger.error(f"[SCHEDULER-PN-AUTOCONFERMA] errore: {e}")
        try:
            from app.services.riconciliazione_bancaria import riconcilia_movimenti_banca
            r = await riconcilia_movimenti_banca()
            logger.info(f"[SCHEDULER-PN-RICONCILIA] {r.get('message')}")
        except Exception as e:
            logger.error(f"[SCHEDULER-PN-RICONCILIA] errore: {e}")
        try:
            from app.database import Database
            from app.services.stipendi_bonifici import associa_bonifici_stipendi
            r = await associa_bonifici_stipendi(Database.get_db())
            if r.get("bonifici_associati"):
                logger.info(f"[SCHEDULER-STIPENDI-BONIFICI] associati={r['bonifici_associati']} "
                            f"complete={r['righe_stipendio_completate']}")
        except Exception as e:
            logger.error(f"[SCHEDULER-STIPENDI-BONIFICI] errore: {e}")
        try:
            from app.routers.prima_nota_module.sync import sposta_fatture_cassa_pagate_in_banca
            r = await sposta_fatture_cassa_pagate_in_banca(dry_run=False, anno=anno_corrente)
            if r.get("spostate_in_banca"):
                logger.info(f"[SCHEDULER-CASSA-VS-EC] spostate_in_banca={r['spostate_in_banca']}")
        except Exception as e:
            logger.error(f"[SCHEDULER-CASSA-VS-EC] errore: {e}")
        try:
            from app.routers.fatture_module.crud import pulisci_duplicati_invoices
            r = await pulisci_duplicati_invoices()
            if r.get("fatture_eliminate"):
                logger.info(f"[SCHEDULER-DEDUP-FATTURE] eliminate={r.get('fatture_eliminate')} "
                            f"(gruppi={r.get('gruppi_duplicati')})")
        except Exception as e:
            logger.error(f"[SCHEDULER-DEDUP-FATTURE] errore: {e}")
        try:
            from app.routers.paypal_statements import auto_associa_transazioni, auto_cerca_gmail
            r = await auto_associa_transazioni()
            logger.info(f"[SCHEDULER-PAYPAL-ASSOCIA] associate={r.get('associate')}/{r.get('analizzate')}")
            r2 = await auto_cerca_gmail()
            logger.info(f"[SCHEDULER-PAYPAL-GMAIL] cercate={r2.get('cercate')} associate={r2.get('associate_gmail')}")
        except Exception as e:
            logger.error(f"[SCHEDULER-PAYPAL-ASSOCIA] errore: {e}")

    scheduler.add_job(
        _scan_gmail_verbali_job,
        'interval', minutes=30,
        id="scan_gmail_verbali", name="Scan Gmail Verbali CdS (ogni 30 min)",
        replace_existing=True,
    )
    scheduler.add_job(
        _tesoreria_shadow_job,
        'interval', hours=1,
        next_run_time=datetime.now(),
        id="ai_tesoreria_shadow",
        name="Agente Tesoreria in shadow mode (ogni ora + al riavvio)",
        replace_existing=True,
    )
    scheduler.add_job(
        _cash_flow_shadow_job,
        'interval', hours=6,
        next_run_time=datetime.now(),
        id="ai_cash_flow_13w_shadow",
        name="Cash flow 13 settimane in shadow mode (ogni 6 ore + al riavvio)",
        replace_existing=True,
    )
    scheduler.add_job(
        _contabile_shadow_job,
        'interval', hours=6,
        next_run_time=datetime.now(),
        id="ai_contabile_shadow",
        name="Agente Contabile in shadow mode (ogni 6 ore + al riavvio)",
        replace_existing=True,
    )
    scheduler.add_job(
        _fiscale_shadow_job,
        'interval', hours=6,
        next_run_time=datetime.now(),
        id="ai_fiscale_shadow",
        name="Agente Fiscale in shadow mode (ogni 6 ore + al riavvio)",
        replace_existing=True,
    )
    scheduler.add_job(
        _acquisti_shadow_job,
        'interval', hours=24,
        next_run_time=datetime.now(),
        id="ai_acquisti_shadow",
        name="Agente Acquisti in shadow mode (giornaliero + al riavvio)",
        replace_existing=True,
    )
    scheduler.add_job(
        _crediti_shadow_job,
        'interval', hours=24,
        next_run_time=datetime.now(),
        id="ai_crediti_shadow",
        name="Agente Crediti in shadow mode (giornaliero + al riavvio)",
        replace_existing=True,
    )
    scheduler.add_job(
        _compliance_shadow_job,
        'interval', hours=24,
        next_run_time=datetime.now(),
        id="ai_compliance_shadow",
        name="Agente Compliance in shadow mode (giornaliero + al riavvio)",
        replace_existing=True,
    )
    scheduler.add_job(
        _link_verbali_fatture_job,
        'interval', minutes=60,
        id="link_verbali_fatture", name="Link Verbali ↔ Fatture (ogni 60 min)",
        replace_existing=True,
    )
    # Scelta utente (13/07/2026): ogni ORA (allineata al manuale) + un controllo
    # immediato a ogni riavvio del server (next_run_time=now: la prima esecuzione
    # parte subito, poi prosegue a intervalli regolari).
    scheduler.add_job(
        _drive_ingest_job,
        'interval', hours=1,
        next_run_time=datetime.now(),
        id="drive_fatture_ingest", name="Import Fatture da Google Drive (ogni ora + al riavvio)",
        replace_existing=True,
    )

    scheduler.add_job(
        _drive_cedolini_job,
        'interval', hours=1,
        next_run_time=datetime.now(),
        id="drive_cedolini_ingest", name="Import Cedolini da Google Drive (ogni ora + al riavvio)",
        replace_existing=True,
    )

    scheduler.add_job(
        _drive_corrispettivi_job,
        'interval', hours=1,
        next_run_time=datetime.now(),
        id="drive_corrispettivi_ingest", name="Import Corrispettivi da Google Drive (ogni ora + al riavvio)",
        replace_existing=True,
    )

    scheduler.add_job(
        _drive_quietanze_job,
        'interval', hours=1,
        next_run_time=datetime.now(),
        id="drive_quietanze_ingest", name="Import Quietanze F24 da Google Drive (ogni ora + al riavvio)",
        replace_existing=True,
    )

    scheduler.add_job(
        _drive_estratti_conto_job,
        'interval', hours=1,
        next_run_time=datetime.now(),
        id="drive_estratti_conto_ingest",
        name="Import Estratti Conto da Google Drive (ogni ora + al riavvio)",
        replace_existing=True,
    )

    scheduler.add_job(
        _bonifici_pdf_inbox_job,
        'interval', minutes=10,
        next_run_time=datetime.now(),
        id="bonifici_pdf_inbox",
        name="Elabora PDF bonifico da Import documenti (ogni 10 min + al riavvio)",
        replace_existing=True,
    )

    # ── Documenti da mittenti Gmail attendibili (ceraldigroupsrl@gmail.com),
    #    ogni ora. Copre TUTTI i tipi configurati in "Mittenti Email"
    #    (Integrazioni → Mittenti): fatture ESTERE (tipo_documento=
    #    "fattura_estera_pdf" — il sistema SDI/FatturaPA è SOLO italiano, i
    #    fornitori esteri mandano un semplice PDF in allegato, MAI un XML;
    #    il PDF viene scaricato e archiviato in Documenti categoria "Fatture
    #    estere (PDF)", pronto da associare/registrare — nessuna estrazione
    #    automatica dei dati per ora, decisione rimandata) più cedolino/
    #    pagopa/inps/inail/paypal/cartella esattoriale se un mittente è
    #    configurato per quei tipi. Le fatture ITALIANE arrivano SEMPRE via
    #    SDI/Aruba/Drive in XML, mai da qui.
    #    Trovato dormiente in sessione di debug 2026-07-14 (stesso pattern di
    #    bug già trovato altrove: nessuno chiamava sync_email_documents), attivato
    #    su richiesta esplicita dell'utente contestualmente alla pagina di
    #    gestione mittenti. Senza mittenti configurati è un no-op innocuo
    #    (0 mittenti attivi → 0 email scaricate).
    async def _mittenti_email_job():
        from app.database import Database
        from app.services.email_monitor_service import sync_email_documents
        try:
            result = await sync_email_documents(Database.get_db(), giorni=1)
            if result.get("success") is False:
                logger.info(f"[SCHEDULER-MITTENTI-EMAIL] non eseguito: {result.get('error')}")
            else:
                logger.info(f"[SCHEDULER-MITTENTI-EMAIL] nuovi={result.get('new_documents')} "
                            f"xml_processati={result.get('xml_processed')}")
        except Exception as e:
            logger.error(f"[SCHEDULER-MITTENTI-EMAIL] errore: {e}")

    scheduler.add_job(
        _mittenti_email_job,
        'interval', hours=1,
        id="mittenti_email_sync",
        name="Documenti da mittenti email attendibili: fatture estere XML + altri tipi (ogni ora)",
        replace_existing=True,
    )

    # ── Google Drive: nuovi canali documentali (dichiarazione IVA, cartelle
    # esattoriali, avvisi bonari) ogni ora. Ogni canale gira solo se acceso e
    # con la cartella configurata su Render (altrimenti no-op). ──
    async def _drive_documenti_job():
        from app.database import Database
        from app.services import drive_documenti_ingest
        try:
            result = await drive_documenti_ingest.sync_tutti(Database.get_db())
            logger.info(f"[SCHEDULER-DRIVE-DOCUMENTI] {result}")
        except Exception as e:
            logger.error(f"[SCHEDULER-DRIVE-DOCUMENTI] errore: {e}")

    scheduler.add_job(
        _drive_documenti_job,
        'interval', hours=1,
        id="drive_documenti_ingest",
        name="Import documenti fiscali (dichiarazione IVA/esattoriali/avvisi) da Drive (ogni ora)",
        replace_existing=True,
    )

    # Quadratura settimanale Elaborate ↔ gestionale: verifica che ogni file
    # archiviato in Drive/Elaborate abbia la sua fattura nel gestionale;
    # i buchi vengono re-importati (idempotente) e segnalati con un alert.
    async def _drive_quadratura_job():
        from app.database import Database
        from app.services import drive_invoice_ingest
        try:
            r = await drive_invoice_ingest.verifica_quadratura_elaborate(Database.get_db())
            logger.info(f"[SCHEDULER-DRIVE-QUADRATURA] {r if r.get('status') != 'ok' else {k: r[k] for k in ('totale_file_elaborate', 'quadrati', 'recuperati', 'errori')}}")
        except Exception as e:
            logger.error(f"[SCHEDULER-DRIVE-QUADRATURA] errore: {e}")

    scheduler.add_job(
        _drive_quadratura_job,
        CronTrigger(day_of_week="sun", hour=5, minute=0),
        id="drive_fatture_quadratura",
        name="Quadratura fatture Drive Elaborate (domenica ore 5:00)",
        replace_existing=True,
    )

    # COLLAUDO AUTOMATICO (richiesta utente 18/07/2026): ogni notte tutti gli
    # invarianti contabili vengono verificati; le violazioni diventano alert
    # COLLAUDO_INVARIANTE in dashboard, i check tornati puliti li risolvono.
    async def _collaudo_notturno_job():
        from app.database import Database
        from app.services.collaudo_invarianti import esegui_collaudo
        try:
            r = await esegui_collaudo(Database.get_db())
            logger.info(f"[SCHEDULER-COLLAUDO] checks={r['checks_totali']} "
                        f"violati={r['checks_violati']} violazioni={r['violazioni_totali']}")
        except Exception as e:
            logger.error(f"[SCHEDULER-COLLAUDO] errore: {e}")

    scheduler.add_job(
        _collaudo_notturno_job,
        CronTrigger(hour=4, minute=30),
        id="collaudo_invarianti",
        name="Collaudo automatico invarianti (ogni notte 4:30)",
        replace_existing=True,
    )

    # Stessa quadratura Elaborate anche per cedolini e corrispettivi
    # (richiesta utente 10/07): archivio Drive ↔ gestionale, buchi recuperati.
    async def _drive_quadratura_cedolini_job():
        from app.database import Database
        from app.services import drive_cedolini_ingest
        db = Database.get_db()
        try:
            r = await drive_cedolini_ingest.verifica_quadratura_elaborate(db)
            logger.info(f"[SCHEDULER-QUADRATURA-CEDOLINI] {r if r.get('status') != 'ok' else {k: r[k] for k in ('controllati', 'quadrati', 'recuperati', 'errori')}}")
        except Exception as e:
            logger.error(f"[SCHEDULER-QUADRATURA-CEDOLINI] errore: {e}")
        # Richiesta utente 15/07/2026: la quadratura sopra verifica solo
        # Drive ↔ documents_inbox (il file è arrivato), non che sia
        # diventato un cedolino vero in contabilità — un buco lì (parsing
        # fallito, dipendente non trovato) restava invisibile per sempre.
        try:
            bloccati = await drive_cedolini_ingest.verifica_documenti_bloccati(db)
            if bloccati["totale_bloccati"] > 0:
                logger.warning(f"[SCHEDULER-QUADRATURA-CEDOLINI] {bloccati['totale_bloccati']} documenti cedolini mai processati oltre {bloccati['soglia_ore']}h")
                from app.services.alert_engine import genera_alert
                await genera_alert(
                    "CEDOLINO_MAI_PROCESSATO", "quadratura_cedolini_bloccati", "documents_inbox",
                    f"{bloccati['totale_bloccati']} cedolini arrivati (Drive/email) ma mai diventati un "
                    f"cedolino vero in contabilità da oltre {bloccati['soglia_ore']} ore: verifica manualmente.",
                    db, extra={"bloccati": bloccati["bloccati"][:20]},
                )
        except Exception as e:
            logger.error(f"[SCHEDULER-QUADRATURA-CEDOLINI] errore verifica bloccati: {e}")

    async def _drive_quadratura_corrispettivi_job():
        from app.database import Database
        from app.services import drive_corrispettivi_ingest
        try:
            r = await drive_corrispettivi_ingest.verifica_quadratura_elaborate(Database.get_db())
            logger.info(f"[SCHEDULER-QUADRATURA-CORRISPETTIVI] {r if r.get('status') != 'ok' else {k: r[k] for k in ('controllati', 'quadrati', 'recuperati', 'errori')}}")
        except Exception as e:
            logger.error(f"[SCHEDULER-QUADRATURA-CORRISPETTIVI] errore: {e}")

    scheduler.add_job(
        _drive_quadratura_cedolini_job,
        CronTrigger(day_of_week="sun", hour=5, minute=15),
        id="drive_cedolini_quadratura",
        name="Quadratura cedolini Drive Elaborate (domenica ore 5:15)",
        replace_existing=True,
    )
    scheduler.add_job(
        _drive_quadratura_corrispettivi_job,
        CronTrigger(day_of_week="sun", hour=5, minute=30),
        id="drive_corrispettivi_quadratura",
        name="Quadratura corrispettivi Drive Elaborate (domenica ore 5:30)",
        replace_existing=True,
    )

    async def _drive_quadratura_quietanze_job():
        from app.database import Database
        from app.services import drive_quietanze_ingest
        try:
            r = await drive_quietanze_ingest.verifica_quadratura_elaborate(Database.get_db())
            logger.info(f"[SCHEDULER-QUADRATURA-QUIETANZE] {r if r.get('status') != 'ok' else {k: r[k] for k in ('controllati', 'quadrati', 'recuperati', 'errori')}}")
        except Exception as e:
            logger.error(f"[SCHEDULER-QUADRATURA-QUIETANZE] errore: {e}")

    scheduler.add_job(
        _drive_quadratura_quietanze_job,
        CronTrigger(day_of_week="sun", hour=5, minute=45),
        id="drive_quietanze_quadratura",
        name="Quadratura quietanze Drive Elaborate (domenica ore 5:45)",
        replace_existing=True,
    )
    scheduler.add_job(
        _automazioni_prima_nota_job,
        'interval', minutes=30,
        id="automazioni_prima_nota",
        name="Automazioni Prima Nota: corrispettivi + provvisori + riconciliazione (ogni 30 min)",
        replace_existing=True,
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

    # Task Controllo POS con calendario - ogni giorno alle 7:30.
    # Genera avvisi SOLO quando il calendario (lavorativi/festivi) non spiega
    # la differenza: accredito in ritardo oltre la data prevista, importo
    # banca diverso dal POS atteso, POS manuale diverso dall'XML oltre
    # tolleranza. Gli slittamenti fisiologici (weekend/festivi) non generano
    # mai nulla: sono il comportamento previsto dal calendario.
    async def controllo_pos_calendario_task():
        try:
            from app.routers.pos_corrispettivi_check import alert_oggi
            r = await alert_oggi(tolleranza_euro=0.5)
            logger.info(
                f"[SCHEDULER-POS] alert banca={r.get('num_alert_banca', 0)} "
                f"compensazioni={r.get('num_alert_compensazione', 0)} "
                f"xml mancanti={r.get('num_alert_xml_mancante', 0)}"
            )
        except Exception as e:
            logger.error(f"[SCHEDULER-POS] errore controllo POS calendario: {e}")

    scheduler.add_job(
        controllo_pos_calendario_task,
        CronTrigger(hour=7, minute=30),
        id="controllo_pos_calendario",
        name="Controllo POS con calendario accrediti (ogni giorno ore 7:30)",
        replace_existing=True
    )

    # Task Regolarità canoni noleggio - ogni giorno alle 7:45.
    # Per i veicoli con contratto ATTIVO controlla che arrivino fatture
    # entro NOLEGGIO_GIORNI_SENZA_FATTURA (35 gg, scelta utente); se
    # mancano rilegge l'ultima fattura: diciture di cessazione → avviso
    # informativo "probabile contratto cessato" (lo stato lo cambia solo
    # l'utente), altrimenti avviso soft "da verificare". Contratti
    # cessati: MAI avvisi (regola non negoziabile).
    async def controllo_canoni_noleggio_task():
        try:
            from app.services.noleggio import controlla_regolarita_canoni
            from app.database import Database
            r = await controlla_regolarita_canoni(Database.get_db())
            logger.info(f"[SCHEDULER-NOLEGGIO] controllo canoni: {r}")
        except Exception as e:
            logger.error(f"[SCHEDULER-NOLEGGIO] errore controllo canoni: {e}")

    scheduler.add_job(
        controllo_canoni_noleggio_task,
        CronTrigger(hour=7, minute=45),
        id="controllo_canoni_noleggio",
        name="Regolarità canoni noleggio (ogni giorno ore 7:45)",
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

    # Task Verifica retroattiva trattenute verbali - ogni giorno alle 8:30.
    # Ripesca i cedolini GIÀ archiviati (posta/Drive, in qualsiasi momento):
    # per le trattenute confermate/comunicate/in attesa cerca la voce di
    # trattenuta nei cedolini con periodo >= mese suggerito e applica le
    # stesse transizioni del percorso on-import (recuperata_in_busta /
    # non_trovata_nel_cedolino + alert). Idempotente, nessuna cancellazione.
    async def verifica_trattenute_retro_task():
        try:
            from app.services.trattenute_verbali_service import verifica_trattenute_retroattiva
            from app.database import Database
            r = await verifica_trattenute_retroattiva(Database.get_db())
            logger.info(f"[SCHEDULER-TRATTENUTE] verifica retroattiva: {r}")
        except Exception as e:
            logger.error(f"[SCHEDULER-TRATTENUTE] errore verifica retroattiva: {e}")

    scheduler.add_job(
        verifica_trattenute_retro_task,
        CronTrigger(hour=8, minute=30),
        id="verifica_trattenute_retro",
        name="Verifica retroattiva trattenute verbali nei cedolini (ogni giorno ore 8:30)",
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
    
    # Task Fornitori Duplicati - ogni giorno alle 6:00
    scheduler.add_job(
        check_fornitori_duplicati_task,
        CronTrigger(hour=6, minute=0),
        id="fornitori_duplicati_check",
        name="Controllo Fornitori Duplicati (ogni giorno ore 6:00)",
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

    # Task Recupero Fatture PayPal mancanti - ogni giorno alle 5:30
    scheduler.add_job(
        paypal_recupera_fatture_email_task,
        CronTrigger(hour=5, minute=30),
        id="paypal_recupera_fatture_email",
        name="Recupero Fatture PayPal mancanti dalla posta (ogni giorno ore 5:30)",
        replace_existing=True
    )

    scheduler.start()
    logger.info("✅ [SCHEDULER] Scheduler avviato")
    logger.info("   - Gmail Full Scan (tutte cartelle): ogni ora")
    logger.info("   - Verbali Email: ogni ora")
    logger.info("   - Scadenze Partite Aperte: ogni giorno ore 7:00")
    logger.info("   - Scadenze F24: ogni giorno ore 8:00 e 14:00")
    logger.info("   - Recupero Fatture PayPal mancanti: ogni giorno ore 5:30")


def stop_scheduler():
    """Ferma lo scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("🛑 [SCHEDULER] Scheduler fermato")
