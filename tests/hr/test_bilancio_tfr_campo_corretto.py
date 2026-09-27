"""Bug trovato nell'audit funzionale del 15/07/2026: il Conto Economico
dettagliato (B9c_tfr) sommava il campo "tfr" sui documenti di `cedolini`,
ma quel campo non esiste mai — il campo reale scritto da
salari_unificati_v2.py è "tfr_mese" (stesso nome già usato correttamente in
piano_conti.py). La somma dava quindi sempre 0, e il codice cadeva
sistematicamente sulla stima forfettaria (lordo*6.91%) invece di usare il
TFR realmente accantonato dai cedolini.

27/09/2026: le stime forfettarie non ci sono piu'. Gli oneri sociali a carico
azienda non esistono sulle buste e restano None, mai il 30% del lordo."""
import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria

from app.routers.accounting import bilancio as mod


def _run(c):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(c)
    finally:
        loop.close()


def _db(monkeypatch, buste):
    db = ClientArchivioMemoria()["bilancio_tfr_test"]
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    _run(db["cedolini"].insert_many(buste))
    return db


def test_b9c_tfr_usa_il_campo_reale_non_la_stima(monkeypatch):
    _db(monkeypatch, [
        {"id": "b1", "anno": 2026, "lordo": 2000.0, "netto": 1500.0, "tfr_mese": 137.0,
         "inps_dipendente": 0, "inps_azienda": 500.0, "inail": 20.0,
         "costo_azienda": 0, "irpef": 0},
    ])

    esito = _run(mod.get_conto_economico_dettagliato(anno=2026, mese=None))

    costo_personale = esito["B_COSTI_PRODUZIONE"]["B9_costo_personale"]
    assert costo_personale["B9c_tfr"] == 137.0
    assert costo_personale["B9a_salari_stipendi"] == 2000.0
    assert costo_personale["totale"] == 2137.0


def test_b9_non_stima_oneri_ne_tfr_quando_mancano(monkeypatch):
    _db(monkeypatch, [{"id": "b1", "anno": 2026, "lordo": 2000.0, "tfr_mese": 0}])

    esito = _run(mod.get_conto_economico_dettagliato(anno=2026, mese=None))

    costo_personale = esito["B_COSTI_PRODUZIONE"]["B9_costo_personale"]
    assert costo_personale["B9b_oneri_sociali"] is None  # mai lordo * 30%
    assert costo_personale["B9c_tfr"] is None  # mai lordo * 6,91%
    assert costo_personale["totale"] == 2000.0
    assert costo_personale["incompleto"] is True


def test_b9_senza_buste_non_dichiara_un_risultato(monkeypatch):
    _db(monkeypatch, [])

    esito = _run(mod.get_conto_economico_dettagliato(anno=2026, mese=None))

    assert esito["B_COSTI_PRODUZIONE"]["B9_costo_personale"]["totale"] is None
    assert esito["B_COSTI_PRODUZIONE"]["totale_costi_produzione"] is None
    assert esito["RISULTATO"]["risultato_ante_imposte"] is None
    assert esito["RISULTATO"]["tipo"] == "non_determinabile"
