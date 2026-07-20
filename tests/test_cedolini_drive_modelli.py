import base64
import asyncio


def test_teamsystem_legge_totali_dalle_celle_e_non_dalla_riga_precedente():
    from app.parsers.busta_paga_multi_template import _parse_teamsystem_layout

    words = [[
        (10, 10, 20, 14, "TOT."),
        (22, 10, 58, 14, "TRATTENUTE"),
        (30, 22, 55, 26, "25,84"),
        (10, 40, 25, 44, "NETTO"),
        (27, 40, 40, 44, "BUSTA"),
        (25, 52, 45, 56, "251,00"),
        (10, 70, 18, 74, "TFR"),
        (20, 70, 31, 74, "MESE"),
        (20, 82, 40, 86, "19,37"),
    ]]

    dati = _parse_teamsystem_layout(words)

    assert dati["trattenute"] == 25.84
    assert dati["netto"] == 251.0
    assert dati["tfr_quota_mese"] == 19.37


def test_drive_cedolino_usa_parser_multi_template_e_propagazione_pdf(monkeypatch):
    from app.parsers import busta_paga_multi_template as multi
    from app.services import cedolini_manager
    from app.services import salari_unificati_v2

    pdf_bytes = b"pdf-sintetico-senza-dati-reali"
    ricevuto = {}

    monkeypatch.setattr(multi, "parse_busta_paga_from_bytes", lambda _data: {
        "parse_success": True,
        "template": "teamsystem",
        "num_pages": 4,
        "dipendente": {"nome_completo": "DIPENDENTE TEST", "codice_fiscale": "TSTTST80A01F205X"},
        "periodo": {"mese": 5, "anno": 2026},
        "totali": {"netto": 1234.56, "lordo": 1600.0, "trattenute": 365.44},
        "tfr": {"quota_anno": 100.0},
        "ferie_permessi": {},
    })

    async def fake_processa(**kwargs):
        ricevuto.update(kwargs)
        return {"success": True, "riconciliato": False}

    monkeypatch.setattr(salari_unificati_v2, "processa_cedolino_v2", fake_processa)

    risultato = asyncio.run(
        cedolini_manager.processa_tutti_cedolini_pdf(
            db=object(),
            pdf_data=base64.b64encode(pdf_bytes).decode(),
            filename="cedolino_test.pdf",
        )
    )

    assert risultato["success"] is True
    assert risultato["metodo"] == "multi_template"
    assert risultato["cedolini_processati"] == 1
    assert ricevuto["cedolino_data"]["formato_rilevato"] == "teamsystem"
    assert ricevuto["cedolino_data"]["netto_mese"] == 1234.56
    assert ricevuto["pdf_data"] == base64.b64encode(pdf_bytes).decode()


class _Collection:
    def __init__(self, rows):
        self.rows = rows

    async def find_one(self, query, projection=None):
        for row in self.rows:
            if all(row.get(k) == v for k, v in query.items() if not isinstance(v, dict)):
                return dict(row)
        return None


class _Db:
    def __init__(self, salary, cedolino):
        self.collections = {
            "prima_nota_salari": _Collection([salary]),
            "cedolini": _Collection([cedolino]),
        }

    def __getitem__(self, name):
        return self.collections[name]


def test_pdf_cedolino_visualizzabile_dalla_riga_salario(monkeypatch):
    from app.database import Database
    from app.routers.accounting.prima_nota_salari import get_cedolino_pdf

    contenuto = b"%PDF-1.4\ncedolino sintetico\n%%EOF"
    db = _Db(
        {"id": "sal-1", "cedolino_id": "ced-1", "codice_fiscale": "TEST", "mese": 5, "anno": 2026},
        {"id": "ced-1", "pdf_data": base64.b64encode(contenuto).decode()},
    )
    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: db))

    async def _leggi():
        response = await get_cedolino_pdf("sal-1", _current_user={"user_id": "test"})
        body = b"".join([chunk async for chunk in response.body_iterator])
        return response, body

    response, body = asyncio.run(_leggi())

    assert response.media_type == "application/pdf"
    assert body == contenuto
    assert response.headers["content-disposition"].startswith("inline")
