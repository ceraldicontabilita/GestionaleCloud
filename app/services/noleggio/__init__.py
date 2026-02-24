"""
Servizio Gestione Noleggio Auto
Modulo per elaborazione fatture noleggio auto e gestione flotta aziendale.
"""

from .constants import FORNITORI_NOLEGGIO, TARGA_PATTERN, COLLECTION
from .parsers import (
    estrai_codice_cliente,
    estrai_numero_verbale,
    estrai_data_verbale,
    estrai_numero_verbale_completo,
    categorizza_spesa,
    estrai_modello_marca
)
from .processors import (
    processa_fattura_noleggio,
    scan_fatture_noleggio
)

__all__ = [
    # Constants
    "FORNITORI_NOLEGGIO",
    "TARGA_PATTERN", 
    "COLLECTION",
    # Parsers
    "estrai_codice_cliente",
    "estrai_numero_verbale",
    "estrai_data_verbale",
    "estrai_numero_verbale_completo",
    "categorizza_spesa",
    "estrai_modello_marca",
    # Processors
    "processa_fattura_noleggio",
    "scan_fatture_noleggio"
]
