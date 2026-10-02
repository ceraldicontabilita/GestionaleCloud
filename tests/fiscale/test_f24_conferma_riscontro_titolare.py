"""PROBABILE e PARZIALE hanno un'azione: la conferma del titolare.

`conferma_riscontro_titolare` scrive il pagamento con lo stesso motore del
CERTO (`applica_riscontri_modelli` / `applica_riscontri_quietanze`: nessun
secondo writer), segna la relazione `confirmed` con `actor=titolare` e il
motivo (chip, «altro» vuole il testo), registra la differenza del PARZIALE
senza inventare conguagli, rifiuta un movimento che il motore non ha proposto
(409) e un motivo fuori elenco (422). Il secondo giro non riscrive.
"""
import asyncio

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.db_collections import COLL_ENTITY_RELATIONS, COLL_ESTRATTO_CONTO, COLL_F24, COLL_QUIETANZE_F24
from app.services import f24_controllo_incrociato as reg
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _m(id_, data, importo, incasso=None):
    causale = "I24 AGENZIA ENTRATE - PAG.TO TELEMATICO"
    if incasso:
        causale += f" - DATA INCASSO {incasso} 2026-08-19-22.35.33.939744076309"
    return {"id": id_, "data": data, "importo": importo, "descrizione": causale, "tipo": "uscita"}


def _modello(id_, data, saldo, **extra):
    return {"id": id_, "status": "da_pagare", "pagato": False, "file_name": f"{id_}.pdf",
            "dati_generali": {"data_versamento": data}, "totali": {"saldo_netto": saldo},
            "sezione_erario": [{"codice_tributo": "1001", "periodo_riferimento": "12/2025",
                                "importo_debito": saldo}], **extra}


def _q(id_, data, saldo, protocollo="26082011065626134/000001", **extra):
    return {"id": id_, "data_pagamento": data, "saldo": saldo,
            "protocollo_telematico": protocollo, "filename": f"{id_}.pdf", "f24_associati": [], **extra}


def _db(quietanze=(), movimenti=(), modelli=()):
    db = ClientArchivioMemoria()["f24_conferma"]

    async def _carica():
        for q in quietanze:
            await db[COLL_QUIETANZE_F24].insert_one(dict(q))
        for m in movimenti:
            await db[COLL_ESTRATTO_CONTO].insert_one(dict(m))
        for f in modelli:
            await db[COLL_F24].insert_one(dict(f))
    _run(_carica())
    return db


def _relazioni(db, target):
    """(movimento, stato, chi) -> relazione; «chi» e' `updated_by` (l'`actor` dell'upsert)."""
    return {(r["source"]["id"], r["status"], r.get("updated_by")): r
            for r in _run(db[COLL_ENTITY_RELATIONS].find({"target.id": target}, {"_id": 0}).to_list(50))}


def _conferma(db, f24_id, movimento_id, motivo="unico_addebito_compatibile", **kw):
    return _run(reg.conferma_riscontro_titolare(db, f24_id=f24_id, movimento_id=movimento_id, motivo=motivo, **kw))


# ── modello PROBABILE (due candidati) ────────────────────────────────────────

def _db_probabile():
    return _db(movimenti=[_m("m1", "2026-01-16", -500.00), _m("m2", "2026-01-16", -500.00)],
               modelli=[_modello("f1", "2026-01-16", 500.00)])


def test_il_motore_da_solo_non_sceglie_fra_due_candidati():
    db = _db_probabile()
    esito = _run(reg.riconcilia_f24_banca(db))
    [r] = esito["modelli"]["da_verificare"]
    assert r["livello"] == reg.LIVELLO_PROBABILE and {c["movimento_id"] for c in r["candidati"]} == {"m1", "m2"}
    assert _run(db[COLL_F24].find_one({"id": "f1"}))["pagato"] is False


def test_la_conferma_scrive_il_pagamento_come_il_certo_e_la_relazione_del_titolare():
    db = _db_probabile()
    _run(reg.riconcilia_f24_banca(db))  # le relazioni pending verso m1 e m2
    esito = _conferma(db, "f1", "m1", utente="titolare@test")

    assert esito["natura"] == "modello" and esito["livello"] == reg.LIVELLO_PROBABILE
    assert esito["differenza_cents"] is None and esito["scritti"]["modelli"]["modelli"] == 1
    f = _run(db[COLL_F24].find_one({"id": "f1"}))
    assert f["pagato"] is True and f["movimento_bancario_id"] == "m1" and f["pagamento_verificato_banca"] is True
    assert f["data_pagamento_effettivo"] == "2026-01-16"
    assert f["conferma_titolare_banca"]["motivo"] == "unico_addebito_compatibile"
    assert f["conferma_titolare_banca"]["actor"] == "titolare" and f["conferma_titolare_banca"]["utente"] == "titolare@test"
    assert f["livello_riscontro_banca"] == reg.LIVELLO_PROBABILE
    m1 = _run(db[COLL_ESTRATTO_CONTO].find_one({"id": "m1"}))
    assert m1["riconciliato"] is True and m1["f24_ids"] == ["f1"]
    assert not _run(db[COLL_ESTRATTO_CONTO].find_one({"id": "m2"})).get("riconciliato")
    rel = _relazioni(db, "f1")
    assert ("m1", "confirmed", "titolare") in rel and ("m2", "revoked", "system") in rel
    confermata = rel[("m1", "confirmed", "titolare")]
    assert confermata["rule"] == f"f24_banca:PROBABILE:{reg.REGOLA_CONFERMA_TITOLARE}"
    assert {e["type"]: e["value"] for e in confermata["evidence"]}["motivo"] == reg.MOTIVI_CONFERMA_TITOLARE["unico_addebito_compatibile"]


