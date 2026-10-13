import asyncio

import fitz
from mongomock_motor import AsyncMongoMockClient

from app.services.payment_notice_modules import parse_notice_modules
from app.services.pagopa_receipts import associa_avvisi_a_ricevuta


def pdf(text):
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((30, 30), text, fontsize=8)
        return doc.tobytes()


def postal(code, cents):
    return (f"18{code}1200001234567810{cents:010d}3896\n"
            f"{code}\n<{code}>\n{cents // 100},{cents % 100:02d}\n")


def test_codice_e_centesimi_del_modulo_postale_non_fanno_una_quietanza():
    content = pdf("BOLLO DELL'UFFICIO POSTALE\ncodice cliente\nCONTI CORRENTI POSTALI - Ricevuta di Versamento\n"
                  + postal("888888000000000001", 43453) + postal("888888000000000002", 43452))
    modules = parse_notice_modules(content)
    assert [(m["code"], m["amount_cents"]) for m in modules] == [
        ("888888000000000001", 43453), ("888888000000000002", 43452)]
    assert all(not m["is_payment_receipt"] for m in modules)
    from app.routers.documenti import detect_document_type
    assert detect_document_type("bolletta.pdf", content) == "avviso_pagopa"


def test_mav_prestampato_non_e_f24_anche_se_scrive_quietanza():
    content = pdf("M.AV. elettronico bancario\nquietanza di pagamento - Copia cliente\n"
                  "Codice identificativo MAV\nTimbro datario\n06230000000000001\n14,79\n14,79\n")
    assert parse_notice_modules(content)[0]["amount_cents"] == 1479
    from app.routers.documenti import detect_document_type
    assert detect_document_type("mav.pdf", content) == "avviso_pagopa"


def test_bolletta_con_quietanza_nelle_voci_e_moduli_dopo_la_quinta_pagina():
    # ABC cita il bollo quietanza nelle voci; i bollettini arrivano a pagina 7.
    with fitz.open() as doc:
        for _ in range(6):
            doc.new_page().insert_text((30, 30), "Bolletta acquedotto - Componente bollo quietanza")
        doc.new_page().insert_text((30, 30), "BOLLO DELL'UFFICIO POSTALE\ncodice cliente\n"
                                  + postal("888888000433211148", 43453), fontsize=8)
        content = doc.tobytes()
    from app.routers.documenti import detect_document_type
    assert detect_document_type("bolletta.pdf", content) == "avviso_pagopa"
    assert parse_notice_modules(content)[0]["page_number"] == 7


def test_mav_ambiguo_e_barcode_senza_conferma_non_creano_importi():
    assert parse_notice_modules(pdf("Codice identificativo MAV\nTimbro datario\n"
                                   "06230000000000001\n14,79\n20,00\n")) == []
    assert parse_notice_modules(pdf("BOLLO DELL'UFFICIO POSTALE\ncodice cliente\n"
                                   "18888888000000000001120000123456781000000434533896\n")) == []


def test_modulo_rottamazione_legge_codice_e_importo_della_stessa_pagina():
    content = pdf("MODULO DI PAGAMENTO\nCOMUNICAZIONE DELLE SOMME DOVUTE\n"
                  "BANCHE E ALTRI CANALI\nEuro 126,68\nCodice modulo di pagamento\n"
                  "AJZ8Z\n180071500000000001\nBOLLETTINO POSTALE PA\nEuro 126,68\n")
    result = parse_notice_modules(content)
    assert len(result) == 1 and result[0]["code"] == "180071500000000001"
    assert result[0]["amount_cents"] == 12668


def test_ricevute_si_agganciano_alle_rate_esatte_senza_chiudere_tutta_la_bolletta():
    async def scenario():
        db = AsyncMongoMockClient()["moduli"]
        modules = [{"code": "888888000000000001", "amount": 434.53, "amount_cents": 43453},
                   {"code": "888888000000000002", "amount": 434.52, "amount_cents": 43452}]
        await db.documents_inbox.insert_one({"id": "bolletta", "document_type": "avviso_pagopa",
                                            "parsed_metadata": {"payment_modules": modules}, "pagato": False})
        receipt = {"id": "r1", "identificativo_bolletta": modules[0]["code"], "importo": 434.53,
                   "is_payment_receipt": True}
        await db.ricevute_pagopa.insert_one(receipt)
        for _ in range(2):
            assert await associa_avvisi_a_ricevuta(db, receipt) == ["bolletta"]
        row = await db.documents_inbox.find_one({"id": "bolletta"})
        assert not row["pagato"] and len(row["pagamenti_moduli"]) == 1
        assert await associa_avvisi_a_ricevuta(db, {**receipt, "importo": 435.53}) == []
        assert await associa_avvisi_a_ricevuta(db, {**receipt, "duplicate_of": "r2"}) == []
    asyncio.run(scenario())


