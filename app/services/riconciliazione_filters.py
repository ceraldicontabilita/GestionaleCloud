"""Filtri canonici per la riconciliazione bancaria."""
from typing import Any, Dict


def filtro_uscite_da_riconciliare() -> Dict[str, Any]:
    """Movimenti di uscita non ancora riconciliati, inclusi i dati legacy."""
    return {
        "riconciliato": {"$nin": ["riconciliato", "parziale", True]},
        "$or": [
            {"tipo": "uscita"},
            {"importo": {"$lt": 0}},
        ],
    }
