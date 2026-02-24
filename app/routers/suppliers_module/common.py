"""
Common utilities and constants for suppliers module.
"""
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

# Cache key per suppliers
SUPPLIERS_CACHE_KEY = "suppliers_list"
SUPPLIERS_CACHE_TTL = 300  # 5 minuti per performance migliori

# Metodi di pagamento disponibili
PAYMENT_METHODS = {
    "contanti": {"label": "Contanti", "prima_nota": "cassa"},
    "bonifico": {"label": "Bonifico Bancario", "prima_nota": "banca"},
    "assegno": {"label": "Assegno", "prima_nota": "banca"},
    "riba": {"label": "Ri.Ba.", "prima_nota": "banca"},
    "carta": {"label": "Carta di Credito", "prima_nota": "banca"},
    "sepa": {"label": "Addebito SEPA", "prima_nota": "banca"},
    "mav": {"label": "MAV", "prima_nota": "banca"},
    "rav": {"label": "RAV", "prima_nota": "banca"},
    "rid": {"label": "RID", "prima_nota": "banca"},
    "f24": {"label": "F24", "prima_nota": "banca"},
    "compensazione": {"label": "Compensazione", "prima_nota": "altro"},
    "misto": {"label": "Misto (Cassa + Banca)", "prima_nota": "misto"}
}

# Termini di pagamento predefiniti
PAYMENT_TERMS = [
    {"code": "VISTA", "days": 0, "label": "A vista"},
    {"code": "30GG", "days": 30, "label": "30 giorni"},
    {"code": "30GGDFM", "days": 30, "label": "30 giorni data fattura fine mese"},
    {"code": "60GG", "days": 60, "label": "60 giorni"},
    {"code": "60GGDFM", "days": 60, "label": "60 giorni data fattura fine mese"},
    {"code": "90GG", "days": 90, "label": "90 giorni"},
    {"code": "120GG", "days": 120, "label": "120 giorni"},
]

# Metodi bancari che richiedono IBAN
METODI_BANCARI = ["bonifico", "banca", "sepa", "rid", "sdd", "assegno", "riba", "mav", "rav", "f24", "carta", "misto"]


def clean_mongo_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Rimuove _id da documento MongoDB."""
    if doc and "_id" in doc:
        doc.pop("_id", None)
    return doc
