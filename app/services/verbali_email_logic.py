"""
LOGICA AUTOMAZIONE VERBALI - DOCUMENTAZIONE

================================================================================
PRINCIPIO FONDAMENTALE: PRIMA COMPLETA, POI AGGIUNGI
================================================================================

Ogni volta che il sistema scansiona la posta elettronica, DEVE seguire questa
sequenza di priorità:

1. FASE 1 - COMPLETARE LE COSE SOSPESE (PRIORITÀ ALTA)
   ----------------------------------------------------
   Prima di cercare nuovi elementi, il sistema deve cercare documenti per
   completare i record esistenti che sono incompleti:

   a) Verbali "DA PAGARE" → Cerca quietanza (PayPal, bonifico, ricevuta)
   b) Verbali senza PDF → Cerca il PDF del verbale
   c) Verbali "IDENTIFICATO" → Cerca la fattura di ri-notifica
   d) Quietanze orfane → Cerca il verbale corrispondente

2. FASE 2 - AGGIUNGERE NUOVI ELEMENTI (PRIORITÀ NORMALE)
   ------------------------------------------------------
   Solo dopo aver cercato di completare le cose sospese:

   a) Cerca nuovi verbali nelle email
   b) Cerca nuove quietanze
   c) Cerca nuove fatture da noleggiatori


================================================================================
STATI DEI VERBALI
================================================================================

DA_SCARICARE    → Email trovata, PDF non ancora scaricato
SALVATO         → PDF scaricato, in attesa di identificazione
IDENTIFICATO    → Targa e/o driver trovati, in attesa di fattura
FATTURA_RICEVUTA → Fattura ri-notifica ricevuta, in attesa di pagamento
DA_PAGARE       → Verbale completo, manca quietanza pagamento
PAGATO          → Quietanza trovata, pagamento confermato
RICONCILIATO    → Fattura + Quietanza + Driver tutti collegati


================================================================================
COSA TENERE IN MEMORIA (SOSPESI DA COMPLETARE)
================================================================================

Il sistema deve mantenere una lista di:

1. verbali_senza_quietanza[]   → Cercherà quietanze con questi numeri
2. verbali_senza_pdf[]         → Cercherà PDF con questi numeri
3. verbali_senza_fattura[]     → Cercherà fatture con questi numeri/targhe
4. quietanze_orfane[]          → Quietanze trovate ma senza verbale associato
5. fatture_orfane[]            → Fatture con verbali non ancora in sistema


================================================================================
PATTERN RICERCA EMAIL
================================================================================

VERBALE:
- Subject contiene: "verbale", "multa", "contravvenzione", "notifica"
- Allegato PDF con nome tipo: "verbale_*.pdf", "notifica_*.pdf"
- Nel corpo: numero verbale (pattern: [A-Z]\\d{10,12})

QUIETANZA PAGAMENTO:
- Subject contiene: "quietanza", "pagamento", "ricevuta", "PayPal", "bonifico"
- Allegato PDF con nome tipo: "quietanza_*.pdf", "ricevuta_*.pdf"
- Nel corpo: riferimento a numero verbale

FATTURA NOLEGGIATORE:
- Mittente: ALD, Leasys, Arval, Alphabet, etc.
- Allegato XML fattura elettronica
- Nel corpo/oggetto: "ri-notifica", "rinotifica", "addebito verbale"


================================================================================
ASSOCIAZIONE VERBALE → DIPENDENTE
================================================================================

Quando trovo un verbale:
1. Estraggo la TARGA dal verbale
2. Cerco il VEICOLO con quella targa in veicoli_noleggio
3. Dal veicolo trovo il DRIVER associato
4. Creo il record in verbali_noleggio con tutti i collegamenti
5. Creo la voce costo in costi_dipendenti per addebitare al driver


================================================================================
VISUALIZZAZIONE FRONTEND
================================================================================

Nella sezione VERBALI del dipendente:
- Lista verbali associati a quel driver
- Per ogni verbale: [Vedi PDF] [Stato] [Importo] [Data]
- Filtri: Da pagare | Pagati | Tutti
- Totale verbali da pagare


================================================================================
STORICO EMAIL
================================================================================

- Scansionare email dal 2018 in poi
- Mantenere traccia dell'ultima email processata per non riprocessare
- Processare in ordine cronologico (dal più vecchio al più recente)
- Loggare ogni operazione per audit trail


================================================================================
ESEMPIO FLUSSO COMPLETO
================================================================================

Giorno 1:
- Arriva email con verbale T26020100001 per targa GE911SC
- Sistema: Crea verbale, associa a CERALDI VALERIO, stato "DA_PAGARE"
- Aggiunge T26020100001 a verbali_senza_quietanza[]

Giorno 2:
- Sistema scansiona email
- FASE 1: Cerca quietanza per T26020100001 → Non trovata
- FASE 2: Trova nuovo verbale T26020100002 → Aggiunge con stato "DA_PAGARE"

Giorno 3:
- Sistema scansiona email
- FASE 1: Cerca quietanza per T26020100001 → TROVATA!
- Sistema: Aggiorna verbale T26020100001 stato "PAGATO", allega quietanza
- FASE 2: Nessun nuovo verbale

"""

