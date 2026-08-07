import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services import riconciliazione_bancaria as mod


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _noop(*args, **kwargs):
    return None


def _fattura(fid, numero, importo):
    return {
        "id": fid,
        "invoice_number": numero,
        "invoice_date": "2026-03-01",
        "supplier_vat": "01234567890",
        "supplier_name": "FORNITORE MULTI SRL",
        "total_amount": importo,
        "importo_pagato": 0.0,
        "importo_residuo": importo,
        "pagato": False,
        "stato_pagamento": "aperta",
    }


def _prepara_db(monkeypatch, importo_movimento):
    db = AsyncMongoMockClient()["test_multi_fattura_causale"]
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(mod, "_propaga_fattura_pagata", _noop)
    monkeypatch.setattr(mod, "_registra_match_partita_aperta", _noop)
    monkeypatch.setattr(mod, "_alert_match_ambiguo", _noop)
    return db


def test_bonifico_con_due_numeri_ripartisce_due_fatture(monkeypatch):
    async def scenario():
        db = _prepara_db(monkeypatch, 300.0)
        await db.invoices.insert_many([
            _fattura("fatt-101", "FT-101/26", 100.0),
            _fattura("fatt-102", "FT-102/26", 200.0),
        ])
        await db.estratto_conto_movimenti.insert_one({
            "id": "ec-multi-ok",
            "data": "2026-03-20",
            "tipo": "uscita",
            "importo": -300.0,
            "descrizione_originale": (
                "BONIFICO FORNITORE MULTI SRL PAGAMENTO FATTURE "
                "FT-101/26 E FT-102/26"
            ),
            "riconciliato": False,
        })

        risultato = await mod.riconcilia_movimenti_banca()

        assert risultato["riconciliati_fatture"] == 1
        assert risultato["riconciliati_movimenti_multi_fattura"] == 1
        assert risultato["fatture_ripartite_multi"] == 2
        assert risultato["dubbi"] == 0

        fatture = await db.invoices.find({}, {"_id": 0}).sort("id", 1).to_list(10)
        assert [fattura["pagato"] for fattura in fatture] == [True, True]
        assert [fattura["importo_residuo"] for fattura in fatture] == [0.0, 0.0]

        movimenti_banca = await db.prima_nota_banca.find(
            {}, {"_id": 0}
        ).sort("importo", 1).to_list(10)
        assert len(movimenti_banca) == 2
        assert [movimento["importo"] for movimento in movimenti_banca] == [100.0, 200.0]
        assert {
            movimento["movimento_estratto_conto_id"] for movimento in movimenti_banca
        } == {"ec-multi-ok"}
        assert {
            movimento["invoice_id"] for movimento in movimenti_banca
        } == {"fatt-101", "fatt-102"}

        ec = await db.estratto_conto_movimenti.find_one(
            {"id": "ec-multi-ok"}, {"_id": 0}
        )
        assert ec["riconciliato"] is True
        assert ec["tipo_riconciliazione"] == "fatture_multiple_causale"
        assert ec["dettagli_riconciliazione"]["importo_ripartito"] == 300.0
        assert len(ec["dettagli_riconciliazione"]["fatture"]) == 2

    _run(scenario())


def test_bonifico_multi_con_somma_diversa_resta_da_confermare(monkeypatch):
    async def scenario():
        db = _prepara_db(monkeypatch, 250.0)
        await db.invoices.insert_many([
            _fattura("fatt-201", "FT-201/26", 100.0),
            _fattura("fatt-202", "FT-202/26", 200.0),
        ])
        await db.estratto_conto_movimenti.insert_one({
            "id": "ec-multi-dubbio",
            "data": "2026-03-20",
            "tipo": "uscita",
            "importo": -250.0,
            "descrizione_originale": (
                "BONIFICO FORNITORE MULTI SRL PAGAMENTO FATTURE "
                "FT-201/26 E FT-202/26"
            ),
            "riconciliato": False,
        })

        risultato = await mod.riconcilia_movimenti_banca()

        assert risultato["riconciliati_fatture"] == 0
        assert risultato["dubbi"] == 1
        assert risultato["non_trovati"] == 0
        assert await db.prima_nota_banca.count_documents({}) == 0
        assert await db.invoices.count_documents({"pagato": True}) == 0

        ec = await db.estratto_conto_movimenti.find_one(
            {"id": "ec-multi-dubbio"}, {"_id": 0}
        )
        assert ec["riconciliato"] is False

        proposta = await db.operazioni_da_confermare.find_one(
            {"movimento_ec_id": "ec-multi-dubbio"}, {"_id": 0}
        )
        assert proposta["match_type"] == "fatture_multiple_causale"
        assert proposta["dettagli"]["somma_residui"] == 300.0
        assert proposta["dettagli"]["differenza"] == -50.0
        assert len(proposta["dettagli"]["fatture_candidate"]) == 2

    _run(scenario())


