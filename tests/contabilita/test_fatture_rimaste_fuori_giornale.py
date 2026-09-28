"""Fatture rifiutate dal giornale in attesa della classificazione IVA.

All'import il giornale rifiuta una fattura con ``iva_detraibile`` assente;
il job bancario corto la classifica dopo, e da allora deve entrare da sola
nel giornale, una volta sola, senza toccare chi aspetta una decisione umana.
"""
import asyncio

from app.services import registrazione_contabile as rc
from app.services.archivio_documenti_memoria import ClientArchivioMemoria

RIFIUTATA = {"stato": "da_verificare", "motivo": "IVA detraibile non classificata"}


def _fattura(fid, **extra):
    base = {
        "id": fid, "invoice_number": fid, "invoice_date": "2026-04-10",
        "supplier_vat": "01234567890", "supplier_name": "Fornitore Latticini Srl",
        "total_amount": 122.0, "imponibile": 100.0, "iva": 22.0, "iva_detraibile": 22.0,
        "tipo_documento": "TD01",
        "linee": [{"descrizione": "Latte fresco", "prezzo_totale": 100.0, "aliquota_iva": 22}],
    }
    base.update(extra)
    return base


def test_la_fattura_classificata_dopo_il_rifiuto_entra_nel_giornale_una_volta():
    async def scenario():
        db = ClientArchivioMemoria()["gc"]
        await db["invoices"].insert_many([
            _fattura("f-rifiutata", registrazione_contabile_esito=RIFIUTATA),
            _fattura("f-mai-provata"),
            _fattura("f-ancora-da-classificare", iva_detraibile=None,
                     registrazione_contabile_esito=RIFIUTATA),
            _fattura("f-da-correggere-a-mano", registrazione_contabile_esito={
                "stato": "da_verificare", "motivo": "scrittura gia' registrata per 10.00"}),
            _fattura("f-archiviata", status="archiviata"),
        ])
        primo = await rc.registra_fatture_rimaste_fuori(db)
        secondo = await rc.registra_fatture_rimaste_fuori(db)
        movimenti = await db[rc.COLL_MOVIMENTI].find(
            {"tipo": "fattura_acquisto"}, {"_id": 0, "fattura_id": 1}).to_list(None)
        rifiutata = await db["invoices"].find_one({"id": "f-rifiutata"}, {"_id": 0})
        return primo, secondo, movimenti, rifiutata

    primo, secondo, movimenti, rifiutata = asyncio.run(scenario())
    assert primo == {"candidate": 2, "registrate": 2, "ancora_fuori": 0}
    assert secondo == {"candidate": 0, "registrate": 0, "ancora_fuori": 0}
    assert sorted(m["fattura_id"] for m in movimenti) == ["f-mai-provata", "f-rifiutata"]
    assert "registrazione_contabile_esito" not in rifiutata


def test_il_lotto_ha_un_tetto():
    async def scenario():
        db = ClientArchivioMemoria()["gc"]
        await db["invoices"].insert_many([_fattura(f"f-{i}") for i in range(5)])
        return await rc.registra_fatture_rimaste_fuori(db, limite=2)

    assert asyncio.run(scenario()) == {"candidate": 5, "registrate": 2, "ancora_fuori": 0}
