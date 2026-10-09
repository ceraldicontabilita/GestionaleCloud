"""Collaudo funzionale PayPal <-> banca: giro automatico e collegamento scelto dal titolare.

ATTESO secondo CLAUDE.md («PayPal pagato dal conto»): il collegamento a mano vale solo per i
candidati veri (uscite non collegate, stesso importo al centesimo, da 3 giorni prima a 20 dopo),
un movimento non candidato e' 409 e una transazione gia' provata non si ricollega; il giro
`paypal_automatico` abbina l'addebito SDD solo se la coppia e' biunivoca, N addebiti e N pagamenti
dello stesso importo in ordine di data, e l'accredito «BON.DA PayPal» a un solo prelievo T04.
"""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import paypal_statements as mod
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

SDD = "ADDEBITO DIRETTO SDD - SDD CORE: 49RJ2252ASLM4 PayPal Europe S.a.r.l. et Cie S.C.A"
BON = "BONIF. VS. FAVORE - BON.DA PayPal Europe S.a.r.l. et Cie S.C.A - YYW1052371473308/PAYPAL"


def _run(coro):
    return asyncio.run(coro)


def _tx(tid, data, importo, tipo="T0006", **extra):
    return {"transaction_id": tid, "event_code": tipo, "tipo": tipo, "lordo": importo, "importo": importo,
            "currency": "EUR", "data": data, "transaction_status": "S", "nome_controparte": "Spotify", **extra}


def _mov(mid, data, importo, descrizione=SDD, tipo="uscita", **extra):
    return {"id": mid, "data": data, "importo": importo, "tipo": tipo, "descrizione": descrizione, **extra}


@pytest.fixture
def db():
    return ClientArchivioMemoria()["paypal-scenari"]


@pytest.fixture
def client(db, monkeypatch):
    from app.database import Database
    from app.utils.dependencies import get_current_admin_user

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/paypal-statements")
    app.dependency_overrides[get_current_admin_user] = lambda: {"sub": "a", "role": "admin"}
    return TestClient(app)


def _riempi(db, txs=(), movimenti=()):
    if txs:
        _run(db["paypal_transactions"].insert_many([dict(t) for t in txs]))
    if movimenti:
        _run(db["estratto_conto_movimenti"].insert_many([dict(m) for m in movimenti]))


def _legami(db):
    return {t["transaction_id"]: t.get("movimento_banca_id")
            for t in _run(db["paypal_transactions"].find({}).to_list(100))}


# ── giro automatico: addebito SDD ────────────────────────────────────────────────────────

def test_sdd_con_coppia_biunivoca_si_abbina_da_solo_e_il_secondo_giro_non_cambia_nulla(db):
    _riempi(db, [_tx("P1", "2026-09-12", -20.99)], [_mov("M1", "2026-09-16", 20.99)])
    anteprima = _run(mod._auto_riconcilia(db, applica=False))
    assert anteprima["proposte"] == 1 and anteprima["riconciliati"] == 0
    assert _legami(db) == {"P1": None}                                    # l'anteprima non scrive

    giro = _run(mod._auto_riconcilia(db, applica=True))
    assert giro["riconciliati"] == 1 and _legami(db) == {"P1": "M1"}
    mov = _run(db["estratto_conto_movimenti"].find_one({"id": "M1"}))
    assert mov["riconciliato"] is True and mov["paypal_transaction_id"] == "P1"
    assert _run(mod._auto_riconcilia(db, applica=True))["riconciliati"] == 0


def test_un_pagamento_e_due_addebiti_uguali_restano_sospesi(db):
    _riempi(db, [_tx("P1", "2026-09-12", -20.99)],
            [_mov("M1", "2026-09-14", 20.99), _mov("M2", "2026-09-14", 20.99, SDD + " bis")])
    esito = _run(mod._auto_riconcilia(db, applica=True))
    assert esito["riconciliati"] == 0 and esito["ambigui"] >= 1
    assert _legami(db) == {"P1": None}


def test_pagamenti_dello_stesso_importo_a_distanza_di_giorni_non_si_scambiano(db):
    """Tre abbonamenti da 32,94 € a distanza di una settimana: ogni addebito va al suo pagamento."""
    _riempi(db, [_tx("P-C", "2026-09-20", -32.94), _tx("P-A", "2026-09-02", -32.94), _tx("P-B", "2026-09-10", -32.94)],
            [_mov("M-3", "2026-09-22", 32.94), _mov("M-1", "2026-09-04", 32.94), _mov("M-2", "2026-09-12", 32.94)])
    _run(mod._auto_riconcilia(db, applica=True))
    assert _legami(db) == {"P-A": "M-1", "P-B": "M-2", "P-C": "M-3"}