import base64
import logging
import os
import re
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from app.services.verbali_pagamento_finder import (
    trova_pagamento_verbale,
    applica_pagamento_a_verbale,
)
from app.services.verbali_gmail_scanner import scan_gmail_verbali
from app.services.verbali_email_scanner import (
    VerbaliEmailScanner,
    decode_mime_header,
)

logger = logging.getLogger(__name__)

# Limite operativo per singolo scan: stesso valore già in produzione nello
# scanner storico (VerbaliEmailScanner.scan_completo_priorita usa 30).
MAX_COMPLETAMENTI_PER_SCAN = 30


class VerbaliPendingManager:
    """
    Gestisce la lista delle cose sospese da completare.
    
    Mantiene in memoria:
    - Verbali senza quietanza
    - Verbali senza PDF
    - Quietanze orfane
    """
    
    def __init__(self):
        self.verbali_senza_quietanza: List[str] = []
        self.verbali_senza_pdf: List[str] = []
        self.verbali_senza_fattura: List[str] = []
        self.quietanze_orfane: List[Dict] = []
        self.last_sync: Optional[datetime] = None
    
    async def load_pending_from_db(self, db) -> Dict[str, int]:
        """
        Carica le cose sospese dal database.
        Chiamato all'avvio e prima di ogni scan email.
        """
        # Verbali da pagare (senza quietanza)
        cursor = db["verbali_noleggio"].find(
            {"stato": {"$in": ["da_pagare", "DA_PAGARE", "identificato", "IDENTIFICATO", "fattura_ricevuta"]}},
            {"numero_verbale": 1, "_id": 0}
        )
        self.verbali_senza_quietanza = [
            v["numero_verbale"] async for v in cursor if v.get("numero_verbale")
        ]

        # Verbali senza PDF
        cursor = db["verbali_noleggio"].find(
            {"$or": [
                {"pdf_data": {"$exists": False}},
                {"pdf_data": None},
                {"pdf_data": ""}
            ]},
            {"numero_verbale": 1, "_id": 0}
        )
        self.verbali_senza_pdf = [
            v["numero_verbale"] async for v in cursor if v.get("numero_verbale")
        ]

        # Verbali senza fattura
        cursor = db["verbali_noleggio"].find(
            {"$or": [
                {"fattura_id": {"$exists": False}},
                {"fattura_id": None}
            ]},
            {"numero_verbale": 1, "_id": 0}
        )
        self.verbali_senza_fattura = [
            v["numero_verbale"] async for v in cursor if v.get("numero_verbale")
        ]
        
        self.last_sync = datetime.now(timezone.utc)
        
        return {
            "senza_quietanza": len(self.verbali_senza_quietanza),
            "senza_pdf": len(self.verbali_senza_pdf),
            "senza_fattura": len(self.verbali_senza_fattura),
            "quietanze_orfane": len(self.quietanze_orfane)
        }
    
    def is_verbale_pending(self, numero_verbale: str) -> Dict[str, bool]:
        """Verifica se un verbale ha cose da completare."""
        return {
            "needs_quietanza": numero_verbale in self.verbali_senza_quietanza,
            "needs_pdf": numero_verbale in self.verbali_senza_pdf,
            "needs_fattura": numero_verbale in self.verbali_senza_fattura
        }
    
    def add_quietanza_orfana(self, quietanza_data: Dict):
        """Aggiunge una quietanza trovata ma non ancora associata."""
        self.quietanze_orfane.append(quietanza_data)
    
    def remove_from_pending(self, numero_verbale: str, tipo: str):
        """Rimuove un verbale dalla lista pending quando viene completato."""
        if tipo == "quietanza" and numero_verbale in self.verbali_senza_quietanza:
            self.verbali_senza_quietanza.remove(numero_verbale)
        elif tipo == "pdf" and numero_verbale in self.verbali_senza_pdf:
            self.verbali_senza_pdf.remove(numero_verbale)
        elif tipo == "fattura" and numero_verbale in self.verbali_senza_fattura:
            self.verbali_senza_fattura.remove(numero_verbale)


