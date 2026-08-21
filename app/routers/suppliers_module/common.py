"""
Common utilities and constants for suppliers module.
"""
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

# Cache key per suppliers
SUPPLIERS_CACHE_KEY = "suppliers_list"
SUPPLIERS_CACHE_TTL = 300  # 5 minuti per performance migliori

# Metodi di pagamento validi in scrittura sui fornitori. Il dropdown di
# Fornitori.jsx propone solo cassa/banca/misto ("certo" è stato rimosso: il
# sistema non può sapere con certezza dove imputare il pagamento solo dal
# metodo impostato in anagrafica) — i valori legacy restano qui SOLO per non
# rompere la validazione su dati/flussi già esistenti che li scrivono ancora
# (import Excel, bulk, integrazioni) senza richiedere una migrazione dati.
PAYMENT_METHODS = {
    "cassa": {"label": "Cassa", "prima_nota": "cassa"},
    "banca": {"label": "Banca", "prima_nota": "banca"},
    "misto": {"label": "Misto", "prima_nota": "provvisorio"},
    "contanti": {"label": "Contanti", "prima_nota": "cassa"},
    "assegno": {"label": "Assegno", "prima_nota": "banca"},
    "bonifico": {"label": "Bonifico", "prima_nota": "banca"},
    "rid": {"label": "R.I.D.", "prima_nota": "banca"},
    "carta": {"label": "Carta", "prima_nota": "banca"},
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

# Metodi bancari che richiedono IBAN: punto unico nel motore condiviso
# (prima questa lista era un sottoinsieme divergente da quella di
# suppliers/iban_service.py: "sepa"/"riba"/... risultavano bancari in un
# flusso e non nell'altro).
from app.engines.prima_nota_engine import METODI_RICHIEDONO_IBAN as METODI_BANCARI


def clean_record(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Rimuove l'identificatore interno prima della risposta JSON."""
    if doc and "_id" in doc:
        doc.pop("_id", None)
    return doc
