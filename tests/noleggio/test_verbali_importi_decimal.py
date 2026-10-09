"""Importi dei verbali: «uguale» si decide in centesimi interi, mai con un float.

`_select_document_amount` confronta le fonti in centesimi (`amount_to_cents`),
il finder rifiuta un importo non positivo in centesimi e decide al centesimo,
la correzione a mano salva `importo` e `importo_centesimi` dal Decimal.
"""
import asyncio

import pytest
from fastapi import HTTPException

from app.services import verbali_document_import as vdi
from app.services import verbali_pagamento_finder as finder
from app.services.archivio_documenti_memoria import ClientArchivioMemoria


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_uguale_in_centesimi_non_in_float():
    # 0.1 + 0.2 != 0.3 in float: in centesimi sono 30 e 30, nessun conflitto
    importo, fonte, conflitto = vdi._select_document_amount({"importo_ridotto": 0.1 + 0.2}, {}, "Importo € 0,30")
    assert (importo, fonte, conflitto) == (0.3, "pdf_testo", False)


def test_il_conflitto_x100_si_riconosce_in_centesimi():
    importo, fonte, conflitto = vdi._select_document_amount({"importo_ridotto": 5164}, {}, "Totale € 51,64")
    assert (importo, fonte, conflitto) == (51.64, "pdf_testo_conflitto_ocr_x100", True)
    importo, fonte, conflitto = vdi._select_document_amount({"importo_ridotto": 25.82}, {"importo": "25,82"}, "")
    assert (importo, fonte, conflitto) == (25.82, "parser_pagopa", False)


def test_una_differenza_di_un_centesimo_e_un_conflitto():
    importo, fonte, conflitto = vdi._select_document_amount({"importo_ridotto": 25.83}, {"importo": 25.82}, "")
    assert (importo, fonte, conflitto) == (25.82, "parser_pagopa", True)


def test_lettura_di_stringhe_italiane_e_centesimi():
    assert vdi._float_or_none("1.234,56") == 1234.56
    assert vdi._float_or_none("€ 47,50") == 47.5
    assert vdi._float_or_none("abc") is None
    assert vdi._extract_amount("Importo da pagare € 1.234,56") == 1234.56


def test_il_finder_rifiuta_importo_non_positivo_e_decide_al_centesimo():
    db = ClientArchivioMemoria()["verbali_finder"]
    verbale = {"numero_verbale": "A1", "data_verbale": "2026-03-01"}
    assert _run(finder._cerca_in_estratto_conto(db, None, "A1", "GX037HJ", "0,00", verbale)) is None
    assert _run(finder._cerca_in_estratto_conto(db, None, "A1", "GX037HJ", None, verbale)) is None
    _run(db["estratto_conto_movimenti"].insert_one({
        "id": "m-giusto", "data": "2026-03-10", "importo": -120.51, "tipo": "uscita",
        "descrizione": "PAGOPA VERBALE A1"}))
    _run(db["estratto_conto_movimenti"].insert_one({
        "id": "m-vicino", "data": "2026-03-10", "importo": -120.52, "tipo": "uscita",
        "descrizione": "PAGOPA VERBALE A1"}))
    esito = _run(finder._cerca_in_estratto_conto(db, None, "A1", "GX037HJ", "120,51", verbale))
    assert esito["fonte"] == "estratto_conto" and esito["movimento_id"] == "m-giusto"
    # un centesimo in piu' non e' lo stesso importo
    assert _run(finder._cerca_in_estratto_conto(db, None, "A1", "GX037HJ", 120.53, verbale)) is None


def test_la_correzione_a_mano_salva_centesimi_dal_decimal(monkeypatch):
    from app.database import Database
    from app.routers import verbali_noleggio as rotta

    db = ClientArchivioMemoria()["verbali_correzione"]
    _run(db["verbali_noleggio"].insert_one({"id": "v1", "numero_verbale": "A1", "importo": 10.0}))
    monkeypatch.setattr(Database, "get_db", staticmethod(lambda: db))
    admin = {"email": "titolare@test"}

    esito = _run(rotta.correggi_importo_verbale("A1", {"importo": "12,34"}, admin))
    assert esito["importo"] == 12.34
    v = _run(db["verbali_noleggio"].find_one({"id": "v1"}, {"_id": 0}))
    assert v["importo"] == 12.34 and v["importo_centesimi"] == 1234 and v["importo_precedente"] == 10.0
    # La conferma dell'operatore rende l'importo operativo (riconciliazione col pagamento).
    assert v["importo_verificato"] is True and v["importo_stato"] == "CONFERMATO_OPERATORE"

    with pytest.raises(HTTPException) as exc:
        _run(rotta.correggi_importo_verbale("A1", {"importo": "abc"}, admin))
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        _run(rotta.correggi_importo_verbale("A1", {"importo": 0}, admin))
    assert exc.value.status_code == 400


def test_data_violazione_in_forma_italiana_diventa_iso():
    from app.services.verbali_evidence import data_ora_evento_verbale, data_violazione_verbale

    assert data_violazione_verbale({"data_violazione": "01/08/2026"}) == "2026-08-01"
    assert data_violazione_verbale({"data_violazione": "2026-08-01"}) == "2026-08-01"
    assert data_ora_evento_verbale({"data_violazione": "01/08/2026", "ora_violazione": "16:15"})[0] == "2026-08-01T16:15"
