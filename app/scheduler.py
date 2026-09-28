"""
Scheduler per task automatici.
- Email Verbali: Scan automatico ogni ora
"""
import logging
import uuid
import asyncio
import inspect
from datetime import datetime, timedelta, timezone
from functools import wraps
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.combining import OrTrigger
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

# Il lock locale mantiene seriali i job nella stessa istanza. In produzione e'
# affiancato da una lease atomica su Supabase, necessaria durante i rolling
# deploy; finche' la connessione non c'e' (avvio, test) resta il solo
# meccanismo disponibile.
_lock_scheduler_locale = asyncio.Lock()


async def _esegui_con_lock_locale(job_id, funzione, *args, **kwargs):
    if _lock_scheduler_locale.locked():
        logger.info(
            "[SCHEDULER] job %s rinviato: un'altra automazione e' in esecuzione",
            job_id,
        )
        return None
    async with _lock_scheduler_locale:
        risultato = funzione(*args, **kwargs)
        return await risultato if inspect.isawaitable(risultato) else risultato

async def _esegui_con_lease(job_id, funzione, *args, **kwargs):
    """Usa una lease Supabase tra istanze, con il lock locale come riserva."""
    from app.database import Database

    database = Database.db
    lease_factory = getattr(database, "scheduler_lease", None) if database else None
    if callable(lease_factory):
        async with lease_factory(str(job_id)) as acquired:
            if not acquired:
                logger.info(
                    "[SCHEDULER] job %s saltato: lease detenuta da un'altra istanza",
                    job_id,
                )
                return None
            risultato = funzione(*args, **kwargs)
            return await risultato if inspect.isawaitable(risultato) else risultato
    return await _esegui_con_lock_locale(job_id, funzione, *args, **kwargs)


class SchedulerConLease(AsyncIOScheduler):
    """APScheduler con lease Supabase o esclusione locale di compatibilita'."""

    def add_job(self, func, trigger=None, args=None, kwargs=None, id=None, **options):
        job_id = id or getattr(func, "__name__", str(uuid.uuid4()))

        @wraps(func)
        async def _locked(*job_args, **job_kwargs):
            return await _esegui_con_lease(
                job_id, func, *job_args, **job_kwargs
            )

        return super().add_job(
            _locked,
            trigger,
            args=args,
            kwargs=kwargs,
            id=id,
            **options,
        )


# Un solo oggetto per processo; la lease impedisce sovrapposizioni tra istanze.
scheduler = SchedulerConLease()

async def scan_verbali_email_task():
    """
    Task eseguito ogni ora.
    Scansiona le email per trovare nuovi verbali e completare quelli sospesi.
    Gated dagli interruttori Gmail generale e del canale verbali.
    """
    from app.config import settings
    if not getattr(settings, "ENABLE_GMAIL_IMAP", True):
        logger.info("🚗 [SCHEDULER] Scan email verbali saltato (Gmail spento).")
        return
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

        logger.info("🚗 [SCHEDULER] Scan verbali completato:")
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


async def verbali_notifications_task():
    from app.database import Database
    from app.services.partenopay_archive_import import dispatch_due_verbali_notifications
    result = await dispatch_due_verbali_notifications(Database.get_db())
    logger.info("[SCHEDULER-VERBALI] notifiche: %s", result)


#: Le partite di un fornitore: la fattura e la sua nota di credito. Non hanno
#: scadenza (decide il titolare quando pagare), quindi nessun alert «scaduta»
#: e nessuna «partita vecchia» nasce da loro.
TIPI_PARTITA_FORNITORE = ("fattura_fornitore", "nota_credito")


