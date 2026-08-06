import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services.assegni_estratto_conto import (
    collega_assegno_riconciliato_a_fattura,
    collega_assegno_riconciliato_a_fatture,
    estrai_numero_assegno,
    sincronizza_assegni_da_estratto_conto,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _mov(numero="0208770981", importo=1853.02, idx=1):
    return {
        "id": f"ec-{idx}",
        "data": "2026-05-08",
        "data_pagamento": "2026-05-07",
        "importo": importo,  # schema canonico: valore assoluto
        "tipo": "uscita",
        "descrizione": (
            f"PRELIEVO ASSEGNO - DM 05387 CRA: 26050700167309 NUM: {numero}"
        ),
        "riconciliato": False,
    }


def test_numero_preserva_zero_iniziale_e_usa_num_non_cra():
    assert estrai_numero_assegno(_mov()["descrizione"]) == "0208770981"


def test_importo_assoluto_tipo_uscita_crea_assegno_e_prima_nota_idempotenti():
    async def scenario():
        db = AsyncMongoMockClient().db
        await db.estratto_conto_movimenti.insert_one(_mov())

        primo = await sincronizza_assegni_da_estratto_conto(db)
        secondo = await sincronizza_assegni_da_estratto_conto(db)

        assegno = await db.assegni.find_one({}, {"_id": 0})
        movimento = await db.estratto_conto_movimenti.find_one({"id": "ec-1"}, {"_id": 0})
        prima_nota = await db.prima_nota_banca.find_one({}, {"_id": 0})
        assert primo["assegni_creati"] == 1
        assert secondo["assegni_creati"] == 0
        assert await db.assegni.count_documents({}) == 1
        assert await db.prima_nota_banca.count_documents({}) == 1
        assert assegno["numero"] == "0208770981"
        assert assegno["stato"] == "incassato"
        assert assegno["incassato_confermato_banca"] is True
        assert movimento["riconciliato_con"] == "assegno"
        assert prima_nota["numero_assegno"] == "0208770981"
        assert prima_nota["riconciliato"] is True

    _run(scenario())


def test_quattro_assegni_da_tremila_chiudono_quattro_rate_non_il_totale_subito():
    async def scenario():
        db = AsyncMongoMockClient().db
        await db.invoices.insert_one({
            "id": "fatt-rata",
            "invoice_number": "TEST-RATE",
            "invoice_date": "2026-02-06",
            "supplier_vat": "00000000000",
            "supplier_name": "FORNITORE TEST SRL",
            "total_amount": 12000.0,
            "importo_pagato": 0.0,
            "importo_residuo": 12000.0,
            "payment_status": "open",
            "pagato": False,
            "pagamento_rate": [
                {"importo": "3000.00", "data_scadenza": f"2026-0{mese}-28"}
                for mese in range(2, 6)
            ],
        })
        for idx in range(1, 5):
            numero = f"02087709{idx:02d}"
            await db.assegni.insert_one({
                "id": f"ass-rata-{idx}",
                "numero": numero,
                "importo": 3000.0,
                "fattura_collegata": "fatt-rata",
                "stato": "emesso",
            })
            await db.estratto_conto_movimenti.insert_one(
                _mov(numero=numero, importo=3000.0, idx=idx)
            )

        esito = await sincronizza_assegni_da_estratto_conto(db)
        fattura = await db.invoices.find_one({"id": "fatt-rata"}, {"_id": 0})
        assert esito["fatture_associate"] == 4
        assert fattura["importo_pagato"] == 12000.0
        assert fattura["importo_residuo"] == 0.0
        assert fattura["payment_status"] == "paid"
        assert fattura["pagato"] is True
        assert len(fattura["assegni_collegati"]) == 4
        assert await db.prima_nota_banca.count_documents({}) == 4

    _run(scenario())


def test_importo_univoco_senza_numero_fattura_resta_proposta():
    async def scenario():
        db = AsyncMongoMockClient().db
        await db.invoices.insert_one({
            "id": "fatt-unica", "invoice_number": "TEST-UNICA",
            "invoice_date": "2026-04-01", "supplier_vat": "00000000001",
            "supplier_name": "FORNITORE TEST", "total_amount": 1853.02,
            "importo_pagato": 0.0, "payment_status": "open", "pagato": False,
        })
        await db.estratto_conto_movimenti.insert_one(_mov())

        esito = await sincronizza_assegni_da_estratto_conto(db)

        assert esito["fatture_associate"] == 0
        assert esito["proposte_ambigue"] == 1
        assert await db.invoices.count_documents({"pagato": True}) == 0
        proposta = await db.proposte_associazione_assegni.find_one({}, {"_id": 0})
        assert proposta["fattura_id"] == "fatt-unica"
        assert proposta["stato"] == "da_confermare"

    _run(scenario())


def test_sync_limitata_non_riesamina_gli_assegni_storici():
    async def scenario():
        db = AsyncMongoMockClient().db
        await db.estratto_conto_movimenti.insert_many([
            _mov(numero="0208770981", idx=1),
            _mov(numero="0208770982", idx=2),
        ])

        esito = await sincronizza_assegni_da_estratto_conto(
            db, movimento_ids=["ec-2", "ec-2"],
        )

        assert esito["ambito"] == "nuovi_movimenti"
        assert esito["movimenti_analizzati"] == 1
        assert await db.assegni.count_documents({"numero": "0208770982"}) == 1
        assert await db.assegni.count_documents({"numero": "0208770981"}) == 0
        storico = await db.estratto_conto_movimenti.find_one({"id": "ec-1"}, {"_id": 0})
        assert storico["riconciliato"] is False

    _run(scenario())


def test_importo_ambiguo_non_marca_fatture_pagata_e_salva_proposte():
    async def scenario():
        db = AsyncMongoMockClient().db
        for idx in (1, 2):
            await db.invoices.insert_one({
                "id": f"fatt-{idx}", "invoice_number": f"TEST-{idx}",
                "invoice_date": "2026-04-01", "supplier_vat": f"0000000000{idx}",
                "supplier_name": f"FORNITORE TEST {idx}", "total_amount": 1853.02,
                "importo_pagato": 0.0, "payment_status": "open", "pagato": False,
            })
        await db.estratto_conto_movimenti.insert_one(_mov())

        esito = await sincronizza_assegni_da_estratto_conto(db)
        assert esito["fatture_associate"] == 0
        assert esito["proposte_ambigue"] == 2
        assert await db.proposte_associazione_assegni.count_documents({"stato": "da_confermare"}) == 2
        assert await db.invoices.count_documents({"pagato": True}) == 0

    _run(scenario())


def test_assegno_gia_presente_viene_riscontrato_invece_di_essere_saltato():
    async def scenario():
        db = AsyncMongoMockClient().db
        await db.assegni.insert_one({
            "id": "ass-esistente", "numero": "0208770981", "importo": 1853.02,
            "stato": "emesso", "beneficiario": "FORNITORE TEST",
        })
        await db.estratto_conto_movimenti.insert_one(_mov())

        esito = await sincronizza_assegni_da_estratto_conto(db)
        assegno = await db.assegni.find_one({"id": "ass-esistente"}, {"_id": 0})
        assert esito["assegni_esistenti"] == 1
        assert esito["assegni_creati"] == 0
        assert assegno["stato"] == "incassato"
        assert assegno["movimento_estratto_conto_id"] == "ec-1"

    _run(scenario())


def test_due_assegni_uguali_restano_distinti_e_chiudono_due_rate():
    async def scenario():
        db = AsyncMongoMockClient().db
        await db.invoices.insert_one({
            "id": "fatt-due-rate", "invoice_number": "F-9760",
            "invoice_date": "2026-05-15", "supplier_vat": "00000000001",
            "supplier_name": "FORNITORE DUE RATE", "total_amount": 19520.0,
            "importo_pagato": 0.0, "importo_residuo": 19520.0,
            "payment_status": "open", "pagato": False,
            "pagamento_rate": [
                {"importo": "9760.00", "data_scadenza": "2026-06-30"},
                {"importo": "9760.00", "data_scadenza": "2026-07-31"},
            ],
        })
        await db.estratto_conto_movimenti.insert_many([
            _mov(numero="0208770985", importo=9760.0, idx=85),
            _mov(numero="0208770986", importo=9760.0, idx=86),
        ])

        esito = await sincronizza_assegni_da_estratto_conto(db)
        assert esito["fatture_associate"] == 0
        assert esito["proposte_ambigue"] == 2

        for numero in ("0208770985", "0208770986"):
            assegno = await db.assegni.find_one({"numero": numero}, {"_id": 0})
            fattura = await db.invoices.find_one({"id": "fatt-due-rate"}, {"_id": 0})
            await collega_assegno_riconciliato_a_fattura(db, assegno, fattura)

        fattura = await db.invoices.find_one({"id": "fatt-due-rate"}, {"_id": 0})
        assert fattura["importo_pagato"] == 19520.0
        assert fattura["importo_residuo"] == 0.0
        assert fattura["payment_status"] == "paid"
        assert {link["numero"] for link in fattura["assegni_collegati"]} == {
            "0208770985", "0208770986",
        }
        assert await db.prima_nota_banca.count_documents({}) == 2
        assert await db.proposte_associazione_assegni.count_documents({"stato": "confermata"}) == 2

    _run(scenario())


def test_assegno_gia_in_banca_puo_chiudere_due_fatture_senza_due_righe_banca():
    async def scenario():
        db = AsyncMongoMockClient().db
        assegno = {
            "id": "ass-multi", "numero": "0208770985", "importo": 9760.0,
            "incassato_confermato_banca": True,
            "movimento_estratto_conto_id": "ec-multi", "stato": "incassato",
        }
        await db.assegni.insert_one(assegno)
        await db.estratto_conto_movimenti.insert_one(
            _mov(numero="0208770985", importo=9760.0, idx="multi")
        )
        await db.estratto_conto_movimenti.update_one(
            {"id": "ec-multi"}, {"$set": {"id": "ec-multi"}}, upsert=True,
        )
        fatture = [
            {"id": "fatt-a", "invoice_number": "A-1", "supplier_vat": "00000000001",
             "supplier_name": "FORNITORE TEST", "total_amount": 4000.0,
             "importo_pagato": 0.0, "pagato": False,
             "assegni_collegati": [{"assegno_id": "ass-multi", "quota": 4000.0, "banca_confermata": False}]},
            {"id": "fatt-b", "invoice_number": "B-2", "supplier_vat": "00000000001",
             "supplier_name": "FORNITORE TEST", "total_amount": 5760.0,
             "importo_pagato": 0.0, "pagato": False,
             "assegni_collegati": [{"assegno_id": "ass-multi", "quota": 5760.0, "banca_confermata": False}]},
        ]
        await db.invoices.insert_many(fatture)

        esito = await collega_assegno_riconciliato_a_fatture(db, assegno, [
            {"fattura": fatture[0], "quota": 4000.0},
            {"fattura": fatture[1], "quota": 5760.0},
        ])

        assert esito["quote_applicate"] == 2
        assert esito["fattura_id"] is None
        assert esito["fattura_ids"] == ["fatt-a", "fatt-b"]
        assert await db.prima_nota_banca.count_documents({}) == 1
        riga = await db.prima_nota_banca.find_one({}, {"_id": 0})
        assert riga["fattura_ids"] == ["fatt-a", "fatt-b"]
        assert (await db.invoices.find_one({"id": "fatt-a"}))["pagato"] is True
        assert (await db.invoices.find_one({"id": "fatt-b"}))["pagato"] is True

    _run(scenario())
