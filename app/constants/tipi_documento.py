"""
Tipi documento SDI — costanti condivise (fonte unica di verità).

Prima `TIPI_NOTA_CREDITO` era ridefinito in 5+ punti (iva.py, sync.py,
liquidazione_iva_engine.py, riepilogo_iva_engine.py, config/azienda.py) con
rischio di divergenza. Importare da qui.
"""

# Note di credito: invertono il segno dell'IVA (TD04 nota di credito,
# TD08 nota di credito semplificata).
TIPI_NOTA_CREDITO = ("TD04", "TD08")


# ---------------------------------------------------------------------------
# Tassonomia documenti di `documents_inbox` (P2-3)
# ---------------------------------------------------------------------------
# Storicamente un documento porta TRE campi con lo stesso valore:
#   - `tipo_documento`  → CANONICO (usato dai saver e dalle mappe tipo→collection)
#   - `categoria`       → alias legacy (lettori italiani)
#   - `category`        → alias legacy (lettori inglesi / frontend)
# Sono ridondanti: qui si dichiara `tipo_documento` come fonte di verità e si
# forniscono helper per (a) scriverli tutti coerenti da un unico valore e
# (b) leggere il tipo qualunque alias sia presente. NON si rinominano i campi
# esistenti (footprint ampio, rischio regressione): si centralizza soltanto la
# redondanza cosi' che chi scrive parta da un'unica sorgente.

CAMPO_TIPO_DOCUMENTO_CANONICO = "tipo_documento"
_ALIAS_TIPO_DOCUMENTO = ("tipo_documento", "categoria", "category")


def set_tassonomia_documento(doc: dict, tipo: str, label: str = None) -> dict:
    """Imposta in modo coerente `tipo_documento`/`categoria`/`category` (e,
    se dato, `category_label`) su `doc` a partire da un unico valore `tipo`.
    Ritorna `doc` (modificato in place) per comodità di chaining."""
    doc["tipo_documento"] = tipo
    doc["categoria"] = tipo
    doc["category"] = tipo
    if label is not None:
        doc["category_label"] = label
    return doc


def leggi_tipo_documento(doc: dict) -> str:
    """Ritorna il tipo del documento leggendo il primo alias presente,
    dando priorità al campo canonico. '' se nessuno è valorizzato."""
    for campo in _ALIAS_TIPO_DOCUMENTO:
        val = (doc or {}).get(campo)
        if val:
            return val
    return ""