async def check_scadenze_partite_task():
    """
    Task eseguito ogni giorno alle 7:00.
    Scansiona partite_aperte con stato 'aperta' o 'parziale' e data_scadenza < oggi,
    e genera gli alert relazionali appropriati in base al tipo di partita:
      - f24               → F24_SCADUTO (+ F24_NON_PAGATO se non riconciliato)
      - stipendio         → CED_NON_PAGATO
      - pos_atteso        → BNK_POS_NON_RICONCILIATO

    L'alert_engine.genera_alert() è idempotente: non ricrea alert già aperti,
    quindi il task può girare ogni giorno senza duplicare.

    Le partite fornitore (fatture e note di credito) sono fuori da tutti e
    tre i giri: le fatture fornitore non hanno scadenza (decisione del
    titolare, 19/09/2026), e la «data_scadenza» che portano e' un +30
    inventato. Da lì nascevano 548 FAT_DA_PAGARE_SCADUTA «critical».
    """
    from app.database import Database
    from app.services.alert_engine import genera_alert

    logger.info("📅 [SCHEDULER] Controllo scadenze partite aperte...")

    try:
        db = Database.get_db()
        oggi = datetime.now().date().isoformat()

        # Tipi di partita → codice alert associato
        mapping_alert = {
            "f24": "F24_SCADUTO",
            "stipendio": "CED_NON_PAGATO",
            "pos_atteso": "BNK_POS_NON_RICONCILIATO",
        }

        stats = {t: 0 for t in mapping_alert}
        stats["fornitore_senza_scadenza"] = 0
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
            if tipo in TIPI_PARTITA_FORNITORE:
                stats["fornitore_senza_scadenza"] += 1
                continue
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

        stats["partita_vecchia_scaduta"] = 0
        cursor_scadute_senza_mapping = db["partite_aperte"].find(
            {
                "stato": {"$in": ["aperta", "parziale"]},
                "data_scadenza": {"$lt": oggi, "$ne": None},
                "tipo": {"$nin": list(mapping_alert.keys()) + list(TIPI_PARTITA_FORNITORE)},
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

        soglia_stale = (datetime.now() - timedelta(days=90)).isoformat()
        stats["partita_vecchia_senza_scadenza"] = 0
        cursor_senza_scadenza = db["partite_aperte"].find(
            {
                "stato": {"$in": ["aperta", "parziale"]},
                "$or": [{"data_scadenza": None}, {"data_scadenza": ""}],
                "created_at": {"$lt": soglia_stale},
                "tipo": {"$nin": list(TIPI_PARTITA_FORNITORE)},
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
            f"fornitore_saltate={stats['fornitore_senza_scadenza']}, f24={stats['f24']}, "
            f"stipendi={stats['stipendio']}, pos={stats['pos_atteso']}, "
            f"partita_vecchia_scaduta={stats['partita_vecchia_scaduta']}, "
            f"partita_vecchia_senza_scadenza={stats['partita_vecchia_senza_scadenza']}, "
            f"senza_mapping={stats['senza_mapping']}, errori={stats['errori']}"
        )

        totale_nuovi = sum(stats[t] for t in mapping_alert)
        if totale_nuovi > 0:
            try:
                from app.services.websocket_manager import notify_data_change
                await notify_data_change("scadenze_partite", {
                    "nuovi_alert": totale_nuovi,
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
    """Task eseguito ogni giorno alle 5:30."""
    from app.config import settings
    if not getattr(settings, "ENABLE_GMAIL_IMAP", True):
        logger.info("💳 [SCHEDULER] Recupero fatture PayPal saltato (Gmail spento).")
        return
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
    """Ogni ora: posta di tutte le cartelle, con cursore per cartella.

    Il primo giro parte dai messaggi piu' recenti e scende fino al primo della
    casella; da li' in poi legge solo i nuovi. Il cursore sta su Supabase e il
    giro riprende dopo un riavvio. Un login rifiutato apre un alert e manda
    un Telegram: non e' un giro vuoto.
    """
    from app.config import settings
    if not getattr(settings, "ENABLE_GMAIL_IMAP", True):
        logger.info("📧 [SCHEDULER-GMAIL] Scansione Gmail saltata (ENABLE_GMAIL_IMAP spento).")
        return

    from app.database import Database
    from app.services.email_full_download import scarica_posta_con_cursori

    db = Database.get_db()
    try:
        esito = await scarica_posta_con_cursori(db)
    except Exception as e:
        logger.error("[SCHEDULER-GMAIL] Errore scansione Gmail (%s): %s", type(e).__name__, e)
        return
    logger.info("[SCHEDULER-GMAIL] %s", {k: v for k, v in esito.items() if k != "pdf_per_categoria"})
    if esito.get("pdf_salvati", 0) > 0:
        try:
            from app.services.post_download_pipeline import esegui_pipeline_completa
            logger.info("[SCHEDULER-GMAIL] Pipeline: %s", await esegui_pipeline_completa(db))
        except Exception as pipe_err:
            logger.error("[SCHEDULER-GMAIL] Pipeline errore (%s): %s",
                         type(pipe_err).__name__, pipe_err)


def start_scheduler():
    """Avvia lo scheduler con i task programmati."""
    logger.info("🚀 [SCHEDULER] Configurazione scheduler...")
    avvio = datetime.now()

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
        from app.config import settings
        if not getattr(settings, "ENABLE_GMAIL_IMAP", True):
            logger.info("[SCHEDULER-VERBALI-GMAIL] saltato: Gmail spento")
            return
        if not getattr(settings, "ENABLE_EMAIL_VERBALI_SYNC", True):
            logger.info("[SCHEDULER-VERBALI-GMAIL] saltato: canale verbali spento")
            return
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


    GIRI_CARTELLA_UNICA = 1000

    async def _drive_cartella_unica_job():
        from app.database import Database
        from app.services import drive_cartella_unica
        if not drive_cartella_unica.attivo():
            return
        try:
            # Tutta la coda, un giro dopo l'altro (decisione del titolare):
            # il lotto resta solo come passo di lavoro, non come tetto.
            result = await drive_cartella_unica.svuota(Database.get_db(), max_giri=GIRI_CARTELLA_UNICA)
            logger.info(f"[SCHEDULER-DRIVE-CARTELLA-UNICA] {result}")
        except Exception as e:
            logger.error(f"[SCHEDULER-DRIVE-CARTELLA-UNICA] errore: {type(e).__name__}: {e}")

    async def _stampe_controllo_job():
        # Stampe di controllo delle buste con la definitiva identica: via da
        # Drive. Giro proprio, non in coda allo svuotamento (che dura ore):
        # lavora solo su ELABORATE, dove lo smistatore non legge.
        from app.database import Database
        from app.services import drive_cartella_unica
        if not drive_cartella_unica.attivo():
            return
        try:
            from app.services.cedolini_stampe_controllo import pulisci_archivio
            pulizia = await pulisci_archivio(Database.get_db(), gruppi_per_giro=None)
            logger.info(f"[SCHEDULER-STAMPE-CONTROLLO] {pulizia}")
        except Exception as e:
            logger.error(f"[SCHEDULER-STAMPE-CONTROLLO] errore: {type(e).__name__}: {e}")

    async def _drive_censimento_doppioni_job():
        # Censimento della cartella GESTIONALE richiesto dal titolare: elenca
        # le copie identiche e, in modalita' «marca», le rinomina soltanto.
        from app.database import Database
        from app.services import drive_censimento_doppioni as censimento
        if censimento.modalita() == "off":
            return
        try:
            result = await censimento.giro(Database.get_db())
            logger.info(f"[SCHEDULER-DRIVE-CENSIMENTO] {result}")
        except Exception as e:
            logger.error(f"[SCHEDULER-DRIVE-CENSIMENTO] errore: {type(e).__name__}: {e}")


    async def _f24_doppioni_job():
        # Stesso F24 arrivato da due PDF: quarantena della copia (reversibile).
        import os
        from app.database import Database
        from app.services.f24_doppioni import metti_in_quarantena
        if os.getenv("F24_QUARANTENA_DOPPIONI", "false").strip().lower() not in ("true", "1", "si"):
            return
        try:
            result = await metti_in_quarantena(Database.get_db(), dry_run=False)
            logger.info("[SCHEDULER-F24-DOPPIONI] gruppi=%s in_quarantena=%s",
                        result["gruppi"], result["in_quarantena"])
        except Exception as e:
            logger.error(f"[SCHEDULER-F24-DOPPIONI] errore: {type(e).__name__}: {e}")


    async def _fonti_ferme_job():
        # Una fonte che smette di arrivare non da' errori: da' silenzio. Il
        # controllo gira da solo, non piu' in coda a un import Drive.
        from app.database import Database
        try:
            from app.services.fonti_ferme import controlla_fonti_ferme
            stato = await controlla_fonti_ferme(Database.get_db())
            if stato.get("ferme"):
                logger.warning("[SCHEDULER-FONTI-FERME] %s", stato["ferme"])
            else:
                logger.info("[SCHEDULER-FONTI-FERME] tutte aggiornate")
        except Exception as e:
            logger.error(f"[SCHEDULER-FONTI-FERME] errore: {type(e).__name__}: {e}")

    async def _controlli_incrociati_job():
        # Segnali, mai correzioni: beneficiario diverso, fattura pagata due
        # volte, importo anomalo, mesi di estratto mancanti, RT dimenticata.
        from app.database import Database
        try:
            from app.services.controlli_incrociati import esegui_controlli
            esito = await esegui_controlli(Database.get_db())
            logger.info("[SCHEDULER-CONTROLLI-INCROCIATI] %s", esito)
        except Exception as e:
            logger.error(f"[SCHEDULER-CONTROLLI-INCROCIATI] errore: {type(e).__name__}: {e}")

    async def _bonifici_pdf_inbox_job():
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

    _sumup_riallineo_fatto = {}

    async def _sumup_sync_job():
        from app.database import Database
        from app.services import sumup_sync

        try:
            oggi = datetime.now().date()
            # Prima il riallineamento, che legge solo il database e dura
            # secondi: messo dopo la sincronizzazione (minuti di API), un
            # deploy a meta' giro lo saltava ogni volta. Una volta al giorno le
            # giornate dell'anno fuori dalla finestra dei trenta giorni si
            # riallineano all'archivio senza doppioni.
            if _sumup_riallineo_fatto.get("giorno") != oggi.isoformat():
                try:
                    esito = await sumup_sync.riallinea_chiusure_da_archivio(
                        Database.get_db(), f"{oggi.year}-01-01",
                        (oggi - timedelta(days=31)).isoformat(),
                    )
                    _sumup_riallineo_fatto["giorno"] = oggi.isoformat()
                    if esito["corrette"]:
                        logger.info("[SCHEDULER-SUMUP] chiusure riallineate: %s", esito["corrette"])
                except Exception as exc:  # la sincronizzazione del mese va fatta comunque
                    logger.error("[SCHEDULER-SUMUP] riallineamento chiusure non riuscito: %s: %s",
                                 type(exc).__name__, exc)
            r = await sumup_sync.sincronizza(
                Database.get_db(), (oggi - timedelta(days=30)).isoformat(), oggi.isoformat()
            )
            logger.info(
                "[SCHEDULER-SUMUP] giornate=%s lordo=%s netto=%s",
                len(r.get("giornate") or []), r.get("totale_lordo", 0),
                r.get("totale_netto", 0),
            )
        except sumup_sync.SumUpNonConfigurato:
            logger.info("[SCHEDULER-SUMUP] credenziali non configurate")
        except Exception as e:
            logger.error(f"[SCHEDULER-SUMUP] errore: {e}")

    async def _dedup_fatture_job():
        """Identita' canonica dall'XML per le fatture che ne sono prive,
        dedup provata per hash (archivio reversibile + storno della scrittura
        doppia), storno delle registrazioni non ammesse. Stesso giro di
        `POST /api/invoices/bonifica-identita`; qui gira da solo, ogni 30
        minuti, senza dipendere dalla durata degli altri job."""
        try:
            from app.database import Database
            from app.services.fatture_identita import bonifica_identita_fatture
            r = await bonifica_identita_fatture(Database.get_db())
            dedup = r.get("dedup") or {}
            impronte = r.get("impronte") or {}
            logger.info(
                "[SCHEDULER-DEDUP-FATTURE] identita=%s senza_xml=%s impronte=%s "
                "(restanti=%s) archiviate=%s (gruppi=%s) storni=%s",
                (r.get("identita") or {}).get("normalizzate"),
                (r.get("identita") or {}).get("senza_xml"),
                impronte.get("calcolate"), impronte.get("restanti"),
                dedup.get("fatture_archiviate"), dedup.get("gruppi_duplicati"),
                (r.get("storni") or {}).get("stornate"),
            )
        except Exception as e:
            logger.error(f"[SCHEDULER-DEDUP-FATTURE] errore: {e}")

    async def _quietanze_orfane_job():
        """Quietanze F24 rimaste senza modello: si ricollegano al loro F24,
        anche gia' pagato in banca. Job a se': dentro «Automazioni Prima
        Nota», che in produzione dura ore e riparte a ogni deploy, non ci
        arrivava mai."""
        try:
            from app.database import Database
            from app.services.quietanze_import import ricollega_quietanze_orfane
            r = await ricollega_quietanze_orfane(Database.get_db())
            logger.info("[SCHEDULER-QUIETANZE-ORFANE] orfane=%s collegate=%s",
                        r.get("orfane"), r.get("collegate"))
        except Exception as e:
            logger.error("[SCHEDULER-QUIETANZE-ORFANE] errore: %s: %s", type(e).__name__, e)

    async def _pagamenti_dichiarati_job():
        """Report del titolare: le righe ancora aperte (fattura arrivata dopo,
        riga dichiarata da scrivere, assegno comparso in banca). Job a se':
        dentro «Automazioni Prima Nota», che dura ore e riparte a ogni
        deploy, le 182 fatture pagate in banca aspettavano senza fine."""
        try:
            from app.database import Database
            from app.routers.ritenute import allinea_ritenute_fatture
            from app.services.pagamenti_dichiarati_titolare import (
                applica_pagamenti_dichiarati, ripara_righe_dichiarate,
            )
            db = Database.get_db()
            logger.info("[SCHEDULER-PAGAMENTI-DICHIARATI] ritenute %s, righe %s",
                        await allinea_ritenute_fatture(db), await ripara_righe_dichiarate(db))
            r = await applica_pagamenti_dichiarati(db, solo_pendenti=True)
            logger.info("[SCHEDULER-PAGAMENTI-DICHIARATI] %s", r.get("conteggi") or r.get("saltato"))
        except Exception as e:
            logger.error("[SCHEDULER-PAGAMENTI-DICHIARATI] errore: %s: %s", type(e).__name__, e)

    async def _fatture_emesse_job():
        """Rete delle fatture emesse: quelle finite fra le passive tornano al
        loro archivio (con storno), e il corrispettivo arrivato dopo la
        fattura si aggancia. Pochi documenti, idempotente."""
        from app.database import Database
        from app.services.fatture_emesse import riallinea
        try:
            esito = await riallinea(Database.get_db())
            if esito.get("spostate") or esito.get("agganciate") or esito.get("errori"):
                logger.info(f"[SCHEDULER-FATTURE-EMESSE] {esito}")
        except Exception as e:
            logger.error(f"[SCHEDULER-FATTURE-EMESSE] errore: {type(e).__name__}: {e}")

    async def _fatture_estere_job():
        """Fatture estere da confermare riallineate alle regole di classificazione attuali."""
        from app.database import Database
        from app.routers.fatture_estera_verifica import riallinea_fatture_estere_in_attesa
        try:
            esito = await riallinea_fatture_estere_in_attesa(Database.get_db())
            if esito.get("riregistrate") or esito.get("errori"):
                logger.info(f"[SCHEDULER-FATTURE-ESTERE] {esito}")
        except Exception as e:
            logger.error(f"[SCHEDULER-FATTURE-ESTERE] errore: {type(e).__name__}: {e}")

    async def _f24_quietanze_banca_job():
        """F24 del commercialista ↔ ravvedimento, poi quietanze ↔ addebiti I24.

        Pochi secondi, idempotenti. Stavano in «Automazioni Prima Nota», che
        parte 13 minuti dopo l'avvio e dura a lungo: il 27/09/2026 i deploy
        ravvicinati l'hanno interrotto dalle 02:47 in poi e nessun riscontro
        arrivava ai dati. L'ordine conta: il legame di ravvedimento e' gia'
        scritto quando il riscontro lo porta nella vista della banca."""
        from app.database import Database
        db = Database.get_db()
        try:
            from app.services.f24_ravvedimento import collega_ravvedimenti
            r = await collega_ravvedimenti(db)
            logger.info("[SCHEDULER-F24] ravvedimenti abbinati=%s ambigui=%s scritti=%s",
                        r["conteggi"]["abbinati"], r["conteggi"]["ambigui"], r["scritti"])
        except Exception as e:
            logger.error("[SCHEDULER-F24] ravvedimenti: %s: %s", type(e).__name__, e)
        try:
            from app.services.f24_controllo_incrociato import riscontra_quietanze_banca
            r = await riscontra_quietanze_banca(db)
            logger.info("[SCHEDULER-F24] quietanze/banca riscontrati=%s da_verificare=%s scritti=%s",
                        r["conteggi"].get("riscontrati"), r["conteggi"].get("da_verificare"), r["scritti"])
        except Exception as e:
            logger.error("[SCHEDULER-F24] quietanze/banca: %s: %s", type(e).__name__, e)
        try:
            # Dopo il riscontro: la rata prende l'addebito dalla sua quietanza.
            from app.services.dilazioni_inps import collega_dilazioni
            r = await collega_dilazioni(db)
            logger.info("[SCHEDULER-F24] dilazioni INPS=%s scritti=%s", r["dilazioni"], r.get("scritti"))
        except Exception as e:
            logger.error("[SCHEDULER-F24] dilazioni INPS: %s: %s", type(e).__name__, e)

    async def _banca_versamenti_proiezione_job():
        """Assegni, versamenti di contante e proiezione dei movimenti bancari
        in Prima Nota. Pochi secondi, idempotenti: job a se', come le
        quietanze, perche' dentro «Automazioni Prima Nota» (ore di lavoro,
        riparte a ogni deploy) non ci arrivavano mai. L'ordine conta: la
        gamba di cassa del versamento esiste gia' quando la proiezione la cerca."""
        from app.database import Database
        db = Database.get_db()
        try:
            # Primo passo: una riga per movimento, qualunque export l'abbia
            # portata (estratto scaricato la settimana scorsa e oggi, vecchio
            # archivio, banca diretta). Tutto quello che segue legge righe uniche.
            from app.services.doppioni_estratto_conto import unifica_copie
            r = await unifica_copie(db)
            if r.get("copie") or r.get("entrambe_collegate"):
                logger.info("[SCHEDULER-BANCA] estratto conto copie unificate=%s entrambe_collegate=%s",
                            r.get("copie"), r.get("entrambe_collegate"))
        except Exception as e:
            logger.error("[SCHEDULER-BANCA] copie estratto conto: %s: %s", type(e).__name__, e)
        try:
            from app.services.assegni_estratto_conto import sincronizza_assegni_da_estratto_conto
            r = await sincronizza_assegni_da_estratto_conto(db, include_provvisori=True)
            logger.info("[SCHEDULER-BANCA] assegni riconciliati=%s creati=%s",
                        r.get("assegni_riconciliati"), r.get("assegni_creati"))
        except Exception as e:
            logger.error("[SCHEDULER-BANCA] assegni: %s: %s", type(e).__name__, e)
        try:
            # Una fattura pagata in piu' bonifici allo stesso fornitore.
            from app.services.bank_payment_allocations import riconcilia_acconti_in_sospeso
            r = await riconcilia_acconti_in_sospeso(db)
            if r.get("collegati_count") or r.get("ambigui"):
                logger.info("[SCHEDULER-BANCA] acconti collegati=%s ambigui=%s",
                            r.get("collegati_count"), r.get("ambigui"))
        except Exception as e:
            logger.error("[SCHEDULER-BANCA] acconti: %s: %s", type(e).__name__, e)
        try:
            # Fatture dell'anno prima pagate quest'anno: solo il debito.
            from app.services.debiti_anno_precedente import abbina_pagamenti, recupera_da_drive
            r = await recupera_da_drive(db)
            if r.get("letti"):
                logger.info("[SCHEDULER-BANCA] debiti anno precedente letti=%s registrati=%s restano=%s",
                            r.get("letti"), r.get("registrati"), r.get("restano"))
            r = await abbina_pagamenti(db)
            if r.get("collegati") or r.get("ambigui"):
                logger.info("[SCHEDULER-BANCA] debiti anno precedente pagati=%s ambigui=%s",
                            len(r.get("collegati") or []), r.get("ambigui"))
        except Exception as e:
            logger.error("[SCHEDULER-BANCA] debiti anno precedente: %s: %s", type(e).__name__, e)
        try:
            from app.services.doppioni_estratto_conto import eredita_categorie_da_copie
            r = await eredita_categorie_da_copie(db)
            logger.info("[SCHEDULER-BANCA] categorie senza=%s ereditate=%s contraddette=%s",
                        r.get("senza_categoria"), r.get("ereditate"), r.get("contraddette"))
            from app.services.categorizzazione_movimenti import backfill_categorie_banca
            r = await backfill_categorie_banca(db, anno=None, dry_run=False, con_stipendi=False)
            logger.info("[SCHEDULER-BANCA] categorie da causale aggiornate=%s restano=%s",
                        r.get("aggiornati"), r.get("non_categorizzati_totale"))
        except Exception as e:
            logger.error("[SCHEDULER-BANCA] categorie: %s: %s", type(e).__name__, e)
        try:
            from app.services.versamenti_contanti import riconosci_versamenti
            r = await riconosci_versamenti(db, dry_run=False)
            logger.info(
                "[SCHEDULER-BANCA] versamenti=%s create_cassa=%s create_banca=%s doppioni=%s/%s",
                r.get("versamenti"), r.get("gambe_cassa_create"), r.get("gambe_banca_create"),
                r.get("doppioni_cassa_tolti"), r.get("doppioni_banca_tolti"),
            )
        except Exception as e:
            logger.error("[SCHEDULER-BANCA] versamenti: %s: %s", type(e).__name__, e)
        try:
            # Carta SumUp: stipendi, fatture, spese di lite e Prima Nota sul suo
            # conto. Qui e non nel giro lungo: quello ogni deploy lo interrompe.
            from app.services.sumup_conto import abbina_movimenti_sumup
            r = await abbina_movimenti_sumup(db)
            logger.info("[SCHEDULER-BANCA] carta SumUp stipendi=%s fatture=%s citate=%s",
                        r.get("stipendi_abbinati"), r.get("fatture_abbinate"),
                        r.get("fatture_citate_abbinate"))
        except Exception as e:
            logger.error("[SCHEDULER-BANCA] carta SumUp: %s: %s", type(e).__name__, e)
        try:
            # Prima del fascicolo: l'uscita che cita una sentenza va in Banca
            # come spesa di lite, non resta senza categoria.
            from app.services.atti_giudiziari import collega_pagamenti
            r = await collega_pagamenti(db, collezioni=("estratto_conto_movimenti",))
            if r.get("collegati"):
                logger.info("[SCHEDULER-BANCA] spese di lite collegate=%s", r.get("collegati"))
        except Exception as e:
            logger.error("[SCHEDULER-BANCA] atti giudiziari: %s: %s", type(e).__name__, e)
        try:
            from app.services.proiezione_bancaria import proietta_movimenti_bancari_semantici
            r = await proietta_movimenti_bancari_semantici(db)
            logger.info("[SCHEDULER-BANCA] proiezione proiettati=%s doppioni_tolti=%s rate_mutuo=%s",
                        r.get("proiettati"), r.get("doppioni_tolti"), r.get("rate_mutuo"))
        except Exception as e:
            logger.error("[SCHEDULER-BANCA] proiezione: %s: %s", type(e).__name__, e)
        try:
            # Conti CEE sulle righe di Prima Nota che ne sono prive (solo i
            # campi mancanti; il conto di tesoreria segue il metodo dichiarato).
            from app.services.bonifica_prima_nota_conti import applica as completa_conti
            r = await completa_conti(db, actor="scheduler-banca")
            if r.get("righe_aggiornate"):
                logger.info("[SCHEDULER-BANCA] conti Prima Nota completati=%s", r.get("righe_aggiornate"))
        except Exception as e:
            logger.error("[SCHEDULER-BANCA] conti Prima Nota: %s: %s", type(e).__name__, e)
        try:
            # Fatture rimaste senza detraibilita' decisa o ferme DA_VERIFICARE:
            # a lotti, finche' l'arretrato non e' smaltito.
            from app.services.iva_detraibilita import completa_iva_pregresso
            r = await completa_iva_pregresso(db)
            if r.get("candidate"):
                logger.info("[SCHEDULER-BANCA] IVA fatture %s", r)
        except Exception as e:
            logger.error("[SCHEDULER-BANCA] IVA fatture: %s: %s", type(e).__name__, e)
        try:
            # Le fatture che il giornale aveva rifiutato in attesa della
            # classificazione IVA appena fatta sopra: stesso aggancio dell'import.
            from app.services.registrazione_contabile import registra_fatture_rimaste_fuori
            r = await registra_fatture_rimaste_fuori(db)
            if r.get("candidate"):
                logger.info("[SCHEDULER-BANCA] fatture nel giornale %s", r)
        except Exception as e:
            logger.error("[SCHEDULER-BANCA] fatture nel giornale: %s: %s", type(e).__name__, e)
        try:
            # Fatture che non hanno mai propagato fattura.created (import del
            # 14/09/2026): partita, alert e audit dagli stessi handler.
            from app.services.recupero_fatture_pregresso import ripubblica_a_lotti
            r = await ripubblica_a_lotti(db)
            if r.get("candidate"):
                logger.info("[SCHEDULER-BANCA] fattura.created ripubblicato %s", r)
        except Exception as e:
            logger.error("[SCHEDULER-BANCA] replay fattura.created: %s: %s", type(e).__name__, e)
        try:
            # Ultimo passo: chiude gli alert che i passi sopra (e gli altri
            # motori) hanno reso falsi e mette in quarantena i verbali nati
            # dai numeri di fattura. Solo per id, con il motivo scritto.
            from app.services.bonifiche_automatiche import esegui_bonifiche
            r = await esegui_bonifiche(db)
            logger.info("[SCHEDULER-BANCA] bonifiche %s", r.get("conteggi"))
        except Exception as e:
            logger.error("[SCHEDULER-BANCA] bonifiche: %s: %s", type(e).__name__, e)

    async def _automazioni_prima_nota_job():
        from datetime import datetime as _dt
        anno_corrente = _dt.now().year
        try:
            from app.database import Database
            from app.services.scritture_contabili import bonifica_accrediti_pos_numia

            r = await bonifica_accrediti_pos_numia(
                Database.get_db(), anno_corrente, dry_run=False,
                actor={"sub": "scheduler-pos-numia"},
            )
            recupero = r.get("recupero_storico") or {}
            if (r.get("righe_prima_nota_archiviate")
                    or recupero.get("creati") or recupero.get("aggiornati")):
                logger.info(
                    "[SCHEDULER-NUMIA-EC] giorni=%s riconciliati=%s "
                    "legacy_archiviate=%s creati=%s aggiornati=%s",
                    r.get("giornate_numia", 0),
                    r.get("giornate_riconciliate", 0),
                    r.get("righe_prima_nota_archiviate", 0),
                    recupero.get("creati", 0), recupero.get("aggiornati", 0),
                )
        except Exception as e:
            logger.error(f"[SCHEDULER-NUMIA-EC] errore: {e}")
        try:
            from app.database import Database
            from app.services import bonifica_pos_xml
            r = await bonifica_pos_xml.applica(
                Database.get_db(), anno=anno_corrente,
                actor={"sub": "scheduler_pos_reale"},
            )
            if r.get("righe_archiviate") or r.get("trasferimenti_reali_ricostruiti"):
                logger.info(
                    "[SCHEDULER-POS-XML] archiviate=%s ricostruite=%s attesa=%s",
                    r.get("righe_archiviate", 0),
                    r.get("trasferimenti_reali_ricostruiti", 0),
                    r.get("giornate_riportate_in_attesa", 0),
                )
        except Exception as e:
            logger.error(f"[SCHEDULER-POS-XML] errore: {e}")
        try:
            from app.routers.prima_nota_module.sync import _sync_corrispettivi_impl
            r = await _sync_corrispettivi_impl(anno_corrente)
            logger.info(f"[SCHEDULER-PN-CORRISPETTIVI] inseriti={r.get('inseriti')} duplicati={r.get('duplicati')}")
        except Exception as e:
            logger.error(f"[SCHEDULER-PN-CORRISPETTIVI] errore: {e}")
        # Fase 0 (15/09/2026): auto_conferma_provvisori_per_metodo spento — vedi
        # PROMPT_CLAUDE_CODE_FASE_0.md punto 1. Confermava pagamenti in cassa
        # senza alcuna prova, solo per metodo dichiarato del fornitore.
        try:
            from app.services.riconciliazione_bancaria import riconcilia_movimenti_banca
            r = await riconcilia_movimenti_banca()
            logger.info(f"[SCHEDULER-PN-RICONCILIA] {r.get('message')}")
        except Exception as e:
            logger.error(f"[SCHEDULER-PN-RICONCILIA] errore: {e}")
        try:
            from app.database import Database
            from app.routers.paypal_statements import _auto_riconcilia
            r = await _auto_riconcilia(Database.get_db(), applica=True)
            logger.info(
                f"[SCHEDULER-PAYPAL-BANCA] riconciliati={r.get('riconciliati')} "
                f"ambigui={r.get('ambigui')}"
            )
        except Exception as e:
            logger.error(f"[SCHEDULER-PAYPAL-BANCA] errore: {e}")
        from app.database import Database
        from app.services.aggiornamento_dati import registra_giro_riconciliazione
        iniziato = datetime.now(timezone.utc)
        try:
            from app.services.reconciliation_orchestrator import (
                riconcilia_documenti_e_pagamenti,
            )
            r = await riconcilia_documenti_e_pagamenti(Database.get_db())
            logger.info(
                "[SCHEDULER-DOCUMENTI-PAGAMENTI] assegni=%s salari=%s f24=%s bonifici=%s",
                (r.get("assegni_intenti") or {}).get("collegati", 0),
                (r.get("salari") or {}).get("bonifici_associati", 0),
                (r.get("f24") or {}).get("movimenti_associati", 0),
                (r.get("bonifici_pdf") or {}).get("associati", 0),
            )
            # L'esito resta in `sistema_stato`: lo legge il riquadro
            # «Aggiornamento dati» della Dashboard.
            await registra_giro_riconciliazione(Database.get_db(), iniziato_at=iniziato, risultato=r)
        except Exception as e:
            logger.error("[SCHEDULER-DOCUMENTI-PAGAMENTI] errore: %s: %s", type(e).__name__, e)
            await registra_giro_riconciliazione(Database.get_db(), iniziato_at=iniziato, errore=e)
        # Fase 0 (15/09/2026): sposta_fatture_cassa_pagate_in_banca spento —
        # senza il ramo cassa di auto_registra_prima_nota (punto 2) non ha
        # più righe cassa automatiche da spostare, e rischierebbe di
        # spostare righe inserite a mano.
        # 17/09/2026: la dedup fatture (identita' dall'XML → dedup per hash →
        # storni) e' un job a se' (`dedup_fatture`, sotto): dentro questo giro
        # veniva dopo la riconciliazione bancaria, che in produzione dura ore,
        # e non e' mai arrivata a girare.
        try:
            from app.routers.paypal_statements import auto_associa_transazioni, auto_cerca_gmail
            r = await auto_associa_transazioni()
            logger.info(f"[SCHEDULER-PAYPAL-ASSOCIA] associate={r.get('associate')}/{r.get('analizzate')}")
            r2 = await auto_cerca_gmail()
            logger.info(f"[SCHEDULER-PAYPAL-GMAIL] cercate={r2.get('cercate')} associate={r2.get('associate_gmail')}")
        except Exception as e:
            logger.error(f"[SCHEDULER-PAYPAL-ASSOCIA] errore: {e}")

    scheduler.add_job(
        _sumup_sync_job,
        'interval', minutes=30,
        next_run_time=avvio + timedelta(minutes=3),
        misfire_grace_time=300,
        coalesce=True,
        id="sumup_sync", name="Sincronizzazione SumUp (ogni 30 min)",
        replace_existing=True,
    )
    scheduler.add_job(
        _scan_gmail_verbali_job,
        'interval', minutes=30,
        next_run_time=avvio + timedelta(minutes=6),
        misfire_grace_time=300,
        coalesce=True,
        id="scan_gmail_verbali", name="Scan Gmail Verbali CdS (ogni 30 min)",
        replace_existing=True,
    )
    scheduler.add_job(
        _tesoreria_shadow_job,
        'interval', hours=1,
        next_run_time=avvio + timedelta(minutes=40),
        misfire_grace_time=300,
        coalesce=True,
        id="ai_tesoreria_shadow",
        name="Agente Tesoreria in shadow mode (ogni ora)",
        replace_existing=True,
    )
    scheduler.add_job(
        _cash_flow_shadow_job,
        'interval', hours=6,
        next_run_time=avvio + timedelta(minutes=41),
        misfire_grace_time=300,
        coalesce=True,
        id="ai_cash_flow_13w_shadow",
        name="Cash flow 13 settimane in shadow mode (ogni 6 ore)",
        replace_existing=True,
    )
    scheduler.add_job(
        _contabile_shadow_job,
        'interval', hours=6,
        next_run_time=avvio + timedelta(minutes=42),
        misfire_grace_time=300,
        coalesce=True,
        id="ai_contabile_shadow",
        name="Agente Contabile in shadow mode (ogni 6 ore)",
        replace_existing=True,
    )
    scheduler.add_job(
        _fiscale_shadow_job,
        'interval', hours=6,
        next_run_time=avvio + timedelta(minutes=43),
        misfire_grace_time=300,
        coalesce=True,
        id="ai_fiscale_shadow",
        name="Agente Fiscale in shadow mode (ogni 6 ore)",
        replace_existing=True,
    )
    scheduler.add_job(
        _acquisti_shadow_job,
        'interval', hours=24,
        next_run_time=avvio + timedelta(minutes=44),
        misfire_grace_time=300,
        coalesce=True,
        id="ai_acquisti_shadow",
        name="Agente Acquisti in shadow mode (giornaliero)",
        replace_existing=True,
    )
    scheduler.add_job(
        _crediti_shadow_job,
        'interval', hours=24,
        next_run_time=avvio + timedelta(minutes=45),
        misfire_grace_time=300,
        coalesce=True,
        id="ai_crediti_shadow",
        name="Agente Crediti in shadow mode (giornaliero)",
        replace_existing=True,
    )
    scheduler.add_job(
        _compliance_shadow_job,
        'interval', hours=24,
        next_run_time=avvio + timedelta(minutes=46),
        misfire_grace_time=300,
        coalesce=True,
        id="ai_compliance_shadow",
        name="Agente Compliance in shadow mode (giornaliero)",
        replace_existing=True,
    )
    scheduler.add_job(
        _link_verbali_fatture_job,
        'interval', minutes=60,
        next_run_time=avvio + timedelta(minutes=9),
        misfire_grace_time=300,
        coalesce=True,
        id="link_verbali_fatture", name="Link Verbali ↔ Fatture (ogni 60 min)",
        replace_existing=True,
    )

    scheduler.add_job(
        _drive_cartella_unica_job,
        'interval', minutes=15,
        next_run_time=avvio + timedelta(minutes=2),
        misfire_grace_time=300,
        coalesce=True,
        id="drive_cartella_unica", name="Cartella unica Drive DATI SOCIETA CERALDI (ogni 15 min)",
        replace_existing=True,
    )

    scheduler.add_job(
        _stampe_controllo_job,
        'interval', minutes=15,
        next_run_time=avvio + timedelta(minutes=4),
        misfire_grace_time=300,
        coalesce=True,
        id="cedolini_stampe_controllo", name="Stampe di controllo buste: via da Drive (ogni 15 min)",
        replace_existing=True,
    )

    scheduler.add_job(
        _fonti_ferme_job,
        'interval', hours=1,
        next_run_time=avvio + timedelta(minutes=10),
        misfire_grace_time=300,
        coalesce=True,
        id="fonti_ferme", name="Fonti ferme: corrispettivi, POS, estratti (ogni ora)",
        replace_existing=True,
    )

    scheduler.add_job(
        _controlli_incrociati_job,
        CronTrigger(hour=6, minute=40, timezone="Europe/Rome"),
        misfire_grace_time=3600,
        coalesce=True,
        id="controlli_incrociati",
        name="Controlli incrociati: pagamenti, estratti mancanti, RT dimenticata (ogni giorno)",
        replace_existing=True,
    )

    scheduler.add_job(
        _drive_censimento_doppioni_job,
        'interval', minutes=5,
        next_run_time=avvio + timedelta(minutes=6),
        misfire_grace_time=300,
        coalesce=True,
        id="drive_censimento_doppioni",
        name="Censimento doppioni cartella GESTIONALE, solo rinomina (ogni 5 min)",
        replace_existing=True,
    )

    scheduler.add_job(
        _f24_doppioni_job,
        'interval', hours=6,
        next_run_time=avvio + timedelta(minutes=8),
        misfire_grace_time=600,
        coalesce=True,
        id="f24_doppioni",
        name="Quarantena F24 con lo stesso contenuto (ogni 6 ore)",
        replace_existing=True,
    )


    scheduler.add_job(
        _bonifici_pdf_inbox_job,
        'interval', minutes=10,
        next_run_time=avvio + timedelta(minutes=4),
        misfire_grace_time=300,
        coalesce=True,
        id="bonifici_pdf_inbox",
        name="Elabora PDF bonifico da Import documenti (ogni 10 min)",
        replace_existing=True,
    )

    async def _allinea_status_documenti_job():
        """Riallinea i badge senza attendere il ciclo orario delle email."""
        from app.database import Database
        from app.services.email_monitor_service import allinea_status_documenti_processati

        try:
            aggiornati = await allinea_status_documenti_processati(Database.get_db())
            logger.info(
                "[SCHEDULER-STATUS-DOCUMENTI] documenti riallineati=%s",
                aggiornati,
            )
        except Exception:
            logger.exception("[SCHEDULER-STATUS-DOCUMENTI] riallineamento non completato")

    scheduler.add_job(
        _allinea_status_documenti_job,
        'interval', minutes=15,
        next_run_time=avvio + timedelta(seconds=20),
        misfire_grace_time=300,
        coalesce=True,
        id="allinea_status_documenti",
        name="Riallinea badge documenti processati (ogni 15 minuti)",
        replace_existing=True,
    )

    async def _hr_pagamenti_deposito_job():
        """Bonifici PDF e righe banca del gestionale -> pagamenti HR
        (pagamenti_esiti/paghe_mensili/coda manuale). Riprende solo i
        documenti senza marcatore `hr_deposito`, qualunque sia il punto di
        ingresso (Drive, email, upload, API)."""
        from app.database import Database
        from app.services.hr_pagamenti_deposito import deposita_pagamenti_in_hr

        try:
            result = await deposita_pagamenti_in_hr(Database.get_db())
            letti = result.get("letti") or {}
            if letti.get("bonifici_pdf") or letti.get("estratto_conto"):
                logger.info(
                    "[SCHEDULER-HR-PAGAMENTI] bonifici_pdf=%s estratto_conto=%s",
                    result.get("bonifici_pdf"), result.get("estratto_conto"),
                )
        except Exception:
            logger.exception("[SCHEDULER-HR-PAGAMENTI] deposito non completato")

    async def _cedolini_hr_riverifica_job():
        """Netti HR riletti dal PDF della busta col lettore unico, un lotto per
        giro; si ferma da solo quando tutte le righe portano la versione."""
        from app.database import Database
        from app.services import hr_cedolini_deposito as deposito
        from app.services.cedolini_hr_riverifica import riverifica_lotto

        dsn = deposito.dsn_hr()
        if not dsn:
            return
        con = await deposito.connetti_hr(dsn)
        try:
            r = await riverifica_lotto(con)
        finally:
            await con.close()
        if r["lette"]:
            logger.info("[SCHEDULER-HR-NETTI] lette=%s esiti=%s", r["lette"], r["conteggi"])
            db = Database.get_db()
            stato = await db["sistema_stato"].find_one({"chiave": "cedolini_hr_riverifica"}, {"_id": 0}) or {}
            conteggi = dict(stato.get("conteggi") or {})
            for k, v in r["conteggi"].items():
                conteggi[k] = conteggi.get(k, 0) + v
            await db["sistema_stato"].update_one(
                {"chiave": "cedolini_hr_riverifica"},
                {"$set": {"chiave": "cedolini_hr_riverifica", "conteggi": conteggi,
                          "correzioni": (stato.get("correzioni") or []) + r["correzioni"],
                          "aggiornato_il": datetime.now(timezone.utc).isoformat()}},
                upsert=True,
            )

    async def _cedolini_tipo_dal_pdf_job():
        """13ª/14ª salvate come mensile: tipo riletto dal PDF, un lotto per giro
        (si applica da solo il solo verso mensile -> 13ª/14ª, il resto si annota)."""
        from app.database import Database
        from app.services.cedolini_tipo_dal_pdf import giro

        r = await giro(Database.get_db())
        if r["lette"]:
            logger.info("[SCHEDULER-CEDOLINI-TIPO] lette=%s rimaste=%s esiti=%s simulazione=%s",
                        r["lette"], r["rimaste"], r["conteggi"], r["simulazione"])

    async def _chiusure_attivita_job():
        """Registro dei giorni di chiusura (ferie/ristrutturazione): periodi
        confermati + ferie collettive nelle presenze HR. Toglie quei giorni
        dai "corrispettivi mancanti"."""
        from app.database import Database
        from app.services.chiusure_attivita import aggiorna_registro_chiusure

        try:
            result = await aggiorna_registro_chiusure(Database.get_db())
            if result.get("seminati") or result.get("nuovi"):
                logger.info("[SCHEDULER-CHIUSURE] %s", result)
        except Exception:
            logger.exception("[SCHEDULER-CHIUSURE] aggiornamento non completato")

    async def _riallinea_cessazioni_job():
        """La copia `dipendenti` del gestionale segue l'anagrafica HR per chi e'
        stato cessato automaticamente da una busta (15/09/2026: buste storiche
        avevano cessato Carotenuto, Capezzuto, Guarino, oggi in forza)."""
        from app.database import Database
        from app.services.cessazione_da_cedolino import riallinea_cessazioni_automatiche

        try:
            result = await riallinea_cessazioni_automatiche(Database.get_db())
            if result.get("riattivati") or result.get("date_corrette"):
                logger.info("[SCHEDULER-CESSAZIONI-AUTO] %s", result)
        except Exception:
            logger.exception("[SCHEDULER-CESSAZIONI-AUTO] riallineamento non completato")

    scheduler.add_job(
        _riallinea_cessazioni_job,
        'interval', hours=6,
        next_run_time=avvio + timedelta(minutes=2),
        misfire_grace_time=600,
        coalesce=True,
        id="riallinea_cessazioni_auto",
        name="Riallinea le cessazioni automatiche da cedolino con l'anagrafica HR (ogni 6 ore)",
        replace_existing=True,
    )

    scheduler.add_job(
        _chiusure_attivita_job,
        'interval', hours=6,
        next_run_time=avvio + timedelta(minutes=7),
        misfire_grace_time=600,
        coalesce=True,
        id="chiusure_attivita",
        name="Registro giorni di chiusura attivita' (ogni 6 ore)",
        replace_existing=True,
    )

    scheduler.add_job(
        _cedolini_hr_riverifica_job,
        'interval', minutes=20,
        next_run_time=avvio + timedelta(minutes=7),
        misfire_grace_time=300,
        coalesce=True,
        id="cedolini_hr_riverifica",
        name="Netti HR riletti dal PDF della busta (un lotto ogni 20 minuti)",
        replace_existing=True,
    )

    scheduler.add_job(
        _cedolini_tipo_dal_pdf_job,
        'interval', minutes=20,
        next_run_time=avvio + timedelta(minutes=9),
        misfire_grace_time=300,
        coalesce=True,
        id="cedolini_tipo_dal_pdf",
        name="13a/14a dei cedolini: tipo riletto dal PDF (un lotto ogni 20 minuti)",
        replace_existing=True,
    )

    scheduler.add_job(
        _hr_pagamenti_deposito_job,
        'interval', minutes=15,
        next_run_time=avvio + timedelta(minutes=6),
        misfire_grace_time=300,
        coalesce=True,
        id="hr_pagamenti_deposito",
        name="Deposita bonifici ed estratti conto nei pagamenti HR (ogni 15 minuti)",
        replace_existing=True,
    )

    async def _mittenti_email_job():
        from app.database import Database
        from app.services.email_monitor_service import (
            allinea_status_documenti_processati,
            sync_email_documents,
        )
        try:
            db = Database.get_db()
            result = await sync_email_documents(db, giorni=1)
            result["status_documenti_allineati"] = await allinea_status_documenti_processati(db)
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
        next_run_time=avvio + timedelta(minutes=27),
        misfire_grace_time=300,
        coalesce=True,
        id="mittenti_email_sync",
        name="Documenti da mittenti email attendibili: fatture estere XML + altri tipi (ogni ora)",
        replace_existing=True,
    )

    # Canali Drive documentali generici: bonifici dipendenti, verbali e canali
    # fiscali esplicitamente abilitati. Il resolver di ciascun canale limita la
    # scansione alla propria DA ELABORARE canonica.


    async def _tax_code_registry_job():
        from app.database import Database
        from app.services.tax_code_registry import sync_tax_code_registry
        try:
            result = await sync_tax_code_registry(Database.get_db())
            logger.info(f"[SCHEDULER-CODICI-TRIBUTO] {result}")
        except Exception as e:
            logger.error(f"[SCHEDULER-CODICI-TRIBUTO] errore: {e}")

    scheduler.add_job(
        _tax_code_registry_job,
        CronTrigger(day_of_week="sun", hour=4, minute=10),
        id="tax_code_registry_sync",
        name="Aggiornamento registro ufficiale codici tributo (settimanale)",
        replace_existing=True,
    )


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

    async def _cedolini_bloccati_job():
        from app.database import Database
        from app.services.cedolini_bloccati import verifica_documenti_bloccati
        db = Database.get_db()
        try:
            bloccati = await verifica_documenti_bloccati(db)
            if bloccati["totale_bloccati"] > 0:
                logger.warning(f"[SCHEDULER-CEDOLINI-BLOCCATI] {bloccati['totale_bloccati']} documenti cedolini mai processati oltre {bloccati['soglia_ore']}h")
                from app.services.alert_engine import genera_alert
                await genera_alert(
                    "CEDOLINO_MAI_PROCESSATO", "quadratura_cedolini_bloccati", "documents_inbox",
                    f"{bloccati['totale_bloccati']} cedolini arrivati (Drive/email) ma mai diventati un "
                    f"cedolino vero in contabilità da oltre {bloccati['soglia_ore']} ore: verifica manualmente.",
                    db, extra={"bloccati": bloccati["bloccati"][:20]},
                )
        except Exception as e:
            logger.error(f"[SCHEDULER-CEDOLINI-BLOCCATI] errore: {type(e).__name__}: {e}")

    scheduler.add_job(
        _cedolini_bloccati_job,
        CronTrigger(day_of_week="sun", hour=5, minute=15),
        id="cedolini_bloccati",
        name="Cedolini arrivati ma mai elaborati (domenica ore 5:15)",
        replace_existing=True,
    )


    scheduler.add_job(
        _dedup_fatture_job,
        'interval', minutes=30,
        next_run_time=avvio + timedelta(minutes=4),
        misfire_grace_time=300,
        coalesce=True,
        id="dedup_fatture",
        name="Dedup fatture: identita' dall'XML, doppioni per hash, storni (ogni 30 min)",
        replace_existing=True,
    )
    scheduler.add_job(
        _quietanze_orfane_job,
        'interval', minutes=30,
        next_run_time=avvio + timedelta(minutes=3),
        misfire_grace_time=300,
        coalesce=True,
        id="quietanze_orfane",
        name="Quietanze F24 senza modello: ricollega al loro F24 (ogni 30 min)",
        replace_existing=True,
    )
    scheduler.add_job(
        _pagamenti_dichiarati_job,
        'interval', minutes=30,
        next_run_time=avvio + timedelta(minutes=5),
        misfire_grace_time=300,
        coalesce=True,
        id="pagamenti_dichiarati",
        name="Report del titolare: pagamenti dichiarati ancora aperti (ogni 30 min)",
        replace_existing=True,
    )
    scheduler.add_job(
        _banca_versamenti_proiezione_job,
        'interval', minutes=30,
        next_run_time=avvio + timedelta(minutes=2),
        misfire_grace_time=300,
        coalesce=True,
        id="banca_versamenti_proiezione",
        name="Banca: assegni, versamenti contanti e proiezione in Prima Nota (ogni 30 min)",
        replace_existing=True,
    )
    scheduler.add_job(
        _f24_quietanze_banca_job,
        'interval', minutes=30,
        next_run_time=avvio + timedelta(minutes=4),
        misfire_grace_time=300,
        coalesce=True,
        id="f24_quietanze_banca",
        name="F24: ravvedimenti, quietanze con gli addebiti in banca, rate delle dilazioni INPS (ogni 30 min)",
        replace_existing=True,
    )
    scheduler.add_job(
        _fatture_emesse_job,
        'interval', minutes=30,
        next_run_time=avvio + timedelta(minutes=3),
        misfire_grace_time=300,
        coalesce=True,
        id="fatture_emesse",
        name="Fatture emesse: fuori dalle passive, aggancio al corrispettivo (ogni 30 min)",
        replace_existing=True,
    )
    scheduler.add_job(
        _fatture_estere_job,
        'interval', minutes=30,
        next_run_time=avvio + timedelta(minutes=5),
        misfire_grace_time=300,
        coalesce=True,
        id="fatture_estere_riallineamento",
        name="Fatture estere da confermare: classificazione e registrazione alle regole attuali (ogni 30 min)",
        replace_existing=True,
    )
    scheduler.add_job(
        _automazioni_prima_nota_job,
        'interval', minutes=30,
        next_run_time=avvio + timedelta(minutes=13),
        misfire_grace_time=300,
        coalesce=True,
        id="automazioni_prima_nota",
        name="Automazioni Prima Nota: corrispettivi + provvisori + riconciliazione (ogni 30 min)",
        replace_existing=True,
    )

    from zoneinfo import ZoneInfo
    from app.config import settings as scheduler_settings
    scheduler.add_job(
        scan_verbali_email_task,
        CronTrigger(
            hour=max(0, min(23, int(scheduler_settings.VERBALI_EMAIL_SCAN_HOUR))),
            minute=0,
            timezone=ZoneInfo("Europe/Rome"),
        ),
        id="verbali_email_scan",
        name="Scan Email Verbali (giornaliero Europe/Rome)",
        replace_existing=True
    )
    scheduler.add_job(
        verbali_notifications_task,
        CronTrigger(hour=7, minute=10, timezone=ZoneInfo("Europe/Rome")),
        id="verbali_notifications",
        name="Promemoria verbali (giornaliero Europe/Rome)",
        replace_existing=True,
    )

    scheduler.add_job(
        check_scadenze_partite_task,
        CronTrigger(hour=7, minute=0),
        id="scadenze_partite_check",
        name="Controllo Scadenze Partite Aperte (ogni giorno ore 7:00)",
        replace_existing=True
    )

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

    async def enable_banking_giro_task():
        """Banco BPM: importa da solo i movimenti certamente nuovi."""
        try:
            import httpx
            from app.database import Database
            from app.services import enable_banking as eb
            if not eb.attivo():
                return
            async with httpx.AsyncClient(timeout=90.0, follow_redirects=False) as client:
                esito = await eb.giro_automatico(Database.get_db(), client)
            logger.info(f"[SCHEDULER-BANCA] giro Enable Banking: {esito}")
        except Exception as e:
            logger.error(f"[SCHEDULER-BANCA] giro Enable Banking non riuscito: {type(e).__name__}: {e}")

    scheduler.add_job(
        enable_banking_giro_task,
        OrTrigger([
            CronTrigger(hour=7, minute=15, timezone=ZoneInfo("Europe/Rome")),
            CronTrigger(hour=9, minute=0, timezone=ZoneInfo("Europe/Rome")),
        ]),
        id="enable_banking_giro",
        name="Banco BPM: movimenti nuovi dalla banca (07:15 e 09:00 Europe/Rome)",
        replace_existing=True,
    )

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

    scheduler.add_job(
        check_scadenze_f24_task,
        CronTrigger(hour=8, minute=0),
        id="f24_scadenze_check",
        name="Controllo Scadenze F24 (ogni giorno ore 8:00)",
        replace_existing=True
    )

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

    scheduler.add_job(
        check_scadenze_f24_task,
        CronTrigger(hour=14, minute=0),
        id="f24_scadenze_check_pm",
        name="Reminder Scadenze F24 (ogni giorno ore 14:00)",
        replace_existing=True
    )

    scheduler.add_job(
        check_fornitori_duplicati_task,
        CronTrigger(hour=6, minute=0),
        id="fornitori_duplicati_check",
        name="Controllo Fornitori Duplicati (ogni giorno ore 6:00)",
        replace_existing=True
    )

    scheduler.add_job(
        gmail_full_scan_task,
        'interval',
        hours=1,
        next_run_time=avvio + timedelta(minutes=7),
        misfire_grace_time=300,
        coalesce=True,
        id="gmail_full_scan",
        name="Gmail Full Scan Multi-Cartella (ogni ora)",
        replace_existing=True
    )

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
    """Ferma lo scheduler senza bloccare il loop.

    `shutdown()` di default aspetta i job in corso, ma i job qui sono
    coroutine sullo stesso event loop: aspettarli da dentro il loop lo
    blocca, lo spegnimento non arriva mai in fondo e il processo viene
    ucciso con i lease ancora in mano. Si chiude subito, e i lease li
    restituisce esplicitamente lo shutdown dell'applicazione.
    """
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("🛑 [SCHEDULER] Scheduler fermato")
