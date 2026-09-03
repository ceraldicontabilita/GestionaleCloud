import logging

"""
scheduler.py — Task automatici periodici per HACCP Ceraldi.

Job registrati:
  01:00  aggiorna_riferimenti_fatture  — riscrive numeri fattura >30gg nei lotti
  01:30  pulisci_lotti_scaduti         — elimina lotti scaduti >30gg non in ricetta
  ogni:15 sync_gestionale_fatture     — riceve fatture da GestionaleCloud
  07:00  genera_haccp_giornaliero      — pre-compila temperature + sanificazione
  02:30  backup_notturno               — backup DB con rotazione 7 giorni
  04:00  pipeline_aggiornamento        — aggiorna prezzi, food cost, manuale HACCP
"""

import re
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from typing import List, Optional

from app.lotti.db import database as db
from app.lotti.auth import require_admin, require_automation_or_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])

scheduler = AsyncIOScheduler(timezone="Europe/Rome")
scheduler_started = False


class SchedulerJob(BaseModel):
    id: str
    name: str
    next_run: Optional[str]
    trigger: str
    enabled: bool


class SchedulerStatus(BaseModel):
    running: bool
    jobs: List[SchedulerJob]
    last_haccp_update: Optional[str]


# ── JOB 01:00 — Aggiornamento riferimenti fatture nei lotti ──────────────────


async def job_aggiorna_riferimenti_fatture():
    """
    Ogni notte alle 01:00 (Roma).
    Aggiorna i riferimenti fattura negli ingredienti_dettaglio dei lotti
    quando la fattura originale ha più di 30 giorni.
    """
    print(f"[Scheduler] {datetime.now()} - Aggiornamento riferimenti fatture nei lotti...")
    aggiornati = 0
    ora = datetime.now(timezone.utc)
    soglia = ora - timedelta(days=30)

    PATTERN_FATT = re.compile(r"n° fatt\s+([\w/\-]+)\s+-\s+(\d{4}-\d{2}-\d{2})")
    PATTERN_FORN = re.compile(r"-\s+(.+?)\s+n° fatt")

    lotti = await db.lotti.find({}, {"_id": 1, "ingredienti_dettaglio": 1}).to_list(5000)

    for lotto in lotti:
        ingredienti = lotto.get("ingredienti_dettaglio", [])
        nuovi = []
        modificato = False

        for riga in ingredienti:
            m_fatt = PATTERN_FATT.search(riga)
            m_forn = PATTERN_FORN.search(riga)
            if not m_fatt or not m_forn:
                nuovi.append(riga)
                continue

            try:
                data_fatt = datetime.fromisoformat(m_fatt.group(2)).replace(tzinfo=timezone.utc)
            except Exception:
                nuovi.append(riga)
                continue

            if data_fatt >= soglia:
                nuovi.append(riga)
                continue

            num_old = m_fatt.group(1)
            fornitore_raw = m_forn.group(1).strip()
            nome_ing = riga.split("contiene")[0].split("non contiene")[0].strip()

            # il campo si chiama data_fattura (non "data": la query storica non
            # trovava MAI nulla) ed è in formato misto dd/mm|ISO → filtro e
            # ordinamento su date vere in Python.
            from app.lotti.routers.utils import parse_data_flessibile
            _data_min = parse_data_flessibile(m_fatt.group(2))
            _candidate = await db.fatture.find(
                {"fornitore": {"$regex": re.escape(fornitore_raw[:15]), "$options": "i"}},
                {"_id": 0, "numero_fattura": 1, "data_fattura": 1, "prodotti": 1},
            ).to_list(500)
            _con_data = [
                (parse_data_flessibile(f.get("data_fattura")), f) for f in _candidate
            ]
            fatture_recenti = [
                f for d, f in sorted(
                    (x for x in _con_data if x[0] and _data_min and x[0] >= _data_min),
                    key=lambda x: x[0], reverse=True,
                )
            ][:5]

            fattura_nuova = None
            for f in fatture_recenti:
                for p in f.get("prodotti", []):
                    if nome_ing[:15].upper() in (p.get("descrizione") or "").upper():
                        fattura_nuova = f
                        break
                if fattura_nuova:
                    break

            if fattura_nuova:
                riga_nuova = PATTERN_FATT.sub(
                    f"n° fatt {fattura_nuova['numero_fattura']} - {fattura_nuova.get('data_fattura', '')}", riga
                )
                nuovi.append(riga_nuova)
                modificato = True
            else:
                nuovi.append(riga)

        if modificato:
            await db.lotti.update_one(
                {"_id": lotto["_id"]}, {"$set": {"ingredienti_dettaglio": nuovi}}
            )
            aggiornati += 1

    await db.scheduler_logs.insert_one(
        {
            "job": "aggiorna_riferimenti_fatture",
            "timestamp": ora.isoformat(),
            "success": True,
            "lotti_aggiornati": aggiornati,
        }
    )
    print(f"[Scheduler] Riferimenti fatture aggiornati in {aggiornati} lotti")


