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

# Categorie predefinite cassa. Unificazione (utente 17/07/2026):
# "Fatture" = tutti i pagamenti fatture fornitori (prima anche "Pagamento
# fornitore"/"Fornitori"/"fornitori"); "Versamento Banca" = contanti da
# cassa a banca; "Prelevamento Banca" = contanti da banca a cassa (prima
# anche "Versamento"/"Prelievo"/"trasferimento_interno").
CATEGORIE_CASSA = [
    "Fatture",
    "Incasso cliente",
    "Prelevamento Banca",
    "Versamento Banca",
    "Spese generali",
    "Corrispettivi",
    "Altro"
]

# Categorie predefinite banca: OPERAZIONI sintetiche (regola utente
# 17/07/2026), il dettaglio sta nella descrizione.
CATEGORIE_BANCA = [
    "Fatture",
    "Utenze",
    "Versamento Banca",
    "Prelevamento Banca",
    "Corrispettivi POS",
    "Pagamento PayPal",
    "Rimborso",
    "Assegni",
    "Commissioni bancarie",
    "F24",
    "Stipendi",
    "Altro"
]

# Categorie da escludere nei conteggi: non sono movimenti bancari/di cassa
# reali, quindi non devono mai contribuire a saldi/entrate/uscite.
CATEGORIE_ESCLUSE = ["POS_DUPLICATO"]

# Source da escludere nei conteggi. Bug corretto 16/07/2026: prima qui era
# esclusa l'intera categoria "Corrispettivi POS", ma quella categoria la
# scrivono DUE percorsi diversi: la chiusura POS serale di verifica (source
# chiusura_pos_mobile — giustamente da escludere, non è un secondo incasso)
# E la quota POS del corrispettivo XML (source corrispettivo_pos /
# corrispettivi_sync — che è l'INCASSO REALE in banca, l'unico: l'import
# dell'estratto conto NON copia gli accrediti POS proprio perché già qui,
# vedi bank/estratto_conto.py). Risultato: la Prima Nota Banca mostrava
# solo uscite, con ~204.000€ di incassi POS 2026 spariti dai saldi.
# La distinzione giusta è per source, non per categoria:
#  - chiusura_pos_mobile / import_manuale_pos: chiusure serali di VERIFICA
#    (coerenza col battuto POS), mai un secondo incasso reale.
#  - estratto_conto_sync: copia integrale del vecchio endpoint di sync
#    dell'estratto conto reale dentro prima_nota_banca — duplicherebbe sia
#    i pagamenti fatture (già registrati dai flussi gestionali) sia gli
#    accrediti POS (già registrati come quota POS del corrispettivo).
#    L'estratto conto reale vive in estratto_conto_movimenti e serve a
#    riconciliare, non a sommare (verificato live 16/07/2026: 409 uscite
#    gen-apr contate due volte per questo).
SOURCES_ESCLUSE = ["chiusura_pos_mobile", "import_manuale_pos", "estratto_conto_sync"]

# Esclusioni standard complete della Prima Nota (da spargere con ** nelle
# query dei chiamanti, insieme al filtro status deleted/archived).
ESCLUSIONI_PRIMA_NOTA = {
    "categoria": {"$nin": CATEGORIE_ESCLUSE},
    "source": {"$nin": SOURCES_ESCLUSE},
}


