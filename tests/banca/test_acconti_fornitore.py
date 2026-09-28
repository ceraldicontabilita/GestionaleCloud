"""Acconti: una fattura pagata in piu' bonifici allo stesso fornitore.

Titolare, 28/09/2026: «sono acconti delle fatture». FEP 7_26 di A 2000
Costruzioni (24.400,00 dell'11/02) = 15.000,00 del 12/02 + 9.400,00 del 26/02:
nessun bonifico quadra da solo, e il motore li lasciava senza fattura.
"""
import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.bank_payment_allocations import (
    reconcile_acconti_fornitore,
    reconcile_deterministic_invoice_allocations,
)

FORNITORE = "A 2000 Costruzioni S.r.l"


def _run(coro):
    return asyncio.run(coro)


def _fattura(fid, numero, importo, data, fornitore=FORNITORE, piva="08577391215"):
    return {
        "id": fid, "invoice_number": numero, "invoice_date": data,
        "supplier_name": fornitore, "supplier_vat": piva, "total_amount": importo,
        "importo_residuo": importo, "importo_pagato": 0.0, "pagato": False,
        "stato_pagamento": "da_pagare",
    }


def _bonifico(mid, data, importo, beneficiario="A 2000 COSTRUZIONI S.R.L"):
    return {
        "id": mid, "data": data, "tipo": "uscita", "importo": -importo, "riconciliato": False,
        "descrizione_originale": f"VS.DISP. RIF. MBVT{mid}/1 FAVORE {beneficiario}",
    }


def test_due_acconti_che_fanno_la_fattura_la_pagano():
    async def scenario():
        db = ClientArchivioMemoria()["acconti"]
        await db.invoices.insert_many([
            _fattura("fep7", "FEP 7_26", 24400.0, "2026-02-11"),
            _fattura("fep39", "FEP 39_26", 9760.0, "2026-04-28"),
        ])
        await db.estratto_conto_movimenti.insert_many([
            _bonifico("m1", "2026-02-12", 15000.0),
            _bonifico("m2", "2026-02-26", 9400.0),
            # stesso fornitore, ma non fa nessun totale: resta
            _bonifico("m3", "2026-05-02", 4200.0),
        ])
        esito = await reconcile_deterministic_invoice_allocations(db)
        assert esito["allocati_acconti"] == 2
        for mid in ("m1", "m2"):
            m = await db.estratto_conto_movimenti.find_one({"id": mid}, {"_id": 0})
            assert m["riconciliato"] is True
        fattura = await db.invoices.find_one({"id": "fep7"}, {"_id": 0})
        assert fattura["pagato"] is True
        assert not (await db.estratto_conto_movimenti.find_one({"id": "m3"}, {"_id": 0})).get("riconciliato")
        # Il secondo giro non collega niente di nuovo.
        secondo = await reconcile_deterministic_invoice_allocations(db)
        assert secondo["allocati_acconti"] == 0

    _run(scenario())


def test_senza_il_fornitore_in_causale_non_si_somma_niente():
    async def scenario():
        db = ClientArchivioMemoria()["acconti-altro"]
        await db.invoices.insert_one(_fattura("fep7", "FEP 7_26", 24400.0, "2026-02-11"))
        movimenti = [
            _bonifico("m1", "2026-02-12", 15000.0, beneficiario="ROSSI MARIO"),
            _bonifico("m2", "2026-02-26", 9400.0, beneficiario="ROSSI MARIO"),
        ]
        esito = await reconcile_acconti_fornitore(db, movimenti, proponi=False)
        assert esito["collegati_count"] == 0 and esito["ambigui"] == 0

    _run(scenario())


def test_due_combinazioni_per_la_stessa_fattura_non_scelgono():
    async def scenario():
        db = ClientArchivioMemoria()["acconti-ambigui"]
        await db.invoices.insert_one(_fattura("f1", "FEP 1_26", 300.0, "2026-03-01"))
        movimenti = [
            _bonifico("a", "2026-03-02", 100.0),
            _bonifico("b", "2026-03-03", 200.0),
            _bonifico("c", "2026-03-04", 200.0),
        ]
        esito = await reconcile_acconti_fornitore(db, movimenti, proponi=False)
        assert esito["collegati_count"] == 0 and esito["ambigui"] == 1
        assert not (await db.invoices.find_one({"id": "f1"}, {"_id": 0})).get("pagato")

    _run(scenario())


def test_il_bonifico_prima_della_fattura_o_oltre_90_giorni_non_conta():
    async def scenario():
        db = ClientArchivioMemoria()["acconti-date"]
        await db.invoices.insert_one(_fattura("f1", "FEP 1_26", 300.0, "2026-03-01"))
        movimenti = [
            _bonifico("a", "2026-02-20", 100.0),
            _bonifico("b", "2026-06-15", 200.0),
        ]
        esito = await reconcile_acconti_fornitore(db, movimenti, proponi=False)
        assert esito["collegati_count"] == 0

    _run(scenario())


def test_job_corto_collega_gli_acconti_della_fattura_dichiarata_pagata():
    """FEP 7_26 in produzione: il titolare l'ha dichiarata pagata col report
    (``in_attesa_riscontro_banca``), i due bonifici arrivano dopo. Il job
    bancario corto la collega senza aspettare il giro «Automazioni»."""
    from app.services.bank_payment_allocations import riconcilia_acconti_in_sospeso

    async def scenario():
        db = ClientArchivioMemoria()["acconti"]
        fattura = _fattura("fep7", "FEP 7_26", 24400.0, "2026-02-11")
        fattura.update({
            "stato_pagamento": "pagata", "pagato": True, "paid": True,
            "payment_status": "paid", "in_attesa_riscontro_banca": True,
        })
        await db.invoices.insert_one(fattura)
        await db.estratto_conto_movimenti.insert_many([
            _bonifico("m1", "2026-02-12", 15000.0),
            _bonifico("m2", "2026-02-26", 9400.0),
        ])
        esito = await riconcilia_acconti_in_sospeso(db)
        assert esito["collegati_count"] == 2
        for mid in ("m1", "m2"):
            m = await db.estratto_conto_movimenti.find_one({"id": mid}, {"_id": 0})
            assert m["riconciliato"] is True
        assert (await riconcilia_acconti_in_sospeso(db))["collegati_count"] == 0

    _run(scenario())
