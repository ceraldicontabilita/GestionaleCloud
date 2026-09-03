"""PR 11 — "Interroga avviso bonario": controllo incrociato per riga.

Fixture reale (audit §4): F24 `149f2355…` del 20/12/2019, saldo 2.738,28,
riga 1001 10/2019 = 1.455,21 (con 1012 893,71; 1655 80,06 e credito 400,00;
8906 40,73; 3802 132,30 10/2018; 3847/3848). I cinque esiti sono coperti con
dati finti sullo stesso registro; il DB e' il finto in memoria del progetto.
"""
import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import f24_controllo_incrociato as ctrl
from app.services.hr_cedolini_lettura import riepilogo_ritenute
from app.services.sheets_document_store import MemorySheetsClient


def _run(coro):
    return asyncio.run(coro)


def _riga(codice, periodo, debito, credito=0.0, **extra):
    mese, anno = periodo.split("/")
    return {
        "codice_tributo": codice, "periodo_riferimento": periodo, "mese": mese, "anno": anno,
        "importo_debito": debito, "importo_credito": credito,
        "descrizione": extra.get("descrizione", ""),
    }


def _f24_149f(**override):
    base = {
        "id": "149f2355-cb6c-4553-a9da-33f4b0391e44",
        "status": "da_pagare", "pagato": False,
        "file_name": "2019-12-20__F24_000__formato_stampabile__senza_protocollo_AE.pdf",
        "dati_generali": {"codice_fiscale": "04523831214", "data_versamento": "2019-12-20"},
        "totali": {"saldo_netto": 2738.28, "totale_debito": 3138.28, "totale_credito": 400.0},
        "sezione_erario": [
            _riga("1001", "10/2019", 1455.21, descrizione="Ritenute su retribuzioni"),
            _riga("1012", "10/2019", 893.71),
            _riga("1655", "10/2019", 80.06),
            _riga("8906", "10/2019", 40.73),
            _riga("1655", "10/2019", 0.0, credito=400.0),
            _riga("8906", "10/2018", 2.89),
        ],
        "sezione_regioni": [_riga("3802", "10/2018", 132.30)],
        "sezione_tributi_locali": [
            _riga("3848", "10/2018", 41.37), _riga("3847", "10/2019", 13.94), _riga("3847", "10/2019", 3.07),
        ],
        "sezione_inps": [], "sezione_inail": [],
    }
    base.update(override)
    return base


def _movimento_i24(id_, data, importo, **extra):
    return {
        "id": id_, "data": data, "importo": importo, "tipo": "uscita",
        "descrizione": f"I24 AGENZIA ENTRATE PAG.TO TELEMATICO - DATA INCASSO {data[8:]}/{data[5:7]}/{data[:4]}",
        "classificazione_tipo": "f24", "riconciliato": False, **extra,
    }


def _quietanza_fiscal(id_, filename, **extra):
    return {"id": id_, "category": "quietanza_f24", "filename": filename, "metadata": {}, **extra}


async def _nessun_cedolino(anno, mese):
    return {"configurato": False, "cedolini": [], "errore": "hr_non_configurato"}


def _db_base():
    db = MemorySheetsClient()["avviso_bonario"]
    return db


def _controlla(db, righe, leggi=_nessun_cedolino):
    return _run(ctrl.controlla_avviso(db, righe, leggi_cedolini=leggi))


# ── parse del periodo ─────────────────────────────────────────────────────────

def test_parse_periodo_avviso_mensile_e_annuale():
    assert ctrl.parse_periodo_avviso("10/2019") == {"mese": 10, "anno": 2019}
    assert ctrl.parse_periodo_avviso("2019-10") == {"mese": 10, "anno": 2019}
    assert ctrl.parse_periodo_avviso("2019") == {"mese": None, "anno": 2019}
    assert ctrl.parse_periodo_avviso("", anno_imposta=2020) == {"mese": None, "anno": 2020}
    for cattivo in ("13/2019", "abc", "10-19"):
        try:
            ctrl.parse_periodo_avviso(cattivo)
            assert False, cattivo
        except ValueError:
            pass


# ── i cinque esiti ────────────────────────────────────────────────────────────

def test_da_pagare_quando_il_modello_esiste_senza_prove():
    db = _db_base()
    _run(db.f24_unificato.insert_one(_f24_149f()))
    esito = _controlla(db, [{"codice_tributo": "1001", "periodo": "10/2019", "importo": 1455.21}])
    riga = esito["righe"][0]
    assert riga["esito"] == "DA_PAGARE"
    assert riga["differenza"] == 0.0
    assert riga["descrizione_tributo"] == "Ritenute su retribuzioni"
    assert riga["righe_f24"][0]["data_versamento_it"] == "20/12/2019"
    assert riga["righe_f24"][0]["saldo_modello"] == 2738.28
    assert riga["righe_f24"][0]["pdf_url"].endswith("/149f2355-cb6c-4553-a9da-33f4b0391e44/pdf")
    assert esito["riepilogo"]["totale_scoperto"] == 1455.21
    assert esito["riepilogo"]["totale_coperto"] == 0.0
    assert esito["sola_lettura"] is True


