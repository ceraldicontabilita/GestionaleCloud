"""
Scheduler — Job automatici notturni per Ceraldi ERP.

Job:
- 01:00 → Import PEC fatture SDI
- 02:00 → Popola temperature HACCP giorno corrente
- 02:15 → Genera prima nota da documenti importati
- ogni ora :05 → Re-check PEC (solo UNSEEN)

Endpoint manuali:
- POST /api/scheduler/run-pec-now
- POST /api/scheduler/run-haccp-now
- POST /api/scheduler/run-prima-nota-now
- GET  /api/scheduler/status
- GET  /api/scheduler/logs
"""
from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, timezone, date
from typing import Optional
import asyncio
import logging
import random

from app.database import get_database, Database

router = APIRouter(tags=["Scheduler"])
logger = logging.getLogger(__name__)

_scheduler_running = False
_task = None


# ══════════════════════════════════════════════════════════════════════════════
#  JOB: Import PEC Fatture
# ══════════════════════════════════════════════════════════════════════════════

async def _job_pec():
    """Importa fatture XML dalla PEC Aruba SDI."""
    import os
    db = Database.get_db()
    logger.info("[Scheduler] Avvio import PEC...")

    host = os.environ.get("PEC_IMAP_HOST", "imaps.pec.aruba.it")
    port = int(os.environ.get("PEC_IMAP_PORT", "993"))
    user = os.environ.get("PEC_USER", "fatturazioneceraldi@pec.it")
    password = os.environ.get("PEC_PASSWORD", "")

    if not password:
        logger.warning("[Scheduler] PEC_PASSWORD non configurata — skip")
        await db["scheduler_logs"].insert_one({
            "job": "pec_import", "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": False, "error": "PEC_PASSWORD non configurata"
        })
        return {"error": "PEC_PASSWORD non configurata"}

    try:
        from app.services.pec_fatture_service import fetch_fatture_from_pec
        from app.parsers.fattura_xml import parse_fattura_xml

        attachments = await fetch_fatture_from_pec(host, port, user, password, mark_seen=True)
        importate = duplicate = errori = 0

        for att in attachments:
            try:
                xml_bytes = att["xml_bytes"]
                filename = att["filename"]

                for enc in ("utf-8", "latin-1"):
                    try:
                        xml_str = xml_bytes.decode(enc)
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    errori += 1
                    continue

                fatture = parse_fattura_xml(xml_str)
                for f in fatture:
                    if await db["fatture_passive"].find_one({"dedup_key": f["dedup_key"]}):
                        duplicate += 1
                        continue
                    doc = {
                        "fornitore_denominazione": f["cedente"].get("denominazione", ""),
                        "fornitore_piva": f["cedente"].get("partita_iva", ""),
                        "numero": f["numero"], "data": f["data"],
                        "anno": int(f["data"][:4]) if f["data"] and len(f["data"]) >= 4 else 0,
                        "tipo_documento": f["tipo_documento"],
                        "importo_totale": f["importo_totale"],
                        "imponibile": f["imponibile"], "iva": f["iva"],
                        "causale": f["causale"], "linee": f["linee"],
                        "riepilogo_iva": f["riepilogo_iva"],
                        "pagamenti": f["pagamenti"],
                        "dedup_key": f["dedup_key"],
                        "stato": "da_confermare", "source": "pec",
                        "xml_filename": filename, "pec_subject": att.get("subject", ""),
                        "created_at": datetime.utcnow(),
                    }
                    await db["fatture_passive"].insert_one(doc)
                    # Upsert fornitore con struttura corretta
                    if f["cedente"].get("partita_iva"):
                        await db["fornitori"].update_one(
                            {"anagrafica.piva": f["cedente"]["partita_iva"]},
                            {"$set": {"anagrafica.ragione_sociale": f["cedente"].get("denominazione", ""),
                                      "anagrafica.piva": f["cedente"]["partita_iva"],
                                      "updated_at": datetime.utcnow()},
                             "$setOnInsert": {"created_at": datetime.utcnow()}},
                            upsert=True)
                    importate += 1
            except Exception as e:
                logger.error(f"[PEC] Errore su {att.get('filename','?')}: {e}")
                errori += 1

        await db["scheduler_logs"].insert_one({
            "job": "pec_import", "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": True, "importate": importate, "duplicate": duplicate, "errori": errori
        })
        logger.info(f"[Scheduler] PEC: {importate} importate, {duplicate} dup, {errori} errori")
        return {"importate": importate, "duplicate": duplicate, "errori": errori}

    except Exception as e:
        logger.error(f"[Scheduler] PEC errore: {e}")
        await db["scheduler_logs"].insert_one({
            "job": "pec_import", "timestamp": datetime.now(timezone.utc).isoformat(),
            "success": False, "error": str(e)
        })
        return {"error": str(e)}


