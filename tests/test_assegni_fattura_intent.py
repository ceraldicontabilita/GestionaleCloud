import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services.assegni_estratto_conto import sincronizza_assegni_da_estratto_conto
from app.services.assegni_fattura_intent import (
    collega_intento_assegno_a_fattura,
    prepara_intento_assegno,
)
from app.routers.bank import assegni as assegni_router


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_assegno_compilato_prevale_su_fornitore_cassa_e_attende_estratto():
    async def scenario():
        db = AsyncMongoMockClient()["assegno_intento_cassa"]
        await db.assegni.insert_one({
            "id": "ass-1", "numero": "0208770981", "importo": 267.02,
            "beneficiario": "TOP SPINA SRL UNIPERSONALE",
            "fornitore_piva": "01234567890", "numero_fattura": "1855/01",
            "stato": "compilato",
        })

        attesa = await prepara_intento_assegno(db, "ass-1")
        assert attesa == {
            "registrato": True, "collegato": False, "motivo": "in_attesa_xml"
        }

        invoice = {
            "id": "fatt-1", "invoice_number": "1855/01",
            "invoice_date": "2026-03-31", "supplier_vat": "01234567890",
            "supplier_name": "TOP SPINA s.r.l. unipersonale",
            "total_amount": 267.02, "metodo_pagamento": "cassa",
            "payment_status": "open", "pagato": False,
        }
        await db.invoices.insert_one(dict(invoice))
        esito = await collega_intento_assegno_a_fattura(db, invoice)

        salvata = await db.invoices.find_one({"id": "fatt-1"}, {"_id": 0})
        assert esito["collegato"] is True
        assert salvata["metodo_pagamento_fornitore_originale"] == "cassa"
        assert salvata["metodo_pagamento_previsto"] == "assegno"
        assert salvata["stato_finanziario"] == "in_attesa_estratto_conto"
        assert salvata["pagato"] is False
        assert salvata["riconciliato_con_ec"] is False
        assert await db.prima_nota_banca.count_documents({}) == 0

    _run(scenario())


def test_estratto_conto_chiude_il_ciclo_e_imposta_flag_riconciliato():
    async def scenario():
        db = AsyncMongoMockClient()["assegno_intento_ec"]
        await db.assegni.insert_one({
            "id": "ass-2", "numero": "0208770981", "importo": 267.02,
            "beneficiario": "TOP SPINA SRL UNIPERSONALE",
            "fornitore_piva": "01234567890", "numero_fattura": "1855/01",
            "stato": "compilato",
        })
        invoice = {
            "id": "fatt-2", "invoice_number": "1855/01",
            "invoice_date": "2026-03-31", "supplier_vat": "01234567890",
            "supplier_name": "TOP SPINA s.r.l. unipersonale",
            "total_amount": 267.02, "metodo_pagamento": "misto",
            "payment_status": "open", "pagato": False,
        }
        await db.invoices.insert_one(dict(invoice))
        await collega_intento_assegno_a_fattura(db, invoice)
        await db.estratto_conto_movimenti.insert_one({
            "id": "ec-assegno-2", "data": "2026-04-08", "importo": 267.02,
            "tipo": "uscita",
            "descrizione": "PRELIEVO ASSEGNO NUM: 0208770981",
            "riconciliato": False,
        })

        esito = await sincronizza_assegni_da_estratto_conto(db)
        salvata = await db.invoices.find_one({"id": "fatt-2"}, {"_id": 0})
        assegno = await db.assegni.find_one({"id": "ass-2"}, {"_id": 0})

        assert esito["assegni_riconciliati"] == 1
        assert salvata["pagato"] is True
        assert salvata["riconciliato_con_ec"] is True
        assert salvata["stato_finanziario"] == "riconciliato"
        assert salvata["movimento_bancario_id"] == "ec-assegno-2"
        assert assegno["incassato_confermato_banca"] is True
        assert await db.prima_nota_banca.count_documents({"riconciliato": True}) == 1

    _run(scenario())