def test_pagato_senza_quietanza_con_addebito_i24_compatibile_non_agganciato():
    db = _db_base()
    _run(db.f24_unificato.insert_one(_f24_149f()))
    _run(db.estratto_conto_movimenti.insert_one(_movimento_i24("mov-2738", "2019-12-20", 2738.28)))
    esito = _controlla(db, [{"codice_tributo": "1001", "periodo": "10/2019", "importo": 1455.21}])
    riga = esito["righe"][0]
    assert riga["esito"] == "PAGATO_SENZA_QUIETANZA"
    addebito = riga["addebiti_banca"][0]
    assert addebito["movimento_id"] == "mov-2738" and addebito["agganciato"] is False
    assert addebito["data_it"] == "20/12/2019" and addebito["importo"] == 2738.28
    assert addebito["link"] == "/riconciliazione/banca?movimento=mov-2738"
    assert esito["riepilogo"]["totale_pagato_senza_quietanza"] == 1455.21


def test_coperto_con_addebito_agganciato_e_quietanza_collegata():
    db = _db_base()
    _run(db.f24_unificato.insert_one(_f24_149f(
        movimento_bancario_id="mov-2738", data_pagamento_effettivo="2019-12-20",
        quietanza_id="fdoc_q1", status="pagato", pagato=True,
    )))
    _run(db.estratto_conto_movimenti.insert_one(
        _movimento_i24("mov-2738", "2019-12-20", 2738.28, riconciliato=True,
                       tipo_riconciliazione="f24_tributi", f24_ids=["149f2355-cb6c-4553-a9da-33f4b0391e44"])
    ))
    _run(db.fiscal_documents.insert_one(_quietanza_fiscal(
        "fdoc_q1", "2019-12-20__F24_000__quietanza_AE__prot_19122012345678901-000001.pdf",
    )))
    esito = _controlla(db, [{"codice_tributo": "1001", "periodo": "10/2019", "importo": 1455.21}])
    riga = esito["righe"][0]
    assert riga["esito"] == "COPERTO"
    assert riga["quietanze"][0]["quietanza_id"] == "fdoc_q1"
    assert riga["quietanze"][0]["protocollo"] == "19122012345678901-000001"
    assert riga["quietanze"][0]["data_it"] == "20/12/2019"
    assert riga["addebiti_banca"][0]["agganciato"] is True
    assert esito["riepilogo"]["totale_coperto"] == 1455.21


def test_non_trovato_e_importo_diverso_con_differenza_al_centesimo():
    db = _db_base()
    _run(db.f24_unificato.insert_one(_f24_149f()))
    esito = _controlla(db, [
        {"codice_tributo": "1001", "periodo": "11/2019", "importo": 1455.21},
        {"codice_tributo": "1012", "periodo": "10/2019", "importo": 900.00},
        {"codice_tributo": "3847", "periodo": "10/2019", "importo": 17.01},
    ])
    non_trovato, diverso, somma_righe = esito["righe"]
    assert non_trovato["esito"] == "NON_TROVATO" and non_trovato["righe_f24"] == []
    assert diverso["esito"] == "IMPORTO_DIVERSO"
    assert diverso["importo_f24"] == 893.71
    assert diverso["differenza"] == 6.29
    assert diverso["differenza_cents"] == 629
    # due righe 3847 dello stesso modello (13,94 + 3,07) si sommano per il confronto
    assert somma_righe["esito"] == "DA_PAGARE" and somma_righe["differenza"] == 0.0
    assert esito["riepilogo"]["per_esito"] == {
        "COPERTO": 0, "PAGATO_SENZA_QUIETANZA": 0, "DA_PAGARE": 1, "NON_TROVATO": 1, "IMPORTO_DIVERSO": 1,
    }
    assert esito["riepilogo"]["totale_avviso"] == 2372.22


def test_periodo_annuale_dell_avviso_accetta_righe_con_solo_anno():
    db = _db_base()
    _run(db.f24_unificato.insert_one({
        "id": "f24-6008", "status": "da_pagare", "pagato": False,
        "dati_generali": {"data_versamento": "2020-09-16"},
        "totali": {"saldo_netto": 990.26},
        "sezione_erario": [{"codice_tributo": "6008", "periodo_riferimento": "2020", "anno": "2020",
                            "mese": "00", "importo_debito": 990.26}],
    }))
    esito = _controlla(db, [{"codice_tributo": "6008", "periodo": "2020", "importo": 990.26}])
    assert esito["righe"][0]["esito"] == "DA_PAGARE"
    assert esito["righe"][0]["periodo"] == "2020"


# ── cedolini HR ───────────────────────────────────────────────────────────────

