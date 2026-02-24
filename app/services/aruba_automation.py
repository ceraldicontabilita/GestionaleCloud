"""
Automazione Completa Fatture da Email Aruba
===========================================

FLUSSO:
1. Scarica email da Aruba (notifiche fatture)
2. Estrai dati dal corpo: fornitore, numero, data, importo
3. Crea "fattura_provvisoria" in attesa dell'XML
4. Cerca riconciliazione con estratto conto bancario:
   - Se trova match → pagata_banca (inserisci in prima nota banca)
   - Se non trova → probabile_cassa (inserisci in prima nota cassa)
5. Quando arriva l'XML → associa e chiudi il cerchio

Collezione: fatture_provvisorie
"""
import imaplib
import email
import re
import hashlib
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List
from bs4 import BeautifulSoup
import logging
import os

logger = logging.getLogger(__name__)

ARUBA_SENDER = "noreply@fatturazioneelettronica.aruba.it"
ARUBA_SUBJECT = "Hai ricevuto una nuova fattura"
COLL_FATTURE_PROVVISORIE = "fatture_provvisorie"


def parse_aruba_email_body(html_content: str) -> Optional[Dict[str, Any]]:
    """Estrae i dati della fattura dal corpo HTML dell'email Aruba."""
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        text = soup.get_text()
        text_clean = re.sub(r'\s+', ' ', text)
        
        # Estrai fornitore
        fornitore_match = re.search(r"dall['\u2019]azienda\s+(.+?)\.\s*Di seguito", text_clean)
        if not fornitore_match:
            fornitore_match = re.search(r"fattura elettronica dall['\u2019]azienda\s+(.+?)[\.,]", text_clean)
        
        # Estrai altri campi
        numero_match = re.search(r"Numero:\s*(\S+)", text_clean)
        data_match = re.search(r"Data documento:\s*(\d{2}/\d{2}/\d{4})", text_clean)
        tipo_match = re.search(r"Tipo documento:\s*(\w+)", text_clean)
        totale_match = re.search(r"Totale documento:\s*([\d.,]+)", text_clean)
        netto_match = re.search(r"Netto a pagare:\s*([\d.,]+)", text_clean)
        
        if not numero_match or not totale_match:
            return None
        
        fornitore = fornitore_match.group(1).strip() if fornitore_match else "Fornitore sconosciuto"
        if len(fornitore) > 80:
            fornitore = re.sub(r'\s*\([^)]+\)\s*', ' ', fornitore).strip()
        
        # Converti importo (formato italiano: 1.234,56 -> 1234.56)
        totale_str = totale_match.group(1).replace('.', '').replace(',', '.')
        netto_str = netto_match.group(1).replace('.', '').replace(',', '.') if netto_match else totale_str
        
        try:
            totale_float = float(totale_str)
            netto_float = float(netto_str)
        except (ValueError, TypeError) as e:
            logger.error(f"Errore conversione importi: totale='{totale_str}', netto='{netto_str}': {e}")
            raise ValueError(f"Importi non validi: {e}")
        
        # Converti data
        data_str = data_match.group(1) if data_match else None
        data_documento = None
        if data_str:
            try:
                data_documento = datetime.strptime(data_str, "%d/%m/%Y").strftime("%Y-%m-%d")
            except ValueError as e:
                logger.warning(f"Errore parsing data '{data_str}': {e}")
                data_documento = data_str
        
        return {
            "fornitore": fornitore,
            "numero_fattura": numero_match.group(1),
            "data_documento": data_documento,
            "data_documento_raw": data_str,
            "tipo_documento": tipo_match.group(1) if tipo_match else "Fattura",
            "totale": totale_float,
            "netto_pagare": netto_float
        }
    except Exception as e:
        logger.error(f"Errore parsing email Aruba: {e}")
        return None


def generate_hash(fornitore: str, numero: str, importo: float) -> str:
    """Genera hash univoco per identificare duplicati."""
    content = f"{fornitore}|{numero}|{importo}"
    return hashlib.md5(content.encode()).hexdigest()


