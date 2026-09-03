"""Job di migrazione una tantum Sheets -> Supabase (app/routers/admin.py).

Copre: guardie sull'avvio del job (conferma esplicita, collegamento Supabase
configurato, riuso del job gia' in corso), isolamento degli errori per
singola collezione, blocco se il backend attivo e' gia' Supabase, e
correttezza del conteggio righe riportato a fine job.

I test sull'avvio (guardie sincrone) evitano deliberatamente di lasciar
girare il task di sfondo schedulato da asyncio.create_task, il cui esito
dipende da dettagli di scheduling dell'event loop non rilevanti per queste
guardie; i test sull'esecuzione effettiva invocano invece direttamente
_run_supabase_migration_job in modo deterministico, popolando a mano il
job come farebbe l'endpoint.
"""
import asyncio
import uuid

import pytest
from fastapi import HTTPException

from app.config import settings
from app.database import Database
from app.services.sheets_document_store import MemorySheetsClient
import app.services.supabase_runtime_database as supabase_runtime_database
from app.routers.admin import (
    _run_supabase_migration_job,
    _supabase_migration_jobs,
    avvia_migrazione_supabase,
    stato_migrazione_supabase,
)


class FakeSupabaseRuntimeDatabase:
    """Sostituto in memoria di SupabaseRuntimeDatabase per i test: nessuna
    connessione Postgres reale, registra soltanto cosa gli verrebbe scritto."""

    scritture: dict = {}
    fallisci_su: set = set()
    closed = False

    def __init__(self, name, config):
        self.name = name
        self.config = config
        FakeSupabaseRuntimeDatabase.scritture = {}
        FakeSupabaseRuntimeDatabase.closed = False

    async def bulk_seed(self, collection_name, documents):
        if collection_name in FakeSupabaseRuntimeDatabase.fallisci_su:
            raise RuntimeError(f"scrittura simulata fallita per {collection_name}")
        FakeSupabaseRuntimeDatabase.scritture[collection_name] = list(documents)
        return len(documents)

    async def mirror_collection(self, collection_name, documents):
        return await self.bulk_seed(collection_name, documents)

    async def verify_collection(self, collection_name, documents):
        remote = FakeSupabaseRuntimeDatabase.scritture.get(collection_name, [])
        coincide = remote == list(documents)
        return {
            "righe_origine": len(documents),
            "righe_destinazione": len(remote),
            "impronta_origine": "origine",
            "impronta_destinazione": "origine" if coincide else "diversa",
            "coincide": coincide,
        }

    def close(self):
        FakeSupabaseRuntimeDatabase.closed = True


@pytest.fixture(autouse=True)
def _reset_stato(monkeypatch):
    _supabase_migration_jobs.clear()
    FakeSupabaseRuntimeDatabase.fallisci_su = set()
    monkeypatch.setattr(
        supabase_runtime_database, "SupabaseRuntimeDatabase", FakeSupabaseRuntimeDatabase,
    )
    yield
    _supabase_migration_jobs.clear()


def _origine_con_dati():
    db = MemorySheetsClient()["gestionale_test"]
    asyncio.run(db["fatture"].insert_many([
        {"_id": "f1", "numero": "1"}, {"_id": "f2", "numero": "2"},
    ]))
    asyncio.run(db["fornitori"].insert_one({"_id": "forn1", "nome": "Acme"}))
    return db


def _job_manuale():
    job_id = str(uuid.uuid4())
    _supabase_migration_jobs[job_id] = {"job_id": job_id, "status": "running"}
    return job_id


