"""Replay automatico di `fattura.created` per le fatture senza partita.

Il job bancario corto rigioca l'evento sugli stessi handler, a lotti: la
fattura aperta riceve la sua partita, quella gia' pagata (in uno qualunque
dei cinque campi) no, e nessuna delle due torna al giro dopo.
"""
import asyncio

from app.services import recupero_fatture_pregresso as recupero
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.eventi_fattura import costruisci_evento_fattura_created


def _fattura(fid, **extra):
    base = {"id": fid, "invoice_number": fid, "invoice_date": "2026-04-10",
            "supplier_id": "FORN-1", "supplier_name": "Fornitore Srl",
            "total_amount": 122.0, "imponibile": 100.0, "iva": 22.0, "tipo_documento": "TD01"}
    base.update(extra)
    return base


def test_la_pagata_in_un_campo_qualunque_non_riceve_la_partita():
    assert costruisci_evento_fattura_created(_fattura("f", paid=True))["pagato"] is True
    assert costruisci_evento_fattura_created(_fattura("f"))["pagato"] is False


def test_replay_a_lotti_apre_la_partita_una_volta_e_non_ripassa(monkeypatch):
    from app.services import event_bus
    from app.services.handlers.fattura_handlers import on_fattura_created_crea_partita

    async def solo_partita(tipo, evento, db, **_kw):
        return await on_fattura_created_crea_partita(evento, db)

    monkeypatch.setattr(event_bus, "propagate_event", solo_partita)

    async def scenario():
        db = ClientArchivioMemoria()["gc"]
        await db["invoices"].insert_many([
            _fattura("f-aperta"),
            _fattura("f-pagata", pagato=True),
            _fattura("f-cancellata", entity_status="deleted"),
        ])
        primo = await recupero.ripubblica_a_lotti(db)
        secondo = await recupero.ripubblica_a_lotti(db)
        partite = await db["partite_aperte"].find({}, {"_id": 0, "documento_id": 1}).to_list(None)
        return primo, secondo, partite

    primo, secondo, partite = asyncio.run(scenario())
    assert primo == {"candidate": 2, "ripubblicate": 2, "errori": 0}
    assert secondo == {"candidate": 0, "ripubblicate": 0, "errori": 0}
    assert [p["documento_id"] for p in partite] == ["f-aperta"]
