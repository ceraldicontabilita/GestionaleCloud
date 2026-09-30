"""13ª e 14ª: totali per dipendente e spostamenti che non duplicano mai."""
import asyncio

import pytest
from mongomock_motor import AsyncMongoMockClient

from app.hr.routers import posizione_dipendente as router
from app.services import mensilita_aggiuntive as mens


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def hr(monkeypatch):
    from app.hr.database import Database as DatabaseHR

    db = AsyncMongoMockClient()["hr_mens"]
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: db))
    _run(db.dipendenti.insert_one({"id": "d1", "nome_completo": "Rossi Mario", "stato": "attivo"}))
    for m in range(1, 13):
        _run(db.cedolini.insert_one({
            "id": f"c{m}", "dipendente_id": "d1", "anno": 2025, "mese": m, "tipo_cedolino": "mensile",
            "netto": 1000, "stato_netto": "NETTO_VERIFICATO_DA_CEDOLINO",
            "dati_chiave": {"rateo_13ma_importo": "60,27", "rateo_14ma_importo": "10,00"} if m != 5 else {}}))
    _run(db.cedolini.insert_one({
        "id": "c13", "dipendente_id": "d1", "anno": 2025, "mese": 12, "tipo_cedolino": "tredicesima",
        "netto": 900, "stato_netto": "NETTO_VERIFICATO_DA_CEDOLINO"}))
    _run(db.pagamenti_esiti.insert_one({
        "id": "pe1", "key": "k1", "dipendente_id": "d1", "anno": 2025, "mese": 11, "importo": 400.0,
        "data": "2025-12-15", "causale": "BONIFICO"}))
    _run(db.acconti_dipendenti.insert_one({
        "id": "a1", "dipendente_id": "d1", "tipo": "stipendio", "stato": "registrato", "importo": 200,
        "data": "2025-12-10", "scalato_su_anno_mese": "2025-12", "source": "bonifici_da_associare"}))
    return db


def test_riepilogo_somma_ratei_e_dice_quante_buste_mancano(hr):
    out = _run(mens.riepilogo(hr, 2025))
    riga = out["righe"][0]
    t = riga["tredicesima"]
    assert t["rateo_maturato"] == pytest.approx(60.27 * 11) and t["buste_con_rateo"] == 11
    assert t["buste_mensili"] == 12 and t["busta"] == 900.0 and t["pagato"] == 0.0 and t["saldo"] == 900.0


def test_spostare_un_acconto_sulla_tredicesima_non_lo_duplica_e_si_riporta(hr):
    _run(mens.sposta_acconto(hr, "d1", "a1", "13", 2025))
    _run(mens.sposta_acconto(hr, "d1", "a1", "13", 2025))  # ripetuto: nessun effetto
    assert _run(hr.acconti_dipendenti.count_documents({})) == 1
    t = _run(mens.riepilogo(hr, 2025))["righe"][0]["tredicesima"]
    assert t["pagato"] == 200.0 and t["saldo"] == 700.0
    _run(mens.riporta_acconto(hr, "d1", "a1"))
    acc = _run(hr.acconti_dipendenti.find_one({"id": "a1"}))
    assert acc["tipo"] == "stipendio" and acc["scalato_su_anno_mese"] == "2025-12"
    assert _run(mens.riepilogo(hr, 2025))["righe"][0]["tredicesima"]["pagato"] == 0.0


def test_il_bonifico_si_sposta_col_motore_esistente_e_resta_uno(hr):
    _run(router.mensilita_sposta({"dipendente_id": "d1", "sorgente": "esito", "id": "k1",
                                  "mensilita": "14", "anno": 2025}))
    assert _run(hr.pagamenti_esiti.count_documents({})) == 1
    q = _run(mens.riepilogo(hr, 2025))["righe"][0]["quattordicesima"]
    assert q["pagato"] == 400.0
    _run(router.mensilita_riporta({"dipendente_id": "d1", "sorgente": "esito", "id": "k1"}))
    e = _run(hr.pagamenti_esiti.find_one({"key": "k1"}))
    assert (e["anno"], e["mese"]) == (2025, 11)


def test_acconto_in_contanti_della_riga_paga_passa_alla_riga_13(hr):
    _run(hr.paghe_mensili.insert_one({"dipendente_id": "d1", "anno": 2025, "mese": 10,
                                      "acconti": [{"importo": 150, "data": "2025-10-20"}]}))
    _run(mens.sposta_acconto_paga(hr, "d1", "2025:10:0", "13", 2025, data="2025-10-20", importo=150))
    assert _run(hr.paghe_mensili.find_one({"anno": 2025, "mese": 10}))["acconti"] == []
    assert len(_run(hr.paghe_mensili.find_one({"anno": 2025, "mese": 13}))["acconti"]) == 1
    with pytest.raises(mens.ErroreMensilita):  # l'indice non punta piu' a quella voce
        _run(mens.sposta_acconto_paga(hr, "d1", "2025:10:0", "14", 2025, data="2025-10-20", importo=150))
    _run(mens.riporta_acconto_paga(hr, "d1", "2025:13:0"))
    assert len(_run(hr.paghe_mensili.find_one({"anno": 2025, "mese": 10}))["acconti"]) == 1


def test_un_pagamento_di_un_altro_dipendente_non_si_sposta(hr):
    with pytest.raises(mens.ErroreMensilita):
        _run(mens.sposta_acconto(hr, "altro", "a1", "13", 2025))


def test_i_candidati_dicono_dove_stanno_ora(hr):
    righe = _run(mens.candidati(hr, "d1", 2025))
    assert {r["sorgente"] for r in righe} == {"esito", "acconto"}
    assert all(r["collocazione"] and r["sulla_mensilita"] is False for r in righe)
