"""
Prima Nota Module - Costanti e utility condivise.
"""
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

# Collections
COLLECTION_PRIMA_NOTA_CASSA = "prima_nota_cassa"
COLLECTION_PRIMA_NOTA_BANCA = "prima_nota_banca"
COLLECTION_PRIMA_NOTA_SALARI = "prima_nota_salari"

# Tipi movimento
TIPO_MOVIMENTO = {
    "entrata": {"label": "Entrata", "sign": 1},
    "uscita": {"label": "Uscita", "sign": -1}
}

# Categorie predefinite cassa
CATEGORIE_CASSA = [
    "Pagamento fornitore",
    "Incasso cliente",
    "Prelievo",
    "Versamento",
    "Spese generali",
    "Corrispettivi",
    "Altro"
]

# Categorie predefinite banca
CATEGORIE_BANCA = [
    "Pagamento fornitore",
    "Incasso cliente",
    "Bonifico in entrata",
    "Bonifico in uscita",
    "Addebito assegno",
    "Accredito assegno",
    "Commissioni bancarie",
    "F24",
    "Stipendi",
    "Altro"
]

# Categorie da escludere nei conteggi
CATEGORIE_ESCLUSE = ["POS_DUPLICATO"]


def clean_mongo_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Rimuove _id da documento MongoDB."""
    if doc and "_id" in doc:
        doc.pop("_id", None)
    return doc


async def calcola_saldo_anni_precedenti(db, collection: str, anno: int) -> float:
    """
    Calcola il saldo cumulativo di tutti gli anni precedenti all'anno specificato.
    Questo è il "riporto" o "saldo iniziale" dell'anno.
    """
    if not anno:
        return 0.0
    
    query = {
        "data": {"$lt": f"{anno}-01-01"},
        "status": {"$nin": ["deleted", "archived"]}
    }
    
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": None,
            "entrate": {"$sum": {"$cond": [{"$eq": ["$tipo", "entrata"]}, "$importo", 0]}},
            "uscite": {"$sum": {"$cond": [{"$eq": ["$tipo", "uscita"]}, "$importo", 0]}}
        }}
    ]
    
    totals = await db[collection].aggregate(pipeline).to_list(1)
    
    if totals:
        return totals[0].get("entrate", 0) - totals[0].get("uscite", 0)
    return 0.0
