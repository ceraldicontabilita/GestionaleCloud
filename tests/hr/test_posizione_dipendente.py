"""Posizione dare/avere del dipendente (regole del titolare, dati inventati).

- busta con acconto recuperato in busta: dovuto = netto + acconto;
- acconto pagato con bonifico fuori busta: solo avere;
- conciliazione: parte ordinaria nel dare, bonus solo nel riquadro bonus;
- riporto del saldo da un anno al successivo;
- totale diverso dalla somma delle voci: rifiutato;
- «importi non compilati»: accettato con totale nullo;
- coda «Bonifici da associare» con tipo acconto / conciliazione / bonus.
"""
import asyncio
from decimal import Decimal

import pytest
from fastapi import HTTPException
from mongomock_motor import AsyncMongoMockClient

from app.hr.routers import dipendenti_cloud as cloud
from app.hr.routers import posizione_dipendente as router_pos
from app.parsers.cedolino_voci import VOCI_ACCONTO_RECUPERATO, acconto_recuperato_in_busta
from app.services import posizione_dipendente as pos


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def hr(monkeypatch):
    from app.hr.database import Database as DatabaseHR

    db = AsyncMongoMockClient()["hr_posizione"]
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: db))
    _run(db.dipendenti.insert_one({"id": "dip-1", "nome_completo": "Rossi Mario"}))
    return db


def _conc(**extra):
    base = {"dipendente_id": "dip-1", "data": "2026-05-10", "tipo": "conciliazione_sindacale",
            "modalita_pagamento": "bonifico",
            "voci": [{"voce": "straordinari", "importo": "700.00"},
                     {"voce": "bonus_transattivo", "importo": "300.00"}],
            "totale": "1000.00"}
    base.update(extra)
    return base


# ── lettore: la voce di acconto recuperato ──────────────────────────────────

def test_voci_acconto_in_un_elenco_solo():
    codici = {c for c, _ in VOCI_ACCONTO_RECUPERATO}
    assert {"000306", "8210"} <= codici
    assert acconto_recuperato_in_busta("000306 Recupero acconto 400,00")["importo"] == "400,00"
    assert acconto_recuperato_in_busta("8210 ACCONTO TRATT. RETRIB. 1.200,00")["codice"] == "8210"
    # l'anticipo del fondo TFR non e' stipendio
    assert acconto_recuperato_in_busta("ACCONTI GIA' EROGATI 2.000,00") is None


def test_lettore_unico_porta_l_acconto_nei_dati_chiave():
    from app.services.cedolini_motore import _con_voci

    busta = _con_voci({"_raw_text": "000306 Recupero acconto 400,00\nTOTALE NETTO 101,00"})
    assert busta["dati_chiave"]["acconto_recuperato_busta"] == "400,00"
    assert busta["dati_chiave"]["acconto_recuperato_voce"] == "000306"


# ── dovuto della busta ───────────────────────────────────────────────────────

def test_busta_con_acconto_in_busta_dovuto_netto_piu_acconto():
    ced = {"id": "c1", "netto": 150.0, "competenze": 1400.0, "trattenute": 250.0,
           "dati_chiave": {"acconto_recuperato_busta": "1.000,00", "acconto_recuperato_voce": "000306"}}
    d = pos.dovuto_busta({"importo_busta": 150.0}, ced)
    assert d["dovuto"] == Decimal("1150.00") and d["acconto"] == Decimal("1000.00")
    # riga HR gia' riverificata: netto = totale, cella in netto_busta -> niente doppio conteggio
    ced2 = {"id": "c2", "netto": 1150.0, "netto_busta": 150.0, "acconti": {"acconto_recuperato": 1000.0}}
    assert pos.dovuto_busta({"importo_busta": 1150.0}, ced2)["dovuto"] == Decimal("1150.00")
    # vecchio import: netto gia' totale (= competenze − trattenute), acconto annotato
    ced3 = {"id": "c3", "netto": 1150.0, "competenze": 1400.0, "trattenute": 250.0,
            "acconti": {"acconto_recuperato": 1000.0}}
    assert pos.dovuto_busta({}, ced3)["dovuto"] == Decimal("1150.00")
    # nessuna voce: ripiego su competenze − trattenute oltre 1,00
    ced4 = {"id": "c4", "netto": 150.0, "competenze": 1400.0, "trattenute": 250.0}
    assert pos.dovuto_busta({}, ced4)["dovuto"] == Decimal("1150.00")
    # importo corretto a mano: vince
    assert pos.dovuto_busta({"importo_busta": 900.0, "importo_busta_manuale": True}, ced)["dovuto"] == Decimal("900.00")


