"""La fattura arrivata dopo il report del titolare si paga al suo arrivo.

Prima il pagamento dichiarato aspettava il giro «Automazioni Prima Nota»,
che in produzione dura ore e riparte a ogni deploy.
"""
import asyncio

from app.database import Database
from app.services import pagamenti_dichiarati_titolare as pagamenti
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.fatture_report_ae import COLLECTION_REPORT

PIVA = "01238591216"


def test_la_fattura_appena_arrivata_riceve_il_pagamento_dichiarato(monkeypatch):
    db = ClientArchivioMemoria()["test_fattura_dopo_report"]
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))

    async def scenario():
        await db[COLLECTION_REPORT].insert_one({
            "report_key": "r-1", "supplier_vat": PIVA, "supplier_name": "KIMBO S.P.A.",
            "numero_fattura": "K-10", "data_documento": "2026-03-05",
            "filename_xml": "IT01238591216_K10.xml", "totale_documento": 99.0,
            "metodo_pagamento_titolare": "banca", "pagata_titolare": True,
            "pagamento_applicato": {"stato": "fattura_non_ancora_arrivata"},
        })
        # Un'altra riga dello stesso fornitore, per un'altra fattura: non si tocca.
        await db[COLLECTION_REPORT].insert_one({
            "report_key": "r-2", "supplier_vat": PIVA, "numero_fattura": "K-11",
            "data_documento": "2026-03-09", "filename_xml": "IT01238591216_K11.xml",
            "metodo_pagamento_titolare": "cassa", "pagata_titolare": True,
            "pagamento_applicato": {"stato": "fattura_non_ancora_arrivata"},
        })
        fattura = {
            "id": "f-k10", "invoice_number": "K-10", "supplier_vat": PIVA,
            "supplier_name": "KIMBO S.P.A.", "invoice_date": "2026-03-05",
            "total_amount": 99.0, "tipo_documento": "TD01", "status": "imported",
            "stato_import": "attivo", "filename": "IT01238591216_K10.xml",
        }
        await db["invoices"].insert_one(dict(fattura))
        esito = await pagamenti.applica_per_fattura_arrivata(db, fattura)
        return (esito, await db["invoices"].find_one({"id": "f-k10"}),
                await db["prima_nota_banca"].find({"fattura_id": "f-k10"}, {"_id": 0}).to_list(5),
                await db[COLLECTION_REPORT].find_one({"report_key": "r-2"}))

    esito, fattura, righe, altra = asyncio.run(scenario())
    assert esito["applicate"] == 1
    assert fattura["pagato"] is True and fattura["in_attesa_riscontro_banca"] is True
    assert len(righe) == 1 and righe[0]["dichiarato_titolare"] is True
    assert altra["pagamento_applicato"]["stato"] == "fattura_non_ancora_arrivata"


def test_fattura_senza_righe_nel_report_non_fa_niente():
    db = ClientArchivioMemoria()["test_fattura_senza_report"]
    esito = asyncio.run(pagamenti.applica_per_fattura_arrivata(
        db, {"id": "f-1", "supplier_vat": PIVA, "invoice_number": "X"},
    ))
    assert esito == {"applicate": 0}