# ── JOB 01:30 — Pulizia lotti scaduti ────────────────────────────────────────


async def job_pulisci_lotti_scaduti():
    """
    Ogni notte alle 01:30 (Roma).
    ARCHIVIA (non elimina più) i lotti scaduti da oltre 30 giorni il cui
    prodotto non è più usato in nessuna ricetta attiva.

    CAMBIO 25/07/2026 (audit import/database §2.2): prima faceva
    `delete_one` — cancellazione FISICA. I `movimenti_lotto` e le
    `vendite_banco` che citavano quel lotto restavano orfani e, soprattutto,
    il lotto spariva dai registri stampati, mentre il registro ASL dichiara
    "conservare 5 anni". Un'ispezione che chiede il registro di due mesi prima
    non lo avrebbe più trovato.
    Ora il lotto resta a DB con `archiviato=True` (+ data e motivo): esce dagli
    elenchi operativi come prima (il filtro canonico guarda stato/esaurito e
    questi lotti sono comunque scaduti da un mese), ma le stampe e la
    tracciabilità continuano a vederlo.
    """
    print(f"[Scheduler] {datetime.now()} - Pulizia lotti scaduti...")
    ora = datetime.now(timezone.utc)
    soglia_iso = (ora - timedelta(days=30)).strftime("%Y-%m-%d")

    ricette = await db.ricette.find({}, {"_id": 0, "ingredienti": 1, "nome": 1}).to_list(5000)
    nomi_in_ricette = set()
    for r in ricette:
        nomi_in_ricette.add((r.get("nome") or "").lower())
        for ing in r.get("ingredienti") or []:
            nome_ing = (ing if isinstance(ing, str) else ing.get("nome", "")).lower()
            nomi_in_ricette.add(nome_ing)

    tutti_lotti = await db.lotti.find(
        {"archiviato": {"$ne": True}},
        {"_id": 1, "prodotto": 1, "data_scadenza": 1},
    ).to_list(5000)

    eliminati = 0
    for lotto in tutti_lotti:
        ds = lotto.get("data_scadenza", "")
        try:
            if re.match(r"\d{2}/\d{2}/\d{4}", ds):
                parts = ds.split("/")
                ds_iso = f"{parts[2]}-{parts[1]}-{parts[0]}"
            else:
                ds_iso = ds[:10]

            if ds_iso >= soglia_iso:
                continue

            prodotto = (lotto.get("prodotto") or "").lower()
            in_ricetta = any(
                prodotto in nome or nome in prodotto for nome in nomi_in_ricette if nome
            )

            if not in_ricetta:
                # ARCHIVIAZIONE LOGICA, mai cancellazione: i registri devono
                # restare consultabili 5 anni (Reg. CE 178/2002).
                await db.lotti.update_one(
                    {"_id": lotto["_id"]},
                    {"$set": {
                        "archiviato": True,
                        "archiviato_il": ora.isoformat(),
                        "archiviato_motivo": "scaduto da oltre 30 giorni, prodotto non più in ricetta",
                    }},
                )
                eliminati += 1

        except Exception as e:
            logger.warning(f"[scheduler] Errore pulizia lotto: {e}")
            continue

    await db.scheduler_logs.insert_one(
        {
            "job": "pulizia_lotti_scaduti",
            "timestamp": ora.isoformat(),
            "success": True,
            # nome storico della chiave mantenuto per non rompere i grafici
            # esistenti; da oggi conta gli ARCHIVIATI, non i cancellati
            "lotti_eliminati": eliminati,
            "lotti_archiviati": eliminati,
        }
    )
    print(f"[Scheduler] Lotti scaduti archiviati: {eliminati}")