def test_la_seconda_conferma_e_idempotente_e_il_giro_non_riscrive():
    db = _db_probabile()
    _conferma(db, "f1", "m1")
    assert _conferma(db, "f1", "m1")["gia_confermato"] is True
    assert _run(reg.riconcilia_f24_banca(db))["scritti"]["modelli"] == {"modelli": 0, "relazioni": 0}


def test_un_movimento_non_candidato_e_rifiutato():
    db = _db(movimenti=[_m("m1", "2026-01-16", -500.00), _m("m2", "2026-01-16", -500.00),
                        _m("lontano", "2026-03-30", -500.00)],
             modelli=[_modello("f1", "2026-01-16", 500.00)])
    with pytest.raises(reg.ConfermaNonAmmessa) as exc:
        _conferma(db, "f1", "lontano")
    assert exc.value.code == "MOVIMENTO_NON_CANDIDATO" and exc.value.stato == 409
    assert exc.value.details["candidati"] == ["m1", "m2"]
    assert _run(db[COLL_F24].find_one({"id": "f1"}))["pagato"] is False


def test_un_certo_non_si_conferma_e_un_f24_sconosciuto_e_409():
    db = _db(movimenti=[_m("m1", "2026-01-16", -500.00)], modelli=[_modello("f1", "2026-01-16", 500.00)])
    with pytest.raises(reg.ConfermaNonAmmessa) as exc:
        _conferma(db, "f1", "m1")
    assert exc.value.code == "NESSUN_RISCONTRO_DA_CONFERMARE"


def test_il_motivo_e_a_chip_e_altro_vuole_il_testo():
    db = _db_probabile()
    with pytest.raises(reg.ConfermaNonAmmessa) as exc:
        _conferma(db, "f1", "m1", motivo="perche' si")
    assert exc.value.code == "MOTIVO_NON_AMMESSO" and exc.value.stato == 422
    with pytest.raises(reg.ConfermaNonAmmessa) as exc:
        _conferma(db, "f1", "m1", motivo="altro")
    assert exc.value.code == "MOTIVO_TESTO_OBBLIGATORIO"
    esito = _conferma(db, "f1", "m1", motivo="altro", motivo_testo="Visto l'estratto cartaceo")
    assert esito["motivo_testo"] == "Visto l'estratto cartaceo"


# ── modello PARZIALE: la differenza si registra, niente conguagli ─────────────

def test_il_parziale_confermato_registra_la_differenza_al_centesimo():
    db = _db(movimenti=[_m("m1", "2026-01-16", -503.00)], modelli=[_modello("f1", "2026-01-16", 500.00)])
    [r] = _run(reg.riconcilia_f24_banca(db))["modelli"]["da_verificare"]
    assert r["livello"] == reg.LIVELLO_PARZIALE
    esito = _conferma(db, "f1", "m1", motivo="differenza_commissioni")
    assert esito["differenza_cents"] == 300 and esito["differenza"] == 3.0
    f = _run(db[COLL_F24].find_one({"id": "f1"}))
    assert f["pagato"] is True and f["differenza_banca_cents"] == 300 and f["differenza_banca"] == 3.0
    assert f["conferma_titolare_banca"]["differenza_cents"] == 300
    # nessun movimento ne' scrittura in piu' per la differenza: resta il solo addebito
    assert len(_run(db[COLL_ESTRATTO_CONTO].find({}, {"_id": 0}).to_list(10))) == 1
    assert _run(db["partite_aperte"].find({}, {"_id": 0}).to_list(10)) == []


# ── quietanza PROBABILE: causale senza data d'incasso ─────────────────────────

