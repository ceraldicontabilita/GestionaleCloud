import asyncio

from app.services.paypal_reconciliation_pipeline import riconcilia_paypal_importato


def test_paypal_importato_ripassa_fattura_banca_fattura_per_anni_reali(monkeypatch):
    calls = []

    async def links(db, **kwargs):
        calls.append(("fattura", kwargs))
        return {"collegati": 1}

    async def bank(db, *, anno=None, applica=False):
        calls.append(("banca", anno, applica))
        return {"riconciliati": 1, "proposte": 1, "ambigui": ["da_verificare"]}

    monkeypatch.setattr(
        "app.services.paypal_reconciliation_links.riprocessa_collegamenti_paypal", links,
    )
    monkeypatch.setattr("app.routers.paypal_statements._auto_riconcilia", bank)

    result = asyncio.run(riconcilia_paypal_importato(
        object(), start_date="2025-12-31", end_date="2026-01-01",
    ))

    assert [call[0] for call in calls] == ["fattura", "banca", "banca", "fattura"]
    assert result["banca"]["riconciliati"] == 2
    assert result["banca"]["ambigui"] == 2
    assert set(result["banca"]["per_anno"]) == {"2025", "2026"}
