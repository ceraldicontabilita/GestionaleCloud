"""
Router per gestione estratti conto PayPal (MSR/CSR).
Import PDF, visualizzazione transazioni, riconciliazione con estratto conto bancario.
"""
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import calendar
import os
import logging
import re

from app.database import Database
from app.db_collections import (
    COLL_ESTRATTO_CONTO,
    COLL_INVOICES,
    COLL_FORNITORI,
    COLL_EMPLOYEES
)
from app.services.paypal_invoice_matching import evaluate_paypal_invoice_match
from app.services.payment_invoice_matching import amounts_equal_to_cent
from app.services.paypal_reconciliation_links import (
    associa_transazione_univoca,
    finalizza_transazione_paypal_se_completa,
    is_successful_paypal_payment,
    riprocessa_collegamenti_paypal,
    supplier_mapping_for_transaction,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Collection PayPal
COLL_PAYPAL_STATEMENTS = "paypal_statements"
COLL_PAYPAL_TRANSACTIONS = "paypal_transactions"

SAFE_INVOICE_MATCHES = {
    "manuale_validato",
    "fornitore_numero_importo_esatti",
}
SUPPLIER_EVIDENCE = {
    "partita_iva_o_cf",
    "denominazione_fornitore",
    "email_fornitore",
}

UPLOAD_DIR = "/tmp/uploads/msr_statements"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _backfill_controparte(transactions: List[Dict[str, Any]]) -> None:
    """Completa nome_controparte/email_controparte mancanti usando altre
    transazioni con lo stesso paypal_account_id.

    PayPal non riporta sempre il payer_name su ogni singola transazione dello
    stesso account (es. eventi 'carta ospite' T0200): se un'altra transazione
    con lo stesso account_id lo conosce, è certamente la stessa controparte
    reale, quindi lo riusiamo invece di lasciare il dato vuoto.
    """
    per_account: Dict[str, Dict[str, str]] = {}
    for t in transactions:
        acc = t.get("paypal_account_id")
        if not acc:
            continue
        entry = per_account.setdefault(acc, {})
        if t.get("nome_controparte") and "nome_controparte" not in entry:
            entry["nome_controparte"] = t["nome_controparte"]
        if t.get("email_controparte") and "email_controparte" not in entry:
            entry["email_controparte"] = t["email_controparte"]

    for t in transactions:
        acc = t.get("paypal_account_id")
        known = per_account.get(acc) if acc else None
        if not known:
            continue
        if not t.get("nome_controparte") and known.get("nome_controparte"):
            t["nome_controparte"] = known["nome_controparte"]
        if not t.get("email_controparte") and known.get("email_controparte"):
            t["email_controparte"] = known["email_controparte"]


def _stato_collegamento_fattura(transaction: Dict[str, Any]) -> str:
    """Distingue un collegamento provato da un riferimento storico da rivalidare.

    Le vecchie versioni potevano salvare collegamenti basati su importo o nome
    approssimativo. Non cancelliamo la traccia in lettura, ma non la esponiamo
    come fattura riconciliata finche' le evidenze salvate non provano
    contemporaneamente fornitore, numero fattura e importo al centesimo.
    """
    link = transaction.get("fattura_associata") or {}
    if not link:
        return "non_associata"
    evidenze = set(link.get("evidenze") or [])
    match = str(link.get("match") or "")
    strict_reference_match = (
        match in SAFE_INVOICE_MATCHES
        and {"numero_fattura", "importo"}.issubset(evidenze)
        and bool(evidenze & SUPPLIER_EVIDENCE)
    )
    unique_date_match = (
        match == "fornitore_importo_data_univoci"
        and {"importo", "data_entro_120_giorni"}.issubset(evidenze)
        and bool(evidenze & SUPPLIER_EVIDENCE)
    )
    if strict_reference_match or unique_date_match:
        return "associata_validata"
    return "da_rivalidare"


def _data_documento(doc: Dict[str, Any]) -> Optional[datetime]:
    """Normalizza le date dei due schemi PayPal e dell'estratto conto."""
    value = (
        doc.get("data")
        or doc.get("data_contabile")
        or doc.get("booking_date")
        or doc.get("initiation_date")
        or doc.get("transaction_initiation_date")
    )
    if not value:
        return None
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt)
        except (TypeError, ValueError):
            continue
    return None


