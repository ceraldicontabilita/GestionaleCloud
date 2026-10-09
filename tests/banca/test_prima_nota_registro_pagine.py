"""Prima Nota a pagine: saldo progressivo, filtri e totali sul server.

La pagina chiedeva 10.000 righe e calcolava ordine, saldo di ogni riga e
ricerca nel browser. Ora lo fa ``registro.py``: questi test provano che le
pagine messe in fila danno lo stesso registro dell'elenco intero e che i
totali della testata non dipendono da quante righe si caricano.
"""
import asyncio
from decimal import Decimal

from app.routers.prima_nota_module import banca, cassa, registro
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(awaitable):
    return asyncio.run(awaitable)


def _aggrega_python(riporto):
    async def _aggrega(db_corrente, collection, query, anno, query_base_precedente=None):
        documenti = await db_corrente[collection].find(query, {"_id": 0}).to_list(None)
        entrate = sum(Decimal(str(d.get("importo") or 0)) for d in documenti if d.get("tipo") == "entrata")
        uscite = sum(Decimal(str(d.get("importo") or 0)) for d in documenti if d.get("tipo") == "uscita")
        return {
            "saldo": float(riporto + entrate - uscite),
            "saldo_anno": float(entrate - uscite),
            "saldo_precedente": float(riporto),
            "saldo_iniziale_manuale": True,
            "totale_entrate": float(entrate),
            "totale_uscite": float(uscite),
        }
    return _aggrega


RIGHE_CASSA = [
    {"id": "c1", "data": "2026-01-02", "anno": 2026, "tipo": "entrata", "importo": 100.10,
     "categoria": "Corrispettivi", "descrizione": "Corrispettivo 02/01"},
    {"id": "c2", "data": "2026-01-02", "anno": 2026, "tipo": "uscita", "importo": 30.05,
     "categoria": "Versamento Banca", "descrizione": "Versamento"},
    {"id": "c3", "data": "2026-01-02", "anno": 2026, "tipo": "uscita", "importo": 12.00,
     "categoria": "Fatture", "descrizione": "Pagamento fattura 7/A - Forno Rossi",
     "numero_fattura": "7/A", "created_at": "2026-01-02T10:00:00"},
    {"id": "c4", "data": "2026-02-10", "anno": 2026, "tipo": "entrata", "importo": 250.00,
     "categoria": "Corrispettivi", "descrizione": "Corrispettivo 10/02"},
    {"id": "c5", "data": "2026-02-11", "anno": 2026, "tipo": "uscita", "importo": 40.33,
     "categoria": "2019", "descrizione": "Movimento storico"},
    {"id": "c6", "data": "2026-03-01", "anno": 2026, "tipo": "entrata", "importo": 5.55,
     "categoria": "Altro", "descrizione": "Assegno", "numero_assegno": "AB123"},
]


def _db_cassa(monkeypatch, riporto=Decimal("1000.00")):
    db = ClientArchivioMemoria()["prima_nota_registro_test"]
    monkeypatch.setattr(cassa.Database, "get_db", staticmethod(lambda: db))
    monkeypatch.setattr(cassa, "aggrega_saldo_prima_nota", _aggrega_python(riporto))
    _run(db["prima_nota_cassa"].insert_many([dict(r) for r in RIGHE_CASSA]))
    return db


def _lista_cassa(**kwargs):
    base = dict(skip=0, limit=200, anno=2026, data_da=None, data_a=None, tipo=None, categoria=None)
    base.update(kwargs)
    return _run(cassa.list_prima_nota_cassa(**base))


def test_pagine_in_fila_uguali_all_elenco_intero(monkeypatch):
    _db_cassa(monkeypatch)
    intero = _lista_cassa()
    assert intero["totale"] == len(RIGHE_CASSA)
    assert intero["count"] == len(RIGHE_CASSA)

    righe = []
    for skip in range(0, len(RIGHE_CASSA), 2):
        pagina = _lista_cassa(skip=skip, limit=2)
        assert pagina["totale"] == len(RIGHE_CASSA)
        # La testata e' la stessa su ogni pagina: non dipende dalle righe caricate.
        assert (pagina["totale_entrate"], pagina["totale_uscite"], pagina["saldo"]) == (
            intero["totale_entrate"], intero["totale_uscite"], intero["saldo"])
        righe.extend(pagina["movimenti"])
    assert [(r["id"], r["saldo_progressivo"]) for r in righe] == [
        (r["id"], r["saldo_progressivo"]) for r in intero["movimenti"]]


