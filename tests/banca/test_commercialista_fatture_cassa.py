"""Audit 27/09/2026 (punto 13): «fatture pagate per cassa» dalla Prima Nota.

L'endpoint filtrava ``invoices`` su ``metodo_pagamento``/``payment_method``/
``modalita_pagamento``, campi quasi assenti: l'elenco era vuoto. Ora le
fatture pagate in cassa sono quelle con una riga ATTIVA di Prima Nota Cassa
in uscita collegata per ``fattura_id``, esclusi i ripieghi senza prova.
"""
import asyncio

from app.routers import commercialista as mod
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _db():
    db = ClientArchivioMemoria()["commercialista-cassa"]
    _run(db["invoices"].insert_many([
        {"id": "F1", "invoice_number": "1/A", "invoice_date": "2026-03-02",
         "supplier_name": "Forno Srl", "total_amount": 122.0},
        {"id": "F2", "invoice_number": "2/A", "invoice_date": "2026-02-25",
         "supplier_name": "Latte Srl", "total_amount": 50.0},
        {"id": "F3", "invoice_number": "3/A", "invoice_date": "2026-03-05",
         "supplier_name": "Ripiego Srl", "total_amount": 80.0},
        {"id": "F4", "invoice_number": "4/A", "invoice_date": "2026-03-06",
         "supplier_name": "Copia Srl", "total_amount": 70.0, "status": "archived"},
        # metodo scritto sulla fattura ma nessun pagamento in cassa: non conta
        {"id": "F5", "invoice_number": "5/A", "invoice_date": "2026-03-07",
         "supplier_name": "Dichiarata Srl", "total_amount": 30.0, "metodo_pagamento": "contanti"},
    ]))
    _run(db["prima_nota_cassa"].insert_many([
        {"id": "C1", "data": "2026-03-10", "tipo": "uscita", "importo": 100.0, "fattura_id": "F1"},
        {"id": "C2", "data": "2026-03-12", "tipo": "uscita", "importo": 22.0, "fattura_id": "F1"},
        # fattura di febbraio pagata in cassa a marzo: conta a marzo
        {"id": "C3", "data": "2026-03-01", "tipo": "uscita", "importo": 50.0, "fattura_id": "F2"},
        # cassa d'ufficio senza prova: non e' un pagamento
        {"id": "C4", "data": "2026-03-05", "tipo": "uscita", "importo": 80.0, "fattura_id": "F3",
         "source": "metodo_fornitore_assente_provvisorio"},
        # riga cancellata e fattura archiviata: fuori
        {"id": "C5", "data": "2026-03-06", "tipo": "uscita", "importo": 70.0, "fattura_id": "F4"},
        {"id": "C6", "data": "2026-03-06", "tipo": "uscita", "importo": 10.0, "fattura_id": "F1",
         "status": "deleted"},
        # altro mese
        {"id": "C7", "data": "2026-04-01", "tipo": "uscita", "importo": 5.0, "fattura_id": "F1"},
    ]))
    return db


def test_fatture_cassa_dalle_righe_di_prima_nota(monkeypatch):
    db = _db()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    esito = _run(mod.get_fatture_pagate_cassa(2026, 3))
    per_id = {f["id"]: f for f in esito["fatture"]}
    assert set(per_id) == {"F1", "F2"}
    assert per_id["F1"]["importo_pagato_cassa"] == 122.0
    assert per_id["F1"]["data_pagamento"] == "2026-03-12"
    assert per_id["F2"]["importo_pagato_cassa"] == 50.0
    assert esito["totale_fatture"] == 2
    assert esito["totale_importo"] == 172.0
    assert esito["fonte"] == "prima_nota_cassa"


def test_anno_intero(monkeypatch):
    db = _db()
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: db))
    esito = _run(mod.get_fatture_pagate_cassa(2026, 0))
    per_id = {f["id"]: f for f in esito["fatture"]}
    assert per_id["F1"]["importo_pagato_cassa"] == 127.0
