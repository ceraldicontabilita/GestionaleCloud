"""Lo stesso F24 da due PDF: un modello solo, la copia in quarantena."""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services import f24_doppioni as dop
from app.services.f24_canonico import salva_f24


def run(coro):
    return asyncio.run(coro)


def _f24(id_, file_name, saldo=497363, righe=(("1001", "03/2026", 94079, 0),), **kw):
    return {
        "id": id_, "file_name": file_name, "status": kw.pop("status", "da_pagare"),
        "codice_fiscale": "04523831214", "created_at": kw.pop("created_at", "2026-09-13T02:19:00"),
        "dati_generali": {"data_versamento": kw.pop("versamento", "2026-04-16")},
        "totali": {"saldo_netto_cents": saldo},
        "sezione_erario": [
            {"codice_tributo": c, "periodo_riferimento": p, "anno": p[-4:], "mese": p[:2],
             "importo_debito_cents": d, "importo_credito_cents": cr} for c, p, d, cr in righe
        ],
        **kw,
    }


def test_la_copia_non_pagata_va_in_quarantena_e_resta_quella_pagata():
    db = AsyncMongoMockClient()["t"]
    pagato = _f24("pagato", "2026-03 Marzo - F24.pdf", movimento_bancario_id="mov",
                  data_pagamento_effettivo="2026-04-16", created_at="2026-09-13T02:19:30", status="pagato")
    copia = _f24("copia", "2026-03 Marzo - F24 (2).pdf", created_at="2026-09-13T02:18:00")
    diverso = _f24("diverso", "altro.pdf", saldo=100, righe=(("1001", "02/2026", 100, 0),))
    run(db[dop.COLL].insert_many([pagato, copia, diverso]))

    prova = run(dop.metti_in_quarantena(db, dry_run=True))
    assert prova["in_quarantena"] == 1 and prova["modelli"][0]["doppione_di"] == "pagato"
    assert run(db[dop.COLL].find_one({"id": "copia"}))["status"] == "da_pagare"   # dry_run non scrive

    run(dop.metti_in_quarantena(db, dry_run=False))
    q = run(db[dop.COLL].find_one({"id": "copia"}, {"_id": 0}))
    assert q["status"] == "eliminato" and q["motivo_quarantena"] == "doppione"
    assert q["doppione_di"] == "pagato" and q["stato_prima_della_quarantena"] == "da_pagare"
    assert run(db[dop.COLL].find_one({"id": "pagato"}))["status"] == "pagato"
    assert run(db[dop.COLL].find_one({"id": "diverso"}))["status"] == "da_pagare"
    # Seconda passata: niente da fare.
    assert run(dop.metti_in_quarantena(db, dry_run=False))["in_quarantena"] == 0


def test_stesso_saldo_ma_righe_diverse_non_e_un_doppione():
    a = _f24("a", "a.pdf", righe=(("1001", "03/2026", 94079, 0),))
    b = _f24("b", "b.pdf", righe=(("1001", "02/2026", 94079, 0),))
    assert dop.trova_doppioni([a, b]) == []


def test_senza_righe_non_si_decide_nulla():
    a = _f24("a", "a.pdf", righe=())
    b = _f24("b", "b.pdf", righe=())
    assert dop.trova_doppioni([a, b]) == []


def test_l_import_dello_stesso_f24_da_un_altro_pdf_non_crea_un_secondo_modello():
    db = AsyncMongoMockClient()["t"]
    primo = _f24(None, "2026-03 Marzo - F24.pdf", pdf_hash="h1", drive_file_id="d1")
    primo.pop("id")
    id1 = run(salva_f24(db, primo, source="cartella_unica"))
    secondo = _f24(None, "Stampa modello F24 di controllo.pdf", pdf_hash="h2", drive_file_id="d2")
    secondo.pop("id")
    id2 = run(salva_f24(db, secondo, source="cartella_unica"))
    assert id1 == id2
    assert run(db[dop.COLL].count_documents({})) == 1
    doc = run(db[dop.COLL].find_one({"id": id1}, {"_id": 0}))
    assert [p["drive_file_id"] for p in doc["source_occurrences"]] == ["d2"]
    # Lo stesso file rivisto non aggiunge provenienze.
    terzo = _f24(None, "Stampa modello F24 di controllo.pdf", pdf_hash="h2", drive_file_id="d2")
    terzo.pop("id")
    run(salva_f24(db, terzo, source="cartella_unica"))
    assert len(run(db[dop.COLL].find_one({"id": id1}))["source_occurrences"]) == 1