def test_la_quietanza_probabile_confermata_prova_anche_il_suo_modello():
    db = _db(quietanze=[_q("q1", "2026-08-20", 654.33)],
             movimenti=[_m("m1", "2026-08-20", -654.33)],  # senza DATA INCASSO: probabile
             modelli=[_modello("f-q", "2026-08-20", 654.33, quietanza_id="q1")])
    esito_giro = _run(reg.riconcilia_f24_banca(db))
    [r] = esito_giro["da_verificare"]
    assert r["livello"] == reg.LIVELLO_PROBABILE and esito_giro["modelli"]["riscontrati"] == []

    esito = _conferma(db, "f-q", "m1", motivo="causale_senza_data_incasso")
    assert esito["natura"] == "quietanza"
    q = _run(db[COLL_QUIETANZE_F24].find_one({"id": "q1"}))
    assert q["riscontro_banca"]["stato"] == reg.RISCONTRO_CERTO and q["riscontro_banca"]["livello"] == reg.LIVELLO_PROBABILE
    assert q["riscontro_banca"]["conferma_titolare"]["motivo"] == "causale_senza_data_incasso"
    assert q["movimento_bancario_id"] == "m1"
    f = _run(db[COLL_F24].find_one({"id": "f-q"}))
    assert f["pagato"] is True and f["movimento_bancario_id"] == "m1"
    rel = _relazioni(db, "q1")
    assert ("m1", "confirmed", "titolare") in rel
    # anche con l'id della quietanza nella rotta: e' la stessa scheda
    assert _conferma(db, "q1", "m1", motivo="causale_senza_data_incasso")["gia_confermato"] is True


def test_la_quietanza_parziale_confermata_prova_il_modello_con_lo_stesso_saldo(monkeypatch):
    db = _db(quietanze=[_q("q1", "2026-08-20", 654.33)],
             movimenti=[_m("m1", "2026-08-20", -656.00, "20/08/2026")],
             modelli=[_modello("f-q", "2026-08-20", 654.33, quietanza_id="q1")])
    [r] = _run(reg.riconcilia_f24_banca(db))["da_verificare"]
    assert r["livello"] == reg.LIVELLO_PARZIALE
    esito = _conferma(db, "q1", "m1", motivo="differenza_commissioni")
    assert esito["differenza_cents"] == 167
    q = _run(db[COLL_QUIETANZE_F24].find_one({"id": "q1"}))
    assert q["riscontro_banca"]["differenza_cents"] == 167
    f = _run(db[COLL_F24].find_one({"id": "f-q"}))
    assert f["pagato"] is True and f["differenza_banca_cents"] == 167


# ── la rotta: solo admin, errori con code e correlation_id ────────────────────

def _client(db, monkeypatch, admin=True):
    from app.database import Database
    from app.routers.bank import riconciliazione_f24_banca as rotta
    from app.utils.dependencies import get_current_admin_user

    app = FastAPI()
    app.include_router(rotta.router, prefix="/api/f24-riconciliazione")
    if admin:
        app.dependency_overrides[get_current_admin_user] = lambda: {"email": "titolare@test", "role": "admin"}
    else:
        def _nega():
            raise HTTPException(status_code=403, detail="Solo admin")
        app.dependency_overrides[get_current_admin_user] = _nega
    # Con monkeypatch il Database torna quello vero a fine test: una sostituzione
    # permanente lasciava l'archivio finto ai test successivi (MFA, Lotti).
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    return TestClient(app)


def test_la_rotta_rifiuta_il_non_admin_e_spiega_il_409(monkeypatch):
    db = _db_probabile()
    assert _client(db, monkeypatch, admin=False).post("/api/f24-riconciliazione/quietanze-banca/f1/conferma",
                                         json={"movimento_id": "m1", "motivo": "unico_addebito_compatibile"}).status_code == 403
    client = _client(db, monkeypatch)
    risposta = client.post("/api/f24-riconciliazione/quietanze-banca/f1/conferma",
                           json={"movimento_id": "altro", "motivo": "unico_addebito_compatibile"})
    assert risposta.status_code == 409
    corpo = risposta.json()
    assert corpo["code"] == "MOVIMENTO_NON_CANDIDATO" and corpo["correlation_id"] and corpo["details"]["candidati"] == ["m1", "m2"]
    assert client.post("/api/f24-riconciliazione/quietanze-banca/f1/conferma",
                       json={"movimento_id": "m1", "motivo": "boh"}).status_code == 422
    ok = client.post("/api/f24-riconciliazione/quietanze-banca/f1/conferma",
                     json={"movimento_id": "m1", "motivo": "unico_addebito_compatibile"})
    assert ok.status_code == 200 and ok.json()["livello"] == "PROBABILE"
    assert _run(db[COLL_F24].find_one({"id": "f1"}))["conferma_titolare_banca"]["utente"] == "titolare@test"


def test_la_lettura_porta_i_motivi_della_tendina(monkeypatch):
    corpo = _client(_db_probabile(), monkeypatch).get("/api/f24-riconciliazione/quietanze-banca").json()
    assert corpo["conferma"]["livelli"] == ["PROBABILE", "PARZIALE"]
    assert corpo["conferma"]["motivi"]["altro"].startswith("Altro")
    [r] = corpo["modelli_da_verificare"]
    assert r["livello"] == "PROBABILE"
