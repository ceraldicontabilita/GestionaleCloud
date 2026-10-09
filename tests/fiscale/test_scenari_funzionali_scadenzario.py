"""Scenario funzionale: pagamento puntuale / in ritardo / ravveduto, dalla quietanza allo Scadenzario.

Percorso reale: `importa_quietanza_bytes` (lettura del PDF sostituita) → scadenzario persistente →
`GET /api/f24/tributi/scadenzario` (la scheda «Tributi › Scadenzario» del titolare).
Atteso (CLAUDE.md, «Scadenzario tributi»): scadenza dal modello del commercialista o dalla regola del
codice, con festivi e proroga di Ferragosto; ravvedimento atteso con sanzione 30% previgente / 25% dal
01/09/2024 ridotta per fascia e interessi legali per anno; senza regola «scadenza non determinata».
"""
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services import quietanze_import as qi
from app.services import scadenzario_tributi as sc
from tests.fiscale.scenari_f24_comuni import db_nuovo, quietanza_parsed, run

E = "sezione_erario"
PDF = {}


@pytest.fixture
def ambiente(monkeypatch):
    db = db_nuovo("scenari_scadenzario")
    import app.services.f24_parser as f24_parser
    from app.database import Database

    monkeypatch.setattr(f24_parser, "parse_quietanza_f24", lambda pdf_content: PDF[pdf_content])
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    PDF.clear()
    return db


def _paga(db, righe, data, n=1):
    pdf = f"%PDF-scadenzario-{n}-{data}".encode()
    PDF[pdf] = quietanza_parsed(righe, data, f"2600000000000{n:04d}/000001")
    esito = run(qi.importa_quietanza_bytes(db, pdf, f"q{n}.pdf", fonte="test"))
    assert esito["success"] and not esito["duplicate"]
    return esito


def _voce(db, chiave):
    return run(db[sc.COLL].find_one({"chiave": chiave}, {"_id": 0}))


def _titolare(db):
    from app.routers.f24 import tributi
    from app.utils.dependencies import get_current_admin_user

    app = FastAPI()
    app.include_router(tributi.router, prefix="/api/f24")
    app.dependency_overrides[get_current_admin_user] = lambda: {"sub": "titolare", "role": "admin"}
    return TestClient(app)


def test_puntuale_con_la_proroga_di_ferragosto(ambiente):
    db = ambiente
    # ritenute di luglio: il 16/08 e' domenica e vale la proroga di Ferragosto, quindi il 20/08
    _paga(db, [(E, "1001", "07/2026", "1000.00", "0")], "2026-08-20")
    v = _voce(db, "sezione_erario|1001|2026|7")
    assert v["stato"] == sc.PUNTUALE and v["scadenza"] == "2026-08-20"
    assert v["pagamenti"][0]["giorni_ritardo"] == 0 and v["pagato_cents"] == 100000


def test_un_giorno_dopo_ferragosto_e_ritardo_non_ravveduto_con_giorni_e_ravvedimento_atteso(ambiente):
    db = ambiente
    _paga(db, [(E, "1001", "07/2026", "1000.00", "0")], "2026-08-21")
    v = _voce(db, "sezione_erario|1001|2026|7")
    p = v["pagamenti"][0]
    assert v["stato"] == sc.RITARDO_NON_RAVVEDUTO and p["giorni_ritardo"] == 1
    # nuovo regime, 1 giorno: 0,0833% di 1.000,00 = 0,83; interessi 1,6% per 1/365 = 0,04
    assert p["sanzione_attesa_cents"] == 83 and p["interessi_attesi_cents"] == 4
    assert "senza sanzione ne' interessi nella delega" in p["motivazione"]
    assert all(isinstance(p[k], int) for k in ("importo_cents", "sanzione_attesa_cents", "interessi_attesi_cents"))


def test_il_sedici_di_sabato_slitta_a_lunedi(ambiente):
    db = ambiente
    _paga(db, [(E, "1001", "04/2026", "500.00", "0")], "2026-05-18", n=1)     # 16/05 e' sabato
    _paga(db, [(E, "1001", "03/2026", "500.00", "0")], "2026-04-17", n=2)     # 16/04 e' giovedi
    assert _voce(db, "sezione_erario|1001|2026|4")["stato"] == sc.PUNTUALE
    assert _voce(db, "sezione_erario|1001|2026|4")["scadenza"] == "2026-05-18"
    v = _voce(db, "sezione_erario|1001|2026|3")
    assert v["scadenza"] == "2026-04-16" and v["pagamenti"][0]["giorni_ritardo"] == 1


