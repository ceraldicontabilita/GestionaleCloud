"""Piano tributi: il piano crea l'attesa, le prove la soddisfano soltanto."""
import asyncio
from datetime import date

from mongomock_motor import AsyncMongoMockClient

from app.services import piano_tributi as piano
from app.services.expectation_policy import ExpectationStatus


def run(coro):
    return asyncio.run(coro)


def _f24(id_, versamento, erario=(), inps=(), regioni=(), **kw):
    return {
        "id": id_, "status": "da_pagare",
        "dati_generali": {"data_versamento": versamento, "saldo_delega_cents": kw.pop("saldo", 10000)},
        "sezione_erario": [
            {"codice_tributo": c, "anno": str(a), "mese": f"{m:02d}", "importo_debito_cents": d,
             "importo_credito_cents": cr, "periodo_riferimento": f"{m:02d}/{a}"}
            for c, m, a, d, cr in erario
        ],
        "sezione_inps": [
            {"causale": c, "anno": str(a), "mese": f"{m:02d}", "importo_debito_cents": d,
             "importo_credito_cents": 0} for c, m, a, d in inps
        ],
        "sezione_regioni": [
            {"codice_tributo": c, "anno": str(a), "mese": f"{m:02d}", "importo_debito_cents": d,
             "importo_credito_cents": 0} for c, m, a, d in regioni
        ],
        **kw,
    }


def _db(*f24):
    db = AsyncMongoMockClient()["piano"]
    if f24:
        run(db["f24_unificato"].insert_many([dict(f) for f in f24]))
    return db


def _voce(g, voce_id):
    return next(r for r in g["voci"] if r["voce"]["id"] == voce_id)


def _mese(g, voce_id, mese):
    return next(c for c in _voce(g, voce_id)["caselle"] if c["periodo"] == f"{mese:02d}")


OGGI = date(2026, 9, 26)


def test_il_piano_crea_l_attesa_prima_della_prova():
    g = run(piano.griglia(_db(), 2026, oggi=OGGI))
    giugno = _mese(g, "ritenute_1001", 6)
    assert giugno["stato"] == piano.MANCA_F24 and giugno["importo"] is None   # mai un importo inventato
    assert giugno["expectation_status"] == ExpectationStatus.ATTESO.value
    assert giugno["source_fact_id"] == "piano:ritenute_1001:2026:06"
    assert giugno["scadenza"] == "2026-07-16"
    assert _mese(g, "ritenute_1001", 10)["stato"] == piano.FUTURO
    assert {"voce": "Ritenute lavoro dipendente", "codici": ["1001"], "periodo": "06/2026",
            "scadenza": "2026-07-16", "stato": piano.MANCA_F24} in g["mancano"]


def test_la_prova_bancaria_soddisfa_e_conserva_gli_id():
    f = _f24("f-mag", "2026-06-16", erario=[("1001", 5, 2026, 102651, 0)],
             movimento_bancario_id="mov-1", data_pagamento_effettivo="2026-06-17")
    g = run(piano.griglia(_db(f), 2026, oggi=OGGI))
    maggio = _mese(g, "ritenute_1001", 5)
    assert maggio["stato"] == piano.PAGATO
    assert maggio["expectation_status"] == ExpectationStatus.SODDISFATTO.value
    assert maggio["importo"] == "1026.51"
    assert maggio["modelli"][0]["f24_id"] == "f-mag"


def test_la_sola_quietanza_non_vale_come_banca():
    f = _f24("f-apr", "2026-05-18", erario=[("1001", 4, 2026, 94079, 0)], quietanza_id="q-1")
    g = run(piano.griglia(_db(f), 2026, oggi=OGGI))
    aprile = _mese(g, "ritenute_1001", 4)
    assert aprile["stato"] == piano.QUIETANZA_SENZA_BANCA
    assert aprile["expectation_status"] == ExpectationStatus.DA_VERIFICARE.value


def test_f24_arrivato_e_non_pagato_dopo_la_scadenza():
    f = _f24("f-lug", "2026-08-20", erario=[("1001", 7, 2026, 179456, 0)])
    g = run(piano.griglia(_db(f), 2026, oggi=OGGI))
    assert _mese(g, "ritenute_1001", 7)["stato"] == piano.SCADUTO_NON_PAGATO
    assert _mese(g, "ritenute_1001", 7)["scadenza"] == "2026-08-20"   # 16 agosto -> 20
    g = run(piano.griglia(_db(f), 2026, oggi=date(2026, 8, 1)))
    assert _mese(g, "ritenute_1001", 7)["stato"] == piano.DA_PAGARE


def test_modello_doppio_conta_una_volta_e_vince_la_prova():
    pagato = _f24("f-a", "2026-05-18", erario=[("1001", 4, 2026, 94079, 0)], movimento_bancario_id="m", data_pagamento_effettivo="2026-06-17")
    doppio = _f24("f-b", "2026-05-18", erario=[("1001", 4, 2026, 94079, 0)])
    g = run(piano.griglia(_db(pagato, doppio), 2026, oggi=OGGI))
    aprile = _mese(g, "ritenute_1001", 4)
    assert aprile["stato"] == piano.PAGATO
    assert aprile["importo"] == "940.79"          # non raddoppiato
    assert aprile["modelli_doppi"] == 1 and g["modelli_doppi"] == 1


