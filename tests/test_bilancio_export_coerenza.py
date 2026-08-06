"""Guardie di coerenza per pagina, PDF e confronto del Bilancio.

Il Bilancio deve avere un solo calcolatore per Stato Patrimoniale e Conto
Economico. In particolare, export e confronto non possono riclassificare le
fatture ricevute come crediti o stimare imposte non confermate.
"""

import asyncio

from app.routers.accounting import bilancio as mod


def _run(coro):
    return asyncio.run(coro)


def _sp(anno, *, attivo=1000.0, immobilizzazioni=200.0, tfr=100.0):
    debiti = 300.0
    patrimonio = attivo - debiti - tfr
    return {
        "anno": anno,
        "attivo": {
            "disponibilita_liquide": {"cassa": 100.0, "banca": 600.0, "totale": 700.0},
            "crediti": {"crediti_vs_clienti": 100.0, "totale": 100.0},
            "immobilizzazioni": {
                "da_cespiti": immobilizzazioni,
                "da_voci_manuali": 0.0,
                "totale": immobilizzazioni,
            },
            "totale_attivo": attivo,
        },
        "passivo": {
            "debiti": {"debiti_vs_fornitori": debiti, "totale": debiti},
            "fondo_tfr": tfr,
            "patrimonio_netto": patrimonio,
            "patrimonio_netto_dettaglio_manuale": 0.0,
            "totale_passivo": attivo,
        },
    }


def _ce(anno, *, ricavi=800.0, costi=500.0):
    risultato = ricavi - costi
    return {
        "anno": anno,
        "ricavi": {
            "corrispettivi": ricavi,
            "corrispettivi_lordi": ricavi,
            "totale_ricavi": ricavi,
        },
        "costi": {
            "acquisti": costi,
            "note_credito": 0.0,
            "costi_netti": costi,
            "totale_costi": costi,
        },
        "risultato": {
            "utile_perdita": risultato,
            "margine_percentuale": round(risultato / ricavi * 100, 1),
            "tipo": "utile" if risultato >= 0 else "perdita",
        },
    }


def test_helper_stato_patrimoniale_delega_al_calcolatore_della_pagina(monkeypatch):
    expected = _sp(2026)
    chiamata = {}

    async def fake_get_stato_patrimoniale(*, anno, mese, data_a):
        chiamata.update(anno=anno, mese=mese, data_a=data_a)
        return expected

    monkeypatch.setattr(mod, "get_stato_patrimoniale", fake_get_stato_patrimoniale)

    assert _run(mod._get_stato_patrimoniale_data(2026, 6)) is expected
    assert chiamata == {"anno": 2026, "mese": 6, "data_a": None}


def test_helper_conto_economico_delega_al_calcolatore_della_pagina(monkeypatch):
    expected = _ce(2026)
    chiamata = {}

    async def fake_get_conto_economico(*, anno, mese):
        chiamata.update(anno=anno, mese=mese)
        return expected

    monkeypatch.setattr(mod, "get_conto_economico", fake_get_conto_economico)

    assert _run(mod._get_conto_economico_data(2026, 4)) is expected
    assert chiamata == {"anno": 2026, "mese": 4}


def test_confronto_usa_dati_reali_senza_utile_netto_forfettario(monkeypatch):
    async def fake_sp(anno, mese=None):
        return _sp(anno, attivo=1000.0 if anno == 2026 else 900.0)

    async def fake_ce(anno, mese=None):
        return _ce(
            anno,
            ricavi=800.0 if anno == 2026 else 700.0,
            costi=500.0 if anno == 2026 else 450.0,
        )

    monkeypatch.setattr(mod, "_get_stato_patrimoniale_data", fake_sp)
    monkeypatch.setattr(mod, "_get_conto_economico_data", fake_ce)

    result = _run(mod.get_confronto_annuale(anno_corrente=2026, anno_precedente=2025))

    assert result["conto_economico"]["risultato"]["utile_perdita"]["attuale"] == 300.0
    assert "utile_netto" not in result["conto_economico"]["risultato"]
    assert result["stato_patrimoniale"]["attivo"]["immobilizzazioni"]["attuale"] == 200.0
    assert result["stato_patrimoniale"]["passivo"]["fondo_tfr"]["attuale"] == 100.0
    assert result["stato_patrimoniale"]["passivo"]["totale_passivo"]["attuale"] == 1000.0
    assert "risultato_su_attivo_pct" in result["kpi"]
    assert "roi_pct" not in result["kpi"]


def test_export_pdf_accetta_la_struttura_canonica_completa(monkeypatch):
    async def fake_sp(anno, mese=None):
        return _sp(anno)

    async def fake_ce(anno, mese=None):
        return _ce(anno)

    monkeypatch.setattr(mod, "_get_stato_patrimoniale_data", fake_sp)
    monkeypatch.setattr(mod, "_get_conto_economico_data", fake_ce)

    response = _run(mod.export_bilancio_pdf(anno=2026, mese=6))

    async def read_body():
        return b"".join([chunk async for chunk in response.body_iterator])

    body = _run(read_body())
    assert response.media_type == "application/pdf"
    assert body.startswith(b"%PDF")
    assert "bilancio_2026_06.pdf" in response.headers["content-disposition"]
