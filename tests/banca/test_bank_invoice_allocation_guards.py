"""Il riscontro fattura usa verso, netto fornitore e controparte coerenti."""
import asyncio

import pytest
from fastapi import HTTPException

from app.routers.operazioni_module import smart
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.bank_payment_allocations import (
    reconcile_cited_invoices,
    reconcile_deterministic_invoice_allocations,
)


def _fattura(**extra):
    return {
        "id": "F1", "invoice_number": "12345", "invoice_date": "2026-08-01",
        "supplier_name": "ALFA RICAMBI SRL", "supplier_vat": "11111111111",
        "total_amount": 100.0, **extra,
    }


def _movimento(**extra):
    return {
        "id": "M1", "data": "2026-08-10", "tipo": "uscita", "importo": -100.0,
        "descrizione": "BONIFICO ALFA RICAMBI SRL SALDO FATTURA 12345", **extra,
    }


async def _nessuna_scrittura(db):
    assert await db.bank_payment_allocations.count_documents({}) == 0
    assert await db.prima_nota_banca.count_documents({}) == 0
    assert not (await db.invoices.find_one({"id": "F1"})).get("pagato")
    assert not (await db.estratto_conto_movimenti.find_one({"id": "M1"})).get("riconciliato")


def test_parcella_non_alloca_la_ritenuta_al_fornitore(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria()["guard_netto_fornitore"]
        await db.invoices.insert_one(_fattura(
            total_amount=1220.0, ritenuta_importo=200.0, pagamento_rate_totale=1020.0,
        ))
        await db.estratto_conto_movimenti.insert_one(_movimento(importo=-1220.0))
        monkeypatch.setattr(smart.Database, "get_db", staticmethod(lambda: db))
        with pytest.raises(HTTPException) as exc:
            await smart.riconcilia_manuale(smart.RiconciliaManuale(
                movimento_id="M1", tipo="fattura_bonifico",
                associazioni=[{"id": "F1", "quota_cents": 122000}],
            ))
        assert exc.value.status_code == 409
        await _nessuna_scrittura(db)

        # Lo stesso percorso accetta il netto documentato, senza versare il 1040.
        await db.estratto_conto_movimenti.update_one({"id": "M1"}, {"$set": {"importo": -1020.0}})
        await smart.riconcilia_manuale(smart.RiconciliaManuale(
            movimento_id="M1", tipo="fattura_bonifico",
            associazioni=[{"id": "F1", "quota_cents": 102000}],
        ))
        fattura = await db.invoices.find_one({"id": "F1"})
        assert fattura["pagato"] is True
        assert fattura["importo_pagato"] == 1020.0
        assert fattura["ritenuta_non_pagabile_fornitore"] == 200.0

    asyncio.run(scenario())


def test_totale_negativo_non_diventa_un_debito_positivo(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria()["guard_totale_negativo"]
        await db.invoices.insert_one(_fattura(total_amount=-100.0))
        await db.estratto_conto_movimenti.insert_one(_movimento())
        monkeypatch.setattr(smart.Database, "get_db", staticmethod(lambda: db))
        with pytest.raises(HTTPException) as exc:
            await smart.riconcilia_manuale(smart.RiconciliaManuale(
                movimento_id="M1", tipo="fattura_bonifico",
                associazioni=[{"id": "F1", "quota_cents": 10000}],
            ))
        assert exc.value.status_code == 409
        assert "totale_documento_non_valido" in exc.value.detail
        await _nessuna_scrittura(db)

    asyncio.run(scenario())


@pytest.mark.parametrize("tipo,importo", [
    ("entrata", 100.0), ("accredito", -100.0), ("carta_credito", -100.0),
])
def test_entrata_non_chiude_un_debito_fornitore(monkeypatch, tipo, importo):
    async def scenario():
        db = ClientArchivioMemoria()[f"guard_verso_{tipo}"]
        await db.invoices.insert_one(_fattura())
        await db.estratto_conto_movimenti.insert_one(_movimento(tipo=tipo, importo=importo))
        monkeypatch.setattr(smart.Database, "get_db", staticmethod(lambda: db))
        with pytest.raises(HTTPException) as exc:
            await smart.riconcilia_manuale(smart.RiconciliaManuale(
                movimento_id="M1", tipo="fattura_bonifico",
                associazioni=[{"id": "F1", "quota_cents": 10000}],
            ))
        assert exc.value.status_code == 409
        await _nessuna_scrittura(db)

    asyncio.run(scenario())


@pytest.mark.parametrize("tipo", ["uscita", "addebito", "pagamento", "carta_credito"])
def test_uscita_con_importo_positivo_conserva_il_formato_storico(monkeypatch, tipo):
    async def scenario():
        db = ClientArchivioMemoria()["guard_uscita_storica"]
        await db.invoices.insert_one(_fattura())
        await db.estratto_conto_movimenti.insert_one(_movimento(importo=100.0, tipo=tipo))
        monkeypatch.setattr(smart.Database, "get_db", staticmethod(lambda: db))
        await smart.riconcilia_manuale(smart.RiconciliaManuale(
            movimento_id="M1", tipo="fattura_bonifico",
            associazioni=[{"id": "F1", "quota_cents": 10000}],
        ))
        assert (await db.invoices.find_one({"id": "F1"}))["pagato"] is True
        assert (await db.prima_nota_banca.find_one({}))["tipo"] == "uscita"

    asyncio.run(scenario())


@pytest.mark.parametrize("descrizione,controparte", [
    ("BONIFICO BETA ALIMENTARI SRL SALDO FATTURA 12345", {"beneficiario": "BETA ALIMENTARI SRL"}),
    ("SDD CORE: MANDATO123 BETA ALIMENTARI SRL - SALDO FATTURA 12345", {}),
    ("BONIFICO SALDO FATTURA 12345", {"iban_beneficiario": "IT22B2222222222222222222222"}),
    ("BONIFICO SALDO FATTURA 12345 P.IVA 11111111111", {"iban_beneficiario": "IT22B2222222222222222222222"}),
    ("BONIFICO SALDO FATTURA 12345 P.IVA 11111111111", {"beneficiario": "BETA ALIMENTARI SRL"}),
])
@pytest.mark.parametrize("motore", ["deterministico", "fatture_citate"])
def test_numero_fattura_non_prevale_sulla_controparte_incompatibile(descrizione, controparte, motore):
    async def scenario():
        db = ClientArchivioMemoria()["guard_controparte"]
        await db.invoices.insert_one(_fattura(supplier_iban="IT11A1111111111111111111111"))
        movimento = _movimento(descrizione=descrizione, **controparte)
        await db.estratto_conto_movimenti.insert_one(movimento)
        if motore == "deterministico":
            risultato = await reconcile_deterministic_invoice_allocations(db, movement_ids=["M1"])
            assert risultato["allocati"] == 0
            assert risultato["allocati_identita"] == 0
        else:
            risultato = await reconcile_cited_invoices(db, [movimento])
            assert risultato["collegati_count"] == 0
        await _nessuna_scrittura(db)

    asyncio.run(scenario())


def test_nota_credito_resta_fuori_dal_pagamento_debito(monkeypatch):
    async def scenario():
        db = ClientArchivioMemoria()["guard_nota_credito"]
        await db.invoices.insert_one(_fattura(tipo_documento="TD04"))
        await db.estratto_conto_movimenti.insert_one(_movimento())
        monkeypatch.setattr(smart.Database, "get_db", staticmethod(lambda: db))
        with pytest.raises(HTTPException) as exc:
            await smart.riconcilia_manuale(smart.RiconciliaManuale(
                movimento_id="M1", tipo="fattura_bonifico",
                associazioni=[{"id": "F1", "quota_cents": 10000}],
            ))
        assert exc.value.status_code == 409
        assert "nota_di_credito" in exc.value.detail
        await _nessuna_scrittura(db)

    asyncio.run(scenario())
