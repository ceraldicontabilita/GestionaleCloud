"""La stampa PDF di una fattura (cita «Bonifico» e IBAN) non e' un bonifico."""
import asyncio

import fitz

from app.services.bonifici_pdf_ingest import e_stampa_fattura, importa_pdf_bonifico

RIGHE = [
    "Fattura elettronica FPR 31/26",
    "Cedente/prestatore ROSARIA MAROTTA",
    "Cessionario/committente CERALDI GROUP SRL",
    "Totale imponibile 1.612,00  Totale imposta 354,64  Totale documento 1.966,64",
    "Modalita pagamento: Bonifico IBAN IT07914040634",
]


def _pdf(righe) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    for i, riga in enumerate(righe):
        page.insert_text((40, 60 + 16 * i), riga)
    return doc.tobytes()


def test_riconosce_la_stampa_dal_contenuto():
    assert e_stampa_fattura(" ".join(RIGHE))
    assert not e_stampa_fattura("Il seguente bonifico IBAN beneficiario importo 1.656,64")


def test_importa_pdf_bonifico_rifiuta_la_stampa_senza_salvare():
    from mongomock_motor import AsyncMongoMockClient

    db = AsyncMongoMockClient()["t"]
    esito = asyncio.run(importa_pdf_bonifico(db, _pdf(RIGHE), "FPR 31_26.pdf"))
    assert esito["status"] == "non_bonifico"
    assert asyncio.run(db["bonifici_transfers"].count_documents({})) == 0


def test_detect_document_type_la_manda_alle_fatture():
    from app.routers.documenti import detect_document_type

    assert detect_document_type("FPR 31_26.pdf", _pdf(RIGHE)) == "fattura"


SUMUP = """Ricevuta di bonifico 07 Aug 2026, 10:45 GMT
Dettagli bonifico
Riferimento esterno
40eebd7002774b00a91f24dfd2cbf6c2
Riferimento interno
40eebd70-0277-4b00-a91f-24dfd2cbf6c2
Data
Causale pagamento 07 Aug 2026, 10:43 GMT
Preventivo N 1908 del 07/08/2026
Importo €214.40
StatoRiuscito
Dati mittente
Dati beneficiario
Nome
Nome ceraldi group srl
Today Service S.r.l.
IBAN
IBAN IE21SUMU99036513164215
IT87M0303203406010000002929
BICSUMUIE22XXX
SumUp Limited Block 8, Dublino"""


def test_ricevuta_sumup_beneficiario_causale_e_riferimento():
    from app.routers.bonifici_module.pdf_parser import extract_transfers_from_text

    t = extract_transfers_from_text(SUMUP, filename="2026-08-07_ceraldigroupsrl@gmail.com_20260807_Ricevuta_bonifico.pdf")[0]
    assert t["importo"] == 214.40
    assert t["beneficiario"] == {"nome": "Today Service S.r.l.", "iban": "IT87M0303203406010000002929"}
    assert t["ordinante"]["iban"] == "IE21SUMU99036513164215"
    assert t["causale"] == "Preventivo N 1908 del 07/08/2026"
    assert t["cro_trn"] == "40eebd7002774b00a91f24dfd2cbf6c2"
    assert (t["data"].year, t["data"].month, t["data"].day) == (2026, 8, 7)


def test_ripulisci_mette_in_quarantena_la_stampa_anche_con_nome_generico():
    import base64

    from mongomock_motor import AsyncMongoMockClient

    from app.services.doppioni_archivio import _stampe_fattura_tra_bonifici

    db = AsyncMongoMockClient()["t"]
    asyncio.run(db["bonifici_transfers"].insert_one({
        "id": "t1", "source_file": "FPR 31_26.pdf", "importo": 1612,
        "pdf_data": base64.b64encode(_pdf(RIGHE)).decode()}))
    esito = asyncio.run(_stampe_fattura_tra_bonifici(db, dry_run=False, actor="test"))
    assert esito["stampe_fattura"] == 1
    assert asyncio.run(db["bonifici_transfers"].count_documents({})) == 0
    assert asyncio.run(db["bonifici_transfers_quarantena"].count_documents({"id": "t1"})) == 1


def test_inbox_riclassifica_la_stampa_invece_di_marcarla_elaborata():
    import base64

    from mongomock_motor import AsyncMongoMockClient

    from app.services.bonifici_pdf_ingest import processa_inbox_bonifici

    db = AsyncMongoMockClient()["t"]
    asyncio.run(db["documents_inbox"].insert_one({
        "id": "d1", "category": "bonifico", "status": "da_processare", "processed": False,
        "filename": "FPR 31_26.pdf", "pdf_data": base64.b64encode(_pdf(RIGHE)).decode()}))
    asyncio.run(processa_inbox_bonifici(db))
    doc = asyncio.run(db["documents_inbox"].find_one({"id": "d1"}))
    assert doc["category"] == "fattura_pdf" and doc["status"] == "fuori_contabilita"
    assert not doc.get("bonifico_transfer_id")
