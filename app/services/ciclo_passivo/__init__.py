"""
Servizio Ciclo Passivo Integrato
Modulo per gestione import fatture, magazzino, prima nota, scadenziario.
"""

from .constants import (
    MAGAZZINO_COLLECTION,
    LOTTI_COLLECTION,
    PRIMA_NOTA_COLLECTION,
    SCADENZIARIO_COLLECTION,
    CONTI_DARE,
    CONTI_AVERE
)

from .helpers import (
    estrai_codice_lotto,
    estrai_scadenza,
    detect_centro_costo,
    get_or_create_fornitore
)

from .magazzino import (
    genera_id_lotto_interno,
    processa_carico_magazzino
)

from .prima_nota import (
    genera_scrittura_prima_nota
)

from .scadenziario import (
    crea_scadenza_pagamento
)

from .riconciliazione import (
    cerca_match_bancario,
    esegui_riconciliazione
)

__all__ = [
    # Constants
    "MAGAZZINO_COLLECTION",
    "LOTTI_COLLECTION", 
    "PRIMA_NOTA_COLLECTION",
    "SCADENZIARIO_COLLECTION",
    "CONTI_DARE",
    "CONTI_AVERE",
    # Helpers
    "estrai_codice_lotto",
    "estrai_scadenza",
    "detect_centro_costo",
    "get_or_create_fornitore",
    # Magazzino
    "genera_id_lotto_interno",
    "processa_carico_magazzino",
    # Prima Nota
    "genera_scrittura_prima_nota",
    # Scadenziario
    "crea_scadenza_pagamento",
    # Riconciliazione
    "cerca_match_bancario",
    "esegui_riconciliazione"
]
