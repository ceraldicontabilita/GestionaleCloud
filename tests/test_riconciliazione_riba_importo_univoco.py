import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.services import riconciliazione_bancaria as mod


async def _noop(*args, **kwargs):
    return None


def _fattura(fid, numero):
    return {
        "id": fid,
        "invoice_number": numero,
        "invoice_date": "2026-08-01",
        "supplier_vat": "06707340960",
        "supplier_name": "LEASYS ITALIA SPA",
        "total_amount": 1119.48,
        "importo_pagato": 0.0,
        "importo_residuo": 1119.48,
        "pagato": False,
        "stato_pagamento": "aperta",
    }


def _db(monkeypatch, nome):
    db = MemorySheetsClient()[nome]
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(mod, "_propaga_fattura_pagata", _noop)
    monkeypatch.setattr(mod, "_registra_match_partita_aperta", _noop)
    monkeypatch.setattr(mod, "_alert_match_ambiguo", _noop)
    return db


def test_riba_importo_al_centesimo_e_fornitore_univoco_si_aggancia(monkeypatch):
    async def scenario():
        db = _db(monkeypatch, "riba_univoca")
        await db.invoices.insert_one(_fattura("f1", "0000202611306589"))
        await db.estratto_conto_movimenti.insert_one({
            "id": "ec-riba-1", "data": "2026-08-08", "tipo": "uscita",
            "importo": -1119.48, "descrizione_originale": "RIB LEASYS ITALIA SPA",
            "riconciliato": False,
        })

        risultato = await mod.riconcilia_movimenti_banca()

        assert risultato["riconciliati_fatture"] == 1
        assert risultato["dubbi"] == 0
        fattura = await db.invoices.find_one({"id": "f1"})
        assert fattura["pagato"] is True
        assert fattura["metodo_pagamento"] == "RiBa"
        movimento = await db.prima_nota_banca.find_one({"fattura_id": "f1"})
        assert "RiBa" in movimento["descrizione"]

    asyncio.run(scenario())


def test_riba_stesso_importo_su_due_fatture_resta_sospesa(monkeypatch):
    async def scenario():
        db = _db(monkeypatch, "riba_ambigua")
        await db.invoices.insert_many([_fattura("f1", "100"), _fattura("f2", "101")])
        await db.estratto_conto_movimenti.insert_one({
            "id": "ec-riba-2", "data": "2026-08-08", "tipo": "uscita",
            "importo": -1119.48, "descrizione_originale": "RIB LEASYS ITALIA SPA",
            "riconciliato": False,
        })

        risultato = await mod.riconcilia_movimenti_banca()

        assert risultato["riconciliati_fatture"] == 0
        assert risultato["dubbi"] == 1
        assert await db.invoices.count_documents({"pagato": True}) == 0
        proposta = await db.operazioni_da_confermare.find_one({"movimento_ec_id": "ec-riba-2"})
        assert len(proposta["dettagli"]["fatture_candidate"]) == 2
        assert "Importo al centesimo" in proposta["dettagli"]["motivo_dubbio"]

    asyncio.run(scenario())
