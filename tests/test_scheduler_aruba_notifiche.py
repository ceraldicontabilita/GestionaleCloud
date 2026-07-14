"""Trovato in sessione di debug 2026-07-14: la scansione notifiche Aruba
(anticipo Prima Nota provvisoria dalle email di avviso fattura) esisteva solo
come endpoint manuale (`/api/prima-nota/attese/scan-notifiche-ora`), mai
chiamato da nessuno (FE/scheduler/test) — quindi non partiva mai da sola.

Scelta utente: job automatico orario nello scheduler persistente (sopravvive
ai riavvii/deploy, a differenza del vecchio "email monitor" ad asyncio in
memoria). Questo test blocca la regressione: se il job sparisce dallo
scheduler, il test fallisce."""
import app.scheduler as scheduler_mod


def test_job_scansione_aruba_registrato_nello_scheduler(monkeypatch):
    # add_job() popola il job store indipendentemente dallo stato "running":
    # evitiamo scheduler.start() (richiede un event loop asyncio corrente nel
    # thread, fragile in base all'ordine di esecuzione degli altri test).
    monkeypatch.setattr(scheduler_mod.scheduler, "start", lambda: None)
    scheduler_mod.start_scheduler()
    jobs = {j.id: j for j in scheduler_mod.scheduler.get_jobs()}
    assert "aruba_notifiche_scan" in jobs, (
        "Il job di scansione notifiche Aruba non è registrato: "
        "le fatture attese/provvisorie non verranno più popolate da sole."
    )
    job = jobs["aruba_notifiche_scan"]
    # deve girare periodicamente (interval), non essere un job one-shot
    assert job.trigger is not None