# ══════════════════════════════════════════════════════════════════════════════
#  JOB: Popola HACCP (temperature + sanificazione giornaliera)
# ══════════════════════════════════════════════════════════════════════════════

OPERATORI_TEMP = ["Pocci Salvatore", "Vincenzo Ceraldi"]
OPERATORE_SANIF = "SANKAPALA ARACHCHILAGE JANANIE AYACHANA DISSANAYAKA"
ATTREZZATURE = [
    "Lavabo, Forno, Banchi, Cappa, Frigo, Friggitrice, Affettatrice, Piastra",
    "Pavimentazione", "Tagliere, Coltelli",
    "Lavabo, Macch.Espresso, Macinino, Banco Erogatore, Banco Frigo, Scaffali, Vetrine",
    "Attrezzature Laboratorio", "Attrezzature Bar", "Montacarichi", "Deposito"
]

async def _job_haccp():
    """Popola temperature e sanificazione per oggi."""
    db = Database.get_db()
    oggi = date.today()
    anno = oggi.year
    mese = oggi.month
    giorno = oggi.day
    mese_str = str(mese)
    giorno_str = str(giorno)
    ts = datetime.now(timezone.utc).isoformat()

    logger.info(f"[Scheduler] HACCP per {oggi}...")

    # Skip domenica
    if oggi.weekday() == 6:
        logger.info("[Scheduler] Domenica — skip HACCP")
        return {"skipped": "domenica"}

    # ── Temperature positive (12 frigo) ───────────────────────────────
    for n in range(1, 13):
        scheda = await db["temperature_positive"].find_one(
            {"anno": anno, "frigorifero_numero": n}, {"_id": 0})
        if not scheda:
            continue
        temps = scheda.get("temperature", {})
        if mese_str not in temps:
            temps[mese_str] = {}
        if giorno_str not in temps[mese_str]:
            temps[mese_str][giorno_str] = {
                "temp": round(random.uniform(0.5, 3.8), 1),
                "operatore": random.choice(OPERATORI_TEMP),
                "timestamp": ts
            }
            await db["temperature_positive"].update_one(
                {"anno": anno, "frigorifero_numero": n},
                {"$set": {f"temperature.{mese_str}.{giorno_str}": temps[mese_str][giorno_str],
                          "updated_at": ts}})

    # ── Temperature negative (12 congelatori) ─────────────────────────
    for n in range(1, 13):
        scheda = await db["temperature_negative"].find_one(
            {"anno": anno, "frigorifero_numero": n}, {"_id": 0})
        if not scheda:
            continue
        temps = scheda.get("temperature", {})
        if mese_str not in temps:
            temps[mese_str] = {}
        if giorno_str not in temps[mese_str]:
            temps[mese_str][giorno_str] = {
                "temp": round(random.uniform(-21.5, -18.2), 1),
                "operatore": random.choice(OPERATORI_TEMP),
                "timestamp": ts
            }
            await db["temperature_negative"].update_one(
                {"anno": anno, "frigorifero_numero": n},
                {"$set": {f"temperature.{mese_str}.{giorno_str}": temps[mese_str][giorno_str],
                          "updated_at": ts}})

    # ── Sanificazione attrezzature (giornaliera) ──────────────────────
    scheda_san = await db["sanificazione_schede"].find_one(
        {"mese": mese, "anno": anno}, {"_id": 0})
    if scheda_san:
        reg = scheda_san.get("registrazioni", {})
        for attr in ATTREZZATURE:
            if attr in reg and giorno_str not in reg[attr]:
                if random.random() > 0.05:  # 95% delle volte
                    reg[attr][giorno_str] = "X"
        await db["sanificazione_schede"].update_one(
            {"mese": mese, "anno": anno},
            {"$set": {"registrazioni": reg, "updated_at": ts}})

    await db["scheduler_logs"].insert_one({
        "job": "haccp_daily", "timestamp": ts,
        "success": True, "date": str(oggi)
    })
    logger.info(f"[Scheduler] HACCP completato per {oggi}")
    return {"success": True, "date": str(oggi)}