# ── JOB 07:00 — Generazione HACCP giornaliero ────────────────────────────────


async def job_genera_haccp_giornaliero():
    """
    Ogni mattino alle 07:00 (Roma) — prima che gli operatori arrivino.

    Usa verifica_oggi() che:
    1. Controlla se temperature e sanificazione sono già presenti
    2. Genera SOLO quello che manca (non sovrascrive dati manuali)
    3. Per la sanificazione usa correttamente db.sanificazione_schede
       con lo schema {registrazioni: {attrezzatura: {giorno: 'X'}}}

    Se la scheda sanificazione del mese non esiste ancora (operatori non l'hanno
    creata tramite l'interfaccia) non la crea automaticamente per non interferire
    con il workflow manuale.
    """
    from app.lotti.servizi.automatismi_mattutini import run_morning_automation

    return await run_morning_automation(source="internal_scheduler")

    from app.lotti.routers.haccp_auto import verifica_e_popola_oggi, marca_giorni_non_rilevati

    print(f"[Scheduler] {datetime.now()} - Generazione HACCP giornaliero...")
    oggi = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    try:
        result = await verifica_e_popola_oggi()

        # RECUPERO DEI BUCHI (AUDIT_SCHEDULER_TEMPERATURE §2.3): se il server è
        # rimasto giù per uno o più giorni, quei giorni restavano vuoti a
        # database senza dire perché. Ora vengono DICHIARATI "non rilevato" col
        # motivo — nessuna temperatura inventata, nessun dato esistente
        # riscritto. Gira anche al riavvio, perché il catchup richiama questo
        # stesso job.
        non_rilevati = await marca_giorni_non_rilevati()

        await db.scheduler_logs.insert_one(
            {
                "job": "haccp_daily",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "success": True,
                "date": oggi,
                "generato": result.get("generato", False),
                "elementi": result.get("elementi", []),
                "message": result.get("message", ""),
                "giorni_non_rilevati": non_rilevati,
            }
        )
        print(f"[Scheduler] HACCP {oggi}: {result.get('message', 'ok')}")

    except Exception as e:
        await db.scheduler_logs.insert_one(
            {
                "job": "haccp_daily",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "success": False,
                "date": oggi,
                "error": str(e),
            }
        )
        print(f"[Scheduler] Errore HACCP: {e}")

    # ── Riordino automatico sotto-scorta: crea bozze per fornitore ──────────
    #    FUORI dal try HACCP: un errore nella generazione registri non deve
    #    saltare il riordino del giorno (funzioni di business indipendenti).
    try:
        from app.lotti.routers.ordini_fornitori import esegui_riordino_automatico
        r = await esegui_riordino_automatico()
        logger.info(f"[scheduler] riordino auto: {len(r.get('bozze_create', []))} bozze")
    except Exception as e:
        logger.warning(f"[scheduler] riordino auto fallito: {e}")

    # ── Task dipendenti: genera checklist giornaliera ────────────────────────
    try:
        from app.lotti.routers.task_dipendenti import genera_task_giornalieri

        await genera_task_giornalieri()
    except Exception as _te:
        print(f"[Scheduler] Generazione task fallita: {_te}")


# ── JOB 02:30 — Backup notturno ──────────────────────────────────────────────


