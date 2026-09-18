"""Compliance shadow: permessi, audit e code documentali minimizzati."""

import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.agents.compliance_shadow import ComplianceShadow
from app.services.compliance_shadow_service import leggi_snapshot_compliance


def _db():
    return MemorySheetsClient()["compliance_shadow_test"]


async def _seed(db):
    await db["utenti_pin"].insert_many([
        {"nome": "RISERVATO", "ruolo": "operatore", "attivo": True, "pin_hash": "SEGRETO"},
        {"nome": "", "ruolo": "responsabile", "attivo": True},
        {"nome": "INATTIVO", "ruolo": "sconosciuto", "attivo": False},
    ])
    await db["audit_log"].insert_many([
        {
            "id": "A1", "timestamp": "2026-07-20T10:00:00+00:00",
            "modulo": "fatture", "azione": "aggiornato", "utente": "sistema",
            "entita_id": "E1", "entita_collection": "invoices",
        },
        {"timestamp": "2026-07-20T11:00:00+00:00", "operation": "delete_many"},
    ])
    await db["documents_inbox"].insert_many([
        {"status": "nuovo", "processed": False, "pdf_data": "BASE64-RISERVATO", "filename": "RISERVATO.pdf"},
        {"status": "errore", "processed": False, "pdf_data": "BASE64"},
        {"status": "nuovo", "processed": False},
        {"status": "processato", "processed": True, "pdf_data": "BASE64"},
    ])
    await db["documenti_non_associati"].insert_one({
        "associato": False, "filename": "NON ESPORRE.pdf",
    })


def test_snapshot_aggregato_non_espone_identita_o_documenti():
    db = _db()
    asyncio.run(_seed(db))
    result = asyncio.run(leggi_snapshot_compliance(db)).to_dict()
    assert result["active_users"] == 2
    assert result["active_users_with_invalid_role"] == 1
    assert result["active_users_without_name"] == 1
    assert result["audit_records"] == 2
    assert result["audit_records_complete"] == 1
    assert result["audit_coverage_percent"] == 50.0
    assert result["inbox_documents_pending"] == 3
    assert result["inbox_documents_in_error"] == 1
    assert result["inbox_documents_without_payload"] == 1
    assert result["documents_unassociated"] == 1
    assert "RISERVATO" not in str(result)
    assert "SEGRETO" not in str(result)


def test_agente_segnala_senza_modificare_permessi_audit_o_documenti():
    db = _db()
    asyncio.run(_seed(db))
    asyncio.run(ComplianceShadow().run(db))
    before = asyncio.run(db["utenti_pin"].find({}, {"_id": 0}).to_list(10))
    audit_before = asyncio.run(db["audit_log"].count_documents({}))
    asyncio.run(ComplianceShadow().run(db))
    after = asyncio.run(db["utenti_pin"].find({}, {"_id": 0}).to_list(10))
    decisions = asyncio.run(db["ai_decisions"].find({}, {"_id": 0}).to_list(10))
    permission = next(d for d in decisions if d["semantic_key"] == "compliance:permessi")
    assert permission["autonomy_level"] == "L3"
    assert permission["execution_status"] == "pending_approval"
    assert len(decisions) == 3
    assert all(d["occurrence_count"] == 2 for d in decisions)
    assert before == after
    assert asyncio.run(db["audit_log"].count_documents({})) == audit_before
    assert asyncio.run(db["documents_inbox"].count_documents({})) == 4
    assert "RISERVATO" not in str(decisions)


def test_nessuna_anomalia_non_crea_decisioni():
    db = _db()
    asyncio.run(db["utenti_pin"].insert_one({
        "nome": "Utente", "ruolo": "sola_lettura", "attivo": True,
    }))
    asyncio.run(db["audit_log"].insert_one({
        "id": "A1", "timestamp": "2026-07-20T10:00:00+00:00",
        "modulo": "fatture", "azione": "letto", "utente": "sistema",
        "entita_id": "E1", "entita_collection": "invoices",
    }))
    asyncio.run(ComplianceShadow().run(db))
    assert asyncio.run(db["ai_decisions"].count_documents({})) == 0


def test_scheduler_registra_compliance_shadow(monkeypatch):
    from app.agents.orchestrator import SCHEDULE
    import app.scheduler as scheduler_mod

    assert SCHEDULE["ComplianceShadow"] == 86400

    class Scheduler:
        def __init__(self):
            self.jobs, self.running = [], False

        def add_job(self, fn, *args, **kwargs):
            self.jobs.append((fn, args, kwargs))

        def start(self):
            self.running = True

    scheduler = Scheduler()
    monkeypatch.setattr(scheduler_mod, "scheduler", scheduler)
    scheduler_mod.start_scheduler()
    job = next(j for j in scheduler.jobs if j[2].get("id") == "ai_compliance_shadow")
    assert job[2]["hours"] == 24
    assert job[2]["next_run_time"] is not None
