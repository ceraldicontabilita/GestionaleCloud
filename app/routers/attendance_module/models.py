"""
ATTENDANCE - Modelli e Costanti Condivise
=========================================
"""

from enum import Enum


class TipoTimbratura(Enum):
    ENTRATA = "entrata"
    USCITA = "uscita"
    PAUSA_INIZIO = "pausa_inizio"
    PAUSA_FINE = "pausa_fine"


class TipoAssenza(Enum):
    FERIE = "ferie"
    PERMESSO = "permesso"
    MALATTIA = "malattia"
    MATERNITA = "maternita"
    PATERNITA = "paternita"
    INFORTUNIO = "infortunio"


class StatoRichiesta(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


# Stati presenza per il calendario
STATI_PRESENZA = {
    "presente": {"label": "P", "name": "Presente", "bg": "#dcfce7", "color": "#166534"},
    "assente": {"label": "A", "name": "Assente", "bg": "#fee2e2", "color": "#dc2626"},
    "ferie": {"label": "F", "name": "Ferie", "bg": "#dbeafe", "color": "#1d4ed8"},
    "permesso": {"label": "PE", "name": "Permesso", "bg": "#fef3c7", "color": "#d97706"},
    "malattia": {"label": "M", "name": "Malattia", "bg": "#fce7f3", "color": "#db2777"},
    "rol": {"label": "R", "name": "ROL", "bg": "#e0e7ff", "color": "#4f46e5"},
    "smartworking": {"label": "SW", "name": "Smart Working", "bg": "#ccfbf1", "color": "#0d9488"},
    "trasferta": {"label": "T", "name": "Trasferta", "bg": "#fef9c3", "color": "#ca8a04"},
    "riposo": {"label": "-", "name": "Riposo", "bg": "#f3f4f6", "color": "#6b7280"}
}


# Mesi in italiano
MESI = [
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"
]
