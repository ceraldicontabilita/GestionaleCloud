import asyncio
from datetime import date

from mongomock_motor import AsyncMongoMockClient

from app.handlers.corrispettivi import handler_prima_nota_corrispettivi
from app.parsers.corrispettivi_parser import parse_corrispettivo_xml
from app.routers.invoices.corrispettivi_helpers import _build_corrispettivo_doc
from app.services.fiscal_deadlines import monthly_deadline
from app.services.iva_liquidation_query import get_iva_period_snapshot
from app.services import paypal_api_sync
from app.routers import verifica_coerenza as verifica_coerenza_router


def _run(coro):
    return asyncio.run(coro)


def test_iva_maggio_2026_conserva_scadenza_nominale_e_legale():
    deadline = monthly_deadline(2026, 4)
    assert deadline["scadenza_nominale"] == "2026-05-16"
    assert deadline["scadenza_legale"] == "2026-05-18"


def test_iva_mese_corrente_non_espone_importi_parziali():
    snapshot = _run(get_iva_period_snapshot(
        None, anno=2026, mese=8, today=date(2026, 8, 11),
    ))
    assert snapshot["stato_calcolo"] == "NON_CALCOLATO"
    assert snapshot["iva_vendite"] is None
    assert snapshot["iva_acquisti"] is None
    assert snapshot["saldo"] is None


def test_iva_annuale_non_somma_mesi_futuri(monkeypatch):
    async def fake_month(_self, _anno, mese):
        calculated = mese == 1
        return {
            "iva_credito": {
                "da_fatture": 10.0 if calculated else None,
                "da_fatture_cents": 1000 if calculated else None,
                "num_fatture": 1 if calculated else 0,
            },
            "iva_debito": {
                "da_corrispettivi": 20.0 if calculated else None,
                "da_corrispettivi_cents": 2000 if calculated else None,
                "num_corrispettivi": 1 if calculated else 0,
            },
            "f24_commercialista": {},
        }

    monkeypatch.setattr(verifica_coerenza_router.Database, "get_db", lambda: object())
    monkeypatch.setattr(
        verifica_coerenza_router.VerificaCoerenza,
        "verifica_coerenza_iva_tra_pagine",
        fake_month,
    )
    result = _run(verifica_coerenza_router.confronto_iva_completo(2026))
    assert result["mensile"][0]["saldo_cents"] == 1000
    assert result["mensile"][1]["saldo"] is None
    assert result["totali"]["iva_credito_totale_cents"] == 1000
    assert result["totali"]["iva_debito_totale_cents"] == 2000
    assert result["totali"]["periodi_calcolati"] == 1


def test_corrispettivo_senza_imposta_non_inventa_iva():
    xml = """<DatiCorrispettivi versione="COR10">
      <Trasmissione><Progressivo>1</Progressivo><Dispositivo><Tipo>RT</Tipo><IdDispositivo>RT1</IdDispositivo></Dispositivo></Trasmissione>
      <DataOraRilevazione>2026-08-10T22:00:00+02:00</DataOraRilevazione>
      <DatiRT>
        <Riepilogo><IVA><AliquotaIVA>10.00</AliquotaIVA></IVA><Ammontare>100.00</Ammontare></Riepilogo>
        <Totali><NumeroDocCommerciali>1</NumeroDocCommerciali><PagatoContanti>100.00</PagatoContanti></Totali>
      </DatiRT>
    </DatiCorrispettivi>"""
    parsed = parse_corrispettivo_xml(xml)
    assert parsed["totale_iva"] == 0
    assert parsed["quadratura_iva_status"] == "NON_VERIFICABILE"
    doc = _build_corrispettivo_doc(parsed, "rt.xml", "documenti")
    assert doc["totale_cents"] == 10000
    assert doc["totale_iva_cents"] == 0
    assert doc["quadratura_iva_status"] == "NON_VERIFICABILE"


def test_handler_evento_corrispettivi_non_scrive_una_seconda_prima_nota():
    db = AsyncMongoMockClient().db
    result = _run(handler_prima_nota_corrispettivi(
        {"data": "2026-08-10", "totale": 100}, db,
    ))
    assert result["skipped"] is True
    assert result["prima_nota_scritti"] == 0
    assert _run(db.prima_nota_cassa.count_documents({})) == 0


def test_paypal_incrementale_usa_lease_atomico(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient().db
        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_sync(_db, start, end):
            started.set()
            await release.wait()
            return {"total": 0, "enriched": 0,
                    "period_start": start.isoformat(), "period_end": end.isoformat()}

        monkeypatch.setattr(paypal_api_sync, "sync_paypal_period", slow_sync)
        first = asyncio.create_task(paypal_api_sync.sync_paypal_incremental(db))
        await started.wait()
        second = await paypal_api_sync.sync_paypal_incremental(db)
        release.set()
        first_result = await first
        assert first_result["status"] == "updated"
        assert second["status"] == "already_running"

    _run(scenario())
