"""17/09/2026 (collaudo funzionale): una fattura con IVA di un fornitore nuovo
resta ``da_verificare`` ("IVA detraibile non classificata") e la
classificazione manuale per centro di costo scriveva solo ``centro_costo_id``:
nessuna azione la sbloccava. Ora la scelta del centro di costo ricalcola gli
importi fiscali con la stessa funzione del handler automatico e chiede la
registrazione al motore unico del libro giornale.
"""
import asyncio

from app.routers.invoices import fatture_upload as fu
from app.services.sheets_document_store import MemorySheetsClient


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _db(nome):
    return MemorySheetsClient()[nome]


def _fattura(**extra):
    doc = {
        "id": "f-nuova", "invoice_number": "ZZZ-1", "invoice_date": "2026-02-02",
        "supplier_name": "ZZZ TEST FORNITORE", "supplier_id": "s1",
        "imponibile": 100.0, "iva": 22.0, "total_amount": 122.0, "status": "imported",
        "registrazione_contabile_esito": {"stato": "da_verificare", "motivo": "IVA detraibile non classificata"},
    }
    doc.update(extra)
    return doc


def test_classifica_manuale_calcola_iva_detraibile_e_registra(monkeypatch):
    db = _db("classifica-registra")
    monkeypatch.setattr(fu.Database, "get_db", staticmethod(lambda: db))

    async def scenario():
        await db["invoices"].insert_one(_fattura())
        esito = await fu.classifica_fattura_manuale("f-nuova", {"centro_costo_id": "1.1_CAFFE_BEVANDE_CALDE"})
        fattura = await db["invoices"].find_one({"id": "f-nuova"})
        scritture = await db["movimenti_contabili"].find({}).to_list(10)
        return esito, fattura, scritture

    esito, fattura, scritture = _run(scenario())

    assert esito["success"] is True
    assert esito["centro_costo_id"] == "1.1_CAFFE_BEVANDE_CALDE"
    assert esito["registrazione_contabile"]["stato"] == "registrato"
    # stessi importi del handler automatico: detraibilita' 100% => 22,00
    assert fattura["iva_detraibile"] == 22.0 and fattura["iva_indetraibile"] == 0.0
    assert fattura["classificato_da"] == "manuale"
    assert fattura["registrata_contabilita"] is True
    assert len(scritture) == 1 and scritture[0]["idempotency_key"] == "reg:fattura:f-nuova"
    righe = scritture[0]["righe"]
    assert round(sum(r.get("dare") or 0 for r in righe), 2) == round(sum(r.get("avere") or 0 for r in righe), 2) == 122.0


def test_classifica_manuale_e_idempotente_sul_libro_giornale(monkeypatch):
    db = _db("classifica-idempotente")
    monkeypatch.setattr(fu.Database, "get_db", staticmethod(lambda: db))

    async def scenario():
        await db["invoices"].insert_one(_fattura())
        primo = await fu.classifica_fattura_manuale("f-nuova", {"centro_costo_id": "1.1_CAFFE_BEVANDE_CALDE"})
        secondo = await fu.classifica_fattura_manuale("f-nuova", {"centro_costo_id": "1.1_CAFFE_BEVANDE_CALDE"})
        return primo, secondo, await db["movimenti_contabili"].find({}).to_list(10)

    primo, secondo, scritture = _run(scenario())
    assert primo["registrazione_contabile"]["stato"] == "registrato"
    assert secondo["registrazione_contabile"]["stato"] == "gia_registrato"
    assert len(scritture) == 1


def test_classifica_manuale_con_centro_sconosciuto_non_inventa_la_detraibilita(monkeypatch):
    db = _db("classifica-sconosciuto")
    monkeypatch.setattr(fu.Database, "get_db", staticmethod(lambda: db))

    async def scenario():
        await db["invoices"].insert_one(_fattura())
        esito = await fu.classifica_fattura_manuale("f-nuova", {"centro_costo_id": "CDC_INESISTENTE"})
        fattura = await db["invoices"].find_one({"id": "f-nuova"})
        return esito, fattura, await db["movimenti_contabili"].find({}).to_list(10)

    esito, fattura, scritture = _run(scenario())
    assert esito["success"] is True  # il centro di costo resta comunque annotato
    assert esito["registrazione_contabile"]["stato"] == "saltato"
    assert "detraibilita" in esito["registrazione_contabile"]["motivo"]
    assert "iva_detraibile" not in fattura
    assert scritture == []