def test_posizione_busta_con_acconto_e_acconto_bonifico_fuori_busta(hr):
    _run(hr.cedolini.insert_one({"id": "c1", "dipendente_id": "dip-1", "anno": 2026, "mese": 3,
                                 "tipo_cedolino": "ordinario", "netto": 150.0,
                                 "dati_chiave": {"acconto_recuperato_busta": "1.000,00"}}))
    _run(hr.paghe_mensili.insert_one({"dipendente_id": "dip-1", "anno": 2026, "mese": 3,
                                      "importo_busta": 150.0, "cedolino_id": "c1"}))
    # acconto di marzo dato col bonifico il 10/03, recuperato nella busta di marzo
    _run(hr.acconti_dipendenti.insert_one({"id": "a1", "dipendente_id": "dip-1", "tipo": "stipendio",
                                           "importo": 1000.0, "data": "2026-03-10", "stato": "registrato"}))
    # acconto di aprile pagato fuori busta: solo avere
    _run(hr.acconti_dipendenti.insert_one({"id": "a2", "dipendente_id": "dip-1", "tipo": "stipendio",
                                           "importo": 200.0, "data": "2026-04-05", "stato": "registrato"}))
    # un acconto TFR non e' stipendio
    _run(hr.acconti_dipendenti.insert_one({"id": "a3", "dipendente_id": "dip-1", "tipo": "tfr",
                                           "importo": 500.0, "data": "2026-04-06"}))
    _run(hr.pagamenti_esiti.insert_one({"key": "k1", "dipendente_id": "dip-1", "anno": 2026, "mese": 3,
                                        "data": "2026-04-02", "importo": 150.0}))
    p = _run(pos.posizione_dipendente(hr, "dip-1", 2026))
    assert p["totale_dare"] == 1150.0
    assert p["totale_avere"] == 1350.0  # 1000 acconto + 150 bonifico + 200 acconto fuori busta
    assert p["chiusura"] == -200.0      # l'acconto di aprile e' un credito verso il dipendente
    busta = next(r for r in p["righe"] if r["tipo"] == "busta")
    assert busta["dare"] == 1150.0 and "acconto recuperato" in busta["descrizione"]
    acconti = [r for r in p["righe"] if r["tipo"] == "acconto"]
    assert sorted(r["avere"] for r in acconti) == [200.0, 1000.0]
    assert all(r["dare"] is None for r in acconti)

    # la vecchia prima nota mensile e' la stessa posizione, per competenza
    pn = _run(cloud.prima_nota("dip-1"))
    assert pn["saldo_finale"] == -200.0
    marzo = next(r for r in pn["righe"] if (r["anno"], r["mese"]) == (2026, 3))
    assert marzo["busta"] == 1150.0 and marzo["saldo_progressivo"] == 0.0


