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

# Categorie da escludere nei conteggi: non sono movimenti bancari/di cassa
# reali, quindi non devono mai contribuire a saldi/entrate/uscite.
# "Corrispettivi POS" è la chiusura POS serale inserita manualmente
# dall'utente (PUT /api/pos-corrispettivi/chiusura-giornaliera) — serve solo
# per la verifica di coerenza con l'importo elettronico dichiarato nel
# corrispettivo XML (che è già la fonte fiscale corretta ed è già contato
# in Prima Nota Cassa all'import); non è un secondo incasso reale.
CATEGORIE_ESCLUSE = ["POS_DUPLICATO", "Corrispettivi POS"]


def clean_mongo_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Rimuove _id da documento MongoDB."""
    if doc and "_id" in doc:
        doc.pop("_id", None)
    return doc


# Importo robusto: in estratto_conto_movimenti alcuni documenti storici hanno
# `importo` come stringa; $convert li somma comunque (onError/onNull → 0).
# Per cassa/banca (importi già numerici) il risultato è identico a "$importo".
_IMPORTO_NUMERICO = {"$convert": {"input": "$importo", "to": "double",
                                  "onError": 0, "onNull": 0}}


def _pipeline_entrate_uscite(query: Dict[str, Any]) -> list:
    """Pipeline di aggregazione entrate/uscite (segno §6.4): l'IMPORTO è sempre
    positivo, il segno lo dà il campo `tipo` (entrata=+, uscita=−)."""
    return [
        {"$match": query},
        {"$group": {
            "_id": None,
            "entrate": {"$sum": {"$cond": [{"$eq": ["$tipo", "entrata"]}, _IMPORTO_NUMERICO, 0]}},
            "uscite": {"$sum": {"$cond": [{"$eq": ["$tipo", "uscita"]}, _IMPORTO_NUMERICO, 0]}},
        }},
    ]


async def aggrega_saldo_prima_nota(db, collection: str, query: Dict[str, Any],
                                   anno: int = None,
                                   query_base_precedente: Dict[str, Any] = None) -> Dict[str, float]:
    """Funzione UNICA di saldo Prima Nota (§6.4) — cassa/banca/estratto conto usano questa.

    Uniforma segno, saldo iniziale (riporto anni precedenti) e saldo finale:
      saldo_anno   = entrate − uscite (sui movimenti che soddisfano `query`)
      saldo_iniziale = riporto cumulato di tutti gli anni precedenti
      saldo_finale = saldo_iniziale + saldo_anno

    Le esclusioni (status deleted/archived, CATEGORIE_ESCLUSE) fanno parte di `query`
    costruita dal chiamante. Per il riporto: con `query_base_precedente=None` (default,
    Prima Nota cassa/banca) si applicano le esclusioni standard della Prima Nota;
    passando un dict (es. {} per l'estratto conto, che non ha soft-delete né categorie
    escluse) il riporto usa quelle condizioni + data < 1/1/anno.
    Ritorna importi già arrotondati a 2 decimali.
    """
    totals = await db[collection].aggregate(_pipeline_entrate_uscite(query)).to_list(1)
    entrate = totals[0].get("entrate", 0) if totals else 0
    uscite = totals[0].get("uscite", 0) if totals else 0
    saldo_anno = entrate - uscite
    saldo_precedente = (
        await calcola_saldo_anni_precedenti(db, collection, anno, query_base_precedente)
        if anno else 0.0
    )
    saldo_finale = saldo_precedente + saldo_anno
    return {
        "totale_entrate": round(entrate, 2),
        "totale_uscite": round(uscite, 2),
        "saldo_anno": round(saldo_anno, 2),
        "saldo_precedente": round(saldo_precedente, 2),
        "saldo": round(saldo_finale, 2),
    }


async def calcola_saldo_anni_precedenti(db, collection: str, anno: int,
                                        query_base: Dict[str, Any] = None) -> float:
    """
    Calcola il saldo cumulativo di tutti gli anni precedenti all'anno specificato.
    Questo è il "riporto" o "saldo iniziale" dell'anno.

    `query_base=None` (default) applica le esclusioni standard della Prima Nota;
    un dict esplicito (anche vuoto) le sostituisce (usato dall'estratto conto).
    """
    if not anno:
        return 0.0

    if query_base is None:
        query_base = {
            "status": {"$nin": ["deleted", "archived"]},
            "categoria": {"$nin": CATEGORIE_ESCLUSE}
        }
    query = {**query_base, "data": {"$lt": f"{anno}-01-01"}}

    totals = await db[collection].aggregate(_pipeline_entrate_uscite(query)).to_list(1)
    
    if totals:
        return totals[0].get("entrate", 0) - totals[0].get("uscite", 0)
    return 0.0
