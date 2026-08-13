import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.routers.prima_nota_module import cassa, stats
from app.services.prima_nota_sumup_projection import (
    applica_proiezione_ai_movimenti,
    giorno_corrente_negozio,
    leggi_proiezione_sumup_cassa,
    leggi_proiezioni_sumup_cassa,
)


def _run(awaitable):
    return asyncio.run(awaitable)


def _evidenza(data, importo=635.80):
    return {
        "id": "sumup-api-oggi",
        "data": data,
        "gestore": "sumup",
        "source": "api_gestore_pos",
        "fonte_dato": "api",
        "stato_dato": "confermato",
        "importo": importo,
        "updated_at": f"{data}T15:00:00+00:00",
    }


def _riga_cassa(data, ident="cassa-sumup-oggi", importo=116.90):
    return {
        "id": ident,
        "data": data,
        "tipo": "uscita",
        "importo": importo,
        "categoria": "POS SUMUP Verso Banca",
        "descrizione": "POS SUMUP snapshot precedente",
        "status": "active",
    }


def test_proiezione_sumup_aggiorna_la_risposta_senza_riscrivere_il_db():
    db = AsyncMongoMockClient()["sumup_live_projection_test"]
    oggi = giorno_corrente_negozio()
    _run(db["chiusure_pos_manuali"].insert_one(_evidenza(oggi)))
    _run(db["prima_nota_cassa"].insert_one(_riga_cassa(oggi)))

    proiezione = _run(leggi_proiezione_sumup_cassa(db, oggi))
    righe_api = applica_proiezione_ai_movimenti([_riga_cassa(oggi)], proiezione)
    persistita = _run(db["prima_nota_cassa"].find_one({"id": "cassa-sumup-oggi"}))

    assert proiezione["applicabile"] is True
    assert proiezione["delta"] == 518.90
    assert righe_api[0]["importo"] == 635.80
    assert righe_api[0]["importo_persistito"] == 116.90
    assert righe_api[0]["non_modificabile"] is True
    assert persistita["importo"] == 116.90


def test_proiezione_sumup_non_accorpa_due_righe_ambigue():
    db = AsyncMongoMockClient()["sumup_live_ambiguous_test"]
    oggi = giorno_corrente_negozio()
    _run(db["chiusure_pos_manuali"].insert_one(_evidenza(oggi)))
    _run(db["prima_nota_cassa"].insert_many([
        _riga_cassa(oggi, "duplicato-1"),
        _riga_cassa(oggi, "duplicato-2"),
    ]))

    proiezione = _run(leggi_proiezione_sumup_cassa(db, oggi))

    assert proiezione["applicabile"] is False
    assert proiezione["stato"] == "righe_persistite_ambigue"
    assert proiezione["movimento_ids"] == ["duplicato-1", "duplicato-2"]


def test_dashboard_usa_il_totale_sumup_live_senza_modificare_la_riga(monkeypatch):
    db = AsyncMongoMockClient()["sumup_live_dashboard_test"]
    oggi = giorno_corrente_negozio()
    monkeypatch.setattr(stats.Database, "get_db", staticmethod(lambda: db))
    _run(db["chiusure_pos_manuali"].insert_one(_evidenza(oggi)))
    _run(db["prima_nota_cassa"].insert_one(_riga_cassa(oggi)))

    risultato = _run(stats.get_prima_nota_stats(
        data_da=f"{oggi[:4]}-01-01", data_a=f"{oggi[:4]}-12-31",
    ))
    persistita = _run(db["prima_nota_cassa"].find_one({"id": "cassa-sumup-oggi"}))

    assert risultato["cassa"]["uscite"] == 635.80
    assert risultato["cassa"]["saldo"] == -635.80
    assert risultato["sumup_cassa_live"]["delta"] == 518.90
    assert persistita["importo"] == 116.90


def test_endpoint_cassa_mostra_il_totale_sumup_live_e_conserva_lo_snapshot(monkeypatch):
    db = AsyncMongoMockClient()["sumup_live_cassa_endpoint_test"]
    oggi = giorno_corrente_negozio()
    monkeypatch.setattr(cassa.Database, "get_db", staticmethod(lambda: db))
    async def saldi_prima_della_proiezione(*_args, **_kwargs):
        return {
            "saldo": -116.90,
            "saldo_anno": -116.90,
            "saldo_precedente": 0.0,
            "saldo_iniziale_manuale": False,
            "totale_entrate": 0.0,
            "totale_uscite": 116.90,
        }
    monkeypatch.setattr(cassa, "aggrega_saldo_prima_nota", saldi_prima_della_proiezione)
    _run(db["chiusure_pos_manuali"].insert_one(_evidenza(oggi)))
    _run(db["prima_nota_cassa"].insert_one(_riga_cassa(oggi)))

    risultato = _run(cassa.list_prima_nota_cassa(
        skip=0,
        limit=10000,
        anno=int(oggi[:4]),
        data_da=None,
        data_a=None,
        tipo=None,
        categoria=None,
    ))
    persistita = _run(db["prima_nota_cassa"].find_one({"id": "cassa-sumup-oggi"}))

    assert risultato["movimenti"][0]["importo"] == 635.80
    assert risultato["movimenti"][0]["importo_persistito"] == 116.90
    assert risultato["totale_uscite"] == 635.80
    assert risultato["saldo_anno"] == -635.80
    assert risultato["sumup_live"]["stato"] == "periodo_sumup_archiviato"
    assert risultato["sumup_live"]["giornate"][0]["stato"] == "aggiornato_live"
    assert persistita["importo"] == 116.90


def test_periodo_sumup_corregge_11_e_aggiunge_12_senza_scrivere(monkeypatch):
    db = AsyncMongoMockClient()["sumup_period_projection_test"]
    _run(db["prima_nota_cassa"].insert_one(_riga_cassa(
        "2026-08-11", ident="legacy-11", importo=116.90
    )))
    transazioni = [
        {"data": "2026-08-11", "tipo": "PAYMENT", "stato": "SUCCESSFUL", "importo": 1407.10},
        {"data": "2026-08-12", "tipo": "PAYMENT", "stato": "SUCCESSFUL", "importo": 1522.20},
    ]

    async def archiviate(*_args, **_kwargs):
        return transazioni

    from app.services import prima_nota_sumup_projection as projection
    monkeypatch.setattr(projection.sumup_sync, "transazioni_del_periodo", archiviate)
    monkeypatch.setattr(projection.sumup_sync, "TIPO_VENDITA", "PAYMENT")
    monkeypatch.setattr(projection.sumup_sync, "STATO_VALIDO", "SUCCESSFUL")

    proiezioni = _run(leggi_proiezioni_sumup_cassa(
        db, "2026-08-11", "2026-08-12"
    ))
    movimenti = [_riga_cassa("2026-08-11", ident="legacy-11", importo=116.90)]
    for proiezione in proiezioni:
        movimenti = applica_proiezione_ai_movimenti(movimenti, proiezione)

    per_data = {m["data"]: m for m in movimenti}
    assert per_data["2026-08-11"]["importo"] == 1407.10
    assert per_data["2026-08-11"]["importo_persistito"] == 116.90
    assert per_data["2026-08-12"]["importo"] == 1522.20
    assert per_data["2026-08-12"]["virtuale"] is True
    persistita = _run(db["prima_nota_cassa"].find_one({"id": "legacy-11"}))
    assert persistita["importo"] == 116.90
