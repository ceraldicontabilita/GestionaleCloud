"""
Parser per email notifiche fatture da Aruba
Estrae: fornitore, numero fattura, data, importo
Include riconciliazione automatica con estratto conto bancario
"""

import asyncio
import imaplib
import email
import re
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple, List
from bs4 import BeautifulSoup
import logging

logger = logging.getLogger(__name__)

ARUBA_SENDER = "noreply@fatturazioneelettronica.aruba.it"
ARUBA_SUBJECT = "Hai ricevuto una nuova fattura"


def extract_check_number(descrizione: str) -> Optional[str]:
    """
    Estrae il numero di assegno dalla descrizione del movimento bancario.
    
    Patterns supportati:
    - "NUM: 0208770631"
    - "ASSEGNO N. 12345"
    - "ASS. 12345"
    """
    if not descrizione:
        return None
    
    patterns = [
        r'NUM:\s*(\d+)',
        r'ASSEGNO\s*N\.?\s*(\d+)',
        r'ASS\.?\s*N?\.?\s*(\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, descrizione, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None


def determine_payment_method(descrizione: str) -> Tuple[str, Optional[str]]:
    """
    Determina il metodo di pagamento dalla descrizione del movimento bancario.
    
    Returns:
        Tuple[metodo, numero_assegno]
    """
    if not descrizione:
        return ("bonifico", None)
    
    desc_upper = descrizione.upper()
    
    if "ASSEGNO" in desc_upper or "ASS." in desc_upper:
        numero_assegno = extract_check_number(descrizione)
        return ("assegno", numero_assegno)
    elif "BONIFICO" in desc_upper or "BON." in desc_upper:
        return ("banca", None)
    elif "SEPA" in desc_upper:
        return ("banca", None)
    elif "CARTA" in desc_upper or "POS" in desc_upper:
        return ("banca", None)
    else:
        return ("bonifico", None)


async def find_bank_match(db, importo: float, data_documento: str, fornitore: str) -> Optional[Dict[str, Any]]:
    """
    Cerca un movimento corrispondente nell'estratto conto bancario.
    
    Criteri di match:
    - Stesso importo (tolleranza ±0.50€)
    - Data vicina (±60 giorni dalla data documento)
    - Tipo uscita
    
    Returns:
        Dict con info del movimento trovato o None
    """
    try:
        # Tolleranza importo
        importo_min = importo - 0.50
        importo_max = importo + 0.50
        
        # Cerca nella collezione estratto_conto
        # Prima prova match esatto per importo
        query = {
            "tipo": "uscita",
            "$or": [
                {"importo": {"$gte": importo_min, "$lte": importo_max}},
                {"importo": {"$gte": -importo_max, "$lte": -importo_min}}  # Alcuni sistemi usano valori negativi per uscite
            ]
        }
        
        # Se abbiamo la data, filtriamo anche per data vicina
        if data_documento:
            try:
                data_doc = datetime.strptime(data_documento, "%Y-%m-%d")
                data_min = (data_doc - timedelta(days=60)).strftime("%Y-%m-%d")
                data_max = (data_doc + timedelta(days=60)).strftime("%Y-%m-%d")
                query["data"] = {"$gte": data_min, "$lte": data_max}
            except:
                pass
        
        # Cerca match
        cursor = db["estratto_conto_movimenti"].find(query, {"_id": 0}).limit(10)
        matches = await cursor.to_list(10)
        
        if not matches:
            return None
        
        # Se c'è un solo match, usalo
        if len(matches) == 1:
            return matches[0]
        
        # Se ci sono più match, cerca quello con fornitore simile nella descrizione
        fornitore_parts = fornitore.upper().split()[:2]  # Prime 2 parole del fornitore
        
        for match in matches:
            desc = (match.get("descrizione") or "").upper()
            if any(part in desc for part in fornitore_parts if len(part) > 3):
                return match
        
        # Altrimenti ritorna il primo (per importo)
        return matches[0]
        
    except Exception as e:
        logger.error(f"Errore ricerca match bancario: {e}")
        return None


async def find_multiple_checks_match(db, importo: float, data_documento: str, fornitore: str, tolleranza_percentuale: float = 5.0) -> Optional[Dict[str, Any]]:
    """
    Cerca una combinazione di assegni che sommati corrispondono all'importo della fattura.
    
    Una fattura da €3000 può essere pagata con 3 assegni da €1000.
    
    Args:
        db: Database MongoDB
        importo: Importo della fattura
        data_documento: Data documento fattura
        fornitore: Nome fornitore
        tolleranza_percentuale: Tolleranza % sulla somma (default 5%)
    
    Returns:
        Dict con lista assegni trovati o None
    """
    try:
        # Tolleranza sulla somma
        tolleranza = importo * (tolleranza_percentuale / 100)
        importo_min = importo - tolleranza
        importo_max = importo + tolleranza
        
        # Range date
        data_min = None
        data_max = None
        if data_documento:
            try:
                data_doc = datetime.strptime(data_documento, "%Y-%m-%d")
                data_min = (data_doc - timedelta(days=90)).strftime("%Y-%m-%d")
                data_max = (data_doc + timedelta(days=90)).strftime("%Y-%m-%d")
            except:
                pass
        
        # Cerca tutti gli assegni nel periodo
        query = {
            "descrizione": {"$regex": "assegno", "$options": "i"}
        }
        if data_min and data_max:
            query["data"] = {"$gte": data_min, "$lte": data_max}
        
        cursor = db["estratto_conto_movimenti"].find(query, {"_id": 0}).limit(100)
        assegni = await cursor.to_list(100)
        
        if not assegni:
            return None
        
        # Converti importi in valori assoluti positivi
        for a in assegni:
            a["importo_abs"] = abs(a.get("importo", 0))
        
        # Cerca combinazioni di 2, 3 o 4 assegni che sommano all'importo
        from itertools import combinations
        
        for num_assegni in [2, 3, 4]:
            for combo in combinations(assegni, num_assegni):
                somma = sum(a["importo_abs"] for a in combo)
                if importo_min <= somma <= importo_max:
                    # Trovata combinazione!
                    assegni_trovati = []
                    for a in combo:
                        numero_assegno = extract_check_number(a.get("descrizione", ""))
                        assegni_trovati.append({
                            "id": a.get("id"),
                            "descrizione": a.get("descrizione"),
                            "data": a.get("data"),
                            "importo": a["importo_abs"],
                            "numero_assegno": numero_assegno
                        })
                    
                    return {
                        "tipo": "assegni_multipli",
                        "assegni": assegni_trovati,
                        "somma": somma,
                        "differenza": round(somma - importo, 2),
                        "num_assegni": len(assegni_trovati)
                    }
        
        return None
        
    except Exception as e:
        logger.error(f"Errore ricerca assegni multipli: {e}")
        return None


def parse_aruba_email_body(html_content: str) -> Optional[Dict[str, Any]]:
    """
    Estrae i dati della fattura dal corpo HTML dell'email Aruba.
    
    Returns:
        Dict con: fornitore, numero_fattura, data_documento, totale, netto
    """
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        text = soup.get_text()
        
        # Pulisci spazi multipli
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
        # Pulisci fornitore da parti tra parentesi se troppo lungo
        if len(fornitore) > 80:
            fornitore = re.sub(r'\s*\([^)]+\)\s*', ' ', fornitore).strip()
        
        # Converti importo (formato italiano: 1.234,56 -> 1234.56)
        totale_str = totale_match.group(1).replace('.', '').replace(',', '.')
        netto_str = netto_match.group(1).replace('.', '').replace(',', '.') if netto_match else totale_str
        
        # Converti data
        data_str = data_match.group(1) if data_match else None
        data_documento = None
        if data_str:
            try:
                data_documento = datetime.strptime(data_str, "%d/%m/%Y").strftime("%Y-%m-%d")
            except:
                data_documento = data_str
        
        return {
            "fornitore": fornitore,
            "numero_fattura": numero_match.group(1),
            "data_documento": data_documento,
            "tipo_documento": tipo_match.group(1) if tipo_match else "Fattura",
            "totale": float(totale_str),
            "netto_pagare": float(netto_str)
        }
    except Exception as e:
        logger.error(f"Errore parsing email Aruba: {e}")
        return None


def generate_email_hash(fornitore: str, numero: str, data: str, importo: float) -> str:
    """Genera hash univoco per identificare duplicati."""
    content = f"{fornitore}|{numero}|{data}|{importo}"
    return hashlib.md5(content.encode()).hexdigest()


def _fetch_emails_imap_sync(
    email_user: str,
    email_password: str,
    since_days: int
) -> tuple:
    """
    Funzione SINCRONA pura per IMAP — gira in asyncio.to_thread().
    NON blocca l'event loop FastAPI.
    Restituisce (lista_email_raw, numero_totale_email_trovate).
    """
    result: List[Dict] = []
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    try:
        mail.login(email_user, email_password)
        mail.select("INBOX")

        search_criteria = f'FROM "{ARUBA_SENDER}" SUBJECT "{ARUBA_SUBJECT}"'
        since_date = (datetime.now() - timedelta(days=since_days)).strftime("%d-%b-%Y")
        search_criteria = f'({search_criteria} SINCE {since_date})'

        _, messages = mail.search(None, search_criteria)
        email_ids = messages[0].split()

        for eid in email_ids:
            try:
                _, msg_data = mail.fetch(eid, "(RFC822)")
                msg = email.message_from_bytes(msg_data[0][1])

                html_body = None
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/html":
                            html_body = part.get_payload(decode=True).decode("utf-8", errors="replace")
                            break
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        html_body = payload.decode("utf-8", errors="replace")

                if html_body:
                    result.append({
                        "html_body": html_body,
                        "email_date": msg.get("Date", ""),
                    })
            except Exception as e:
                logger.error(f"Errore fetch singola email IMAP: {e}")
    finally:
        try:
            mail.logout()
        except Exception:
            pass
    return result, len(result)


async def fetch_aruba_invoices(
    db,
    email_user: str,
    email_password: str,
    since_days: int = 30
) -> Dict[str, Any]:
    """
    Scarica le notifiche fatture da Aruba e le salva in 'operazioni_da_confermare'.
    Include riconciliazione automatica con estratto conto bancario.
    
    Args:
        db: Database MongoDB
        email_user: Email account
        email_password: Password app
        since_days: Giorni indietro da controllare
        
    Returns:
        Statistiche sul download
    """
    stats = {
        "emails_checked": 0,
        "invoices_found": 0,
        "new_invoices": 0,
        "duplicates_skipped": 0,
        "riconciliate_auto": 0,
        "non_riconciliate": 0,
        "errors": 0
    }
    
    try:
        # ── IMAP in thread separato (NON blocca l'event loop FastAPI) ──
        raw_emails, total_checked = await asyncio.to_thread(
            _fetch_emails_imap_sync, email_user, email_password, since_days
        )
        stats["emails_checked"] = total_checked
        logger.info(f"Email Aruba trovate: {total_checked}")

        for raw in raw_emails:
            try:
                html_body = raw["html_body"]
                email_date = raw["email_date"]
                
                # Parsa email
                invoice_data = parse_aruba_email_body(html_body)
                if not invoice_data:
                    continue
                
                stats["invoices_found"] += 1
                
                # Genera hash per check duplicati
                email_hash = generate_email_hash(
                    invoice_data["fornitore"],
                    invoice_data["numero_fattura"],
                    invoice_data["data_documento"],
                    invoice_data["totale"]
                )
                
                # Controlla se già esiste nelle operazioni
                existing = await db["operazioni_da_confermare"].find_one({"email_hash": email_hash})
                if existing:
                    stats["duplicates_skipped"] += 1
                    continue
                
                # === NUOVO: Controlla se la fattura esiste già ===
                # 1. Controlla nelle fatture XML importate
                fattura_xml = await db["invoices"].find_one({
                    "$or": [
                        {"numero_fattura": invoice_data["numero_fattura"]},
                        {"invoice_number": invoice_data["numero_fattura"]}
                    ],
                    "$or": [
                        {"supplier_name": {"$regex": invoice_data["fornitore"][:20], "$options": "i"}},
                        {"cedente_denominazione": {"$regex": invoice_data["fornitore"][:20], "$options": "i"}}
                    ]
                })
                
                # 2. Controlla in prima nota cassa
                prima_nota_cassa = await db["prima_nota_cassa"].find_one({
                    "numero_fattura": invoice_data["numero_fattura"],
                    "fornitore": {"$regex": invoice_data["fornitore"][:20], "$options": "i"}
                })
                
                # 3. Controlla in prima nota banca
                prima_nota_banca = await db["prima_nota_banca"].find_one({
                    "numero_fattura": invoice_data["numero_fattura"],
                    "fornitore": {"$regex": invoice_data["fornitore"][:20], "$options": "i"}
                })
                
                # 4. Controlla nel dizionario operazioni elaborate
                gia_elaborata = await db["aruba_elaborazioni"].find_one({
                    "numero_fattura": invoice_data["numero_fattura"],
                    "fornitore": invoice_data["fornitore"],
                    "stato": {"$in": ["inserita_cassa", "inserita_banca", "inserita_assegno", "scartata"]}
                })
                
                if fattura_xml or prima_nota_cassa or prima_nota_banca or gia_elaborata:
                    stats["duplicates_skipped"] += 1
                    # Salva nel dizionario per tracciamento
                    await db["aruba_elaborazioni"].update_one(
                        {
                            "email_hash": email_hash,
                            "numero_fattura": invoice_data["numero_fattura"]
                        },
                        {
                            "$set": {
                                "fornitore": invoice_data["fornitore"],
                                "numero_fattura": invoice_data["numero_fattura"],
                                "importo": invoice_data["totale"],
                                "data_documento": invoice_data["data_documento"],
                                "stato": "gia_presente",
                                "fonte_duplicato": "xml" if fattura_xml else "cassa" if prima_nota_cassa else "banca" if prima_nota_banca else "aruba",
                                "updated_at": datetime.now(timezone.utc).isoformat()
                            },
                            "$setOnInsert": {
                                "created_at": datetime.now(timezone.utc).isoformat()
                            }
                        },
                        upsert=True
                    )
                    continue
                
                # Data email (viene dal dict raw)
                email_date = raw["email_date"]
                
                # Cerca fornitore nel database per proporre metodo pagamento
                fornitore_db = await db["fornitori"].find_one({
                    "$or": [
                        {"ragione_sociale": {"$regex": invoice_data["fornitore"][:30], "$options": "i"}},
                        {"ragione_sociale": {"$regex": invoice_data["fornitore"].split()[0], "$options": "i"}}
                    ]
                })
                
                metodo_pagamento_proposto = "bonifico"  # Default
                fornitore_id = None
                if fornitore_db:
                    metodo_pagamento_proposto = fornitore_db.get("metodo_pagamento", "bonifico")
                    fornitore_id = fornitore_db.get("id")
                
                # Estrai anno dalla data documento per separazione fiscale
                anno_fiscale = None
                if invoice_data["data_documento"]:
                    try:
                        anno_fiscale = int(invoice_data["data_documento"].split("-")[0])
                    except:
                        anno_fiscale = datetime.now().year
                else:
                    anno_fiscale = datetime.now().year
                
                # === RICONCILIAZIONE AUTOMATICA CON ESTRATTO CONTO ===
                riconciliato_auto = False
                numero_assegno_auto = None
                estratto_conto_match = None
                assegni_multipli = None
                da_verificare = False  # Flag per casi dubbi (assegni multipli)
                
                # Prima cerca match singolo (importo esatto)
                bank_match = await find_bank_match(
                    db, 
                    invoice_data["totale"], 
                    invoice_data["data_documento"],
                    invoice_data["fornitore"]
                )
                
                if bank_match:
                    riconciliato_auto = True
                    estratto_conto_match = {
                        "tipo": "singolo",
                        "id": bank_match.get("id"),
                        "descrizione": bank_match.get("descrizione"),
                        "data": bank_match.get("data"),
                        "importo": bank_match.get("importo")
                    }
                    
                    # Determina metodo di pagamento dalla descrizione bancaria
                    metodo_from_bank, numero_assegno_auto = determine_payment_method(
                        bank_match.get("descrizione")
                    )
                    
                    # Se trovato match, usa il metodo dall'estratto conto
                    if metodo_from_bank == "assegno":
                        metodo_pagamento_proposto = "assegno"
                    elif metodo_from_bank == "banca":
                        metodo_pagamento_proposto = "banca"
                    
                    stats["riconciliate_auto"] += 1
                    logger.info(f"Riconciliata auto: {invoice_data['fornitore'][:30]} | €{invoice_data['totale']} -> {metodo_pagamento_proposto}")
                else:
                    # Se non trovato match singolo, cerca assegni multipli
                    multi_match = await find_multiple_checks_match(
                        db,
                        invoice_data["totale"],
                        invoice_data["data_documento"],
                        invoice_data["fornitore"]
                    )
                    
                    if multi_match:
                        riconciliato_auto = True
                        da_verificare = True  # Richiede conferma utente
                        metodo_pagamento_proposto = "assegno"
                        assegni_multipli = multi_match["assegni"]
                        
                        # Usa i numeri degli assegni trovati
                        numeri_assegni = [a.get("numero_assegno") for a in assegni_multipli if a.get("numero_assegno")]
                        if numeri_assegni:
                            numero_assegno_auto = ", ".join(numeri_assegni)
                        
                        estratto_conto_match = {
                            "tipo": "multiplo",
                            "assegni": assegni_multipli,
                            "somma": multi_match["somma"],
                            "differenza": multi_match["differenza"],
                            "num_assegni": multi_match["num_assegni"]
                        }
                        
                        stats["riconciliate_auto"] += 1
                        logger.info(f"Riconciliata MULTIPLA: {invoice_data['fornitore'][:30]} | €{invoice_data['totale']} -> {multi_match['num_assegni']} assegni")
                    else:
                        stats["non_riconciliate"] += 1
                
                # Salva in operazioni_da_confermare
                operazione = {
                    "id": hashlib.md5(f"{email_hash}{datetime.now().isoformat()}".encode()).hexdigest()[:16],
                    "email_hash": email_hash,
                    "fornitore": invoice_data["fornitore"],
                    "fornitore_id": fornitore_id,
                    "numero_fattura": invoice_data["numero_fattura"],
                    "data_documento": invoice_data["data_documento"],
                    "anno": anno_fiscale,  # Anno fiscale per separazione contabilità
                    "tipo_documento": invoice_data["tipo_documento"],
                    "importo": invoice_data["totale"],
                    "netto_pagare": invoice_data["netto_pagare"],
                    "metodo_pagamento_proposto": metodo_pagamento_proposto,
                    "metodo_pagamento_confermato": None,
                    "numero_assegno": numero_assegno_auto,  # Pre-compilato se trovato
                    "stato": "da_verificare" if da_verificare else "da_confermare",
                    "prima_nota_id": None,
                    "riconciliato_auto": riconciliato_auto,
                    "da_verificare": da_verificare,  # True se assegni multipli (richiede conferma)
                    "assegni_multipli": assegni_multipli,  # Lista assegni se pagamento multiplo
                    "estratto_conto_match": estratto_conto_match,
                    "email_date": email_date,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "confirmed_at": None,
                    "fonte": "aruba_email"
                }
                
                await db["operazioni_da_confermare"].insert_one(operazione.copy())
                stats["new_invoices"] += 1
                
            except Exception as e:
                logger.error(f"Errore processamento email: {e}")
                stats["errors"] += 1
        
    except Exception as e:
        logger.error(f"Errore fetch/processamento email Aruba: {e}")
        raise
    
    return {
        "success": True,
        "stats": stats
    }
