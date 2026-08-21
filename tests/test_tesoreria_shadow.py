"""Agente Tesoreria: aggregati minimizzati, shadow mode e idempotenza."""

import asyncio
from datetime import date

from app.services.sheets_document_store import MemorySheetsClient

import app.agents.tesoreria_shadow as agente_mod
import app.services.tesoreria_shadow_service as servizio_mod
from app.agents.tesoreria_shadow import TesoreriaShadow
from app.services.tesoreria_shadow_service import leggi_snapshot_tesoreria


def _db():
    return MemorySheetsClient()["tesoreria_shadow_test"]


async def _semina(db):
    await db["scadenziario_fornitori"].insert_many([
        {
            "id": "scaduta-1",
            "data_scadenza": "2026-07-10",
            "importo_rata": "100.00",
            "pagato": False,
            "stato": "aperta",
            "fornitore": "DATO CHE NON DEVE USCIRE",
        },
        {
            "id": "futura-1",
            "data_scadenza": "2026-07-25",
            "importo_rata": "200.00",
            "pagato": False,
            "stato": "aperta",
            "fornitore": "ALTRO DATO CHE NON DEVE USCIRE",
        },
        {
            "id": "futura-2",
            "data_scadenza": "2026-08-15",
            "importo_residuo": "1.300,50",
            "pagato": False,
            "stato": "aperta",
        },
        {
            "id": "gia-pagata",
            "data_scadenza": "2026-07-22",
            "importo": 999,
            "pagato": True,
            "stato": "pagata",
        },
    ])


async def _semina_fonti_operative(db):
    await db["prima_nota_cassa"].insert_one({
        "id": "cassa-1", "data": "2026-07-01", "tipo": "entrata", "importo": 100,
    })
    await db["prima_nota_banca"].insert_one({
        "id": "banca-1", "data": "2026-07-02", "tipo": "uscita", "importo": 150,
    })
    await db["chiusure_pos_manuali"].insert_many([
        {"data": "2026-07-01", "importo": 100, "source": "import_storico"},
        {"data": "2026-07-02", "importo": 50, "source": "inserimento_manuale_terminale"},
    ])
    await db["estratto_conto_movimenti"].insert_many([
        {
            "data": "2026-07-02", "importo": 90,
            "descrizione_originale": "INC.POS CARTE CREDIT - NUMIA-INTER DEL 01/07/26 PDV TEST",
        },
        {
            "data": "2026-07-02", "importo": 0.02,
            "descrizione_originale": "INC.POS CARTE CREDIT - REMUNERAZIONE DCC NUMIA DEL 01/07/26",
        },
    ])
    await db["assegni"].insert_one({
        "id": "a-1", "importo": 20, "stato": "emesso", "beneficiario": "NON DEVE USCIRE",
    })
    await db["bonifici_transfers"].insert_one({
        "id": "b-1", "importo": 30, "riconciliato": False,
        "beneficiario": {"nome": "NON DEVE USCIRE", "iban": "IT00TEST"},
    })
    await db["paypal_transactions"].insert_one({
        "transaction_id": "p-1", "importo": -40,
        "riconciliato_con_estratto_banca": False, "nome_controparte": "NON DEVE USCIRE",
    })


def test_servizio_restituisce_solo_aggregati_minimizzati():
    db = _db()
    asyncio.run(_semina(db))
    snapshot = asyncio.run(leggi_snapshot_tesoreria(
        db, reference_date=date(2026, 7, 20), horizon_days=30
    )).to_dict()

    assert snapshot["overdue"]["count"] == 1
    assert snapshot["overdue"]["total"] == "100.00"
    assert snapshot["upcoming"]["count"] == 2
    assert snapshot["upcoming"]["total"] == "1500.50"
    assert "fornitore" not in str(snapshot).lower()


def test_servizio_estende_snapshot_a_liquidita_pos_e_code_senza_dati_personali(monkeypatch):
    db = _db()
    asyncio.run(_semina_fonti_operative(db))

    async def saldi_canonici(database, collection, query, anno=None, query_base_precedente=None):
        saldo = 100.0 if collection == "prima_nota_cassa" else -150.0
        return {
            "saldo": saldo, "saldo_iniziale_manuale": False,
            "totale_entrate": 0, "totale_uscite": 0,
            "saldo_anno": saldo, "saldo_precedente": 0,
        }

    monkeypatch.setattr(servizio_mod, "aggrega_saldo_prima_nota", saldi_canonici)
    snapshot = asyncio.run(leggi_snapshot_tesoreria(
        db, reference_date=date(2026, 7, 20), horizon_days=30
    )).to_dict()

    assert snapshot["liquidity"] == {
        "cassa": "100.00", "banca": "-150.00", "totale": "-50.00",
        "saldo_cassa_manuale": False, "saldo_banca_manuale": False,
    }
    assert snapshot["pos"]["giorni_chiusura"] == 2
    assert snapshot["pos"]["attesa_giorni"] == 7
    assert snapshot["pos"]["giorni_con_evidenza_banca"] == 1
    assert snapshot["pos"]["giorni_senza_evidenza_banca"] == 1
    assert snapshot["pos"]["giorni_importo_non_coerente"] == 1
    assert snapshot["pos"]["totale_accrediti_banca"] == "90.00"
    assert snapshot["pending_checks"] == {
        "assegni": {"count": 1, "total": "20.00"},
        "bonifici": {"count": 1, "total": "30.00"},
        "paypal": {"count": 1, "total": "40.00"},
    }
    serializzato = str(snapshot).lower()
    assert "non deve uscire" not in serializzato
    assert "it00test" not in serializzato


