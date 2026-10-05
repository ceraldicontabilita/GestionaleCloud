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


def test_proposta_dal_nome_conosciuto_e_consumo():
    erp, lotti = _db()
    _run(erp["invoices"].insert_one(_fattura("F4", "07489941216", ["SHOPPERS SOLE 365 BIOCOMP.", "VINO ROSSO XYZ"])))
    # Il nome dice la categoria con certezza: proposta, non scritta.
    p = _run(srv.proponi(erp, lotti, "F1:1"))
    assert p["categoria"] == "Carni e Salumi" and p["natura"] == "ingrediente" and p["non_cespite"] is False
    assert p["fonte"] == "dal_nome"
    # Materiale di consumo: non alimentare e non cespite, da confermare.
    c = _run(srv.proponi(erp, lotti, "F4:1"))
    assert c["alimentare"] is False and c["non_cespite"] is True and c["natura"] == "altro"
    # Nessuna fonte: tutto vuoto, mai inventato.
    n = _run(srv.proponi(erp, lotti, "F4:2"))
    assert n["categoria"] is None and n["nome_canc"] is None and n["non_cespite"] is False
    assert _run(erp["righe_acquisti_classificazioni"].find({}).to_list(None)) == []
    # Un articolo già confermato in Lotti torna come tale.
    _run(srv.assegna_prodotto(erp, lotti, "F1:1", "Petto di pollo", "Carni e Salumi", "t"))
    assert _run(srv.proponi(erp, lotti, "F2:1"))["fonte"] == "lotti_confermato"


def test_correzioni_dai_campi_e_flag_non_cespite_sulle_righe_uguali():
    erp, lotti = _db()
    conto = next(iter(srv.CONTI_UFFICIALI))
    esito = _run(srv.assegna_prodotto(
        erp, lotti, "F1:1", "Petto di pollo", "Carni e Salumi", "t",
        natura="servizio", conto=conto, destinazione_operativa="", non_cespite=True,
    ))
    cl = esito["classificazione"]
    assert cl["natura"] == "servizio" and cl["conto"] == conto and cl["non_cespite"] is True
    assert cl["destinazione_operativa"] is None  # vuoto scelto dal titolare: non si riempie
    esclusi = _run(srv.chiavi_non_cespite(erp))
    assert esclusi == {"F1": {"petto di pollo a fette"}, "F2": {"petto di pollo a fette"}}
    assert srv.esclusa_dai_cespiti(esclusi, "F1", "PETTO DI POLLO A FETTE")
    assert not srv.esclusa_dai_cespiti(esclusi, "F1", "RANA LASAGNE")
    with pytest.raises(srv.SceltaNonValida):
        _run(srv.assegna_prodotto(erp, lotti, "F1:1", "Pollo", "Carni e Salumi", "t",
                                  natura="cespite", non_cespite=True))


def test_riga_non_cespite_non_genera_il_cespite_dall_handler():
    from app.handlers.cespiti import handler_auto_cespite_da_fattura

    erp, lotti = _db()
    _run(erp["invoices"].insert_one({
        "id": "F5", "invoice_number": "F5", "invoice_date": "2026-10-03", "supplier_vat": "07489941216",
        "supplier_name": "AP SRL", "content_hash": "h5",
        "linee": [{"numero_linea": "1", "descrizione": "FORNO ELETTRICO PROFESSIONALE", "prezzo_totale": "900.00",
                   "aliquota_iva": "22.00"}],
    }))
    payload = {"fattura_id": "F5", "data_documento": "2026-10-03", "fornitore_ragione_sociale": "AP SRL",
               "tipo_documento": "TD01", "righe_linee": [
                   {"descrizione": "FORNO ELETTRICO PROFESSIONALE", "prezzo_totale": 900.0}]}
    _run(srv.assegna_prodotto(erp, lotti, "F5:1", "Forno", "Non Alimentare", "t",
                              alimentare=False, non_cespite=True))
    esito = _run(handler_auto_cespite_da_fattura(payload, erp))
    assert esito.get("skipped") and _run(erp["cespiti"].find({}).to_list(None)) == []
    # Senza il flag lo stesso payload crea il cespite.
    erp2 = ArchivioDocumenti("erp2")
    esito2 = _run(handler_auto_cespite_da_fattura(payload, erp2))
    assert len(esito2["cespiti_creati"]) == 1


def test_riga_non_cespite_non_compare_nello_scan_manuale(monkeypatch):
    from app.routers import cespiti as mod

    erp, lotti = _db()
    _run(erp["invoices"].insert_one({
        "id": "F6", "invoice_number": "F6", "invoice_date": "2026-10-03", "supplier_vat": "07489941216",
        "supplier_name": "AP SRL", "total_amount": 900.0, "content_hash": "h6",
        "linee": [{"numero_linea": "1", "descrizione": "FORNO ELETTRICO PROFESSIONALE", "prezzo_totale": "900.00",
                   "aliquota_iva": "22.00"}],
    }))
    monkeypatch.setattr(mod.Database, "get_db", staticmethod(lambda: erp))
    prima = _run(mod.scan_fatture_per_cespiti(soglia_valore=516.46, dry_run=True))
    assert prima["num_potenziali_cespiti"] == 1
    _run(srv.assegna_prodotto(erp, lotti, "F6:1", "Forno", "Non Alimentare", "t",
                              alimentare=False, non_cespite=True))
    dopo = _run(mod.scan_fatture_per_cespiti(soglia_valore=516.46, dry_run=True))
    assert dopo["num_potenziali_cespiti"] == 0