def test_totali_uguali_alla_somma_di_tutte_le_righe(monkeypatch):
    _db_cassa(monkeypatch)
    risposta = _lista_cassa(limit=2)
    entrate = sum(Decimal(str(r["importo"])) for r in RIGHE_CASSA if r["tipo"] == "entrata")
    uscite = sum(Decimal(str(r["importo"])) for r in RIGHE_CASSA if r["tipo"] == "uscita")
    assert Decimal(str(risposta["totale_entrate"])) == entrate
    assert Decimal(str(risposta["totale_uscite"])) == uscite
    # La riga piu' recente porta il saldo finale: riporto + entrate - uscite.
    assert Decimal(str(risposta["movimenti"][0]["saldo_progressivo"])) == Decimal("1000.00") + entrate - uscite
    assert Decimal(str(risposta["saldo"])) == Decimal("1000.00") + entrate - uscite


def test_ordine_a_video_e_saldo_dal_riporto(monkeypatch):
    _db_cassa(monkeypatch)
    risposta = _lista_cassa()
    # Dal piu' recente; nella giornata corrispettivo, fatture, versamento.
    assert [r["id"] for r in risposta["movimenti"]] == ["c6", "c5", "c4", "c1", "c3", "c2"]
    saldi = {r["id"]: r["saldo_progressivo"] for r in risposta["movimenti"]}
    # In fondo al registro: riporto - versamento (ultima riga del 02/01).
    assert saldi["c2"] == 969.95
    assert saldi["c3"] == 957.95
    assert saldi["c1"] == 1058.05
    netti = {r["id"]: r["netto_giorno"] for r in risposta["movimenti"]}
    assert netti["c1"] == netti["c2"] == 58.05


def test_filtri_scelgono_le_righe_non_il_saldo(monkeypatch):
    _db_cassa(monkeypatch)
    intero = _lista_cassa()
    saldi = {r["id"]: r["saldo_progressivo"] for r in intero["movimenti"]}

    gennaio = _lista_cassa(mese=1)
    assert [r["id"] for r in gennaio["movimenti"]] == ["c1", "c3", "c2"]
    assert gennaio["totale"] == 3
    assert gennaio["totale_entrate"] == intero["totale_entrate"]
    assert all(r["saldo_progressivo"] == saldi[r["id"]] for r in gennaio["movimenti"])

    storici = _lista_cassa(filtro_categoria=registro.CATEGORIA_STORICA)
    assert [r["id"] for r in storici["movimenti"]] == ["c5"]
    assert intero["categorie"] == ["Altro", "Corrispettivi", "Fatture", "Versamento Banca",
                                   registro.CATEGORIA_STORICA]

    assert [r["id"] for r in _lista_cassa(filtro_tipo="entrata")["movimenti"]] == ["c6", "c4", "c1"]
    assert [r["id"] for r in _lista_cassa(cerca="ab123")["movimenti"]] == ["c6"]
    assert [r["id"] for r in _lista_cassa(cerca="250")["movimenti"]] == ["c4"]
    assert [r["id"] for r in _lista_cassa(numero_fattura="7/a", fornitore="forno",
                                          data_fattura="2026-01-02")["movimenti"]] == ["c3"]
    assert _lista_cassa(numero_fattura="7/a", data_fattura="2026-01-03")["movimenti"] == []


