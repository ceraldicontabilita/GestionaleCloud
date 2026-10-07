"""Il router TFR (``app/hr/routers/tfr.py``, l'unico: il lato ERP e' una proiezione
in sola lettura) scrive i conti CEE ufficiali col motore unico ``app/services/tfr_acconti.py``:

* acconto TFR: DARE 29.01.01 Fondo TFR / AVERE 39.07.05 Personale c/liquidazione
  (prima 02.04.01 / 01.01.02, conti operativi fuori dal piano ufficiale);
* eliminazione e correzione: storno (``acconto_tfr_rettifica``), mai cancellazione;
* accantonamento: 67.01.07.01 / 29.01.01, idempotente per dipendente+anno, rifiuta
  un totale non positivo; liquidazione: 29.01.01 / 39.07.05 e 39.07.05 / 35.03.15.
"""
import pytest

from app.hr.routers import tfr as mod
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.piano_conti_ufficiale import CONTI_UFFICIALI
from tests.hr.scenari_base import run


@pytest.fixture
def db(monkeypatch):
    from app.database import Database as DatabaseGest
    from app.hr.database import Database as DatabaseHR

    # Anagrafica HR e giornale del gestionale sono due archivi: qui lo stesso
    # archivio in memoria risponde per entrambi, cosi' i controlli leggono
    # fondo e scritture da un posto solo.
    archivio = ClientArchivioMemoria()["gest_tfr"]
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: archivio))
    monkeypatch.setattr(DatabaseGest, "get_db", classmethod(lambda cls: archivio))
    run(archivio["dipendenti"].insert_one(
        {"id": "d1", "nome_completo": "Rossi Mario", "tfr_accantonato": 5000.0, "stato": "attivo"}))
    return archivio


def _giornale(db, tipo=None):
    filtro = {"tipo": tipo} if tipo else {}
    return run(db["movimenti_contabili"].find(filtro, {"_id": 0}).to_list(100))


def _quadra(s):
    dare = round(sum(float(r["dare"]) for r in s["righe"]), 2)
    avere = round(sum(float(r["avere"]) for r in s["righe"]), 2)
    return dare == avere == round(float(s["totale_dare"]), 2)


def _fondo(db):
    return round(sum(float(r["dare"]) - float(r["avere"]) for s in _giornale(db) for r in s["righe"]
                     if r["conto_codice"] == "29.01.01"), 2)


def _tfr(db):
    return run(db["dipendenti"].find_one({"id": "d1"}))["tfr_accantonato"]


def test_i_conti_del_tfr_sono_nel_piano_ufficiale():
    from app.services import tfr_acconti
    from app.services.registrazione_contabile import (
        _C_ERARIO_TFR, _C_FONDO_TFR, _C_PERSONALE_LIQUIDAZIONE, _C_QUOTE_TFR)

    for conto in (_C_QUOTE_TFR, _C_FONDO_TFR, _C_PERSONALE_LIQUIDAZIONE, _C_ERARIO_TFR,
                  tfr_acconti.CONTO_FONDO_TFR, tfr_acconti.CONTO_PERSONALE_LIQUIDAZIONE):
        assert conto[0] in CONTI_UFFICIALI, conto
    assert (tfr_acconti.CONTO_FONDO_TFR, tfr_acconti.CONTO_PERSONALE_LIQUIDAZIONE) == (
        _C_FONDO_TFR, _C_PERSONALE_LIQUIDAZIONE)


def test_acconto_tfr_scrive_fondo_e_personale_c_liquidazione(db):
    esito = run(mod.registra_acconto(mod.AccontoInput(dipendente_id="d1", tipo="tfr", importo=500.0,
                                                      data="2026-04-06")))
    assert _tfr(db) == 4500.0
    scritture = _giornale(db, "acconto_tfr")
    assert len(scritture) == 1 and _quadra(scritture[0])
    assert scritture[0]["acconto_id"] == esito["acconto_id"] and scritture[0]["numero_registrazione"] == 1
    assert {(r["conto_codice"], float(r["dare"]), float(r["avere"])) for r in scritture[0]["righe"]} == {
        ("29.01.01", 500.0, 0.0), ("39.07.05", 0.0, 500.0)}
    codici = {r["conto_codice"] for s in _giornale(db) for r in s["righe"]}
    assert not codici & {"02.04.01", "01.01.02"}


