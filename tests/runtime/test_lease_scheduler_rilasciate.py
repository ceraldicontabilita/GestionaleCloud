"""Un lease abbandonato blocca il suo job per tutto il TTL.

Misurato in produzione il 19/09/2026. Il merge di una PR fa ridistribuire
Render; il processo uscente muore mentre tiene il lease del job in corso, e
quello entrante trova il job occupato:

    [SCHEDULER] job drive_fatture_ricostruzione_ripresa saltato:
    lease detenuta da un'altra istanza

ogni due minuti. La ricostruzione dell'archivio Drive e' rimasta ferma a 57
file su 2.447 per venti minuti, finche' il lease non e' scaduto da solo — TTL
900 secondi. Non era un blocco permanente: era un quarto d'ora di lavoro di
fondo perso a ogni deploy.

Due cose lo evitano: annotare i lease vivi e restituirli allo spegnimento, e
non bloccare l'event loop aspettando i job che girano su quello stesso loop.
"""
import asyncio
import inspect

import pytest

from app.services.supabase_runtime_database import SupabaseRuntimeDatabase


def _run(coroutine):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coroutine)
    finally:
        loop.close()


class _Db(SupabaseRuntimeDatabase):
    """Il database vero, con le sole RPC sostituite da una spia."""

    def __init__(self):  # noqa: D107 — niente connessioni, solo lo stato che serve
        self._instance_id = "istanza-1"
        self._lease_attive = set()
        self.chiamate = []
        self.acquisizione_riesce = True

    async def _rpc(self, nome, payload=None, **_k):
        self.chiamate.append((nome, dict(payload or {})))
        if nome == "gc_try_scheduler_lease":
            return self.acquisizione_riesce
        return True


def _rpc_di(db, nome):
    return [p for n, p in db.chiamate if n == nome]


def test_il_lease_preso_viene_annotato():
    db = _Db()

    async def prendi():
        async with db.scheduler_lease("job-a", ttl_seconds=1) as preso:
            assert preso is True
            assert db._lease_attive == {"job-a"}

    _run(prendi())


def test_a_fine_job_il_lease_e_gia_restituito():
    db = _Db()

    async def prendi():
        async with db.scheduler_lease("job-a", ttl_seconds=1):
            pass

    _run(prendi())

    assert db._lease_attive == set()
    assert _rpc_di(db, "gc_release_scheduler_lease") == [
        {"p_job_id": "job-a", "p_owner_id": "istanza-1"}
    ]


def test_un_lease_non_ottenuto_non_si_annota():
    """Se il lease e' di un'altra istanza, non e' nostro da restituire."""
    db = _Db()
    db.acquisizione_riesce = False

    async def prendi():
        async with db.scheduler_lease("job-a") as preso:
            assert preso is False

    _run(prendi())

    assert db._lease_attive == set()
    assert _rpc_di(db, "gc_release_scheduler_lease") == []


def test_allo_spegnimento_i_lease_rimasti_tornano_indietro():
    """Il caso del deploy: il processo esce con dei lease in mano."""
    db = _Db()
    db._lease_attive = {"drive_fatture_ricostruzione_ripresa", "dedup_fatture"}

    rimasti = _run(db.rilascia_lease_attive())

    assert rimasti == ["dedup_fatture", "drive_fatture_ricostruzione_ripresa"]
    assert db._lease_attive == set()
    assert _rpc_di(db, "gc_release_scheduler_lease") == [
        {"p_job_id": "dedup_fatture", "p_owner_id": "istanza-1"},
        {"p_job_id": "drive_fatture_ricostruzione_ripresa", "p_owner_id": "istanza-1"},
    ]


def test_si_rilascia_per_job_id_mai_con_un_filtro():
    """La regola §6: nessuna cancellazione con filtro. Si usa la stessa RPC
    per identificativo del percorso normale."""
    db = _Db()
    db._lease_attive = {"job-a"}

    _run(db.rilascia_lease_attive())

    nomi = {n for n, _ in db.chiamate}
    assert nomi == {"gc_release_scheduler_lease"}


def test_senza_lease_non_si_chiama_niente():
    db = _Db()
    assert _run(db.rilascia_lease_attive()) == []
    assert db.chiamate == []


def test_un_rilascio_fallito_non_ferma_gli_altri():
    db = _Db()
    db._lease_attive = {"job-a", "job-b"}
    originale = db._rpc

    async def _rpc(nome, payload=None, **k):
        if (payload or {}).get("p_job_id") == "job-a":
            raise RuntimeError("Supabase irraggiungibile")
        return await originale(nome, payload, **k)

    db._rpc = _rpc

    assert _run(db.rilascia_lease_attive()) == ["job-a", "job-b"]
    assert db._lease_attive == set()


# ── Lo spegnimento non deve bloccare l'event loop ─────────────────────────

def test_lo_scheduler_si_ferma_senza_aspettare_i_job():
    """I job sono coroutine sullo stesso loop: aspettarli da dentro il loop
    lo blocca, lo spegnimento non finisce e il processo muore coi lease in
    mano. E' la causa a monte del lease abbandonato."""
    from app import scheduler as mod

    sorgente = inspect.getsource(mod.stop_scheduler)
    assert "shutdown(wait=False)" in sorgente


def test_lo_shutdown_dell_applicazione_restituisce_i_lease():
    from pathlib import Path

    sorgente = (
        Path(__file__).resolve().parents[2] / "app" / "main.py"
    ).read_text(encoding="utf-8")

    assert "rilascia_lease_attive" in sorgente, (
        "Senza questa chiamata il processo esce coi lease in mano e il job "
        "resta bloccato per tutto il TTL."
    )


@pytest.mark.parametrize("attributo", ["rilascia_lease_attive", "scheduler_lease"])
def test_l_interfaccia_resta_quella_attesa(attributo):
    assert callable(getattr(SupabaseRuntimeDatabase, attributo, None))
