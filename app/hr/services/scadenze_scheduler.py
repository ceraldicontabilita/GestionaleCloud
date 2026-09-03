"""
Scadenzario automatico (A→B): job periodico che genera alert per
- contratti a termine in scadenza (data_fine_contratto sull'anagrafica);
- periodi di prova in scadenza (da employee_contracts.additional_data).

Usa l'alert_engine esistente (idempotente: non duplica alert già aperti).
Avviato dal lifespan di FastAPI tramite APScheduler.
"""
import logging
from datetime import datetime, timedelta, date

logger = logging.getLogger(__name__)
_scheduler = None


def _parse_date(s):
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


async def verifica_scadenze(db, giorni_contratto: int = 30, giorni_prova: int = 7) -> int:
    """Genera gli alert di scadenza. Ritorna il numero di alert NUOVI creati."""
    from app.hr.services.alert_engine import genera_alert
    oggi = date.today()
    creati = 0

    # 1. Contratti a termine in scadenza (data_fine_contratto sull'anagrafica)
    try:
        emps = await db["dipendenti"].find(
            {"data_fine_contratto": {"$nin": [None, ""]},
             "stato": {"$nin": ["cessato", "dimesso", "archiviato"]}},
            {"_id": 0, "id": 1, "nome_completo": 1, "nome": 1, "cognome": 1,
             "data_fine_contratto": 1}).to_list(2000)
    except Exception as e:
        logger.warning(f"scadenze contratti: query saltata: {e}")
        emps = []
    for e in emps:
        fine = _parse_date(e.get("data_fine_contratto"))
        if fine and oggi <= fine <= oggi + timedelta(days=giorni_contratto):
            nome = e.get("nome_completo") or f"{e.get('cognome','')} {e.get('nome','')}".strip()
            r = await genera_alert(
                "DIP_CONTRATTO_IN_SCADENZA", e.get("id"), "dipendenti",
                f"Contratto a termine di {nome} in scadenza il {fine.strftime('%d/%m/%Y')}",
                db, extra={"data_fine": fine.isoformat()})
            if r:
                creati += 1

    # 2. Periodo di prova in scadenza (da employee_contracts)
    try:
        contratti = await db["employee_contracts"].find(
            {"additional_data.periodo_prova": {"$nin": [None, ""]}},
            {"_id": 0, "employee_id": 1, "employee_name": 1, "additional_data": 1}
        ).sort("generated_at", -1).to_list(2000)
    except Exception as e:
        logger.warning(f"scadenze prova: query saltata: {e}")
        contratti = []
    visti = set()
    for c in contratti:
        eid = c.get("employee_id")
        if not eid or eid in visti:
            continue
        add = c.get("additional_data") or {}
        inizio = _parse_date(add.get("data_inizio"))
        try:
            gg = int(str(add.get("periodo_prova")).strip())
        except (ValueError, TypeError):
            gg = None
        if inizio and gg:
            fine_prova = inizio + timedelta(days=gg)
            if oggi <= fine_prova <= oggi + timedelta(days=giorni_prova):
                visti.add(eid)
                r = await genera_alert(
                    "DIP_PERIODO_PROVA_IN_SCADENZA", eid, "dipendenti",
                    f"Periodo di prova di {c.get('employee_name','')} in scadenza il "
                    f"{fine_prova.strftime('%d/%m/%Y')}",
                    db, extra={"fine_prova": fine_prova.isoformat()})
                if r:
                    creati += 1

    logger.info(f"Scadenzario: {creati} nuovi alert generati")
    return creati


def start_scheduler():
    """Avvia il job giornaliero (best-effort). No-op se APScheduler manca."""
    global _scheduler
    if _scheduler:
        return _scheduler
    try:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
    except Exception as e:
        logger.warning(f"APScheduler non disponibile, scadenzario disattivato: {e}")
        return None
    from app.hr.database import Database

    async def _job():
        try:
            await verifica_scadenze(Database.get_db())
        except Exception as e:
            logger.error(f"Job scadenze fallito: {e}")

    sched = AsyncIOScheduler(timezone="Europe/Rome")
    sched.add_job(_job, "interval", hours=24, id="scadenze",
                  next_run_time=datetime.now() + timedelta(seconds=45),
                  replace_existing=True)
    sched.start()
    _scheduler = sched
    logger.info("Scheduler scadenze avviato (ogni 24h)")
    return sched


def stop_scheduler():
    global _scheduler
    if _scheduler:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:
            pass
        _scheduler = None
