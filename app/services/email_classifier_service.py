"""
Servizio di Classificazione Intelligente Email
Sistema unificato per classificare, processare e associare email ai moduli del gestionale.

Mapping Email -> Sezioni Gestionale:
- Verbali/Multe -> Fatture Noleggio
- Dimissioni -> Anagrafica Dipendenti  
- Cartelle Esattoriali -> Commercialista
- F24 -> Gestione F24
- Buste Paga -> Cedolini
- Bonifici Stipendi -> Prima Nota Salari
- Delibere FONSI/INPS -> Documenti INPS
- ADR/Rottamazione -> ADR
- Fatture -> Ciclo Passivo
"""

import imaplib
import email
from email.header import decode_header
import os
import re
import base64
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Configurazione email
EMAIL = os.environ.get("EMAIL_ADDRESS", "")
EMAIL_PASSWORD = os.environ.get("EMAIL_APP_PASSWORD", "")
IMAP_SERVER = os.environ.get("IMAP_SERVER", "imap.gmail.com")


@dataclass
class EmailRule:
    """Regola di classificazione email."""
    name: str
    keywords: List[str]  # Parole chiave da cercare (OR)
    subject_patterns: List[str]  # Pattern regex per subject
    sender_patterns: List[str]  # Pattern per mittente
    category: str  # Categoria nel sistema
    gestionale_section: str  # Sezione del gestionale
    collection: str  # Collection MongoDB
    action: str  # Tipo di azione: 'save_pdf', 'extract_data', 'associate'
    priority: int = 0  # Priorità (più alto = più prioritario)


# ============================================================
# REGOLE DI CLASSIFICAZIONE EMAIL
# ============================================================

