"""«Fattura attiva»: un criterio solo per tutti i lettori di ``invoices``.

Stesso vocabolario del recupero del pregresso e del libro giornale: fuori le
copie archiviate (``archived``/``archiviata`` convivono in archivio, regola
13), le cancellate, l'archivio storico e le collisioni di identita' ancora
aperte. ``$nin``/``$ne`` su un campo assente passano (regola 11): e' voluto,
un campo assente vuol dire attiva.

Prima il filtro esisteva in due copie (report AE e noleggio) e la
liquidazione IVA, il riepilogo annuale e la dashboard non ne avevano
nessuno: le 555 copie archiviate delle fatture 2026 pesavano due volte.
"""
from typing import Any, Dict

STATI_FATTURA_NON_ATTIVA = ("archived", "archiviata", "deleted")
STATI_IMPORT_NON_ATTIVI = ("archivio_storico", "collisione_identita_da_verificare")

FILTRO_FATTURA_ATTIVA: Dict[str, Any] = {
    "status": {"$nin": list(STATI_FATTURA_NON_ATTIVA)},
    "stato_import": {"$nin": list(STATI_IMPORT_NON_ATTIVI)},
    "entity_status": {"$ne": "deleted"},
    "deleted": {"$ne": True},
}


def fattura_attiva(fattura: Dict[str, Any]) -> bool:
    """Stesso predicato di ``FILTRO_FATTURA_ATTIVA`` per un documento gia' letto."""
    if str(fattura.get("status") or "").strip().lower() in STATI_FATTURA_NON_ATTIVA:
        return False
    if str(fattura.get("stato_import") or "").strip().lower() in STATI_IMPORT_NON_ATTIVI:
        return False
    if str(fattura.get("entity_status") or "").strip().lower() == "deleted":
        return False
    return fattura.get("deleted") is not True