def test_n_addebiti_e_n_pagamenti_vicini_si_abbinano_in_ordine(db):
    _riempi(db, [_tx("P-2", "2026-09-05", -32.94), _tx("P-1", "2026-09-03", -32.94), _tx("P-3", "2026-09-07", -32.94)],
            [_mov("M-3", "2026-09-10", 32.94), _mov("M-1", "2026-09-06", 32.94), _mov("M-2", "2026-09-08", 32.94)])
    esito = _run(mod._auto_riconcilia(db, applica=True))
    assert esito["riconciliati"] == 3 and esito["ambigui"] == 0
    assert _legami(db) == {"P-1": "M-1", "P-2": "M-2", "P-3": "M-3"}


def test_n_pagamenti_e_m_addebiti_diversi_non_si_abbinano_a_caso(db):
    _riempi(db, [_tx("P-1", "2026-09-03", -32.94), _tx("P-2", "2026-09-05", -32.94)],
            [_mov("M-1", "2026-09-06", 32.94), _mov("M-2", "2026-09-08", 32.94), _mov("M-3", "2026-09-09", 32.94)])
    esito = _run(mod._auto_riconcilia(db, applica=True))
    assert esito["riconciliati"] == 0
    assert _legami(db) == {"P-1": None, "P-2": None}


def test_oltre_10_giorni_non_si_abbina_salvo_l_id_paypal_nella_causale(db):
    _riempi(db, [_tx("P1", "2026-09-01", -50.0), _tx("ABCDEF123456", "2026-09-01", -60.0)],
            [_mov("M1", "2026-09-15", 50.0), _mov("M2", "2026-09-15", 60.0, SDD + " ABCDEF123456")])
    _run(mod._auto_riconcilia(db, applica=True))
    assert _legami(db) == {"P1": None, "ABCDEF123456": "M2"}


def test_importo_diverso_di_un_centesimo_o_entrata_non_si_abbinano_a_un_pagamento(db):
    _riempi(db, [_tx("P1", "2026-09-12", -20.99)],
            [_mov("M1", "2026-09-14", 21.00), _mov("M2", "2026-09-14", 20.99, BON, tipo="entrata")])
    assert _run(mod._auto_riconcilia(db, applica=True))["riconciliati"] == 0


# ── giro automatico: accredito «BON.DA PayPal» ───────────────────────────────────────────

def test_accredito_si_abbina_al_solo_prelievo_t04_e_non_all_incasso(db):
    _riempi(db, [_tx("INCASSO", "2026-08-04", 9.38, tipo="T1107"),
                 _tx("PRELIEVO", "2026-08-04", -9.38, tipo="T0403")],
            [_mov("M-BON", "2026-08-05", 9.38, BON, tipo="entrata")])
    _run(mod._auto_riconcilia(db, applica=True))
    assert _legami(db) == {"INCASSO": None, "PRELIEVO": "M-BON"}


def test_un_prelievo_e_due_accrediti_uguali_non_si_abbinano_a_caso(db):
    _riempi(db, [_tx("PRELIEVO", "2026-08-04", -9.38, tipo="T0403")],
            [_mov("M-1", "2026-08-05", 9.38, BON, tipo="entrata"), _mov("M-2", "2026-08-05", 9.38, BON + " 2", tipo="entrata")])
    assert _run(mod._auto_riconcilia(db, applica=True))["riconciliati"] == 0
    assert _legami(db) == {"PRELIEVO": None}


def test_due_prelievi_e_due_accrediti_uguali_si_abbinano_in_ordine(db):
    _riempi(db, [_tx("PRE-2", "2026-08-08", -9.38, tipo="T0403"), _tx("PRE-1", "2026-08-04", -9.38, tipo="T0403")],
            [_mov("M-2", "2026-08-10", 9.38, BON + " 2", tipo="entrata"), _mov("M-1", "2026-08-05", 9.38, BON, tipo="entrata")])
    _run(mod._auto_riconcilia(db, applica=True))
    assert _legami(db) == {"PRE-1": "M-1", "PRE-2": "M-2"}


def test_il_prelievo_non_e_un_pagamento_e_non_ruba_l_addebito_sdd_dello_stesso_importo(db):
    """Un acquisto da 9,38 e un prelievo da 9,38: l'SDD e' dell'acquisto, il bonifico del prelievo."""
    _riempi(db, [_tx("ACQUISTO", "2026-08-04", -9.38), _tx("PRELIEVO", "2026-08-04", -9.38, tipo="T0403")],
            [_mov("M-SDD", "2026-08-06", 9.38), _mov("M-BON", "2026-08-05", 9.38, BON, tipo="entrata")])
    esito = _run(mod._auto_riconcilia(db, applica=True))
    assert esito["ambigui"] == 0 and esito["riconciliati"] == 2
    assert _legami(db) == {"ACQUISTO": "M-SDD", "PRELIEVO": "M-BON"}