EMAIL_RULES: List[EmailRule] = [
    # --- VERBALI NOLEGGIO ---
    EmailRule(
        name="verbali_noleggio",
        keywords=["verbale", "multa", "infrazione", "contravvenzione", "violazione codice strada"],
        subject_patterns=[r"verbale\s*n", r"B\d{10,}", r"multa", r"infrazione"],
        sender_patterns=["leasys", "ald", "arval", "europcar", "hertz", "avis"],
        category="verbali",
        gestionale_section="Noleggio Auto",
        collection="verbali_noleggio",
        action="associate_fattura",
        priority=10
    ),
    
    # --- DIMISSIONI DIPENDENTI ---
    EmailRule(
        name="dimissioni",
        keywords=["Notifica richiesta recesso", "dimissioni", "cessazione rapporto", "recesso"],
        subject_patterns=[r"notifica.*recesso", r"dimission", r"cessazione.*rapporto"],
        sender_patterns=["inps", "lavoro.gov", "cliclavoro"],
        category="dimissioni",
        gestionale_section="Anagrafica Dipendenti",
        collection="dimissioni",
        action="update_employee",
        priority=15
    ),
    
    # --- CARTELLE ESATTORIALI / ADR ---
    EmailRule(
        name="cartelle_esattoriali",
        keywords=["cartella esattoriale", "Agenzia delle entrate-Riscossione", "AdER", "rottamazione", "definizione agevolata", "intimazione"],
        subject_patterns=[r"cartella\s*(di\s*)?pagamento", r"agenzia.*riscossione", r"rottamazione", r"definizione\s*agevolata"],
        sender_patterns=["agenziaentrate", "ader", "riscossione"],
        category="cartelle_esattoriali",
        gestionale_section="Commercialista",
        collection="adr_definizione_agevolata",
        action="save_commercialista",
        priority=20
    ),
    
    # --- DELIBERE FONSI / CASSA INTEGRAZIONE ---
    EmailRule(
        name="delibere_fonsi",
        keywords=["Delibere - Fonsi", "FONSI", "cassa integrazione", "ammortizzatori sociali"],
        subject_patterns=[r"delibere.*fonsi", r"cassa\s*integrazione", r"cig[os]?"],
        sender_patterns=["inps", "pec.inps"],
        category="inps_fonsi",
        gestionale_section="INPS Documenti",
        collection="delibere_fonsi",
        action="extract_cassa_integrazione",
        priority=12
    ),
    
    # --- DILAZIONI INPS ---
    EmailRule(
        name="dilazioni_inps",
        keywords=["dilazione amministrativa", "Sede INPS", "rateizzazione INPS", "5100"],
        subject_patterns=[r"dilazion.*inps", r"sede.*inps.*\d{4}", r"rateizzazione"],
        sender_patterns=["inps", "pec.inps"],
        category="inps_dilazioni",
        gestionale_section="INPS Documenti",
        collection="dilazioni_inps",
        action="save_pdf",
        priority=11
    ),
    
    # --- BONIFICI STIPENDI ---
    # Accetta qualsiasi banca/mittente - match su contenuto
    EmailRule(
        name="bonifici_stipendi",
        keywords=["Info Bonifico", "YouBusiness", "disposizione bonifico", "pagamento stipendio",
                  "bonifico sepa", "esito bonifico", "conferma bonifico", "accredito stipendio"],
        subject_patterns=[r"info\s*bonifico", r"bonifico.*stipend", r"pagamento.*dipendent",
                         r"esito.*bonifico", r"conferma.*bonifico", r"bonifico.*sepa"],
        sender_patterns=[],  # Accetta QUALSIASI mittente
        category="bonifici_stipendi",
        gestionale_section="Prima Nota Salari",
        collection="bonifici_stipendi",
        action="associate_employee",
        priority=8
    ),
    
    # --- F24 ---
    EmailRule(
        name="f24",
        keywords=["F24", "modello F24", "delega F24", "tributi", "versamento unificato"],
        subject_patterns=[r"f24", r"modello\s*f\s*24", r"tribut", r"delega.*f24"],
        sender_patterns=[],  # Accetta QUALSIASI mittente
        category="f24",
        gestionale_section="F24",
        collection="f24",
        action="save_pdf",
        priority=7
    ),
    
    # --- BUSTE PAGA / CEDOLINI ---
    EmailRule(
        name="buste_paga",
        keywords=["busta paga", "cedolino", "LUL", "libro unico lavoro", "prospetto paga"],
        subject_patterns=[r"busta\s*paga", r"cedolino", r"lul", r"prospetto.*paga"],
        sender_patterns=[],  # Accetta QUALSIASI mittente
        category="buste_paga",
        gestionale_section="Cedolini",
        collection="cedolini_pdf",
        action="save_pdf",
        priority=9
    ),
    
    # --- ESTRATTI CONTO ---
    # NOTA: sender_patterns vuoto = accetta qualsiasi mittente
    # Il match avviene su oggetto, corpo email o nome allegato
    EmailRule(
        name="estratti_conto",
        keywords=["estratto conto", "movimenti bancari", "rendiconto", "situazione conto", 
                  "lista movimenti", "saldo conto", "conto corrente", "riepilogo movimenti"],
        subject_patterns=[r"estratto\s*conto", r"movimenti\s*bancar", r"rendiconto", 
                         r"lista\s*movimenti", r"saldo.*conto", r"riepilogo.*conto"],
        sender_patterns=[],  # Accetta QUALSIASI mittente
        category="estratti_conto",
        gestionale_section="Banca",
        collection="estratti_conto_pdf",
        action="parse_and_save",  # Nuova azione: parsa e salva in estratto_conto_movimenti
        priority=6
    ),
    
    # --- FATTURE ELETTRONICHE ---
    EmailRule(
        name="fatture_sdi",
        keywords=["fattura elettronica", "fattura PA", "XML fattura", "SDI", "sistema di interscambio"],
        subject_patterns=[r"fattura.*elettronic", r"sdi", r"fe\s*\d+", r"sistema.*interscambio"],
        sender_patterns=[],  # Accetta QUALSIASI mittente
        category="fatture",
        gestionale_section="Fatture Ricevute",
        collection="invoices",
        action="import_fattura",
        priority=5
    ),
]


def decode_email_subject(subject: str) -> str:
    """Decodifica il subject dell'email."""
    if not subject:
        return ""
    decoded_parts = decode_header(subject)
    result = []
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            result.append(part.decode(encoding or 'utf-8', errors='replace'))
        else:
            result.append(part)
    return ''.join(result)


def extract_codice_fiscale(text: str) -> Optional[str]:
    """Estrae codice fiscale da testo."""
    match = re.search(r'\b([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b', text.upper())
    return match.group(1) if match else None


