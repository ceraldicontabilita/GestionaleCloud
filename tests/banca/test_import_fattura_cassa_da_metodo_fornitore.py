"""Import fattura XML e metodo di pagamento del fornitore (CLAUDE.md §29).

Decisione del titolare del 07/10/2026, che supera la «Fase 0» del 15/09/2026:
le fatture si registrano in Prima Nota per metodo di pagamento impostato nei
fornitori, in automatico.

- fornitore **cassa** -> movimento in Prima Nota Cassa all'import, data
  fattura, fattura pagata, evento `fattura.pagata` una volta sola;
- secondo import della stessa fattura -> nessun secondo movimento e nessun
  secondo evento (§122);
- fornitore **senza metodo** -> fattura sospesa con alert, nessun movimento e
  nessun ripiego su Cassa.
"""
import asyncio

import pytest

from app.routers.invoices import fatture_upload as mod
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(c):
    return asyncio.run(c)


def _fattura(fattura_id="FT-1", piva="12345678901"):
    return {
        "id": fattura_id, "supplier_vat": piva, "supplier_name": "Fornitore Cassa",
        "invoice_number": "1/2026", "invoice_date": "2026-10-01",
        "total_amount": 61.0, "tipo_documento": "TD01",
    }


@pytest.fixture
def db(monkeypatch):
    database = ClientArchivioMemoria()["import_metodo_fornitore"]
    from app.routers.prima_nota_module import sync as sync_mod
    monkeypatch.setattr(sync_mod.Database, "get_db", staticmethod(lambda: database))
    return database


@pytest.fixture
def eventi(monkeypatch):
    registrati = []

    async def finto_propagate(event_type, payload, _db, source_module="", **_k):
        registrati.append((event_type, payload, source_module))
        return []

    from app.services import event_bus
    monkeypatch.setattr(event_bus, "propagate_event", finto_propagate)
    return registrati


def test_fornitore_cassa_scrive_prima_nota_cassa_e_marca_pagata(db, eventi):
    _run(db["fornitori"].insert_one({"partita_iva": "12345678901", "metodo_pagamento": "cassa"}))
    _run(db["invoices"].insert_one(_fattura()))

    result = _run(mod.auto_registra_prima_nota(db, _fattura(), "cassa"))

    movimenti = _run(db["prima_nota_cassa"].find({}).to_list(None))
    assert len(movimenti) == 1
    mov = movimenti[0]
    assert mov["fattura_id"] == "FT-1"
    assert mov["riferimento"] == "FATT-FT-1"
    assert mov["tipo"] == "uscita"
    assert mov["importo"] == 61.0
    # La data e' quella della fattura: dichiarazione del titolare via anagrafica.
    assert mov["data"] == "2026-10-01"
    assert mov["source"] == mod.SOURCE_AUTO_METODO_FORNITORE
    assert mov["fonte_data"] == "data_fattura"
    assert "anagrafica fornitore" in mov["motivo"]

    fattura = _run(db["invoices"].find_one({"id": "FT-1"}))
    from app.services.stato_pagamento_fattura import e_pagata, stato_pagamento
    assert e_pagata(fattura) is True
    assert stato_pagamento(fattura) == "pagata"
    assert fattura["metodo_pagamento_effettivo"] == "cassa"
    assert fattura["provvisorio"] is False
    assert fattura["decisione_pagamento_richiesta"] is False
    assert fattura["prima_nota_cassa_id"] == mov["id"]
    assert fattura["registrata_auto_da_metodo_fornitore"] is True
    assert fattura["data_pagamento"] == "2026-10-01"
    assert fattura["importo_residuo"] == 0
    assert result["stato_pagamento"] == "pagata"

    assert [e[0] for e in eventi] == ["fattura.pagata"]
    payload = eventi[0][1]
    assert payload["fattura_id"] == "FT-1"
    assert payload["metodo_pagamento"] == "cassa"
    assert payload["data_pagamento"] == "2026-10-01"
    assert payload["importo"] == 61.0
    assert payload["movimento_id"] == mov["id"]
    # Nessun alert «metodo non definito»: il metodo c'e'.
    assert _run(db["alerts"].count_documents({})) == 0


def test_secondo_import_stessa_fattura_non_duplica_movimento_ne_evento(db, eventi):
    _run(db["fornitori"].insert_one({"partita_iva": "12345678901", "metodo_pagamento": "contanti"}))
    _run(db["invoices"].insert_one(_fattura()))

    primo = _run(mod.auto_registra_prima_nota(db, _fattura(), "cassa"))
    # Il secondo giro riceve la fattura come sta in archivio (gia' pagata)...
    secondo = _run(mod.auto_registra_prima_nota(
        db, _run(db["invoices"].find_one({"id": "FT-1"}, {"_id": 0})), "cassa",
    ))
    # ...e anche un reimport con il dict grezzo non deve scrivere due volte.
    terzo = _run(mod.auto_registra_prima_nota(db, _fattura(), "cassa"))

    assert primo["stato_pagamento"] == "pagata"
    assert secondo is None
    assert terzo["prima_nota_cassa_id"] == primo["prima_nota_cassa_id"]
    assert _run(db["prima_nota_cassa"].count_documents({})) == 1
    assert [e[0] for e in eventi] == ["fattura.pagata"]


def test_fornitore_senza_metodo_resta_sospesa_con_alert_senza_movimento(db, eventi):
    _run(db["fornitori"].insert_one({"partita_iva": "12345678901"}))  # nessun metodo
    _run(db["invoices"].insert_one(_fattura()))

    result = _run(mod.auto_registra_prima_nota(db, _fattura(), ""))

    assert _run(db["prima_nota_cassa"].count_documents({})) == 0
    assert _run(db["prima_nota_banca"].count_documents({})) == 0
    fattura = _run(db["invoices"].find_one({"id": "FT-1"}))
    from app.services.stato_pagamento_fattura import e_pagata
    assert e_pagata(fattura) is False
    # §29: nessun ripiego su Cassa, nemmeno come suggerimento di stato.
    assert fattura["stato_finanziario"] == mod.STATO_SOSPESA_METODO_MANCANTE
    assert "cassa" not in fattura["stato_finanziario"]
    assert fattura["decisione_pagamento_richiesta"] is True
    assert fattura["provvisorio"] is True
    assert result["stato_finanziario"] == mod.STATO_SOSPESA_METODO_MANCANTE
    alert = _run(db["alerts"].find_one({"codice": "FAT_MP_NON_DEFINITO", "entita_id": "FT-1"}))
    assert alert is not None and alert["stato"] == "aperto"
    assert eventi == []
