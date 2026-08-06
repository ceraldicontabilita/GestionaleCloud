"""Conti del piano ufficiale usati dai circuiti di incasso elettronico.

Punto unico in cui un circuito (NEXI, SUMUP, PAYPAL) si traduce in codici
contabili. Averlo in un posto solo evita che lo stesso codice venga scritto
a mano in tre servizi diversi e poi diverga.

Il modello contabile e' quello deciso dall'utente:

- l'incasso elettronico della giornata NON e' denaro in banca: e' un
  **credito verso il gestore** (15.07.xx), che vive in un saldo proprio;
- l'accredito reale entra sul conto che lo riceve davvero — Banco BPM per
  Nexi/Numia, il conto Mastercard SumUp per SumUp — e in quel momento
  **chiude** il credito;
- la trattenuta del gestore e' un costo su 75.01.07.xx, mai un minor ricavo.

Tutti i codici sono verificati contro il piano ufficiale all'import: se
qualcuno rinomina o rimuove un conto, il modulo non parte invece di scrivere
in silenzio su un codice inesistente.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.services.piano_conti_ufficiale import CONTI_UFFICIALI

NEXI = "nexi"
SUMUP = "sumup"
PAYPAL = "paypal"

# Conto reale su cui il circuito accredita davvero.
CONTO_BPM = "19.01.01"
CONTO_SUMUP_MASTERCARD = "19.01.05"

CIRCUITI: Dict[str, Dict[str, str]] = {
    NEXI: {
        "etichetta": "Nexi/Numia",
        "credito": "15.07.01",
        "commissioni": "75.01.07.01",
        "conto_accredito": CONTO_BPM,
    },
    SUMUP: {
        "etichetta": "SumUp",
        "credito": "15.07.02",
        "commissioni": "75.01.07.02",
        # I payout SumUp NON arrivano su BPM: vanno sul conto aziendale
        # Mastercard, che si legge via API e ha un saldo suo.
        "conto_accredito": CONTO_SUMUP_MASTERCARD,
    },
    PAYPAL: {
        "etichetta": "PayPal",
        "credito": "15.07.03",
        "commissioni": "75.01.07.03",
        "conto_accredito": "",
    },
}

COMMISSIONI_ALTRO = "75.01.07.04"

# Sigla con cui il circuito compare in Prima Nota. Nexi accredita tramite
# Numia, ed e' "NUMIA" che l'utente legge sull'estratto conto: chiamarla cosi'
# rende la riga riconoscibile senza tradurre.
SIGLE = {NEXI: "NUMIA", SUMUP: "SUMUP", PAYPAL: "PAYPAL"}

CATEGORIA_USCITA_STORICA = "POS Verso Banca"


def sigla(circuito: Any) -> str:
    return SIGLE.get(normalizza(circuito), normalizza(circuito).upper())


def categoria_uscita_pos(circuito: Any) -> str:
    """Categoria dell'uscita di cassa verso il circuito.

    I circuiti non si fondono: ognuno ha la sua categoria, cosi' in Prima Nota
    si distingue a colpo d'occhio il POS Numia (inserito a mano) da quello
    SumUp (scritto dall'API).
    """
    return f"POS {sigla(circuito)} Verso Banca"


# Le righe scritte prima del 07/08/2026 hanno la categoria indistinta: le
# query devono continuare a trovarle, altrimenti se ne creerebbero di nuove
# in parallelo e l'uscita POS del giorno risulterebbe doppia.
CATEGORIE_USCITA_POS = [CATEGORIA_USCITA_STORICA] + [
    f"POS {s} Verso Banca" for s in sorted(set(SIGLE.values()))
]

# Tutti i conti di credito verso gestori: sono cio' che va tenuto FUORI dai
# saldi bancari reali.
CONTI_CREDITO = tuple(sorted(c["credito"] for c in CIRCUITI.values()))
CONTI_COMMISSIONI = tuple(sorted(
    [c["commissioni"] for c in CIRCUITI.values()] + [COMMISSIONI_ALTRO]
))


def _verifica_piano() -> None:
    mancanti = [
        codice for codice in
        list(CONTI_CREDITO) + list(CONTI_COMMISSIONI)
        + [CONTO_BPM, CONTO_SUMUP_MASTERCARD]
        if codice and codice not in CONTI_UFFICIALI
    ]
    if mancanti:
        raise RuntimeError(
            "Conti assenti dal piano ufficiale: " + ", ".join(mancanti)
        )


_verifica_piano()


def normalizza(circuito: Any) -> str:
    return str(circuito or "").strip().lower() or NEXI


def _voce(circuito: str, chiave: str, predefinito: str = "") -> str:
    return CIRCUITI.get(normalizza(circuito), {}).get(chiave, predefinito)


def conto_credito(circuito: Any) -> str:
    """Conto del credito verso il gestore. Vuoto se il circuito e' ignoto."""
    return _voce(circuito, "credito")


def conto_commissioni(circuito: Any) -> str:
    """Sottoconto commissioni del circuito, con ripiego su 'Altri costi'."""
    return _voce(circuito, "commissioni") or COMMISSIONI_ALTRO


def conto_accredito(circuito: Any) -> str:
    """Conto reale su cui il gestore versa: BPM per Nexi, Mastercard per SumUp."""
    return _voce(circuito, "conto_accredito")


def etichetta(circuito: Any) -> str:
    return _voce(circuito, "etichetta") or normalizza(circuito).upper()


def descrizione_conto(codice: str) -> str:
    return CONTI_UFFICIALI.get(str(codice or ""), "")


def e_conto_credito(codice: Any) -> bool:
    return str(codice or "") in CONTI_CREDITO


def circuiti_attivi() -> List[str]:
    """Circuiti che partecipano alla coerenza POS giornaliera.

    PayPal ha conti propri ma non passa dal registratore di cassa: non entra
    nel confronto XML-POS, quindi non e' un circuito 'attivo' in quel senso.
    """
    return [NEXI, SUMUP]


def circuito_di_conto(codice: Any) -> Optional[str]:
    """Circuito a cui appartiene un conto di credito o di commissioni."""
    codice = str(codice or "")
    for circuito, voci in CIRCUITI.items():
        if codice in (voci.get("credito"), voci.get("commissioni")):
            return circuito
    return None


def data_italiana(iso: Any) -> str:
    """Data in formato italiano gg/mm/aaaa per i testi letti dall'utente.

    A database le date restano ISO (AAAA-MM-GG): e' l'unico formato che si
    ordina e si confronta correttamente. Ma ogni descrizione che finisce in
    Prima Nota viene letta da una persona, e va scritta come la scriverebbe
    lei — regola dell'utente, valida in tutto il gestionale.
    """
    testo = str(iso or "").strip()[:10]
    parti = testo.split("-")
    if len(parti) == 3 and len(parti[0]) == 4:
        anno, mese, giorno = parti
        return f"{giorno}/{mese}/{anno}"
    return testo