async def job_backup_notturno():
    """Ogni notte alle 02:30 (Roma). Backup DB con rotazione 7 giorni."""
    print(f"[Scheduler] {datetime.now()} - Backup notturno...")
    try:
        from app.lotti.routers.backup import esegui_backup_async

        result = await esegui_backup_async()
        await db.scheduler_logs.insert_one(
            {
                "job": "backup_notturno",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "success": True,
                "file": result.get("file"),
                "dimensione": result.get("dimensione"),
                "eliminati": result.get("eliminati", []),
            }
        )
        print(f"[Scheduler] Backup: {result.get('file')} ({result.get('dimensione')})")
    except Exception as e:
        await db.scheduler_logs.insert_one(
            {
                "job": "backup_notturno",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "success": False,
                "error": str(e),
            }
        )
        print(f"[Scheduler] Errore backup: {e}")


# ── JOB 04:00 — Pipeline aggiornamento ───────────────────────────────────────


async def job_pipeline_aggiornamento():
    """Ogni notte alle 04:00 (Roma). Aggiorna prezzi, food cost e manuale HACCP."""
    print(f"[Scheduler] {datetime.now()} - Pipeline aggiornamento...")
    try:
        from app.lotti.routers.pipeline import esegui_pipeline_post_import

        result = await esegui_pipeline_post_import(motivo="scheduler_notte")
        await db.scheduler_logs.insert_one(
            {
                "job": "pipeline_aggiornamento",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "success": result.get("esito") == "OK",
                "durata_s": result.get("durata_s"),
            }
        )
        print(f"[Scheduler] Pipeline completata ({result.get('durata_s', '?')}s)")
    except Exception as e:
        await db.scheduler_logs.insert_one(
            {
                "job": "pipeline_aggiornamento",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "success": False,
                "error": str(e),
            }
        )
        print(f"[Scheduler] Errore pipeline: {e}")


async def job_normalizza_nuovi_prodotti():
    """Ogni notte alle 03:00 (Roma). Classifica i prodotti nuovi arrivati dalle fatture
    (keyword statiche + AI Cloud) e li aggiunge al dizionario nome_mapping."""
    print(f"[Scheduler] {datetime.now()} - Normalizzazione nuovi prodotti...")
    try:
        from app.lotti.routers.normalizzazione import processa_nuovi_prodotti

        totale = 0
        # processa a blocchi finché ci sono nuovi (max 5 giri = ~250 prodotti/notte)
        for _ in range(5):
            res = await processa_nuovi_prodotti(limit=50)
            n = res.get("processati", 0) if isinstance(res, dict) else 0
            totale += n
            if n == 0:
                break
        await db.scheduler_logs.insert_one(
            {
                "job": "normalizza_nuovi_prodotti",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "success": True,
                "processati": totale,
            }
        )
        print(f"[Scheduler] Normalizzazione completata — {totale} prodotti classificati")
    except Exception as e:
        await db.scheduler_logs.insert_one(
            {
                "job": "normalizza_nuovi_prodotti",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "success": False,
                "error": str(e),
            }
        )
        print(f"[Scheduler] Errore normalizzazione: {e}")


async def job_ricerca_web_prodotti():
    """Ogni 20 min (06:00-22:59 Roma). Identifica via ricerca web le righe fattura
    senza nome canonico: 3 per giro, più frequenti prima. Risultato PERMANENTE
    (nome_mapping + scheda tecnica con link): ogni prodotto si identifica una
    volta sola, le righe nuove degli import XML entrano in coda da sole.
    Richiesta Enzo 02/07/2026."""
    import os as _os
    if not _os.environ.get("ANTHROPIC_API_KEY"):
        return  # ricerca web non configurata: nessun rumore nei log
    try:
        from app.lotti.routers.schede_tecniche import esegui_ricerca_web_batch
        res = await esegui_ricerca_web_batch(limit=3)
        if res.get("processati"):
            # dopo nuovi mapping, ricollega gli ingredienti ricetta rimasti orfani
            if res.get("salvati"):
                try:
                    from app.lotti.routers.ricette import collega_ingredienti_canonico
                    await collega_ingredienti_canonico()
                except Exception:
                    logger.debug("[scheduler] collega-ingredienti non bloccante ignorato")
            await db.scheduler_logs.insert_one(
                {
                    "job": "ricerca_web_prodotti",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "success": True,
                    "processati": res.get("processati"),
                    "salvati": res.get("salvati"),
                    "in_coda": res.get("in_coda"),
                }
            )
            print(f"[Scheduler] Ricerca web: {res.get('salvati')}/{res.get('processati')} salvati, {res.get('in_coda')} in coda")
    except Exception as e:
        await db.scheduler_logs.insert_one(
            {
                "job": "ricerca_web_prodotti",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "success": False,
                "error": str(e),
            }
        )
        print(f"[Scheduler] Errore ricerca web: {e}")


