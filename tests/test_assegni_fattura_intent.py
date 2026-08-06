import asyncio

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.services.assegni_estratto_conto import (
    _collega_fattura_univoca,
    sincronizza_assegni_da_estratto_conto,
)
from app.services.assegni_fattura_intent import (
    collega_intento_assegno_a_fattura,
    prepara_intento_assegno,
    riprocessa_intenti_assegni,
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


def test_due_assegni_distinti_non_possono_saldare_due_volte_la_stessa_fattura():
    async def scenario():
        db = AsyncMongoMockClient()["assegno_no_doppio_pagamento"]
        invoice = {
            "id": "fatt-unica", "invoice_number": "56/D",
            "total_amount": 646.72, "importo_pagato": 0.0,
            "payment_status": "open", "pagato": False,
        }
        await db.invoices.insert_one(dict(invoice))
        primo = {"id": "ass-1", "numero": "0208770988", "importo": 646.72}
        secondo = {"id": "ass-2", "numero": "0208770864", "importo": 646.72}

        assert await _collega_fattura_univoca(
            db, primo, invoice, "2026-05-15", "2026-08-06T10:00:00+00:00"
        ) is True
        aggiornata = await db.invoices.find_one({"id": "fatt-unica"}, {"_id": 0})
        assert await _collega_fattura_univoca(
            db, secondo, aggiornata, "2026-04-27", "2026-08-06T10:01:00+00:00"
        ) is False

        finale = await db.invoices.find_one({"id": "fatt-unica"}, {"_id": 0})
        assert finale["importo_pagato"] == 646.72
        assert len(finale["assegni_collegati"]) == 1
        assert finale["assegni_collegati"][0]["assegno_id"] == "ass-1"

    _run(scenario())


def test_due_rate_con_assegni_diversi_sono_ammesse_entro_totale():
    async def scenario():
        db = AsyncMongoMockClient()["assegno_rate_valide"]
        invoice = {
            "id": "fatt-rate", "invoice_number": "R-200",
            "total_amount": 200.0, "importo_pagato": 0.0,
            "payment_status": "open", "pagato": False,
        }
        await db.invoices.insert_one(dict(invoice))
        primo = {"id": "ass-r1", "numero": "0208770101", "importo": 100.0}
        secondo = {"id": "ass-r2", "numero": "0208770102", "importo": 100.0}

        assert await _collega_fattura_univoca(
            db, primo, invoice, "2026-06-01", "2026-08-06T10:00:00+00:00"
        ) is True
        aggiornata = await db.invoices.find_one({"id": "fatt-rate"}, {"_id": 0})
        assert await _collega_fattura_univoca(
            db, secondo, aggiornata, "2026-07-01", "2026-08-06T10:01:00+00:00"
        ) is True

        finale = await db.invoices.find_one({"id": "fatt-rate"}, {"_id": 0})
        assert finale["importo_pagato"] == 200.0
        assert finale["pagato"] is True
        assert {l["assegno_id"] for l in finale["assegni_collegati"]} == {"ass-r1", "ass-r2"}

    _run(scenario())


def test_lista_segnala_sovra_attribuzione_storica_senza_modificare_dati(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["assegno_conflitto_storico"]
        await db.invoices.insert_one({
            "id": "fatt-conflitto", "invoice_number": "56/D",
            "supplier_name": "EUREKA ONLUS", "invoice_date": "2026-07-07",
            "total_amount": 646.72,
            "assegni_collegati": [
                {"assegno_id": "ass-a", "quota": 646.72, "banca_confermata": True},
                {"assegno_id": "ass-b", "quota": 646.72, "banca_confermata": True},
            ],
        })
        for aid, numero in (("ass-a", "0208770988"), ("ass-b", "0208770864")):
            await db.assegni.insert_one({
                "id": aid, "numero": numero, "anno": 2026,
                "data_incasso": "2026-05-15", "importo": 646.72,
                "stato": "incassato", "fattura_id": "fatt-conflitto",
                "fattura_collegata": "fatt-conflitto",
                "fatture_collegate": [{"fattura_id": "fatt-conflitto", "quota": 646.72}],
            })
        monkeypatch.setattr(assegni_router.Database, "get_db", staticmethod(lambda: db))

        righe = await assegni_router.list_assegni(
            skip=0, limit=1000, stato=None, fornitore_piva=None,
            search=None, anno=2026,
        )
        salvata = await db.invoices.find_one({"id": "fatt-conflitto"}, {"_id": 0})
        return righe, salvata

    righe, salvata = _run(scenario())
    assert len(righe) == 2
    assert all(r["associazione_conflittuale"] is True for r in righe)
    assert all(r["fatture_conflittuali"][0]["importo_attribuito"] == 1293.44 for r in righe)
    assert len(salvata["assegni_collegati"]) == 2


def test_endpoint_legacy_non_puo_sovrascrivere_una_fattura_gia_attribuita(monkeypatch):
    async def scenario():
        db = AsyncMongoMockClient()["assegno_endpoint_protetto"]
        await db.assegni.insert_one({
            "id": "ass-nuovo", "numero": "0208770990", "importo": 120.0,
            "stato": "incassato", "incassato_confermato_banca": True,
        })
        await db.invoices.insert_one({
            "id": "fatt-protetta", "invoice_number": "F-120",
            "total_amount": 120.0, "importo_residuo": 0.0,
            "importo_pagato": 120.0, "pagato": True,
            "assegni_collegati": [{
                "assegno_id": "ass-vecchio", "quota": 120.0,
                "banca_confermata": True,
            }],
        })
        monkeypatch.setattr(assegni_router.Database, "get_db", staticmethod(lambda: db))

        with pytest.raises(HTTPException) as errore:
            await assegni_router.collega_fatture_assegno(
                "ass-nuovo",
                assegni_router.FattureCollegateIn(fatture=[
                    assegni_router.FatturaQuotaIn(
                        fattura_id="fatt-protetta", quota=120.0,
                    )
                ]),
            )
        salvata = await db.invoices.find_one({"id": "fatt-protetta"}, {"_id": 0})
        return errore.value, salvata

    errore, salvata = _run(scenario())
    assert errore.status_code == 409
    assert "gia attribuita" in errore.detail
    assert len(salvata["assegni_collegati"]) == 1
    assert salvata["assegni_collegati"][0]["assegno_id"] == "ass-vecchio"


def test_riprocessamento_storico_collega_assegno_incassato_alla_fattura_univoca():
    async def scenario():
        db = AsyncMongoMockClient()["assegno_riprocessamento_storico"]
        await db.assegni.insert_one({
            "id": "ass-storico", "numero": "0208770649", "anno": 2026,
            "importo": 977.38, "beneficiario": "FORNITORE AUTOMATICO SRL",
            "fornitore_piva": "09999999999", "numero_fattura": "FA-649",
            "stato": "incassato", "incassato_confermato_banca": True,
            "movimento_estratto_conto_id": "ec-storico",
            "data_incasso": "2026-04-10",
        })
        await db.estratto_conto_movimenti.insert_one({
            "id": "ec-storico", "data": "2026-04-10", "importo": 977.38,
            "tipo": "uscita", "descrizione": "ASSEGNO N. 0208770649",
            "riconciliato": True, "assegno_id": "ass-storico",
        })
        await db.invoices.insert_one({
            "id": "fatt-storica", "invoice_number": "FA-649", "anno": 2026,
            "invoice_date": "2026-03-31", "supplier_vat": "09999999999",
            "supplier_name": "FORNITORE AUTOMATICO SRL", "total_amount": 977.38,
            "importo_pagato": 0.0, "importo_residuo": 977.38,
            "payment_status": "open", "pagato": False,
        })

        esito = await riprocessa_intenti_assegni(db, anno=2026)
        assegno = await db.assegni.find_one({"id": "ass-storico"}, {"_id": 0})
        fattura = await db.invoices.find_one({"id": "fatt-storica"}, {"_id": 0})
        return esito, assegno, fattura

    esito, assegno, fattura = _run(scenario())
    assert esito["analizzati"] == 1
    assert esito["collegati"] == 1
    assert esito["ambigui"] == 0
    assert assegno["fattura_id"] == "fatt-storica"
    assert assegno["stato"] == "incassato"
    assert fattura["pagato"] is True
    assert fattura["riconciliato_con_ec"] is True


def test_riprocessamento_non_indovina_tra_due_fatture_identiche():
    async def scenario():
        db = AsyncMongoMockClient()["assegno_riprocessamento_ambiguo"]
        await db.assegni.insert_one({
            "id": "ass-ambiguo", "numero": "0208770650", "anno": 2026,
            "importo": 200.0, "beneficiario": "FORNITORE DOPPIO SRL",
            "fornitore_piva": "08888888888", "stato": "compilato",
        })
        for invoice_id, numero in (("fatt-a", "A-1"), ("fatt-b", "B-1")):
            await db.invoices.insert_one({
                "id": invoice_id, "invoice_number": numero, "anno": 2026,
                "invoice_date": "2026-03-31", "supplier_vat": "08888888888",
                "supplier_name": "FORNITORE DOPPIO SRL", "total_amount": 200.0,
                "pagato": False,
            })

        esito = await riprocessa_intenti_assegni(db, anno=2026)
        assegno = await db.assegni.find_one({"id": "ass-ambiguo"}, {"_id": 0})
        return esito, assegno

    esito, assegno = _run(scenario())
    assert esito["analizzati"] == 1
    assert esito["collegati"] == 0
    assert esito["ambigui"] == 1
    assert not assegno.get("fattura_id")
    assert not assegno.get("fattura_collegata")