def extract_data_from_text(text: str, pattern: str) -> Optional[str]:
    """Estrae data da testo usando pattern DD/MM/YYYY o YYYY-MM-DD."""
    match = re.search(pattern, text, re.I)
    return match.group(1) if match else None


def classify_email(subject: str, sender: str, body: str = "", attachment_names: List[str] = None) -> Tuple[Optional[EmailRule], float]:
    """
    Classifica un'email in base alle regole definite.
    Controlla: oggetto, corpo email, nomi allegati.
    NON filtra più per mittente (sender_patterns vuoti = accetta tutti).
    
    Args:
        subject: Oggetto dell'email
        sender: Mittente dell'email
        body: Corpo dell'email
        attachment_names: Lista dei nomi degli allegati
    
    Returns:
        (regola_matchata, confidence_score)
    """
    subject_lower = subject.lower()
    sender_lower = sender.lower()
    body_lower = body.lower() if body else ""
    
    # Combina tutto il testo searchable: oggetto + corpo + nomi allegati
    attachments_text = " ".join([name.lower() for name in (attachment_names or [])])
    full_text = f"{subject_lower} {body_lower} {attachments_text}"
    
    best_match: Optional[EmailRule] = None
    best_score = 0.0
    
    for rule in sorted(EMAIL_RULES, key=lambda r: -r.priority):
        score = 0.0
        
        # Check keywords nel testo completo (oggetto + corpo + allegati)
        keyword_matches = sum(1 for kw in rule.keywords if kw.lower() in full_text)
        if keyword_matches > 0:
            score += 0.4 * (keyword_matches / len(rule.keywords))  # Aumentato da 0.3 a 0.4
        
        # Check subject patterns
        for pattern in rule.subject_patterns:
            if re.search(pattern, subject_lower, re.I):
                score += 0.35
                break
        
        # Check patterns anche nel corpo e allegati
        for pattern in rule.subject_patterns:
            if re.search(pattern, body_lower, re.I) or re.search(pattern, attachments_text, re.I):
                score += 0.15  # Bonus se pattern trovato nel corpo/allegati
                break
        
        # Check sender patterns SOLO se specificati (non vuoti)
        if rule.sender_patterns:
            for pattern in rule.sender_patterns:
                if pattern.lower() in sender_lower:
                    score += 0.1  # Ridotto da 0.3 a 0.1 - non più determinante
                    break
        
        # Apply priority bonus
        score += rule.priority * 0.01
        
        if score > best_score:
            best_score = score
            best_match = rule
    
    # Soglia minima per considerare il match valido (abbassata da 0.25 a 0.20)
    if best_score < 0.20:
        return None, 0.0
    
    return best_match, min(best_score, 1.0)


def get_all_keywords() -> List[str]:
    """Ritorna tutte le parole chiave da tutte le regole."""
    keywords = set()
    for rule in EMAIL_RULES:
        keywords.update(rule.keywords)
    return list(keywords)


def get_categories_mapping() -> Dict[str, Dict[str, Any]]:
    """Ritorna il mapping categorie -> sezioni gestionale."""
    return {
        rule.category: {
            "name": rule.name,
            "gestionale_section": rule.gestionale_section,
            "collection": rule.collection,
            "action": rule.action,
            "keywords": rule.keywords
        }
        for rule in EMAIL_RULES
    }


