"""Una prova di pagamento della rata regge solo se l'importo torna al centesimo
(entro la tolleranza dichiarata): un pagamento parziale non e' «Pagata»."""
import asyncio
from datetime import date

import pytest

from app.routers import mutui as mod
from app.services import mutui_rate_dichiarate as svc
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

OGGI = date(2026, 9, 30)
MUTUO = "mutuo_905217466"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _p(fonte, importo, identita="x"):
    return {"prova": fonte, "identita": identita, "importo_cents": importo}


def test_importo_uguale_regge():
    v = svc.valuta_prove([_p(svc.PROVA_ESTRATTO, 100000)], 100000)
    assert v["vincente"]["prova"] == svc.PROVA_ESTRATTO
    assert v["vincente"]["differenza_cents"] == 0 and v["non_conforme"] is None


def test_scarto_dentro_la_tolleranza_regge_e_si_vede():
    v = svc.valuta_prove([_p(svc.PROVA_BANCA, 100275)], 100000)  # +2,75 come sul mutuo Retail
    assert v["vincente"]["differenza_cents"] == 275


def test_confine_della_tolleranza_al_centesimo():
    assert svc.valuta_prove([_p(svc.PROVA_BANCA, 100500)], 100000)["vincente"] is not None
    v = svc.valuta_prove([_p(svc.PROVA_BANCA, 100501)], 100000)
    assert v["vincente"] is None and v["non_conforme"]["differenza_cents"] == 501


def test_pagamento_parziale_non_regge():
    v = svc.valuta_prove([_p(svc.PROVA_ESTRATTO, 50000)], 100000)
    assert v["vincente"] is None
    assert v["non_conforme"] == {"prova": svc.PROVA_ESTRATTO, "importo_cents": 50000,
                                 "differenza_cents": -50000}


def test_due_pagamenti_distinti_che_sommano_la_rata_reggono():
    v = svc.valuta_prove(
        [_p(svc.PROVA_ESTRATTO, 60000, "a"), _p(svc.PROVA_ESTRATTO, 40000, "b")], 100000)
    assert v["vincente"]["importo_cents"] == 100000


def test_la_fonte_piu_forte_che_non_torna_cede_a_una_che_torna():
    v = svc.valuta_prove(
        [_p(svc.PROVA_BANCA, 30000), _p(svc.PROVA_ESTRATTO, 100000)], 100000)
    assert v["vincente"]["prova"] == svc.PROVA_ESTRATTO


@pytest.mark.parametrize("rata,prova", [(None, 100000), (100000, None)])
def test_importo_non_leggibile_non_e_una_prova(rata, prova):
    v = svc.valuta_prove([_p(svc.PROVA_QUIETANZA, prova)], rata)
    assert v["vincente"] is None and v["non_conforme"]["prova"] == svc.PROVA_QUIETANZA
    assert v["non_conforme"]["differenza_cents"] is None


def test_senza_prove_non_cambia_niente():
    assert svc.valuta_prove([], 100000) == {"vincente": None, "non_conforme": None}
    assert svc.valuta_prove(None, None) == {"vincente": None, "non_conforme": None}


def test_importo_decimale_senza_float():
    # 0,1 + 0,2 in float non fa 0,3: i centesimi vengono da Decimal.
    assert svc._cents_o_none(0.1 + 0.2) == 30
    assert svc._cents_o_none("1.037,12") is None  # formato non numerico: mai indovinato
    assert svc._cents_o_none(None) is None and svc._cents_o_none("nan") is None


def test_esito_rata_parziale_resta_da_verificare_anche_se_il_piano_dice_pagata():
    rata = {"numero_rata": 1, "importo_totale": 1000.0, "stato": "Pagata"}
    e = svc.esito_rata(rata, [_p(svc.PROVA_ESTRATTO, 40000)], None)
    assert e["pagata"] is False and e["da_verificare"] is True and e["prova"] is None
    assert e["differenza_cents"] == -60000 and e["prova_non_conforme"] == svc.PROVA_ESTRATTO


