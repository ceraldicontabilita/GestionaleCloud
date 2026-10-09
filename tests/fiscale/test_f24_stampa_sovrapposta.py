"""F24 del 2018-2019 (modulo con i dati sovrapposti, senza protocollo): lettura, dedup per contenuto, gusci vuoti."""
import asyncio

import fitz
from mongomock_motor import AsyncMongoMockClient

from app.routers.documenti import detect_document_type
from app.services.f24_canonico import importa_quietanza
from app.services.f24_parser import parse_quietanza_f24


def _pdf(data="19032018", saldo="260,00", righe=(("ERARIO", 174, "1040", "0002", "2018", "260,00", "0,00"),),
         segno=b"") -> bytes:
    """Il modulo com'e' nei PDF veri: parole a coordinate fisse, una cifra per casella della data."""
    doc = fitz.open()
    pagina = doc.new_page()

    def scrivi(x, y0, testo):
        pagina.insert_text((x, y0 + 9), testo, fontsize=10)

    scrivi(170, 201, "B0100503400" + data[:2] + data[2:4] + data[6:])
    scrivi(500, 201, saldo)
    scrivi(378, 222, "01005")
    scrivi(488, 222, "03400")
    for x, cifra in zip((174, 186, 200, 212, 226, 238, 250, 264), data):
        scrivi(x, 224, cifra)
    y = 417
    for sezione, x_codice, codice, mese, anno, debito, credito in righe:
        scrivi(54, y, sezione)
        scrivi(x_codice, y, codice)
        scrivi(325, y, mese)
        scrivi(358, y, anno)
        scrivi(436, y, debito)
        scrivi(520, y, credito)
        y += 11
    contenuto = doc.tobytes()
    doc.close()
    return contenuto + segno  # byte finali diversi: stesso contenuto, PDF diverso


def _run(coro):
    return asyncio.run(coro)


def test_legge_data_totale_e_mese_scritto_come_0002():
    letto = parse_quietanza_f24(pdf_content=_pdf())

    assert letto["dati_generali"]["data_pagamento"] == "2018-03-19"
    assert letto["dati_generali"]["saldo_delega"] == 260.0
    riga = letto["sezione_erario"][0]
    assert (riga["codice_tributo"], riga["periodo_riferimento"]) == ("1040", "02/2018")
    assert letto["validazione"]["saldo_quadrato"] is True


def test_totale_senza_separatore_delle_migliaia_e_credito_compensato():
    righe = (
        ("ERARIO", 174, "1001", "0012", "2018", "1675,36", "0,00"),
        ("ERARIO", 174, "1655", "0012", "2018", "0,00", "500,00"),
    )
    letto = parse_quietanza_f24(pdf_content=_pdf(saldo="1175,36", righe=righe))

    assert letto["dati_generali"]["saldo_delega"] == 1175.36
    assert letto["validazione"]["saldo_quadrato"] is True


def test_documenti_import_la_riconosce_come_quietanza_f24():
    assert detect_document_type("10_201877286_A0GHE_04523831214.pdf", _pdf()) == "quietanza_f24"


def test_lo_stesso_contenuto_stampato_due_volte_e_una_sola_quietanza():
    db = AsyncMongoMockClient()["f24old"]

    primo = _run(importa_quietanza(db, _pdf(), "a.pdf", source="prova"))
    secondo = _run(importa_quietanza(db, _pdf(segno=b"\n%copia"), "b.pdf", source="prova"))

    assert primo["success"] and primo["duplicate"] is False
    assert secondo["success"] and secondo["duplicate"] is True
    assert _run(db["quietanze_f24"].count_documents({})) == 1


def test_un_altro_importo_o_un_altro_giorno_e_un_altra_quietanza():
    db = AsyncMongoMockClient()["f24old"]
    _run(importa_quietanza(db, _pdf(), "a.pdf", source="prova"))

    altro_giorno = _run(importa_quietanza(db, _pdf(data="20032018"), "b.pdf", source="prova"))

    assert altro_giorno["duplicate"] is False
    assert _run(db["quietanze_f24"].count_documents({})) == 2


def test_guscio_vuoto_gia_in_archivio_viene_riletto_sul_posto():
    import hashlib

    contenuto = _pdf()
    db = AsyncMongoMockClient()["f24old"]
    _run(db["quietanze_f24"].insert_one({
        "id": "guscio-1", "filename": "10_201877286_A0GHE.pdf",
        "pdf_hash": hashlib.md5(contenuto).hexdigest(), "fonte": "drive_quietanze",
        "drive_file_id": "drive-1", "saldo": 0.0, "protocollo_telematico": "",
        "source_occurrences": [{"source": "drive_quietanze"}],
    }))

    esito = _run(importa_quietanza(db, contenuto, "a.pdf", source="documenti_upload_auto"))
    doc = _run(db["quietanze_f24"].find_one({"id": "guscio-1"}))

    assert esito["success"] and esito["duplicate"] is False and esito["quietanza_id"] == "guscio-1"
    assert _run(db["quietanze_f24"].count_documents({})) == 1
    assert doc["data_pagamento"] == "2018-03-19" and doc["sezione_erario"][0]["codice_tributo"] == "1040"
    assert doc["drive_file_id"] == "drive-1" and "pdf_data" not in doc
    assert len(doc["source_occurrences"]) == 2


def test_secondo_guscio_con_lo_stesso_contenuto_va_in_quarantena_reversibile():
    import hashlib

    db = AsyncMongoMockClient()["f24old"]
    prima = _pdf()
    seconda = _pdf(segno=b"\n%copia")
    for id_, contenuto in (("g1", prima), ("g2", seconda)):
        _run(db["quietanze_f24"].insert_one({
            "id": id_, "filename": f"{id_}.pdf", "pdf_hash": hashlib.md5(contenuto).hexdigest(),
            "fonte": "drive_quietanze", "drive_file_id": f"drive-{id_}", "saldo": 0.0,
            "protocollo_telematico": "",
        }))

    _run(importa_quietanza(db, prima, "g1.pdf", source="prova"))
    _run(importa_quietanza(db, seconda, "g2.pdf", source="prova"))
    secondo = _run(db["quietanze_f24"].find_one({"id": "g2"}))

    assert secondo["status"] == "eliminato" and secondo["doppione_di"] == "g1"
    assert secondo["motivo_quarantena"] == "stesso contenuto fiscale"