async def job_automatismi_haccp():
    """Ogni 5 giorni (Roma). Genera le registrazioni HACCP obbligatorie SEMPRE CONFORMI
    (controllo olio, temperature cottura) e, occasionalmente, un reclamo fornitore realistico.
    Le non conformità restano una scelta manuale dell'operatore."""
    print(f"[Scheduler] {datetime.now()} - Automatismi HACCP...")
    try:
        from app.lotti.routers.automatismi_haccp import (
            genera_controllo_olio_automatico,
            genera_temperature_cottura_automatico,
            genera_reclamo_fornitore_automatico,
        )

        n_olio = await genera_controllo_olio_automatico()
        n_temp = await genera_temperature_cottura_automatico()
        n_recl = await genera_reclamo_fornitore_automatico()

        await db.scheduler_logs.insert_one({
            "job": "automatismi_haccp",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": True,
            "controllo_olio": n_olio,
            "temperature_cottura": n_temp,
            "reclami_fornitori": n_recl,
        })
        print(f"[Scheduler] Automatismi HACCP — olio:{n_olio} temp:{n_temp} reclami:{n_recl}")
    except Exception as e:
        await db.scheduler_logs.insert_one({
            "job": "automatismi_haccp",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": False,
            "error": str(e),
        })
        print(f"[Scheduler] Errore automatismi HACCP: {e}")


# job_check_scorta_minima RIMOSSO (02/07/2026): faceva da doppione del riordino
# automatico su un'altra collezione (dizionario_prodotti.scorta_minima) creando
# una bozza cumulativa parallela senza dedup incrociata. Ora le materie prime
# sotto scorta sono coperte dal MOTORE UNICO esegui_riordino_automatico
# (ordini_fornitori.py), che gira alle 07:00 dentro job_genera_haccp_giornaliero.


async def job_sync_gestionale_fatture():
    """Riceve le fatture correnti da GestionaleCloud con registro idempotente."""
    try:
        from app.lotti.routers.gestionale_fatture import configurato, esegui_sync_gestionale
        if not configurato():
            return
        res = await esegui_sync_gestionale(
            anno=datetime.now().year, massimo=1000, anteprima=False
        )
        await db.scheduler_logs.insert_one({
            "job": "sync_gestionale_fatture",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": bool(res.get("ok")),
            "importate": res.get("importate", 0),
            "gia_ricevute": res.get("gia_ricevute", 0),
            "collegate_esistenti": res.get("collegate_esistenti", 0),
            "errori": (res.get("errori") or [])[:10],
            "conflitti": (res.get("conflitti") or [])[:10],
        })
    except Exception as e:
        logger.warning(f"[scheduler] gestionale-fatture fallito: {e}")
        await db.scheduler_logs.insert_one({
            "job": "sync_gestionale_fatture",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": False,
            "error": str(e)[:250],
        })


async def job_keep_warm():
    """Self-ping sull'URL pubblico in orario di lavoro (04:00-22:59 Roma).
    Il traffico HTTP esterno impedisce a Render free di addormentare il servizio
    (cold start ~50s percepito dai tablet come 'app rotta'). Fuori orario il job
    non gira: il servizio dorme e non consuma ore istanza del piano free.
    La finestra copre TUTTA la fascia del job ricerca_web_prodotti (06-22:40):
    prima finiva alle 20:59 e l'ultima ora e mezza di ricerche rischiava di
    saltare per lo sleep di Render. ~19h/giorno ≈ 590h/mese, dentro le 750h free.
    L'URL arriva da RENDER_EXTERNAL_URL (settato automaticamente da Render)."""
    import os
    url = (os.environ.get("RENDER_EXTERNAL_URL") or "").rstrip("/")
    if not url:
        return
    try:
        import httpx
        async with httpx.AsyncClient(timeout=20) as client:
            await client.get(f"{url}/api/health")
    except Exception as e:
        logger.warning(f"[KeepWarm] ping fallito: {e}")


