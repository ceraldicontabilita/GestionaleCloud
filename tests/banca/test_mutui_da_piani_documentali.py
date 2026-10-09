"""Audit 27/09/2026 (punto 11): la pagina Mutui legge i piani importati.

Il router leggeva ``mutui``, collezione inesistente in produzione: la pagina
era sempre vuota. Il piano vero sta in ``mutui_piani_documentali`` (import
documentale, deduplica SHA-256) e il riscontro della rata con la banca e'
la riga di Prima Nota Banca scritta dalla proiezione bancaria.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.routers import mutui as mod
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _rata(n, scadenza, stato, capitale=900.0, interessi=100.0):
    return {"numero_rata": n, "data_scadenza": scadenza, "importo_totale": capitale + interessi,
            "quota_capitale": capitale, "quota_interessi": interessi, "stato": stato}


def _piano(sha, updated_at, rate):
    return {
        "numero_delibera": "904851906", "tipo_finanziamento": "Mutuo chirografario",
        "importo_accordato": 50000.0, "intestatario": "CERALDI GROUP SRL",
        "rate": rate, "sha256": sha, "filename": f"{sha}.pdf", "updated_at": updated_at,
        "tipo_documento": "piano_ammortamento",
    }


@pytest.fixture
def db(monkeypatch):
    db = ClientArchivioMemoria()["mutui-piani"]
    _run(db["mutui_piani_documentali"].insert_many([
        # versione vecchia del piano: non deve contare
        _piano("vecchio", "2026-01-10T00:00:00+00:00", [
            _rata(1, "24/01/2026", "Da pagare"),
        ]),
        _piano("nuovo", "2026-09-01T00:00:00+00:00", [
            _rata(1, "24/01/2026", "Pagata"),
            _rata(2, "24/02/2026", "Pagata"),
            _rata(3, "24/10/2099", "Da pagare"),
        ]),
    ]))
    # Rata 1 addebitata in banca (riga della proiezione bancaria).
    _run(db["prima_nota_banca"].insert_one({
        "id": "PNB1", "data": "2026-01-24", "importo": 1000.0, "tipo": "uscita",
        "tipo_classificazione_contabile": "rata_mutuo", "numero_mutuo": "1788 4851906",
        "rata_scadenza": "24/01/2026", "movimento_bancario_id": "EC-1",
    }))
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    return db


def test_lista_dai_piani_documentali_una_versione_per_delibera(db):
    esito = _run(mod.get_mutui(skip=0, limit=100))
    assert esito["pagination"]["total"] == 1
    mutuo = esito["data"][0]
    assert mutuo["mutuo_id"] == "mutuo_904851906"
    assert mutuo["totale_rate"] == 3
    assert mutuo["rate_pagate"] == 2 and mutuo["rate_da_pagare"] == 1
    assert mutuo["totale_pagato"] == 2000.0
    assert mutuo["totale_pagato_capitale"] == 1800.0
    assert mutuo["debito_residuo_totale"] == 1000.0
    assert mutuo["prossima_data_scadenza"] == "24/10/2099"
    # Riscontro con la banca: solo la rata 1 ha l'addebito.
    assert mutuo["rate_riconciliate"] == 1
    assert mutuo["percentuale_riconciliazione"] == 50.0
    assert mutuo["rate"][0]["movimento_bancario_id"] == "EC-1"
    assert mutuo["rate"][1]["riconciliata"] is False
    assert esito["statistiche"]["importo_totale_accordato"] == 50000.0


def test_statistiche_dashboard(db):
    stats = _run(mod.get_statistiche_mutui())["data"]
    assert stats["numero_mutui"] == 1
    assert stats["totale_pagato_capitale"] == 1800.0
    assert stats["percentuale_completamento"] == 3.6
    assert stats["rate_da_pagare"] == 1


def test_dettaglio_rate_e_404(db):
    assert len(_run(mod.get_rate_mutuo("mutuo_904851906"))["data"]["rate"]) == 3
    with pytest.raises(HTTPException) as err:
        _run(mod.get_mutuo_by_id("mutuo_inesistente"))
    assert err.value.status_code == 404


def test_riscontro_non_scrive_e_dice_cosa_manca(db):
    prima = _run(db["prima_nota_banca"].count_documents({}))
    esito = _run(mod.riconcilia_mutui_con_estratto_conto())["data"]
    assert esito["totale_rate_processate"] == 2
    assert esito["riconciliazioni_automatiche"] == 1
    assert esito["riconciliazioni_manuali_richieste"] == 1
    assert _run(db["prima_nota_banca"].count_documents({})) == prima


def test_senza_piani_la_lista_e_vuota_non_un_errore(monkeypatch):
    vuoto = ClientArchivioMemoria()["mutui-vuoto"]
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: vuoto))
    assert _run(mod.get_mutui(skip=0, limit=100))["data"] == []
    assert _run(mod.get_statistiche_mutui())["data"]["numero_mutui"] == 0