async def scan_and_classify_emails(
    db,
    cartella: str = "INBOX",
    giorni: int = 30,
    delete_unmatched: bool = False,
    dry_run: bool = True
) -> Dict[str, Any]:
    """
    Scansiona le email, le classifica e le processa.
    
    Args:
        db: Database MongoDB
        cartella: Cartella IMAP da scansionare
        giorni: Numero di giorni da controllare
        delete_unmatched: Se True, elimina email che non matchano nessuna regola
        dry_run: Se True, non esegue modifiche reali
    
    Returns:
        Statistiche e risultati della scansione
    """
    if not EMAIL or not EMAIL_PASSWORD:
        return {"error": "Credenziali email non configurate"}
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cartella": cartella,
        "giorni_scansionati": giorni,
        "dry_run": dry_run,
        "email_totali": 0,
        "email_classificate": 0,
        "email_non_classificate": 0,
        "email_da_eliminare": 0,
        "per_categoria": {},
        "documenti_salvati": 0,
        "associazioni_effettuate": 0,
        "errori": [],
        "dettagli": []
    }
    
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL, EMAIL_PASSWORD)
        mail.select(cartella)
        
        # Calcola data limite
        data_limite = datetime.now() - timedelta(days=giorni)
        date_str = data_limite.strftime("%d-%b-%Y")
        
        # Cerca tutte le email nel periodo
        status, messages = mail.search(None, f'(SINCE {date_str})')
        
        if status != "OK":
            mail.logout()
            return risultati
        
        message_ids = messages[0].split()
        risultati["email_totali"] = len(message_ids)
        
        emails_to_delete = []
        
        for msg_id in message_ids:
            try:
                status, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status != "OK":
                    continue
                
                email_body = msg_data[0][1]
                msg = email.message_from_bytes(email_body)
                
                subject = decode_email_subject(msg.get("Subject", ""))
                sender = msg.get("From", "")
                date_str = msg.get("Date", "")
                
                # Estrai body text e nomi allegati
                body_text = ""
                attachment_names = []
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            payload = part.get_payload(decode=True)
                            if payload:
                                body_text += payload.decode('utf-8', errors='replace')
                        except:
                            pass
                    # Raccogli nomi allegati per il matching
                    filename = part.get_filename()
                    if filename:
                        decoded_filename = decode_email_subject(filename)
                        attachment_names.append(decoded_filename)
                
                # Classifica email (ora include anche i nomi allegati)
                rule, confidence = classify_email(subject, sender, body_text, attachment_names)
                
                email_info = {
                    "msg_id": msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id),
                    "subject": subject[:100],
                    "sender": sender[:50],
                    "date": date_str,
                    "attachments": attachment_names[:5] if attachment_names else [],  # Max 5 allegati mostrati
                    "classified": rule is not None,
                    "category": rule.category if rule else None,
                    "confidence": round(confidence, 2),
                    "gestionale_section": rule.gestionale_section if rule else None,
                    "action": rule.action if rule else None
                }
                
                if rule:
                    risultati["email_classificate"] += 1
                    
                    # Incrementa contatore categoria
                    if rule.category not in risultati["per_categoria"]:
                        risultati["per_categoria"][rule.category] = {
                            "count": 0,
                            "gestionale_section": rule.gestionale_section,
                            "emails": []
                        }
                    risultati["per_categoria"][rule.category]["count"] += 1
                    risultati["per_categoria"][rule.category]["emails"].append({
                        "subject": subject[:60],
                        "confidence": round(confidence, 2)
                    })
                    
                    # Estrai allegati PDF se non dry_run
                    if not dry_run:
                        for part in msg.walk():
                            filename = part.get_filename()
                            if filename and filename.lower().endswith('.pdf'):
                                filename = decode_email_subject(filename)
                                payload = part.get_payload(decode=True)
                                
                                if payload:
                                    # Salva nel database
                                    doc = {
                                        "tipo": rule.category,
                                        "filename": filename,
                                        "subject": subject,
                                        "sender": sender,
                                        "data_email": date_str,
                                        "pdf_base64": base64.b64encode(payload).decode('utf-8'),
                                        "confidence": confidence,
                                        "gestionale_section": rule.gestionale_section,
                                        "processed": False,
                                        "data_inserimento": datetime.now(timezone.utc).isoformat()
                                    }
                                    
                                    # Evita duplicati
                                    existing = await db["documents_classified"].find_one({
                                        "subject": subject,
                                        "filename": filename
                                    })
                                    
                                    if not existing:
                                        await db["documents_classified"].insert_one(doc)
                                        risultati["documenti_salvati"] += 1
                
                else:
                    risultati["email_non_classificate"] += 1
                    if delete_unmatched:
                        emails_to_delete.append(msg_id)
                        email_info["marked_for_deletion"] = True
                
                risultati["dettagli"].append(email_info)
                
            except Exception as e:
                risultati["errori"].append(f"Errore email {msg_id}: {str(e)}")
        
        # Elimina email non classificate se richiesto
        if delete_unmatched and not dry_run and emails_to_delete:
            for msg_id in emails_to_delete:
                try:
                    mail.store(msg_id, '+FLAGS', '\\Deleted')
                except Exception as e:
                    risultati["errori"].append(f"Errore eliminazione {msg_id}: {str(e)}")
            
            mail.expunge()
            risultati["email_da_eliminare"] = len(emails_to_delete)
        elif delete_unmatched and dry_run:
            risultati["email_da_eliminare"] = len(emails_to_delete)
        
        mail.logout()
        
    except Exception as e:
        risultati["errori"].append(f"Errore connessione: {str(e)}")
    
    return risultati