# Istanza globale del manager
pending_manager = VerbaliPendingManager()


def _crea_scanner_connesso(db) -> Optional[VerbaliEmailScanner]:
    """Crea e connette lo scanner IMAP condiviso per l'intero scan.

    Se le credenziali mancano o la connessione fallisce ritorna None: le
    ricerche che non richiedono IMAP diretto (PayPal, estratto conto,
    scanner Gmail strutturato) funzionano comunque.
    """
    try:
        scanner = VerbaliEmailScanner(db)
        if scanner.connect():
            return scanner
    except Exception as e:
        logger.warning(f"Scanner IMAP non disponibile: {e}")
    return None


async def _trova_doc_verbale(db, numero_verbale: str) -> Optional[Dict]:
    return await db["verbali_noleggio"].find_one(
        {"$or": [{"numero_verbale": numero_verbale}, {"id": numero_verbale}]}
    )


_STATI_GIA_PAGATI = {"pagato", "PAGATO", "riconciliato", "pagato_attesa_quietanza", "pagato_attesa_fattura"}


async def scan_email_con_priorita(db, email_service=None, days_back: int = 30) -> Dict[str, Any]:
    """
    Scansiona la posta elettronica con la logica di priorità:
    1. PRIMA completa le cose sospese
    2. POI aggiungi nuove cose

    email_service: un VerbaliEmailScanner già connesso (opzionale). Se None
    viene creato e chiuso internamente.

    Returns:
        Dict con risultati dello scan
    """
    risultato = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fase_1_completamenti": {
            "quietanze_cercate": 0,
            "quietanze_trovate": 0,
            "pdf_cercati": 0,
            "pdf_trovati": 0,
            "fatture_associate": 0
        },
        "fase_2_nuovi": {
            "verbali_nuovi": 0,
            "quietanze_nuove": 0,
            "fatture_nuove": 0
        },
        "errori": []
    }

    # Carica stato pending attuale
    pending = await pending_manager.load_pending_from_db(db)
    logger.info(f"📋 Cose sospese da completare: {pending}")

    scanner = email_service
    scanner_creato = False
    if scanner is None:
        scanner = _crea_scanner_connesso(db)
        scanner_creato = scanner is not None
    risultato["imap_disponibile"] = scanner is not None

    try:
        # ===== FASE 1: COMPLETA LE COSE SOSPESE =====
        logger.info("🔍 FASE 1: Cercando documenti per completare cose sospese...")

        # 1a. Cerca quietanze per verbali da pagare
        if pending_manager.verbali_senza_quietanza:
            logger.info(f"   Cercando quietanze per {len(pending_manager.verbali_senza_quietanza)} verbali...")
            for numero_verbale in pending_manager.verbali_senza_quietanza[:MAX_COMPLETAMENTI_PER_SCAN]:
                risultato["fase_1_completamenti"]["quietanze_cercate"] += 1
                try:
                    quietanza = await cerca_quietanza_per_verbale(db, scanner, numero_verbale)
                    if quietanza:
                        risultato["fase_1_completamenti"]["quietanze_trovate"] += 1
                        pending_manager.remove_from_pending(numero_verbale, "quietanza")
                except Exception as e:
                    risultato["errori"].append(f"Quietanza {numero_verbale}: {str(e)}")

        # 1b. Cerca PDF per verbali senza allegato
        if pending_manager.verbali_senza_pdf:
            logger.info(f"   Cercando PDF per {len(pending_manager.verbali_senza_pdf)} verbali...")
            for numero_verbale in pending_manager.verbali_senza_pdf[:MAX_COMPLETAMENTI_PER_SCAN]:
                risultato["fase_1_completamenti"]["pdf_cercati"] += 1
                try:
                    pdf = await cerca_pdf_per_verbale(db, scanner, numero_verbale)
                    if pdf:
                        risultato["fase_1_completamenti"]["pdf_trovati"] += 1
                        pending_manager.remove_from_pending(numero_verbale, "pdf")
                except Exception as e:
                    risultato["errori"].append(f"PDF {numero_verbale}: {str(e)}")

        # ===== FASE 2: AGGIUNGI NUOVE COSE =====
        logger.info("🔍 FASE 2: Cercando nuovi elementi...")

        # 2a. Cerca nuovi verbali
        try:
            nuovi_verbali = await cerca_nuovi_verbali(db, scanner, days_back=days_back)
            risultato["fase_2_nuovi"]["verbali_nuovi"] = len(nuovi_verbali)
        except Exception as e:
            risultato["errori"].append(f"Nuovi verbali: {str(e)}")

        # 2b. Cerca nuove quietanze (che potrebbero associarsi a verbali esistenti)
        try:
            nuove_quietanze = await cerca_nuove_quietanze(db, scanner, days_back=days_back)
            risultato["fase_2_nuovi"]["quietanze_nuove"] = len(nuove_quietanze)
        except Exception as e:
            risultato["errori"].append(f"Nuove quietanze: {str(e)}")
    finally:
        if scanner_creato:
            scanner.disconnect()

    logger.info(f"✅ Scan completato: {risultato}")
    return risultato