def test_addizionale_regionale_legge_le_rate_dell_anno_prima():
    f = _f24("f-mag", "2026-06-16", regioni=[("3802", 5, 2025, 69044)], movimento_bancario_id="m", data_pagamento_effettivo="2026-06-17")
    g = run(piano.griglia(_db(f), 2026, oggi=OGGI))
    assert _mese(g, "add_regionale_3802", 5)["stato"] == piano.PAGATO
    assert [c["periodo"] for c in _voce(g, "add_regionale_3802")["caselle"]][-1] == "11"


def test_inps_dm10_e_credito_mai_in_rosso():
    f = _f24("f-mag", "2026-06-16", inps=[("DM10", 5, 2026, 523700)],
             erario=[("1704", 5, 2026, 0, 67028)], movimento_bancario_id="m", data_pagamento_effettivo="2026-06-17")
    g = run(piano.griglia(_db(f), 2026, oggi=OGGI))
    assert _mese(g, "inps_dm10", 5)["stato"] == piano.PAGATO
    assert _mese(g, "credito_1704", 5)["stato"] == piano.CREDITO_USATO
    assert _mese(g, "credito_1704", 5)["credito"] == "670.28"
    assert _mese(g, "credito_1704", 6)["stato"] == piano.CREDITO_ASSENTE
    assert not _mese(g, "credito_1704", 6)["mandatory"]


def test_ires_saldo_dell_anno_prima_e_acconti():
    f = _f24("f-ires", "2026-06-30", erario=[("2003", 0, 2025, 500000, 0), ("2001", 0, 2026, 200000, 0)],
             movimento_bancario_id="m", data_pagamento_effettivo="2026-06-17")
    g = run(piano.griglia(_db(f), 2026, oggi=OGGI))
    assert _voce(g, "ires_saldo")["caselle"][0]["stato"] == piano.PAGATO
    assert _voce(g, "ires_acconto_1")["caselle"][0]["stato"] == piano.PAGATO
    assert _voce(g, "ires_acconto_2")["caselle"][0]["stato"] == piano.FUTURO
    assert _voce(g, "ires_acconto_2")["caselle"][0]["scadenza"] == "2026-11-30"


def test_cosap_fuori_f24_e_codici_fuori_piano():
    f = _f24("f-x", "2026-06-16", erario=[("1631", 5, 2026, 0, 1000)])
    g = run(piano.griglia(_db(f), 2026, oggi=OGGI))
    assert _voce(g, "cosap")["caselle"] == []                  # scadenza da impostare
    assert [v["codice"] for v in g["fuori_piano"]] == ["1631"]


def test_l_anno_non_si_chiude_con_un_attesa_aperta():
    g = run(piano.griglia(_db(), 2026, oggi=OGGI))
    assert g["anno_chiuso"] is False


def test_il_piano_si_scrive_una_volta_sola_e_rispetta_le_modifiche():
    db = _db()
    run(piano.griglia(db, 2026, oggi=OGGI))
    run(piano.aggiorna_voce(db, "inps_cxx", {"attivo": False}))
    run(db[piano.COLL_PIANO].delete_one({"id": "imu_saldo"}))    # voce di base nuova nel codice
    g = run(piano.griglia(db, 2026, oggi=OGGI))
    assert run(db[piano.COLL_PIANO].count_documents({})) == len(piano.PIANO_BASE)
    assert "inps_cxx" not in [r["voce"]["id"] for r in g["voci"]]      # spenta resta spenta
    assert "imu_saldo" in [r["voce"]["id"] for r in g["voci"]]


def test_modifica_voce_e_scadenza_cosap():
    db = _db()
    voce = run(piano.aggiorna_voce(db, "cosap", {"scadenze": [[3, 31]], "codici": ["X"]}))
    assert voce["scadenze"] == [[3, 31]] and "X" not in (voce.get("codici") or [])
    g = run(piano.griglia(db, 2026, oggi=OGGI))
    cosap = _voce(g, "cosap")["caselle"][0]
    assert cosap["stato"] == piano.DA_VERIFICARE_A_MANO and cosap["scadenza"] == "2026-03-31"


def test_scadenze_festivi_e_weekend():
    assert piano.scadenza_effettiva(date(2026, 8, 16)) == date(2026, 8, 20)
    assert piano.scadenza_effettiva(date(2026, 5, 16)) == date(2026, 5, 18)   # sabato
    assert piano.scadenza_effettiva(date(2026, 11, 1)) == date(2026, 11, 2)   # Ognissanti
    assert piano._scadenza_mensile(2026, 12) == date(2027, 1, 18)             # 16/01/2027 e' sabato


def test_rotte_solo_admin_e_prima_della_rotta_dinamica():
    from app.routers.f24.f24_main import router
    from app.utils.dependencies import get_current_admin_user

    percorsi = [r.path for r in router.routes]
    dinamica_get = next(i for i, r in enumerate(router.routes)
                        if r.path == "/{f24_id}" and "GET" in r.methods)
    for p in ("/piano-tributi", "/piano-tributi/voci", "/piano-tributi/voci/{voce_id}"):
        assert percorsi.index(p) < dinamica_get
        for rotta in (r for r in router.routes if r.path == p):
            assert get_current_admin_user in [d.call for d in rotta.dependant.dependencies]
