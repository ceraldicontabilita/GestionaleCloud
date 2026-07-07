"""
Router per gestione estratti conto PayPal (MSR/CSR).
Import PDF, visualizzazione transazioni, riconciliazione con estratto conto bancario.
"""
from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import uuid
import os
import logging
import shutil

from app.database import Database
from app.db_collections import (
    COLL_ESTRATTO_CONTO,
    COLL_INVOICES,
    COLL_FORNITORI
)

logger = logging.getLogger(__name__)
router = APIRouter()

# Collection PayPal
COLL_PAYPAL_STATEMENTS = "paypal_statements"
COLL_PAYPAL_TRANSACTIONS = "paypal_transactions"

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


@router.get("/statements")
async def get_paypal_statements(
    anno: Optional[int] = None,
    limit: int = Query(default=100, le=500)
):
    """Restituisce tutti gli estratti conto PayPal importati."""
    db = Database.get_db()
    query = {}
    if anno:
        query["anno"] = anno
    
    statements = await db[COLL_PAYPAL_STATEMENTS].find(
        query, {"_id": 0}
    ).sort("periodo_inizio", -1).limit(limit).to_list(limit)
    
    return {"statements": statements, "totale": len(statements)}


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

    # Descrizione leggibile: le transazioni da API PayPal non hanno il campo
    # "descrizione" ma trasportano oggetto/nota/numero fattura del fornitore.
    for t in transactions:
        if not t.get("descrizione"):
            t["descrizione"] = (
                t.get("transaction_subject")
                or t.get("transaction_note")
                or (f"Fatt. {t['invoice_id_fornitore']}" if t.get("invoice_id_fornitore") else "")
            )

    # Statistiche
    totale_pagamenti = sum(t['lordo'] for t in transactions if t.get('lordo', 0) < 0)
    totale_accrediti = sum(t['lordo'] for t in transactions if t.get('lordo', 0) > 0)
    
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
    
    # Transazioni solo pagamenti (lordo < 0)
    pag_query = {**tx_query, "lordo": {"$lt": 0}}
    pagamenti = await db[COLL_PAYPAL_TRANSACTIONS].find(
        pag_query, {"_id": 0, "lordo": 1, "tipo": 1, "nome_controparte": 1, "paypal_account_id": 1}
    ).to_list(2000)
    _backfill_controparte(pagamenti)

    totale_speso = sum(p['lordo'] for p in pagamenti)
    
    # Top fornitori
    fornitori_map = {}
    for p in pagamenti:
        nome = p.get('nome_controparte', 'N/D') or 'N/D'
        if nome not in fornitori_map:
            fornitori_map[nome] = {'nome': nome, 'totale': 0.0, 'count': 0}
        fornitori_map[nome]['totale'] += p['lordo']
        fornitori_map[nome]['count'] += 1
    
    top_fornitori = sorted(fornitori_map.values(), key=lambda x: x['totale'])[:10]
    
    # Per tipo
    tipo_map = {}
    for p in pagamenti:
        tipo = p.get('tipo', 'altro')
        if tipo not in tipo_map:
            tipo_map[tipo] = {'tipo': tipo, 'totale': 0.0, 'count': 0}
        tipo_map[tipo]['totale'] += p['lordo']
        tipo_map[tipo]['count'] += 1
    
    # Riconciliazione con estratto conto
    riconciliati = await db[COLL_PAYPAL_TRANSACTIONS].count_documents(
        {**tx_query, "riconciliato_banca": True}
    )
    
    # Transazioni in estratto conto bancario con PayPal
    # Stessa logica della riconciliazione: descrizione O descrizione_originale,
    # e rispetta il filtro anno selezionato (prima contava sempre tutto).
    ec_query = {"$or": [
        {"descrizione": {"$regex": "paypal", "$options": "i"}},
        {"descrizione_originale": {"$regex": "paypal", "$options": "i"}},
    ]}
    if anno:
        ec_query = {"$and": [ec_query, {"data": {"$regex": f"^{anno}"}}]}
    ec_paypal = await db[COLL_ESTRATTO_CONTO].count_documents(ec_query)
    
    return {
        "total_statements": total_statements,
        "total_transactions": total_transactions,
        "totale_speso": round(totale_speso, 2),
        "totale_pagamenti": len(pagamenti),
        "top_fornitori": top_fornitori,
        "per_tipo": list(tipo_map.values()),
        "riconciliati_banca": riconciliati,
        "movimenti_banca_paypal": ec_paypal,
        "anno_filtro": anno
    }