def setup_scheduler():
    global scheduler_started
    if scheduler_started:
        return

    TZ = "Europe/Rome"

    scheduler.add_job(
        job_keep_warm,
        CronTrigger(minute="*/10", hour="4-22", timezone=TZ),
        id="keep_warm",
        name="Keep-warm Render (self-ping ogni 10 min, 04:00-22:59)",
        replace_existing=True,
    )
    scheduler.add_job(
        job_aggiorna_riferimenti_fatture,
        CronTrigger(hour=1, minute=0, timezone=TZ),
        id="aggiorna_riferimenti_fatture",
        name="Aggiornamento Riferimenti Fatture nei Lotti (>30gg)",
        replace_existing=True,
    )
    scheduler.add_job(
        job_pulisci_lotti_scaduti,
        CronTrigger(hour=1, minute=30, timezone=TZ),
        id="pulizia_lotti_scaduti",
        name="Pulizia Lotti Scaduti (>30gg non in ricetta)",
        replace_existing=True,
    )
    scheduler.add_job(
        job_genera_haccp_giornaliero,
        CronTrigger(hour=7, minute=0, timezone=TZ),
        id="haccp_daily_generation",
        name="Generazione HACCP Giornaliera (07:00)",
        replace_existing=True,
    )
    scheduler.add_job(
        job_digest_mattutino,
        CronTrigger(hour=7, minute=30, timezone=TZ),
        id="digest_mattutino",
        name="Promemoria mattutino WhatsApp (07:30) — lotti in scadenza/scaduti",
        replace_existing=True,
    )
    scheduler.add_job(
        job_backup_notturno,
        CronTrigger(hour=2, minute=30, timezone=TZ),
        id="backup_notturno",
        name="Backup DB Notturno (rotazione 7 giorni)",
        replace_existing=True,
    )
    scheduler.add_job(
        job_pipeline_aggiornamento,
        CronTrigger(hour=4, minute=0, timezone=TZ),
        id="pipeline_aggiornamento",
        name="Pipeline Aggiornamento Prezzi e Food Cost",
        replace_existing=True,
    )

    scheduler.add_job(
        job_normalizza_nuovi_prodotti,
        CronTrigger(hour=3, minute=0, timezone=TZ),
        id="normalizza_nuovi_prodotti",
        name="Normalizzazione Nuovi Prodotti da Fatture (03:00)",
        replace_existing=True,
    )

    # HACCP obbligatorio: ogni 5 giorni (giorni 1,6,11,16,21,26,31) alle 07:30
    scheduler.add_job(
        job_automatismi_haccp,
        CronTrigger(day="1,6,11,16,21,26,31", hour=7, minute=30, timezone=TZ),
        id="automatismi_haccp",
        name="Automatismi HACCP olio/temperature/reclami (ogni 5gg, 07:30)",
        replace_existing=True,
    )

    # Ricerca web prodotti: identifica le righe fattura senza canonico, 3 per
    # giro (~200/giorno). Permanente: una riga identificata non si ricerca più.
    scheduler.add_job(
        job_ricerca_web_prodotti,
        CronTrigger(minute="*/20", hour="6-22", timezone=TZ),
        id="ricerca_web_prodotti",
        name="Ricerca web prodotti da fatture (ogni 20 min, 06-22)",
        replace_existing=True,
    )

    scheduler.add_job(
        job_sync_gestionale_fatture,
        CronTrigger(minute="5,20,35,50", hour="5-22", timezone=TZ),
        id="sync_gestionale_fatture",
        name="Ricezione fatture da GestionaleCloud (ogni 15 min, 05-22)",
        replace_existing=True,
    )

    scheduler.start()
    scheduler_started = True
    print(
        "[Scheduler] Avviato — 01:00 ref-fatture | 01:30 pulizia-lotti | "
        "ogni:15 GestionaleCloud-fatture | 02:30 backup | 03:00 normalizza | 04:00 pipeline | 07:00 HACCP+riordino"
    )

    # ── CATCHUP ALL'AVVIO ────────────────────────────────────────────────────
    # Se il backend riparte (deploy/hot-reload) dopo l'orario pianificato di un
    # job critico e oggi non è ancora stato eseguito, lo esegue subito.
    # APScheduler è in-memory: se il server si spegne prima del trigger,
    # il job viene saltato. Questo catchup evita buchi nei dati HACCP.
    asyncio.create_task(_catchup_jobs_mancanti())


