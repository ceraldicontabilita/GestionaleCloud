import asyncio
import base64

import fitz


def _run(coro):
    return asyncio.run(coro)


def test_libro_unico_hr_passa_dallo_scrittore_unico_e_riporta_ogni_busta(monkeypatch):
    from app.database import Database
    from app.hr.services import libro_unico_bundle
    from app.services import cedolini_manager

    pdf = fitz.open()
    for testo in ("PAGINA 1", "PAGINA 2", "PAGINA 3"):
        pdf.new_page().insert_text((72, 72), testo)
    pdf_bytes = pdf.tobytes()
    pdf.close()

    chiamate = []
    erp_db = object()

    async def scrittore(db, pdf_b64, filename, **kwargs):
        chiamate.append((db, base64.b64decode(pdf_b64), filename, kwargs))
        return {"dettaglio": [
            {"dipendente": "ROSSI MARIO", "codice_fiscale": "RSSMRA80A01H501U", "anno": 2026,
             "mese": 7, "tipo_cedolino": "mensile", "netto": 1200.0, "esito": "scritta"},
            {"dipendente": "ROSSI MARIO", "codice_fiscale": "RSSMRA80A01H501U", "anno": 2026,
             "mese": 7, "tipo_cedolino": "quattordicesima", "netto": 600.0, "esito": "solo_hr"},
            {"dipendente": "BIANCHI LUCA", "codice_fiscale": "BNCLCU80A01H501X", "anno": 2026,
             "mese": 7, "tipo_cedolino": "mensile", "netto": 900.0, "esito": "gia_presente"},
        ], "errori": ["ROSSI: scrittura fallita"]}

    monkeypatch.setattr(cedolini_manager, "processa_tutti_cedolini_pdf", scrittore)
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: erp_db))

    esito = _run(libro_unico_bundle.dividi_e_registra(object(), pdf_bytes, "libro-unico.pdf"))

    assert chiamate[0][0] is erp_db
    assert chiamate[0][1] == pdf_bytes
    assert esito["pagine_totali"] == 3
    assert esito["dipendenti_nel_documento"] == 2
    assert {(b["tipo_cedolino"], b["netto"]) for b in esito["inseriti"]} == {
        ("ordinario", 1200.0), ("quattordicesima", 600.0),
    }
    assert esito["inseriti"][0]["competenza"] == "2026-07"
    assert esito["gia_presenti"] == [{"dipendente": "BIANCHI LUCA", "competenza": "2026-07"}]
    assert esito["senza_pagina_retributiva"] == [{"errore": "ROSSI: scrittura fallita"}]


def test_endpoint_libro_unico_canonico_sincronizza_attese_14a(monkeypatch):
    from app.hr.routers import dipendenti_cloud
    from app.hr.services import libro_unico_bundle, sincronizza_paghe_mensili

    db = object()
    monkeypatch.setattr(dipendenti_cloud, "get_db", lambda: db)
    monkeypatch.setattr(
        dipendenti_cloud,
        "_espandi_in_pdf",
        lambda nome, data: ([(nome, data)], []),
    )

    async def dividi(db_arg, pdf_bytes, nome):
        assert db_arg is db
        assert pdf_bytes == b"pdf"
        return {
            "inseriti": [{
                "dipendente": "Rossi Mario", "competenza": "2025-07",
                "tipo_cedolino": "quattordicesima", "netto": 607.0,
            }],
            "gia_presenti": [], "senza_pagina_retributiva": [], "senza_anagrafica": [],
        }

    async def sincronizza(db_arg):
        assert db_arg is db
        return {"creati": 1, "aggiornati": 0, "saltati_manuali": 0}

    monkeypatch.setattr(libro_unico_bundle, "dividi_e_registra", dividi)
    monkeypatch.setattr(sincronizza_paghe_mensili, "sincronizza", sincronizza)

    class File:
        filename = "libro-unico.pdf"

        async def read(self):
            return b"pdf"

    esito = _run(dipendenti_cloud.importa_libro_unico_canonico([File()]))

    assert esito["totale_associati"] == 1
    assert esito["associati"][0]["mese"] == 14
    assert esito["associati"][0]["mese_competenza"] == 7
    assert esito["sincronizzazione_paghe"]["creati"] == 1
