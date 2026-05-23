"""
Router per gestione estratti conto PayPal (MSR/CSR).
Import PDF, visualizzazione transazioni, riconciliazione con estratto conto bancario.
"""
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
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
        pag_query, {"_id": 0, "lordo": 1, "tipo": 1, "nome_controparte": 1}
    ).to_list(2000)
    
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
    ec_paypal = await db[COLL_ESTRATTO_CONTO].count_documents(
        {"descrizione": {"$regex": "paypal", "$options": "i"}}
    )
    
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
