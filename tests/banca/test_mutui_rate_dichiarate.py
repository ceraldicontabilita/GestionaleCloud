"""Rate di mutuo «pagate, dichiarato dal titolare»: anteprima, idempotenza,
prova che vince, ritiro, rate future, nessuna scrittura contabile."""
import asyncio
from datetime import date

import pytest
from fastapi import HTTPException

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


def _rata(n, scadenza, stato="Da pagare", capitale=900.0, interessi=100.0):
    return {"numero_rata": n, "data_scadenza": scadenza, "importo_totale": capitale + interessi,
            "quota_capitale": capitale, "quota_interessi": interessi, "stato": stato}


@pytest.fixture
def db(monkeypatch):
    db = ClientArchivioMemoria()["mutui-dichiarate"]
    _run(db["mutui_piani_documentali"].insert_one({
        "numero_delibera": "905217466", "tipo_finanziamento": "MUTUO IMPRESA RETAIL",
        "importo_accordato": 10000.0, "sha256": "s", "updated_at": "2026-09-01T00:00:00+00:00",
        "rate": [
            _rata(1, "17/03/2021", "Pagata"),       # pagata scritta sul piano
            _rata(2, "17/04/2021"),                 # provata da estratto annuale
            _rata(3, "17/05/2021"),                 # provata da riga di Prima Nota Banca
            _rata(4, "17/06/2021"),                 # senza prova: da dichiarare
            _rata(5, "17/01/2026"),                 # senza prova, anno attivo
            _rata(6, "17/12/2026"),                 # futura
        ],
    }))
    _run(db["mutui_estratti_annuali"].insert_one({
        "numero_finanziamento": "1788/045/000005217466", "anno": 2021, "sha256": "e",
        "pagamenti": [{"data_scadenza": "2021-04-17", "data_valuta": "2021-04-17", "importo": 1003.5}],
    }))
    _run(db["prima_nota_banca"].insert_one({
        "id": "PNB3", "data": "2021-05-17", "importo": 1000.0,
        "tipo_classificazione_contabile": "rata_mutuo", "numero_mutuo": "1788 5217466",
        "rata_scadenza": "17/05/2021", "movimento_bancario_id": "EC-3",
    }))
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    return db


def _anteprima(db, **kw):
    return _run(svc.anteprima_dichiarazione(db, MUTUO, oggi=OGGI, anno_attivo=2026, **kw))


def _esegui(db, **kw):
    anteprima = _anteprima(db)
    return _run(svc.dichiara_rate_pagate(
        db, MUTUO, dry_run=False, conferma=anteprima["frase_conferma"], oggi=OGGI, anno_attivo=2026, **kw,
    ))


def test_anteprima_conta_solo_le_rate_senza_prova_e_scadute(db):
    a = _anteprima(db)
    assert a["dry_run"] is True
    assert a["numeri_rata"] == [4, 5]
    assert a["numero_rate"] == 2
    assert a["totale_cents"] == 200000 and a["totale"] == "2000.00" and a["valuta"] == "EUR"
    assert a["prima_scadenza"] == "2021-06-17" and a["ultima_scadenza"] == "2026-01-17"
    assert a["gia_provate"] == [2, 3]
    assert a["gia_pagate_sul_piano"] == [1]
    assert a["future_escluse"] == [6]
    assert a["di_cui_anno_attivo"] == 1
    assert a["effetti_contabili"] == "nessuno"
    assert a["frase_conferma"] == "DICHIARO PAGATE 2 RATE"


def test_dry_run_per_difetto_non_scrive(db):
    esito = _run(svc.dichiara_rate_pagate(db, MUTUO, oggi=OGGI, anno_attivo=2026))
    assert esito["dry_run"] is True
    assert _run(db["mutui_rate_dichiarate"].count_documents({})) == 0


def test_esecuzione_richiede_la_conferma_forte(db):
    with pytest.raises(HTTPException) as exc:
        _run(svc.dichiara_rate_pagate(db, MUTUO, dry_run=False, conferma="si", oggi=OGGI))
    assert exc.value.status_code == 409 and exc.value.detail["code"] == "CONFERMA_RICHIESTA"
    assert _run(db["mutui_rate_dichiarate"].count_documents({})) == 0


def test_dichiara_e_secondo_giro_zero(db):
    primo = _esegui(db)
    assert primo["dichiarate"] == 2
    righe = _run(db["mutui_rate_dichiarate"].find({}, {"_id": 0}).to_list(None))
    assert {r["numero_rata"] for r in righe} == {4, 5}
    riga = next(r for r in righe if r["numero_rata"] == 4)
    assert riga["stato"] == "pagata_dichiarata_titolare"
    assert riga["motivo"] == "Estratti precedenti non disponibili"
    assert riga["dichiarato_da"] == "titolare" and riga["dichiarato_il"]
    assert riga["importo_totale_cents"] == 100000 and riga["storico"][0]["evento"] == "dichiarata"
    # secondo giro: nulla da fare
    assert _anteprima(db)["numero_rate"] == 0
    secondo = _run(svc.dichiara_rate_pagate(db, MUTUO, dry_run=False, oggi=OGGI))
    assert secondo["dichiarate"] == 0
    assert _run(db["mutui_rate_dichiarate"].count_documents({})) == 2


