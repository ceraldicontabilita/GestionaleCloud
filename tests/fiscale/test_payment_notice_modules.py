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
