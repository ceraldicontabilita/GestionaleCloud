"""PR 12 — un solo registro F24 / quietanze / banca.

`verifica-codice` legge i modelli, le quietanze reali (`fiscal_documents`
+ collezione storica) e gli addebiti bancari; `riconcilia-addebiti` aggancia
addebito I24 ↔ F24 per data ±3 gg + importo esatto e quietanza ↔ F24 per
protocollo o data+importo esatto, mai per solo importo, idempotente, con
dry-run. I casi ambigui restano proposte.
"""
import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import f24_controllo_incrociato as ctrl
from app.services.sheets_document_store import MemorySheetsClient


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
    return MemorySheetsClient()["registro_f24"]


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
    app = FastAPI()
    app.include_router(f24_riconciliazione.router, prefix="/api/f24-riconciliazione")
    res = TestClient(app).get("/api/f24-riconciliazione/verifica-codice/1001?anno=2019&mese=10")
    assert res.status_code == 200, res.text
    corpo = res.json()
    assert corpo["righe_f24"][0]["esito"] == "DA_PAGARE"
    assert corpo["pagato"] is False and corpo["pagamenti"] == []
    assert corpo["in_attesa"][0]["f24_id"] == "f-1"


def test_riconcilia_addebiti_dry_run_non_scrive_e_applica_e_idempotente():
    db = _db()
    _run(db.f24_unificato.insert_one(_f24("f-a", "2026-01-16", 5600.93, [("1001", "12/2025", 5600.93)])))
    _run(db.f24_unificato.insert_one(_f24("f-b", "2026-02-16", 7465.55, [("6001", "2026", 7465.55)],
                                          protocollo_telematico="26021611115538828-000001")))
    _run(db.estratto_conto_movimenti.insert_one(_mov("mov-1", "2026-01-16", 5600.93)))
    _run(db.estratto_conto_movimenti.insert_one(_mov("mov-2", "2026-02-17", 7465.55)))  # +1 giorno
    _run(db.estratto_conto_movimenti.insert_one(_mov("mov-orfano", "2026-03-16", 915.00)))
    _run(db.fiscal_documents.insert_one({
        "id": "fdoc_b", "category": "quietanza_f24",
        "filename": "2026-02-16__F24_004__quietanza_AE__prot_26021611115538828-000001.pdf",
    }))
    _run(db.fiscal_documents.insert_one({
        "id": "fdoc_senza", "category": "quietanza_f24",
        "filename": "2026-03-16__F24_006__quietanza_AE__prot_26031635562559590-000001.pdf",
    }))

    piano = _run(ctrl.riconcilia_addebiti(db, dry_run=True))
    assert piano["dry_run"] is True and piano["applicate"] == {"banca": 0, "quietanze": 0}
    assert {(p["f24_id"], p["movimento_id"]) for p in piano["banca"]["proposte"]} == {("f-a", "mov-1"), ("f-b", "mov-2")}
    assert piano["banca"]["proposte"][0]["criterio"] == "data_±3gg_e_importo_esatto"
    assert [q["quietanza_id"] for q in piano["quietanze"]["proposte"]] == ["fdoc_b"]
    assert piano["quietanze"]["proposte"][0]["criterio"] == "protocollo"
    assert [q["quietanza_id"] for q in piano["quietanze"]["senza_modello"]] == ["fdoc_senza"]
    assert [m["movimento_id"] for m in piano["addebiti_senza_modello"]] == ["mov-orfano"]
    assert piano["addebiti_senza_modello"][0]["alert"] == "F24_MANCANTE"
    assert piano["conteggi"]["importo_addebiti_senza_modello"] == 915.0
    f24_a = _run(db.f24_unificato.find_one({"id": "f-a"}, {"_id": 0}))
    assert f24_a["pagato"] is False and "movimento_bancario_id" not in f24_a  # dry-run: nulla scritto

    esito = _run(ctrl.riconcilia_addebiti(db, dry_run=False))
    assert esito["applicate"] == {"banca": 2, "quietanze": 1}
    f24_a = _run(db.f24_unificato.find_one({"id": "f-a"}, {"_id": 0}))
    assert f24_a["pagato"] is True and f24_a["movimento_bancario_id"] == "mov-1"
    assert f24_a["stato_pagamento"] == "PAGATO" and f24_a["data_pagamento_effettivo"] == "2026-01-16"
    f24_b = _run(db.f24_unificato.find_one({"id": "f-b"}, {"_id": 0}))
    assert f24_b["quietanza_id"] == "fdoc_b" and f24_b["quietanza_fonte"] == "fiscal_documents"
    assert f24_b["pagato"] is True  # la quietanza non declassa la prova bancaria gia' agganciata
    mov1 = _run(db.estratto_conto_movimenti.find_one({"id": "mov-1"}, {"_id": 0}))
    assert mov1["riconciliato"] is True and mov1["f24_ids"] == ["f-a"] and mov1["tipo_riconciliazione"] == "f24_tributi"
    quietanza = _run(db.fiscal_documents.find_one({"id": "fdoc_b"}, {"_id": 0}))
    assert quietanza["f24_id"] == "f-b"

    di_nuovo = _run(ctrl.riconcilia_addebiti(db, dry_run=False))
    assert di_nuovo["applicate"] == {"banca": 0, "quietanze": 0}
    assert di_nuovo["banca"]["proposte"] == [] and di_nuovo["quietanze"]["proposte"] == []
    assert di_nuovo["conteggi"]["f24_senza_prova_bancaria"] == 0


