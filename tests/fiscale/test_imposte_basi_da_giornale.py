"""Audit 27/09/2026 (punto 2): basi IRES/IRAP dal libro giornale.

Prima: costi = ``total_amount`` (IVA compresa) di tutte le fatture, archiviate
comprese; ricavi = totale dei corrispettivi (cancellati compresi) / 1,10,
un'aliquota inventata. Ora costi e ricavi sono le righe economiche delle
scritture attive dell'anno, gia' al netto dell'IVA e con le note di credito.
"""
import asyncio

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.calcolo_imposte import CalcolatoreImposte, basi_imponibili_da_giornale


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _riga(conto, dare=0.0, avere=0.0):
    return {"conto_codice": conto, "dare": dare, "avere": avere}


def _db():
    db = ClientArchivioMemoria()["imposte-giornale"]
    _run(db["movimenti_contabili"].insert_many([
        # corrispettivo: ricavi 1000 (IVA 22% dall'XML, non 10%)
        {"id": "C1", "tipo": "corrispettivo", "anno": 2026, "data": "2026-02-01",
         "righe": [_riga("01.01.01", 1220), _riga("04.01.02", avere=1000), _riga("02.03.01", avere=220)]},
        # fattura: costo 300 al netto dell'IVA
        {"id": "F1", "tipo": "fattura_acquisto", "anno": 2026, "data": "2026-02-02",
         "righe": [_riga("05.01.01", 300), _riga("01.04.01", 66), _riga("02.01.01", avere=366)]},
        # nota di credito: riduce il costo di 50
        {"id": "N1", "tipo": "fattura_acquisto", "anno": 2026, "data": "2026-02-03",
         "righe": [_riga("05.01.01", avere=50), _riga("01.04.01", avere=11), _riga("02.01.01", 61)]},
        # TFR del personale (conto CEE scritto dal motore TFR)
        {"id": "T1", "tipo": "tfr", "anno": 2026, "data": "2026-02-28",
         "righe": [_riga("67.01.07.01", 40), _riga("29.01.01", avere=40)]},
        # scrittura cancellata: non conta
        {"id": "F-DEL", "tipo": "fattura_acquisto", "anno": 2026, "data": "2026-02-02", "deleted": True,
         "righe": [_riga("05.01.01", 300), _riga("01.04.01", 66), _riga("02.01.01", avere=366)]},
        # altro anno: non conta
        {"id": "F25", "tipo": "fattura_acquisto", "anno": 2025, "data": "2025-02-02",
         "righe": [_riga("05.01.01", 900), _riga("02.01.01", avere=900)]},
    ]))
    # Collezioni operative "sporche" che la vecchia logica sommava.
    _run(db["invoices"].insert_one({"id": "X", "status": "archived", "invoice_date": "2026-01-10",
                                     "total_amount": 50000}))
    _run(db["corrispettivi"].insert_one({"id": "Y", "status": "deleted", "data": "2026-01-10",
                                          "totale": 99000}))
    return db


def test_basi_dal_giornale_netto_iva_e_note_di_credito():
    basi = _run(basi_imponibili_da_giornale(_db(), 2026))
    assert basi["ricavi"] == 1000.0            # non 1220 / 1,10
    assert basi["costi"] == 290.0              # 300 - 50 + 40
    assert basi["costo_personale"] == 40.0
    assert basi["costi_per_codice"]["05.01.01"]["importo"] == 250.0


def test_imposte_usano_le_basi_del_giornale():
    risultato = _run(CalcolatoreImposte("campania").calcola_imposte_da_db(_db(), 2026))
    assert risultato.ricavi == 1000.0 and risultato.costi == 290.0
    assert risultato.utile_civilistico == 710.0
    assert risultato.avvisi == []


def test_giornale_vuoto_non_e_un_utile_zero():
    db = ClientArchivioMemoria()["imposte-vuoto"]
    risultato = _run(CalcolatoreImposte().calcola_imposte_da_db(db, 2026))
    assert risultato.utile_civilistico == 0
    assert risultato.avvisi and "vuoto" in risultato.avvisi[0]