def _importo_paypal(tx: Dict[str, Any]) -> float:
    """Importo EUR canonico, compatibile con statement e API Reporting."""
    for field in ("importo_eur", "lordo", "importo"):
        value = tx.get(field)
        if value not in (None, ""):
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _pagamenti_paypal_in_euro(
    transactions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Restituisce una sola riga contabile per ciascun pagamento PayPal.

    Le operazioni in valuta generano un pagamento nella valuta originaria e
    una o piu' gambe tecniche T02 di conversione. Il report deve usare la
    gamba EUR collegata come importo del pagamento, senza contare anche la
    conversione come un secondo acquisto.
    """
    _backfill_controparte(transactions)
    conversioni_per_riferimento: Dict[str, List[Dict[str, Any]]] = {}
    for tx in transactions:
        tipo = str(tx.get("tipo") or tx.get("event_code") or "")
        riferimento = str(tx.get("paypal_reference_id") or "")
        if riferimento and tipo.startswith("T02"):
            conversioni_per_riferimento.setdefault(riferimento, []).append(tx)

    pagamenti: List[Dict[str, Any]] = []
    for tx in transactions:
        if not is_successful_paypal_payment(tx):
            continue
        tipo = str(tx.get("tipo") or tx.get("event_code") or "")
        if tipo.startswith("T02"):
            continue
        importo = _importo_paypal(tx)
        valuta = str(tx.get("currency") or tx.get("valuta") or "EUR").upper()
        if valuta != "EUR":
            gambe = conversioni_per_riferimento.get(
                str(tx.get("transaction_id") or tx.get("id") or ""), []
            )
            gamba_eur = next(
                (
                    g
                    for g in gambe
                    if str(g.get("currency") or g.get("valuta") or "").upper()
                    == "EUR"
                    and (_importo_paypal(g) < 0) == (importo < 0)
                ),
                None,
            )
            if gamba_eur:
                importo = _importo_paypal(gamba_eur)
        if importo >= 0:
            continue
        pagamento = dict(tx)
        pagamento["importo_report_eur"] = round(importo, 2)
        pagamenti.append(pagamento)
    return pagamenti


def _descrizione_banca(mov: Dict[str, Any]) -> str:
    return str(mov.get("descrizione_originale") or mov.get("descrizione") or "")


def _direzione_movimento_banca(mov: Dict[str, Any]) -> str:
    """Normalizza la direzione senza dedurla dal solo segno dell'importo.

    Gli import Banco BPM e Nexi conservano spesso gli addebiti come importi
    positivi e affidano la direzione al campo ``tipo``. La causale e' usata
    solo come fallback per vecchi record che non hanno quel campo.
    """
    tipo = str(mov.get("tipo") or "").strip().lower()
    if tipo in {"uscita", "addebito", "carta_credito", "pagamento"}:
        return "uscita"
    if tipo in {"entrata", "accredito", "incasso"}:
        return "entrata"
    descrizione = _descrizione_banca(mov).lower()
    if re.search(r"\b(addebito|sdd|pagamento|paypalpag)\b", descrizione):
        return "uscita"
    if re.search(r"\b(bon\.da|bonif(?:ico)?\.?\s+vs\.?\s+favore|accredito)\b", descrizione):
        return "entrata"
    try:
        return "uscita" if float(mov.get("importo") or 0) < 0 else "entrata"
    except (TypeError, ValueError):
        return "entrata"


def _descrizione_paypal_canonica(mov: Dict[str, Any]) -> str:
    """Riduce le varianti dello stesso testo bancario a una chiave stabile."""
    text = _descrizione_banca(mov).lower().strip()
    text = re.sub(r"^addebito\s+diretto\s+sdd\s*-\s*", "", text)
    text = re.sub(r"^bonif\.?\s+vs\.?\s+favore\s*-\s*", "", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def _chiave_movimento_paypal(mov: Dict[str, Any]) -> tuple:
    try:
        cents = int(round(abs(float(mov.get("importo") or 0)) * 100))
    except (TypeError, ValueError):
        cents = 0
    return (
        str(mov.get("data") or mov.get("data_contabile") or "")[:10],
        cents,
        _direzione_movimento_banca(mov),
        _descrizione_paypal_canonica(mov),
    )


def _rappresentazione_movimento_paypal(mov: Dict[str, Any]) -> tuple:
    return (
        re.sub(r"[^a-z0-9]+", "", _descrizione_banca(mov).lower()),
        str(mov.get("tipo") or "").strip().lower(),
        re.sub(r"[^a-z0-9]+", "", str(mov.get("banca") or "").lower()),
    )


def _deduplica_movimenti_banca_paypal(
    movimenti: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Unifica fonti equivalenti senza cancellare alcuna prova.

    Se la stessa operazione e' presente in piu' formati (per esempio Banco
    BPM e Nexi), conserva la massima molteplicita' osservata in una singola
    rappresentazione. In questo modo due pagamenti realmente identici nello
    stesso giorno restano due, mentre la loro seconda importazione non li
    raddoppia.
    """
    groups: Dict[tuple, List[Dict[str, Any]]] = {}
    for movimento in movimenti:
        groups.setdefault(_chiave_movimento_paypal(movimento), []).append(movimento)

    canonical: List[Dict[str, Any]] = []
    for rows in groups.values():
        representation_counts: Dict[tuple, int] = {}
        for row in rows:
            representation = _rappresentazione_movimento_paypal(row)
            representation_counts[representation] = representation_counts.get(representation, 0) + 1
        keep_count = max(representation_counts.values(), default=1)

        def rank(row: Dict[str, Any]) -> tuple:
            linked = bool(row.get("paypal_transaction_id") or row.get("riconciliato"))
            bank_type = str(row.get("tipo") or "").lower() in {"uscita", "entrata"}
            return (
                int(linked),
                int(bool(row.get("rapporto"))),
                int(bank_type),
                len(_descrizione_banca(row)),
                str(row.get("updated_at") or row.get("created_at") or ""),
            )

        selected = sorted(rows, key=rank, reverse=True)[:keep_count]
        source_ids = [_id_movimento(row) for row in rows if _id_movimento(row)]
        for row in selected:
            item = dict(row)
            item["paypal_duplicate_source_ids"] = source_ids
            item["paypal_duplicate_sources_unified"] = len(rows) - keep_count
            canonical.append(item)

    canonical.sort(
        key=lambda row: str(row.get("data") or row.get("data_contabile") or ""),
        reverse=True,
    )
    return canonical


def _id_movimento(mov: Dict[str, Any]) -> str:
    return str(mov.get("id") or mov.get("_id") or "")


def _score_match_banca(tx: Dict[str, Any], mov: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Valuta un collegamento PayPal-banca senza accettare l'importo da solo.

    Sono sufficienti importo esatto, segno coerente e data vicina; un ID
    PayPal presente nella causale e' una prova ancora piu' forte. A parita'
    di score il chiamante lascia il movimento non riconciliato.
    """
    # Per pagamenti in valuta estera il movimento bancario e' in EUR: il
    # report canonico espone la gamba EUR della conversione in questo campo.
    # Senza questa precedenza una spesa USD non potrebbe mai combaciare con
    # il relativo addebito bancario in euro.
    try:
        tx_amount = float(tx.get("importo_report_eur") or 0)
    except (TypeError, ValueError):
        tx_amount = 0
    if not tx_amount:
        tx_amount = _importo_paypal(tx)
    try:
        mov_amount = float(mov.get("importo") or 0)
    except (TypeError, ValueError):
        return None
    movimento_uscita = _direzione_movimento_banca(mov) == "uscita"
    transazione_uscita = tx_amount < 0
    if not tx_amount or not mov_amount or movimento_uscita != transazione_uscita:
        return None

    descrizione = _descrizione_banca(mov).lower()
    riferimenti = {
        str(tx.get("transaction_id") or "").lower(),
        str(tx.get("paypal_reference_id") or "").lower(),
        str(tx.get("reference_id") or "").lower(),
    } - {""}
    riferimento_esplicito = next((r for r in riferimenti if len(r) >= 8 and r in descrizione), None)

    importo_esatto = amounts_equal_to_cent(tx_amount, mov_amount)
    if not importo_esatto:
        return None

    tx_date = _data_documento(tx)
    mov_date = _data_documento(mov)
    if not tx_date or not mov_date:
        return None
    delta = abs((tx_date - mov_date).days)
    if delta > 10 and not riferimento_esplicito:
        return None

    score = 10  # segno coerente
    evidenze = ["segno_coerente"]
    if importo_esatto:
        score += 55
        evidenze.append("importo_esatto")
    if riferimento_esplicito:
        score += 100
        evidenze.append("riferimento_paypal_in_causale")
    if delta == 0:
        score += 30
        evidenze.append("stessa_data")
    elif delta <= 3:
        score += 24
        evidenze.append("data_entro_3_giorni")
    elif delta <= 7:
        score += 15
        evidenze.append("data_entro_7_giorni")
    elif delta <= 10:
        score += 5
        evidenze.append("data_entro_10_giorni")

    return {"score": score, "evidenze": evidenze, "delta_giorni": delta}


@router.get("/statements")
async def get_paypal_statements(
    anno: Optional[int] = None,
    limit: int = Query(default=100, le=500)
):
    """Restituisce documenti PayPal e periodi API senza confonderne la fonte.

    Un periodo sincronizzato tramite PayPal Reporting API e' una fonte
    strutturata, ma non e' un PDF/CSV: viene quindi esposto in ``fonti`` senza
    creare un documento fittizio nella collection degli statement.
    """
    db = Database.get_db()
    query = {}
    if anno:
        query["anno"] = anno
    
    statements = await db[COLL_PAYPAL_STATEMENTS].find(
        query, {"_id": 0}
    ).sort("periodo_inizio", -1).limit(limit).to_list(limit)
    
    tx_query: Dict[str, Any] = {"source": "paypal_api"}
    if anno:
        tx_query["data"] = {"$regex": f"^{anno}"}
    api_transactions = await db[COLL_PAYPAL_TRANSACTIONS].find(
        tx_query, {"_id": 0}
    ).sort("data", -1).limit(10000).to_list(10000)

    raw_per_month: Dict[str, List[Dict[str, Any]]] = {}
    for tx in api_transactions:
        date_value = _data_documento(tx)
        if not date_value:
            continue
        key = date_value.strftime("%Y-%m")
        raw_per_month.setdefault(key, []).append(tx)

    api_sources = []
    for key, rows in sorted(raw_per_month.items(), reverse=True):
        year_value, month_value = (int(part) for part in key.split("-"))
        payments = _pagamenti_paypal_in_euro(rows)
        api_sources.append({
            "id": f"paypal-api-{key}",
            "source_type": "api",
            "tipo_documento": "API",
            "periodo_inizio": f"{key}-01",
            "periodo_fine": (
                f"{key}-{calendar.monthrange(year_value, month_value)[1]:02d}"
            ),
            "totale_transazioni": len(rows),
            "totale_pagamenti": len(payments),
            "riepilogo": {
                "pagamenti_inviati": round(
                    abs(sum(float(p.get("importo_report_eur") or 0) for p in payments)),
                    2,
                ),
                "depositi_accrediti": None,
                "saldo_finale": None,
            },
            "file_name": None,
            "source": "paypal_api",
            "documento_presente": False,
        })

    document_sources = [
        {
            **statement,
            "source_type": "documento",
            "documento_presente": True,
        }
        for statement in statements
    ]
    return {
        "statements": statements,
        "fonti": api_sources + document_sources,
        "totale": len(statements),
        "totale_fonti": len(api_sources) + len(document_sources),
        "totale_periodi_api": len(api_sources),
    }


@router.get("/bank-movements")
async def get_paypal_bank_movements(
    anno: Optional[int] = None,
    search: Optional[str] = None,
    stato: str = Query(default="tutti", pattern="^(tutti|riconciliati|da_associare)$"),
    direzione: str = Query(default="tutte", pattern="^(tutte|uscite|entrate)$"),
    limit: int = Query(default=1000, le=5000),
):
    """Espone le righe bancarie PayPal, distinte dai documenti MSR/CSV."""
    db = Database.get_db()
    paypal_filter: Dict[str, Any] = {"$or": [
        {"descrizione": {"$regex": "paypal", "$options": "i"}},
        {"descrizione_originale": {"$regex": "paypal", "$options": "i"}},
    ]}
    query: Dict[str, Any] = paypal_filter
    if anno:
        query = {"$and": [paypal_filter, {"$or": [
            {"data": {"$regex": f"^{anno}"}},
            {"data_contabile": {"$regex": f"^{anno}"}},
        ]}]}

    movimenti_raw = await db[COLL_ESTRATTO_CONTO].find(query, {"_id": 0}).sort("data", -1).to_list(limit)
    ids = {_id_movimento(m) for m in movimenti_raw} - {""}
    tx_collegate = await db[COLL_PAYPAL_TRANSACTIONS].find(
        {"$or": [
            {"movimento_banca_id": {"$in": list(ids)}},
            {"estratto_conto_movimento_id": {"$in": list(ids)}},
        ]},
        {"_id": 0, "transaction_id": 1, "movimento_banca_id": 1,
         "estratto_conto_movimento_id": 1},
    ).to_list(limit) if ids else []
    tx_per_movimento: Dict[str, str] = {}
    for tx in tx_collegate:
        mid = str(tx.get("movimento_banca_id") or tx.get("estratto_conto_movimento_id") or "")
        if mid:
            tx_per_movimento[mid] = str(tx.get("transaction_id") or "")

    # Annota i link prima della deduplica, cosi una prova gia riconciliata
    # prevale sulla sua copia importata da un'altra fonte.
    movimenti_annotati = []
    for movimento in movimenti_raw:
        item = dict(movimento)
        mid = _id_movimento(item)
        if not item.get("paypal_transaction_id") and tx_per_movimento.get(mid):
            item["paypal_transaction_id"] = tx_per_movimento[mid]
        movimenti_annotati.append(item)
    movimenti = _deduplica_movimenti_banca_paypal(movimenti_annotati)

    output = []
    riconciliati_totali = 0
    search_norm = (search or "").strip().lower()
    for mov in movimenti:
        mov_id = _id_movimento(mov)
        tx_id = str(mov.get("paypal_transaction_id") or tx_per_movimento.get(mov_id) or "")
        riconciliato = bool(tx_id)
        if riconciliato:
            riconciliati_totali += 1
        try:
            amount_abs = abs(float(mov.get("importo") or 0))
        except (TypeError, ValueError):
            amount_abs = 0.0
        movimento_direzione = _direzione_movimento_banca(mov)
        amount = -amount_abs if movimento_direzione == "uscita" else amount_abs
        if stato == "riconciliati" and not riconciliato:
            continue
        if stato == "da_associare" and riconciliato:
            continue
        if direzione == "uscite" and amount >= 0:
            continue
        if direzione == "entrate" and amount <= 0:
            continue
        descrizione = _descrizione_banca(mov)
        if search_norm and search_norm not in f"{descrizione} {tx_id} {mov_id}".lower():
            continue
        output.append({
            "id": mov_id,
            "data": str(mov.get("data") or mov.get("data_contabile") or "")[:10],
            "descrizione": descrizione,
            "importo": amount,
            "direzione": movimento_direzione,
            "riconciliato_paypal": riconciliato,
            "paypal_transaction_id": tx_id or None,
            "tipo_riconciliazione": mov.get("tipo_riconciliazione"),
            "riconciliazione_evidenze": mov.get("riconciliazione_evidenze") or [],
            "duplicati_unificati": int(mov.get("paypal_duplicate_sources_unified") or 0),
            "fonti_movimento_ids": mov.get("paypal_duplicate_source_ids") or [mov_id],
        })

    duplicati_unificati = len(movimenti_raw) - len(movimenti)
    return {
        "anno": anno,
        "movimenti": output,
        "totale": len(output),
        "totale_banca_paypal": len(movimenti),
        "totale_banca_paypal_raw": len(movimenti_raw),
        "duplicati_unificati": duplicati_unificati,
        "riconciliati": riconciliati_totali,
        "da_associare": len(movimenti) - riconciliati_totali,
    }


@router.get("/transactions")
async def get_paypal_transactions(
    anno: Optional[int] = None,
    mese: Optional[int] = None,
    tipo: Optional[str] = None,
    solo_pagamenti: bool = False,
    limit: int = Query(default=500, le=2000)
):
    """Restituisce le transazioni PayPal."""
    db = Database.get_db()
    query = {}
    
    if anno:
        query["data"] = {"$regex": f"^{anno}"}
    if anno and mese:
        query["data"] = {"$regex": f"^{anno}-{mese:02d}"}
    if tipo:
        query["tipo"] = tipo
    if solo_pagamenti:
        query["lordo"] = {"$lt": 0}

    transactions = await db[COLL_PAYPAL_TRANSACTIONS].find(
        query, {"_id": 0}
    ).sort("data", -1).limit(limit).to_list(limit)

    _backfill_controparte(transactions)

    # ── Conversioni valuta (eventi T02xx) ──────────────────────────────────
    # Un pagamento in valuta estera (es. MongoDB in USD) genera DUE gambe di
    # conversione T0200: -EUR e +USD. In lista compariva quindi una "seconda
    # riga" senza controparte con un importo diverso (l'EUR reale) accanto al
    # pagamento USD mostrato col simbolo €. Qui accoppiamo le gambe al
    # pagamento (paypal_reference_id) e:
    #  - sul pagamento estero scriviamo importo_eur + valuta originale;
    #  - marchiamo le gambe T02xx accoppiate (is_conversione) e con
    #    solo_pagamenti le togliamo dalla lista (il loro valore è già
    #    mostrato sul pagamento). Le conversioni orfane restano visibili.
    per_riferimento: Dict[str, List[Dict[str, Any]]] = {}
    for t in transactions:
        ref = t.get("paypal_reference_id")
        if ref and str(t.get("tipo", "")).startswith("T02"):
            per_riferimento.setdefault(ref, []).append(t)

    for t in transactions:
        if str(t.get("tipo", "")).startswith("T02"):
            continue
        valuta = t.get("currency")
        if not valuta or valuta == "EUR":
            continue
        gambe = per_riferimento.get(t.get("transaction_id"), [])
        gamba_eur = next(
            (g for g in gambe if g.get("currency") == "EUR"
             and (g.get("lordo", 0) < 0) == (t.get("lordo", 0) < 0)),
            None,
        )
        if gamba_eur:
            t["importo_eur"] = gamba_eur.get("lordo")
            t["importo_valuta"] = t.get("lordo")
            t["valuta_originale"] = valuta
            for g in gambe:
                g["is_conversione"] = True
                g["conversione_di"] = t.get("transaction_id")

    if solo_pagamenti:
        transactions = [t for t in transactions if not t.get("is_conversione")]

    for transaction in transactions:
        transaction["stato_collegamento_fattura"] = _stato_collegamento_fattura(
            transaction
        )

    # Descrizione leggibile: le transazioni da API PayPal non hanno il campo
    # "descrizione" ma trasportano oggetto/nota/numero fattura del fornitore.
    for t in transactions:
        if not t.get("descrizione"):
            t["descrizione"] = (
                t.get("transaction_subject")
                or t.get("transaction_note")
                or (f"Fatt. {t['invoice_id_fornitore']}" if t.get("invoice_id_fornitore") else "")
            )

    # Statistiche in EURO: per i pagamenti in valuta usa l'importo della
    # conversione (prima si sommavano USD ed EUR insieme, contando due volte
    # lo stesso pagamento: gamba valuta + gamba conversione).
    def _importo_eur(t: Dict[str, Any]) -> float:
        return float(t.get("importo_eur", t.get("lordo", 0)) or 0)

    utili = [t for t in transactions if not t.get("is_conversione")]
    totale_pagamenti = sum(_importo_eur(t) for t in utili if _importo_eur(t) < 0)
    totale_accrediti = sum(_importo_eur(t) for t in utili if _importo_eur(t) > 0)
    
    return {
        "transactions": transactions,
        "totale": len(transactions),
        "totale_pagamenti": round(totale_pagamenti, 2),
        "totale_accrediti": round(totale_accrediti, 2)
    }


@router.get("/dashboard")
async def paypal_dashboard(
    anno: Optional[int] = None
):
    """Dashboard riepilogativa PayPal."""
    db = Database.get_db()
    
    # Conta statements
    stmt_query = {"anno": anno} if anno else {}
    total_statements = await db[COLL_PAYPAL_STATEMENTS].count_documents(stmt_query)
    
    # Conta transazioni
    tx_query = {}
    if anno:
        tx_query["data"] = {"$regex": f"^{anno}"}
    total_transactions = await db[COLL_PAYPAL_TRANSACTIONS].count_documents(tx_query)
    
    # Carica entrambe le gambe: per le operazioni in valuta l'importo EUR e'
    # sulla conversione T02 collegata al pagamento originale. Filtrare subito
    # solo i valori negativi faceva sommare pagamento estero e conversione.
    tx_dashboard = await db[COLL_PAYPAL_TRANSACTIONS].find(
        tx_query,
        {"_id": 0, "lordo": 1, "tipo": 1, "nome_controparte": 1,
         "paypal_account_id": 1, "paypal_reference_id": 1,
         "transaction_id": 1, "currency": 1, "importo_eur": 1},
    ).to_list(10000)

    per_riferimento: Dict[str, List[Dict[str, Any]]] = {}
    for tx in tx_dashboard:
        ref = tx.get("paypal_reference_id")
        if ref and str(tx.get("tipo", "")).startswith("T02"):
            per_riferimento.setdefault(ref, []).append(tx)
    for tx in tx_dashboard:
        if str(tx.get("tipo", "")).startswith("T02"):
            continue
        if tx.get("currency") in (None, "", "EUR"):
            continue
        gambe = per_riferimento.get(tx.get("transaction_id"), [])
        gamba_eur = next(
            (g for g in gambe if g.get("currency") == "EUR"
             and (float(g.get("lordo") or 0) < 0) == (float(tx.get("lordo") or 0) < 0)),
            None,
        )
        if gamba_eur:
            tx["importo_eur"] = gamba_eur.get("lordo")
            for gamba in gambe:
                gamba["is_conversione"] = True

    pagamenti = [
        tx for tx in tx_dashboard
        if not tx.get("is_conversione")
        and not str(tx.get("tipo", "")).startswith("T02")
        and tx.get("tipo") != "conversione_valuta"
        and float(tx.get("importo_eur", tx.get("lordo", 0)) or 0) < 0
    ]
    _backfill_controparte(pagamenti)

    totale_speso = sum(float(p.get("importo_eur", p.get("lordo", 0)) or 0) for p in pagamenti)
    
    # Top fornitori
    fornitori_map = {}
    for p in pagamenti:
        nome = p.get('nome_controparte', 'N/D') or 'N/D'
        if nome not in fornitori_map:
            fornitori_map[nome] = {'nome': nome, 'totale': 0.0, 'count': 0}
        fornitori_map[nome]['totale'] += float(p.get("importo_eur", p.get("lordo", 0)) or 0)
        fornitori_map[nome]['count'] += 1
    
    top_fornitori = sorted(fornitori_map.values(), key=lambda x: x['totale'])[:10]
    
    # Per tipo
    tipo_map = {}
    for p in pagamenti:
        tipo = p.get('tipo', 'altro')
        if tipo not in tipo_map:
            tipo_map[tipo] = {'tipo': tipo, 'totale': 0.0, 'count': 0}
        tipo_map[tipo]['totale'] += float(p.get("importo_eur", p.get("lordo", 0)) or 0)
        tipo_map[tipo]['count'] += 1
    
    # Riconciliazione con estratto conto — conta entrambi i flag: il percorso
    # statement scrive riconciliato_banca, il percorso API sync scrive
    # riconciliato_con_estratto_banca (stessa unificazione già fatta nel
    # dettaglio transazione più sotto; senza, il KPI sottostimava le
    # transazioni riconciliate solo lato API — piano residuo op.14,
    # indagine 14/07/2026).
    riconciliati = await db[COLL_PAYPAL_TRANSACTIONS].count_documents(
        {"$and": [tx_query, {"$or": [
            {"riconciliato_banca": True},
            {"riconciliato_con_estratto_banca": True},
        ]}]}
    )
    
    # Transazioni in estratto conto bancario con PayPal
    # Stessa logica della riconciliazione: descrizione O descrizione_originale,
    # e rispetta il filtro anno selezionato (prima contava sempre tutto).
    ec_query = {"$or": [
        {"descrizione": {"$regex": "paypal", "$options": "i"}},
        {"descrizione_originale": {"$regex": "paypal", "$options": "i"}},
    ]}
    if anno:
        ec_query = {"$and": [ec_query, {"$or": [
            {"data": {"$regex": f"^{anno}"}},
            {"data_contabile": {"$regex": f"^{anno}"}},
        ]}]}
    ec_paypal_raw = await db[COLL_ESTRATTO_CONTO].find(
        ec_query, {"_id": 0}
    ).to_list(5000)
    ec_paypal = len(_deduplica_movimenti_banca_paypal(ec_paypal_raw))
    
    return {
        "total_statements": total_statements,
        "total_transactions": total_transactions,
        "totale_speso": round(totale_speso, 2),
        "totale_pagamenti": len(pagamenti),
        "top_fornitori": top_fornitori,
        "per_tipo": list(tipo_map.values()),
        "riconciliati_banca": riconciliati,
        "movimenti_banca_paypal": ec_paypal,
        "movimenti_banca_paypal_raw": len(ec_paypal_raw),
        "duplicati_banca_paypal_unificati": len(ec_paypal_raw) - ec_paypal,
        "anomalia_fonti_mancanti": total_transactions == 0 and ec_paypal > 0,
        "movimenti_banca_senza_sorgente_paypal": ec_paypal if total_transactions == 0 else 0,
        "anno_filtro": anno
    }


@router.post("/import-pdf")
async def import_paypal_pdf(file: UploadFile = File(...)):
    """Importa un PDF PayPal e applica soltanto i match univoci end-to-end."""
    from app.services.paypal_statement_import import import_paypal_statement_pdf
    
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Solo file PDF accettati")
    
    content = await file.read()
    db = Database.get_db()
    try:
        result = await import_paypal_statement_pdf(
            db,
            content,
            os.path.basename(file.filename),
            source="paypal_upload_manuale",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    
    result['collegamenti_prima'] = await riprocessa_collegamenti_paypal(db)
    ric_result = await _auto_riconcilia(db, applica=True)
    result['riconciliazione'] = ric_result
    result['collegamenti_dopo'] = await riprocessa_collegamenti_paypal(db)
    
    return result


@router.post("/import-all-local")
async def import_all_local_pdfs():
    """Importa PDF locali e applica soltanto i match univoci end-to-end."""
    from app.parsers.paypal_msr_parser import parse_paypal_msr
    
    db = Database.get_db()
    files = [f for f in os.listdir(UPLOAD_DIR) if f.lower().endswith('.pdf')]
    
    results = {
        'totale_files': len(files),
        'importati': 0,
        'transazioni_inserite': 0,
        'transazioni_duplicate': 0,
        'errori': []
    }
    
    for fname in sorted(files):
        file_path = os.path.join(UPLOAD_DIR, fname)
        try:
            parsed = parse_paypal_msr(file_path)
            if parsed['success']:
                save_result = await _save_parsed_statement(db, parsed)
                results['importati'] += 1
                results['transazioni_inserite'] += save_result.get('transazioni_inserite', 0)
                results['transazioni_duplicate'] += save_result.get('transazioni_duplicate', 0)
            else:
                results['errori'].append(f"{fname}: {parsed['errors']}")
        except Exception as e:
            results['errori'].append(f"{fname}: {str(e)}")
    
    results['collegamenti_prima'] = await riprocessa_collegamenti_paypal(db)
    ric_result = await _auto_riconcilia(db, applica=True)
    results['riconciliazione'] = ric_result
    results['collegamenti_dopo'] = await riprocessa_collegamenti_paypal(db)
    
    return results


@router.post("/import-csv")
async def import_paypal_csv(file: UploadFile = File(...)):
    """
    Importa un estratto conto PayPal esportato in CSV (formato bulk export,
    più mesi in un unico file) — alternativa a /import-pdf per chi non ha i
    PDF MSR/CSR ma solo l'export CSV. Ogni "File" nel CSV diventa uno
    statement separato; i match bancari univoci vengono applicati subito,
    mentre parita' e ambiguita' restano sospese.
    """
    from app.parsers.paypal_csv_parser import parse_paypal_csv

    if not file.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail="Solo file CSV accettati")

    content = await file.read()
    parsed = parse_paypal_csv(content)

    db = Database.get_db()
    risultati = []
    transazioni_inserite = 0
    transazioni_duplicate = 0
    for statement in parsed['statements']:
        save_result = await _save_parsed_statement(db, statement)
        risultati.append(save_result)
        transazioni_inserite += save_result.get('transazioni_inserite', 0)
        transazioni_duplicate += save_result.get('transazioni_duplicate', 0)

    collegamenti_prima = await riprocessa_collegamenti_paypal(db)
    ric_result = await _auto_riconcilia(db, applica=True)
    collegamenti_dopo = await riprocessa_collegamenti_paypal(db)

    return {
        "success": True,
        "statements_importati": len(risultati),
        "righe_totali_csv": parsed['righe_totali'],
        "righe_scartate": parsed['righe_scartate'],
        "transazioni_inserite": transazioni_inserite,
        "transazioni_duplicate": transazioni_duplicate,
        "collegamenti_prima": collegamenti_prima,
        "riconciliazione": ric_result,
        "collegamenti_dopo": collegamenti_dopo,
    }


@router.post("/riconcilia-banca")
async def riconcilia_con_banca(
    anno: Optional[int] = None,
    conferma: bool = Query(
        False,
        description="False genera solo l'anteprima; True applica i match univoci",
    ),
):
    """Prepara o applica la riconciliazione PayPal-banca.

    Il primo passaggio e' sempre leggibile come anteprima. La scrittura viene
    eseguita soltanto con ``conferma=true`` e soltanto per abbinamenti
    biunivoci; importo e data da soli non possono risolvere una parita'.
    """
    db = Database.get_db()
    return await _auto_riconcilia(db, anno=anno, applica=conferma)


def _proposte_riconciliazione_banca(
    paypal_txs: List[Dict[str, Any]],
    banca_paypal: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Costruisce match biunivoci senza modificare alcun dato."""
    archi_per_movimento: Dict[str, List[Dict[str, Any]]] = {}
    archi_per_transazione: Dict[str, List[Dict[str, Any]]] = {}

    for mov in banca_paypal:
        mov_id = _id_movimento(mov)
        if not mov_id or mov.get("riconciliato") is True or mov.get("paypal_transaction_id"):
            continue
        for tx in paypal_txs:
            tx_id = str(tx.get("transaction_id") or tx.get("id") or "")
            if not tx_id:
                continue
            match = _score_match_banca(tx, mov)
            if not match or match["score"] < 85:
                continue
            arco = {
                "movimento_id": mov_id,
                "transaction_id": tx_id,
                "score": match["score"],
                "evidenze": match["evidenze"],
                "delta_giorni": match["delta_giorni"],
                "data_movimento": str(mov.get("data") or mov.get("data_contabile") or "")[:10],
                "importo_movimento": round(abs(float(mov.get("importo") or 0)), 2),
            }
            archi_per_movimento.setdefault(mov_id, []).append(arco)
            archi_per_transazione.setdefault(tx_id, []).append(arco)

    proposte: List[Dict[str, Any]] = []
    ambigui = set()
    for mov_id, archi in archi_per_movimento.items():
        archi.sort(key=lambda item: item["score"], reverse=True)
        migliori_mov = [a for a in archi if a["score"] == archi[0]["score"]]
        if len(migliori_mov) != 1:
            ambigui.add(mov_id)
            continue
        candidato = migliori_mov[0]
        archi_tx = sorted(
            archi_per_transazione[candidato["transaction_id"]],
            key=lambda item: item["score"],
            reverse=True,
        )
        migliori_tx = [a for a in archi_tx if a["score"] == archi_tx[0]["score"]]
        if len(migliori_tx) != 1 or migliori_tx[0]["movimento_id"] != mov_id:
            ambigui.add(mov_id)
            continue
        proposte.append(candidato)

    return {
        "proposte": proposte,
        "ambigui": len(ambigui),
        "movimenti_con_candidati": len(archi_per_movimento),
    }


async def _auto_riconcilia(
    db,
    anno: Optional[int] = None,
    applica: bool = True,
) -> Dict:
    """Riconcilia transazioni PayPal con movimenti estratto conto bancario.
    Matching univoco per segno + importo + data, oppure riferimento PayPal
    esplicito in causale. L'importo da solo non produce mai un'associazione.
    """
    paypal_txs = await db[COLL_PAYPAL_TRANSACTIONS].find(
        {"$and": [
            {"riconciliato_banca": {"$ne": True}},
            {"riconciliato_con_estratto_banca": {"$ne": True}},
        ]},
        {"_id": 0}
    ).to_list(5000)
    paypal_txs = [
        tx for tx in _pagamenti_paypal_in_euro(paypal_txs)
        if not anno or (_data_documento(tx) and _data_documento(tx).year == anno)
    ]
    
    # Cerca su descrizione_originale E descrizione (entrambi i campi)
    banca_query: Dict[str, Any] = {"$and": [
        {"$or": [
            {"descrizione": {"$regex": "paypal", "$options": "i"}},
            {"descrizione_originale": {"$regex": "paypal", "$options": "i"}},
        ]},
    ]}
    if anno:
        banca_query["$and"].append({"$or": [
            {"data": {"$regex": f"^{anno}"}},
            {"data_contabile": {"$regex": f"^{anno}"}},
        ]})
    banca_paypal_raw = await db[COLL_ESTRATTO_CONTO].find(
        banca_query,
        {"_id": 0}
    ).to_list(5000)
    banca_paypal_canonici = _deduplica_movimenti_banca_paypal(banca_paypal_raw)
    banca_paypal = [
        movimento for movimento in banca_paypal_canonici
        if not movimento.get("riconciliato") and not movimento.get("paypal_transaction_id")
    ]
    
    anteprima = _proposte_riconciliazione_banca(paypal_txs, banca_paypal)
    riconciliati = 0
    for proposta in anteprima["proposte"] if applica else []:
        mov_id = proposta["movimento_id"]
        tx_id = proposta["transaction_id"]
        now = datetime.now(timezone.utc).isoformat()
        mov_date = proposta["data_movimento"]
        await db[COLL_PAYPAL_TRANSACTIONS].update_one(
            {
                "transaction_id": tx_id,
                "riconciliato_banca": {"$ne": True},
                "riconciliato_con_estratto_banca": {"$ne": True},
            },
            {"$set": {
                "riconciliato_banca": True,
                "riconciliato_con_estratto_banca": True,
                "movimento_banca_id": mov_id,
                "estratto_conto_movimento_id": mov_id,
                "data_banca": mov_date,
                "riconciliazione_banca_score": proposta["score"],
                "riconciliazione_banca_evidenze": proposta["evidenze"],
                "riconciliato_il": now,
            }}
        )
        await db[COLL_ESTRATTO_CONTO].update_one(
            {"id": mov_id, "riconciliato": {"$ne": True}},
            {"$set": {
                "riconciliato": True,
                "tipo_riconciliazione": "paypal_evidenze_univoche",
                "paypal_transaction_id": tx_id,
                "riconciliazione_evidenze": proposta["evidenze"],
                "riconciliazione_score": proposta["score"],
                "data_riconciliazione": now,
            }}
        )
        await finalizza_transazione_paypal_se_completa(db, tx_id)
        riconciliati += 1
    
    return {
        "totale_paypal": len(paypal_txs),
        "totale_banca": len(banca_paypal),
        "totale_banca_raw": len(banca_paypal_raw),
        "duplicati_banca_unificati": len(banca_paypal_raw) - len(banca_paypal_canonici),
        "modalita": "applicata" if applica else "anteprima",
        "proposte": len(anteprima["proposte"]),
        "importo_proposto": round(sum(p["importo_movimento"] for p in anteprima["proposte"]), 2),
        "dettaglio_proposte": anteprima["proposte"][:100],
        "riconciliati": riconciliati,
        "non_riconciliati": len(paypal_txs) - riconciliati,
        "ambigui": anteprima["ambigui"],
        "criterio": "match biunivoco: riferimento oppure importo+segno+data; parita non confermate",
    }


@router.get("/report")
async def paypal_report(anno: Optional[int] = None):
    """Report completo PayPal con dettaglio spese per fornitore."""
    db = Database.get_db()

    tx_query: Dict[str, Any] = {}
    if anno:
        tx_query["data"] = {"$regex": f"^{anno}"}

    transazioni = await db[COLL_PAYPAL_TRANSACTIONS].find(
        tx_query, {"_id": 0}
    ).sort("data", -1).to_list(5000)
    pagamenti = _pagamenti_paypal_in_euro(transazioni)
    
    # Raggruppa per fornitore
    fornitori = {}
    for p in pagamenti:
        nome = p.get('nome_controparte') or p.get('descrizione', 'N/D')
        if nome not in fornitori:
            fornitori[nome] = {
                'nome': nome,
                'email': p.get('email_controparte', ''),
                'totale': 0.0,
                'count': 0,
                'transazioni': []
            }
        importo_eur = p['importo_report_eur']
        fornitori[nome]['totale'] += importo_eur
        fornitori[nome]['count'] += 1
        fornitori[nome]['transazioni'].append({
            'data': p['data'],
            'importo': importo_eur,
            'descrizione': p.get('descrizione', ''),
            'transaction_id': p.get('transaction_id', '')
        })
    
    # Raggruppa per mese
    mesi = {}
    for p in pagamenti:
        mese_key = p['data'][:7]  # YYYY-MM
        if mese_key not in mesi:
            mesi[mese_key] = {'mese': mese_key, 'totale': 0.0, 'count': 0}
        mesi[mese_key]['totale'] += p['importo_report_eur']
        mesi[mese_key]['count'] += 1
    
    sorted_fornitori = sorted(fornitori.values(), key=lambda x: x['totale'])
    sorted_mesi = sorted(mesi.values(), key=lambda x: x['mese'])
    
    return {
        "anno": anno,
        "totale_speso": round(sum(p['importo_report_eur'] for p in pagamenti), 2),
        "totale_transazioni": len(pagamenti),
        "per_fornitore": sorted_fornitori,
        "per_mese": sorted_mesi
    }


async def _save_parsed_statement(db, parsed: Dict) -> Dict:
    """Compatibilita' per CSV e test: usa il writer canonico condiviso."""
    from app.services.paypal_statement_import import save_parsed_statement

    return await save_parsed_statement(db, parsed, source="paypal_import_parser")


@router.get("/transazione/{transaction_id}/dettaglio")
async def dettaglio_transazione_paypal(transaction_id: str) -> Dict[str, Any]:
    """Restituisce dettagli completi di una transazione PayPal, includendo
    tutti i collegamenti utili per la vista modale:
      - Dati PayPal (email, metodo, tipo, stato, ID)
      - Verbale collegato (se paypal_transaction_id = {transaction_id})
      - Dipendente (se il verbale ha driver_id)
      - Trattenuta in busta paga (se esiste per questo verbale)
      - Fornitore mappato (se esiste mapping per paypal_account_id)
      - Fatture del fornitore (match per nome/P.IVA nell'anno)
      - Flag has_pdf sul verbale (senza trasferire il PDF, solo il flag)

    La risposta è sempre un oggetto con le stesse chiavi, anche se nulle,
    per semplificare il rendering frontend.
    """
    db = Database.get_db()

    # 1. Transazione PayPal
    tx = await db[COLL_PAYPAL_TRANSACTIONS].find_one(
        {"transaction_id": transaction_id}, {"_id": 0}
    )
    if not tx:
        # fallback: cerca anche per campo 'id' interno
        tx = await db[COLL_PAYPAL_TRANSACTIONS].find_one(
            {"id": transaction_id}, {"_id": 0}
        )
    if not tx:
        raise HTTPException(status_code=404, detail="Transazione PayPal non trovata")

    real_tx_id = tx.get("transaction_id") or tx.get("id")

    # 2. Verbale collegato
    verbale = await db["verbali_noleggio"].find_one(
        {"paypal_transaction_id": real_tx_id},
        {"_id": 0, "pdf_data": 0, "pdf_allegati": 0}  # escludo i pdf binari
    )
    has_pdf = False
    if verbale:
        # Controllo presenza PDF in modo leggero
        v_pdf_check = await db["verbali_noleggio"].find_one(
            {"id": verbale.get("id")},
            {"_id": 0, "pdf_data": 1, "pdf_allegati": 1}
        )
        has_pdf = bool(
            (v_pdf_check or {}).get("pdf_data")
            or (v_pdf_check or {}).get("pdf_allegati")
        )

    # 3. Dipendente (se verbale ha driver_id)
    dipendente = None
    if verbale and verbale.get("driver_id"):
        dipendente = await db[COLL_EMPLOYEES].find_one(
            {"id": verbale["driver_id"]},
            {"_id": 0, "id": 1, "nome": 1, "cognome": 1, "codice_fiscale": 1, "ruolo": 1}
        )

    # 4. Trattenuta in busta paga
    trattenuta = None
    if verbale:
        trattenuta = await db["trattenute_dipendenti"].find_one(
            {"verbale_id": verbale.get("id")},
            {"_id": 0}
        )

    # 5. Mapping fornitore PayPal — il mapping vivo è il campo
    # fornitori.paypal_account_id (stesso pattern di paypal_api.py
    # account-ids-non-mappati/mappa-fornitore), NON la collection
    # "paypal_mapping_fornitori" che non viene mai scritta da nessuna parte
    # del codice (piano residuo op.14, indagine 14/07/2026, era un ramo
    # morto che ritornava sempre None).
    mapping_fornitore = None
    paypal_account_id = tx.get("paypal_account_id") or tx.get("account_id")
    if paypal_account_id:
        forn = await db["fornitori"].find_one(
            {"paypal_account_id": paypal_account_id},
            {"_id": 0, "id": 1, "nome": 1, "ragione_sociale": 1, "piva": 1, "partita_iva": 1}
        )
        if forn:
            mapping_fornitore = {
                "paypal_account_id": paypal_account_id,
                "fornitore_id": forn.get("id"),
                "fornitore_nome": forn.get("nome"),
                "fornitore_ragione_sociale": forn.get("ragione_sociale"),
                "fornitore_piva": forn.get("piva") or forn.get("partita_iva"),
            }

    # 6. Fatture del fornitore associato. Numero fattura e importo possono
    # ripetersi tra fornitori diversi: ogni risultato viene rivalidato con
    # P.IVA/CF, denominazione o email. Il solo importo non e' un candidato.
    fatture_collegate = []
    nome_controparte = (tx.get("nome_controparte") or tx.get("payer_name") or "").strip()
    email_controparte = (tx.get("email_controparte") or tx.get("payer_email") or "").strip().lower()
    projection = {
        "_id": 0, "id": 1, "invoice_number": 1, "numero_fattura": 1,
        "invoice_date": 1, "data_fattura": 1, "data_documento": 1,
        "total_amount": 1, "importo_totale": 1,
        "divisa": 1, "currency": 1, "valuta": 1,
        "supplier_name": 1, "cedente_denominazione": 1,
        "supplier_vat": 1, "cedente_piva": 1, "piva_cedente": 1,
        "supplier_tax_code": 1, "cedente_codice_fiscale": 1,
        "supplier_email": 1, "cedente_email": 1, "email_cedente": 1,
        "stato_pagamento": 1,
    }

    # STRATEGIA 0 (prioritaria): la transazione PayPal porta spesso il numero
    # fattura del fornitore (invoice_id_fornitore, es. Sklum "229819653").
    # Il riferimento restringe la ricerca, ma non basta: numeri come "120"
    # non sono univoci senza identita' del fornitore.
    rif_fattura = str(tx.get("invoice_id_fornitore") or tx.get("invoice_id") or "").strip()
    if rif_fattura:
        import re as _re
        fatture_collegate = await db[COLL_INVOICES].find(
            {"$or": [
                {"invoice_number": rif_fattura},
                {"numero_fattura": rif_fattura},
                {"invoice_number": {"$regex": _re.escape(rif_fattura) + "$"}},
            ]},
            projection,
        ).sort("invoice_date", -1).limit(20).to_list(20)

    if not fatture_collegate and mapping_fornitore and mapping_fornitore.get("fornitore_piva"):
        # STRATEGIA A: P.IVA (il match più affidabile)
        piva = mapping_fornitore["fornitore_piva"]
        fatture_collegate = await db[COLL_INVOICES].find(
            {
                "$or": [
                    {"cedente_piva": piva},
                    {"supplier_vat": piva},
                    {"piva_cedente": piva},
                ]
            },
            projection,
        ).sort("invoice_date", -1).limit(10).to_list(10)

    if not fatture_collegate and nome_controparte:
        # STRATEGIA B: match per parole significative del nome fornitore.
        # Esempio: "Spotify AB" → cerco "spotify". Scarto suffissi societari comuni
        # che darebbero falsi positivi in massa ("SRL", "SPA", "LTD", "SA", "AB").
        import re as _re
        STOP = {"srl", "spa", "sa", "ab", "ltd", "limited", "llc", "inc",
                "gmbh", "ag", "bv", "nv", "s.p.a.", "s.r.l."}
        parole = [
            p for p in _re.split(r"[\s\.\,\-\&]+", nome_controparte.lower())
            if len(p) >= 4 and p not in STOP
        ]
        if parole:
            or_query = []
            for p in parole[:3]:  # max 3 parole per non esplodere la query
                escaped = _re.escape(p)
                or_query.append({"supplier_name": {"$regex": escaped, "$options": "i"}})
                or_query.append({"cedente_denominazione": {"$regex": escaped, "$options": "i"}})
            fatture_collegate = await db[COLL_INVOICES].find(
                {"$or": or_query},
                projection,
            ).sort("invoice_date", -1).limit(5).to_list(5)

    if not fatture_collegate and email_controparte:
        # STRATEGIA C: l'email della controparte è salvata in qualche fattura?
        # Raro ma capita per fornitori SaaS/digitali (Spotify, MongoDB, ecc.)
        fatture_collegate = await db[COLL_INVOICES].find(
            {
                "$or": [
                    {"supplier_email": email_controparte},
                    {"cedente_email": email_controparte},
                    {"email_cedente": email_controparte},
                ]
            },
            projection,
        ).sort("invoice_date", -1).limit(5).to_list(5)

    # Rivalidazione finale. Dedup per ID, non per numero fattura: lo stesso
    # numero puo' esistere legittimamente presso fornitori diversi.
    visti = set()
    dedup = []
    for f in fatture_collegate:
        chiave = f.get("id")
        if chiave in visti:
            continue
        visti.add(chiave)
        valutazione = evaluate_paypal_invoice_match(tx, f, mapping_fornitore)
        if not valutazione["identita_fornitore"]:
            continue
        f["associabile"] = valutazione["associabile"]
        f["match_score"] = valutazione["score"]
        f["match_evidenze"] = valutazione["evidenze"]
        f["match_scarto"] = valutazione["scarto"]
        if "numero_fattura" in valutazione["evidenze"]:
            f["match"] = "riferimento_e_fornitore"
        elif valutazione["associabile"]:
            f["match"] = "fornitore_e_importo"
        dedup.append(f)
    dedup.sort(key=lambda f: (f.get("associabile", False), f.get("match_score", 0)), reverse=True)
    fatture_collegate = dedup[:6]

    # Link diretto alla vista AssoSoftware: la fattura si può SEMPRE vedere,
    # indipendentemente dall'anno selezionato nel gestionale.
    for f in fatture_collegate:
        if f.get("id"):
            f["view_url"] = f"/api/fatture-ricevute/fattura/{f['id']}/view-assoinvoice"

    # --- Flag riconciliato in banca: il DB può avere diversi nomi di campo ---
    # Storicamente: "riconciliato_banca" (boolean)
    # Aggiunto dal service: "riconciliato_con_estratto_banca" (boolean)
    # Aggiungo un campo unificato nel payload per semplificare il frontend.
    riconciliato_unificato = bool(
        tx.get("riconciliato_banca")
        or tx.get("riconciliato_con_estratto_banca")
        or tx.get("estratto_conto_movimento_id")
    )
    # Mantengo nella tx originale il valore booleano che il frontend si aspetta:
    tx["riconciliato_banca"] = riconciliato_unificato

    return {
        "transaction": tx,
        "verbale": verbale,
        "has_pdf_verbale": has_pdf,
        "dipendente": dipendente,
        "trattenuta_busta_paga": trattenuta,
        "mapping_fornitore": mapping_fornitore,
        "fatture_collegate": fatture_collegate,
    }


@router.get("/transazione/{transaction_id}/cerca-gmail")
async def cerca_gmail_transazione(transaction_id: str) -> Dict[str, Any]:
    """Cerca su Gmail email compatibili con la transazione (fatture ESTERNE
    che non passano dal Sistema di Interscambio: SaaS, fornitori esteri).

    Cerca per importo (punto e virgola) e prima parola della controparte in
    una finestra di date intorno alla transazione. Ritorna oggetto/mittente/
    data e il link per aprire il messaggio direttamente in Gmail.
    """
    import asyncio as _asyncio
    from app.services.gmail_search import (
        get_gmail_credentials, search_gmail_sync, build_transaction_query,
    )

    db = Database.get_db()
    tx = await db[COLL_PAYPAL_TRANSACTIONS].find_one(
        {"$or": [{"transaction_id": transaction_id}, {"id": transaction_id}]},
        {"_id": 0},
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Transazione PayPal non trovata")

    user, pwd, server = await get_gmail_credentials(db)
    if not user or not pwd:
        return {"ok": False, "risultati": [],
                "errore": "Nessun account Gmail configurato (Admin → Email, con App Password)"}

    query = build_transaction_query(
        importo=tx.get("importo") or tx.get("lordo") or 0,
        nome_controparte=tx.get("nome_controparte") or "",
        data_iso=tx.get("data") or "",
    )
    if not query:
        return {"ok": False, "risultati": [], "errore": "Dati transazione insufficienti per la ricerca"}
    try:
        risultati = await _asyncio.to_thread(search_gmail_sync, user, pwd, server, query, 10)
    except Exception as e:
        return {"ok": False, "risultati": [], "query": query,
                "errore": f"Ricerca Gmail non riuscita: {e}"}
    return {"ok": True, "query": query, "account": user, "risultati": risultati}


@router.post("/transazione/{transaction_id}/associa")
async def associa_transazione(transaction_id: str, body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """Associa manualmente la transazione a una fattura del gestionale
    (body: {fattura_id}) oppure a un'email Gmail (body: {gmail: {...}})."""
    db = Database.get_db()
    tx = await db[COLL_PAYPAL_TRANSACTIONS].find_one(
        {"$or": [{"transaction_id": transaction_id}, {"id": transaction_id}]},
        {"_id": 0},
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Transazione PayPal non trovata")

    set_data: Dict[str, Any] = {}
    if body.get("fattura_id"):
        risultato = await associa_transazione_univoca(
            db, tx, invoice_id=body["fattura_id"], automatic=False,
        )
        if not risultato.get("collegata"):
            raise HTTPException(
                status_code=409,
                detail={
                    "messaggio": "Associazione rifiutata: fattura e transazione non hanno evidenze sufficienti",
                    "motivo": risultato.get("motivo"),
                },
            )
        return {"success": True, **risultato}
    elif body.get("gmail"):
        g = body["gmail"]
        set_data["gmail_associata"] = {
            "subject": g.get("subject"), "from": g.get("from"),
            "date": g.get("date"), "message_id": g.get("message_id"),
            "gmail_link": g.get("gmail_link"),
        }
    else:
        raise HTTPException(status_code=400, detail="Indicare fattura_id oppure gmail")

    await db[COLL_PAYPAL_TRANSACTIONS].update_one(
        {"$or": [{"transaction_id": transaction_id}, {"id": transaction_id}]},
        {"$set": set_data},
    )
    return {"success": True, **set_data}


@router.post("/auto-associa")
async def auto_associa_transazioni() -> Dict[str, Any]:
    """Associa AUTOMATICAMENTE i pagamenti PayPal alle fatture del gestionale:
    identita' fornitore e importo uguale al centesimo. Il numero fattura e'
    obbligatorio quando PayPal lo espone; in sua assenza servono data
    compatibile e un solo candidato. Quando entrambe le fonti dichiarano la
    valuta, anche la valuta deve coincidere.
    Le transazioni senza evidenze sufficienti restano da verificare."""
    db = Database.get_db()
    return {"success": True, **(await riprocessa_collegamenti_paypal(db))}


@router.post("/riprocessa")
async def riprocessa_paypal_end_to_end(anno: Optional[int] = Query(None)) -> Dict[str, Any]:
    """Riesegue l'intera catena senza creare duplicati.

    Serve anche come recupero per il caso in cui estratto conto, transazione
    e fattura siano arrivati in un ordine diverso. Le associazioni ambigue
    restano sospese e non vengono confermate.
    """
    db = Database.get_db()
    start_date = f"{anno}-01-01" if anno else None
    end_date = f"{anno}-12-31" if anno else None
    prima = await riprocessa_collegamenti_paypal(
        db, start_date=start_date, end_date=end_date,
    )
    banca = await _auto_riconcilia(db, anno=anno, applica=True)
    dopo = await riprocessa_collegamenti_paypal(
        db, start_date=start_date, end_date=end_date,
    )
    return {"success": True, "collegamenti_prima": prima, "banca": banca,
            "collegamenti_dopo": dopo}



@router.post("/pulisci-match-solo-importo")
async def pulisci_match_solo_importo(dry_run: bool = Query(True)) -> Dict[str, Any]:
    """Rivalida tutte le associazioni automatiche PayPal-fattura storiche.

    Il collegamento resta valido solo quando la fattura esiste e la transazione
    prova contemporaneamente identita' fornitore, numero fattura e importo
    uguale al centesimo. Le vecchie etichette ``match`` non sono considerate
    attendibili: una versione precedente poteva aver salvato collegamenti
    basati sul solo importo o su un nome approssimativo.
    """
    db = Database.get_db()
    query = {"fattura_associata.auto": True}
    txs = await db[COLL_PAYPAL_TRANSACTIONS].find(
        query,
        {
            "_id": 0, "transaction_id": 1, "nome_controparte": 1,
            "payer_name": 1, "email_controparte": 1, "payer_email": 1,
            "invoice_id_fornitore": 1, "invoice_id": 1,
            "importo": 1, "lordo": 1, "amount": 1,
            "currency": 1, "valuta": 1, "divisa": 1,
            "fattura_associata": 1,
        },
    ).to_list(2000)

    da_rimuovere = []
    for t in txs:
        fa = t.get("fattura_associata") or {}
        invoice = await db[COLL_INVOICES].find_one(
            {"id": fa.get("fattura_id")},
            {
                "_id": 0, "id": 1, "supplier_name": 1,
                "cedente_denominazione": 1, "supplier_vat": 1,
                "cedente_piva": 1, "piva_cedente": 1,
                "invoice_number": 1, "numero_fattura": 1,
                "total_amount": 1, "importo_totale": 1,
                "divisa": 1, "currency": 1, "valuta": 1,
            },
        )
        if not invoice:
            da_rimuovere.append({**t, "_motivo": "fattura_non_trovata"})
            continue
        mapping = await supplier_mapping_for_transaction(db, t)
        valutazione = evaluate_paypal_invoice_match(t, invoice, mapping)
        if not valutazione["associabile"]:
            da_rimuovere.append({**t, "_motivo": valutazione["scarto"]})

    if not dry_run and da_rimuovere:
        ids = [t["transaction_id"] for t in da_rimuovere]
        await db[COLL_PAYPAL_TRANSACTIONS].update_many(
            {"transaction_id": {"$in": ids}}, {"$unset": {"fattura_associata": ""}}
        )

    return {
        "dry_run": dry_run,
        "trovate": len(da_rimuovere),
        "esempi": [
            {
                "transaction_id": t.get("transaction_id"),
                "controparte": t.get("nome_controparte"),
                "fattura_agganciata_erroneamente": (t.get("fattura_associata") or {}).get("fornitore"),
                "motivo": t.get("_motivo"),
            }
            for t in da_rimuovere[:20]
        ],
    }


@router.post("/auto-cerca-gmail")
async def auto_cerca_gmail(limit: int = 12) -> Dict[str, Any]:
    """Per i pagamenti PayPal SENZA fattura nel gestionale, cerca su Gmail in
    AUTOMATICO (fatture esterne che non passano dallo SDI) e associa il
    risultato migliore: l'utente trova già il link ✉️ senza dover cliccare.

    Ogni transazione viene cercata una sola volta (flag gmail_cercato_at);
    max `limit` ricerche per giro per non sovraccaricare IMAP.
    """
    import asyncio as _asyncio
    from app.services.gmail_search import (
        get_gmail_credentials, search_gmail_sync, build_transaction_query,
    )

    db = Database.get_db()
    user, pwd, server = await get_gmail_credentials(db)
    if not user or not pwd:
        return {"ok": False, "errore": "Nessun account Gmail configurato", "cercate": 0}

    txs = await db[COLL_PAYPAL_TRANSACTIONS].find(
        {"lordo": {"$lt": 0},
         "fattura_associata": {"$exists": False},
         "gmail_associata": {"$exists": False},
         "gmail_cercato_at": {"$exists": False}},
        {"_id": 0, "transaction_id": 1, "importo": 1, "lordo": 1,
         "nome_controparte": 1, "data": 1},
    ).sort("data", -1).limit(limit).to_list(limit)

    cercate = 0
    associate = 0
    now = datetime.now(timezone.utc).isoformat()
    for tx in txs:
        if not tx.get("transaction_id"):
            continue
        query = build_transaction_query(
            importo=tx.get("importo") or tx.get("lordo") or 0,
            nome_controparte=tx.get("nome_controparte") or "",
            data_iso=tx.get("data") or "",
        )
        if not query:
            continue
        try:
            risultati = await _asyncio.to_thread(search_gmail_sync, user, pwd, server, query, 6)
        except Exception as e:
            logger.warning(f"auto-cerca-gmail: errore su {tx['transaction_id']}: {e}")
            break  # problema IMAP: riprova al prossimo giro
        cercate += 1
        set_data: Dict[str, Any] = {
            "gmail_cercato_at": now,
            "gmail_candidati": risultati[:5],
        }
        # Migliore: il primo con allegato, altrimenti il primo
        best = next((m for m in risultati if m.get("has_attachment")), None) or (risultati[0] if risultati else None)
        if best:
            set_data["gmail_associata"] = {**best, "auto": True}
            associate += 1
        await db[COLL_PAYPAL_TRANSACTIONS].update_one(
            {"transaction_id": tx["transaction_id"]}, {"$set": set_data})

    return {"ok": True, "cercate": cercate, "associate_gmail": associate}
