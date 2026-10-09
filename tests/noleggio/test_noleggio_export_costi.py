import asyncio

from app.routers import noleggio


def test_export_pdf_riusa_la_stessa_aggregazione_della_pagina(monkeypatch):
    async def aggregazione_unica(anno=None):
        assert anno == 2026
        return {
            "veicoli": [
                {
                    "targa": "AA000AA",
                    "marca": "Fiat",
                    "modello": "Tipo",
                    "driver": "Mario Rossi",
                    "totale_canoni": 1000.0,
                    "totale_verbali": 50.0,
                    "totale_bollo": 20.0,
                    "totale_pedaggio": 30.0,
                    "totale_costi_extra": 40.0,
                    "totale_riparazioni": 60.0,
                }
            ]
        }

    async def seconda_scansione_vietata(*_args, **_kwargs):
        raise AssertionError("Il PDF non deve ricalcolare le fatture separatamente")

    monkeypatch.setattr(noleggio, "get_veicoli", aggregazione_unica)
    monkeypatch.setattr(noleggio, "scan_fatture_noleggio", seconda_scansione_vietata)

    response = asyncio.run(noleggio.export_pdf_costi(anno=2026))

    assert response.media_type == "application/pdf"
    assert response.headers["content-disposition"] == 'inline; filename="riepilogo_costi_noleggio_2026.pdf"'
    assert response.body.startswith(b"%PDF")
