"""Audit 27/09/2026 (punto 1): i saldi del Piano dei Conti vengono dal libro
giornale, non da un secondo calcolo sulle collezioni operative.

Prima ``_calcola_saldi_piano_conti`` risommava ``invoices`` (555 archiviate
doppie comprese), i corrispettivi ``deleted``, ``prezzo_totale`` stringa e
campi che nessun F24 ha. Qui si prova che contano solo le righe delle
scritture attive di ``movimenti_contabili``, convertite sul CEE.
"""
import asyncio

from app.routers.accounting import contabilita_avanzata as ca
from app.routers.accounting import piano_conti as pc
from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.mapping_piano_conti import saldi_in_cee


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _riga(conto, dare=0.0, avere=0.0):
    return {"conto_codice": conto, "dare": dare, "avere": avere}


def _seed(db):
    scritture = [
        # 2025: una fattura (costo 100 + IVA 22 / debito 122)
        {"id": "F25", "tipo": "fattura_acquisto", "anno": 2025, "data": "2025-06-01",
         "righe": [_riga("05.01.01", 100), _riga("01.04.01", 22), _riga("02.01.01", avere=122)]},
        # 2026: corrispettivo (cassa 110 / ricavi 100 + IVA 10)
        {"id": "C26", "tipo": "corrispettivo", "anno": 2026, "data": "2026-03-01",
         "righe": [_riga("01.01.01", 110), _riga("04.01.02", avere=100), _riga("02.03.01", avere=10)]},
        # 2026: fattura (costo 50 + IVA 11 / debito 61)
        {"id": "F26", "tipo": "fattura_acquisto", "anno": 2026, "data": "2026-04-01",
         "righe": [_riga("05.01.01", 50), _riga("01.04.01", 11), _riga("02.01.01", avere=61)]},
        # 2026: doppione cancellato — non deve contare
        {"id": "F26-DUP", "tipo": "fattura_acquisto", "anno": 2026, "data": "2026-04-01",
         "deleted": True,
         "righe": [_riga("05.01.01", 50), _riga("01.04.01", 11), _riga("02.01.01", avere=61)]},
    ]
    _run(db["movimenti_contabili"].insert_many(scritture))
    # Collezioni operative "sporche": non devono piu' pesare sui saldi.
    _run(db["invoices"].insert_many([
        {"id": "X1", "status": "archived", "invoice_date": "2026-04-01",
         "total_amount": 9999, "imponibile": 9000, "iva_detraibile": 999,
         "linee": [{"descrizione": "x", "prezzo_totale": "9000.00"}]},
    ]))
    _run(db["corrispettivi"].insert_one(
        {"id": "CX", "status": "deleted", "data": "2026-03-02", "totale": 5000,
         "totale_imponibile": 4545, "totale_iva": 455}))
    _run(db["f24_unificato"].insert_one({"id": "F24X", "totale": 7777, "anno": 2026}))


def test_saldi_anno_dal_giornale_senza_collezioni_operative():
    db = ClientArchivioMemoria()["saldi-giornale"]
    _seed(db)
    saldi = _run(pc._calcola_saldi_piano_conti(db, "2026"))
    cee = saldi_in_cee(saldi)
    # Conto economico: solo il 2026
    assert cee["55.01.07"] == 50.0          # acquisti merci 2026
    assert cee["47.01.03"] == 100.0         # ricavi 2026
    # Stato patrimoniale: cumulativo al 31/12/2026
    assert cee["33.03.01"] == 183.0         # debiti fornitori 122 + 61
    assert cee["19.03.03"] == 110.0         # cassa
    # Risultato dell'esercizio 2026 = 100 - 50 sul netto
    assert saldi["03.03.01"] == 50.0
    # Nulla dalle collezioni operative (fattura archiviata, corrispettivo
    # cancellato, F24): altrimenti comparirebbero 9000, 4545, 7777.
    assert all(abs(v) < 4000 for v in cee.values())


def test_saldi_senza_anno_sono_tutto_il_registro():
    db = ClientArchivioMemoria()["saldi-giornale-tutto"]
    _seed(db)
    cee = saldi_in_cee(_run(pc._calcola_saldi_piano_conti(db, None)))
    assert cee["55.01.07"] == 150.0
    assert cee["33.03.01"] == 183.0


def test_chiusura_esercizio_non_azzera_il_conto_economico_dell_anno():
    db = ClientArchivioMemoria()["saldi-chiusura"]
    _seed(db)
    _run(db["movimenti_contabili"].insert_one({
        "id": "CH26", "tipo": "chiusura_esercizio", "anno": 2026, "data": "2026-12-31",
        "righe": [_riga("04.01.02", 100), _riga("05.01.01", avere=50), _riga("03.03.01", avere=50)],
    }))
    saldi = _run(pc._calcola_saldi_piano_conti(db, "2026"))
    cee = saldi_in_cee(saldi)
    assert cee["55.01.07"] == 50.0 and cee["47.01.03"] == 100.0
    assert saldi["03.03.01"] == 50.0  # una volta sola, non 100


def test_bilancio_dettagliato_accetta_e_passa_anno(monkeypatch):
    db = ClientArchivioMemoria()["bilancio-dettagliato-anno"]
    _seed(db)
    monkeypatch.setattr(ca.Database, "get_db", staticmethod(lambda: db))
    del_2026 = _run(ca.get_bilancio_dettagliato(anno=2026))
    tutto = _run(ca.get_bilancio_dettagliato())
    assert del_2026["anno"] == 2026
    assert del_2026["conto_economico"]["costi"]["totale"] == 50.0
    assert tutto["conto_economico"]["costi"]["totale"] == 150.0
