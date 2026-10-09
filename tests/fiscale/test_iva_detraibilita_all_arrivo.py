"""La detraibilita' si decide all'arrivo della fattura, e l'arretrato si smaltisce.

Il motore IVA gira prima della classificazione e trovava `iva_detraibile`
vuota: la fattura restava DA_VERIFICARE per sempre e il mese «non calcolato».
"""
import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services import iva_detraibilita as mod


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _fattura(fid, **extra):
    return {"id": fid, "invoice_date": "2026-03-10", "created_at": "2026-03-12T00:00:00",
            "iva": 22, "imponibile": 100, "total_amount": 122, "status": "imported", **extra}


def test_ricalcolo_sblocca_la_fattura_classificata():
    db = ClientArchivioMemoria()["iva_arrivo"]

    async def scenario():
        await db["invoices"].insert_one(_fattura("F1", stato_detrazione_iva="DA_VERIFICARE",
                                                 iva_detraibile=22))
        await mod.ricalcola_iva_fattura(db, "F1")
        return await db["invoices"].find_one({"id": "F1"}, {"_id": 0})

    assert _run(scenario())["stato_detrazione_iva"] == "DA_INSERIRE"


def test_pregresso_ricalcola_una_volta_e_non_ripassa_le_ferme():
    db = ClientArchivioMemoria()["iva_pregresso"]

    async def scenario():
        await db["invoices"].insert_many([
            _fattura("SBLOCCA", stato_detrazione_iva="DA_VERIFICARE", iva_detraibile=22),
            # righe da rivedere: resta da verificare, e non si ripassa a vuoto
            _fattura("FERMA", stato_detrazione_iva="DA_VERIFICARE", iva_detraibile=22,
                     stato_classificazione="da_verificare"),
            _fattura("ARCHIVIATA", status="archived", stato_detrazione_iva="DA_VERIFICARE",
                     iva_detraibile=22),
        ])
        primo = await mod.completa_iva_pregresso(db)
        secondo = await mod.completa_iva_pregresso(db)
        fatture = {f["id"]: f for f in await db["invoices"].find({}, {"_id": 0}).to_list(None)}
        return primo, secondo, fatture

    primo, secondo, fatture = _run(scenario())
    assert fatture["SBLOCCA"]["stato_detrazione_iva"] == "DA_INSERIRE"
    assert fatture["FERMA"]["stato_detrazione_iva"] == "DA_VERIFICARE"
    assert fatture["ARCHIVIATA"]["stato_detrazione_iva"] == "DA_VERIFICARE"
    assert primo["candidate"] == 2 and primo["sbloccate"] == 1
    assert secondo["candidate"] == 0
