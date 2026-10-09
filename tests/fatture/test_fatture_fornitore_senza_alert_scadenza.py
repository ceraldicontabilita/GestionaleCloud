"""Le fatture fornitore non hanno scadenza: nessun FAT_DA_PAGARE_SCADUTA.

Il 27/09/2026 c'erano 548 FAT_DA_PAGARE_SCADUTA aperti, tutti «critical»,
generati da `check_scadenze_partite_task` su partite con un «+30» inventato.
Le partite fornitore (fattura e nota di credito) escono da tutti e tre i
giri, anche da quello della «partita vecchia»; F24 e stipendi restano.
"""
import asyncio

from app import scheduler
from app.database import Database
from app.services.archivio_documenti_memoria import ArchivioDocumenti


def _partita(pid, tipo, **extra):
    return {"id": pid, "tipo": tipo, "stato": "aperta", "documento_id": f"doc-{pid}",
            "documento_collection": "invoices", "residuo": 100.0, **extra}


def test_nessun_alert_scadenza_da_partite_fornitore(monkeypatch):
    db = ArchivioDocumenti()

    async def scenario():
        await db["partite_aperte"].insert_many([
            _partita("P1", "fattura_fornitore", data_scadenza="2026-01-31"),
            _partita("P2", "nota_credito", data_scadenza="2026-01-31"),
            _partita("P3", "fattura_fornitore", data_scadenza=None,
                     created_at="2025-01-01T00:00:00"),
            _partita("P4", "f24", data_scadenza="2026-01-16",
                     documento_collection="f24_unificato"),
        ])
        await scheduler.check_scadenze_partite_task()
        return await db["alerts"].find({}, {"_id": 0}).to_list(None)

    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    alert = asyncio.run(scenario())

    codici = sorted((a["codice"], a["entita_id"]) for a in alert)
    assert codici == [("F24_SCADUTO", "doc-P4")]
    assert "fattura_fornitore" in scheduler.TIPI_PARTITA_FORNITORE
    assert "nota_credito" in scheduler.TIPI_PARTITA_FORNITORE