def test_non_sovrascrive_le_rate_provate_ne_quelle_del_piano(db):
    _esegui(db)
    numeri = {r["numero_rata"] for r in _run(db["mutui_rate_dichiarate"].find({}).to_list(None))}
    assert not numeri & {1, 2, 3, 6}
    mutuo = _run(mod._mutuo(db, MUTUO))
    per_numero = {r["numero_rata"]: r for r in mutuo["rate"]}
    assert per_numero[1]["prova"] == "piano"
    assert per_numero[2]["prova"] == "estratto_annuale"
    assert per_numero[3]["prova"] == "banca" and per_numero[3]["riconciliata"] is True
    assert per_numero[4]["prova"] == "dichiarata_titolare" and per_numero[4]["dichiarata_titolare"] is True
    assert per_numero[4]["stato"] == "Pagata" and per_numero[4]["stato_piano"] == "Da pagare"
    assert per_numero[6]["stato"] == "Da pagare"


def test_residuo_coerente_col_piano(db):
    prima = _run(mod._mutuo(db, MUTUO))
    assert prima["rate_pagate"] == 3 and prima["debito_residuo_capitale"] == 2700.0  # 4, 5, 6
    _esegui(db)
    dopo = _run(mod._mutuo(db, MUTUO))
    assert dopo["rate_pagate"] == 5 and dopo["rate_da_pagare"] == 1
    assert dopo["rate_dichiarate_titolare"] == 2 and dopo["rate_provate"] == 2
    assert dopo["debito_residuo_capitale"] == 900.0 and dopo["debito_residuo_totale"] == 1000.0
    assert dopo["prossima_data_scadenza"] == "17/12/2026"


def test_rate_future_escluse_anche_con_data_limite_nel_futuro(db):
    a = _anteprima(db, data_limite="31/12/2030")
    assert 6 in a["future_escluse"] and 6 not in a["numeri_rata"]
    assert a["data_limite"] == "2026-09-30" and a["nota_data_limite"]
    ristretta = _anteprima(db, data_limite="31/12/2021")
    assert ristretta["numeri_rata"] == [4] and 5 in ristretta["future_escluse"]


def test_prova_successiva_sostituisce_la_dichiarazione(db):
    _esegui(db)
    _run(db["prima_nota_banca"].insert_one({
        "id": "PNB4", "data": "2021-06-17", "importo": 1000.0,
        "tipo_classificazione_contabile": "rata_mutuo", "numero_mutuo": "1788 5217466",
        "rata_scadenza": "17/06/2021", "movimento_bancario_id": "EC-4",
    }))
    mutuo = _run(mod._mutuo(db, MUTUO))
    rata4 = next(r for r in mutuo["rate"] if r["numero_rata"] == 4)
    assert rata4["prova"] == "banca" and rata4["dichiarata_titolare"] is False
    assert rata4["dichiarazione_sostituita"] is True
    assert mutuo["rate_dichiarate_titolare"] == 1
    esito = _run(svc.assorbi_dichiarazioni_rate(db))
    assert esito["sostituite"] == 1
    riga = _run(db["mutui_rate_dichiarate"].find_one({"numero_rata": 4}))
    assert riga["stato"] == "sostituita_da_prova" and riga["sostituita_da_prova"] == "banca"
    assert [e["evento"] for e in riga["storico"]] == ["dichiarata", "sostituita_da_prova"]
    assert _run(svc.assorbi_dichiarazioni_rate(db))["sostituite"] == 0  # idempotente
    # e la rata provata non si dichiara di nuovo
    assert 4 not in _anteprima(db)["numeri_rata"]