def clean_mongo_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Rimuove _id da documento MongoDB."""
    if doc and "_id" in doc:
        doc.pop("_id", None)
    return doc


async def arricchisci_movimenti_fattura(db, movimenti: list) -> None:
    """Espone numero, data e fornitore come campi distinti nelle righe di
    Prima Nota, senza migrare o riscrivere i movimenti storici.

    I record recenti li salvano gia' direttamente; per quelli precedenti si
    legge in batch la fattura collegata. Il collegamento esplicito evita di
    associare per errore fatture diverse che condividono lo stesso numero.
    """
    riferimenti = set()
    for movimento in movimenti:
        fattura_id = movimento.get("fattura_id")
        riferimento = str(movimento.get("riferimento") or "")
        if not fattura_id and riferimento.startswith("FATT-"):
            fattura_id = riferimento[5:]
        if fattura_id:
            riferimenti.add(fattura_id)
            movimento["_fattura_id_arricchimento"] = fattura_id

    if not riferimenti:
        return

    fatture = await db["invoices"].find(
        {"$or": [
            {"id": {"$in": list(riferimenti)}},
            {"invoice_key": {"$in": list(riferimenti)}},
        ]},
        {"_id": 0, "id": 1, "invoice_key": 1, "invoice_number": 1,
         "numero_fattura": 1, "invoice_date": 1, "data_fattura": 1,
         "supplier_name": 1, "cedente_denominazione": 1},
    ).to_list(max(1, len(riferimenti) * 2))

    per_riferimento = {}
    for fattura in fatture:
        for chiave in (fattura.get("id"), fattura.get("invoice_key")):
            if chiave:
                per_riferimento[chiave] = fattura

    for movimento in movimenti:
        fattura = per_riferimento.get(movimento.pop("_fattura_id_arricchimento", None))
        if not fattura:
            continue
        if not movimento.get("numero_fattura"):
            movimento["numero_fattura"] = fattura.get("invoice_number") or fattura.get("numero_fattura") or ""
        if not movimento.get("fornitore"):
            movimento["fornitore"] = fattura.get("supplier_name") or fattura.get("cedente_denominazione") or ""
        if not movimento.get("data_fattura"):
            movimento["data_fattura"] = fattura.get("invoice_date") or fattura.get("data_fattura") or movimento.get("data")


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


# Saldo iniziale (riporto) inserito A MANO dall'utente per (cassa|banca, anno).
# Richiesta utente 16/07/2026: "il 2 gennaio 2026 il saldo deve essere
# modificabile perché io ho il riporto nel 2025" — il riporto calcolato dai
# movimenti degli anni precedenti non è affidabile quando lo storico a
# sistema è parziale (es. solo uscite di vecchi backfill). Se per un anno
# esiste un saldo iniziale manuale, SOSTITUISCE il riporto calcolato.
COLLECTION_SALDI_INIZIALI = "prima_nota_saldi_iniziali"
_COLLECTION_A_TIPO = {"prima_nota_cassa": "cassa", "prima_nota_banca": "banca"}


async def get_saldo_iniziale_manuale(db, collection: str, anno: int):
    """Saldo iniziale manuale per (collection, anno), None se non impostato."""
    tipo = _COLLECTION_A_TIPO.get(collection)
    if not tipo or not anno:
        return None
    doc = await db[COLLECTION_SALDI_INIZIALI].find_one({"tipo": tipo, "anno": int(anno)})
    if doc is None or doc.get("importo") is None:
        return None
    return float(doc["importo"])


async def aggrega_saldo_prima_nota(db, collection: str, query: Dict[str, Any],
                                   anno: int = None,
                                   query_base_precedente: Dict[str, Any] = None) -> Dict[str, float]:
    """Funzione UNICA di saldo Prima Nota (§6.4) — cassa/banca/estratto conto usano questa.

    Uniforma segno, saldo iniziale (riporto anni precedenti) e saldo finale:
      saldo_anno   = entrate − uscite (sui movimenti che soddisfano `query`)
      saldo_iniziale = riporto manuale dell'anno se impostato dall'utente,
                       altrimenti riporto cumulato degli anni precedenti
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
    saldo_manuale = await get_saldo_iniziale_manuale(db, collection, anno) if anno else None
    if saldo_manuale is not None:
        saldo_precedente = saldo_manuale
    else:
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
        "saldo_iniziale_manuale": saldo_manuale is not None,
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
            **ESCLUSIONI_PRIMA_NOTA,
        }
    query = {**query_base, "data": {"$lt": f"{anno}-01-01"}}

    totals = await db[collection].aggregate(_pipeline_entrate_uscite(query)).to_list(1)
    
    if totals:
        return totals[0].get("entrate", 0) - totals[0].get("uscite", 0)
    return 0.0