def test_esito_rata_parziale_batte_anche_la_dichiarazione():
    rata = {"numero_rata": 1, "importo_totale": 1000.0, "stato": "Da pagare"}
    dich = {"stato": svc.STATO_DICHIARATA}
    e = svc.esito_rata(rata, [_p(svc.PROVA_BANCA, 10000)], dich)
    assert e["pagata"] is False and e["da_verificare"] is True
    assert e["dichiarazione_sostituita"] is False


@pytest.fixture
def db(monkeypatch):
    db = ClientArchivioMemoria()["mutui-importo"]
    rate = [
        {"numero_rata": n, "data_scadenza": f"17/0{n}/2021", "importo_totale": 1000.0,
         "quota_capitale": 900.0, "quota_interessi": 100.0, "stato": "Da pagare"}
        for n in (1, 2, 3)
    ]
    _run(db["mutui_piani_documentali"].insert_one({
        "numero_delibera": "905217466", "tipo_finanziamento": "MUTUO IMPRESA RETAIL",
        "importo_accordato": 10000.0, "sha256": "s", "updated_at": "2026-09-01T00:00:00+00:00",
        "rate": rate,
    }))
    _run(db["mutui_estratti_annuali"].insert_one({
        "numero_finanziamento": "1788/045/000005217466", "anno": 2021, "sha256": "e",
        "pagamenti": [
            {"data_operazione": "2021-01-17", "data_scadenza": "2021-01-17", "data_valuta": "2021-01-17",
             "importo": 1002.75},   # tasso variabile: rientra
            {"data_operazione": "2021-02-17", "data_scadenza": "2021-02-17", "data_valuta": "2021-02-17",
             "importo": 400.0},     # parziale
        ],
    }))
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    return db


def test_pagina_mutui_rata_parziale_da_verificare_con_differenza(db):
    mutuo = _run(mod._mutuo(db, MUTUO))
    r1, r2, r3 = mutuo["rate"]
    assert r1["stato"] == "Pagata" and r1["prova"] == "estratto_annuale"
    assert r1["differenza_importo_cents"] == 275
    assert r2["stato"] == "Da verificare" and r2["prova"] is None
    assert r2["differenza_importo_cents"] == -60000 and r2["importo_provato_cents"] == 40000
    assert r3["stato"] == "Da pagare"
    assert mutuo["rate_pagate"] == 1 and mutuo["rate_da_verificare"] == 1
    # la rata parziale resta nel residuo: il debito non si riduce
    assert mutuo["debito_residuo_totale"] == 2000.0


def test_riscontro_elenca_le_rate_con_importo_da_verificare(db):
    esito = _run(mod.riconcilia_mutui_con_estratto_conto())["data"]
    assert esito["rate_importo_da_verificare"] == 1
    voce = [d for d in esito["dettagli"] if d["status"] == "importo_da_verificare"][0]
    assert voce["rata_numero"] == 2 and voce["differenza_importo_cents"] == -60000


def test_anteprima_dichiarazione_non_dichiara_la_rata_parziale(db):
    a = _run(svc.anteprima_dichiarazione(db, MUTUO, oggi=OGGI, anno_attivo=2026))
    assert a["da_verificare"] == [2]
    assert 2 not in a["numeri_rata"] and a["numeri_rata"] == [3]


def test_la_dichiarazione_non_si_sostituisce_con_una_prova_parziale(db):
    adesso = "2026-09-30T00:00:00+00:00"
    _run(db["mutui_rate_dichiarate"].insert_one({
        "id": "mrd:5217466:002", "cifre_mutuo": "5217466", "numero_rata": 2, "data_scadenza": "17/02/2021",
        "importo_totale_cents": 100000, "stato": svc.STATO_DICHIARATA, "storico": [], "updated_at": adesso,
    }))
    assert _run(svc.assorbi_dichiarazioni_rate(db)) == {"sostituite": 0}
    riga = _run(db["mutui_rate_dichiarate"].find_one({"id": "mrd:5217466:002"}))
    assert riga["stato"] == svc.STATO_DICHIARATA
