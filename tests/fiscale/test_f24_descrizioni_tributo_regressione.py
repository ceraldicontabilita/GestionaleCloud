"""Regressione trovata nell'audit del 19/09/2026 sulla PR di consolidamento
delle descrizioni codice tributo F24.

Fino a quella PR esistevano DUE tabelle "codice tributo -> descrizione": il
dizionario locale di `app/services/parser_f24.py` (quello che l'utente vedeva
davvero nel flusso F24) e il registro canonico
`app/services/codici_tributo_f24.py`. La PR ha giustamente eliminato la copia
locale facendo delegare `parser_f24.get_descrizione_tributo()` al registro,
ma per alcuni codici il registro conteneva GIA' PRIMA una descrizione
sbagliata o che duplicava un altro codice: la delega le ha rese visibili,
peggiorando un documento fiscale regolamentato.

I codici qui sotto sono quelli che divergevano semanticamente fra le due
tabelle. Il testo atteso è ESATTAMENTE quello che era in produzione (il
dizionario locale di parser_f24 su main): non è una riformulazione, perché
CLAUDE.md vieta di inventare o "migliorare" dati di fonte ("non inventare
numeri": se il dato manca, campo vuoto e segnalazione).

Casi peggiorati dalla migrazione e qui bloccati:
- 3812/3813: il registro spostava l'acconto di una rata e duplicava
  "IRAP saldo" su 3800 e 3813.
- 3801/3802: il registro assegnava a 3801 un tributo diverso (IRAP acconto)
  e duplicava "sostituti d'imposta" fra i due codici.
- 1627/1631/1704: il registro descriveva tributi diversi da quelli pagati.
  In particolare 1704 diventava "Credito IVA utilizzato in compensazione",
  in contraddizione diretta con la regola di CLAUDE.md ("1701/1704 sono
  crediti, non IVA né costo").
- 3916: il registro duplicava il significato di 3925 (fabbricati gruppo D
  STATO) su un codice che è invece aree fabbricabili quota COMUNE.

Se qualcuno tocca di nuovo il registro canonico e cambia una di queste voci,
questo test lo intercetta.
"""
import pytest

from app.services import parser_f24
from app.services.codici_tributo_f24 import CODICI_TRIBUTO_F24

# codice -> descrizione esatta mostrata in produzione prima della migrazione
DESCRIZIONI_DIVERGENTI = {
    "1627": "Eccedenza versamenti ritenute lavoro dipendente",
    "1631": "Somme rimborsate sostituto assistenza fiscale",
    "1704": "Credito somma art.1 c.4 L. 207/2024",
    # 3801/3802: il testo «di produzione» li aveva scambiati. Fonte Agenzia
    # delle Entrate: 3802 e' la trattenuta del sostituto d'imposta (le rate
    # mensili sugli F24 delle paghe), 3801 l'autotassazione.
    "3801": "Addizionale regionale IRPEF - autotassazione",
    "3802": "Addizionale regionale IRPEF - sostituto d'imposta",
    "3812": "IRAP acconto prima rata",
    "3813": "IRAP acconto seconda rata o unica soluzione",
    "3916": "IMU aree fabbricabili - comune",
}

# campione più ampio di codici usati di routine dal gruppo, per accorgersi di
# altre derive del registro oltre alle voci già note
DESCRIZIONI_CAMPIONE = {
    "1001": "Ritenute su retribuzioni, pensioni, trasferte, mensilità aggiuntive",
    "1040": "Ritenute su redditi di lavoro autonomo: compensi per l'esercizio di arti e professioni",
    "1701": "Credito trattamento integrativo (DL 3/2020)",
    "3800": "Imposta regionale sulle attività produttive - saldo",
    "3925": "IMU - imposta municipale propria per immobili ad uso produttivo classificati D - STATO",
    "6001": "IVA - Versamento mensile gennaio",
    "6012": "IVA - Versamento mensile dicembre",
}


@pytest.mark.parametrize("codice,attesa", sorted(DESCRIZIONI_DIVERGENTI.items()))
def test_descrizioni_divergenti_restano_quelle_di_produzione(codice, attesa):
    assert parser_f24.get_descrizione_tributo(codice) == attesa


@pytest.mark.parametrize("codice,attesa", sorted(DESCRIZIONI_CAMPIONE.items()))
def test_campione_descrizioni_codici_ricorrenti(codice, attesa):
    assert parser_f24.get_descrizione_tributo(codice) == attesa


def test_parser_f24_delega_al_registro_canonico():
    """Una sola tabella: parser_f24 non deve tornare ad avere una copia locale."""
    for codice, attesa in DESCRIZIONI_DIVERGENTI.items():
        assert CODICI_TRIBUTO_F24[codice]["descrizione"] == attesa
        assert parser_f24.get_descrizione_tributo(codice) == attesa


def test_nessuna_descrizione_duplicata_fra_i_codici_corretti():
    """3800/3813 e 3916/3925 e 3801/3802 non devono più dire la stessa cosa."""
    for a, b in (("3800", "3813"), ("3916", "3925"), ("3801", "3802")):
        assert parser_f24.get_descrizione_tributo(a) != parser_f24.get_descrizione_tributo(b)


def test_1704_resta_un_credito_non_iva_ne_costo():
    """CLAUDE.md, "F24, tributi, dichiarazioni": 1701/1704 sono crediti, non IVA
    né costo. La descrizione non deve tornare a parlare di IVA o di costo."""
    descrizione = parser_f24.get_descrizione_tributo("1704")
    assert "credito" in descrizione.lower()
    assert "iva" not in descrizione.lower()