def test_agente_crea_due_decisioni_shadow_senza_azioni_di_business(monkeypatch):
    db = _db()
    asyncio.run(_semina(db))

    async def snapshot_fisso(database):
        return await leggi_snapshot_tesoreria(
            database, reference_date=date(2026, 7, 20), horizon_days=30
        )

    monkeypatch.setattr(agente_mod, "leggi_snapshot_tesoreria", snapshot_fisso)
    asyncio.run(TesoreriaShadow().run(db))

    decisioni = asyncio.run(db["ai_decisions"].find({}, {"_id": 0}).to_list(10))
    assert len(decisioni) == 2
    scaduta = next(d for d in decisioni if "scadute" in d["objective"])
    futura = next(d for d in decisioni if "prossimi" in d["objective"])
    assert scaduta["execution_status"] == "pending_approval"
    assert futura["execution_status"] == "proposed"
    assert all(d["metadata"]["shadow_mode"] is True for d in decisioni)
    assert asyncio.run(db["prima_nota_banca"].count_documents({})) == 0
    assert asyncio.run(db["operazioni_da_confermare"].count_documents({})) == 0


def test_agente_segnala_liquidita_pos_e_code_senza_eseguire_azioni(monkeypatch):
    db = _db()
    asyncio.run(_semina_fonti_operative(db))

    async def saldi_canonici(database, collection, query, anno=None, query_base_precedente=None):
        saldo = 100.0 if collection == "prima_nota_cassa" else -150.0
        return {
            "saldo": saldo, "saldo_iniziale_manuale": False,
            "totale_entrate": 0, "totale_uscite": 0,
            "saldo_anno": saldo, "saldo_precedente": 0,
        }

    monkeypatch.setattr(servizio_mod, "aggrega_saldo_prima_nota", saldi_canonici)

    async def snapshot_fisso(database):
        return await leggi_snapshot_tesoreria(
            database, reference_date=date(2026, 7, 20), horizon_days=30
        )

    monkeypatch.setattr(agente_mod, "leggi_snapshot_tesoreria", snapshot_fisso)
    asyncio.run(TesoreriaShadow().run(db))

    decisioni = asyncio.run(db["ai_decisions"].find({}, {"_id": 0}).to_list(10))
    assert {d["semantic_key"] for d in decisioni} == {
        "tesoreria:liquidita_negativa",
        "tesoreria:riconciliazioni_pendenti",
        "tesoreria:pos_evidenze",
    }
    assert next(
        d for d in decisioni if d["semantic_key"] == "tesoreria:liquidita_negativa"
    )["execution_status"] == "pending_approval"
    assert asyncio.run(db["prima_nota_banca"].count_documents({})) == 1
    assert asyncio.run(db["operazioni_da_confermare"].count_documents({})) == 0


def test_riesecuzione_stessa_fotografia_non_duplica(monkeypatch):
    db = _db()
    asyncio.run(_semina(db))

    async def snapshot_fisso(database):
        return await leggi_snapshot_tesoreria(
            database, reference_date=date(2026, 7, 20), horizon_days=30
        )

    monkeypatch.setattr(agente_mod, "leggi_snapshot_tesoreria", snapshot_fisso)
    asyncio.run(TesoreriaShadow().run(db))
    asyncio.run(TesoreriaShadow().run(db))

    assert asyncio.run(db["ai_decisions"].count_documents({})) == 2
    assert asyncio.run(db["ai_decision_events"].count_documents({"event": "decisione_creata"})) == 2


def test_nessuna_scadenza_non_genera_decisioni(monkeypatch):
    db = _db()

    async def snapshot_vuoto(database):
        return await leggi_snapshot_tesoreria(
            database, reference_date=date(2026, 7, 20), horizon_days=30
        )

    monkeypatch.setattr(agente_mod, "leggi_snapshot_tesoreria", snapshot_vuoto)
    asyncio.run(TesoreriaShadow().run(db))
    assert asyncio.run(db["ai_decisions"].count_documents({})) == 0


def test_scheduler_registra_tesoreria_shadow_ogni_ora(monkeypatch):
    import app.scheduler as scheduler_mod

    class _SchedulerFinto:
        def __init__(self):
            self.jobs = []
            self.running = False

        def add_job(self, funzione, *args, **kwargs):
            self.jobs.append((funzione, args, kwargs))

        def start(self):
            self.running = True

    schedulatore = _SchedulerFinto()
    monkeypatch.setattr(scheduler_mod, "scheduler", schedulatore)
    scheduler_mod.start_scheduler()

    job = next(item for item in schedulatore.jobs if item[2].get("id") == "ai_tesoreria_shadow")
    assert job[1] == ("interval",)
    assert job[2]["hours"] == 1
    assert job[2]["next_run_time"] is not None
    assert schedulatore.running is True
    cash_flow_job = next(
        item for item in schedulatore.jobs if item[2].get("id") == "ai_cash_flow_13w_shadow"
    )
    assert cash_flow_job[1] == ("interval",)
    assert cash_flow_job[2]["hours"] == 6
    assert cash_flow_job[2]["next_run_time"] is not None
