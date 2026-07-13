"""Mapping CANONICO verso il piano dei conti UFFICIALE CEE (§6.2/§6.3).

Regola utente (vincolante): **il piano dei conti è solo CEE** — quando si incontra un
altro schema, si usa SOLO quello ufficiale CEE (`app/services/piano_conti_ufficiale.py`,
estratto dal bilancio ufficiale Ceraldi).

Nel codice esistono due schemi INTERNI che NON sono il piano ufficiale:
  - operativo puntato di `piano_conti` (es. `05.01.01` = "Acquisto merci") — usato dal
    motore di registrazione §6.1;
  - numerico di `contabilita_italiana` (es. `400100`).
Attenzione: i codici INTERNI collidono con quelli ufficiali (nel piano ufficiale
`05` = Immobilizzazioni materiali, `55` = Acquisti). Per il bilancio/reportistica si
converte SEMPRE verso i codici ufficiali con questa tabella.

`OPERATIVO_A_UFFICIALE`: codice operativo interno → codice ufficiale CEE.
Target `None` = nessun conto ufficiale corrispondente esatto nel bilancio (da rivedere).
"""
from typing import Dict, Optional

from app.services.piano_conti_ufficiale import CONTI_UFFICIALI, MACRO_UFFICIALE, sezione_di

# codice operativo interno (piano_conti.STRUTTURA_BASE) → codice ufficiale CEE
OPERATIVO_A_UFFICIALE: Dict[str, str] = {
    # ATTIVO
    "01.01.01": "19.03.03",   # Cassa → Cassa contanti
    "01.01.02": "19.01.01",   # Banca c/c → Banca c/c
    "01.02.01": "15.05",      # Crediti v/clienti → Crediti vari v/terzi (macro; no leaf clienti nel bilancio)
    "01.03.01": "51.01.03",   # Magazzino merci → Rimanenze di merci
    "01.04.01": "35.01",      # IVA a credito → Erario c/IVA
    # PASSIVO
    "02.01.01": "33.03.01",   # Debiti v/fornitori → Fornitori terzi Italia
    "02.02.01": "35.07",      # Debiti tributari → Erario c/imposte
    "02.02.02": "37.01.01",   # Debiti v/INPS → INPS dipendenti
    "02.03.01": "35.01.11",   # IVA a debito → Erario c/liquidazione IVA
    "02.04.01": "29.01.01",   # TFR → Fondo TFR
    # PATRIMONIO NETTO
    "03.01.01": "23.01.01",   # Capitale sociale
    "03.02.01": "23.01.05",   # Riserva legale
    "03.03.01": "25.01.05",   # Utile d'esercizio → Avanzo utili
    "03.03.02": "25",         # Perdita d'esercizio → Risultati dell'esercizio (macro)
    # RICAVI
    "04.01.01": "47.01.03",   # Ricavi vendite prodotti → Vendita merci
    "04.01.02": "47.01.03",   # Ricavi vendite bar → Vendita merci
    "04.01.03": "47.01.03",   # Ricavi vendite cucina → Vendita merci
    "04.02.01": "47",         # Ricavi prestazioni servizi → Vendite (macro)
    "04.03.01": "53.01",      # Proventi finanziari → Altri ricavi/proventi diversi
    # COSTI
    "05.01.01": "55.01.07",   # Acquisto merci → Acquisti merci
    "05.01.02": "55.01.01",   # Acquisto materie prime → Acquisti di materie prime
    "05.02.01": "57",         # Costi per servizi → Acquisti di servizi (macro)
    "05.02.02": "57.09",      # Utenze → Costi per utenze
    "05.02.03": "65",         # Canoni di locazione → Godimento beni di terzi (macro)
    "05.03.01": "67.01.01",   # Salari e stipendi → Retribuzioni lorde
    "05.03.02": "67.01.03",   # Contributi previdenziali → Contributi INPS
    "05.03.03": "67.01.07",   # TFR → Quote TFR dipendenti
    "05.04.01": "41",         # Ammortamento immobilizzazioni → Fondi ammortamento (macro) VERIFICARE
    "05.05.01": "75",         # Oneri finanziari → Oneri finanziari (macro)
    "05.06.01": "84",         # Imposte e tasse → Imposte dell'esercizio (macro)
}


def operativo_a_ufficiale(codice_operativo: str) -> Optional[str]:
    """Codice interno operativo → codice ufficiale CEE (None se ignoto)."""
    return OPERATIVO_A_UFFICIALE.get(str(codice_operativo))


def descrizione_ufficiale(codice_ufficiale: str) -> Optional[str]:
    """Descrizione del conto ufficiale (o del macro-gruppo se è un codice a 2 cifre)."""
    return CONTI_UFFICIALI.get(str(codice_ufficiale))


def classifica_saldi_ufficiale(saldi_operativi: Dict[str, float]) -> Dict[str, Dict]:
    """VISTA DERIVATA del bilancio in forma UFFICIALE CEE (§6.2): converte i saldi dei
    conti operativi interni nei conti ufficiali e li raggruppa per macro-gruppo di
    bilancio (SP/CE). Funzione PURA: nessun accesso al DB.

    Ritorna {codice_ufficiale: {"descrizione", "sezione", "gruppo", "voce_cee",
             "saldo", "conti_operativi": [...]}}.
    """
    out: Dict[str, Dict] = {}
    for cod_op, saldo in saldi_operativi.items():
        cod_uff = OPERATIVO_A_UFFICIALE.get(str(cod_op))
        if not cod_uff:
            continue
        sez = sezione_di(cod_uff)
        voce = out.setdefault(cod_uff, {
            "descrizione": CONTI_UFFICIALI.get(cod_uff, cod_uff),
            "sezione": sez[0] if sez else None,
            "gruppo": sez[1] if sez else None,
            "voce_cee": sez[2] if sez else None,
            "saldo": 0.0, "conti_operativi": [],
        })
        voce["saldo"] = round(voce["saldo"] + float(saldo or 0), 2)
        voce["conti_operativi"].append(cod_op)
    return out