def test_ricevuta_con_iuv_17_collega_rottamazione_senza_creare_pagamenti():
    async def scenario():
        db = AsyncMongoMockClient()["moduli"]
        await db.documents_inbox.insert_one({"id": "definizione", "document_type": "ader_definizione_agevolata",
            "parsed_metadata": {"payment_modules": [{"code": "180071500000000001", "amount": 126.68,
                                                       "amount_cents": 12668}]}})
        receipt = {"id": "r", "identificativo_bolletta": "80071500000000001", "importo": 126.68}
        assert await associa_avvisi_a_ricevuta(db, receipt) == ["definizione"]
        row = await db.documents_inbox.find_one({"id": "definizione"})
        assert not row.get("pagato")  # Il modulo da solo non certifica l'intero debito.
        assert next(iter(row["pagamenti_moduli"].values()))["pagato_documentalmente"]
        assert await db.ricevute_pagopa.count_documents({}) == 0
    asyncio.run(scenario())


def test_bollettino_postale_ricollega_verbale_pagato_entro_termine_pec():
    from app.services.payment_notice_modules import collega_moduli_verbale
    async def scenario():
        db = AsyncMongoMockClient()["verbale_moduli"]
        content = pdf("BOLLO DELL'UFFICIO POSTALE\ncodice cliente\n"
                      + postal("660002023077708027", 3490) + postal("660002023077708027", 4750))
        await db.verbali_noleggio.insert_one({"id": "v", "source_document_id": "originale", "numero_verbale": "B23123017923",
            "importo": 47.50, "importo_ordinario": 47.50, "importo_ridotto": 34.90,
            "data_notifica": "2023-12-05", "data_notifica_fonte": "pec", "stato": "aperto"})
        receipt = {"id": "r", "identificativo_bolletta": "660002023077708027", "importo": 34.90,
                   "data_pagamento": "2023-12-05", "is_payment_receipt": True}
        await db.ricevute_pagopa.insert_one(receipt)
        assert (await collega_moduli_verbale(db, "originale", content))["collegati"] == 1
        verbale = await db.verbali_noleggio.find_one({"id": "v"})
        assert verbale["pagato_documentalmente"] and verbale["importo_pagato"] == 34.90
        assert verbale["importo"] == 47.50 and not verbale["banca_verificata"]
        assert (await db.ricevute_pagopa.find_one({"id": "r"}))["verbale_id"] == "v"
        assert await db.ricevute_pagopa.count_documents({}) == 1
    asyncio.run(scenario())


def test_bollettino_ridotto_tardivo_resta_da_verificare():
    from app.services.payment_notice_modules import collega_moduli_verbale
    async def scenario():
        db = AsyncMongoMockClient()["verbale_tardivo"]
        content = pdf("BOLLO DELL'UFFICIO POSTALE\ncodice cliente\n" + postal("660002023077708027", 3490))
        await db.verbali_noleggio.insert_one({"id": "v", "source_document_id": "originale", "importo": 47.50,
            "importo_ridotto": 34.90, "data_notifica": "2023-12-05", "data_notifica_fonte": "pec", "stato": "aperto"})
        await db.ricevute_pagopa.insert_one({"id": "r", "identificativo_bolletta": "660002023077708027",
            "importo": 34.90, "data_pagamento": "2023-12-20", "is_payment_receipt": True})
        assert (await collega_moduli_verbale(db, "originale", content))["collegati"] == 0
        assert (await db.verbali_noleggio.find_one({"id": "v"}))["stato"] == "aperto"
    asyncio.run(scenario())


def test_due_rav_nella_stessa_pagina_non_scambiano_gli_importi():
    with fitz.open() as doc:
        page = doc.new_page()
        for x, code, amount, encoded in [(30, '81010494404909929', '17.789,12', '00017789+12>'),
                                         (330, '81010494404910737', '17.788,93', '00017788+93>')]:
            page.insert_text((x, 30), f'RAV\n{code}\n<0{code}>\n{amount}\n{encoded}', fontsize=8)
        result = parse_notice_modules(doc.tobytes())
    assert {(m['code'], m['amount_cents']) for m in result} == {
        ('81010494404909929', 1778912), ('81010494404910737', 1778893)}
    assert all(not m['is_payment_receipt'] for m in result)


def test_rav_importo_codificato_diverso_dal_leggibile_non_si_associa():
    content = pdf('RAV\n81010494404909929\n<081010494404909929>\n17.789,12\n00017789+13>')
    assert parse_notice_modules(content) == []
