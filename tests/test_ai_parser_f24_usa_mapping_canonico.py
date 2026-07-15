"""Bug trovato nell'audit funzionale del 15/07/2026: POST /api/ai-parser/
parse-f24 classificava i tributi con una mappatura hardcoded locale, con ID
di fantasia ("CDC_PERSONALE", "CDC_SERVIZI", "CDC_TASSE") che non esistono
in CENTRI_COSTO e divergeva dal mapping ufficiale
TRIBUTI_F24_MAPPING/classifica_f24_per_tributo — es. il tributo "1040"
(ritenute lavoro autonomo) finiva su "CDC_SERVIZI" qui invece di
"7.1_COMMERCIALISTA" come nel motore canonico usato altrove."""
import asyncio

from app.routers import ai_parser as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


class _FakeUploadFile:
    def __init__(self, filename, content=b"finto pdf"):
        self.filename = filename
        self._content = content

    async def read(self):
        return self._content


def test_parse_f24_usa_mapping_canonico_tributi(monkeypatch):
    async def fake_parse_f24_ai(file_bytes=None, file_path=None):
        return {
            "success": True,
            "sezione_erario": [{"codice_tributo": "1040"}],
            "sezione_inps": [],
            "sezione_regioni": [],
            "sezione_imu": [],
        }
    monkeypatch.setattr(mod, "parse_f24_ai", fake_parse_f24_ai)

    esito = _run(mod.parse_f24_endpoint(
        file=_FakeUploadFile("f24.pdf"), save_to_db=False, apply_learning=True,
    ))

    tributo = esito["sezione_erario"][0]
    assert tributo["centro_costo_id"] == "7.1_COMMERCIALISTA"
    assert tributo["centro_costo_id"] not in ("CDC_PERSONALE", "CDC_SERVIZI", "CDC_TASSE")
