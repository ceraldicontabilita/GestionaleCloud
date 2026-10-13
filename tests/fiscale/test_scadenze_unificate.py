"""Regressioni del rapporto Scadenze: prove, residui, anno e azioni valide."""

import asyncio
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mongomock_motor import AsyncMongoMockClient

from app.routers import scadenze
from app.services.scadenze_unificate import carica_scadenze, seleziona
from tests.fiscale.test_piano_tributi import _f24, _quietanza

OGGI = date(2026, 10, 13)


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def db():
    return AsyncMongoMockClient()["scadenze"]


@pytest.fixture
def client(db, monkeypatch):
    monkeypatch.setattr(scadenze.Database, "get_db", lambda: db)
    monkeypatch.setattr(scadenze, "oggi_roma", lambda: OGGI)
    app = FastAPI()
    app.include_router(scadenze.router, prefix="/api/scadenze")
    return TestClient(app)


def vista(db, anno=2026, **filters):
    p = run(carica_scadenze(db, anno, OGGI))
    return seleziona(p, anno=anno, oggi=OGGI, **filters)


def test_quietanza_senza_modello_e_copia_non_raddoppia_pagato(db):
    q = _quietanza("q-1")
    run(db.quietanze_f24.insert_many([q, {**q, "id": "copia"}]))
    prima = next(
        r
        for r in vista(db, include_chiuse=True)[0]
        if r["id"] == "piano:ritenute_1001:2026:03"
    )
    assert (
        prima["pagata"]
        and prima["residuo_cents"] == 0
        and prima["pagato_cents"] == 10000
    )
    assert prima["documenti"] and not prima["f24_ids"]
    assert not any(r["id"] == prima["id"] for r in vista(db)[0])
    run(
        db.f24_unificato.insert_one(
            _f24("f-1", "2026-04-16", erario=[("1001", 3, 2026, 10000, 0)])
        )
    )
    dopo = next(r for r in vista(db, include_chiuse=True)[0] if r["id"] == prima["id"])
    assert dopo["pagato_cents"] == 10000 and dopo["residuo_cents"] == 0


def test_pagamento_parziale_periodo_e_date_legali(db):
    run(
        db.f24_unificato.insert_one(
            _f24("f-1", "2026-05-16", erario=[("1001", 4, 2026, 10000, 0)])
        )
    )
    run(db.quietanze_f24.insert_one(_quietanza("q-1", importo=4000, mese=4)))
    rows, _ = vista(db)
    r = next(r for r in rows if r["id"] == "piano:ritenute_1001:2026:04")
    assert (
        r["data"] == "2026-05-18"
        and r["residuo_cents"] == 6000
        and r["pagato_cents"] == 4000
    )
    assert r["urgente"] and not r["pagata"]
    luglio = next(r for r in rows if r["id"] == "piano:ritenute_1001:2026:07")
    assert luglio["data"] == "2026-08-20"


def test_competenza_dicembre_compare_in_anno_scadenza(db):
    run(
        db.quietanze_f24.insert_one(
            _quietanza("q-dic", mese=12, anno=2025, data="2026-01-16")
        )
    )
    rows, _ = vista(db, include_chiuse=True)
    r = next(r for r in rows if r["id"] == "piano:ritenute_1001:2025:12")
    assert r["periodo"] == "12/2025" and r["data"] == "2026-01-16" and r["pagata"]
    assert not any(r["id"] == "piano:ritenute_1001:2026:12" for r in rows)


def test_custom_include_unilav_arretrati_note_documento_e_chiuse_escluse_totali(db):
    run(
        db.notifiche_scadenze.insert_many(
            [
                {
                    "id": "a",
                    "tipo": "UNILAV_CESSAZIONE",
                    "data_scadenza": "2026-07-01",
                    "importo": 123.45,
                    "note": "Verificare trasmissione",
                    "documento_id": "d1",
                    "dipendente_id": "e1",
                },
                {
                    "id": "c",
                    "tipo": "CUSTOM",
                    "data_scadenza": "2026-10-13",
                    "importo": 999,
                    "completata": True,
                },
                {
                    "id": "old",
                    "tipo": "CUSTOM",
                    "data_scadenza": "2025-10-13",
                    "importo": 500,
                },
            ]
        )
    )
    rows, stats = vista(db, tipo="CUSTOM", include_chiuse=True)
    assert (
        len(rows) == 2
        and stats["totale_importo_cents"] == 12345
        and stats["urgenti"] == 1
    )
    r = next(r for r in rows if r["id"] == "a")
    assert r["note"] == "Verificare trasmissione" and r["documenti"][0]["url"].endswith(
        "/d1"
    )
    assert r["dettaglio_url"].endswith("?dip=e1")
    assert next(r for r in rows if r["id"] == "c")["urgente"] is False
    assert [r["id"] for r in vista(db, tipo="CUSTOM")[0]] == ["a"]


