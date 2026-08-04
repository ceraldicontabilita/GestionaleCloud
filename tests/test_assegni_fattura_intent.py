import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services.assegni_estratto_conto import sincronizza_assegni_da_estratto_conto
from app.services.assegni_fattura_intent import (
    collega_intento_assegno_a_fattura,
    prepara_intento_assegno,
)


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