def test_conciliazione_bonus_a_parte_e_riporto_fra_anni(hr):
    _run(hr.paghe_mensili.insert_one({"dipendente_id": "dip-1", "anno": 2025, "mese": 12,
                                      "importo_busta": 1200.0}))
    _run(hr.pagamenti_esiti.insert_one({"key": "k1", "dipendente_id": "dip-1", "anno": 2025, "mese": 12,
                                        "data": "2025-12-30", "importo": 1000.0}))
    c = _run(router_pos.crea_conciliazione(_conc()))
    assert c["stato"] == "da_pagare" and c["bonus"] == "300.00" and c["parte_ordinaria"] == "700.00"
    _run(router_pos.aggiungi_pagamento(c["id"], {"data": "2026-05-20", "importo": "700", "parte": "conciliazione",
                                                 "modalita": "assegno"}))
    c = _run(router_pos.aggiungi_pagamento(c["id"], {"data": "2026-05-21", "importo": "100", "parte": "bonus",
                                                     "modalita": "contanti"}))
    assert c["stato"] == "pagata_in_parte" and c["pagato_bonus"] == "100.00"

    p25 = _run(pos.posizione_dipendente(hr, "dip-1", 2025))
    assert p25["apertura"] == 0.0 and p25["chiusura"] == 200.0
    p26 = _run(pos.posizione_dipendente(hr, "dip-1", 2026))
    assert p26["apertura"] == 200.0               # riporto dal 2025
    assert p26["totale_dare"] == 700.0            # solo la parte non bonus
    assert p26["totale_avere"] == 700.0
    assert p26["chiusura"] == 200.0
    assert p26["bonus"] == {**p26["bonus"], "dovuto": 300.0, "pagato": 100.0, "saldo": 200.0}
    assert [a["anno"] for a in p26["per_anno"]] == [2025, 2026]
    assert p26["per_anno"][1]["apertura"] == 200.0


def test_totale_diverso_dalla_somma_rifiutato(hr):
    with pytest.raises(HTTPException) as exc:
        _run(router_pos.crea_conciliazione(_conc(totale="999.99")))
    assert exc.value.status_code == 400 and exc.value.detail["code"] == "TOTALE_NON_QUADRA"
    with pytest.raises(HTTPException) as exc:
        _run(router_pos.crea_conciliazione(_conc(voci=[{"voce": "altro", "importo": "10"}], totale="10")))
    assert exc.value.detail["code"] == "DESCRIZIONE_MANCANTE"
    with pytest.raises(HTTPException) as exc:
        _run(router_pos.crea_conciliazione(_conc(voci=[{"voce": "mance", "importo": "10"}], totale="10")))
    assert exc.value.detail["code"] == "VALORE_NON_AMMESSO"


def test_importi_non_compilati_accettato_senza_totale(hr):
    c = _run(router_pos.crea_conciliazione(_conc(
        importi_non_compilati=True, totale=None,
        voci=[{"voce": "straordinari"}, {"voce": "bonus_transattivo"}])))
    assert c["totale"] is None and c["bonus"] is None and c["importi_non_compilati"] is True
    p = _run(pos.posizione_dipendente(hr, "dip-1", 2026))
    riga = next(r for r in p["righe"] if r["tipo"] == "conciliazione")
    assert riga["dare"] is None and "importi non compilati" in riga["avviso"]
    assert p["chiusura"] == 0.0 and p["bonus"]["dovuto"] == 0.0
    # un importo inventato non passa
    with pytest.raises(HTTPException):
        _run(router_pos.crea_conciliazione(_conc(importi_non_compilati=True, totale="1000.00")))