def test_il_prelievo_non_e_una_spesa_nel_report(db, client):
    _riempi(db, [_tx("ACQUISTO", "2026-08-04", -9.38), _tx("PRELIEVO", "2026-08-04", -500.0, tipo="T0403")])
    report = client.get("/api/paypal-statements/report").json()
    assert report["totale_speso"] == -9.38 and report["totale_transazioni"] == 1     # uscite con segno


# ── collegamento scelto dal titolare ─────────────────────────────────────────────────────

def _candidati(client, tid="TX"):
    return client.get(f"/api/paypal-statements/transazione/{tid}/candidati-banca").json()["candidati"]


def test_i_candidati_rispettano_finestra_importo_verso_e_stato(db, client):
    _riempi(db, [_tx("TX", "2026-09-12", -20.99)], [
        _mov("M-m3", "2026-09-09", 20.99), _mov("M-m4", "2026-09-08", 20.99),          # -3 si, -4 no
        _mov("M-p20", "2026-10-02", 20.99), _mov("M-p21", "2026-10-03", 20.99),        # +20 si, +21 no
        _mov("M-importo", "2026-09-13", 20.98), _mov("M-entrata", "2026-09-13", 20.99, tipo="entrata"),
        _mov("M-gia", "2026-09-13", 20.99, riconciliato=True),
        _mov("M-altro-paypal", "2026-09-13", 20.99, paypal_transaction_id="ALTRA"),
        _mov("M-ok", "2026-09-13", 20.99, "ADDEBITO DIRETTO SPOTIFY"),
    ])
    assert {c["id"] for c in _candidati(client)} == {"M-m3", "M-p20", "M-ok"}
    # il piu' vicino per primo
    assert _candidati(client)[0]["id"] == "M-ok"


def test_collega_banca_solo_a_un_candidato_vero_e_mai_due_volte(db, client):
    _riempi(db, [_tx("TX", "2026-09-12", -20.99), _tx("TX2", "2026-09-12", -20.99)],
            [_mov("M-ok", "2026-09-13", 20.99), _mov("M-no", "2026-09-13", 20.50)])
    base = "/api/paypal-statements/transazione"
    assert client.post(f"{base}/TX/collega-banca", json={}).status_code == 400
    assert client.post(f"{base}/TX/collega-banca", json={"movimento_id": "M-no"}).status_code == 409
    assert _legami(db) == {"TX": None, "TX2": None}

    ok = client.post(f"{base}/TX/collega-banca", json={"movimento_id": "M-ok"})
    assert ok.status_code == 200
    mov = _run(db["estratto_conto_movimenti"].find_one({"id": "M-ok"}))
    assert mov["paypal_transaction_id"] == "TX" and mov["tipo_riconciliazione"] == "paypal_scelto_dal_titolare"
    # transazione gia' provata: non si ricollega; movimento gia' preso: non e' piu' candidato per TX2
    assert client.post(f"{base}/TX/collega-banca", json={"movimento_id": "M-ok"}).status_code == 409
    assert client.post(f"{base}/TX2/collega-banca", json={"movimento_id": "M-ok"}).status_code == 409
    assert _legami(db)["TX2"] is None
    assert client.get(f"{base}/NON-ESISTE/candidati-banca").status_code == 404


def test_la_scelta_del_titolare_non_e_mai_automatica(db, client):
    """Con un solo candidato valido il giro automatico non lo applica se non e' un addebito PayPal."""
    _riempi(db, [_tx("TX", "2026-09-12", -20.99)], [_mov("M-ok", "2026-09-13", 20.99, "ADDEBITO DIRETTO SPOTIFY")])
    _run(mod._auto_riconcilia(db, applica=True))      # la causale non cita PayPal: il giro non lo vede
    assert _legami(db) == {"TX": None}
    assert [c["id"] for c in _candidati(client)] == ["M-ok"]


def test_collega_banca_richiede_admin(db, monkeypatch):
    from app.database import Database

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    app = FastAPI()
    app.include_router(mod.router, prefix="/api/paypal-statements")
    anonimo = TestClient(app)
    _riempi(db, [_tx("TX", "2026-09-12", -20.99)], [_mov("M-ok", "2026-09-13", 20.99)])
    risposta = anonimo.post("/api/paypal-statements/transazione/TX/collega-banca", json={"movimento_id": "M-ok"})
    assert risposta.status_code in (401, 403)
    assert _legami(db) == {"TX": None}