@router.post("/import-pdf")
async def import_paypal_pdf(file: UploadFile = File(...)):
    """Importa un singolo PDF PayPal MSR/CSR e riconcilia automaticamente."""
    from app.parsers.paypal_msr_parser import parse_paypal_msr
    
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Solo file PDF accettati")
    
    # Salva file (sanitize filename to prevent path traversal)
    safe_filename = os.path.basename(file.filename)
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    with open(file_path, 'wb') as f:
        shutil.copyfileobj(file.file, f)
    
    # Parsa
    parsed = parse_paypal_msr(file_path)
    if not parsed['success']:
        raise HTTPException(status_code=422, detail=f"Errore parsing: {parsed['errors']}")
    
    # Salva in DB
    db = Database.get_db()
    result = await _save_parsed_statement(db, parsed)
    
    # AUTO-RICONCILIAZIONE dopo import
    ric_result = await _auto_riconcilia(db)
    result['riconciliazione'] = ric_result
    
    return result


@router.post("/import-all-local")
async def import_all_local_pdfs():
    """Importa tutti i PDF PayPal dalla cartella locale e riconcilia automaticamente."""
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
    
    # AUTO-RICONCILIAZIONE dopo import
    ric_result = await _auto_riconcilia(db)
    results['riconciliazione'] = ric_result
    
    return results