async def _catchup_jobs_mancanti():
    """All'avvio, controlla se i job fissi di oggi sono stati eseguiti.
    Se l'ora attuale supera l'orario pianificato e non c'è log di oggi,
    esegue subito il job (una sola volta per giornata).
    """
    try:
        # Aspetta qualche secondo che il backend sia pronto
        await asyncio.sleep(10)
        from zoneinfo import ZoneInfo

        tz = ZoneInfo("Europe/Rome")
        ora_it = datetime.now(tz)
        oggi_ymd = ora_it.strftime("%Y-%m-%d")
        oggi_start = (
            datetime(ora_it.year, ora_it.month, ora_it.day, tzinfo=tz)
            .astimezone(timezone.utc)
            .isoformat()
        )

        # Mappa job → (ora_trigger, funzione)
        jobs_da_verificare = [
            ("haccp_daily", 7, 0, job_genera_haccp_giornaliero),
            ("pipeline_aggiornamento", 4, 0, job_pipeline_aggiornamento),
        ]

        for job_name, ora, minuto, fn in jobs_da_verificare:
            # Trigger orario in Europe/Rome già passato?
            trigger_dt = datetime(ora_it.year, ora_it.month, ora_it.day, ora, minuto, tzinfo=tz)
            if ora_it < trigger_dt:
                continue  # trigger non ancora scattato oggi → regular schedule farà il lavoro
            # C'è già log success=True di oggi?
            log_oggi = await db.scheduler_logs.find_one(
                {
                    "job": job_name,
                    "success": True,
                    "timestamp": {"$gte": oggi_start},
                }
            )
            if log_oggi:
                continue  # già eseguito oggi
            print(
                f"[Scheduler CATCHUP] Job '{job_name}' non eseguito oggi (trigger {ora:02d}:{minuto:02d}) → eseguo subito"
            )
            try:
                await fn()
            except Exception as e:
                print(f"[Scheduler CATCHUP] Errore eseguendo '{job_name}': {e}")

        # Automatismi HACCP (ogni 5 giorni): se l'ultima esecuzione è >5 giorni fa
        # (o non c'è mai stata), eseguili subito per non lasciare buchi nel registro.
        try:
            ultimo_haccp = await db.scheduler_logs.find_one(
                {"job": "automatismi_haccp", "success": True}, sort=[("timestamp", -1)]
            )
            esegui = True
            if ultimo_haccp and ultimo_haccp.get("timestamp"):
                from datetime import datetime as _dt
                ts = _dt.fromisoformat(ultimo_haccp["timestamp"].replace("Z", "+00:00"))
                giorni = (datetime.now(timezone.utc) - ts).days
                esegui = giorni >= 5
            if esegui:
                print("[Scheduler CATCHUP] Automatismi HACCP non eseguiti da >5gg → eseguo subito")
                await job_automatismi_haccp()
        except Exception as e:
            print(f"[Scheduler CATCHUP] Errore automatismi HACCP: {e}")
    except Exception as e:
        print(f"[Scheduler CATCHUP] Errore generale: {e}")


# ── Endpoint REST ─────────────────────────────────────────────────────────────


@router.post("/esegui-automatismi-haccp")
async def esegui_automatismi_haccp_ora():
    """Lancia subito gli automatismi HACCP (olio, temperature, reclami).
    Utile per popolare il registro al primo avvio senza attendere il giorno pianificato,
    o per forzare un controllo. Idempotente: non duplica le registrazioni di oggi."""
    await job_automatismi_haccp()
    ultimo = await db.scheduler_logs.find_one(
        {"job": "automatismi_haccp"}, {"_id": 0}, sort=[("timestamp", -1)]
    )
    return {"ok": True, "ultimo_log": ultimo}