def test_coda_bonifici_tipo_acconto_e_conciliazione(hr):
    _run(hr.bonifici_da_associare.insert_many([
        {"id": "q1", "data": "2026-06-12", "importo": 250.0, "causale": "BENEFICIARI DIVERSI", "stato": "da_associare"},
        {"id": "q2", "data": "2026-06-15", "importo": 700.0, "causale": "BENEFICIARI DIVERSI", "stato": "da_associare"},
        {"id": "q3", "data": "2026-06-16", "importo": 300.0, "causale": "BENEFICIARI DIVERSI", "stato": "da_associare"},
    ]))
    c = _run(router_pos.crea_conciliazione(_conc()))

    # acconto: anno e mese dalla data del bonifico, niente pagamenti_esiti
    r = _run(cloud.associa_bonifico("q1", {"dipendente_id": "dip-1", "tipo": "acconto"}))
    assert r["tipo"] == "acconto"
    acc = _run(hr.acconti_dipendenti.find_one({"bonifico_da_associare_id": "q1"}, {"_id": 0}))
    assert acc["tipo"] == "stipendio" and acc["scalato_su_anno_mese"] == "2026-06" and acc["importo"] == 250.0
    assert _run(hr.pagamenti_esiti.count_documents({})) == 0
    assert _run(hr.bonifici.count_documents({})) == 0
    # gia' associato: non si ripete
    with pytest.raises(HTTPException) as exc:
        _run(cloud.associa_bonifico("q1", {"dipendente_id": "dip-1", "tipo": "acconto"}))
    assert exc.value.status_code == 409

    # conciliazione senza sceglierla: 400
    with pytest.raises(HTTPException) as exc:
        _run(cloud.associa_bonifico("q2", {"dipendente_id": "dip-1", "tipo": "conciliazione"}))
    assert exc.value.detail["code"] == "CONCILIAZIONE_MANCANTE"
    _run(cloud.associa_bonifico("q2", {"dipendente_id": "dip-1", "tipo": "conciliazione",
                                       "conciliazione_id": c["id"]}))
    _run(cloud.associa_bonifico("q3", {"dipendente_id": "dip-1", "tipo": "bonus",
                                       "conciliazione_id": c["id"]}))
    conc = _run(router_pos.elenco_conciliazioni("dip-1"))["righe"][0]
    assert conc["stato"] == "pagata" and conc["pagato_ordinaria"] == "700.00" and conc["pagato_bonus"] == "300.00"
    assert {p["origine"] for p in conc["pagamenti"]} == {"bonifici_da_associare"}
    coda = _run(hr.bonifici_da_associare.find_one({"id": "q3"}, {"_id": 0}))
    assert coda["stato"] == "associato" and coda["associato_tipo"] == "bonus"

    p = _run(pos.posizione_dipendente(hr, "dip-1", 2026))
    assert p["totale_dare"] == 700.0 and p["totale_avere"] == 950.0  # 700 conciliazione + 250 acconto
    assert p["bonus"]["saldo"] == 0.0

    # un pagamento arrivato dalla coda non si toglie a mano
    pid = conc["pagamenti"][0]["id"]
    with pytest.raises(HTTPException) as exc:
        _run(router_pos.togli_pagamento(c["id"], pid))
    assert exc.value.status_code == 409


def test_coda_bonifici_conciliazione_di_un_altro_dipendente(hr):
    _run(hr.dipendenti.insert_one({"id": "dip-2", "nome_completo": "Bianchi Luca"}))
    _run(hr.bonifici_da_associare.insert_one({"id": "q9", "data": "2026-06-12", "importo": 50.0,
                                              "stato": "da_associare"}))
    c = _run(router_pos.crea_conciliazione(_conc()))
    with pytest.raises(HTTPException) as exc:
        _run(cloud.associa_bonifico("q9", {"dipendente_id": "dip-2", "tipo": "bonus", "conciliazione_id": c["id"]}))
    assert exc.value.detail["code"] == "DIPENDENTE_DIVERSO"
    assert _run(hr.bonifici_da_associare.find_one({"id": "q9"}))["stato"] == "da_associare"


def test_documento_conciliazione_con_impronta(hr):
    c = _run(router_pos.crea_conciliazione(_conc()))
    doc = _run(pos.salva_documento(hr, c["id"], "verbale.pdf", b"%PDF-1.4 prova"))
    assert len(doc["sha256"]) == 64 and doc["mime"] == "application/pdf"
    contenuto, nome, mime = _run(pos.leggi_documento(hr, c["id"]))
    assert contenuto == b"%PDF-1.4 prova" and nome == "verbale.pdf"
    with pytest.raises(pos.ErrorePosizione):
        _run(pos.salva_documento(hr, c["id"], "verbale.exe", b"x"))
    vista = _run(router_pos.elenco_conciliazioni("dip-1"))["righe"][0]
    assert "file_data" not in vista and vista["documento"]["nome"] == "verbale.pdf"