async def cerca_quietanza_per_verbale(db, email_service, numero_verbale: str) -> Optional[Dict]:
    """
    Cerca la quietanza di pagamento di un verbale.

    Ordine delle fonti (dalla più strutturata alla più generica):
    1. `trova_pagamento_verbale` — PayPal transactions (IUV/targa/importo),
       ricevute PagoPA su Gmail, SDD PayPal in estratto conto. Se trova il
       pagamento lo APPLICA al verbale (stato → pagato) con
       `applica_pagamento_a_verbale`.
    2. Fallback IMAP generico: ricerca testuale del numero verbale nella
       cartella dedicata/INBOX tramite lo scanner (se connesso), che registra
       la quietanza con `registra_quietanza`.
    """
    verbale = await _trova_doc_verbale(db, numero_verbale)
    if not verbale:
        return None
    if verbale.get("quietanza_ricevuta") or verbale.get("stato") in _STATI_GIA_PAGATI:
        return None

    match = await trova_pagamento_verbale(db, verbale)
    if match:
        await applica_pagamento_a_verbale(
            db, verbale.get("id") or numero_verbale, match
        )
        logger.info(
            f"✅ Quietanza per {numero_verbale} da fonte {match.get('fonte')}"
        )
        return match

    if email_service is not None and hasattr(email_service, "cerca_quietanza_per_verbale"):
        try:
            trovata = await email_service.cerca_quietanza_per_verbale(numero_verbale)
            if trovata:
                return {"fonte": "imap", "numero_verbale": numero_verbale}
        except Exception as e:
            logger.warning(f"Fallback IMAP quietanza {numero_verbale}: {e}")

    return None


