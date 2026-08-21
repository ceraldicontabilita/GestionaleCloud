import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.routers import previsioni_acquisti


def test_statistiche_espongono_quantita_corrente_confronto_e_costo(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["test_previsioni_statistiche"]
        monkeypatch.setattr(
            previsioni_acquisti.Database, "get_db", staticmethod(lambda: db)
        )
        await db["acquisti_prodotti"].insert_many([
            {
                "anno": 2025, "descrizione_normalizzata": "PANUOZZO",
                "descrizione": "Panuozzo", "unita_misura": "CF",
                "quantita": 42.0, "totale_linea": 0,
                "data_fattura": "2025-06-22",
            },
            {
                "anno": 2026, "descrizione_normalizzata": "PANUOZZO",
                "descrizione": "Panuozzo", "unita_misura": "CF",
                "quantita": 252.0, "totale_linea": 0,
                "data_fattura": "2026-06-22",
            },
            {
                "anno": 2026, "descrizione_normalizzata": "PRODOTTO NUOVO",
                "descrizione": "Prodotto nuovo", "unita_misura": "PZ",
                "quantita": 10.0, "totale_linea": 25.0,
                "data_fattura": "2026-07-01",
            },
        ])

        result = await previsioni_acquisti.statistiche_acquisti(
            anno=2026, prodotto=None
        )
        per_id = {row["id"]: row for row in result["statistiche"]}

        panuozzo = per_id["PANUOZZO"]
        assert panuozzo["quantita_anno_corrente"] == 252.0
        assert panuozzo["quantita_anno_prec"] == 42.0
        assert panuozzo["differenza_quantita"] == 210.0
        assert panuozzo["variazione_pct"] == 500.0
        assert panuozzo["costo_disponibile"] is False

        nuovo = per_id["PRODOTTO NUOVO"]
        assert nuovo["variazione_pct"] is None
        assert nuovo["trend"] == "nuovo"
        assert nuovo["costo_disponibile"] is True

    asyncio.run(scenario())