def test_numero_fattura_lungo_con_zeri_viene_riconosciuto_nella_causale():
    assert mod._numero_fattura_citato_esplicitamente(
        "000000000001855/01",
        "BONIFICO PAGAMENTO FATTURE 1855/01 E 1856/01",
    )
    assert not mod._numero_fattura_citato_esplicitamente(
        "12",
        "BONIFICO DEL 12 MARZO 2026",
    )


def test_numero_composito_accetta_solo_progressivo_finale_documentale():
    assert mod._numero_fattura_citato_esplicitamente(
        "V1-2026-007590",
        "S. PASSALACQUA S.P.A. - fattura 7590",
    )
    assert not mod._numero_fattura_citato_esplicitamente(
        "V1-2026-007590",
        "CRO 7590 PAGAMENTO GENERICO",
    )


def test_bonifico_non_si_chiude_se_la_causale_cita_una_fattura_non_importata(monkeypatch):
    async def scenario():
        db = _prepara_db(monkeypatch, 300.0)
        await db.invoices.insert_many([
            _fattura("fatt-301", "FT-301/26", 100.0),
            _fattura("fatt-302", "FT-302/26", 200.0),
        ])
        await db.estratto_conto_movimenti.insert_one({
            "id": "ec-multi-manca-doc",
            "data": "2026-03-20",
            "tipo": "uscita",
            "importo": -300.0,
            "descrizione_originale": (
                "BONIFICO FORNITORE MULTI SRL PAGAMENTO FATTURE "
                "FT-301/26 FT-302/26 FT-303/26"
            ),
            "riconciliato": False,
        })

        risultato = await mod.riconcilia_movimenti_banca()
        assert risultato["riconciliati_fatture"] == 0
        proposta = await db.operazioni_da_confermare.find_one(
            {"movimento_ec_id": "ec-multi-manca-doc"}, {"_id": 0}
        )
        assert proposta["dettagli"]["riferimenti_mancanti"] == ["FT30326"]
        assert await db.prima_nota_banca.count_documents({}) == 0

    _run(scenario())


def test_import_riconcilia_solo_i_nuovi_movimenti_richiesti(monkeypatch):
    async def scenario():
        db = _prepara_db(monkeypatch, 1.0)
        await db.estratto_conto_movimenti.insert_many([
            {
                "id": "ec-nuovo",
                "data": "2026-08-05",
                "tipo": "uscita",
                "importo": -1.0,
                "descrizione_originale": "COMMISSIONE BANCARIA",
                "riconciliato": False,
            },
            {
                "id": "ec-storico",
                "data": "2026-01-05",
                "tipo": "uscita",
                "importo": -1.0,
                "descrizione_originale": "COMMISSIONE BANCARIA",
                "riconciliato": False,
            },
        ])

        risultato = await mod.riconcilia_movimenti_banca(
            movimento_ids=["ec-nuovo", "ec-nuovo"],
        )

        assert risultato["ambito"] == "nuovi_movimenti"
        assert risultato["movimenti_analizzati"] == 1
        assert risultato["commissioni_ignorate"] == 1
        assert await db.estratto_conto_movimenti.count_documents({
            "id": "ec-nuovo", "riconciliato": True,
        }) == 1
        assert await db.estratto_conto_movimenti.count_documents({
            "id": "ec-storico", "riconciliato": False,
        }) == 1

    _run(scenario())


def test_scope_vuoto_non_avvia_una_scansione_completa(monkeypatch):
    async def scenario():
        db = _prepara_db(monkeypatch, 1.0)
        await db.estratto_conto_movimenti.insert_one({
            "id": "ec-storico",
            "data": "2026-01-05",
            "tipo": "uscita",
            "importo": -1.0,
            "descrizione_originale": "COMMISSIONE BANCARIA",
            "riconciliato": False,
        })

        risultato = await mod.riconcilia_movimenti_banca(movimento_ids=[])

        assert risultato["ambito"] == "nuovi_movimenti"
        assert risultato["movimenti_analizzati"] == 0
        assert await db.estratto_conto_movimenti.count_documents({
            "id": "ec-storico", "riconciliato": False,
        }) == 1

    _run(scenario())
