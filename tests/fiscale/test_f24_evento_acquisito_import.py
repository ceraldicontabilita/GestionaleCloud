"""`f24.acquisito` parte da `salva_f24`, cioe' da ogni ingresso dei modelli, una
volta sola per modello; mai da una quietanza. Il pregresso si recupera con
`ripubblica_f24_acquisito` sugli stessi handler, saltando i modelli gia'
provati in banca e quelli con la partita.
"""
import asyncio

from app.services import f24_evento_acquisito as ev
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.f24_canonico import salva_f24


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _db():
    return ClientArchivioMemoria()["f24_evento"]


def _modello(saldo=500.0, **extra):
    return {"file_name": "F24.pdf", "status": "da_pagare", "pagato": False,
            "dati_generali": {"codice_fiscale": "01879020517", "data_versamento": "2026-01-16"},
            "totali": {"saldo_netto": saldo},
            "sezione_erario": [{"codice_tributo": "1001", "periodo_riferimento": "12/2025",
                                "importo_debito": saldo}],
            "pdf_hash": "a" * 64, **extra}


def _eventi(monkeypatch):
    eventi = []

    async def fake(event_type, payload, db, source_module=None, **_k):
        eventi.append((event_type, payload, source_module))
        return []

    monkeypatch.setattr("app.services.event_bus.propagate_event", fake)
    return eventi


def test_salva_f24_pubblica_una_volta_con_il_payload_degli_handler(monkeypatch):
    eventi = _eventi(monkeypatch)
    db = _db()
    f24_id = _run(salva_f24(db, _modello(), source="drive_cartella_unica"))
    assert len(eventi) == 1
    tipo, payload, fonte = eventi[0]
    assert tipo == "f24.acquisito" and fonte == "drive_cartella_unica"
    assert payload["f24_id"] == f24_id
    assert payload["importo_totale"] == 500.0
    assert payload["codice_tributo"] == "1001" and payload["periodo"] == "12/2025"
    assert payload["data_scadenza"] == "2026-01-16"  # ritenute di dicembre: 16 del mese dopo
    # la stessa copia di nuovo: nessun secondo fatto
    assert _run(salva_f24(db, _modello(), source="drive_cartella_unica")) == f24_id
    assert len(eventi) == 1


def test_una_quietanza_non_pubblica_il_fatto(monkeypatch):
    eventi = _eventi(monkeypatch)
    doc = _modello()
    doc["dati_generali"]["natura_documento"] = "QUIETANZA_STAMPA_CASSETTO"
    _run(salva_f24(_db(), doc, source="test"))
    assert eventi == []
    assert ev.e_quietanza(doc) is True


def test_la_creazione_a_mano_usa_lo_stesso_payload(monkeypatch):
    eventi = _eventi(monkeypatch)
    doc = {"id": "manuale", "importo": 1234.56, "scadenza": "2026-08-16", "periodo_riferimento": "07/2026",
           "codici_tributo": ["6001", "1001"], "created_at": "2026-08-01T00:00:00+00:00"}
    _run(salva_f24(_db(), doc, source="f24_manual_create"))
    [(_, payload, _)] = eventi
    assert payload == {"f24_id": "manuale", "importo_totale": 1234.56, "data_scadenza": "2026-08-16",
                       "periodo": "07/2026", "codice_tributo": "6001, 1001",
                       "data_acquisizione": "2026-08-01T00:00:00+00:00"}


def test_il_pregresso_si_ripubblica_solo_dove_manca_la_partita(monkeypatch):
    eventi = _eventi(monkeypatch)
    db = _db()
    for id_, extra in (
        ("senza-partita", {}),
        ("con-partita", {}),
        ("pagato-banca", {"pagato": True, "pagamento_verificato_banca": True, "movimento_bancario_id": "m1", "data_pagamento_effettivo": "2026-01-16",
                          "status": "pagato"}),
        ("quarantena", {"status": "quarantena"}),
    ):
        _run(db[ev.COLL_F24].insert_one({**_modello(**extra), "id": id_, "pdf_hash": id_ * 8}))
    _run(db[ev.COLL_PARTITE].insert_one({"documento_id": "con-partita", "documento_collection": ev.COLL_F24,
                                         "tipo": "f24", "stato": "aperta"}))

    anteprima = _run(ev.ripubblica_f24_acquisito(db, dry_run=True))
    assert anteprima["candidati"] == 1 and anteprima["ids"] == ["senza-partita"] and eventi == []

    esito = _run(ev.ripubblica_f24_acquisito(db, dry_run=False))
    assert esito["ripubblicati"] == 1 and esito["errori"] == 0
    assert [e[1]["f24_id"] for e in eventi] == ["senza-partita"] and eventi[0][2] == "replay_pregresso"
    marcato = _run(db[ev.COLL_F24].find_one({"id": "senza-partita"}, {"_id": 0}))
    assert marcato[ev.MARCATORE_RIPUBBLICAZIONE]
    # secondo giro: zero
    assert _run(ev.ripubblica_f24_acquisito(db, dry_run=False))["candidati"] == 0


def test_l_handler_crea_la_partita_sul_payload_unico():
    """Lo stesso handler del bus, idempotente per documento e tipo."""
    from app.services.handlers.f24_handlers import on_f24_acquisito_crea_partita

    db = _db()
    doc = {**_modello(), "id": "f-1"}
    payload = ev.costruisci_evento_f24_acquisito(doc)
    primo = _run(on_f24_acquisito_crea_partita(payload, db))
    secondo = _run(on_f24_acquisito_crea_partita(payload, db))
    assert primo["partita_id"] and secondo["partita_id"] is None
    partite = _run(db[ev.COLL_PARTITE].find({}, {"_id": 0}).to_list(10))
    assert len(partite) == 1 and partite[0]["documento_id"] == "f-1" and partite[0]["tipo"] == "f24"
