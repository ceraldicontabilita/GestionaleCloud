"""
Routers package.
API endpoints for all modules.
Organizzati in sottocartelle per modulo.
"""
# I moduli principali sono nelle sottocartelle:
# - accounting/ (prima nota, bilancio, f24, etc.)
# - bank/ (estratto conto, assegni, bonifici)
# - employees/ (dipendenti, contratti, buste paga)
# - f24/ (gestione F24)
# - invoices/ (fatture, corrispettivi)
# - reports/ (export, analytics)
# - warehouse/ (magazzino, prodotti)

from . import accounting, bank, employees, f24, invoices, reports, warehouse

__all__ = [
	"accounting",
	"bank",
	"employees",
	"f24",
	"invoices",
	"reports",
	"warehouse",
]
