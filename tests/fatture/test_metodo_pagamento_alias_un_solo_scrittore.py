"""`PUT /api/suppliers/{id}/metodo-pagamento` non scrive piu' da solo.

Era un secondo scrittore del metodo, senza «metodo valido dal» ne' storico: un
fornitore cambiato da qui non valeva mai per il passato. Ora e' un alias di
`update_supplier`, che stampa la data solo a un cambio vero e accoda lo storico.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _prepara(monkeypatch, nome):
    from app.database import Database
    from app.routers.suppliers_module import base
    from app.utils import iva_calculator

    db = ClientArchivioMemoria()[nome]

    async def clear_pattern(pattern):
        return None

    async def save_dictionary(*args, **kwargs):
        return True

    def discard_background(coro):
        coro.close()
        return None

    monkeypatch.setattr(Database, "get_db", classmethod(lambda cls: db))
    monkeypatch.setattr(base.cache, "clear_pattern", clear_pattern)
    monkeypatch.setattr(iva_calculator, "save_supplier_payment_method", save_dictionary)
    monkeypatch.setattr(asyncio, "create_task", discard_background)
    return db, base


def test_l_alias_scrive_data_e_storico_come_la_scheda(monkeypatch):
    db, base = _prepara(monkeypatch, "alias_metodo")

    async def scenario():
        await db["fornitori"].insert_one({
            "id": "supplier-1", "partita_iva": "04518411212",
            "ragione_sociale": "Fornitore prova", "metodo_pagamento": "cassa",
            "metodo_pagamento_dal": "2025-01-01",
            "storico_metodi_pagamento": [{"metodo": "cassa", "dal": "2025-01-01"}],
        })
        esito = await base.update_supplier_payment_method("supplier-1", "banca")
        dopo = await db["fornitori"].find_one({"id": "supplier-1"}, {"_id": 0})
        # lo stesso metodo di nuovo: nessun cambio, la data non si ristampa
        await base.update_supplier_payment_method("supplier-1", "banca")
        ancora = await db["fornitori"].find_one({"id": "supplier-1"}, {"_id": 0})
        return esito, dopo, ancora

    esito, dopo, ancora = asyncio.run(scenario())
    assert esito["success"] is True and esito["metodo_pagamento"] == "banca"
    assert dopo["metodo_pagamento"] == "banca"
    assert dopo["metodo_pagamento_dal"] == esito["metodo_pagamento_dal"] != "2025-01-01"
    assert [v["metodo"] for v in dopo["storico_metodi_pagamento"]] == ["cassa", "banca"]
    assert ancora["metodo_pagamento_dal"] == dopo["metodo_pagamento_dal"]
    assert len(ancora["storico_metodi_pagamento"]) == 2


def test_l_alias_rifiuta_un_metodo_fuori_vocabolario_e_un_fornitore_assente(monkeypatch):
    db, base = _prepara(monkeypatch, "alias_metodo_errori")

    with pytest.raises(HTTPException) as err:
        asyncio.run(base.update_supplier_payment_method("supplier-1", "criptovaluta"))
    assert err.value.status_code == 400

    with pytest.raises(HTTPException) as err:
        asyncio.run(base.update_supplier_payment_method("non-esiste", "banca"))
    assert err.value.status_code == 404


def test_i_sinonimi_dei_vecchi_chiamanti_restano_nel_vocabolario_unico(monkeypatch):
    db, base = _prepara(monkeypatch, "alias_metodo_sinonimi")

    async def scenario():
        await db["fornitori"].insert_one({"id": "s2", "partita_iva": "04518411212",
                                          "ragione_sociale": "Prova"})
        esito = await base.update_supplier_payment_method("s2", "BANK")
        return esito, await db["fornitori"].find_one({"id": "s2"}, {"_id": 0})

    esito, dopo = asyncio.run(scenario())
    assert esito["metodo_pagamento"] == "banca" and dopo["metodo_pagamento"] == "banca"
    assert dopo["metodo_pagamento_dal"]