def test_non_collega_una_fattura_storica_di_un_altro_anno():
    async def scenario():
        db = AsyncMongoMockClient()["assegno_intento_anno"]
        await db.assegni.insert_one({
            "id": "ass-2026", "numero": "0208770999", "anno": 2026,
            "importo": 267.02, "beneficiario": "TOP SPINA SRL",
            "fornitore_piva": "01234567890", "numero_fattura": "1855/01",
            "stato": "compilato",
        })
        invoice = {
            "id": "fatt-2019", "invoice_number": "1855/01", "anno": 2019,
            "invoice_date": "2019-03-31", "supplier_vat": "01234567890",
            "supplier_name": "TOP SPINA SRL", "total_amount": 267.02,
            "pagato": False,
        }
        await db.invoices.insert_one(dict(invoice))

        esito = await collega_intento_assegno_a_fattura(db, invoice)
        assert esito == {"collegato": False, "motivo": "nessun_intento_compatibile"}
        assert await db.invoices.count_documents({"metodo_pagamento_previsto": "assegno"}) == 0

    _run(scenario())


def test_estratto_arriva_prima_della_fattura_e_xml_completa_tutto_senza_modale():
    async def scenario():
        db = AsyncMongoMockClient()["assegno_ec_prima_xml"]
        await db.assegni.insert_one({
            "id": "ass-ec-prima", "numero": "0208770649", "importo": 977.38,
            "beneficiario": "FORNITORE AUTOMATICO SRL",
            "fornitore_piva": "09999999999", "numero_fattura": "FA-649",
            "stato": "compilato", "anno": 2026,
        })
        await db.estratto_conto_movimenti.insert_one({
            "id": "ec-prima-xml", "data": "2026-04-10", "importo": 977.38,
            "tipo": "uscita", "descrizione": "PRELIEVO ASSEGNO NUM: 0208770649",
            "riconciliato": False,
        })

        prima = await sincronizza_assegni_da_estratto_conto(db)
        assegno_in_banca = await db.assegni.find_one(
            {"id": "ass-ec-prima"}, {"_id": 0}
        )
        assert prima["assegni_riconciliati"] == 1
        assert assegno_in_banca["stato"] == "incassato"
        assert assegno_in_banca["incassato_confermato_banca"] is True
        assert assegno_in_banca.get("fattura_id") is None

        invoice = {
            "id": "fatt-ec-prima", "invoice_number": "FA-649",
            "invoice_date": "2026-03-31", "supplier_vat": "09999999999",
            "supplier_name": "FORNITORE AUTOMATICO SRL", "total_amount": 977.38,
            "importo_pagato": 0.0, "importo_residuo": 977.38,
            "payment_status": "open", "pagato": False,
        }
        await db.invoices.insert_one(dict(invoice))
        esito = await collega_intento_assegno_a_fattura(db, invoice)

        fattura = await db.invoices.find_one({"id": "fatt-ec-prima"}, {"_id": 0})
        assegno = await db.assegni.find_one({"id": "ass-ec-prima"}, {"_id": 0})
        movimento = await db.estratto_conto_movimenti.find_one(
            {"id": "ec-prima-xml"}, {"_id": 0}
        )
        assert esito["collegato"] is True
        assert fattura["pagato"] is True
        assert fattura["riconciliato_con_ec"] is True
        assert assegno["stato"] == "incassato"
        assert assegno["fattura_id"] == "fatt-ec-prima"
        assert assegno["match_auto"] is True
        assert assegno["match_livello"] == "INTENTO_ASSEGNO_XML_EC"
        assert movimento["fattura_id"] == "fatt-ec-prima"
        assert await db.prima_nota_banca.count_documents({}) == 1

    _run(scenario())


