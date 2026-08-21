"""
Prima Nota Module - Costanti e utility condivise.
"""
from typing import Dict, Any, Optional
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

# Source da escludere nei conteggi generali:
#  - chiusura_pos_mobile / import_manuale_pos sono evidenze di verifica POS,
#    non un secondo movimento finanziario;
#  - estratto_conto_sync e' la copia legacy dell'estratto conto e
#    duplicherebbe i movimenti gestionali gia' registrati.
#
# La quota POS lorda (corrispettivo_pos/corrispettivi_sync) non e' liquidita'
# bancaria: apre un credito verso il gestore. Resta visibile nei conti POS
# dedicati ma viene esclusa dal solo saldo dei conti bancari reali tramite
# ESCLUSIONI_SALDO_REALE.
SOURCES_ESCLUSE = ["chiusura_pos_mobile", "import_manuale_pos", "estratto_conto_sync"]

# Esclusioni standard complete della Prima Nota (da spargere con ** nelle
# query dei chiamanti, insieme al filtro status deleted/archived).
ESCLUSIONI_PRIMA_NOTA = {
    "categoria": {"$nin": CATEGORIE_ESCLUSE},
    "source": {"$nin": SOURCES_ESCLUSE},
}

# Decisione utente 07/08/2026: i crediti POS restano FUORI dal saldo bancario
# reale. Il saldo di un conto deve contenere solo cio' che e' davvero
# transitato: l'incasso elettronico del giorno e' un credito verso il gestore
# finche' non viene versato (su BPM per Nexi, sulla Mastercard per SumUp).
#
# ATTENZIONE — questo e' lo STESSO meccanismo del bug del 16/07/2026, quando
# escludere il trasferimento POS fece sparire ~204.000 EUR dai saldi. La
# differenza, e la ragione per cui adesso e' corretto, e' che quel denaro non
# scompare: confluisce nei saldi dedicati "Crediti POS", esposti accanto ai
# conti reali da saldi_finanziari(). Se un giorno si togliesse quella
# esposizione, si ricreerebbe il bug.
SOURCES_CREDITO_POS = ["trasferimento_pos", "corrispettivo_pos", "corrispettivi_sync"]
NATURA_CREDITO_POS = "credito_pos"

# Righe che NON sono liquidita' su un conto reale.
FILTRO_CREDITO_POS = {"$or": [
    {"natura": NATURA_CREDITO_POS},
    {"source": {"$in": SOURCES_CREDITO_POS}},
]}

# Da unire con ** alle query dei saldi bancari reali.
ESCLUSIONI_SALDO_REALE = {
    "categoria": {"$nin": CATEGORIE_ESCLUSE},
    # Un costo trattenuto dal gestore non e' mai transitato sul conto:
    # resta in contabilita' economica, non nella tesoreria.
    "natura": {"$nin": [NATURA_CREDITO_POS, "costo"]},
    "source": {"$nin": SOURCES_ESCLUSE + SOURCES_CREDITO_POS},
}


def esclusioni_saldo_per_collection(collection: str) -> Dict[str, Any]:
    """Restituisce le esclusioni corrette per il luogo finanziario.

    La cassa usa le esclusioni generali. La banca reale esclude anche i
    crediti POS lordi, che appartengono ai conti transitori dei gestori e non
    alla liquidita' BPM/Mastercard finche' non avviene l'accredito.
    """
    if collection == COLLECTION_PRIMA_NOTA_BANCA:
        return {
            "categoria": {"$nin": list(CATEGORIE_ESCLUSE)},
            "natura": {"$nin": [NATURA_CREDITO_POS, "costo"]},
            "source": {"$nin": list(SOURCES_ESCLUSE + SOURCES_CREDITO_POS)},
        }
    return {
        "categoria": {"$nin": list(CATEGORIE_ESCLUSE)},
        "source": {"$nin": list(SOURCES_ESCLUSE)},
    }