def test_rate_inps_incerte_non_diventano_residuo_certo(db):
    run(
        db.dilazioni_inps.insert_one(
            {
                "id": "p",
                "rif": "test",
                "quadra": False,
                "avvertenze": ["Rata mancante"],
                "rate": [
                    {
                        "numero": 1,
                        "scadenza": "2026-01-01",
                        "importo_cents": 131200,
                        "stato": "VERSATA_IMPORTO_DIVERSO",
                        "versamento_diverso": {
                            "importo_cents": 53316,
                            "quietanza_ids": [],
                        },
                    }
                ],
            }
        )
    )
    rows, _ = vista(db)
    r = next(r for r in rows if r["source"] == "rata_inps")
    assert r["residuo_cents"] is None and not r["conteggiabile"] and r["da_verificare"]


def test_pannelli_sono_indipendenti_dai_verbali(db):
    run(
        db.ricevute_pagopa.insert_many(
            [{"id": "r1", "stato": "non_associata"}, {"id": "r2", "stato": "associata"}]
        )
    )
    run(
        db.cartelle_pagamento.insert_one(
            {"id": "c", "expectation_status": "DA_VERIFICARE"}
        )
    )
    panels = run(carica_scadenze(db, 2026, OGGI))["documenti_da_verificare"]
    assert {p["id"]: p["conteggio"] for p in panels} == {
        "ricevute": 1,
        "cartelle": 1,
        "piani": 0,
    }
    assert panels[0]["url"] == "/riconciliazione/pagopa"


@pytest.mark.parametrize(
    "patch",
    [
        {"data_scadenza": "2026-13-99"},
        {"data_scadenza": "13/10/2026"},
        {"data_scadenza": "1800-01-01"},
        {"importo": -100},
        {"importo": "NaN"},
        {"importo": "Infinity"},
        {"importo": "1.123"},
        {"tipo": "inventato"},
        {"descrizione": "   "},
    ],
)
def test_validazione_ingresso(client, db, patch):
    r = client.post(
        "/api/scadenze/crea",
        json={"data_scadenza": "2026-10-13", "descrizione": "Promemoria", **patch},
    )
    assert r.status_code == 422
    assert run(db.notifiche_scadenze.count_documents({})) == 0


def test_importo_sconosciuto_non_zero_e_completamento_idempotente(client, db):
    r = client.post(
        "/api/scadenze/crea",
        json={"data_scadenza": "2026-10-13", "descrizione": "Promemoria"},
    )
    assert r.status_code == 200 and r.json()["notifica"]["importo_cents"] is None
    id_ = r.json()["notifica"]["id"]
    for _ in range(2):
        assert client.put("/api/scadenze/completa/" + id_).status_code == 200
    assert (
        client.get(
            "/api/scadenze/tutte", params={"anno": 2026, "tipo": "CUSTOM"}
        ).json()["totale"]
        == 0
    )


@pytest.mark.parametrize(
    "params",
    [
        {"mese": 13},
        {"mese": 0},
        {"anno": 100},
        {"offset": -1},
        {"limit": 0},
        {"stato": "ignoto"},
    ],
)
def test_filtri_non_validi(client, params):
    assert client.get("/api/scadenze/tutte", params=params).status_code == 422


def test_prossime_ordina_prima_del_limite(client, db):
    run(
        db.notifiche_scadenze.insert_many(
            [
                {"id": f"n-{i}", "data_scadenza": "2026-10-20", "descrizione": "Dopo"}
                for i in range(60)
            ]
            + [{"id": "prima", "data_scadenza": "2026-10-14", "descrizione": "Prima"}]
        )
    )
    r = client.get("/api/scadenze/prossime", params={"giorni": 8, "limit": 1})
    assert r.status_code == 200 and r.json()["scadenze"][0]["id"] == "prima"
    assert r.json()["totale"] >= 61