async def process_classified_documents(db) -> Dict[str, Any]:
    """
    Processa i documenti classificati e li associa alle sezioni del gestionale.
    """
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "documenti_processati": 0,
        "associazioni": [],
        "errori": []
    }
    
    # Trova documenti non processati
    cursor = db["documents_classified"].find({"processed": False})
    
    async for doc in cursor:
        try:
            category = doc.get("tipo")
            
            if category == "dimissioni":
                # Estrai codice fiscale e associa a dipendente
                cf = extract_codice_fiscale(doc.get("subject", "") + doc.get("filename", ""))
                if cf:
                    # Trova dipendente
                    dipendente = await db["employees"].find_one({"codice_fiscale": cf.upper()})
                    if dipendente:
                        # Estrai data dimissione se possibile
                        await db["employees"].update_one(
                            {"_id": dipendente["_id"]},
                            {"$set": {
                                "stato": "dimesso",
                                "documento_dimissioni": doc.get("filename"),
                                "data_modifica": datetime.now(timezone.utc).isoformat()
                            }}
                        )
                        risultati["associazioni"].append({
                            "tipo": "dimissioni",
                            "codice_fiscale": cf,
                            "dipendente": f"{dipendente.get('nome', '')} {dipendente.get('cognome', '')}"
                        })
            
            elif category == "cartelle_esattoriali":
                # Salva in ADR per il commercialista
                cf = extract_codice_fiscale(doc.get("subject", "") + doc.get("filename", ""))
                if cf:
                    await db["adr_definizione_agevolata"].update_one(
                        {"codice_fiscale": cf},
                        {
                            "$setOnInsert": {
                                "codice_fiscale": cf,
                                "denominazione": "",
                                "data_inserimento": datetime.now(timezone.utc).isoformat()
                            },
                            "$push": {"pdf_allegati": {
                                "filename": doc.get("filename"),
                                "subject": doc.get("subject"),
                                "data_email": doc.get("data_email")
                            }}
                        },
                        upsert=True
                    )
                    risultati["associazioni"].append({
                        "tipo": "cartella_esattoriale",
                        "codice_fiscale": cf
                    })
            
            # Marca come processato
            await db["documents_classified"].update_one(
                {"_id": doc["_id"]},
                {"$set": {"processed": True, "data_processamento": datetime.now(timezone.utc).isoformat()}}
            )
            risultati["documenti_processati"] += 1
            
        except Exception as e:
            risultati["errori"].append(f"Errore doc {doc.get('_id')}: {str(e)}")
    
    return risultati