def test_ravvedimento_corretto_nuovo_regime_e_ravveduto(ambiente):
    db = ambiente
    # 1.000,00 pagati 14 giorni dopo il 16/04/2026: sanzione 14 × 0,0833% = 11,66; interessi 1,6% × 14/365 = 0,61
    _paga(db, [(E, "1001", "03/2026", "1000.00", "0"), (E, "8926", "03/2026", "11.66", "0"),
               (E, "1989", "03/2026", "0.61", "0")], "2026-04-30")
    v = _voce(db, "sezione_erario|1001|2026|3")
    p = v["pagamenti"][0]
    assert v["stato"] == sc.RAVVEDUTO and p["giorni_ritardo"] == 14
    assert p["sanzione_attesa_cents"] == 1166 and p["interessi_attesi_cents"] == 61
    assert p["sanzioni_periodo_cents"] == 1166 and p["interessi_periodo_cents"] == 61
    assert "D.Lgs. 87/2024" in p["regime"] and "entro 14 giorni" in p["fascia"]


def test_ravvedimento_con_sanzione_insufficiente(ambiente):
    db = ambiente
    _paga(db, [(E, "1001", "03/2026", "1000.00", "0"), (E, "8926", "03/2026", "5.00", "0"),
               (E, "1989", "03/2026", "0.61", "0")], "2026-04-30")
    v = _voce(db, "sezione_erario|1001|2026|3")
    assert v["stato"] == sc.RAVVEDIMENTO_INSUFFICIENTE
    assert "sanzioni versate 5,00 € " in v["pagamenti"][0]["motivazione"]
    assert "su 11,66 € attese" in v["pagamenti"][0]["motivazione"]


def test_regime_previgente_30_per_cento_e_interessi_dell_anno(ambiente):
    db = ambiente
    # 16/04/2024 → 06/05/2024: 20 giorni = fascia 15–30 (15% ridotto a 1/10 = 1,5%) = 15,00; interessi 2,5% × 20/365 = 1,37
    _paga(db, [(E, "1001", "03/2024", "1000.00", "0"), (E, "8926", "03/2024", "15.00", "0"),
               (E, "1989", "03/2024", "1.37", "0")], "2024-05-06")
    p = _voce(db, "sezione_erario|1001|2024|3")["pagamenti"][0]
    assert p["giorni_ritardo"] == 20 and "previgente" in p["regime"] and "15–30 giorni" in p["fascia"]
    assert p["sanzione_attesa_cents"] == 1500 and p["interessi_attesi_cents"] == 137
    assert _voce(db, "sezione_erario|1001|2024|3")["stato"] == sc.RAVVEDUTO


def test_interessi_legali_a_cavallo_d_anno_usano_il_tasso_di_ciascun_anno(ambiente):
    db = ambiente
    # 16/12/2025 → 20/01/2026 = 35 giorni: 16 giorni al 2% (2025) + 19 giorni all'1,6% (2026)
    atteso = int((Decimal(100000) * (Decimal("0.02") * 16 + Decimal("0.016") * 19) / 365).quantize(Decimal(1)))
    assert atteso == 171
    _paga(db, [(E, "1001", "11/2025", "1000.00", "0"), (E, "8926", "11/2025", "13.89", "0"),
               (E, "1989", "11/2025", "1.71", "0")], "2026-01-20")
    v = _voce(db, "sezione_erario|1001|2025|11")
    p = v["pagamenti"][0]
    assert p["giorni_ritardo"] == 35 and p["interessi_attesi_cents"] == 171 and p["sanzione_attesa_cents"] == 1389
    assert v["stato"] == sc.RAVVEDUTO


def test_codice_senza_regola_resta_scadenza_non_determinata(ambiente):
    db = ambiente
    _paga(db, [(E, "9001", "2023", "50.00", "0")], "2026-06-30")
    v = _voce(db, "sezione_erario|9001|2023|")
    assert v["stato"] == sc.SCADENZA_NON_DETERMINATA and v["scadenza"] is None
    assert v["pagamenti"][0]["giorni_ritardo"] is None