async def find_bank_match(db, importo: float, data_documento: str, fornitore: str) -> Optional[Dict[str, Any]]:
    """
    Cerca un movimento corrispondente nell'estratto conto bancario.
    
    Criteri:
    - Stesso importo (tolleranza ±1€)
    - Data vicina (±60 giorni)
    - Tipo uscita (importo negativo)
    """
    try:
        # Calcola range date
        if data_documento:
            try:
                data_doc = datetime.strptime(data_documento, "%Y-%m-%d")
            except ValueError as e:
                logger.warning(f"Errore parsing data documento '{data_documento}': {e}")
                data_doc = datetime.now()
        else:
            data_doc = datetime.now()
        
        data_inizio = (data_doc - timedelta(days=60)).strftime("%Y-%m-%d")
        data_fine = (data_doc + timedelta(days=30)).strftime("%Y-%m-%d")
        
        # Cerca movimento con importo simile (negativo = uscita)
        # L'importo in banca è negativo per le uscite
        query = {
            "data": {"$gte": data_inizio, "$lte": data_fine},
            "$or": [
                {"importo": {"$gte": -importo - 1, "$lte": -importo + 1}},
                {"importo": {"$gte": importo - 1, "$lte": importo + 1}}
            ]
        }
        
        # Prima cerca con fornitore nel nome
        fornitore_words = fornitore.split()[:2] if fornitore else []  # Prime 2 parole
        if fornitore_words:
            query_with_name = {
                **query,
                "descrizione": {"$regex": fornitore_words[0], "$options": "i"}
            }
            match = await db["estratto_conto_movimenti"].find_one(query_with_name, {"_id": 0})
            if match:
                return match
        
        # Altrimenti cerca solo per importo
        match = await db["estratto_conto_movimenti"].find_one(query, {"_id": 0})
        return match
        
    except Exception as e:
        logger.error(f"Errore find_bank_match: {e}")
        return None