def test_ritiro_reversibile_con_storico(db):
    _esegui(db)
    anteprima = _run(svc.ritira_dichiarazioni(db, MUTUO))
    assert anteprima["dry_run"] is True and anteprima["numeri_rata"] == [4, 5]
    with pytest.raises(HTTPException):
        _run(svc.ritira_dichiarazioni(db, MUTUO, dry_run=False, conferma="no"))
    fatto = _run(svc.ritira_dichiarazioni(
        db, MUTUO, numeri_rata=[5], dry_run=False, conferma="RITIRO DICHIARAZIONE 1 RATE",
    ))
    assert fatto["ritirate"] == 1 and fatto["numeri_rata"] == [5]
    mutuo = _run(mod._mutuo(db, MUTUO))
    per_numero = {r["numero_rata"]: r for r in mutuo["rate"]}
    assert per_numero[5]["stato"] == "Da pagare" and per_numero[4]["dichiarata_titolare"] is True
    riga = _run(db["mutui_rate_dichiarate"].find_one({"numero_rata": 5}))
    assert riga["stato"] == "ritirata" and [e["evento"] for e in riga["storico"]] == ["dichiarata", "ritirata"]
    # il ritiro e' idempotente e la rata si puo' dichiarare di nuovo, storico compreso
    assert _run(svc.ritira_dichiarazioni(db, MUTUO, numeri_rata=[5], dry_run=False))["ritirate"] == 0
    _esegui(db)
    riga = _run(db["mutui_rate_dichiarate"].find_one({"numero_rata": 5}))
    assert riga["stato"] == "pagata_dichiarata_titolare"
    assert [e["evento"] for e in riga["storico"]] == ["dichiarata", "ritirata", "dichiarata"]


def test_motivo_solo_da_elenco_e_altro_vuole_il_testo(db):
    with pytest.raises(HTTPException) as exc:
        _run(svc.dichiara_rate_pagate(db, MUTUO, motivo="a caso", oggi=OGGI))
    assert exc.value.detail["code"] == "MOTIVO_NON_VALIDO"
    with pytest.raises(HTTPException) as exc:
        _run(svc.dichiara_rate_pagate(db, MUTUO, motivo="altro", oggi=OGGI))
    assert exc.value.detail["code"] == "MOTIVO_ALTRO_VUOTO"
    esito = _run(svc.dichiara_rate_pagate(db, MUTUO, motivo="altro", motivo_altro="pagate in filiale", oggi=OGGI))
    assert esito["motivo"] == "Altro: pagate in filiale"


def test_nessuna_scrittura_contabile_ne_prima_nota(db):
    prima_nota = _run(db["prima_nota_banca"].count_documents({}))
    _esegui(db)
    assert _run(db["prima_nota_banca"].count_documents({})) == prima_nota
    for collezione in ("movimenti_contabili", "prima_nota_cassa", "prima_nota"):
        assert _run(db[collezione].count_documents({})) == 0


def test_mutuo_inesistente_404(db):
    with pytest.raises(HTTPException) as exc:
        _run(svc.anteprima_dichiarazione(db, "mutuo_1", oggi=OGGI))
    assert exc.value.status_code == 404


def test_riscontro_non_conta_le_dichiarate_come_addebiti_mancanti(db):
    _esegui(db)
    esito = _run(mod.riconcilia_mutui_con_estratto_conto())["data"]
    assert esito["rate_dichiarate_senza_prova"] == 2
    assert esito["riconciliazioni_manuali_richieste"] == 2  # rata 1 (piano) e rata 2 (estratto): senza riga in banca
    assert esito["riconciliazioni_automatiche"] == 1


@pytest.mark.parametrize("suffisso", ["rate-dichiarate", "rate-dichiarate/ritira"])
@pytest.mark.parametrize("trasporto", ["cookie", "bearer"])
@pytest.mark.parametrize("ruolo,atteso", [("admin", 200), ("operatore", 403), ("sola_lettura", 403)])
def test_l_endpoint_e_solo_admin_con_sessione_reale(db, suffisso, trasporto, ruolo, atteso):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.middleware.authentication import AuthenticationMiddleware
    from tests.banca.test_mutui_permessi import _token_fixture

    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware)
    app.include_router(mod.router, prefix="/api/mutui")
    token = _token_fixture(ruolo)
    kwargs = ({"cookies": {"access_token": token}} if trasporto == "cookie"
              else {"headers": {"Authorization": "Bearer " + token}})
    prima = {nome: _run(db[nome].count_documents({}))
             for nome in ("mutui_rate_dichiarate", "giornale", "prima_nota_banca")}
    with TestClient(app) as client:
        response = client.post(f"/api/mutui/{MUTUO}/{suffisso}",
                               json={"dry_run": True, "data_limite": "2026-09-30"}, **kwargs)
        assert response.status_code == atteso
        if atteso == 200:
            assert response.json()["data"]["dry_run"] is True
    assert {nome: _run(db[nome].count_documents({})) for nome in prima} == prima


@pytest.mark.parametrize("suffisso", ["rate-dichiarate", "rate-dichiarate/ritira"])
def test_l_endpoint_senza_sessione_non_accede(db, suffisso):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.middleware.authentication import AuthenticationMiddleware

    app = FastAPI()
    app.add_middleware(AuthenticationMiddleware)
    app.include_router(mod.router, prefix="/api/mutui")
    with TestClient(app) as client:
        assert client.post(f"/api/mutui/{MUTUO}/{suffisso}", json={"dry_run": True}).status_code == 401