def test_la_scheda_scadenzario_del_titolare_mostra_stati_conteggi_e_filtri(ambiente):
    db = ambiente
    _paga(db, [(E, "1001", "07/2026", "1000.00", "0")], "2026-08-20", n=1)                  # puntuale
    _paga(db, [(E, "1001", "06/2026", "300.00", "0")], "2026-07-31", n=2)                   # in ritardo
    _paga(db, [(E, "9001", "2023", "50.00", "0")], "2026-06-30", n=3)                       # senza regola
    client = _titolare(db)

    corpo = client.get("/api/f24/tributi/scadenzario", params={"anno": 2026}).json()
    per_stato = {s["id"]: s["n"] for s in corpo["per_stato"]}
    assert per_stato[sc.PUNTUALE] == 1 and per_stato[sc.RITARDO_NON_RAVVEDUTO] == 1 and per_stato[sc.SCADENZA_NON_DETERMINATA] == 0
    assert corpo["persistente"] is True
    ritardi = client.get("/api/f24/tributi/scadenzario", params={"stato": sc.RITARDO_NON_RAVVEDUTO}).json()["voci"]
    assert [v["periodo"] for v in ritardi] == ["06/2026"]
    assert ritardi[0]["stato_label"] == "Pagato in ritardo, senza ravvedimento"
    assert ritardi[0]["pagamenti"][0]["giorni_ritardo"] == 15 and ritardi[0]["scadenza"] == "2026-07-16"
    # senza anno si vedono anche gli anni senza regola
    tutti = {s["id"]: s["n"] for s in client.get("/api/f24/tributi/scadenzario").json()["per_stato"]}
    assert tutti[sc.SCADENZA_NON_DETERMINATA] == 1


def test_fasce_del_ravvedimento_nei_due_regimi_fino_all_oltre_due_anni():
    """Le percentuali per fascia (D.Lgs. 472/1997 art. 13, come modificato dal D.Lgs. 87/2024)."""
    from datetime import date

    nuovo, vecchio = date(2026, 4, 16), date(2024, 4, 16)
    assert [sc.percentuale_ravvedimento(g, nuovo)[0] for g in (14, 30, 90, 365, 730, 731)] == [
        Decimal(x) for x in ("1.1662", "1.25", "1.3889", "3.125", "3.5714", "4.1667")]       # 12,5% e 25% ridotti a 1/10, 1/9, 1/8, 1/7, 1/6
    assert [sc.percentuale_ravvedimento(g, vecchio)[0] for g in (14, 30, 90, 365, 730, 731)] == [
        Decimal(x) for x in ("1.4", "1.5", "1.6667", "3.75", "4.2857", "5")]                 # 15% e 30% ridotti a 1/10, 1/9, 1/8, 1/7, 1/6


def test_il_secondo_giro_dello_scadenzario_non_scrive_niente(ambiente):
    db = ambiente
    _paga(db, [(E, "1001", "06/2026", "300.00", "0")], "2026-07-31")
    secondo = run(sc.aggiorna(db))
    assert secondo["scritte"] == 0 and secondo["invariate"] == secondo["voci"] == 1


def test_registro_versamenti_dice_i_mesi_non_pervenuti_solo_a_scadenza_vera(ambiente):
    """Ritenute versate per gennaio-maggio: giugno e' un buco dal 17/07; luglio no fino al 20/08 (Ferragosto)."""
    from app.services import registro_versamenti_f24 as registro

    db = ambiente
    for n, mese in enumerate((1, 2, 3, 4, 5), 1):
        data = {1: "2026-02-16", 2: "2026-03-16", 3: "2026-04-16", 4: "2026-05-18", 5: "2026-06-16"}[mese]
        _paga(db, [(E, "1001", f"{mese:02d}/2026", "500.00", "0")], data, n=n)
    from app.services import f24_controllo_incrociato as reg

    pagamenti = reg.pagamenti_da_quietanze([q for q in run(reg.carica_registro(db))["quietanze"] if q.get("righe")])

    def mancanti(oggi):
        voce = registro.costruisci(pagamenti, anno=2026, oggi=oggi)["codici"]
        return [c for c in voce if c["codice"] == "1001"][0]["mancanti"]
    assert mancanti("2026-07-16") == []            # giugno scade il 16/07: ancora nei termini
    assert mancanti("2026-07-17") == [6]
    assert mancanti("2026-08-19") == [6]           # luglio scade il 20/08 (Ferragosto), non il 16
    assert mancanti("2026-08-21") == [6, 7]
    assert mancanti("2026-09-17") == [6, 7, 8]


def test_inps_in_ritardo_e_da_verificare_non_ravvedimento_art_13(ambiente):
    db = ambiente
    INPS = "sezione_inps"
    _paga(db, [(INPS, "DM10", "05/2026", "2840.00", "0")], "2026-06-30", n=1)      # 16/06 + 14 giorni
    _paga(db, [(INPS, "DM10", "06/2026", "2840.00", "0")], "2026-07-16", n=2)      # puntuale
    ritardo = _voce(db, "sezione_inps|DM10|2026|5")
    assert ritardo["stato"] == sc.RITARDO_DA_VERIFICARE and ritardo["pagamenti"][0]["giorni_ritardo"] == 14
    assert "sanzioni civili INPS/INAIL" in ritardo["motivazione"]
    assert ritardo["pagamenti"][0]["sanzione_attesa_cents"] == 0       # nessuna sanzione art. 13 inventata
    assert _voce(db, "sezione_inps|DM10|2026|6")["stato"] == sc.PUNTUALE
