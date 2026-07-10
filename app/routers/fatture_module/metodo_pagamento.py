"""
Normalizzazione metodo di pagamento e auto-routing fatture
in prima_nota_cassa / prima_nota_banca sulla base dell'anagrafica fornitore.

La normalizzazione vera e propria e' delegata al motore centralizzato
app.engines.prima_nota_engine (REGOLA UNICA in tutto il gestionale: cassa/
banca/misto). "Assegno" non e' piu' una categoria a se': per decisione del
2026-07 e' ricondotto a "banca" come ogni altro strumento che transita dal
conto corrente.
"""
from typing import Optional, Tuple

from app.engines.prima_nota_engine import normalizza_metodo_pagamento as _normalizza_canonico


def normalizza_metodo_pagamento(metodo_raw: Optional[str]) -> Optional[str]:
    """
    Normalizza un metodo di pagamento (fornitore o FE) in una destinazione:
      - 'cassa'  → va in prima_nota_cassa
      - 'banca'  → va in prima_nota_banca (include bonifico, carta, SEPA, assegno, paypal)
      - 'misto'  → va in Prima Nota Provvisoria (attesa conferma utente)
      - None     → ambiguo / da configurare, NON auto-routare

    Il confronto è case-insensitive e accetta sia label italiane (contanti,
    bonifico, carta di credito…) sia codici MP FE (MP01, MP05, MP08…).
    """
    return _normalizza_canonico(metodo_raw)


def destinazione_auto(metodo_fornitore: Optional[str]) -> Tuple[Optional[str], str]:
    """
    Ritorna (destinazione, descrizione) per log/UX:
      destinazione ∈ {'cassa','banca','misto',None}
    """
    dest = normalizza_metodo_pagamento(metodo_fornitore)
    if dest == "cassa":
        return "cassa", "contanti → prima_nota_cassa"
    if dest == "banca":
        return "banca", "banca/carta/bonifico/assegno → prima_nota_banca"
    if dest == "misto":
        return "misto", "misto → Prima Nota Provvisoria, attesa conferma utente"
    return None, f"metodo ambiguo/non configurato: {metodo_fornitore!r}"
