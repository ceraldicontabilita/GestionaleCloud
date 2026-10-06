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