async def find_supplier(db, fornitore_nome: str) -> Optional[Dict[str, Any]]:
    """Cerca il fornitore nel database. Se non esiste, lo crea."""
    if not fornitore_nome:
        return None
    
    # Cerca per nome simile in fornitori_dizionario (collezione principale)
    fornitore_words = fornitore_nome.split()[:2] if fornitore_nome else []
    for word in fornitore_words:
        if len(word) > 3:
            # Prima cerca in fornitori_dizionario
            supplier = await db["fornitori_dizionario"].find_one(
                {"$or": [
                    {"ragione_sociale": {"$regex": word, "$options": "i"}},
                    {"denominazione": {"$regex": word, "$options": "i"}},
                    {"nome": {"$regex": word, "$options": "i"}}
                ]},
                {"_id": 0, "id": 1, "ragione_sociale": 1, "metodo_pagamento": 1}
            )
            if supplier:
                return supplier
            
            # Fallback su fornitori (già unificata)
            supplier = await db["suppliers"].find_one(
                {"$or": [
                    {"ragione_sociale": {"$regex": word, "$options": "i"}},
                    {"denominazione": {"$regex": word, "$options": "i"}}
                ]},
                {"_id": 0, "id": 1, "ragione_sociale": 1, "metodo_pagamento": 1}
            )
            if supplier:
                return supplier
    
    # NON TROVATO: Crea automaticamente il fornitore
    nuovo_fornitore = {
        "id": str(uuid.uuid4()),
        "ragione_sociale": fornitore_nome,
        "denominazione": fornitore_nome,
        "metodo_pagamento": "bonifico",  # Default: bonifico (la maggior parte paga così)
        "tipo": "fornitore",
        "attivo": True,
        "fonte": "aruba_email_auto",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Inserisci in fornitori_dizionario
    await db["fornitori_dizionario"].insert_one(nuovo_fornitore.copy())
    logger.info(f"🆕 Fornitore creato automaticamente: {fornitore_nome}")
    
    return {
        "id": nuovo_fornitore["id"],
        "ragione_sociale": fornitore_nome,
        "metodo_pagamento": "bonifico"
    }


async def check_xml_exists(db, numero_fattura: str, fornitore: str) -> Optional[Dict[str, Any]]:
    """Verifica se l'XML della fattura è già presente."""
    # Cerca per numero fattura
    fattura = await db["invoices"].find_one(
        {"$or": [
            {"invoice_number": numero_fattura},
            {"numero_fattura": numero_fattura}
        ]},
        {"_id": 0, "id": 1, "invoice_number": 1, "supplier_name": 1, "total_amount": 1}
    )
    
    if fattura:
        return fattura
    
    # Cerca anche con fornitore
    if fornitore:
        fornitore_word = fornitore.split()[0] if fornitore.split() else ""
        if fornitore_word:
            fattura = await db["invoices"].find_one(
                {
                    "invoice_number": numero_fattura,
                    "supplier_name": {"$regex": fornitore_word, "$options": "i"}
                },
                {"_id": 0, "id": 1, "invoice_number": 1, "supplier_name": 1}
            )
            if fattura:
                return fattura
    
    return None


async def insert_prima_nota(db, fattura_data: Dict[str, Any], metodo: str, bank_match: Optional[Dict] = None) -> str:
    """
    Inserisce il movimento in Prima Nota.
    
    Args:
        fattura_data: Dati fattura
        metodo: 'banca' o 'cassa'
        bank_match: Movimento bancario associato (se trovato)
    """
    prima_nota_id = str(uuid.uuid4())
    
    movimento = {
        "id": prima_nota_id,
        "data": fattura_data.get("data_documento") or datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "tipo": "uscita",
        "causale": f"Fattura {fattura_data.get('numero_fattura')} - {fattura_data.get('fornitore', '')[:50]}",
        "descrizione": f"Fattura da {fattura_data.get('fornitore')}",
        "fornitore": fattura_data.get("fornitore"),
        "fornitore_id": fattura_data.get("fornitore_id"),
        "numero_fattura": fattura_data.get("numero_fattura"),
        "importo": fattura_data.get("totale"),
        "netto_pagare": fattura_data.get("netto_pagare"),
        "metodo_pagamento": metodo,
        "fonte": "aruba_email_auto",
        "fattura_provvisoria_id": fattura_data.get("id"),
        "riconciliato_auto": bank_match is not None,
        "movimento_banca_id": bank_match.get("id") if bank_match else None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    collection = "prima_nota_banca" if metodo == "banca" else "prima_nota_cassa"
    await db[collection].insert_one(movimento.copy())
    
    return prima_nota_id


async def process_aruba_emails(
    db,
    email_user: str,
    email_password: str,
    since_days: int = 7,
    auto_insert_prima_nota: bool = False
) -> Dict[str, Any]:
    """
    Processo completo di automazione fatture Aruba.
    
    FLUSSO:
    1. Scarica email Aruba
    2. Estrai dati dal corpo
    3. Verifica se XML già presente → se sì, salta
    4. Verifica se già elaborata → se sì, salta
    5. Crea fattura_provvisoria
    6. Cerca match in estratto conto:
       - Se trova → pagata_banca → inserisci in prima nota banca
       - Se non trova → probabile_cassa → inserisci in prima nota cassa
    7. Attende XML per completare
    """
    stats = {
        "emails_checked": 0,
        "fatture_trovate": 0,
        "gia_presenti_xml": 0,
        "gia_elaborate": 0,
        "nuove_provvisorie": 0,
        "riconciliate_banca": 0,
        "inserite_cassa": 0,
        "errori": 0
    }
    
    fatture_processate = []
    
    try:
        # Connessione IMAP
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(email_user, email_password)
        mail.select("INBOX")
        
        # Cerca email Aruba
        since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
        search_criteria = f'(FROM "{ARUBA_SENDER}" SINCE {since_date})'
        
        _, messages = mail.search(None, search_criteria)
        email_ids = messages[0].split()
        
        stats["emails_checked"] = len(email_ids)
        logger.info(f"📧 Email Aruba trovate: {len(email_ids)}")
        
        for eid in email_ids:
            try:
                _, msg_data = mail.fetch(eid, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])
                
                # Estrai corpo HTML
                html_body = None
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/html":
                            html_body = part.get_payload(decode=True).decode('utf-8', errors='replace')
                            break
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        html_body = payload.decode('utf-8', errors='replace')
                
                if not html_body:
                    continue
                
                # Parse email
                invoice_data = parse_aruba_email_body(html_body)
                if not invoice_data:
                    continue
                
                stats["fatture_trovate"] += 1
                
                # Genera hash per check duplicati
                doc_hash = generate_hash(
                    invoice_data["fornitore"],
                    invoice_data["numero_fattura"],
                    invoice_data["totale"]
                )
                
                # 1. Verifica se XML già presente
                xml_exists = await check_xml_exists(
                    db, 
                    invoice_data["numero_fattura"],
                    invoice_data["fornitore"]
                )
                if xml_exists:
                    stats["gia_presenti_xml"] += 1
                    logger.debug(f"XML già presente: {invoice_data['numero_fattura']}")
                    continue
                
                # 2. Verifica se già elaborata come provvisoria
                existing = await db[COLL_FATTURE_PROVVISORIE].find_one({"hash": doc_hash})
                if existing:
                    stats["gia_elaborate"] += 1
                    continue
                
                # 3. Cerca fornitore nel DB
                supplier = await find_supplier(db, invoice_data["fornitore"])
                if supplier:
                    invoice_data["fornitore_id"] = supplier.get("id")
                    invoice_data["metodo_pagamento_abituale"] = supplier.get("metodo_pagamento", "cassa")
                
                # 4. Cerca match in estratto conto
                bank_match = await find_bank_match(
                    db,
                    invoice_data["totale"],
                    invoice_data["data_documento"],
                    invoice_data["fornitore"]
                )
                
                # 5. Determina metodo pagamento
                # REGOLA: Il metodo di pagamento del FORNITORE ha la priorità!
                metodo_fornitore = invoice_data.get("metodo_pagamento_abituale", "").lower()
                
                if bank_match:
                    # Trovato in estratto conto → sicuramente banca, riconciliato
                    metodo_pagamento = "banca"
                    stato = "pagata_banca"
                    stats["riconciliate_banca"] += 1
                    logger.info(f"✅ Riconciliata BANCA: {invoice_data['fornitore'][:30]} | €{invoice_data['totale']}")
                elif metodo_fornitore in ["banca", "bonifico", "rid", "sepa"]:
                    # Fornitore paga sempre in banca → banca in attesa di riconciliazione
                    metodo_pagamento = "banca"
                    stato = "attesa_riconciliazione_banca"
                    stats["riconciliate_banca"] += 1  # Conta come banca
                    logger.info(f"🏦 BANCA (da fornitore): {invoice_data['fornitore'][:30]} | €{invoice_data['totale']} - attesa riconciliazione")
                elif metodo_fornitore in ["cassa", "contanti"]:
                    # Fornitore paga sempre in cassa
                    metodo_pagamento = "cassa"
                    stato = "pagata_cassa"
                    stats["inserite_cassa"] += 1
                    logger.info(f"💵 CASSA (da fornitore): {invoice_data['fornitore'][:30]} | €{invoice_data['totale']}")
                else:
                    # Metodo non definito e non trovato in banca → probabile cassa
                    metodo_pagamento = "cassa"
                    stato = "probabile_cassa"
                    stats["inserite_cassa"] += 1
                    logger.info(f"❓ Probabile CASSA: {invoice_data['fornitore'][:30]} | €{invoice_data['totale']}")
                
                # 6. Crea fattura provvisoria
                fattura_provvisoria = {
                    "id": str(uuid.uuid4()),
                    "hash": doc_hash,
                    "fornitore": invoice_data["fornitore"],
                    "fornitore_id": invoice_data.get("fornitore_id"),
                    "numero_fattura": invoice_data["numero_fattura"],
                    "data_documento": invoice_data["data_documento"],
                    "data_documento_raw": invoice_data.get("data_documento_raw"),
                    "tipo_documento": invoice_data["tipo_documento"],
                    "totale": invoice_data["totale"],
                    "netto_pagare": invoice_data["netto_pagare"],
                    "stato": stato,
                    "metodo_pagamento": metodo_pagamento,
                    "xml_associato": False,
                    "xml_invoice_id": None,
                    "prima_nota_id": None,
                    "prima_nota_collection": None,
                    "riconciliato_auto": bank_match is not None,
                    "movimento_banca_id": bank_match.get("id") if bank_match else None,
                    "movimento_banca_data": bank_match.get("data") if bank_match else None,
                    "email_date": msg.get("Date", ""),
                    "fonte": "aruba_email",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
                
                # 7. Inserisci in Prima Nota se auto_insert è abilitato
                if auto_insert_prima_nota:
                    prima_nota_id = await insert_prima_nota(db, fattura_provvisoria, metodo_pagamento, bank_match)
                    fattura_provvisoria["prima_nota_id"] = prima_nota_id
                    fattura_provvisoria["prima_nota_collection"] = f"prima_nota_{metodo_pagamento}"
                
                # 8. Salva fattura provvisoria
                await db[COLL_FATTURE_PROVVISORIE].insert_one(fattura_provvisoria.copy())
                stats["nuove_provvisorie"] += 1
                
                fatture_processate.append({
                    "fornitore": invoice_data["fornitore"][:50],
                    "numero_fattura": invoice_data["numero_fattura"],
                    "data": invoice_data["data_documento"],
                    "totale": invoice_data["totale"],
                    "stato": stato,
                    "metodo_pagamento": metodo_pagamento,
                    "riconciliato": bank_match is not None
                })
                
            except Exception as e:
                logger.error(f"Errore processamento email: {e}")
                stats["errori"] += 1
        
        mail.close()
        mail.logout()
        
    except Exception as e:
        logger.error(f"Errore connessione IMAP: {e}")
        return {"success": False, "error": str(e), "stats": stats}
    
    return {
        "success": True,
        "stats": stats,
        "fatture": fatture_processate
    }


async def associate_xml_to_provvisoria(db, xml_invoice: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Quando arriva un XML, cerca se esiste una fattura provvisoria corrispondente
    e la associa, completando il ciclo.
    
    Args:
        xml_invoice: Fattura XML appena importata
        
    Returns:
        Fattura provvisoria associata (se trovata)
    """
    numero_fattura = xml_invoice.get("invoice_number") or xml_invoice.get("numero_fattura")
    fornitore = xml_invoice.get("supplier_name") or xml_invoice.get("fornitore")
    totale = xml_invoice.get("total_amount") or xml_invoice.get("totale")
    
    if not numero_fattura:
        return None
    
    # Cerca fattura provvisoria con stesso numero
    provvisoria = await db[COLL_FATTURE_PROVVISORIE].find_one({
        "numero_fattura": numero_fattura,
        "xml_associato": False
    }, {"_id": 0})
    
    if not provvisoria:
        # Prova anche con match più ampio
        if fornitore:
            fornitore_words = fornitore.split()
            fornitore_word = fornitore_words[0] if fornitore_words else ""
            if fornitore_word:
                provvisoria = await db[COLL_FATTURE_PROVVISORIE].find_one({
                    "numero_fattura": numero_fattura,
                    "fornitore": {"$regex": fornitore_word, "$options": "i"},
                    "xml_associato": False
                }, {"_id": 0})
    
    if not provvisoria:
        # Ultimo tentativo: numero fattura + importo simile
        if totale:
            provvisoria = await db[COLL_FATTURE_PROVVISORIE].find_one({
                "numero_fattura": numero_fattura,
                "totale": {"$gte": totale - 1, "$lte": totale + 1},
                "xml_associato": False
            }, {"_id": 0})
    
    if provvisoria:
        # Associa XML alla provvisoria
        await db[COLL_FATTURE_PROVVISORIE].update_one(
            {"id": provvisoria["id"]},
            {"$set": {
                "xml_associato": True,
                "xml_invoice_id": xml_invoice.get("id"),
                "stato": "completata",
                "completata_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        logger.info(f"✅ XML associato a provvisoria: {numero_fattura} -> {provvisoria['id']}")
        return provvisoria
    
    return None


async def get_fatture_provvisorie_stats(db) -> Dict[str, Any]:
    """Statistiche fatture provvisorie."""
    stats = {
        "totale": await db[COLL_FATTURE_PROVVISORIE].count_documents({}),
        "in_attesa_xml": await db[COLL_FATTURE_PROVVISORIE].count_documents({"xml_associato": False}),
        "completate": await db[COLL_FATTURE_PROVVISORIE].count_documents({"xml_associato": True}),
        "pagate_banca": await db[COLL_FATTURE_PROVVISORIE].count_documents({"stato": "pagata_banca"}),
        "pagate_cassa": await db[COLL_FATTURE_PROVVISORIE].count_documents({"stato": "probabile_cassa"}),
        "importo_totale": 0,
        "importo_in_attesa": 0
    }
    
    # Calcola importi
    pipeline_totale = [
        {"$group": {"_id": None, "totale": {"$sum": "$totale"}}}
    ]
    result = await db[COLL_FATTURE_PROVVISORIE].aggregate(pipeline_totale).to_list(1)
    if result:
        stats["importo_totale"] = result[0].get("totale", 0)
    
    pipeline_attesa = [
        {"$match": {"xml_associato": False}},
        {"$group": {"_id": None, "totale": {"$sum": "$totale"}}}
    ]
    result = await db[COLL_FATTURE_PROVVISORIE].aggregate(pipeline_attesa).to_list(1)
    if result:
        stats["importo_in_attesa"] = result[0].get("totale", 0)
    
    return stats
