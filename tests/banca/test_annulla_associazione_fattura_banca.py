import asyncio

from app.services.sheets_document_store import MemorySheetsClient

from app.routers.prima_nota_module import manutenzione


def test_annulla_solo_falso_match_e_conserva_associazione_corretta(monkeypatch):
    async def scenario():
        db = MemorySheetsClient()["annulla_falso_match"]
        await db.invoices.insert_many([
            {
                "id": "carta-56", "supplier_vat": "05851861210",
                "invoice_number": "56", "total_amount": 153.72,
                "pagato": True, "paid": True, "stato_pagamento": "pagata",
                "riconciliato_con_ec": "ec-timas",
            },
            {
                "id": "timas-386", "supplier_vat": "07818970639",
                "invoice_number": "386", "total_amount": 153.72,
                "pagato": True, "riconciliato_con_ec": "ec-timas",
            },
        ])
        await db.prima_nota_banca.insert_many([
            {"id": "pn-carta", "fattura_id": "carta-56",
             "estratto_conto_id": "ec-timas", "status": "active"},
            {"id": "pn-timas", "fattura_id": "timas-386",
             "estratto_conto_id": "ec-timas", "status": "active"},
        ])
        await db.estratto_conto_movimenti.insert_one(
            {"id": "ec-timas", "riconciliato": True, "descrizione": "FAVORE TIMAS ASCENSORI"}
        )
        await db.scadenziario_fornitori.insert_one({
            "id": "rata-carta", "fattura_id": "carta-56", "importo_rata": 153.72,
            "importo_pagato": 153.72, "pagato": True,
            "evidenze_pagamento": [{
                "evidenza_id": "banca:ec-timas:carta-56", "importo": 153.72,
            }],
        })
        monkeypatch.setattr(manutenzione.Database, "get_db", staticmethod(lambda: db))

        result = await manutenzione.annulla_associazione_fattura_banca(
            manutenzione.AnnullaAssociazioneFatturaBancaRequest(
                partita_iva="05851861210", numero_fattura="56",
                importo_atteso=153.72,
                motivo="Il movimento bancario nomina TIMAS e non Carta & Party",
            ),
            {"username": "test-admin"},
        )

        carta = await db.invoices.find_one({"id": "carta-56"})
        timas = await db.invoices.find_one({"id": "timas-386"})
        movimento = await db.estratto_conto_movimenti.find_one({"id": "ec-timas"})
        rata = await db.scadenziario_fornitori.find_one({"id": "rata-carta"})
        assert result["scritture_archiviate"] == 1
        assert result["movimenti_estratto_liberati"] == 0
        assert carta["pagato"] is False and carta["stato_pagamento"] == "da_pagare"
        assert timas["pagato"] is True
        assert movimento["riconciliato"] is True
        assert rata["pagato"] is False and rata["importo_pagato"] == 0
        assert await db.audit_log.count_documents({"entita_id": "carta-56"}) == 1

    asyncio.run(scenario())
