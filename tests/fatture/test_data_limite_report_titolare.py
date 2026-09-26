"""Regola del titolare (26/09/2026) sul report «Fatture ricevute».

Fino all'ultima operazione del suo file comanda il file; dal giorno dopo il
sistema applica il metodo impostato sul fornitore. E il file non riscrive
mai un metodo che il titolare ha gia' impostato in Fornitori.
"""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def db(monkeypatch):
    database = AsyncMongoMockClient()["data_limite"]
    from app.database import Database

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: database))
    return database


def _report(db, *date, titolare=True):
    righe = []
    for i, d in enumerate(date):
        riga = {"report_key": f"r{i}", "data_documento": d}
        if titolare:
            riga["pagata_titolare"] = True
        righe.append(riga)
    run(db["fatture_report_ae"].insert_many(righe))


def test_la_data_limite_e_l_ultima_del_file_del_titolare(db):
    from app.routers.prima_nota_module.sync import data_limite_dichiarazioni

    assert run(data_limite_dichiarazioni(db)) == ""
    _report(db, "2026-01-05", "2026-09-18", "2026-03-10")
    # un report dell'Agenzia senza le colonne del titolare non sposta la data
    run(db["fatture_report_ae"].insert_one({"report_key": "x", "data_documento": "2026-12-31"}))
    assert run(data_limite_dichiarazioni(db)) == "2026-09-18"


@pytest.mark.parametrize("data,atteso", [
    ("2026-09-18", ("sospesa", "in_attesa", "dichiarazione_titolare")),
    ("2026-02-01", ("sospesa", "in_attesa", "dichiarazione_titolare")),
    ("2026-09-19", ("cassa", "confermato", "fornitore")),
])
def test_entro_la_data_comanda_il_file_dopo_il_metodo(data, atteso):
    from app.routers.prima_nota_module.sync import _PerPiva, _classifica_provvisorio_fattura

    metodi = _PerPiva()
    metodi["01234567890"] = "contanti"
    fattura = {"supplier_vat": "01234567890", "invoice_date": data}
    assert _classifica_provvisorio_fattura(fattura, metodi, "2026-09-18") == atteso


def test_la_banca_dichiarata_nel_file_resta_banca():
    """Le fatture che il file dice pagate in banca aspettano l'estratto conto
    come banca, non tornano «da decidere» per la data limite."""
    from app.routers.prima_nota_module.sync import _PerPiva, _classifica_provvisorio_fattura

    fattura = {"supplier_vat": "01234567890", "invoice_date": "2026-05-01",
               "metodo_pagamento_previsto": "banca",
               "metodo_pagamento_override_source": "operatore_prima_nota"}
    assert _classifica_provvisorio_fattura(fattura, _PerPiva(), "2026-09-18")[0] == "banca"


def test_senza_file_vale_sempre_il_metodo():
    from app.routers.prima_nota_module.sync import _PerPiva, _classifica_provvisorio_fattura

    metodi = _PerPiva()
    metodi["01234567890"] = "banca"
    fattura = {"supplier_vat": "01234567890", "invoice_date": "2026-02-01"}
    assert _classifica_provvisorio_fattura(fattura, metodi, "")[0] == "banca"


def test_all_import_entro_la_data_nessuna_registrazione_dal_metodo(db):
    from app.routers.invoices.fatture_upload import auto_registra_prima_nota

    _report(db, "2026-09-18")
    run(db["fornitori"].insert_one({"id": 1, "partita_iva": "01234567890", "metodo_pagamento": "banca"}))
    fattura = {"id": "f1", "supplier_vat": "01234567890", "invoice_date": "2026-09-10", "total_amount": 100}
    assert run(auto_registra_prima_nota(db, fattura, "banca")) is None
    assert run(db["prima_nota_banca"].count_documents({})) == 0


def test_il_file_non_riscrive_il_metodo_impostato(db, monkeypatch):
    from app.services import metodi_pagamento_fornitori as metodi
    from app.services.pagamenti_dichiarati_titolare import _aggiorna_fornitori

    run(db["fornitori"].insert_many([
        {"id": 1, "partita_iva": "01111111111", "metodo_pagamento": "banca"},
        {"id": 2, "partita_iva": "02222222222", "metodo_pagamento": ""},
    ]))
    inviati = []

    async def finto_importa(_db, dati, **_k):
        inviati.extend(dati["fornitori"])
        return {"applicati": len(dati["fornitori"]), "fornitori_non_trovati": []}

    monkeypatch.setattr(metodi, "importa", finto_importa)
    righe = [
        {"supplier_vat": "01111111111", "supplier_name": "Impostato", "metodo_pagamento_titolare": "cassa"},
        {"supplier_vat": "02222222222", "supplier_name": "Vuoto", "metodo_pagamento_titolare": "cassa"},
    ]
    esito = run(_aggiorna_fornitori(db, righe, dry_run=False))
    assert [d["partita_iva"] for d in inviati] == ["02222222222"]
    assert esito["metodi_gia_impostati_non_toccati"] == 1