def test_numero_fattura_e_importo_univoci_collegano_anche_senza_beneficiario():
    async def scenario():
        db = AsyncMongoMockClient()["assegno_numero_importo"]
        await db.assegni.insert_one({
            "id": "ass-solo-numero",
            "numero": "0208770650",
            "importo": 123.45,
            "numero_fattura": "FPR-77/26",
            "stato": "vuoto",
            "anno": 2026,
        })
        await db.invoices.insert_one({
            "id": "fatt-solo-numero",
            "invoice_number": "FPR-77/26",
            "invoice_date": "2026-05-10",
            "supplier_vat": "01111111111",
            "supplier_name": "FORNITORE DA FATTURA SRL",
            "total_amount": 123.45,
            "payment_status": "open",
            "pagato": False,
        })

        esito = await prepara_intento_assegno(db, "ass-solo-numero")
        assegno = await db.assegni.find_one(
            {"id": "ass-solo-numero"}, {"_id": 0}
        )

        assert esito["collegato"] is True
        assert assegno["fattura_id"] == "fatt-solo-numero"
        assert assegno["beneficiario"] == "FORNITORE DA FATTURA SRL"
        assert assegno["stato_finanziario"] == "in_attesa_estratto_conto"

    _run(scenario())


def test_numero_fattura_e_importo_duplicati_restano_ambigui():
    async def scenario():
        db = AsyncMongoMockClient()["assegno_numero_ambiguo"]
        await db.assegni.insert_one({
            "id": "ass-ambiguo",
            "numero": "0208770651",
            "importo": 90.00,
            "numero_fattura": "12",
            "stato": "compilato",
            "anno": 2026,
        })
        await db.invoices.insert_many([
            {
                "id": "fatt-a",
                "invoice_number": "12",
                "invoice_date": "2026-01-10",
                "supplier_vat": "01111111111",
                "supplier_name": "FORNITORE A",
                "total_amount": 90.00,
                "pagato": False,
            },
            {
                "id": "fatt-b",
                "invoice_number": "12",
                "invoice_date": "2026-02-10",
                "supplier_vat": "02222222222",
                "supplier_name": "FORNITORE B",
                "total_amount": 90.00,
                "pagato": False,
            },
        ])

        esito = await prepara_intento_assegno(db, "ass-ambiguo")
        assegno = await db.assegni.find_one({"id": "ass-ambiguo"}, {"_id": 0})
        proposte = await db.proposte_associazione_assegni.find(
            {"assegno_id": "ass-ambiguo", "stato": "da_confermare"},
            {"_id": 0},
        ).to_list(10)

        assert esito == {
            "registrato": True,
            "collegato": False,
            "motivo": "ambiguo",
            "candidati": 2,
        }
        assert assegno.get("fattura_id") is None
        assert {p["fattura_id"] for p in proposte} == {"fatt-a", "fatt-b"}

    _run(scenario())


def test_modifica_anagrafica_non_degrada_un_assegno_incassato(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["assegno_incassato_protetto"]
        await db.assegni.insert_one({
            "id": "ass-incassato",
            "numero": "0208770652",
            "importo": 50.00,
            "stato": "incassato",
            "incassato_confermato_banca": True,
            "movimento_estratto_conto_id": "ec-52",
        })
        monkeypatch.setattr(
            assegni_router.Database,
            "get_db",
            staticmethod(lambda: db),
        )
        esito = await assegni_router.update_assegno(
            "0208770652",
            {
                "numero_fattura": "F-52",
                "importo": 50.00,
                "stato": "vuoto",
            },
        )
        assegno = await db.assegni.find_one(
            {"id": "ass-incassato"}, {"_id": 0}
        )
        return esito, assegno

    esito, assegno = _run(scenario())
    assert assegno["stato"] == "incassato"
    assert assegno["numero_fattura"] == "F-52"
    assert esito["intento_fattura"]["registrato"] is True
    assert esito["intento_fattura"]["motivo"] == "in_attesa_xml"