def filtro_saldo_prima_nota(collection: str, **extra: Any) -> Dict[str, Any]:
    """Filtro canonico per qualsiasi saldo/riepilogo di Prima Nota."""
    return {
        "status": {"$nin": ["deleted", "archived"]},
        **esclusioni_saldo_per_collection(collection),
        **extra,
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


async def _totali_entrate_uscite(db, collection: str,
                                  query: Dict[str, Any]) -> tuple[float, float]:
    """Somma entrate/uscite su Mongo e sul runtime Drive/Sheets.

    MongoDB esegue la pipeline sul server. Il database in memoria usato dal
    backend Sheets non implementa ``$convert``: in quel caso leggiamo i soli
    campi necessari e applichiamo la stessa conversione tollerante in Python.
    """
    try:
        totals = await db[collection].aggregate(
            _pipeline_entrate_uscite(query)
        ).to_list(1)
        if not totals:
            return 0.0, 0.0
        return (
            float(totals[0].get("entrate", 0) or 0),
            float(totals[0].get("uscite", 0) or 0),
        )
    except NotImplementedError:
        cursor = db[collection].find(
            query, {"_id": 0, "tipo": 1, "importo": 1},
        )
        rows = (await cursor.to_list(100000) if hasattr(cursor, "to_list")
                else [row async for row in cursor])
        entrate = 0.0
        uscite = 0.0
        for row in rows:
            try:
                importo = float(row.get("importo") or 0)
            except (TypeError, ValueError):
                continue
            if row.get("tipo") == "entrata":
                entrate += importo
            elif row.get("tipo") == "uscita":
                uscite += importo
        return entrate, uscite


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

    Le esclusioni fanno parte di `query`, costruita dal chiamante tramite
    filtro_saldo_prima_nota(). Per il riporto: con
    `query_base_precedente=None` (default, Prima Nota cassa/banca) si applicano
    automaticamente le esclusioni proprie della collection; per la banca
    vengono esclusi anche i crediti POS virtuali;
    passando un dict (es. {} per l'estratto conto, che non ha soft-delete né categorie
    escluse) il riporto usa quelle condizioni + data < 1/1/anno.
    Ritorna importi già arrotondati a 2 decimali.
    """
    entrate, uscite = await _totali_entrate_uscite(db, collection, query)
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


async def saldi_finanziari(db, anno: int = None) -> Dict[str, Any]:
    """Schede finanziarie separate, mai sommate in un unico numero.

    Restituisce un conto reale per ogni luogo dove il denaro sta davvero
    (Banca BPM, Mastercard SumUp) e un credito per ogni gestore che deve
    ancora versare. Il totale delle disponibilita' liquide comprende solo i
    conti reali: un credito non e' liquidita' finche' non e' accreditato.
    """
    from app.services import conti_pos

    base: Dict[str, Any] = {
        "status": {"$nin": ["deleted", "archived"]},
        "categoria": {"$nin": CATEGORIE_ESCLUSE},
    }
    if anno:
        base["data"] = {"$regex": f"^{int(anno)}-"}

    async def _saldo(query: Dict[str, Any]) -> float:
        # Somma in Python invece che in aggregate: sono le righe di una
        # singola scheda di tesoreria, non l'intero registro, e cosi' il
        # calcolo non dipende da $convert (assente in mongomock, quindi
        # altrimenti non verificabile nei test).
        cursore = db["prima_nota_banca"].find(
            {**base, **query}, {"_id": 0, "tipo": 1, "importo": 1})
        righe = (await cursore.to_list(100000) if hasattr(cursore, "to_list")
                 else [r async for r in cursore])
        totale = 0.0
        for riga in righe:
            try:
                importo = float(riga.get("importo") or 0)
            except (TypeError, ValueError):
                continue
            totale += importo if riga.get("tipo") == "entrata" else -importo
        return round(totale, 2)

    conti_reali = []
    for codice, nome in ((conti_pos.CONTO_BPM, "Banca BPM"),
                         (conti_pos.CONTO_SUMUP_MASTERCARD, "Mastercard SumUp")):
        if codice == conti_pos.CONTO_BPM:
            # Le righe storiche non hanno conto_contabile: sono tutte BPM,
            # unico conto esistito finora.
            appartenenza = {"$or": [
                {"conto_contabile": codice},
                {"conto_contabile": {"$in": [None, ""]}},
                {"conto_contabile": {"$exists": False}},
            ]}
        else:
            appartenenza = {"conto_contabile": codice}
        conti_reali.append({
            "codice": codice,
            "nome": nome,
            "tipo": "conto_reale",
            "saldo": await _saldo({**ESCLUSIONI_SALDO_REALE, **appartenenza}),
        })

    crediti = []
    for circuito in conti_pos.circuiti_attivi():
        codice = conti_pos.conto_credito(circuito)
        # Saldo algebrico: l'apertura del credito e' un'entrata, la chiusura
        # (quando il gestore versa) e' un'uscita di pari importo. Il saldo
        # residuo e' quindi, per costruzione, quanto il gestore deve ancora.
        if circuito == conti_pos.NEXI:
            # Storico senza campo gestore: e' Nexi, unico circuito finora.
            appartenenza = {"$and": [{"$or": [
                {"gestore": circuito},
                {"gestore": {"$in": [None, ""]}},
                {"gestore": {"$exists": False}},
            ]}]}
        else:
            appartenenza = {"gestore": circuito}
        aperti = {**FILTRO_CREDITO_POS, **appartenenza}
        crediti.append({
            "codice": codice,
            "nome": conti_pos.descrizione_conto(codice),
            "tipo": "credito_pos",
            "circuito": circuito,
            "saldo": await _saldo(aperti),
        })

    return {
        "anno": anno,
        "conti_reali": conti_reali,
        "crediti_pos": crediti,
        "disponibilita_liquide": round(
            sum(c["saldo"] for c in conti_reali), 2),
        "crediti_pos_aperti": round(sum(c["saldo"] for c in crediti), 2),
    }


async def calcola_saldo_anni_precedenti(db, collection: str, anno: int,
                                        query_base: Dict[str, Any] = None) -> float:
    """
    Calcola il saldo cumulativo di tutti gli anni precedenti all'anno specificato.
    Questo è il "riporto" o "saldo iniziale" dell'anno.

    `query_base=None` (default) applica le esclusioni canoniche della collection
    (inclusi i crediti POS virtuali per la banca); un dict esplicito, anche
    vuoto, le sostituisce (usato dall'estratto conto).
    """
    if not anno:
        return 0.0

    if query_base is None:
        query_base = filtro_saldo_prima_nota(collection)
    query = {**query_base, "data": {"$lt": f"{anno}-01-01"}}

    entrate, uscite = await _totali_entrate_uscite(db, collection, query)
    return entrate - uscite


# REGOLA PRIMA NOTA BANCA (utente 07/08/2026): la Prima Nota non e' una copia
# dell'estratto conto. Un pagamento entra quando si sa A COSA si riferisce —
# una fattura, un cedolino, un F24, un assegno, un trasferimento POS. Finche'
# non lo si sa resta nella coda "da riconciliare", non in Prima Nota.
#
# L'eccezione sotto non e' una scorciatoia: sono i movimenti che un documento
# non ce l'hanno e non possono averlo. Le competenze del trimestre, il bollo,
# il prelievo al bancomat sono operazioni della banca stessa. Tenerli fuori
# non renderebbe la Prima Nota piu' pulita: la renderebbe SBAGLIATA, perche'
# quel denaro dal conto e' uscito davvero e il saldo non tornerebbe mai.
CATEGORIE_SENZA_DOCUMENTO = frozenset({
    "Commissioni bancarie",
    "Prelevamento Banca",
})


def entra_in_prima_nota(categoria: Optional[str]) -> bool:
    """Se il movimento puo' entrare in Prima Nota senza un documento dietro."""
    return str(categoria or "").strip() in CATEGORIE_SENZA_DOCUMENTO
