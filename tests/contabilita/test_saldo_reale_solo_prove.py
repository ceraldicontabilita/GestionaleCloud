"""Il saldo reale del conto BPM conta solo il denaro che la banca ha mosso.

- una riga senza prova dell'estratto (pagamento dichiarato, riga provvisoria)
  resta in elenco ma fuori dal saldo reale;
- una riga ``DA_VERIFICARE`` o ``archiviata`` non conta in nessun saldo;
- il filtro canonico della banca e' il solo BPM: la Mastercard SumUp ha il
  suo saldo, e chi somma la liquidita' lo chiede con ``TUTTI_I_CONTI``;
- un pagamento dichiarato con carta o PayPal non e' mai BPM, nemmeno senza
  ``conto_contabile``.
"""
import asyncio

from app.routers.prima_nota_module import banca
from app.routers.prima_nota_module.common import (
    TUTTI_I_CONTI,
    aggrega_saldo_prima_nota,
    filtro_saldo_prima_nota,
    saldi_finanziari,
)
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

DATA = "2026-08-06"


def _run(awaitable):
    return asyncio.run(awaitable)


def _db(nome):
    return ClientArchivioMemoria()[nome]


def _riga(id_, importo, tipo="uscita", **extra):
    return {"id": id_, "data": DATA, "anno": 2026, "tipo": tipo, "importo": importo,
            "categoria": "Fatture", "source": "estratto_conto", **extra}


def _scheda(saldi, nome):
    return next(v for v in saldi["conti_reali"] if v["nome"] == nome)


def _ids(db, collezione, query):
    return sorted(r["id"] for r in _run(db[collezione].find(query, {"_id": 0}).to_list(None)))


def test_il_pagamento_dichiarato_resta_fuori_dal_saldo_reale_bpm():
    db = _db("saldo_reale_dichiarato")
    _run(db["prima_nota_banca"].insert_many([
        _riga("provata", 100.0, estratto_conto_id="ec-1"),
        _riga("dichiarata", 40.0, dichiarato_titolare=True, stato="DA_VERIFICARE",
              in_attesa_estratto_ufficiale=True, metodo_pagamento_dichiarato="banca"),
    ]))
    saldi = _run(saldi_finanziari(db))
    assert _scheda(saldi, "Banca BPM")["saldo"] == -100.0


def test_la_lista_banca_mostra_la_riga_dichiarata_ma_non_la_somma(monkeypatch):
    db = _db("saldo_reale_lista")
    monkeypatch.setattr(banca.Database, "get_db", staticmethod(lambda: db))
    viste = {}

    async def _aggrega(db_corrente, collection, query, anno, query_base_precedente=None):
        righe = await db_corrente[collection].find(query, {"_id": 0}).to_list(None)
        viste["saldo"] = sorted(r["id"] for r in righe)
        return {"saldo": 0.0, "saldo_anno": 0.0, "saldo_precedente": 0.0,
                "saldo_iniziale_manuale": False, "totale_entrate": 0.0, "totale_uscite": 0.0}

    monkeypatch.setattr(banca, "aggrega_saldo_prima_nota", _aggrega)
    _run(db["prima_nota_banca"].insert_many([
        _riga("provata", 100.0, estratto_conto_id="ec-1"),
        _riga("dichiarata", 40.0, in_attesa_estratto_ufficiale=True),
    ]))
    risultato = _run(banca.list_prima_nota_banca(
        skip=0, limit=100, anno=2026, data_da=None, data_a=None, tipo=None, categoria=None,
    ))
    assert sorted(r["id"] for r in risultato["movimenti"]) == ["dichiarata", "provata"]
    assert viste["saldo"] == ["provata"]


def test_da_verificare_e_archiviata_non_contano_in_nessun_saldo():
    db = _db("saldo_stati")
    for collezione in ("prima_nota_cassa", "prima_nota_banca"):
        _run(db[collezione].insert_many([
            _riga("buona", 10.0),
            _riga("archiviata", 20.0, status="archiviata"),
            _riga("status-da-verificare", 30.0, status="DA_VERIFICARE"),
            _riga("stato-da-verificare", 40.0, stato="DA_VERIFICARE"),
        ]))
        assert _ids(db, collezione, filtro_saldo_prima_nota(collezione)) == ["buona"]


def test_il_filtro_della_banca_e_il_solo_bpm():
    db = _db("saldo_conti")
    _run(db["prima_nota_banca"].insert_many([
        _riga("storica", 10.0),
        _riga("bpm", 20.0, conto_contabile="19.01.01"),
        _riga("carta", 30.0, conto_contabile="19.01.05"),
    ]))
    bpm = filtro_saldo_prima_nota("prima_nota_banca")
    assert _ids(db, "prima_nota_banca", bpm) == ["bpm", "storica"]
    tutti = filtro_saldo_prima_nota("prima_nota_banca", conto=TUTTI_I_CONTI)
    assert _ids(db, "prima_nota_banca", tutti) == ["bpm", "carta", "storica"]
    # Il conto esplicito del chiamante vince, come prima.
    carta = filtro_saldo_prima_nota("prima_nota_banca", conto_contabile="19.01.05")
    assert _ids(db, "prima_nota_banca", carta) == ["carta"]


def test_il_riporto_e_dello_stesso_conto_dell_anno():
    db = _db("saldo_riporto")
    _run(db["prima_nota_banca"].insert_many([
        {**_riga("bpm-2025", 100.0, tipo="entrata"), "data": "2025-12-01", "anno": 2025},
        {**_riga("carta-2025", 50.0, tipo="entrata", conto_contabile="19.01.05"),
         "data": "2025-12-01", "anno": 2025},
    ]))

    async def _saldi(conto):
        from app.routers.prima_nota_module import common

        query = common.filtro_saldo_prima_nota(
            "prima_nota_banca", **({} if conto == "bpm" else {"conto": TUTTI_I_CONTI}),
            data={"$gte": "2026-01-01", "$lte": "2026-12-31"},
        )
        return await aggrega_saldo_prima_nota(db, "prima_nota_banca", query, 2026)

    assert _run(_saldi("bpm"))["saldo_precedente"] == 100.0
    assert _run(_saldi("tutti"))["saldo_precedente"] == 150.0


def test_un_pagamento_dichiarato_con_carta_o_paypal_non_e_bpm():
    db = _db("saldo_dichiarati_carta")
    _run(db["prima_nota_banca"].insert_many([
        _riga("bonifico", 100.0),
        _riga("carta", 40.0, metodo_pagamento_dichiarato="carta"),
        _riga("paypal", 25.0, metodo_pagamento_dichiarato="paypal"),
    ]))
    saldi = _run(saldi_finanziari(db))
    assert _scheda(saldi, "Banca BPM")["saldo"] == -100.0
