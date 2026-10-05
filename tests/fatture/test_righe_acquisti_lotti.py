"""Righe acquisti → Lotti: la scelta dell'articolo conferma la riga, popola Lotti
ed è estesa alle righe con la stessa descrizione dello stesso fornitore."""
import asyncio

import pytest

from app.services import righe_acquisti_lotti as srv
from app.services.archivio_documenti_memoria import ArchivioDocumenti


def _run(c):
    return asyncio.new_event_loop().run_until_complete(c)


def _fattura(fid, piva, righe):
    return {
        "id": fid, "invoice_number": fid, "invoice_date": "2026-10-03", "supplier_name": "AP SRL",
        "supplier_vat": piva, "content_hash": "h" + fid,
        "linee": [{"numero_linea": str(i + 1), "descrizione": d, "prezzo_totale": "10.00",
                   "aliquota_iva": "10.00"} for i, d in enumerate(righe)],
    }


def _db():
    erp, lotti = ArchivioDocumenti("erp"), ArchivioDocumenti("lotti")
    _run(erp["invoices"].insert_one(_fattura("F1", "07489941216", ["PETTO DI POLLO A FETTE", "RANA LASAGNE"])))
    _run(erp["invoices"].insert_one(_fattura("F2", "07489941216", ["Petto di pollo  a fette"])))
    # Stessa descrizione ma altro fornitore: non si tocca.
    _run(erp["invoices"].insert_one(_fattura("F3", "99999999999", ["PETTO DI POLLO A FETTE"])))
    _run(lotti.lotti_fornitori.insert_one({"id": "L1", "prodotto_nome": "PETTO DI POLLO A FETTE"}))
    return erp, lotti


def test_assegna_prodotto_conferma_riga_popola_lotti_ed_estende():
    erp, lotti = _db()
    esito = _run(srv.assegna_prodotto(erp, lotti, "F1:1", "Petto di pollo", "Carni e Salumi", "titolare"))

    cl = esito["classificazione"]
    assert cl["stato"] == "CONFERMATA" and cl["natura"] == "ingrediente"
    assert cl["categoria"] == "Carni e Salumi" and cl["destinazione_operativa"] == "magazzino_lotti"
    # Nessuna regola impostata: conto e centro di costo restano vuoti, mai inventati.
    assert cl["conto"] is None and cl["centro_costo"] is None
    # Lotti: associazione confermata e lotto col nome canonico.
    mapping = _run(lotti.nome_mapping.find_one({"descrizione_key": "petto di pollo a fette"}))
    assert mapping["confermato"] is True and mapping["nome_canc"] == "Petto di pollo"
    assert _run(lotti.lotti_fornitori.find_one({"id": "L1"}))["nome_canonico"] == "Petto di pollo"
    # Estesa solo a F2 (stesso fornitore, stessa descrizione); non a F3 né alla riga 2.
    assert esito["righe_estese"] == 1
    salvate = {r["id"]: r for r in _run(erp["righe_acquisti_classificazioni"].find({}).to_list(None))}
    assert set(salvate) == {"F1:1", "F2:1"}
    assert salvate["F2:1"]["fonte"] == srv.FONTE_STESSA_DESCRIZIONE


def test_la_regola_per_categoria_compila_conto_e_centro_costo():
    erp, lotti = _db()
    _run(erp["centri_costo"].insert_one({"codice": "CDC-01", "nome": "Bar"}))
    conto = next(iter(srv.CONTI_UFFICIALI))
    _run(srv.salva_regola(erp, "Carni e Salumi", conto, "CDC-01", "titolare"))
    esito = _run(srv.assegna_prodotto(erp, lotti, "F1:1", "Petto di pollo", "Carni e Salumi", "titolare"))
    assert esito["classificazione"]["conto"] == conto
    assert esito["classificazione"]["centro_costo"] == "CDC-01"


def test_regola_con_conto_o_centro_inesistente_e_rifiutata():
    erp, _ = _db()
    with pytest.raises(srv.SceltaNonValida):
        _run(srv.salva_regola(erp, "Carni e Salumi", "99.99.99", None, "t"))
    with pytest.raises(srv.SceltaNonValida):
        _run(srv.salva_regola(erp, "Carni e Salumi", None, "CDC-XX", "t"))
    with pytest.raises(srv.SceltaNonValida):
        _run(srv.salva_regola(erp, "Categoria inventata", None, None, "t"))


def test_decisione_umana_gia_presa_non_si_sovrascrive_sulle_righe_estese():
    erp, lotti = _db()
    _run(srv.assegna_prodotto(erp, lotti, "F2:1", "Pollo intero", "Carni e Salumi", "titolare"))
    esito = _run(srv.assegna_prodotto(erp, lotti, "F1:1", "Petto di pollo", "Carni e Salumi", "titolare"))
    assert esito["righe_estese"] == 0
    f2 = _run(erp["righe_acquisti_classificazioni"].find_one({"id": "F2:1"}))
    assert f2["fonte"] == srv.FONTE_TITOLARE


def test_scelta_incompleta_o_riga_inesistente():
    erp, lotti = _db()
    with pytest.raises(srv.SceltaNonValida):
        _run(srv.assegna_prodotto(erp, lotti, "F1:1", "", "Carni e Salumi", "t"))
    with pytest.raises(srv.SceltaNonValida):
        _run(srv.assegna_prodotto(erp, lotti, "F1:1", "Pollo", "Boh", "t"))
    with pytest.raises(srv.SceltaNonValida):
        _run(srv.assegna_prodotto(erp, lotti, "F9:1", "Pollo", "Carni e Salumi", "t"))
