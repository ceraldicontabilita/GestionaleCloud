"""Regressioni per gli incassi contanti e i pagamenti fornitore da EC."""
import asyncio

from app.routers.prima_nota_module import sync
from app.services.sheets_document_store import MemorySheetsClient


def test_fattura_impostata_cassa_trova_addebito_ec_con_type_e_causale(monkeypatch):
    async def scenario():
        db = MemorySheetsClient().db
        await db.prima_nota_cassa.insert_one({
            "id": "cassa-1", "data": "2026-08-01", "tipo": "uscita",
            "fattura_id": "fatt-1", "importo": 123.45, "status": "active",
        })
        await db.invoices.insert_one({
            "id": "fatt-1", "invoice_number": "A-44", "supplier_name": "Fornitore Verdi SRL",
            "supplier_vat": "01234567890", "total_amount": 123.45,
        })
        await db.estratto_conto_movimenti.insert_one({
            "id": "ec-1", "data": "2026-08-03", "type": "uscita", "importo": -123.45,
            "causale": "PAGAMENTO FORNITORE VERDI SRL DOC A-44", "riconciliato": False,
        })
        monkeypatch.setattr(sync.Database, "get_db", staticmethod(lambda: db))
        return await sync.sposta_fatture_cassa_pagate_in_banca(dry_run=True, anno=2026)

    risultato = asyncio.run(scenario())
    assert risultato["dry_run"] is True
    assert risultato["da_spostare_in_banca"] == 1
    assert risultato["dettaglio"][0]["fattura"] == "A-44"