def _configura_supabase(monkeypatch, *, completo=True):
    monkeypatch.setattr(settings, "SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setattr(settings, "SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setattr(
        settings,
        "SUPABASE_RUNTIME_SECRET",
        "runtime-test-secret" if completo else "",
    )


# ---------------------------------------------------------------- avvio ----

def test_avvio_richiede_conferma_esplicita():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(avvia_migrazione_supabase(payload={}, _admin={}))
    assert exc.value.status_code == 400


def test_avvio_richiede_collegamento_supabase_completo(monkeypatch):
    _configura_supabase(monkeypatch, completo=False)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(avvia_migrazione_supabase(payload={"conferma": "MIGRA"}, _admin={}))
    assert exc.value.status_code == 503


def test_avvio_valido_crea_un_job_in_esecuzione(monkeypatch):
    _configura_supabase(monkeypatch)
    monkeypatch.setattr(Database, "db", _origine_con_dati())
    # Non lasciamo girare il task reale: verifichiamo solo la risposta
    # sincrona dell'endpoint (creazione job), non l'esecuzione in background.
    monkeypatch.setattr("app.routers.admin.asyncio.create_task", lambda coro: coro.close())

    job = asyncio.run(avvia_migrazione_supabase(payload={"conferma": "MIGRA"}, _admin={}))
    assert job["status"] == "running"
    assert _supabase_migration_jobs[job["job_id"]] is job


def test_seconda_richiesta_mentre_gira_riusa_lo_stesso_job(monkeypatch):
    _configura_supabase(monkeypatch)
    monkeypatch.setattr(Database, "db", _origine_con_dati())
    monkeypatch.setattr("app.routers.admin.asyncio.create_task", lambda coro: coro.close())

    primo = asyncio.run(avvia_migrazione_supabase(payload={"conferma": "MIGRA"}, _admin={}))
    secondo = asyncio.run(avvia_migrazione_supabase(payload={"conferma": "MIGRA"}, _admin={}))
    assert primo["job_id"] == secondo["job_id"]


def test_job_id_sconosciuto_da_404():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(stato_migrazione_supabase(job_id="non-esiste", _admin={}))
    assert exc.value.status_code == 404


# ------------------------------------------------------------ esecuzione ---

def test_migrazione_copia_tutte_le_collezioni_e_riporta_i_conteggi(monkeypatch):
    _configura_supabase(monkeypatch)
    monkeypatch.setattr(Database, "db", _origine_con_dati())
    job_id = _job_manuale()

    asyncio.run(_run_supabase_migration_job(job_id))

    esito = asyncio.run(stato_migrazione_supabase(job_id=job_id, _admin={}))
    assert esito["status"] == "completed"
    assert esito["result"]["righe_totali"] == 3
    assert esito["result"]["backend_origine"] == "SheetDatabase"
    dettaglio = {item["collezione"]: item["righe"] for item in esito["result"]["dettaglio"]}
    assert dettaglio["fatture"] == 2
    assert dettaglio["fornitori"] == 1
    assert FakeSupabaseRuntimeDatabase.scritture["fatture"][0]["_id"] in {"f1", "f2"}
    assert FakeSupabaseRuntimeDatabase.closed is True


def test_errore_su_una_collezione_non_blocca_le_altre(monkeypatch):
    _configura_supabase(monkeypatch)
    monkeypatch.setattr(Database, "db", _origine_con_dati())
    FakeSupabaseRuntimeDatabase.fallisci_su = {"fatture"}
    job_id = _job_manuale()

    asyncio.run(_run_supabase_migration_job(job_id))

    esito = _supabase_migration_jobs[job_id]
    assert esito["status"] == "completed_con_errori"
    assert esito["result"]["errori"] == [
        {"collezione": "fatture", "errore": "scrittura simulata fallita per fatture"}
    ]
    # fornitori, non coinvolta dal fallimento, deve comunque essere passata.
    assert FakeSupabaseRuntimeDatabase.scritture["fornitori"][0]["_id"] == "forn1"


def test_blocca_se_il_backend_attivo_e_gia_supabase(monkeypatch):
    _configura_supabase(monkeypatch)
    monkeypatch.setattr(Database, "db", FakeSupabaseRuntimeDatabase("gestionale", {}))
    job_id = _job_manuale()

    asyncio.run(_run_supabase_migration_job(job_id))

    esito = _supabase_migration_jobs[job_id]
    assert esito["status"] == "failed"
    assert "gia' Supabase" in esito["error"]
