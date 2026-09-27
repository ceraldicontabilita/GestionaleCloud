"""Movimenti banca senza categoria: dalla causale della banca o dalla copia.

27/09/2026: 1.416 movimenti 2026 senza categoria, quasi tutti del vecchio
archivio, che scrive le causali senza la categoria della banca. Il banner di
Prima Nota li contava come «da classificare» anche quando la causale diceva
gia' tutto (accrediti POS, assegni, versamenti, rate del mutuo).
"""
import asyncio

import pytest

from app.services.archivio_documenti_memoria import ClientArchivioMemoria
from app.services.categorizzazione_movimenti import categorizza_movimento_bancario
from app.services.doppioni_estratto_conto import eredita_categorie_da_copie


@pytest.mark.parametrize("causale,attesa", [
    ("NUMIA-INTER DEL 30/08/26 PDV 3757283/00012 CERALDI CAFFE' NA", "Corrispettivi POS"),
    ("INCAS. TRAMITE P.O.S - NUMIA-PGBNT DEL 31/12/25 PDV 3757283/00012", "Corrispettivi POS"),
    ("INC.POS CARTE CREDIT - REMUNERAZIONE DCC 03/26", "Corrispettivi POS"),
    ("REMUNERAZIONE DCC 03/26", "Corrispettivi POS"),
    ("VOSTRO ASSEGNO N. 0208770635", "Assegni"),
    ("PRELIEVO ASSEGNO - DM 02008 CRA: 26265800123405 NUM: 0208769486", "Assegni"),
    ("VERS. CONTANTI - VVVVV", "Versamento Banca"),
    ("VERSAMENTO CONTANTI", "Versamento Banca"),
    ("MUTUO N.1788 4851906 RATA 24/06/2026", "Rata mutuo"),
    ("RIMBORSO FINANZ. - MUTUO N.1788 4851906 RATA 24/09/2026", "Rata mutuo"),
    ("SDD CORE: 49RJ2252ASLM4 PAYPAL EUROPE", "Pagamento PayPal"),
    ("RIF.MBVT02317394 COMM.BON. TELEMATICO SCT/ IST", "Commissioni bancarie"),
    ("COMMISSIONI - Comm.sdd: 49RJ2252ASLM4 PAYPAL", "Commissioni bancarie"),
    # Restano senza categoria: non si indovina.
    ("STORNO VERS. CONTANTI", None),
    ("FATTURA NUMIA N. 123", None),
    ("VS.DISP. RIF. MB0B39331321/90553561 FAVORE GUARINO GIULIANO", None),
    ("SDD CORE: PK)K,TLYRBPN8JWYCYKCMKCV(58MO6 AMAZON PAYMENTS", None),
])
def test_categoria_dalla_causale(causale, attesa):
    assert categorizza_movimento_bancario(causale).categoria == attesa


def _run(coro):
    return asyncio.run(coro)


def test_la_copia_senza_categoria_prende_quella_del_csv():
    db = ClientArchivioMemoria()["copie"]
    _run(db["estratto_conto_movimenti"].insert_many([
        {"id": "legacy", "data": "2026-03-10", "importo": 43.86, "tipo": "uscita",
         "banca": "Banco BPM", "descrizione": "SDD CORE: 3F3811A21532878 FASTWEB SPA", "fonte": "legacy"},
        {"id": "csv", "data": "2026-03-10", "importo": 43.86, "tipo": "uscita", "banca": "Banco BPM",
         "descrizione_originale": "ADDEBITO DIRETTO SDD - SDD CORE: 3F3811A21532878 FASTWEB SpA",
         "categoria": "Utenze - Internet e spese telefoniche", "source_filename": "export.csv"},
    ]))
    esito = _run(eredita_categorie_da_copie(db))
    riga = _run(db["estratto_conto_movimenti"].find_one({"id": "legacy"}))
    assert esito["ereditate"] == 1
    assert riga["categoria"] == "Utenze - Internet e spese telefoniche"
    assert riga["categoria_ereditata_da"] == "csv"


def test_due_righe_dello_stesso_export_non_si_passano_la_categoria():
    db = ClientArchivioMemoria()["stesso"]
    _run(db["estratto_conto_movimenti"].insert_many([
        {"id": "a", "data": "2026-03-10", "importo": 100.0, "tipo": "uscita", "banca": "Banco BPM",
         "descrizione": "OPERAZIONE A", "source_filename": "export.csv"},
        {"id": "b", "data": "2026-03-10", "importo": 100.0, "tipo": "uscita", "banca": "Banco BPM",
         "descrizione": "OPERAZIONE B", "categoria": "Fatture", "source_filename": "export.csv"},
    ]))
    assert _run(eredita_categorie_da_copie(db))["ereditate"] == 0
    assert not _run(db["estratto_conto_movimenti"].find_one({"id": "a"})).get("categoria")