async def process_documents_with_ai(
    db,
    process_all: bool = False,
    document_types: List[str] = None,
    save_to_gestionale: bool = True,
    model: str = "claude-sonnet-4-5-20250929"
) -> Dict[str, Any]:
    """
    Processa i documenti classificati usando Document AI per estrarre dati strutturati.
    
    Args:
        db: Database MongoDB
        process_all: Se True, riprocessa anche documenti già processati
        document_types: Lista di tipi da processare (None = tutti)
        save_to_gestionale: Se True, salva i dati estratti nelle collection del gestionale
        model: Modello LLM da usare
    
    Returns:
        Statistiche del processamento
    """
    from app.services.document_ai_extractor import process_document_from_base64
    from app.services.document_data_saver import save_extracted_data_to_gestionale
    
    risultati = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "documenti_analizzati": 0,
        "documenti_estratti": 0,
        "documenti_salvati": 0,
        "documenti_duplicati": 0,
        "errori_estrazione": 0,
        "errori_salvataggio": 0,
        "per_tipo": {},
        "dettagli": [],
        "errori": []
    }
    
    # Query per documenti da processare
    query = {}
    if not process_all:
        query["$or"] = [
            {"ai_processed": {"$ne": True}},
            {"ai_processed": {"$exists": False}}
        ]
    
    if document_types:
        query["tipo"] = {"$in": document_types}
    
    # Processa solo documenti con PDF
    query["pdf_base64"] = {"$exists": True, "$ne": None}
    
    cursor = db["documents_classified"].find(query)
    documents = await cursor.to_list(length=500)  # Max 500 documenti per batch
    
    for doc in documents:
        doc_id = str(doc.get("_id"))
        filename = doc.get("filename", "documento.pdf")
        tipo_email = doc.get("tipo", "generico")
        
        risultati["documenti_analizzati"] += 1
        
        # Inizializza contatore per tipo
        if tipo_email not in risultati["per_tipo"]:
            risultati["per_tipo"][tipo_email] = {"analizzati": 0, "estratti": 0, "salvati": 0, "errori": 0}
        risultati["per_tipo"][tipo_email]["analizzati"] += 1
        
        dettaglio = {
            "doc_id": doc_id,
            "filename": filename,
            "tipo_email": tipo_email,
            "status": "pending"
        }
        
        try:
            # Estrai dati con Document AI
            extraction_result = await process_document_from_base64(
                base64_data=doc["pdf_base64"],
                filename=filename,
                document_type=None,  # Auto-detect
                model=model
            )
            
            if extraction_result.get("structured_data", {}).get("success"):
                risultati["documenti_estratti"] += 1
                risultati["per_tipo"][tipo_email]["estratti"] += 1
                
                extracted_data = extraction_result["structured_data"]
                tipo_documento = extracted_data.get("document_type", "generico")
                dettaglio["tipo_documento_rilevato"] = tipo_documento
                dettaglio["status"] = "extracted"
                
                # Aggiorna documento con dati estratti
                await db["documents_classified"].update_one(
                    {"_id": doc["_id"]},
                    {
                        "$set": {
                            "ai_processed": True,
                            "ai_processed_at": datetime.now(timezone.utc).isoformat(),
                            "ai_model": model,
                            "ai_document_type": tipo_documento,
                            "ai_extracted_data": extracted_data.get("data", {}),
                            "ai_ocr_used": extraction_result.get("ocr_used", False)
                        }
                    }
                )
                
                # Salva nel gestionale se richiesto
                if save_to_gestionale:
                    source_info = {
                        "email_subject": doc.get("subject"),
                        "email_sender": doc.get("sender"),
                        "email_date": doc.get("data_email"),
                        "filename": filename,
                        "documents_classified_id": doc_id
                    }
                    
                    save_result = await save_extracted_data_to_gestionale(
                        db, extracted_data, source_info
                    )
                    
                    dettaglio["save_result"] = save_result
                    
                    if save_result.get("status") == "saved":
                        risultati["documenti_salvati"] += 1
                        risultati["per_tipo"][tipo_email]["salvati"] += 1
                        dettaglio["status"] = "saved"
                        dettaglio["collection"] = save_result.get("collection")
                    elif save_result.get("status") == "duplicate":
                        risultati["documenti_duplicati"] += 1
                        dettaglio["status"] = "duplicate"
                    elif save_result.get("status") == "error":
                        risultati["errori_salvataggio"] += 1
                        dettaglio["status"] = "save_error"
                        dettaglio["error"] = save_result.get("message")
            else:
                risultati["errori_estrazione"] += 1
                risultati["per_tipo"][tipo_email]["errori"] += 1
                dettaglio["status"] = "extraction_error"
                dettaglio["error"] = extraction_result.get("structured_data", {}).get("error", "Unknown error")[:200]
                
                # Marca come tentato ma fallito
                await db["documents_classified"].update_one(
                    {"_id": doc["_id"]},
                    {
                        "$set": {
                            "ai_processed": False,
                            "ai_last_attempt": datetime.now(timezone.utc).isoformat(),
                            "ai_error": dettaglio["error"]
                        }
                    }
                )
        
        except Exception as e:
            risultati["errori_estrazione"] += 1
            risultati["per_tipo"][tipo_email]["errori"] += 1
            dettaglio["status"] = "exception"
            dettaglio["error"] = str(e)[:200]
            risultati["errori"].append(f"Doc {doc_id}: {str(e)[:100]}")
        
        risultati["dettagli"].append(dettaglio)
    
    return risultati
