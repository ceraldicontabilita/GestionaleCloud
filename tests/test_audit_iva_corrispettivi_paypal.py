import asyncio
from datetime import date

from mongomock_motor import AsyncMongoMockClient

from app.handlers.corrispettivi import handler_prima_nota_corrispettivi
from app.parsers.corrispettivi_parser import parse_corrispettivo_xml
from app.routers.invoices.corrispettivi_helpers import _build_corrispettivo_doc
from app.services.fiscal_deadlines import monthly_deadline
from app.services.iva_liquidation_query import get_iva_period_snapshot
from app.services import paypal_api_sync
from app.services.verifica_coerenza import VerificaCoerenza
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
            "stato_calcolo": "CALCOLATO" if calculated else "NON_CALCOLATO",
            "fonte_calcolo": "test",
            "scadenza_nominale": f"2026-{mese:02d}-16",
            "scadenza_legale": f"2026-{mese:02d}-16",
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
    assert result["mensile"][1]["stato_calcolo"] == "NON_CALCOLATO"
    assert result["totali"]["iva_credito_totale_cents"] == 1000
    assert result["totali"]["iva_debito_totale_cents"] == 2000
    assert result["totali"]["periodi_calcolati"] == 1


def test_confronto_iva_include_tutte_le_fatture_indipendentemente_dal_pagamento():
    async def scenario():
        db = AsyncMongoMockClient().db
        base = {
            "periodo_iva_attribuito": "2026-07",
            "iva_detraibile": 100.0,
            "tipo_documento": "TD01",
            "stato_detrazione_iva": "DA_INSERIRE",
        }
        await db.invoices.insert_many([
            {**base, "id": "cassa", "metodo_pagamento": "cassa", "pagata": True},
            {**base, "id": "banca", "metodo_pagamento": "banca", "pagata": True},
            {**base, "id": "aperta", "stato_pagamento": "da_pagare"},
            {
                **base,
                "id": "gia-liquidata",
                "iva_utilizzata": True,
                "periodo_iva_utilizzato": "2026-07",
                "stato_detrazione_iva": "INSERITA_IN_LIQUIDAZIONE",
            },
        ])

        snapshot = await get_iva_period_snapshot(
            db, anno=2026, mese=7, today=date(2026, 8, 11),
        )
        credito = await VerificaCoerenza(db).verifica_iva_credito_mensile(2026, 7)

        assert snapshot["conteggi"]["fatture_periodo_attribuito"] == 4
        assert snapshot["conteggi"]["fatture_incluse_competenza"] == 4
        assert snapshot["conteggi"]["fatture_gia_utilizzate"] == 1
        assert snapshot["iva_acquisti_competenza_cents"] == 40000
        assert snapshot["iva_acquisti_disponibile_cents"] == 30000
        assert credito["iva_credito_fatture_cents"] == 40000
        assert credito["num_fatture"] == 4

    _run(scenario())


def test_confronto_iva_non_scambia_liquidazione_confermata_con_competenza_corrente():
    async def scenario():
        db = AsyncMongoMockClient().db
        await db.invoices.insert_many([
            {
                "id": "storica-1", "periodo_iva_attribuito": "2026-06",
                "iva_detraibile": 220.0, "iva_utilizzata": True,
                "periodo_iva_utilizzato": "2026-06",
                "stato_detrazione_iva": "INSERITA_IN_LIQUIDAZIONE",
            },
            {
                "id": "importata-dopo", "periodo_iva_attribuito": "2026-06",
                "iva_detraibile": 80.0, "iva_utilizzata": False,
                "stato_detrazione_iva": "DA_INSERIRE",
            },
        ])
        await db.liquidazioni_iva.insert_one({
            "id": "liq-giugno", "periodo": "2026-06", "versione": 1,
            "stato": "CONFERMATA", "iva_vendite": 500.0,
            "iva_acquisti": 220.0, "credito_precedente": 0.0, "saldo": 280.0,
        })

        snapshot = await get_iva_period_snapshot(
            db, anno=2026, mese=6, today=date(2026, 8, 11),
        )

        assert snapshot["iva_acquisti"] == 220.0
        assert snapshot["fonte"] == "liquidazione_confermata"
        assert snapshot["iva_acquisti_competenza"] == 300.0

    _run(scenario())


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
