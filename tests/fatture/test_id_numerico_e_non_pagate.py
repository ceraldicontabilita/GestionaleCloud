"""Su `invoices` l'`id` e' un numero su meta' delle righe (regola 12) e lo
stato di pagamento vive in cinque campi (regola 11): i filtri devono
trovare la fattura per id numerico e non contare come aperta una pagata."""
import asyncio

from app.services import distinta_bonifici as distinta
from app.services import iva_detraibilita
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.data_propagation import DataPropagationService
from app.services.handlers.fattura_handlers import on_fattura_created_iva
from app.services.riallinea_pagamenti_fatture import _valuta_riga
from app.services.riconciliazione_smart import cerca_fatture_fornitore
from app.utils.id_fattura import filtro_id, filtro_id_in, varianti_id

ID_NUM = 1776634698467


def _fattura(fid, **extra):
    return {"id": fid, "invoice_number": "7", "invoice_date": "2026-09-01",
            "supplier_name": "Rossi Srl", "supplier_vat": "01234567890",
            "supplier_id": "forn-1", "total_amount": 100.0, "tipo_documento": "TD01",
            "status": "imported", **extra}


def _run(coro):
    return asyncio.run(coro)


def test_varianti_id():
    assert varianti_id(ID_NUM) == [str(ID_NUM), ID_NUM]
    assert varianti_id("abc") == ["abc"]
    assert filtro_id("12") == {"id": {"$in": ["12", 12]}}
    assert filtro_id_in(["1", 1, "x"]) == {"id": {"$in": ["1", 1, "x"]}}


def test_distinta_trova_la_fattura_con_id_numerico():
    async def scenario():
        db = ClientArchivioMemoria()["id-num-distinta"]
        await db["invoices"].insert_one(_fattura(ID_NUM))
        return await distinta.componi_bonifici(db, [str(ID_NUM)])

    esito = _run(scenario())
    assert {"id": str(ID_NUM), "motivo": "fattura_non_trovata"} not in esito.get("scartate", [])


def test_handler_iva_e_ricalcolo_trovano_la_fattura_numerica():
    async def scenario():
        db = ClientArchivioMemoria()["id-num-iva"]
        await db["invoices"].insert_one(_fattura(ID_NUM))
        a = await on_fattura_created_iva({"fattura_id": str(ID_NUM)}, db)
        b = await iva_detraibilita.ricalcola_iva_fattura(db, str(ID_NUM))
        return a, b

    a, b = _run(scenario())
    assert a.get("reason") != "fattura non trovata"
    assert b.get("motivo") != "fattura non trovata"


def test_riallinea_valuta_riga_trova_la_fattura_numerica():
    async def scenario():
        db = ClientArchivioMemoria()["id-num-riallinea"]
        await db["invoices"].insert_one(_fattura(ID_NUM))
        return await _valuta_riga(db, {"id": "pn1", "fattura_id": str(ID_NUM)})

    esito = _run(scenario())
    assert "fattura_non_trovata" not in str(esito.get("esito"))


def test_una_pagata_senza_campo_pagato_non_e_fra_le_non_pagate():
    async def scenario():
        db = ClientArchivioMemoria()["non-pagate"]
        await db["invoices"].insert_many([
            _fattura("aperta"),
            _fattura("pagata-inglese", payment_status="paid"),
            _fattura("pagata-italiana", stato="pagata"),
        ])
        saldo = await DataPropagationService(db).recalculate_supplier_balance("forn-1")
        trovate = await cerca_fatture_fornitore(db, piva_fornitore="01234567890")
        return saldo, trovate

    saldo, trovate = _run(scenario())
    assert saldo["saldo_aperto"] == 100.0
    assert [f["id"] for f in trovate] == ["aperta"]