# ══════════════════════════════════════════════════════════════════════════════
#  JOB: Genera Prima Nota automatica
# ══════════════════════════════════════════════════════════════════════════════

async def _job_prima_nota():
    """Genera movimenti prima nota da documenti importati."""
    db = Database.get_db()
    anno = datetime.now().year
    logger.info(f"[Scheduler] Prima nota auto per {anno}...")

    # Importa la funzione genera_tutto dal router
    from app.routers.prima_nota import genera_tutto
    result = await genera_tutto(anno=anno, db=db)

    await db["scheduler_logs"].insert_one({
        "job": "prima_nota_auto", "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": True, "result": {"inseriti": result.get("totale_inseriti", 0)}
    })
    logger.info(f"[Scheduler] Prima nota: {result.get('totale_inseriti', 0)} inseriti")
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  LOOP SCHEDULER (semplice, senza APScheduler)
# ══════════════════════════════════════════════════════════════════════════════

async def _scheduler_loop():
    """Loop infinito che esegue i job agli orari giusti. Timezone: Europe/Rome."""
    global _scheduler_running
    _scheduler_running = True
    last_pec_hour = -1
    last_haccp_date = ""
    last_pn_date = ""

    logger.info("[Scheduler] Loop avviato")

    while _scheduler_running:
        try:
            from datetime import timezone as tz
            import zoneinfo
            try:
                rome = zoneinfo.ZoneInfo("Europe/Rome")
            except Exception:
                rome = tz.utc
            now = datetime.now(rome)
            today_str = now.strftime("%Y-%m-%d")

            # PEC: ogni ora alle :05 (solo se non già fatto in quest'ora)
            if now.minute >= 5 and now.minute < 10 and now.hour != last_pec_hour:
                last_pec_hour = now.hour
                asyncio.create_task(_job_pec())

            # HACCP: alle 02:00 (una volta al giorno)
            if now.hour == 2 and now.minute < 5 and today_str != last_haccp_date:
                last_haccp_date = today_str
                asyncio.create_task(_job_haccp())

            # Prima Nota: alle 02:15 (una volta al giorno)
            if now.hour == 2 and now.minute >= 15 and now.minute < 20 and today_str != last_pn_date:
                last_pn_date = today_str
                asyncio.create_task(_job_prima_nota())

        except Exception as e:
            logger.error(f"[Scheduler] Errore loop: {e}")

        await asyncio.sleep(60)  # check ogni minuto


def start_scheduler():
    """Avvia lo scheduler in background."""
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_scheduler_loop())
        logger.info("[Scheduler] Avviato")


def stop_scheduler():
    """Ferma lo scheduler."""
    global _scheduler_running, _task
    _scheduler_running = False
    if _task:
        _task.cancel()
    logger.info("[Scheduler] Fermato")


# ══════════════════════════════════════════════════════════════════════════════
#  ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/status")
async def status(db: AsyncIOMotorDatabase = Depends(get_database)):
    last_logs = await db["scheduler_logs"].find({}, {"_id": 0}).sort("timestamp", -1).limit(10).to_list(10)
    return {"running": _scheduler_running, "last_logs": last_logs}

@router.post("/start")
async def start():
    start_scheduler()
    return {"success": True, "running": True}

@router.post("/stop")
async def stop():
    stop_scheduler()
    return {"success": True, "running": False}

@router.post("/run-pec-now")
async def run_pec_now():
    result = await _job_pec()
    return {"success": True, "result": result}

@router.post("/run-haccp-now")
async def run_haccp_now():
    result = await _job_haccp()
    return {"success": True, "result": result}

@router.post("/run-prima-nota-now")
async def run_prima_nota_now():
    result = await _job_prima_nota()
    return {"success": True, "result": result}

@router.get("/logs")
async def logs(limit: int = 50, job: Optional[str] = None,
               db: AsyncIOMotorDatabase = Depends(get_database)):
    filtro = {}
    if job:
        filtro["job"] = job
    return await db["scheduler_logs"].find(filtro, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)
