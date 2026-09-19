# Constants Module
#
# `app/constants/codici_tributo_f24.py` e' stato rimosso il 19/09/2026: era una
# copia troncata (89 righe contro 1.992, stessa intestazione parola per parola)
# della tabella in `app/services/codici_tributo_f24.py`, e non la importava
# nessuno. Il re-export punta alla tabella canonica, cosi' un import futuro
# non puo' finire di nuovo su una copia.
from app.services.codici_tributo_f24 import CODICI_TRIBUTO_F24

__all__ = ['CODICI_TRIBUTO_F24']
