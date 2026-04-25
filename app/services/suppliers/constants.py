"""
Costanti per il modulo Fornitori.

Regola canonica: la collection MongoDB dei fornitori e' `fornitori`.
`supplier`/`suppliers` restano nomi tecnici/inglesi di moduli, endpoint e servizi,
ma NON devono indicare una collection MongoDB separata.
"""

from app.db_collections import COLL_FORNITORI, COLL_INVOICES


class Collections:
    """Nomi delle collection MongoDB per il modulo fornitori."""
    FORNITORI = COLL_FORNITORI
    SUPPLIERS = COLL_FORNITORI  # Alias legacy/inglese -> collection canonica `fornitori`
    INVOICES = COLL_INVOICES


# Metodi di pagamento disponibili
PAYMENT_METHODS = [
    {"id": "bonifico", "nome": "Bonifico Bancario", "icon": "🏦"},
    {"id": "riba", "nome": "Ri.Ba. (Ricevuta Bancaria)", "icon": "📋"},
    {"id": "contanti", "nome": "Contanti", "icon": "💵"},
    {"id": "assegno", "nome": "Assegno", "icon": "📝"},
    {"id": "carta", "nome": "Carta di Credito/Debito", "icon": "💳"},
    {"id": "compensazione", "nome": "Compensazione", "icon": "⚖️"},
    {"id": "altro", "nome": "Altro", "icon": "📦"}
]

# Termini di pagamento
PAYMENT_TERMS = [
    {"id": "immediato", "giorni": 0, "nome": "Pagamento Immediato"},
    {"id": "30gg_fm", "giorni": 30, "nome": "30 giorni fine mese"},
    {"id": "30gg_df", "giorni": 30, "nome": "30 giorni data fattura"},
    {"id": "60gg_fm", "giorni": 60, "nome": "60 giorni fine mese"},
    {"id": "60gg_df", "giorni": 60, "nome": "60 giorni data fattura"},
    {"id": "90gg_fm", "giorni": 90, "nome": "90 giorni fine mese"},
    {"id": "90gg_df", "giorni": 90, "nome": "90 giorni data fattura"},
    {"id": "120gg_fm", "giorni": 120, "nome": "120 giorni fine mese"},
    {"id": "custom", "giorni": 0, "nome": "Personalizzato"}
]

# Campi obbligatori per validazione P0
CAMPI_OBBLIGATORI_P0 = [
    "partita_iva",
    "denominazione",
    "metodo_pagamento"
]

# Campi consigliati per validazione completa
CAMPI_CONSIGLIATI = [
    "iban",
    "email",
    "pec",
    "telefono",
    "indirizzo"
]
