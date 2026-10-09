"""Prima Nota Banca non e' una copia dell'estratto conto.

Regola dell'utente (07/08/2026): un pagamento entra in Prima Nota quando si sa
A COSA si riferisce — fattura, cedolino, F24, assegno, trasferimento POS.
Finche' non lo si sa resta nella coda da riconciliare.

C'e' pero' un confine da non superare, ed e' il motivo per cui questi test
esistono: le competenze bancarie e i prelievi al bancomat un documento non ce
l'hanno e non possono averlo. Escluderli non renderebbe la Prima Nota piu'
pulita, la renderebbe SBAGLIATA — quel denaro dal conto e' uscito davvero.
"""
import pytest

from app.routers.bank.estratto_conto import mappa_categoria_ec
from app.routers.prima_nota_module.common import (
    CATEGORIE_SENZA_DOCUMENTO,
    entra_in_prima_nota,
)


# --- Chi entra senza documento --------------------------------------------

@pytest.mark.parametrize("categoria", [
    "Commissioni bancarie",
    "Prelevamento Banca",
])
def test_i_movimenti_della_banca_entrano_lo_stesso(categoria):
    """Competenze, bolli, prelievi: non esiste una fattura da aspettare."""
    assert entra_in_prima_nota(categoria) is True


@pytest.mark.parametrize("categoria", [
    "Fatture",
    "Stipendi",
    "F24",
    "Utenze",
    "Pagamento PayPal",
    "Altro",
    "Rimborso",
])
def test_chi_dovrebbe_avere_un_documento_aspetta(categoria):
    """Erano proprio queste a riempire la Prima Nota di righe grezze."""
    assert entra_in_prima_nota(categoria) is False


@pytest.mark.parametrize("valore", [None, "", "   ", "categoria mai vista"])
def test_nel_dubbio_non_entra(valore):
    """Una categoria sconosciuta non e' un lasciapassare: si aspetta."""
    assert entra_in_prima_nota(valore) is False


def test_l_elenco_delle_eccezioni_resta_corto():
    """Se questo elenco cresce, la Prima Nota torna a essere una fotocopia.
    Allargarlo deve essere una scelta esplicita, non una svista."""
    assert len(CATEGORIE_SENZA_DOCUMENTO) == 2


# --- Il collegamento con la classificazione reale della banca --------------

@pytest.mark.parametrize(("descrizione", "categoria_banca", "entra"), [
    # Movimenti della banca: entrano.
    ("PRELIEVO BANCOMAT SPORTELLO 1234", None, True),
    ("COMM.SU BONIFICI", "Operazioni Finanziarie - Commissioni", True),
    # Pagamenti che devono agganciarsi a un documento: aspettano.
    ("BONIFICO A FAVORE SCARAMUZZA SPA", "Fornitori - Beni", False),
    ("PAGAMENTO F24", "Tasse - Erario", False),
    ("STIPENDIO DIPENDENTE", "Risorse Umane - Stipendi", False),
    ("ADDEBITO UTENZA ENEL", None, False),
    ("PAGAMENTO PAYPAL EUROPE", None, False),
])
def test_la_regola_applicata_alle_causali_vere(descrizione, categoria_banca, entra):
    categoria = mappa_categoria_ec(categoria_banca, descrizione.upper()) or "Altro"
    assert entra_in_prima_nota(categoria) is entra


def test_un_bonifico_a_fornitore_non_entra_come_riga_grezza():
    """Il caso segnalato: l'estratto conto riversato in Prima Nota."""
    categoria = mappa_categoria_ec("Fornitori - Servizi",
                                   "BONIFICO A FAVORE RTA SRL NOTPROVIDE")
    assert categoria == "Fatture"
    assert entra_in_prima_nota(categoria) is False
