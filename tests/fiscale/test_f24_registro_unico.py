"""PR 12 — un solo registro F24 / quietanze / banca.

`verifica-codice` legge i modelli, le quietanze reali (`fiscal_documents`
+ collezione storica) e gli addebiti bancari. L'aggancio addebito ↔ pagamento
e' il motore a livelli `riconcilia_f24_banca` (test_f24_riconciliazione_livelli).
"""
import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import f24_controllo_incrociato as ctrl
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coro):
    return asyncio.run(coro)


def _f24(id_, data, saldo, righe, **extra):
    return {
        "id": id_, "status": "da_pagare", "pagato": False,
        "file_name": f"{data}__F24_{id_}.pdf",
        "dati_generali": {"codice_fiscale": "04523831214", "data_versamento": data},
        "totali": {"saldo_netto": saldo},
        "sezione_erario": [
            {"codice_tributo": c, "periodo_riferimento": p, "importo_debito": i} for c, p, i in righe
        ],
        **extra,
    }


def _mov(id_, data, importo, **extra):
    return {"id": id_, "data": data, "importo": importo, "tipo": "uscita",
            "descrizione": "I24 AGENZIA ENTRATE PAG.TO TELEMATICO", "riconciliato": False, **extra}


def _db():
    return ClientArchivioMemoria()["registro_f24"]


def test_verifica_codice_legge_fiscal_documents_e_banca_non_solo_quietanze_f24():
    db = _db()
    _run(db.f24_unificato.insert_one(_f24(
        "f-2019", "2019-12-20", 2738.28, [("1001", "10/2019", 1455.21), ("1012", "10/2019", 893.71)],
        quietanza_id="fdoc_q", movimento_bancario_id="mov-a", data_pagamento_effettivo="2019-12-20",
    )))
    _run(db.f24_unificato.insert_one(_f24("f-2020", "2020-01-16", 500.0, [("1001", "12/2019", 500.0)])))
    _run(db.fiscal_documents.insert_one({
        "id": "fdoc_q", "category": "quietanza_f24",
        "filename": "2019-12-20__F24_000__quietanza_AE__prot_1912200001-000001.pdf",
    }))
    _run(db.estratto_conto_movimenti.insert_one(_mov("mov-a", "2019-12-20", 2738.28, f24_ids=["f-2019"])))

    tutto = _run(ctrl.verifica_codice(db, "1001"))
    assert [r["f24_id"] for r in tutto["righe_f24"]] == ["f-2020", "f-2019"]
    assert tutto["pagato"] is True
    assert tutto["fonti"]["quietanze_fiscal_documents"] == 1

    ottobre = _run(ctrl.verifica_codice(db, "1001", anno="2019", mese="10"))
    assert ottobre["periodo_cercato"] == "10/2019"
    (riga,) = ottobre["righe_f24"]
    assert riga["esito"] == "COPERTO"
    assert riga["quietanze"][0]["quietanza_id"] == "fdoc_q" and riga["quietanze"][0]["fonte"] == "fiscal_documents"
    assert riga["addebiti_banca"][0]["movimento_id"] == "mov-a"
    assert ottobre["in_attesa"] == []

    dicembre = _run(ctrl.verifica_codice(db, "1001", anno="2019", mese="12"))
    assert dicembre["righe_f24"][0]["esito"] == "DA_PAGARE"
    assert dicembre["in_attesa"][0] == {"f24_id": "f-2020", "scadenza": "2020-01-16",
                                        "scadenza_it": "16/01/2020", "importo": 500.0}


def test_endpoint_verifica_codice_usa_il_registro_unico(monkeypatch):
    from app.database import Database
    from app.routers.f24 import f24_riconciliazione

    db = _db()
    _run(db.f24_unificato.insert_one(_f24("f-1", "2019-12-20", 100.0, [("1001", "10/2019", 100.0)])))
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    from app.utils.dependencies import get_current_admin_user

    app = FastAPI()
    app.include_router(f24_riconciliazione.router, prefix="/api/f24-riconciliazione")
    assert TestClient(app).get("/api/f24-riconciliazione/verifica-codice/1001").status_code in (401, 403)
    app.dependency_overrides[get_current_admin_user] = lambda: {"role": "admin"}
    res = TestClient(app).get("/api/f24-riconciliazione/verifica-codice/1001?anno=2019&mese=10")
    assert res.status_code == 200, res.text
    corpo = res.json()
    assert corpo["righe_f24"][0]["esito"] == "DA_PAGARE"
    assert corpo["pagato"] is False and corpo["pagamenti"] == []
    assert corpo["in_attesa"][0]["f24_id"] == "f-1"


def test_fascicolo_legge_anche_le_quietanze_di_fiscal_documents():
    from app.services import fascicolo_f24 as fasc

    db = _db()
    cf = "04523831214"
    _run(db.f24_unificato.insert_one(_f24("f-6", "2026-07-16", 100.0, [("1001", "06/2026", 100.0)],
                                          quietanza_id="fdoc_a")))
    _run(db.fiscal_documents.insert_one({"id": "fdoc_a", "category": "quietanza_f24", "filename": "a.pdf"}))
    _run(db.fiscal_documents.insert_one({"id": "fdoc_b", "category": "quietanza_f24", "filename": "b.pdf",
                                         "f24_associati": ["f-6"]}))
    _run(db.fiscal_documents.insert_one({"id": "fdoc_altro", "category": "quietanza_f24", "filename": "c.pdf"}))
    fascicolo = _run(fasc.costruisci_fascicolo(db, cf, (6, 2026)))
    assert fascicolo["f24_ids"] == ["f-6"]
    assert sorted(fascicolo["quietanza_ids"]) == ["fdoc_a", "fdoc_b"]
