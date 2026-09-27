"""PagoPA/CBILL: i movimenti CBILL hanno la causale in `descrizione`, non in
`descrizione_originale`; la banca addebita l'importo dell'operazione, non
importo + commissione."""
import asyncio

from app.database import Database
from app.routers import pagopa
from app.services.archivio_documenti_memoria import ArchivioDocumenti
from app.services.pagopa_receipts import _movimento_della_ricevuta

CBILL = "CBILL 301000000012345678"


def _db_con_movimenti():
    db = ArchivioDocumenti()

    async def prepara():
        await db["estratto_conto_movimenti"].insert_many([
            # CBILL: solo `descrizione`
            {"id": "M-1", "data": "2026-05-10", "importo": -781.60,
             "descrizione": f"PAGAMENTO {CBILL} AGENZIA DELLE ENTRATE - RISCOSSIONE"},
            # PagoPA con descrizione_originale
            {"id": "M-2", "data": "2026-06-10", "importo": -50.00,
             "descrizione_originale": "PAGOPA COMUNE DI NAPOLI"},
            {"id": "M-3", "data": "2026-06-11", "importo": -20.00,
             "descrizione": "BONIFICO FORNITORE"},
        ])

    asyncio.run(prepara())
    return db


def test_stats_contano_anche_i_cbill_senza_descrizione_originale(monkeypatch):
    db = _db_con_movimenti()
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    stats = asyncio.run(pagopa.stats_pagopa(anno=2026))
    assert stats["movimenti_pagopa"] == 2
    assert stats["movimenti_senza_ricevuta"] == 2
    assert stats["totale_pagato"] == 781.60


def test_cerca_movimenti_raggruppa_i_cbill_per_ente(monkeypatch):
    db = _db_con_movimenti()
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    risultato = asyncio.run(pagopa.cerca_movimenti_pagopa(anno=2026, solo_non_associati=True))
    assert risultato["totale"] == 2
    assert risultato["per_beneficiario"]["Agenzia delle Entrate - Riscossione"]["count"] == 1


def test_ricevuta_trova_il_movimento_all_importo_dell_operazione():
    db = _db_con_movimenti()
    valori = {"operation_amount": 781.60, "bank_debit_total": 784.45}
    movimento = asyncio.run(_movimento_della_ricevuta(
        db, ["301000000012345678"], valori, 781.60,
    ))
    assert movimento["id"] == "M-1"


def test_ricevuta_ripiega_sull_addebito_totale_sempre_col_codice():
    db = ArchivioDocumenti()

    async def scenario():
        await db["estratto_conto_movimenti"].insert_many([
            {"id": "M-T", "importo": -784.45, "descrizione": f"PAGAMENTO {CBILL}"},
            # stesso importo, senza il codice: non e' il movimento
            {"id": "M-X", "importo": -781.60, "descrizione": "PAGAMENTO ALTRO"},
        ])
        trovato = await _movimento_della_ricevuta(
            db, ["301000000012345678"], {"operation_amount": 781.60, "bank_debit_total": 784.45},
            781.60,
        )
        senza_codice = await _movimento_della_ricevuta(
            db, ["999999999999999999"], {"operation_amount": 781.60}, 781.60,
        )
        return trovato, senza_codice

    trovato, senza_codice = asyncio.run(scenario())
    assert trovato["id"] == "M-T"
    assert senza_codice is None
