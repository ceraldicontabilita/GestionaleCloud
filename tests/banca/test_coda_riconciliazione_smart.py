"""Coda «da riconciliare» di /smart/analizza e del tab Banca.

- «Ignora» scrive ``ignorato``/``escluso_dalla_coda``: il movimento non torna;
- una copia provvisoria coperta dall'estratto ufficiale non entra; oltre il suo
  ultimo giorno e' l'unica traccia del movimento ed entra;
- un accredito POS NUMIA non ha documento da abbinare: si conta a parte;
- le fatture fornitore non hanno scadenza, quindi anche una fattura vecchia
  resta candidata.
"""
import asyncio
from datetime import datetime, timedelta

from app.services.archivio_documenti_memoria import ClientArchivioMemoria

import app.services.riconciliazione_smart as smart_service
from app.routers.operazioni_module import smart as smart_router


def _run(coro):
    return asyncio.run(coro)


MOVIMENTI = [
    {"id": "M-BUONO", "data": "2026-08-10", "importo": -120.0, "tipo": "uscita",
     "descrizione": "BONIFICO A FORNITORE ALFA SRL"},
    {"id": "M-IGNORATO", "data": "2026-08-10", "importo": -50.0, "tipo": "uscita",
     "descrizione": "BONIFICO DUPLICATO", "ignorato": True, "escluso_dalla_coda": True},
    {"id": "M-IGNORATA", "data": "2026-08-10", "importo": -51.0, "tipo": "uscita",
     "descrizione": "BONIFICO VECCHIO FLAG", "ignorata": True},
    {"id": "M-PROVVISORIO", "data": "2026-08-09", "importo": -60.0, "tipo": "uscita",
     "descrizione": "BONIFICO DA EXPORT CSV", "livello_evidenza": "provvisoria",
     "evidenza_bancaria_ufficiale": False, "in_attesa_estratto_ufficiale": True},
    # Oltre l'ultimo giorno dell'estratto ufficiale (10/08) la copia
    # provvisoria e' l'unica traccia: entra in coda.
    {"id": "M-RECENTE", "data": "2026-08-20", "importo": -70.0, "tipo": "uscita",
     "descrizione": "BONIFICO DA BANCA DIRETTA", "livello_evidenza": "provvisoria",
     "evidenza_bancaria_ufficiale": False, "in_attesa_estratto_ufficiale": True},
    {"id": "M-POS", "data": "2026-08-04", "importo": 867.30, "tipo": "entrata",
     "descrizione_originale": "INC.POS CARTE CREDIT - NUMIA-INTER DEL 03/08/26 PDV 3757283/0001"},
]


def _db(nome):
    db = ClientArchivioMemoria()[nome]

    async def carica():
        await db.estratto_conto_movimenti.insert_many([dict(m) for m in MOVIMENTI])

    _run(carica())
    return db


def test_analizza_esclude_ignorati_provvisori_e_accrediti_numia(monkeypatch):
    db = _db("test_coda_smart_filtri")
    monkeypatch.setattr(smart_service.Database, "get_db", staticmethod(lambda: db))

    risultati = _run(smart_service.analizza_estratto_conto_batch(limit=50, anno=2026))

    ids = {r.get("movimento_id") or (r.get("movimento") or {}).get("id") for r in risultati["movimenti"]}
    assert "M-BUONO" in ids
    assert not ids & {"M-IGNORATO", "M-IGNORATA", "M-PROVVISORIO", "M-POS"}
    assert risultati["stats"]["totale_righe"] == 2
    assert risultati["stats"]["accrediti_pos_numia_esclusi"] == 1


def test_analizza_propone_anche_fatture_oltre_novanta_giorni(monkeypatch):
    db = ClientArchivioMemoria()["test_coda_smart_fatture_vecchie"]
    vecchia = (datetime.now() - timedelta(days=200)).strftime("%Y-%m-%d")

    async def carica():
        await db.estratto_conto_movimenti.insert_one(dict(MOVIMENTI[0]))
        await db.invoices.insert_many([
            {"id": "F-VECCHIA", "invoice_number": "1/26", "invoice_date": vecchia,
             "supplier_name": "ALFA SRL", "total_amount": 120.0},
            {"id": "F-PAGATA", "invoice_number": "2/26", "invoice_date": vecchia,
             "supplier_name": "ALFA SRL", "total_amount": 120.0,
             "stato_pagamento": "pagata", "pagato": True},
        ])

    _run(carica())
    monkeypatch.setattr(smart_service.Database, "get_db", staticmethod(lambda: db))
    catturata = {}

    async def spia(mov, cache):
        catturata["fatture"] = [f["id"] for f in cache["fatture"]]
        return {"tipo": "non_riconosciuto"}

    monkeypatch.setattr(smart_service, "analizza_movimento_con_cache", spia)
    _run(smart_service.analizza_estratto_conto_batch(limit=50, anno=2026))

    assert catturata["fatture"] == ["F-VECCHIA"]


def test_banca_veloce_non_ripropone_i_movimenti_ignorati(monkeypatch):
    db = _db("test_banca_veloce_ignorati")
    monkeypatch.setattr(smart_router.Database, "get_db", staticmethod(lambda: db))

    result = _run(smart_router.banca_veloce(limit=50, anno=2026))

    ids = {m["id"] for m in result["movimenti"]}
    assert not ids & {"M-IGNORATO", "M-IGNORATA"}
    assert "M-BUONO" in ids
    assert result["stats"]["non_riconciliati"] == len(MOVIMENTI) - 2