def test_fornitore_e_numero_come_nel_registro():
    storica = {"categoria": "Fatture", "numero_fattura": "V1-8016",
               "descrizione": "Pagamento fattura V1-8016 - G.I.A.L. Generale Ingrosso Alimentare S.R.L."}
    assert registro.nome_fornitore(storica) == "G.I.A.L. Generale Ingrosso Alimentare S.R.L."
    assert registro.nome_fornitore({"descrizione": "Versamento - contanti"}) == ""
    prova = [{"id": "PN-1", "movimento_estratto_conto_id": "EC-2026-08-07-23.10-d2ef4678",
              "descrizione": "Pagamento", "importo": 23.10}]
    assert registro.filtra(prova, {"cerca": "EC-2026-08-07-23.10-d2ef4678"}) == prova
    assert registro.e_categoria_storica("5331") and registro.e_categoria_storica(" 5814 ")
    assert not registro.e_categoria_storica("F24")


def test_banca_esclude_dal_saldo_le_stesse_righe_del_saldo_reale():
    for riga in (
        {"natura": "credito_pos", "source": "corrispettivo_pos", "conto_contabile": "15.07.02"},
        {"natura": "costo", "source": "commissioni_sumup"},
        {"source": "trasferimento_pos"},
        {"source": "manuale_banca_senza_evidenza"},
        {"source": "report_pagamenti_titolare", "in_attesa_estratto_ufficiale": True},
        {"categoria": "POS_DUPLICATO"},
    ):
        assert registro.conta_nel_saldo(riga, "banca") is False
    assert registro.conta_nel_saldo({"source": "estratto_conto", "natura": "movimento_bancario_reale"}, "banca")
    assert registro.conta_nel_saldo({"provvisorio": True, "source": "trasferimento_pos"}, "cassa")


def test_banca_pagine_con_saldo_reale(monkeypatch):
    db = ClientArchivioMemoria()["prima_nota_registro_banca_test"]
    monkeypatch.setattr(banca.Database, "get_db", staticmethod(lambda: db))

    async def _aggrega(db_corrente, collection, query, anno, query_base_precedente=None):
        documenti = await db_corrente[collection].find(query, {"_id": 0}).to_list(None)
        entrate = sum(Decimal(str(d["importo"])) for d in documenti if d["tipo"] == "entrata")
        uscite = sum(Decimal(str(d["importo"])) for d in documenti if d["tipo"] == "uscita")
        return {"saldo": float(entrate - uscite), "saldo_anno": float(entrate - uscite),
                "saldo_precedente": 0.0, "saldo_iniziale_manuale": False,
                "totale_entrate": float(entrate), "totale_uscite": float(uscite)}

    monkeypatch.setattr(banca, "aggrega_saldo_prima_nota", _aggrega)
    _run(db["prima_nota_banca"].insert_many([
        {"id": "credito-pos", "data": "2026-08-07", "anno": 2026, "tipo": "entrata",
         "importo": 1000.0, "categoria": "POS NUMIA Verso Banca",
         "source": "trasferimento_pos", "natura": "credito_pos"},
        {"id": "accredito", "data": "2026-08-08", "anno": 2026, "tipo": "entrata",
         "importo": 980.0, "categoria": "Accrediti POS", "source": "estratto_conto"},
        {"id": "uscita", "data": "2026-08-09", "anno": 2026, "tipo": "uscita",
         "importo": 80.0, "categoria": "Bonifico", "source": "estratto_conto"},
    ]))
    argomenti = dict(anno=2026, data_da=None, data_a=None, tipo=None, categoria=None)
    intera = _run(banca.list_prima_nota_banca(skip=0, limit=200, **argomenti))
    prima = _run(banca.list_prima_nota_banca(skip=0, limit=1, **argomenti))
    seconda = _run(banca.list_prima_nota_banca(skip=1, limit=5, **argomenti))

    assert intera["totale"] == prima["totale"] == seconda["totale"] == 3
    assert [r["id"] for r in prima["movimenti"] + seconda["movimenti"]] == [
        r["id"] for r in intera["movimenti"]] == ["uscita", "accredito", "credito-pos"]
    saldi = {r["id"]: r["saldo_progressivo"] for r in intera["movimenti"]}
    # Il credito POS e' in elenco ma non muove il saldo del conto.
    assert saldi == {"credito-pos": 0.0, "accredito": 980.0, "uscita": 900.0}
    assert saldi["uscita"] == intera["saldo"]
    assert {r["id"]: r["conta_nel_saldo"] for r in intera["movimenti"]}["credito-pos"] is False
