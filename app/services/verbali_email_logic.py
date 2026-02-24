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

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import re

logger = logging.getLogger(__name__)


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
        self.verbali_senza_quietanza = [v["numero_verbale"] async for v in cursor]
        
        # Verbali senza PDF
        cursor = db["verbali_noleggio"].find(
            {"$or": [
                {"pdf_data": {"$exists": False}},
                {"pdf_data": None},
                {"pdf_data": ""}
            ]},
            {"numero_verbale": 1, "_id": 0}
        )
        self.verbali_senza_pdf = [v["numero_verbale"] async for v in cursor]
        
        # Verbali senza fattura
        cursor = db["verbali_noleggio"].find(
            {"$or": [
                {"fattura_id": {"$exists": False}},
                {"fattura_id": None}
            ]},
            {"numero_verbale": 1, "_id": 0}
        )
        self.verbali_senza_fattura = [v["numero_verbale"] async for v in cursor]
        
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


async def scan_email_con_priorita(db, email_service) -> Dict[str, Any]:
    """
    Scansiona la posta elettronica con la logica di priorità:
    1. PRIMA completa le cose sospese
    2. POI aggiungi nuove cose
    
    Returns:
        Dict con risultati dello scan
    """
    risultato = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fase_1_completamenti": {
            "quietanze_trovate": 0,
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
    
    # ===== FASE 1: COMPLETA LE COSE SOSPESE =====
    logger.info("🔍 FASE 1: Cercando documenti per completare cose sospese...")
    
    # 1a. Cerca quietanze per verbali da pagare
    if pending_manager.verbali_senza_quietanza:
        logger.info(f"   Cercando quietanze per {len(pending_manager.verbali_senza_quietanza)} verbali...")
        for numero_verbale in pending_manager.verbali_senza_quietanza[:50]:  # Max 50 per scan
            try:
                quietanza = await cerca_quietanza_per_verbale(db, email_service, numero_verbale)
                if quietanza:
                    risultato["fase_1_completamenti"]["quietanze_trovate"] += 1
                    pending_manager.remove_from_pending(numero_verbale, "quietanza")
            except Exception as e:
                risultato["errori"].append(f"Quietanza {numero_verbale}: {str(e)}")
    
    # 1b. Cerca PDF per verbali senza allegato
    if pending_manager.verbali_senza_pdf:
        logger.info(f"   Cercando PDF per {len(pending_manager.verbali_senza_pdf)} verbali...")
        for numero_verbale in pending_manager.verbali_senza_pdf[:50]:
            try:
                pdf = await cerca_pdf_per_verbale(db, email_service, numero_verbale)
                if pdf:
                    risultato["fase_1_completamenti"]["pdf_trovati"] += 1
                    pending_manager.remove_from_pending(numero_verbale, "pdf")
            except Exception as e:
                risultato["errori"].append(f"PDF {numero_verbale}: {str(e)}")
    
    # ===== FASE 2: AGGIUNGI NUOVE COSE =====
    logger.info("🔍 FASE 2: Cercando nuovi elementi...")
    
    # 2a. Cerca nuovi verbali
    try:
        nuovi_verbali = await cerca_nuovi_verbali(db, email_service)
        risultato["fase_2_nuovi"]["verbali_nuovi"] = len(nuovi_verbali)
    except Exception as e:
        risultato["errori"].append(f"Nuovi verbali: {str(e)}")
    
    # 2b. Cerca nuove quietanze (che potrebbero associarsi a verbali esistenti)
    try:
        nuove_quietanze = await cerca_nuove_quietanze(db, email_service)
        risultato["fase_2_nuovi"]["quietanze_nuove"] = len(nuove_quietanze)
    except Exception as e:
        risultato["errori"].append(f"Nuove quietanze: {str(e)}")
    
    logger.info(f"✅ Scan completato: {risultato}")
    return risultato


async def cerca_quietanza_per_verbale(db, email_service, numero_verbale: str) -> Optional[Dict]:
    """
    Cerca specificamente una quietanza per un verbale.
    Pattern di ricerca: numero verbale nell'oggetto o corpo email.
    """
    # Implementazione dipende dal servizio email usato (Aruba, Gmail, etc.)
    # Questa è la struttura base
    
    search_patterns = [
        f"quietanza {numero_verbale}",
        f"pagamento {numero_verbale}",
        f"ricevuta {numero_verbale}",
        numero_verbale  # Cerca anche solo il numero
    ]
    
    # TODO: Implementare ricerca effettiva con email_service
    # Per ora ritorna None - da implementare con integrazione email
    
    return None


async def cerca_pdf_per_verbale(db, email_service, numero_verbale: str) -> Optional[bytes]:
    """
    Cerca il PDF allegato di un verbale specifico.
    """
    # TODO: Implementare ricerca effettiva
    return None


async def cerca_nuovi_verbali(db, email_service) -> List[Dict]:
    """
    Cerca nuovi verbali nelle email non ancora processate.
    """
    # TODO: Implementare ricerca effettiva
    return []


async def cerca_nuove_quietanze(db, email_service) -> List[Dict]:
    """
    Cerca nuove quietanze e prova ad associarle a verbali esistenti.
    """
    # TODO: Implementare ricerca effettiva
    return []


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