def _scegli_allegato_pdf(allegati: List[Dict], numero_verbale: str) -> Optional[Dict]:
    """Sceglie l'allegato più pertinente tra quelli già scaricati su disco."""
    pdf = [a for a in (allegati or [])
           if str(a.get("filename", "")).lower().endswith(".pdf") and a.get("path")]
    if not pdf:
        return None
    chiavi = (numero_verbale.lower(), "verbale", "avviso")
    for a in pdf:
        nome = str(a.get("filename", "")).lower()
        if any(k in nome for k in chiavi):
            return a
    return pdf[0]


async def cerca_pdf_per_verbale(db, email_service, numero_verbale: str) -> Optional[bytes]:
    """
    Cerca il PDF di un verbale e lo salva in `pdf_data` (base64) sul documento.

    1. Allegati già scaricati su disco dallo scanner Gmail (campo `allegati`).
    2. Fallback: ricerca IMAP del numero verbale tramite lo scanner connesso
       (che salva da sé `pdf_data`).
    """
    verbale = await _trova_doc_verbale(db, numero_verbale)
    if not verbale or verbale.get("pdf_data"):
        return None

    allegato = _scegli_allegato_pdf(verbale.get("allegati"), numero_verbale)
    if allegato and os.path.exists(allegato["path"]):
        try:
            with open(allegato["path"], "rb") as f:
                contenuto = f.read()
            if contenuto:
                await db["verbali_noleggio"].update_one(
                    {"$or": [{"numero_verbale": numero_verbale}, {"id": numero_verbale}]},
                    {"$set": {
                        "pdf_data": base64.b64encode(contenuto).decode("utf-8"),
                        "pdf_filename": allegato.get("filename"),
                        "pdf_fonte": "allegato_gmail_scanner",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }}
                )
                logger.info(f"📄 PDF per {numero_verbale} da allegato locale")
                return contenuto
        except Exception as e:
            logger.warning(f"Lettura allegato {numero_verbale}: {e}")

    if email_service is not None and hasattr(email_service, "cerca_pdf_per_verbale"):
        try:
            trovato = await email_service.cerca_pdf_per_verbale(numero_verbale)
            if trovato:
                doc = await _trova_doc_verbale(db, numero_verbale)
                if doc and doc.get("pdf_data"):
                    return base64.b64decode(doc["pdf_data"])
        except Exception as e:
            logger.warning(f"Fallback IMAP PDF {numero_verbale}: {e}")

    return None


async def cerca_nuovi_verbali(db, email_service, days_back: int = 30) -> List[Dict]:
    """
    Cerca nuovi verbali nelle email non ancora processate.

    1. Scanner Gmail strutturato (mittenti attendibili `verbale_cds`):
       crea/aggiorna `verbali_noleggio` con upsert idempotente.
    2. Se lo scanner IMAP è connesso: cartelle dedicate ai verbali
       (nome = numero verbale) + sweep delle cartelle standard.
    """
    nuovi: List[Dict] = []

    stats = await scan_gmail_verbali(db, days_back=days_back)
    nuovi.extend(
        {"fonte": "verbali_gmail_scanner"}
        for _ in range(int(stats.get("verbali_nuovi", 0) or 0))
    )

    if email_service is not None and hasattr(email_service, "scan_cartelle_verbali"):
        try:
            nuovi.extend(await email_service.scan_cartelle_verbali())
        except Exception as e:
            logger.warning(f"Scan cartelle verbali: {e}")
        try:
            nuovi.extend(await email_service.scan_nuovi_verbali(days_back=days_back))
        except Exception as e:
            logger.warning(f"Scan nuovi verbali INBOX: {e}")

    return nuovi


