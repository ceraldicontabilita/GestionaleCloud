"""Il movimento bancario di una ricevuta pagoPA e' un'uscita, mai un'entrata con lo stesso importo."""
import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.pagopa_receipts import find_bank_movement

IUV = "01234567890123456"


def _db(*movimenti):
    db = ClientArchivioMemoria()["pagopa_verso"]
    for m in movimenti:
        asyncio.run(db.estratto_conto_movimenti.insert_one(dict(m)))
    return db


def test_un_rimborso_con_lo_stesso_iuv_non_e_il_pagamento():
    db = _db({"id": "rimborso", "tipo": "entrata", "importo": 781.60,
              "descrizione": f"RIMBORSO IUV {IUV}"})
    assert asyncio.run(find_bank_movement(db, IUV, 781.60)) is None


def test_l_uscita_con_lo_stesso_iuv_si_aggancia_anche_con_l_entrata_accanto():
    db = _db(
        {"id": "rimborso", "tipo": "entrata", "importo": 781.60, "descrizione": f"RIMBORSO IUV {IUV}"},
        {"id": "pagamento", "tipo": "uscita", "importo": 781.60, "descrizione": f"PAGOPA IUV {IUV}"},
    )
    assert asyncio.run(find_bank_movement(db, IUV, 781.60))["id"] == "pagamento"


def test_vecchio_archivio_importo_con_segno_senza_tipo():
    db = _db({"id": "vecchio", "importo": -781.60, "descrizione": f"PAGOPA IUV {IUV}"})
    assert asyncio.run(find_bank_movement(db, IUV, 781.60))["id"] == "vecchio"
