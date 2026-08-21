import asyncio

import pytest
from fastapi import HTTPException
from app.services.sheets_document_store import MemorySheetsClient

from app.routers.accounting import contabilita_gestionale as cg


def _run(coro):
    return asyncio.run(coro)


def _scrittura(protocollo, dare, avere, *, data_field="data_documento"):
    return {
        "id": f"s-{protocollo}-{dare}-{avere}",
        "anno": 2026,
        "numero_registrazione": protocollo,
        data_field: "2026-03-10",
        "righe": [
            {"conto_codice": "01.01.01", "conto_nome": "Cassa", "dare": dare},
            {"conto_codice": "04.01.01", "conto_nome": "Ricavi", "avere": avere},
        ],
    }


def test_query_periodo_include_entrambe_le_date_senza_perdere_filtro_fattura():
    query = cg._query_periodo_giornale("2026-01-01", "2026-12-31", "fattura-1")

    assert "$and" in query
    assert any(
        "$or" in condizione
        and {"data": {"$gte": "2026-01-01", "$lte": "2026-12-31"}}
        in condizione["$or"]
        for condizione in query["$and"]
    )
    assert any(
        {"invoice_key": "fattura-1"} in condizione.get("$or", [])
        for condizione in query["$and"]
    )


def test_non_confonde_due_sbilanci_opposti_con_un_registro_valido():
    qualita = cg._qualita_scritture_giornale([
        _scrittura(1, 100, 90),
        _scrittura(2, 90, 100),
    ])

    assert qualita["totale_dare"] == qualita["totale_avere"] == 190
    assert qualita["scritture_sbilanciate"] == 2
    assert qualita["registro_valido"] is False


def test_rileva_protocollo_duplicato_e_righe_invalide():
    prima = _scrittura(7, 100, 100)
    seconda = _scrittura(7, 50, 50)
    seconda["righe"].append({"conto_codice": "", "dare": "non-numero"})

    qualita = cg._qualita_scritture_giornale([prima, seconda])

    assert qualita["protocolli_duplicati"] == 1
    assert qualita["righe_non_numeriche"] == 1
    assert qualita["righe_senza_conto"] == 1
    assert qualita["registro_valido"] is False


def test_giornale_include_scrittura_con_solo_campo_data(monkeypatch):
    db = MemorySheetsClient().db
    _run(db.movimenti_contabili.insert_one(_scrittura(1, 84, 84, data_field="data")))
    monkeypatch.setattr(cg.Database, "get_db", lambda: db)

    result = _run(cg.get_libro_giornale(
        data_da="2026-01-01",
        data_a="2026-12-31",
        invoice_key=None,
        limit=2000,
    ))
    mastro = _run(cg.get_libro_mastro("2026-01-01", "2026-12-31"))
    export = _run(cg.export_libro_giornale(2026))

    assert result["totale"] == result["totale_disponibile"] == 1
    assert result["troncato"] is False
    assert result["quadratura"] is True
    assert mastro["scritture_aggregate"] == mastro["totale_scritture"] == 1
    assert mastro["totale_dare"] == mastro["totale_avere"] == 84
    assert export["numero_scritture"] == export["totale_disponibile"] == 1


def test_reimport_corrotto_viene_annullato_prima_di_qualsiasi_scrittura():
    dump = {
        "tipo": "libro_giornale_gestionalecloud",
        "versione": 1,
        "scritture": [_scrittura(1, 100, 90)],
    }

    with pytest.raises(HTTPException) as exc:
        _run(cg.import_libro_giornale(dump, {}))

    assert exc.value.status_code == 422
    assert exc.value.detail["qualita_registro"]["scritture_sbilanciate"] == 1


def test_reimport_valido_e_idempotente(monkeypatch):
    db = MemorySheetsClient().db
    monkeypatch.setattr(cg.Database, "get_db", lambda: db)
    dump = {
        "tipo": "libro_giornale_gestionalecloud",
        "versione": 1,
        "scritture": [_scrittura(1, 100, 100)],
    }

    first = _run(cg.import_libro_giornale(dump, {}))
    second = _run(cg.import_libro_giornale(dump, {}))

    assert first["ricreate"] == 1
    assert second["ricreate"] == 0
    assert second["gia_presenti"] == 1
    assert _run(db.movimenti_contabili.count_documents({})) == 1