def test_iva_confermata_non_ricalcola_xml_e_non_richiede_f24(db, monkeypatch):
    from app.services import piano_iva

    async def no_calculation(*a, **kw):
        raise AssertionError("Scadenze non deve ricalcolare gli XML")

    monkeypatch.setattr(piano_iva, "get_iva_period_snapshot", no_calculation)
    run(
        db.liquidazioni_iva.insert_one(
            {
                "id": "liq",
                "periodo": "2026-04",
                "stato": "CONFERMATA",
                "saldo": 250,
                "versione": 1,
            }
        )
    )
    r = next(r for r in vista(db)[0] if r["id"] == "piano:iva_mensile:2026:04")
    assert r["importo_cents"] == 25000 and r["residuo_cents"] == 25000


def test_iva_api_non_riaccumula_i_versamenti_dei_mesi(client, db):
    run(
        db.liquidazioni_iva.insert_many(
            [
                {
                    "id": f"liq-{m}",
                    "periodo": f"2026-{m:02d}",
                    "stato": "CONFERMATA",
                    "versione": 1,
                    "saldo": amount,
                    "iva_vendite": amount,
                    "iva_acquisti": 0,
                    "credito_precedente": 0,
                }
                for m, amount in [(1, 100), (2, 100), (3, 0)]
            ]
        )
    )
    result = client.get("/api/scadenze/iva-mensile/2026")
    assert result.status_code == 200
    rows = result.json()["scadenze"]
    assert [r["importo_versamento_effettivo_cents"] for r in rows[:3]] == [
        10000,
        10000,
        0,
    ]
    assert rows[3]["importo_versamento_effettivo"] is None


def test_riferimento_fattura_non_esistente_non_espone_azione_di_pagamento(db):
    run(
        db.notifiche_scadenze.insert_one(
            {
                "id": "n",
                "tipo": "FATTURA",
                "fattura_id": "assente",
                "data_scadenza": "2026-10-13",
            }
        )
    )
    row = next(r for r in vista(db)[0] if r["id"] == "n")
    assert row["fattura_id"] is None and row["importo_cents"] is None


def test_errore_lettura_quietanze_non_diventa_zero(client, db, monkeypatch):
    def fail(*a, **kw):
        raise ConnectionError("Archivio non disponibile")

    class BrokenCollection:
        find = staticmethod(fail)

    class BrokenDB:
        def __getitem__(self, key):
            return BrokenCollection() if key == "quietanze_f24" else db[key]

    monkeypatch.setattr(scadenze.Database, "get_db", lambda: BrokenDB())
    response = client.get("/api/scadenze/tutte", params={"anno": 2026})
    assert response.status_code == 503 and "statistiche" not in response.json()


@pytest.mark.parametrize(
    "saldo,paid,chiusa,restante",
    [(200, 25000, True, 0), (300, 25000, False, 5000), (0, 25000, True, 0)],
)
def test_iva_confermata_usa_dovuto_e_conserva_pagamento_originale(
    db, saldo, paid, chiusa, restante
):
    run(
        db.f24_unificato.insert_one(
            _f24("f", "2026-05-18", erario=[("6004", 4, 2026, 50000, 0)])
        )
    )
    q = _quietanza("q")
    q["sezione_erario"] = [
        {
            "codice_tributo": "6004",
            "anno": "2026",
            "mese": "04",
            "importo_debito_cents": paid,
            "importo_credito_cents": 0,
        }
    ]
    q["totali"] = {"saldo_netto": paid / 100}
    q["dati_generali"]["saldo_delega_cents"] = paid
    run(db.quietanze_f24.insert_one(q))
    run(
        db.liquidazioni_iva.insert_one(
            {
                "id": "l",
                "periodo": "2026-04",
                "stato": "CONFERMATA",
                "versione": 1,
                "saldo": saldo,
            }
        )
    )
    r = next(
        r
        for r in vista(db, include_chiuse=True)[0]
        if r["id"] == "piano:iva_mensile:2026:04"
    )
    assert (
        r["pagata"] == chiusa
        and r["residuo_cents"] == restante
        and r["pagato_cents"] == paid
    )
    if saldo == 0:
        assert r["da_verificare"]