@router.get("/stato", response_model=SchedulerStatus)
async def get_scheduler_status():
    """Stato dello scheduler: job attivi, orari prossima esecuzione, ultimi log."""
    last_haccp = await db.scheduler_logs.find_one({"job": "haccp_daily"}, sort=[("timestamp", -1)])
    jobs = [
        SchedulerJob(
            id=job.id,
            name=job.name or job.id,
            next_run=str(job.next_run_time) if job.next_run_time else None,
            trigger=str(job.trigger),
            enabled=True,
        )
        for job in scheduler.get_jobs()
    ]
    return SchedulerStatus(
        running=scheduler.running,
        jobs=jobs,
        last_haccp_update=last_haccp.get("timestamp") if last_haccp else None,
    )


@router.post("/start")
async def start_scheduler(_admin=Depends(require_admin)):
    setup_scheduler()
    return {"success": True, "message": "Scheduler avviato"}


@router.post("/stop")
async def stop_scheduler(_admin=Depends(require_admin)):
    global scheduler_started
    if scheduler.running:
        scheduler.shutdown(wait=False)
        scheduler_started = False
        return {"success": True, "message": "Scheduler fermato"}
    return {"success": True, "message": "Scheduler non era in esecuzione"}


@router.post("/run-aggiorna-fatture-now")
async def run_aggiorna_fatture_now():
    """Aggiorna subito i riferimenti fattura nei lotti (>30gg)."""
    await job_aggiorna_riferimenti_fatture()
    return {"success": True, "message": "Riferimenti fatture aggiornati"}


@router.post("/run-pulizia-lotti-now")
async def run_pulizia_lotti_now(_admin=Depends(require_admin)):
    """Elimina subito i lotti scaduti da >30gg non più in ricetta."""
    await job_pulisci_lotti_scaduti()
    return {"success": True, "message": "Lotti scaduti eliminati"}


@router.post("/run-haccp-now")
async def run_haccp_now(_admin=Depends(require_admin)):
    """Esegue l'orchestratore mattutino come amministratore."""
    from app.lotti.servizi.automatismi_mattutini import run_morning_automation

    return await run_morning_automation(source="manual_admin")


@router.post("/morning/run")
async def run_morning(request: Request, actor=Depends(require_automation_or_admin)):
    """Ingresso indipendente Lotti per scheduler interno e workflow GitHub."""
    from app.lotti.servizi.automatismi_mattutini import run_morning_automation

    source = "external_workflow" if actor and actor.get("ruolo") == "automazione" else "manual_admin"
    return await run_morning_automation(source=source, actor=actor)


@router.get("/morning/status")
async def morning_status(data: str = None):
    from app.lotti.servizi.automatismi_mattutini import get_morning_status

    return await get_morning_status(data)


@router.get("/logs")
async def get_scheduler_logs(limit: int = 50, job: str = None):
    """Ultimi log dello scheduler con esito per ogni job. Filtro opzionale
    ?job=nome. I log appartengono al database operativo separato di Lotti."""
    q = {"job": job} if job else {}
    logs = (
        await db.scheduler_logs.find(q, {"_id": 0})
        .sort("timestamp", -1)
        .limit(min(limit, 200))
        .to_list(min(limit, 200))
    )
    return logs


async def job_digest_mattutino():
    """Promemoria operativo del mattino: calcola lotti scaduti/in scadenza e invia
    il riepilogo su WhatsApp (se il gateway è configurato)."""
    from app.lotti.routers.digest import calcola_e_invia
    try:
        res = await calcola_e_invia()
        logger.info(f"[scheduler] digest mattutino: {res.get('conteggi')} esito={res.get('esito')}")
    except Exception as e:
        logger.warning(f"[scheduler] digest mattutino errore: {e}")


# NB: lo scheduler viene avviato dallo startup_event di server.py (dentro l'event
# loop). Non avviarlo qui all'import: scheduler.start()/create_task richiedono un
# event loop in esecuzione, assente in fase di import → fallirebbe sempre.