def test_ambigui_restano_proposte_mai_per_solo_importo():
    db = _db()
    # stesso importo, stessa data: due addebiti per un modello → ambiguo
    _run(db.f24_unificato.insert_one(_f24("f-dup", "2026-03-16", 781.60, [("3802", "2025", 781.60)])))
    _run(db.estratto_conto_movimenti.insert_one(_mov("mov-x", "2026-03-16", 781.60)))
    _run(db.estratto_conto_movimenti.insert_one(_mov("mov-y", "2026-03-16", 781.60)))
    # importo uguale ma 20 giorni di distanza: nessun aggancio per solo importo
    _run(db.f24_unificato.insert_one(_f24("f-lontano", "2026-01-16", 535.70, [("1040", "12/2025", 535.70)])))
    _run(db.estratto_conto_movimenti.insert_one(_mov("mov-lontano", "2026-02-05", 535.70)))
    # quietanza con stessa data ma importo diverso → nessun match
    _run(db.fiscal_documents.insert_one({
        "id": "fdoc_x", "category": "quietanza_f24",
        "filename": "2026-01-16__F24_001__quietanza_AE__prot_9999.pdf", "metadata": {"importo": 535.71},
    }))

    piano = _run(ctrl.riconcilia_addebiti(db, dry_run=False))
    assert piano["applicate"] == {"banca": 0, "quietanze": 0}
    assert [a["f24_id"] for a in piano["banca"]["ambigue"]] == ["f-dup"]
    assert "duplicato" in piano["banca"]["ambigue"][0]["motivo"]
    assert {m["movimento_id"] for m in piano["addebiti_senza_modello"]} == {"mov-lontano"}
    assert [q["quietanza_id"] for q in piano["quietanze"]["senza_modello"]] == ["fdoc_x"]
    for fid in ("f-dup", "f-lontano"):
        f24 = _run(db.f24_unificato.find_one({"id": fid}, {"_id": 0}))
        assert f24["pagato"] is False and "movimento_bancario_id" not in f24


def test_endpoint_riconcilia_addebiti_richiede_admin_e_default_dry_run(monkeypatch):
    from app.database import Database
    from app.routers.f24 import avviso_bonario
    from app.utils.dependencies import get_current_admin_user

    db = _db()
    _run(db.f24_unificato.insert_one(_f24("f-a", "2026-01-16", 5600.93, [("1001", "12/2025", 5600.93)])))
    _run(db.estratto_conto_movimenti.insert_one(_mov("mov-1", "2026-01-16", 5600.93)))
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(avviso_bonario.router, prefix="/api/f24")
    client = TestClient(app)

    assert client.post("/api/f24/riconcilia-addebiti").status_code in (401, 403)

    app.dependency_overrides[get_current_admin_user] = lambda: {"sub": "a", "role": "admin"}
    res = client.post("/api/f24/riconcilia-addebiti")
    assert res.status_code == 200 and res.json()["dry_run"] is True
    assert _run(db.f24_unificato.find_one({"id": "f-a"}, {"_id": 0}))["pagato"] is False

    res = client.post("/api/f24/riconcilia-addebiti?dry_run=false")
    assert res.json()["applicate"]["banca"] == 1
    assert _run(db.f24_unificato.find_one({"id": "f-a"}, {"_id": 0}))["pagato"] is True


def test_parser_estratto_conto_usa_la_data_canonica_dei_movimenti():
    """Prima leggeva solo `data_contabile`: i movimenti reali hanno `data`."""
    from app.services.estratto_conto_bpm_parser import riconcilia_f24_con_estratto

    f24 = _f24("f-a", "2026-01-16", 5600.93, [("1001", "12/2025", 5600.93)])
    esito = riconcilia_f24_con_estratto([f24], [_mov("mov-1", "2026-01-16", 5600.93)])
    assert esito["stats"]["riconciliati"] == 1
    assert esito["f24_riconciliati"][0]["movimento_bancario"]["id"] == "mov-1"


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