def test_cedolini_hr_del_periodo_entrano_solo_per_i_tributi_da_sostituto():
    db = _db_base()
    _run(db.f24_unificato.insert_one(_f24_149f()))
    letture = []

    async def leggi(anno, mese):
        letture.append((anno, mese))
        return {"configurato": True, "errore": None, "cedolini": [
            {"nome_dipendente": "Capezzuto Alessandro", "codice_fiscale": "CPZ", "trattenute": 301.68, "irpef": 1000.00},
            {"nome_dipendente": "Carotenuto Antonella", "codice_fiscale": "CRT", "trattenute": 20.53, "irpef": 455.21},
        ]}

    esito = _controlla(db, [
        {"codice_tributo": "1001", "periodo": "10/2019", "importo": 1455.21},
        {"codice_tributo": "8906", "periodo": "10/2019", "importo": 40.73},
    ], leggi=leggi)
    assert letture == [(2019, 10)]  # una sola lettura per periodo, solo per il tributo da sostituto
    ced = esito["righe"][0]["cedolini_hr"]
    assert ced["natura"] == "irpef" and ced["n_cedolini"] == 2
    assert ced["totale"] == 1455.21 and ced["differenza_vs_avviso"] == 0.0
    assert ced["attendibile"] is True and ced["campo_usato"] == "irpef"
    assert esito["righe"][1]["cedolini_hr"] is None
    assert esito["cedolini_hr_letti"] == {"10/2019": {"n": 2, "configurato": True, "errore": None}}


def test_riepilogo_ritenute_non_spaccia_le_trattenute_totali_per_irpef():
    # forma reale dei 1291 cedolini HR: solo `trattenute` (totale), nessun campo irpef/inps
    cedolini = [{"nome_dipendente": "A", "trattenute": 301.68}, {"nome_dipendente": "B", "trattenute": 20.53}]
    riepilogo = riepilogo_ritenute(cedolini, "irpef", 1455.21)
    assert riepilogo["attendibile"] is False
    assert riepilogo["motivo"] == "voci_non_estratte_nei_cedolini_hr"
    assert riepilogo["totale"] is None and riepilogo["differenza_vs_avviso"] is None
    assert riepilogo["trattenute_totali"] == 322.21
    # con l'elenco voci la somma si ricava dalle voci
    con_voci = [{"voci": [{"codice": "IRPEF", "descrizione": "IRPEF netta", "trattenuta": 120.0},
                          {"codice": "INPS", "trattenuta": 50.0}]}]
    assert riepilogo_ritenute(con_voci, "irpef")["totale"] == 120.0
    assert riepilogo_ritenute(con_voci, "inps")["campo_usato"] == "voci"
    assert riepilogo_ritenute([], "irpef")["motivo"] == "nessun_cedolino_hr_nel_periodo"


# ── endpoint ──────────────────────────────────────────────────────────────────

def _client(monkeypatch, db):
    from app.database import Database
    from app.routers.f24 import avviso_bonario
    from app.utils.dependencies import get_current_admin_user, get_current_user

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(avviso_bonario.router, prefix="/api/f24")
    app.dependency_overrides[get_current_user] = lambda: {"sub": "u", "role": "user"}
    app.dependency_overrides[get_current_admin_user] = lambda: {"sub": "a", "role": "admin"}
    return TestClient(app)


def test_endpoint_controllo_restituisce_esiti_e_422_su_periodo_invalido(monkeypatch):
    db = _db_base()
    _run(db.f24_unificato.insert_one(_f24_149f()))
    monkeypatch.setattr(ctrl, "cedolini_hr_periodo", _nessun_cedolino)
    client = _client(monkeypatch, db)

    ok = client.post("/api/f24/avviso-bonario/controllo", json={
        "numero_avviso": "AB-2026-1", "data_avviso": "2026-09-01",
        "righe": [{"codice_tributo": "1001", "periodo": "10/2019", "importo": 1455.21}],
    })
    assert ok.status_code == 200, ok.text
    corpo = ok.json()
    assert corpo["righe"][0]["esito"] == "DA_PAGARE"
    assert corpo["data_avviso_it"] == "01/09/2026"
    assert corpo["riepilogo"]["n_righe"] == 1

    cattivo = client.post("/api/f24/avviso-bonario/controllo", json={
        "righe": [{"codice_tributo": "1001", "periodo": "13/2019", "importo": 1.0}],
    })
    assert cattivo.status_code == 422
    assert "periodo" in cattivo.json()["detail"] or "mese" in cattivo.json()["detail"]

    # nessuna scrittura: il modello e' come prima
    f24 = _run(db.f24_unificato.find_one({"id": "149f2355-cb6c-4553-a9da-33f4b0391e44"}, {"_id": 0}))
    assert f24["status"] == "da_pagare" and "quietanza_id" not in f24


def test_route_avviso_bonario_precede_la_route_dinamica_di_f24_main():
    from app.routers.f24 import f24_main

    rotte = [(getattr(r, "path", ""), set(getattr(r, "methods", None) or ())) for r in f24_main.router.routes]
    percorsi = [p for p, _ in rotte]
    assert "/avviso-bonario/controllo" in percorsi
    assert "/riconcilia-addebiti" in percorsi
    get_dinamica = max(i for i, (p, m) in enumerate(rotte) if p == "/{f24_id}" and "GET" in m)
    assert percorsi.index("/avviso-bonario/controllo") < get_dinamica