def test_acconto_tfr_eliminato_si_storna_non_si_cancella(db):
    acconto_id = run(mod.registra_acconto(mod.AccontoInput(
        dipendente_id="d1", tipo="tfr", importo=500.0, data="2026-04-06")))["acconto_id"]
    run(mod.elimina_acconto(acconto_id))
    assert _tfr(db) == 5000.0 and run(db["acconti_dipendenti"].count_documents({})) == 0
    tutte = _giornale(db)
    assert [s["tipo"] for s in tutte] == ["acconto_tfr", "acconto_tfr_rettifica"]
    assert all(_quadra(s) for s in tutte) and _fondo(db) == 0.0


def test_acconto_tfr_corretto_rettifica_la_differenza(db):
    acconto_id = run(mod.registra_acconto(mod.AccontoInput(
        dipendente_id="d1", tipo="tfr", importo=500.0, data="2026-04-06")))["acconto_id"]
    run(mod.modifica_acconto(acconto_id, {"importo": 300.0}))
    assert _tfr(db) == 4700.0
    run(mod.modifica_acconto(acconto_id, {"importo": 400.0}))
    assert _tfr(db) == 4600.0 and _fondo(db) == 400.0
    assert len(_giornale(db)) == 3 and all(_quadra(s) for s in _giornale(db))
    run(mod.modifica_acconto(acconto_id, {"importo": 400.0}))      # identica: niente
    assert len(_giornale(db)) == 3


def test_acconto_non_tfr_non_scrive_il_giornale(db):
    run(mod.registra_acconto(mod.AccontoInput(dipendente_id="d1", tipo="ferie", importo=100.0,
                                              data="2026-04-06")))
    assert _giornale(db) == [] and _tfr(db) == 5000.0


def test_accantonamento_conti_ufficiali_idempotente_e_guardia_sul_negativo(db):
    from fastapi import HTTPException

    corpo = mod.AccantonamentoTFRInput(dipendente_id="d1", anno=2026, retribuzione_annua=27000.0, indice_istat=1.0)
    r1 = run(mod.registra_accantonamento_tfr(corpo))
    assert r1["dettaglio"]["quota_annuale"] == 2000.0
    s = _giornale(db, "tfr_accantonamento")
    assert len(s) == 1 and _quadra(s[0])
    assert {r["conto_codice"] for r in s[0]["righe"]} == {"67.01.07.01", "29.01.01"}
    tfr_dopo = _tfr(db)

    r2 = run(mod.registra_accantonamento_tfr(
        mod.AccantonamentoTFRInput(dipendente_id="d1", anno=2026, retribuzione_annua=99999.0)))
    assert r2["gia_registrato"] is True and r2["accantonamento_id"] == r1["accantonamento_id"]
    assert run(db["tfr_accantonamenti"].count_documents({})) == 1 and _tfr(db) == tfr_dopo

    with pytest.raises(HTTPException) as exc:
        run(mod.registra_accantonamento_tfr(mod.AccantonamentoTFRInput(
            dipendente_id="d1", anno=2027, retribuzione_annua=1000.0, indice_istat=-50.0)))
    assert exc.value.status_code == 400
    assert run(db["tfr_accantonamenti"].count_documents({})) == 1 and _tfr(db) == tfr_dopo


def test_liquidazione_conti_ufficiali(db):
    run(mod.liquida_tfr(mod.LiquidazioneTFRInput(dipendente_id="d1", data_liquidazione="2026-06-30",
                                                 motivo="dimissioni")))
    fondo = _giornale(db, "tfr_liquidazione")
    ritenute = _giornale(db, "ritenuta_tfr")
    assert len(fondo) == 1 and len(ritenute) == 1 and _quadra(fondo[0]) and _quadra(ritenute[0])
    assert {r["conto_codice"] for r in fondo[0]["righe"]} == {"29.01.01", "39.07.05"}
    assert {r["conto_codice"] for r in ritenute[0]["righe"]} == {"39.07.05", "35.03.15"}
    assert _tfr(db) == 0.0


def test_il_router_usa_il_motore_e_il_lato_erp_non_scrive():
    import inspect

    from app.routers import tfr as erp

    sorgente = inspect.getsource(mod)
    assert "registra_acconto_tfr" in sorgente and "ritira_acconto_tfr" in sorgente
    assert "correggi_importo_acconto_tfr" in sorgente
    assert "acconto_tfr_rettifica" not in sorgente       # lo storno vive solo nel servizio
    assert "_C_TFR_DEBITO" not in sorgente and "_C_BANCA" not in sorgente
    # Il lato ERP non e' un secondo writer: nessuna scrittura, nessun conto.
    sorgente_erp = inspect.getsource(erp)
    for vietato in ("insert_one", "update_one", "registra_scrittura_semplice",
                    "registra_acconto_tfr", "29.01.01"):
        assert vietato not in sorgente_erp, vietato