@router.post("/import-csv")
async def import_paypal_csv(file: UploadFile = File(...)):
    """
    Importa un estratto conto PayPal esportato in CSV (formato bulk export,
    più mesi in un unico file) — alternativa a /import-pdf per chi non ha i
    PDF MSR/CSR ma solo l'export CSV. Stessa persistenza/riconciliazione
    automatica dei PDF: ogni "File" nel CSV diventa uno statement separato.
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

    ric_result = await _auto_riconcilia(db)

    return {
        "success": True,
        "statements_importati": len(risultati),
        "righe_totali_csv": parsed['righe_totali'],
        "righe_scartate": parsed['righe_scartate'],
        "transazioni_inserite": transazioni_inserite,
        "transazioni_duplicate": transazioni_duplicate,
        "riconciliazione": ric_result,
    }


@router.post("/riconcilia-banca")
async def riconcilia_con_banca():
    """Riconcilia manualmente (normalmente è automatico dopo import)."""
    db = Database.get_db()
    result = await _auto_riconcilia(db)
    return result


async def _auto_riconcilia(db) -> Dict:
    """Riconcilia transazioni PayPal con movimenti estratto conto bancario.
    Matching per importo + data con tolleranza 3 giorni (ritardo SDD).
    """
    from datetime import timedelta
    
    paypal_txs = await db[COLL_PAYPAL_TRANSACTIONS].find(
        {"riconciliato_banca": {"$ne": True}, "lordo": {"$lt": 0}},
        {"_id": 0}
    ).to_list(5000)
    
    # Cerca su descrizione_originale E descrizione (entrambi i campi)
    banca_paypal = await db[COLL_ESTRATTO_CONTO].find(
        {"$or": [
            {"descrizione": {"$regex": "paypal", "$options": "i"}},
            {"descrizione_originale": {"$regex": "paypal", "$options": "i"}}
        ]},
        {"_id": 0}
    ).to_list(5000)
    
    # Index banca per importo per velocizzare matching
    banca_usati = set()
    riconciliati = 0
    
    for tx in paypal_txs:
        tx_importo = abs(tx['lordo'])
        tx_data = tx['data']
        tx_id = tx.get('transaction_id', '')
        
        try:
            tx_dt = datetime.strptime(tx_data, '%Y-%m-%d')
        except (ValueError, TypeError):
            continue
        
        best_match = None
        best_delta = 999
        
        for mov in banca_paypal:
            mov_id = mov.get('id', '')
            if mov_id in banca_usati:
                continue
            
            mov_importo = abs(mov.get('importo', 0))
            importo_match = abs(tx_importo - mov_importo) < 0.02
            if not importo_match:
                continue
            
            mov_data_str = str(mov.get('data', ''))[:10]
            try:
                mov_dt = datetime.strptime(mov_data_str, '%Y-%m-%d')
                delta = abs((tx_dt - mov_dt).days)
            except (ValueError, TypeError):
                continue
            
            if delta <= 3 and delta < best_delta:
                best_match = mov
                best_delta = delta
        
        if best_match:
            banca_usati.add(best_match.get('id', ''))
            await db[COLL_PAYPAL_TRANSACTIONS].update_one(
                {"transaction_id": tx_id},
                {"$set": {
                    "riconciliato_banca": True,
                    "movimento_banca_id": best_match.get('id'),
                    "data_banca": str(best_match.get('data', ''))[:10],
                    "riconciliato_il": datetime.now(timezone.utc).isoformat()
                }}
            )
            riconciliati += 1
    
    return {
        "totale_paypal": len(paypal_txs),
        "totale_banca": len(banca_paypal),
        "riconciliati": riconciliati,
        "non_riconciliati": len(paypal_txs) - riconciliati
    }


@router.get("/report")
async def paypal_report(anno: Optional[int] = None):
    """Report completo PayPal con dettaglio spese per fornitore."""
    db = Database.get_db()
    
    tx_query = {"lordo": {"$lt": 0}}
    if anno:
        tx_query["data"] = {"$regex": f"^{anno}"}
    
    pagamenti = await db[COLL_PAYPAL_TRANSACTIONS].find(
        tx_query, {"_id": 0}
    ).sort("data", -1).to_list(5000)
    
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
        fornitori[nome]['totale'] += p['lordo']
        fornitori[nome]['count'] += 1
        fornitori[nome]['transazioni'].append({
            'data': p['data'],
            'importo': p['lordo'],
            'descrizione': p.get('descrizione', ''),
            'transaction_id': p.get('transaction_id', '')
        })
    
    # Raggruppa per mese
    mesi = {}
    for p in pagamenti:
        mese_key = p['data'][:7]  # YYYY-MM
        if mese_key not in mesi:
            mesi[mese_key] = {'mese': mese_key, 'totale': 0.0, 'count': 0}
        mesi[mese_key]['totale'] += p['lordo']
        mesi[mese_key]['count'] += 1
    
    sorted_fornitori = sorted(fornitori.values(), key=lambda x: x['totale'])
    sorted_mesi = sorted(mesi.values(), key=lambda x: x['mese'])
    
    return {
        "anno": anno,
        "totale_speso": round(sum(p['lordo'] for p in pagamenti), 2),
        "totale_transazioni": len(pagamenti),
        "per_fornitore": sorted_fornitori,
        "per_mese": sorted_mesi
    }


async def _save_parsed_statement(db, parsed: Dict) -> Dict:
    """Salva statement e transazioni nel database."""
    periodo = parsed.get('periodo', {})
    account = parsed.get('account_info', {})
    
    statement_id = str(uuid.uuid4())
    
    # Salva statement
    statement_doc = {
        "id": statement_id,
        "tipo_documento": parsed.get('tipo_documento', 'MSR'),
        "codice_conto": account.get('codice_conto'),
        "email_paypal": account.get('email_paypal'),
        "periodo_inizio": periodo.get('periodo_inizio'),
        "periodo_fine": periodo.get('periodo_fine'),
        "mese": periodo.get('mese'),
        "anno": periodo.get('anno'),
        "riepilogo": parsed.get('riepilogo_attivita', {}),
        "totale_transazioni": parsed.get('totale_transazioni', 0),
        "file_name": parsed.get('file_name'),
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Upsert statement (evita duplicati per periodo)
    await db[COLL_PAYPAL_STATEMENTS].update_one(
        {"periodo_inizio": periodo.get('periodo_inizio'), "periodo_fine": periodo.get('periodo_fine')},
        {"$set": statement_doc},
        upsert=True
    )
    
    # Salva transazioni
    inserted = 0
    duplicates = 0
    for tx in parsed.get('transazioni', []):
        tx['statement_id'] = statement_id
        tx['riconciliato_banca'] = False
        tx['created_at'] = datetime.now(timezone.utc).isoformat()
        
        tid = tx.get('transaction_id')
        if tid:
            existing = await db[COLL_PAYPAL_TRANSACTIONS].find_one({"transaction_id": tid})
            if existing:
                duplicates += 1
                continue
        
        await db[COLL_PAYPAL_TRANSACTIONS].insert_one(tx)
        inserted += 1
    
    return {
        "statement_id": statement_id,
        "periodo": f"{periodo.get('periodo_inizio')} - {periodo.get('periodo_fine')}",
        "transazioni_inserite": inserted,
        "transazioni_duplicate": duplicates
    }


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
        dipendente = await db["employees"].find_one(
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

    # 5. Mapping fornitore PayPal
    mapping_fornitore = None
    paypal_account_id = tx.get("paypal_account_id") or tx.get("account_id")
    if paypal_account_id:
        mapping_fornitore = await db["paypal_mapping_fornitori"].find_one(
            {"paypal_account_id": paypal_account_id},
            {"_id": 0}
        )

    # 6. Fatture del fornitore associato (best-effort).
    # STRATEGIA MULTI-LIVELLO:
    #   a) Se il mapping ha una P.IVA → match esatto su P.IVA (miglior risultato)
    #   b) Altrimenti, cerca per nome con fuzzy: estrae parole significative
    #      (>=4 lettere, non "SRL", "SPA", "LTD") e cerca fatture che contengano
    #      almeno una di quelle parole nel nome fornitore (case-insensitive)
    #   c) Se c'è la stessa email PayPal nelle fatture (raro ma succede)
    #   d) Se nessuna strategia trova qualcosa, ritorna [] con suggerimento "collega manualmente"
    fatture_collegate = []
    nome_controparte = (tx.get("nome_controparte") or tx.get("payer_name") or "").strip()
    email_controparte = (tx.get("email_controparte") or tx.get("payer_email") or "").strip().lower()

    if mapping_fornitore and mapping_fornitore.get("fornitore_piva"):
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
            {"_id": 0, "id": 1, "invoice_number": 1, "numero_fattura": 1,
             "invoice_date": 1, "data_fattura": 1,
             "total_amount": 1, "importo_totale": 1,
             "supplier_name": 1, "cedente_denominazione": 1,
             "stato_pagamento": 1}
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
                {"_id": 0, "id": 1, "invoice_number": 1, "numero_fattura": 1,
                 "invoice_date": 1, "data_fattura": 1,
                 "total_amount": 1, "importo_totale": 1,
                 "supplier_name": 1, "cedente_denominazione": 1,
                 "stato_pagamento": 1}
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
            {"_id": 0, "id": 1, "invoice_number": 1, "numero_fattura": 1,
             "invoice_date": 1, "data_fattura": 1,
             "total_amount": 1, "importo_totale": 1,
             "supplier_name": 1, "cedente_denominazione": 1,
             "stato_pagamento": 1}
        ).sort("invoice_date", -1).limit(5).to_list(5)

    # STRATEGIA D: match per IMPORTO su QUALSIASI anno.
    # Fondamentale per le transazioni senza controparte (es. T0200) e per le
    # fatture registrate in anni diversi da quello del filtro globale.
    importo_tx = abs(float(tx.get("importo") or tx.get("lordo") or 0))
    if not fatture_collegate and importo_tx > 0:
        fatture_collegate = await db[COLL_INVOICES].find(
            {"$or": [
                {"total_amount": {"$gte": importo_tx - 0.05, "$lte": importo_tx + 0.05}},
                {"importo_totale": {"$gte": importo_tx - 0.05, "$lte": importo_tx + 0.05}},
            ]},
            {"_id": 0, "id": 1, "invoice_number": 1, "numero_fattura": 1,
             "invoice_date": 1, "data_fattura": 1,
             "total_amount": 1, "importo_totale": 1,
             "supplier_name": 1, "cedente_denominazione": 1,
             "stato_pagamento": 1}
        ).sort("invoice_date", -1).limit(10).to_list(10)
        for f in fatture_collegate:
            f["match"] = "importo"

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
        {"_id": 0, "transaction_id": 1, "id": 1},
    )
    if not tx:
        raise HTTPException(status_code=404, detail="Transazione PayPal non trovata")

    set_data: Dict[str, Any] = {}
    if body.get("fattura_id"):
        fatt = await db[COLL_INVOICES].find_one(
            {"id": body["fattura_id"]},
            {"_id": 0, "id": 1, "invoice_number": 1, "invoice_date": 1,
             "supplier_name": 1, "total_amount": 1})
        if not fatt:
            raise HTTPException(status_code=404, detail="Fattura non trovata")
        set_data["fattura_associata"] = {
            "fattura_id": fatt["id"],
            "numero": fatt.get("invoice_number"),
            "data": fatt.get("invoice_date"),
            "fornitore": fatt.get("supplier_name"),
            "importo": fatt.get("total_amount"),
            "view_url": f"/api/fatture-ricevute/fattura/{fatt['id']}/view-assoinvoice",
            "auto": False,
        }
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
    match per importo esatto (±0,05 €, qualsiasi anno); se più candidate,
    sceglie quella col nome fornitore compatibile con la controparte.
    Le transazioni senza match restano da cercare su Gmail (fatture esterne)."""
    db = Database.get_db()
    txs = await db[COLL_PAYPAL_TRANSACTIONS].find(
        {"lordo": {"$lt": 0}, "fattura_associata": {"$exists": False}},
        {"_id": 0, "transaction_id": 1, "importo": 1, "lordo": 1,
         "nome_controparte": 1, "data": 1},
    ).to_list(2000)

    associate = 0
    for tx in txs:
        importo = abs(float(tx.get("importo") or tx.get("lordo") or 0))
        if importo <= 0 or not tx.get("transaction_id"):
            continue
        # Confronto su un IMPORTO UNICO per fattura (coalesce total_amount/importo_totale)
        # invece di un $or sui due campi separatamente: con un $or, un documento con
        # total_amount e importo_totale disallineati (schema legacy vs nuovo) può
        # comparire come candidato per DUE transazioni di importo diverso, causando
        # match incrociati errati (es. due pagamenti distinti linkati alla stessa fattura).
        cands = await db[COLL_INVOICES].aggregate([
            {"$addFields": {"_importo_coalesced": {
                "$ifNull": ["$total_amount", "$importo_totale"]
            }}},
            {"$match": {"_importo_coalesced": {"$gte": importo - 0.05, "$lte": importo + 0.05}}},
            {"$project": {"_id": 0, "id": 1, "invoice_number": 1, "invoice_date": 1,
                          "supplier_name": 1, "cedente_denominazione": 1, "total_amount": 1}},
            {"$limit": 10},
        ]).to_list(10)
        if not cands:
            continue
        scelta = None
        nome = (tx.get("nome_controparte") or "").lower()
        parole = [w for w in nome.replace(",", " ").split() if len(w) >= 4]
        if parole:
            for c in cands:
                forn = ((c.get("supplier_name") or c.get("cedente_denominazione") or "")).lower()
                if any(w in forn for w in parole):
                    scelta = c
                    break
        # Senza nome controparte per corroborare il match, un solo candidato per
        # importo non è una prova sufficiente: lo segnaliamo come "solo_importo"
        # (bassa confidenza) invece di scriverlo come collegamento certo.
        confidenza_bassa = False
        if scelta is None and len(cands) == 1:
            scelta = cands[0]
            confidenza_bassa = not parole
        if scelta is None:
            continue
        await db[COLL_PAYPAL_TRANSACTIONS].update_one(
            {"transaction_id": tx["transaction_id"]},
            {"$set": {"fattura_associata": {
                "fattura_id": scelta["id"],
                "numero": scelta.get("invoice_number"),
                "data": scelta.get("invoice_date"),
                "fornitore": scelta.get("supplier_name") or scelta.get("cedente_denominazione"),
                "importo": scelta.get("total_amount"),
                "view_url": f"/api/fatture-ricevute/fattura/{scelta['id']}/view-assoinvoice",
                "auto": True,
                "match": "solo_importo" if confidenza_bassa else "nome_e_importo",
            }}},
        )
        associate += 1

    return {"success": True, "analizzate": len(txs), "associate": associate}


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
