"""Mapping tassonomia bancaria dell'estratto conto ("Categoria -
Sottocategoria" dal CSV) sulle categorie canoniche di Prima Nota (richiesta
utente 17/07/2026). Non distruttivo: il nome canonico è un campo calcolato
(`categoria_canonica`), la riga di estratto conto resta immutabile."""
from app.routers.bank.estratto_conto import mappa_categoria_ec


def test_deposito_contanti_e_il_versamento():
    assert mappa_categoria_ec("Ricavi - Deposito contanti") == "Versamento Banca"


def test_pagamenti_fornitori_e_utenze_sono_fatture():
    for cat in [
        "Fornitori - Generico",
        "Fornitori - Materie prime, beni e servizi",
        "Utenze - Acqua, luce e gas",
        "Utenze - Internet e spese telefoniche",
        "Servizi - Spese per professionisti",
        "Servizi - Noleggi",
        "Assicurazione - Generico",
        "Altre passività - Leasing",
    ]:
        assert mappa_categoria_ec(cat) == "Fatture", cat


def test_altre_mappature():
    assert mappa_categoria_ec("Operazioni Finanziarie - Commissioni") == "Commissioni bancarie"
    assert mappa_categoria_ec("Tasse - Imposte e contributi") == "F24"
    assert mappa_categoria_ec("Risorse Umane - Salari e stipendi") == "Stipendi"
    assert mappa_categoria_ec("Ricavi - Generico") == "Incasso cliente"
    assert mappa_categoria_ec("Altre passività - Mutui") == "Altro"
    assert mappa_categoria_ec("Intercompany in entrata - Prestiti a soci in entrata") == "Altro"


def test_non_mappate_restano_originali():
    assert mappa_categoria_ec("Movimento bancario") is None
    assert mappa_categoria_ec("") is None
    assert mappa_categoria_ec(None) is None
