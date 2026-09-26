import asyncio
import base64

import fitz
from mongomock_motor import AsyncMongoMockClient


def _run(coro):
    return asyncio.run(coro)


def test_import_hr_conserva_ordinario_e_quattordicesima_dello_stesso_periodo(monkeypatch):
    from app.hr.services import libro_unico_bundle
    from app.services import cedolini_motore

    pdf = fitz.open()
    for testo in ("PAGINA 1", "PAGINA 2", "PAGINA 3"):
        pdf.new_page().insert_text((72, 72), testo)
    pdf_bytes = pdf.tobytes()
    pdf.close()
    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")

    monkeypatch.setattr(cedolini_motore, "leggi_pdf", lambda _content: {
        "buste": [
            {
                "codice_fiscale": "RSSMRA80A01H501U", "nome_dipendente": "ROSSI MARIO",
                "anno": 2026, "mese": 7, "tipo_cedolino": "mensile",
                "netto": 1200.0, "lordo": 1500.0, "stato_netto": "NETTO_VERIFICATO_DA_CEDOLINO",
                "source_page_start": 1, "source_page_end": 2, "source_document_pages": 3,
                "_pdf_data": pdf_b64,
            },
            {
                "codice_fiscale": "RSSMRA80A01H501U", "nome_dipendente": "ROSSI MARIO",
                "anno": 2026, "mese": 7, "tipo_cedolino": "quattordicesima",
                "netto": 600.0, "lordo": 750.0, "stato_netto": "NETTO_VERIFICATO_DA_CEDOLINO",
                "retribuzione": {"paga_base": 750.0},
                "source_page_start": 3, "source_page_end": 3, "source_document_pages": 3,
                "_pdf_data": pdf_b64,
            },
        ],
        "presenze": [],
    })

    db = AsyncMongoMockClient()["hr_libro_unico"]
    _run(db.dipendenti.insert_one({
        "id": "dip-1", "codice_fiscale": "RSSMRA80A01H501U", "nome_completo": "Rossi Mario",
    }))

    esito = _run(libro_unico_bundle.dividi_e_registra(db, pdf_bytes, "libro-unico.pdf"))
    inseriti = _run(db.cedolini.find({}, {"_id": 0}).to_list(10))

    assert esito["pagine_totali"] == 3
    assert len(esito["inseriti"]) == 2
    assert {(c["tipo_cedolino"], c["netto"]) for c in inseriti} == {
        ("ordinario", 1200.0), ("quattordicesima", 600.0),
    }
    assert {(c["source_page_start"], c["source_page_end"]) for c in inseriti} == {(1, 2), (3, 3)}
    quattordicesima = next(c for c in inseriti if c["tipo_cedolino"] == "quattordicesima")
    assert quattordicesima["retribuzione"] == {"paga_base": 750.0}
