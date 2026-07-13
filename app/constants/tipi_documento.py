"""
Tipi documento SDI — costanti condivise (fonte unica di verità).

Prima `TIPI_NOTA_CREDITO` era ridefinito in 5+ punti (iva.py, sync.py,
liquidazione_iva_engine.py, riepilogo_iva_engine.py, config/azienda.py) con
rischio di divergenza. Importare da qui.
"""

# Note di credito: invertono il segno dell'IVA (TD04 nota di credito,
# TD08 nota di credito semplificata).
TIPI_NOTA_CREDITO = ("TD04", "TD08")
