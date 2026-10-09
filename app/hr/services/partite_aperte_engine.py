"""Motore delle partite aperte — re-export del modulo unico.

La logica vive in `app.services.partite_aperte_engine`. Fino al 19/09/2026 qui c'era una copia
identica al lato ERP tranne una riga di docstring (il percorso di import
nell'esempio d'uso).

Un modulo che non contiene logica non puo' divergere: e' questo il punto del
re-export. Il fork `app/hr` non nasceva per avere due comportamenti, ma per
avere due percorsi di import, e quelli restano.
"""
from app.services.partite_aperte_engine import (  # noqa: F401
    COLL_PARTITE,
    StatoPartita,
    TipoPartita,
    cerca_partite_compatibili,
    cerca_partite_per_controparte,
    chiudi_partita,
    crea_partita,
    ricalcola_residui,
    totale_partite_aperte,
)

__all__ = [
    "COLL_PARTITE",
    "StatoPartita",
    "TipoPartita",
    "cerca_partite_compatibili",
    "cerca_partite_per_controparte",
    "chiudi_partita",
    "crea_partita",
    "ricalcola_residui",
    "totale_partite_aperte",
]