async def cerca_nuove_quietanze(db, email_service, days_back: int = 30) -> List[Dict]:
    """
    Cerca nuove quietanze nelle email recenti e prova ad associarle a
    verbali esistenti; quelle senza verbale finiscono tra le orfane del
    pending manager.

    Richiede lo scanner IMAP connesso (pattern documentati in testa al file:
    subject "quietanza"/"pagamento"/"ricevuta", numero verbale nel testo).
    """
    if email_service is None or getattr(email_service, "connection", None) is None:
        return []

    import email as email_lib
    from app.services._email_utils import extract_best_body

    conn = email_service.connection
    trovate: List[Dict] = []
    visti: set = set()
    since = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")

    try:
        conn.select("INBOX")
    except Exception as e:
        logger.warning(f"Select INBOX quietanze: {e}")
        return []

    # Parole chiave documentate nel pattern QUIETANZA PAGAMENTO (testa file)
    for kw in ("quietanza", "pagamento eseguito", "ricevuta", "partenopay"):
        try:
            status, messages = conn.search(None, f'(SINCE "{since}" SUBJECT "{kw}")')
        except Exception as e:
            logger.warning(f"Search quietanze '{kw}': {e}")
            continue
        if status != "OK" or not messages or not messages[0]:
            continue
        for email_id in messages[0].split()[-MAX_COMPLETAMENTI_PER_SCAN:]:
            if email_id in visti:
                continue
            visti.add(email_id)
            try:
                status, msg_data = conn.fetch(email_id, "(RFC822)")
                if status != "OK":
                    continue
                msg = email_lib.message_from_bytes(msg_data[0][1])
                subject = decode_mime_header(msg.get("Subject", ""))
                body = extract_best_body(msg)
                if not is_email_quietanza(subject, body):
                    continue
                numero = extract_numero_verbale(f"{subject} {body}")
                if not numero:
                    continue
                verbale = await _trova_doc_verbale(db, numero)
                if verbale is None:
                    orfana = {
                        "numero_verbale": numero,
                        "email_subject": subject,
                        "email_date": msg.get("Date", ""),
                    }
                    pending_manager.add_quietanza_orfana(orfana)
                    trovate.append({**orfana, "associata": False})
                    continue
                if verbale.get("quietanza_ricevuta") or verbale.get("stato") in _STATI_GIA_PAGATI:
                    continue
                await email_service.registra_quietanza(numero, {
                    "email_subject": subject,
                    "email_date": msg.get("Date", ""),
                    "metodo": email_service._detect_payment_method(subject, body),
                })
                trovate.append({"numero_verbale": numero, "associata": True})
            except Exception as e:
                logger.warning(f"Quietanza email {email_id}: {e}")
                continue

    return trovate


def extract_numero_verbale(text: str) -> Optional[str]:
    """Estrae il numero verbale dal testo."""
    if not text:
        return None
    
    patterns = [
        r'([ABCDEFGHIJKLMNOPQRSTUVWXYZ]\d{10,12})',
        r'Verbale\s*(?:Nr|N\.?)?\s*[:\s]*(\w+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    
    return None


def is_email_quietanza(subject: str, body: str) -> bool:
    """Verifica se un'email contiene una quietanza di pagamento."""
    keywords = ["quietanza", "pagamento", "ricevuta", "paypal", "bonifico", "pagato"]
    text = f"{subject} {body}".lower()
    return any(kw in text for kw in keywords)


def is_email_verbale(subject: str, body: str) -> bool:
    """Verifica se un'email contiene un verbale."""
    keywords = ["verbale", "multa", "contravvenzione", "notifica", "infrazione"]
    text = f"{subject} {body}".lower()
    return any(kw in text for kw in keywords)
