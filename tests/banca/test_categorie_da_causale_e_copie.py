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
    # Le sigle del vecchio archivio 2026 (28/09/2026).
    ("COMM. BON. TELEMATICO SCT", "Commissioni bancarie"),
    ("COMM.FISSA SU OPERAZIONE", "Commissioni bancarie"),
    ("RILASCIO CARNET ASSEGNI", "Commissioni bancarie"),
    ("IMP. BOLLO C/C", "Commissioni bancarie"),
    ("CANONE CARTA DEBITO", "Commissioni bancarie"),
    ("COMPETENZE", "Commissioni bancarie"),
    # Decisioni del titolare del 28/09/2026.
    ("BOLL.CBILL AGENZIA DELLE ENTRATE - R CBILL 180071115560092791", "Rateizzazioni AdE"),
    ("BOLL.CBILL REGIONE CAMPANIA CBILL 301000000084494886", "Tassa automobilistica"),
    ("SPESA CON CARTA DI CREDITO NEXI", "Addebito carta di credito"),
    # Restano senza categoria: non si indovina.
    ("BONIFICO COMPETENZE AGOSTO ROSSI", None),
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


def test_l_abbinamento_gia_fatto_decide_la_categoria():
    from app.services.categorizzazione_movimenti import (
        backfill_categorie_banca, categoria_dal_collegamento)

    u = {"tipo": "uscita", "importo": 10.0}
    assert categoria_dal_collegamento({**u, "fattura_id": "f1"}) == "Fatture"
    assert categoria_dal_collegamento({"importo": -10.0, "fattura_ids": ["f1", "f2"]}) == "Fatture"
    assert categoria_dal_collegamento({**u, "dipendente_id": "d1"}) == "Stipendi"
    # Collegato a tutti e due, o a nessuno, o un'entrata: non si decide qui.
    assert categoria_dal_collegamento({**u, "fattura_id": "f1", "dipendente_id": "d1"}) is None
    assert categoria_dal_collegamento(u) is None
    assert categoria_dal_collegamento({"tipo": "entrata", "importo": 10.0, "fattura_id": "f1"}) is None

    db = ClientArchivioMemoria()["collegati"]
    _run(db["estratto_conto_movimenti"].insert_many([
        {"id": "m-fatt", "data": "2026-05-02", "importo": 120.0, "tipo": "uscita",
         "descrizione": "VS.DISP. RIF. MB0B FAVORE ROSSI SRL", "fattura_id": "inv-1"},
        {"id": "m-dip", "data": "2026-05-03", "importo": 900.0, "tipo": "uscita",
         "descrizione": "VS.DISP. RIF. MB0B FAVORE MARIO ROSSI", "dipendente_id": "dip-1"},
        {"id": "m-nulla", "data": "2026-05-04", "importo": 50.0, "tipo": "uscita",
         "descrizione": "VS.DISP. RIF. MB0B FAVORE SCONOSCIUTO"},
    ]))
    esito = _run(backfill_categorie_banca(db, anno=2026, con_stipendi=False))
    righe = {r["id"]: r for r in _run(db["estratto_conto_movimenti"].find({}).to_list(10))}
    assert righe["m-fatt"]["categoria"] == "Fatture"
    assert righe["m-dip"]["categoria"] == "Stipendi"
    assert not righe["m-nulla"].get("categoria")
    assert esito["per_categoria"]["Fatture"] == 1 and esito["per_categoria"]["Stipendi"] == 1


@pytest.mark.parametrize("mov,attesa", [
    ({"tipo": "entrata", "importo": 1137.41, "descrizione": "BON.DA R-STORE S.P.A. RIMBORSO"}, "Rimborso"),
    ({"tipo": "entrata", "importo": 404.0,
      "descrizione": "BON.DA L. MORELLI E FIGLIO S.R.L. - X RESTITUZIONE BONIFICO ERRATO"}, "Rimborso"),
    ({"tipo": "entrata", "importo": 59.48,
      "descrizione": "BON.DA AMAZON PAYMENTS EUROPE S.C.A. AMAZON - 171-0500632"}, "Rimborso"),
    ({"tipo": "entrata", "importo": 45.0, "descrizione": "BON.DA BRUNO ORIETTA - ACCONTO TORTA DI COMPLEANNO"},
     "Acconti clienti"),
    # In uscita «RIMBORSO» e' il contrario: lo restituiamo noi.
    ({"tipo": "uscita", "importo": 50.0, "descrizione": "VS.DISP. FAVORE ROSSI RIMBORSO"}, None),
    ({"importo": -50.0, "descrizione": "BONIFICO TORTA"}, None),
    ({"tipo": "entrata", "importo": 10.0, "descrizione": "RIMBORSO TORTA ANNULLATA"}, None),
])
def test_entrate_rimborso_e_acconto(mov, attesa):
    from app.services.categorizzazione_movimenti import categoria_entrata

    assert categoria_entrata(mov) == attesa


def test_il_socio_gia_riconosciuto_e_finanziamento_soci():
    from app.services.categorizzazione_movimenti import categoria_dal_collegamento

    assert categoria_dal_collegamento(
        {"tipo": "entrata", "importo": 20000.0, "socio_id": "socio-1"}) == "Finanziamento soci"


def test_la_regola_imparata_decide_il_risarcimento():
    regole = [{"id": "r1", "pattern": "CHP LEGAL", "entita_tipo": "categoria",
               "entita_nome": "Risarcimenti e proventi straordinari",
               "categoria": "Risarcimenti e proventi straordinari"}]
    esito = categorizza_movimento_bancario(
        "BON.DA CHP LEGAL SRL CHP-25487-STUDIO ASSOCIA TO PRISCO", regole=regole)
    assert esito.categoria == "Risarcimenti e proventi straordinari"
