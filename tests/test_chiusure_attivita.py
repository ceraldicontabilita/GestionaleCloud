"""Giorni di chiusura dell'attivita' (titolare 14/09/2026): non sono
corrispettivi mancanti. Registro unico + esclusione dai giorni senza RT."""
import asyncio

from mongomock_motor import AsyncMongoMockClient

from app.services import chiusure_attivita as mod


def _run(coro):
    return asyncio.run(coro)


def test_registra_e_idempotente_e_giorni_chiusi():
    db = AsyncMongoMockClient()["gc"]
    primo = _run(mod.registra_chiusura(db, "2026-03-01", "2026-03-08", "ristrutturazione", "titolare"))
    secondo = _run(mod.registra_chiusura(db, "01/03/2026", "08/03/2026", "ristrutturazione", "manuale"))
    assert primo["gia_presente"] is False and primo["giorni"] == 8
    assert secondo["gia_presente"] is True and secondo["id"] == primo["id"]
    assert _run(db.chiusure_attivita.count_documents({})) == 1
    chiusi = _run(mod.giorni_chiusi(db, "2026-03-01", "2026-03-31"))
    assert chiusi == {f"2026-03-0{i}" for i in range(1, 9)}
    assert _run(mod.giorni_chiusi(db, "2026-04-01", "2026-04-30")) == set()


def test_semina_periodi_confermati_una_volta_sola():
    db = AsyncMongoMockClient()["gc"]
    assert _run(mod.semina_periodi_confermati(db)) == 3
    assert _run(mod.semina_periodi_confermati(db)) == 0
    elenco = _run(mod.elenca_chiusure(db, anno=2026))
    assert [(c["data_inizio"], c["data_fine"], c["motivo"]) for c in elenco] == [
        ("2026-01-26", "2026-01-31", "ristrutturazione"),
        ("2026-03-01", "2026-03-08", "ristrutturazione"),
        ("2026-08-15", "2026-08-23", "ferie"),
    ]


def test_ferie_collettive_hr_senza_corrispettivo_diventano_chiusura(monkeypatch):
    from app.hr.database import Database as DatabaseHR

    db = AsyncMongoMockClient()["gc"]
    hr = AsyncMongoMockClient()["hr"]
    monkeypatch.setattr(DatabaseHR, "get_db", classmethod(lambda cls: hr))
    dips = [{"id": f"d{i}", "attivo": True} for i in range(10)]
    _run(hr.dipendenti.insert_many(dips + [{"id": "vecchio", "attivo": False}]))
    presenze = []
    for giorno in ("2026-08-15", "2026-08-16", "2026-08-17"):
        for d in dips[:9]:  # 9 su 10 = 90% in ferie
            presenze.append({"data": giorno, "dipendente_id": d["id"], "stato": "giustificato", "giustificativo": "F"})
    # un giorno con solo 3 in ferie: normale
    presenze += [{"data": "2026-08-20", "dipendente_id": d["id"], "giustificativo": "F"} for d in dips[:3]]
    # un giorno di ferie collettive ma con corrispettivo: negozio aperto (non chiusura)
    presenze += [{"data": "2026-08-18", "dipendente_id": d["id"], "giustificativo": "F"} for d in dips[:9]]
    _run(hr.presenze_cloud.insert_many(presenze))
    _run(db.corrispettivi.insert_one({"data": "2026-08-18", "totale": 500}))

    esito = _run(mod.rileva_chiusure_da_presenze_hr(db, da="2026-08-01", a="2026-08-31"))

    assert esito["nuovi"] == 1 and esito["giorni_chiusura"] == 3
    chiusure = _run(mod.elenca_chiusure(db))
    assert [(c["data_inizio"], c["data_fine"], c["fonte"]) for c in chiusure] == [("2026-08-15", "2026-08-17", "presenze_hr")]
    # secondo giro: niente di nuovo
    assert _run(mod.rileva_chiusure_da_presenze_hr(db, da="2026-08-01", a="2026-08-31"))["nuovi"] == 0


def test_giorni_senza_corrispettivo_esclude_le_chiusure():
    from app.services.iva_liquidation_query import corrispettivi_periodo

    db = AsyncMongoMockClient()["gc"]
    _run(mod.registra_chiusura(db, "2026-03-01", "2026-03-08", "ristrutturazione", "titolare"))
    for g in range(9, 32):
        _run(db.corrispettivi.insert_one({"data": f"2026-03-{g:02d}", "totale": 1000, "totale_iva": 90.91}))
    snap = _run(corrispettivi_periodo(db, "2026-03"))
    assert snap["giorni_senza_corrispettivo"] == []
    assert snap["giorni_chiusura"] == [f"2026-03-0{i}" for i in range(1, 9)]
    assert snap["giorni_con_corrispettivo"] == 23


def test_csv_ade_con_periodo_inattivita_registra_la_chiusura():
    """Il RT, alla riapertura, dichiara il periodo di inattivita' nelle
    colonne 8-9 del tracciato AdE: entra nel registro chiusure."""
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from app.routers.invoices import corrispettivi as router_mod
    from app.database import Database

    db = AsyncMongoMockClient()["gc"]
    app = FastAPI()
    app.include_router(router_mod.router, prefix="/api/corrispettivi")
    Database.db = db
    try:
        csv = (
            "Id invio;Matricola dispositivo;Data e ora rilevazione;Data e ora trasmissione;Ammontare delle vendite (totale in euro);"
            "Imponibile vendite (totale in euro);Imposta vendite (totale in euro);Periodo di inattivita' da;Periodo di inattivita' a\n"
            "'1';'99MEY000000';09/03/2026 21:00:00;09/03/2026 21:01:00;\"000000002580,98\";\"000000002346,35\";\"000000000234,63\";01/03/2026;08/03/2026\n"
        )
        with TestClient(app) as client:
            r = client.post("/api/corrispettivi/import-csv", files={"file": ("ade.csv", csv.encode(), "text/csv")})
        assert r.status_code == 200, r.text
        assert r.json()["importati"] == 1
        chiusure = _run(mod.elenca_chiusure(db))
        assert [(c["data_inizio"], c["data_fine"], c["fonte"], c["riferimento"]) for c in chiusure] == [
            ("2026-03-01", "2026-03-08", "ade_inattivita", "1")]
    finally:
        Database.db = None
