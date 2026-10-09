"""Mapping tassonomia bancaria dell'estratto conto ("Categoria -
Sottocategoria" dal CSV) sulle categorie canoniche di Prima Nota (richiesta
utente 17/07/2026). Non distruttivo: il nome canonico è un campo calcolato
(`categoria_canonica`), la riga di estratto conto resta immutabile."""
from app.routers.bank.estratto_conto import mappa_categoria_ec


def test_deposito_contanti_e_il_versamento():
    assert mappa_categoria_ec("Ricavi - Deposito contanti") == "Versamento Banca"


def test_pagamenti_fornitori_sono_fatture():
    for cat in [
        "Fornitori - Generico",
        "Fornitori - Materie prime, beni e servizi",
        "Servizi - Spese per professionisti",
        "Servizi - Noleggi",
        "Assicurazione - Generico",
        "Altre passività - Leasing",
    ]:
        assert mappa_categoria_ec(cat) == "Fatture", cat


def test_utenze_hanno_voce_propria():
    """Regola utente 17/07/2026: 'pagamento utenze' è un'operazione a sé."""
    assert mappa_categoria_ec("Utenze - Acqua, luce e gas") == "Utenze"
    assert mappa_categoria_ec("Utenze - Internet e spese telefoniche") == "Utenze"
    assert mappa_categoria_ec(None, "Pagamento preautorizzato utenza - Aruba Spa") == "Utenze"


def test_paypal_riconosciuto_dalla_causale():
    """Regola utente 17/07/2026: la banca classifica PayPal in 3 modi
    diversi (Servizi, Utenze, niente) — la causale vince sempre: categoria
    sintetica 'Pagamento PayPal', il dettaglio resta nella descrizione."""
    assert mappa_categoria_ec("Servizi - Spese per servizi online",
                              "ADD. PAGAM. PAYPAL EUROPE") == "Pagamento PayPal"
    assert mappa_categoria_ec("Utenze - Acqua, luce e gas",
                              "PAYPAL EUROPE S.A.R.L.") == "Pagamento PayPal"
    assert mappa_categoria_ec(None, "Bonifico bancario sul conto PayPal - ID: X") == "Pagamento PayPal"


def test_causale_versamento_prelievo_vince_sulla_tassonomia():
    assert mappa_categoria_ec("Ricavi - Generico", "VERS. CONTANTI - VVVVV") == "Versamento Banca"
    assert mappa_categoria_ec(None, "PRELIEVO CONTANTI SPORTELLO") == "Prelevamento Banca"


def test_altre_mappature():
    assert mappa_categoria_ec("Operazioni Finanziarie - Commissioni") == "Commissioni bancarie"
    assert mappa_categoria_ec("Tasse - Imposte e contributi") == "F24"
    assert mappa_categoria_ec("Risorse Umane - Salari e stipendi") == "Stipendi"
    assert mappa_categoria_ec("Ricavi - Generico") == "Rimborso"
    assert mappa_categoria_ec("Ricavi - Rimborsi diversi") == "Rimborso"
    assert mappa_categoria_ec("Altre passività - Mutui") == "Altro"
    assert mappa_categoria_ec("Intercompany in entrata - Prestiti a soci in entrata") == "Altro"


def test_non_mappate_restano_originali():
    assert mappa_categoria_ec("Movimento bancario") is None
    assert mappa_categoria_ec("") is None
    assert mappa_categoria_ec(None) is None
