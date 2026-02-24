"""
Fatture Module - Costanti e utility condivise.
"""
import logging

logger = logging.getLogger(__name__)

# Collection names - STANDARDIZZATE
COL_FORNITORI = "suppliers"
COL_FATTURE_RICEVUTE = "invoices"
COL_DETTAGLIO_RIGHE = "dettaglio_righe_fatture"
COL_ALLEGATI = "allegati_fatture"

# Mapping stato pagamento
STATO_PAGAMENTO = {
    "non_pagata": "Non Pagata",
    "pagata": "Pagata",
    "parziale": "Parzialmente Pagata",
    "in_attesa": "In Attesa"
}

# Metodi pagamento validi
METODI_PAGAMENTO = [
    "bonifico", "contanti", "assegno", "riba", "carta", 
    "sepa", "mav", "rav", "rid", "compensazione", "altro"
]
