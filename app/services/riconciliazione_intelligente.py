"""
RICONCILIAZIONE INTELLIGENTE
=============================

Sistema completo per gestione conferma pagamenti e riconciliazione automatica.

FLUSSO:
1. Import XML → Fattura in stato "in_attesa_conferma" (NON scrive in Prima Nota)
2. Utente conferma metodo (Cassa/Banca) → Solo allora scrive in Prima Nota
3. Sistema verifica con estratto conto → Propone correzioni se necessario
4. Genera automaticamente scrittura contabile in partita doppia

STATI FATTURA:
- in_attesa_conferma: Importata, attende scelta Cassa/Banca
- confermata_cassa: Confermata cassa, in verifica con estratto
- confermata_banca: Confermata banca, in attesa riconciliazione
- sospesa_attesa_estratto: Estratto conto non copre la data fattura
- da_verificare_spostamento: Trovato in estratto ma era cassa - propone spostamento
- da_verificare_match_incerto: Match parziale (importo/causale diversi)
- anomalia_non_in_estratto: Banca confermata ma non trovata in estratto
- riconciliata: Tutto ok, operazione chiusa
- lock_manuale: Bloccata dall'utente, no auto-verifica

Autore: Sistema Gestionale
Data: 22 Gennaio 2026
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
import logging
import uuid
import re

# Fuzzy matching
try:
    from rapidfuzz import fuzz
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False

# Import motore contabile per scritture partita doppia
try:
    from app.services.accounting_engine import get_accounting_engine_persistent
    ACCOUNTING_ENGINE_AVAILABLE = True
except ImportError:
    ACCOUNTING_ENGINE_AVAILABLE = False

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS E COSTANTI
# =============================================================================

class StatoRiconciliazione(Enum):
    """Stati possibili per la riconciliazione fattura"""
    IN_ATTESA_CONFERMA = "in_attesa_conferma"
    CONFERMATA_CASSA = "confermata_cassa"
    CONFERMATA_BANCA = "confermata_banca"
    SOSPESA_ATTESA_ESTRATTO = "sospesa_attesa_estratto"
    DA_VERIFICARE_SPOSTAMENTO = "da_verificare_spostamento"
    DA_VERIFICARE_MATCH_INCERTO = "da_verificare_match_incerto"
    ANOMALIA_NON_IN_ESTRATTO = "anomalia_non_in_estratto"
    RICONCILIATA = "riconciliata"
    LOCK_MANUALE = "lock_manuale"
    # Nuovi stati per casi estesi (Fase 2)
    PARZIALMENTE_PAGATA = "parzialmente_pagata"
    PAGAMENTO_CUMULATIVO = "pagamento_cumulativo"
    CON_NOTA_CREDITO = "con_nota_credito"
    SCONTO_APPLICATO = "sconto_applicato"
    # Nuovi stati per casi estesi (Fase 3)
    ASSEGNI_MULTIPLI = "assegni_multipli"          # Caso 36: Pagamento con più assegni
    ARROTONDAMENTO_APPLICATO = "arrotondamento"    # Caso 37: Riconciliato con arrotondamento
    PAGAMENTO_ANTICIPATO = "pagamento_anticipato"  # Caso 38: Pagamento prima della fattura
    IN_ATTESA_FATTURA = "in_attesa_fattura"        # Pagamento anticipato in attesa di fattura


class TipoMatch(Enum):
    """Tipi di match trovati"""
    ESATTO = "esatto"                    # Importo e riferimenti identici
    PARZIALE_IMPORTO = "parziale_importo"  # Importo diverso di pochi euro
    PARZIALE_CAUSALE = "parziale_causale"  # Causale non corrisponde
    SOLO_IMPORTO = "solo_importo"          # Solo importo uguale
    FUZZY_FORNITORE = "fuzzy_fornitore"    # Fornitore simile
    NESSUNO = "nessuno"


class ConfidenzaMatch(Enum):
    """Livello di confidenza del match"""
    ALTA = "alta"       # Auto-riconcilia
    MEDIA = "media"     # Proponi, attendi conferma
    BASSA = "bassa"     # Suggerisci
    NESSUNA = "nessuna"


# Tolleranze per matching
TOLLERANZA_IMPORTO_ESATTO = 0.01      # €0.01 per match esatto
TOLLERANZA_IMPORTO_PARZIALE = 5.00    # €5.00 per match parziale
TOLLERANZA_PERCENTUALE = 0.01          # 1% per match percentuale
TOLLERANZA_GIORNI_RICERCA = 120        # Cerca movimenti fino a 120 giorni prima

# Tolleranze per arrotondamenti (Caso 37)
TOLLERANZA_ARROTONDAMENTO_DEFAULT = 1.00  # €1.00 tolleranza arrotondamento default
TOLLERANZA_ARROTONDAMENTO_MAX = 5.00      # €5.00 tolleranza arrotondamento massima


# =============================================================================
# CLASSE PRINCIPALE: RiconciliazioneIntelligente
# =============================================================================

class RiconciliazioneIntelligente:
    """
    Gestisce la logica completa di riconciliazione intelligente.
    """
    
    def __init__(self, db):
        """
        Inizializza il servizio.
        
        Args:
            db: Connessione database MongoDB
        """
        self.db = db
    
    # =========================================================================
    # VERIFICA COPERTURA ESTRATTO CONTO
    # =========================================================================
    
    async def get_ultima_data_estratto(self) -> Optional[str]:
        """
        Recupera la data dell'ultimo movimento in estratto conto.
        
        Returns:
            Data in formato YYYY-MM-DD o None se estratto vuoto
        """
        ultimo_movimento = await self.db["estratto_conto_movimenti"].find_one(
            {},
            {"_id": 0, "data": 1},
            sort=[("data", -1)]
        )
        
        if ultimo_movimento:
            return ultimo_movimento.get("data", "")[:10]
        return None
    
    async def verifica_copertura_estratto(self, data_fattura: str) -> Tuple[bool, str]:
        """
        Verifica se l'estratto conto copre la data della fattura.
        
        Args:
            data_fattura: Data fattura in formato YYYY-MM-DD o DD/MM/YYYY
            
        Returns:
            Tuple (coperto, ultima_data_estratto)
        """
        # Normalizza data fattura
        try:
            if "/" in data_fattura:
                parts = data_fattura.split("/")
                if len(parts[0]) == 4:
                    data_fattura_norm = data_fattura.replace("/", "-")
                else:
                    data_fattura_norm = f"{parts[2]}-{parts[1]}-{parts[0]}"
            else:
                data_fattura_norm = data_fattura[:10]
            
            data_fatt = datetime.strptime(data_fattura_norm, "%Y-%m-%d")
        except (ValueError, TypeError, IndexError):
            return False, ""
        
        ultima_data = await self.get_ultima_data_estratto()
        
        if not ultima_data:
            return False, ""
        
        try:
            data_estratto = datetime.strptime(ultima_data, "%Y-%m-%d")
            # L'estratto copre se la sua ultima data >= data fattura
            coperto = data_estratto >= data_fatt
            return coperto, ultima_data
        except (ValueError, TypeError):
            return False, ultima_data
    
    # =========================================================================
    # MATCHING INTELLIGENTE
    # =========================================================================
    
    async def cerca_match_in_estratto(
        self, 
        importo: float, 
        data_fattura: str,
        numero_fattura: str,
        fornitore_nome: str,
        fornitore_piva: str = ""
    ) -> Dict[str, Any]:
        """
        Cerca corrispondenza in estratto conto con algoritmo multi-livello.
        
        Args:
            importo: Importo fattura
            data_fattura: Data fattura
            numero_fattura: Numero documento
            fornitore_nome: Ragione sociale fornitore
            fornitore_piva: Partita IVA fornitore (opzionale)
            
        Returns:
            Dict con match trovato e metadati
        """
        risultato = {
            "trovato": False,
            "tipo_match": TipoMatch.NESSUNO.value,
            "confidenza": ConfidenzaMatch.NESSUNA.value,
            "movimento_id": None,
            "movimento_data": None,
            "movimento_importo": None,
            "movimento_descrizione": None,
            "differenza_importo": None,
            "note": None,
            "suggerimenti": []
        }
        
        if importo <= 0:
            return risultato
        
        importo_abs = abs(importo)
        
        # Normalizza data
        try:
            if "/" in data_fattura:
                parts = data_fattura.split("/")
                if len(parts[0]) == 4:
                    data_fattura_norm = data_fattura.replace("/", "-")
                else:
                    data_fattura_norm = f"{parts[2]}-{parts[1]}-{parts[0]}"
            else:
                data_fattura_norm = data_fattura[:10]
            
            data_fatt = datetime.strptime(data_fattura_norm, "%Y-%m-%d")
            data_min = (data_fatt - timedelta(days=TOLLERANZA_GIORNI_RICERCA)).strftime("%Y-%m-%d")
            data_max = (data_fatt + timedelta(days=60)).strftime("%Y-%m-%d")
        except (ValueError, TypeError, IndexError):
            return risultato
        
        # Prepara keywords fornitore
        parole_comuni = {"srl", "spa", "snc", "sas", "sapa", "srls", "ltd", "gmbh", 
                        "s.r.l.", "s.p.a.", "di", "e", "del", "della", "dei", 
                        "gruppo", "group", "italia", "italy", "europe"}
        fornitore_lower = fornitore_nome.lower() if fornitore_nome else ""
        parole_fornitore = [p for p in fornitore_lower.split() 
                          if len(p) >= 3 and p not in parole_comuni]
        
        # =====================================================================
        # LIVELLO 1: MATCH ESATTO (importo identico ±€0.01)
        # =====================================================================
        query_esatto = {
            "tipo": {"$in": ["uscita", "addebito", "pagamento"]},
            "$or": [
                {"importo": {"$gte": importo_abs - TOLLERANZA_IMPORTO_ESATTO, 
                            "$lte": importo_abs + TOLLERANZA_IMPORTO_ESATTO}},
                {"importo": {"$gte": -importo_abs - TOLLERANZA_IMPORTO_ESATTO, 
                            "$lte": -importo_abs + TOLLERANZA_IMPORTO_ESATTO}}
            ],
            "data": {"$gte": data_min, "$lte": data_max},
            "fattura_id": {"$exists": False}
        }
        
        movimenti_esatti = await self.db["estratto_conto_movimenti"].find(
            query_esatto, {"_id": 0}
        ).to_list(50)
        
        # Cerca match con riferimenti
        for mov in movimenti_esatti:
            descrizione = (mov.get("descrizione_originale") or mov.get("descrizione") or "").lower()
            mov_fornitore = (mov.get("fornitore") or "").lower()
            testo_completo = f"{descrizione} {mov_fornitore}"
            
            # Check numero fattura in descrizione
            numero_fatt_match = False
            if numero_fattura and len(numero_fattura) >= 3:
                # Cerca numero fattura esatto o parziale
                num_fatt_lower = numero_fattura.lower().strip()
                if num_fatt_lower in testo_completo:
                    numero_fatt_match = True
                # Cerca anche solo la parte numerica
                num_only = re.sub(r'[^0-9]', '', numero_fattura)
                if num_only and len(num_only) >= 4 and num_only in testo_completo:
                    numero_fatt_match = True
            
            # Check fornitore
            fornitore_match = False
            if parole_fornitore:
                # Almeno una parola chiave del fornitore
                for parola in parole_fornitore:
                    if parola in testo_completo:
                        fornitore_match = True
                        break
                # Fuzzy matching
                if not fornitore_match and FUZZY_AVAILABLE and mov_fornitore:
                    if fuzz.partial_ratio(fornitore_lower, mov_fornitore) >= 80:
                        fornitore_match = True
            
            # Check P.IVA
            piva_match = False
            if fornitore_piva and len(fornitore_piva) >= 11:
                if fornitore_piva in testo_completo:
                    piva_match = True
            
            # Determina confidenza
            if numero_fatt_match or piva_match:
                # ALTA confidenza: riferimento esplicito
                risultato.update({
                    "trovato": True,
                    "tipo_match": TipoMatch.ESATTO.value,
                    "confidenza": ConfidenzaMatch.ALTA.value,
                    "movimento_id": mov.get("id"),
                    "movimento_data": mov.get("data"),
                    "movimento_importo": abs(float(mov.get("importo", 0))),
                    "movimento_descrizione": mov.get("descrizione_originale") or mov.get("descrizione"),
                    "differenza_importo": 0,
                    "note": "Match esatto con riferimento fattura/P.IVA"
                })
                return risultato
            
            elif fornitore_match:
                # ALTA confidenza: fornitore confermato
                risultato.update({
                    "trovato": True,
                    "tipo_match": TipoMatch.ESATTO.value,
                    "confidenza": ConfidenzaMatch.ALTA.value,
                    "movimento_id": mov.get("id"),
                    "movimento_data": mov.get("data"),
                    "movimento_importo": abs(float(mov.get("importo", 0))),
                    "movimento_descrizione": mov.get("descrizione_originale") or mov.get("descrizione"),
                    "differenza_importo": 0,
                    "note": "Match esatto con fornitore confermato"
                })
                return risultato
        
        # Se importo >= €100 e match esatto senza conferma nome → MEDIA confidenza
        if movimenti_esatti and importo_abs >= 100:
            mov = movimenti_esatti[0]
            risultato.update({
                "trovato": True,
                "tipo_match": TipoMatch.SOLO_IMPORTO.value,
                "confidenza": ConfidenzaMatch.MEDIA.value,
                "movimento_id": mov.get("id"),
                "movimento_data": mov.get("data"),
                "movimento_importo": abs(float(mov.get("importo", 0))),
                "movimento_descrizione": mov.get("descrizione_originale") or mov.get("descrizione"),
                "differenza_importo": 0,
                "note": "Stesso importo ma causale da verificare"
            })
            return risultato
        
        # =====================================================================
        # LIVELLO 2: MATCH PARZIALE (importo diverso di pochi euro)
        # =====================================================================
        tolleranza_parziale = max(TOLLERANZA_IMPORTO_PARZIALE, importo_abs * TOLLERANZA_PERCENTUALE)
        
        query_parziale = {
            "tipo": {"$in": ["uscita", "addebito", "pagamento"]},
            "$or": [
                {"importo": {"$gte": importo_abs - tolleranza_parziale, 
                            "$lte": importo_abs + tolleranza_parziale}},
                {"importo": {"$gte": -importo_abs - tolleranza_parziale, 
                            "$lte": -importo_abs + tolleranza_parziale}}
            ],
            "data": {"$gte": data_min, "$lte": data_max},
            "fattura_id": {"$exists": False}
        }
        
        movimenti_parziali = await self.db["estratto_conto_movimenti"].find(
            query_parziale, {"_id": 0}
        ).to_list(30)
        
        # Filtra quelli già controllati (esatti)
        ids_esatti = {m.get("id") for m in movimenti_esatti}
        movimenti_parziali = [m for m in movimenti_parziali if m.get("id") not in ids_esatti]
        
        for mov in movimenti_parziali:
            descrizione = (mov.get("descrizione_originale") or mov.get("descrizione") or "").lower()
            mov_fornitore = (mov.get("fornitore") or "").lower()
            testo_completo = f"{descrizione} {mov_fornitore}"
            
            # Cerca fornitore
            fornitore_match = False
            if parole_fornitore:
                for parola in parole_fornitore:
                    if parola in testo_completo:
                        fornitore_match = True
                        break
                if not fornitore_match and FUZZY_AVAILABLE and mov_fornitore:
                    if fuzz.partial_ratio(fornitore_lower, mov_fornitore) >= 75:
                        fornitore_match = True
            
            if fornitore_match:
                mov_importo = abs(float(mov.get("importo", 0)))
                differenza = abs(mov_importo - importo_abs)
                
                risultato.update({
                    "trovato": True,
                    "tipo_match": TipoMatch.PARZIALE_IMPORTO.value,
                    "confidenza": ConfidenzaMatch.MEDIA.value,
                    "movimento_id": mov.get("id"),
                    "movimento_data": mov.get("data"),
                    "movimento_importo": mov_importo,
                    "movimento_descrizione": mov.get("descrizione_originale") or mov.get("descrizione"),
                    "differenza_importo": differenza,
                    "note": f"Match fornitore con differenza €{differenza:.2f} (possibili spese bancarie/sconti)"
                })
                return risultato
        
        # =====================================================================
        # LIVELLO 3: SUGGERIMENTI (match deboli)
        # =====================================================================
        # Raccogli suggerimenti anche se non c'è match certo
        for mov in movimenti_esatti + movimenti_parziali:
            mov_importo = abs(float(mov.get("importo", 0)))
            differenza = abs(mov_importo - importo_abs)
            
            risultato["suggerimenti"].append({
                "movimento_id": mov.get("id"),
                "movimento_data": mov.get("data"),
                "movimento_importo": mov_importo,
                "movimento_descrizione": mov.get("descrizione_originale") or mov.get("descrizione"),
                "differenza_importo": differenza,
                "confidenza": ConfidenzaMatch.BASSA.value
            })
        
        # Ordina suggerimenti per differenza importo
        risultato["suggerimenti"] = sorted(
            risultato["suggerimenti"], 
            key=lambda x: x["differenza_importo"]
        )[:5]  # Max 5 suggerimenti
        
        return risultato
    
    # =========================================================================
    # CONFERMA PAGAMENTO
    # =========================================================================
    
    async def conferma_pagamento(
        self,
        fattura_id: str,
        metodo: str,  # "cassa" o "banca"
        data_pagamento: str = None,
        note: str = ""
    ) -> Dict[str, Any]:
        """
        Conferma il metodo di pagamento per una fattura e crea scrittura in Prima Nota.
        
        LOGICA:
        1. Aggiorna stato fattura
        2. Verifica copertura estratto conto
        3. Se CASSA + estratto copre → cerca match (potrebbe essere banca)
        4. Se BANCA + estratto copre → cerca match per riconciliare
        5. Crea movimento in Prima Nota appropriata
        
        Args:
            fattura_id: ID fattura
            metodo: "cassa" o "banca"
            data_pagamento: Data pagamento (default: data fattura)
            note: Note aggiuntive
            
        Returns:
            Dict con risultato operazione
        """
        risultato = {
            "success": False,
            "fattura_id": fattura_id,
            "metodo_confermato": metodo,
            "stato_riconciliazione": None,
            "movimento_prima_nota_id": None,
            "movimento_prima_nota_collection": None,
            "match_estratto": None,
            "azioni_richieste": [],
            "warnings": [],
            "audit": []
        }
        
        # Recupera fattura
        fattura = await self.db["invoices"].find_one(
            {"id": fattura_id},
            {"_id": 0}
        )
        
        if not fattura:
            risultato["error"] = "Fattura non trovata"
            return risultato
        
        # Verifica stato attuale
        stato_attuale = fattura.get("stato_riconciliazione", "in_attesa_conferma")
        if stato_attuale in [StatoRiconciliazione.RICONCILIATA.value, 
                            StatoRiconciliazione.LOCK_MANUALE.value]:
            risultato["error"] = f"Fattura già in stato '{stato_attuale}', non modificabile"
            return risultato
        
        # Dati fattura - normalizza campi (supporta formato legacy e standard)
        importo = float(fattura.get("importo_totale") or fattura.get("total_amount") or 0)
        data_fattura = fattura.get("data_documento") or fattura.get("invoice_date") or ""
        numero_fattura = fattura.get("numero_documento") or fattura.get("invoice_number") or ""
        fornitore_nome = fattura.get("fornitore_ragione_sociale") or fattura.get("supplier_name") or ""
        fornitore_piva = fattura.get("fornitore_partita_iva") or fattura.get("supplier_vat") or ""
        fornitore_id = fattura.get("fornitore_id")
        
        if not data_pagamento:
            data_pagamento = data_fattura
        
        # Verifica copertura estratto
        coperto, ultima_data_estratto = await self.verifica_copertura_estratto(data_fattura)
        
        # Log audit
        risultato["audit"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "azione": "conferma_pagamento",
            "metodo": metodo,
            "estratto_copre_data": coperto,
            "ultima_data_estratto": ultima_data_estratto
        })
        
        # =====================================================================
        # CASO 1: CASSA CONFERMATA
        # =====================================================================
        if metodo == "cassa":
            if not coperto:
                # Estratto non copre → sospendi
                nuovo_stato = StatoRiconciliazione.SOSPESA_ATTESA_ESTRATTO.value
                risultato["warnings"].append(
                    f"Estratto conto non aggiornato (ultimo: {ultima_data_estratto}). "
                    "Operazione sospesa in attesa di nuovo estratto."
                )
                risultato["azioni_richieste"].append("caricare_estratto_aggiornato")
            else:
                # Estratto copre → verifica se è davvero cassa
                match = await self.cerca_match_in_estratto(
                    importo, data_fattura, numero_fattura, fornitore_nome, fornitore_piva
                )
                
                if match["trovato"]:
                    if match["confidenza"] == ConfidenzaMatch.ALTA.value:
                        # Trovato in banca! Proponi spostamento
                        nuovo_stato = StatoRiconciliazione.DA_VERIFICARE_SPOSTAMENTO.value
                        risultato["match_estratto"] = match
                        risultato["warnings"].append(
                            f"⚠️ ATTENZIONE: Operazione trovata in estratto conto bancario! "
                            f"Data: {match['movimento_data']}, Importo: €{match['movimento_importo']:.2f}. "
                            "Probabilmente è un pagamento BANCA, non CASSA."
                        )
                        risultato["azioni_richieste"].append("verificare_spostamento_a_banca")
                    
                    elif match["confidenza"] == ConfidenzaMatch.MEDIA.value:
                        # Match incerto
                        nuovo_stato = StatoRiconciliazione.DA_VERIFICARE_MATCH_INCERTO.value
                        risultato["match_estratto"] = match
                        risultato["warnings"].append(
                            f"Possibile match in estratto: {match['note']}. Verifica necessaria."
                        )
                        risultato["azioni_richieste"].append("verificare_match")
                    
                    else:
                        # Match basso, conferma cassa
                        nuovo_stato = StatoRiconciliazione.CONFERMATA_CASSA.value
                        risultato["match_estratto"] = match
                
                else:
                    # Non trovato in estratto → conferma cassa
                    nuovo_stato = StatoRiconciliazione.CONFERMATA_CASSA.value
            
            collection_prima_nota = "prima_nota_cassa"
        
        # =====================================================================
        # CASO 2: BANCA CONFERMATA
        # =====================================================================
        else:  # metodo == "banca"
            if not coperto:
                # Estratto non copre → sospendi in attesa riconciliazione
                nuovo_stato = StatoRiconciliazione.SOSPESA_ATTESA_ESTRATTO.value
                risultato["warnings"].append(
                    f"Estratto conto non aggiornato (ultimo: {ultima_data_estratto}). "
                    "Pagamento registrato ma in attesa riconciliazione."
                )
                risultato["azioni_richieste"].append("caricare_estratto_aggiornato")
            else:
                # Estratto copre → cerca match per riconciliare
                match = await self.cerca_match_in_estratto(
                    importo, data_fattura, numero_fattura, fornitore_nome, fornitore_piva
                )
                
                if match["trovato"]:
                    if match["confidenza"] == ConfidenzaMatch.ALTA.value:
                        # Match perfetto → riconcilia automaticamente
                        nuovo_stato = StatoRiconciliazione.RICONCILIATA.value
                        risultato["match_estratto"] = match
                        # Collega movimento
                        await self._collega_movimento_estratto(
                            match["movimento_id"], fattura_id
                        )
                    
                    elif match["confidenza"] == ConfidenzaMatch.MEDIA.value:
                        # Match da verificare
                        nuovo_stato = StatoRiconciliazione.DA_VERIFICARE_MATCH_INCERTO.value
                        risultato["match_estratto"] = match
                        risultato["warnings"].append(
                            f"Match trovato con discrepanza: {match['note']}"
                        )
                        risultato["azioni_richieste"].append("verificare_match")
                    
                    else:
                        # Match basso → anomalia
                        nuovo_stato = StatoRiconciliazione.ANOMALIA_NON_IN_ESTRATTO.value
                        risultato["match_estratto"] = match
                        risultato["warnings"].append(
                            "Pagamento banca non trovato in estratto conto. "
                            "Verificare: bonifico partito? Assegno incassato? Errore metodo?"
                        )
                        risultato["azioni_richieste"].append("verificare_anomalia")
                
                else:
                    # Non trovato → anomalia
                    nuovo_stato = StatoRiconciliazione.ANOMALIA_NON_IN_ESTRATTO.value
                    risultato["warnings"].append(
                        "⚠️ Pagamento BANCA confermato ma NON trovato in estratto conto! "
                        "Verificare: bonifico non partito? Era cassa? Estratto incompleto?"
                    )
                    risultato["azioni_richieste"].append("verificare_anomalia")
            
            collection_prima_nota = "prima_nota_banca"
        
        # =====================================================================
        # CREA MOVIMENTO PRIMA NOTA
        # =====================================================================
        movimento_id = str(uuid.uuid4())
        movimento = {
            "id": movimento_id,
            "data": data_pagamento,
            "tipo": "uscita",
            "categoria": "Pagamento fornitore",
            "descrizione": f"Pagamento Fatt. {numero_fattura} - {fornitore_nome}",
            "importo": importo,
            "fattura_id": fattura_id,
            "fattura_numero": numero_fattura,
            "fornitore_id": fornitore_id,
            "fornitore_nome": fornitore_nome,
            "metodo_pagamento": metodo,
            "stato": "registrato",
            "provvisorio": nuovo_stato != StatoRiconciliazione.RICONCILIATA.value,
            "riconciliato": nuovo_stato == StatoRiconciliazione.RICONCILIATA.value,
            "note": note,
            "source": "conferma_pagamento_intelligente",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await self.db[collection_prima_nota].insert_one(movimento.copy())
        
        risultato["movimento_prima_nota_id"] = movimento_id
        risultato["movimento_prima_nota_collection"] = collection_prima_nota
        
        # =====================================================================
        # GENERA SCRITTURA CONTABILE (Partita Doppia)
        # =====================================================================
        scrittura_contabile_id = None
        if ACCOUNTING_ENGINE_AVAILABLE:
            try:
                engine = get_accounting_engine_persistent(self.db)
                scrittura = await engine.genera_scrittura_da_pagamento(
                    fattura_id=fattura_id,
                    metodo=metodo,
                    importo=importo,
                    data_documento=data_pagamento,
                    numero_documento=numero_fattura,
                    fornitore_nome=fornitore_nome
                )
                scrittura_contabile_id = scrittura.get("id")
                risultato["scrittura_contabile_id"] = scrittura_contabile_id
                logger.info(f"✅ Scrittura contabile creata: {scrittura_contabile_id}")
            except Exception as e:
                logger.error(f"Errore creazione scrittura contabile: {e}")
                risultato["warnings"].append(f"Scrittura contabile non creata: {e}")
        
        # =====================================================================
        # AGGIORNA STATO FATTURA
        # =====================================================================
        update_fattura = {
            "stato_riconciliazione": nuovo_stato,
            "metodo_pagamento_confermato": metodo,
            "metodo_pagamento_modificato_manualmente": True,
            "data_pagamento_confermato": data_pagamento,
            "pagato": True,
            "provvisorio": nuovo_stato != StatoRiconciliazione.RICONCILIATA.value,
            "riconciliato": nuovo_stato == StatoRiconciliazione.RICONCILIATA.value,
            f"prima_nota_{metodo}_id": movimento_id,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        if scrittura_contabile_id:
            update_fattura["scrittura_contabile_id"] = scrittura_contabile_id
        
        # Se spostamento proposto, salva dati match per UI
        if risultato.get("match_estratto"):
            update_fattura["match_estratto_proposto"] = risultato["match_estratto"]
        
        await self.db["invoices"].update_one(
            {"id": fattura_id},
            {"$set": update_fattura}
        )
        
        risultato["success"] = True
        risultato["stato_riconciliazione"] = nuovo_stato
        
        logger.info(
            f"✅ Pagamento confermato: Fatt. {numero_fattura} → {metodo.upper()}, "
            f"Stato: {nuovo_stato}"
        )
        
        return risultato
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    async def _collega_movimento_estratto(self, movimento_id: str, fattura_id: str):
        """Collega un movimento estratto conto alla fattura."""
        await self.db["estratto_conto_movimenti"].update_one(
            {"id": movimento_id},
            {"$set": {
                "fattura_id": fattura_id,
                "riconciliato": True,
                "riconciliato_at": datetime.now(timezone.utc).isoformat()
            }}
        )
    
    async def applica_spostamento(
        self,
        fattura_id: str,
        movimento_estratto_id: str,
        conferma: bool = True
    ) -> Dict[str, Any]:
        """
        Applica lo spostamento da Cassa a Banca dopo verifica utente.
        
        Args:
            fattura_id: ID fattura
            movimento_estratto_id: ID movimento estratto da collegare
            conferma: Se True applica, se False mantiene in cassa
            
        Returns:
            Dict con risultato
        """
        fattura = await self.db["invoices"].find_one(
            {"id": fattura_id}, {"_id": 0}
        )
        
        if not fattura:
            return {"success": False, "error": "Fattura non trovata"}
        
        if not conferma:
            # Utente rifiuta spostamento → lock manuale su cassa
            await self.db["invoices"].update_one(
                {"id": fattura_id},
                {"$set": {
                    "stato_riconciliazione": StatoRiconciliazione.LOCK_MANUALE.value,
                    "lock_manuale_motivo": "Utente ha confermato pagamento CASSA nonostante match bancario",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            return {
                "success": True,
                "azione": "lock_manuale_cassa",
                "message": "Operazione bloccata come CASSA. Non verrà più verificata automaticamente."
            }
        
        # Applica spostamento - normalizza campi
        movimento_cassa_id = fattura.get("prima_nota_cassa_id")
        importo = float(fattura.get("importo_totale") or fattura.get("total_amount") or 0)
        numero_fattura = fattura.get("numero_documento") or fattura.get("invoice_number") or ""
        fornitore_nome = fattura.get("fornitore_ragione_sociale") or fattura.get("supplier_name") or ""
        fornitore_id = fattura.get("fornitore_id")
        data_pagamento = fattura.get("data_pagamento_confermato") or fattura.get("data_documento") or fattura.get("invoice_date")
        
        # 1. Recupera e elimina movimento da cassa
        if movimento_cassa_id:
            movimento_cassa = await self.db["prima_nota_cassa"].find_one(
                {"id": movimento_cassa_id}, {"_id": 0}
            )
            await self.db["prima_nota_cassa"].delete_one({"id": movimento_cassa_id})
        
        # 2. Crea movimento in banca
        nuovo_movimento_id = str(uuid.uuid4())
        movimento_banca = {
            "id": nuovo_movimento_id,
            "data": data_pagamento,
            "tipo": "uscita",
            "categoria": "Pagamento fornitore",
            "descrizione": f"Pagamento Fatt. {numero_fattura} - {fornitore_nome}",
            "importo": importo,
            "fattura_id": fattura_id,
            "fattura_numero": numero_fattura,
            "fornitore_id": fornitore_id,
            "fornitore_nome": fornitore_nome,
            "metodo_pagamento": "banca",
            "stato": "registrato",
            "provvisorio": False,
            "riconciliato": True,
            "movimento_estratto_id": movimento_estratto_id,
            "spostato_da_cassa": True,
            "movimento_cassa_originale_id": movimento_cassa_id,
            "note": "Spostato da Cassa dopo verifica estratto conto",
            "source": "spostamento_cassa_banca",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await self.db["prima_nota_banca"].insert_one(movimento_banca.copy())
        
        # 3. Collega movimento estratto
        await self._collega_movimento_estratto(movimento_estratto_id, fattura_id)
        
        # 4. Aggiorna fattura
        await self.db["invoices"].update_one(
            {"id": fattura_id},
            {"$set": {
                "stato_riconciliazione": StatoRiconciliazione.RICONCILIATA.value,
                "metodo_pagamento_confermato": "banca",
                "prima_nota_banca_id": nuovo_movimento_id,
                "prima_nota_cassa_id": None,
                "provvisorio": False,
                "riconciliato": True,
                "spostamento_applicato": True,
                "spostamento_da": "cassa",
                "spostamento_a": "banca",
                "spostamento_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        logger.info(f"✅ Spostamento applicato: Fatt. {numero_fattura} CASSA → BANCA")
        
        return {
            "success": True,
            "azione": "spostamento_applicato",
            "da": "cassa",
            "a": "banca",
            "movimento_eliminato": movimento_cassa_id,
            "movimento_creato": nuovo_movimento_id,
            "message": f"Fattura {numero_fattura} spostata da Cassa a Banca e riconciliata"
        }
    
    # =========================================================================
    # RI-ANALISI SU NUOVO ESTRATTO CONTO
    # =========================================================================
    
    async def rianalizza_operazioni_sospese(self) -> Dict[str, Any]:
        """
        Ri-analizza tutte le operazioni sospese quando arriva nuovo estratto conto.
        
        Chiamare dopo ogni upload di estratto conto.
        
        Returns:
            Dict con operazioni da verificare
        """
        risultato = {
            "analizzate": 0,
            "spostamenti_proposti": [],
            "riconciliate": [],
            "ancora_sospese": [],
            "anomalie": []
        }
        
        # Recupera ultima data estratto
        ultima_data = await self.get_ultima_data_estratto()
        if not ultima_data:
            return risultato
        
        # Trova operazioni da ri-analizzare
        query = {
            "stato_riconciliazione": {"$in": [
                StatoRiconciliazione.SOSPESA_ATTESA_ESTRATTO.value,
                StatoRiconciliazione.CONFERMATA_CASSA.value,
                StatoRiconciliazione.ANOMALIA_NON_IN_ESTRATTO.value
            ]},
            "lock_manuale": {"$ne": True}
        }
        
        fatture = await self.db["invoices"].find(query, {"_id": 0}).to_list(500)
        risultato["analizzate"] = len(fatture)
        
        for fattura in fatture:
            fattura_id = fattura.get("id")
            importo = float(fattura.get("importo_totale", 0))
            data_fattura = fattura.get("data_documento", "")
            numero_fattura = fattura.get("numero_documento", "")
            fornitore_nome = fattura.get("fornitore_ragione_sociale", "")
            fornitore_piva = fattura.get("fornitore_partita_iva", "")
            metodo_confermato = fattura.get("metodo_pagamento_confermato", "")
            stato_attuale = fattura.get("stato_riconciliazione", "")
            
            # Verifica copertura
            coperto, _ = await self.verifica_copertura_estratto(data_fattura)
            
            if not coperto:
                risultato["ancora_sospese"].append({
                    "fattura_id": fattura_id,
                    "numero": numero_fattura,
                    "motivo": "Estratto ancora non copre la data"
                })
                continue
            
            # Cerca match
            match = await self.cerca_match_in_estratto(
                importo, data_fattura, numero_fattura, fornitore_nome, fornitore_piva
            )
            
            if match["trovato"]:
                if metodo_confermato == "cassa":
                    # Era cassa ma trovato in banca → proponi spostamento
                    risultato["spostamenti_proposti"].append({
                        "fattura_id": fattura_id,
                        "numero": numero_fattura,
                        "fornitore": fornitore_nome,
                        "importo": importo,
                        "match": match,
                        "azione_richiesta": "confermare_spostamento_a_banca"
                    })
                    
                    # Aggiorna stato
                    await self.db["invoices"].update_one(
                        {"id": fattura_id},
                        {"$set": {
                            "stato_riconciliazione": StatoRiconciliazione.DA_VERIFICARE_SPOSTAMENTO.value,
                            "match_estratto_proposto": match,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                
                elif metodo_confermato == "banca":
                    # Era banca → riconcilia
                    if match["confidenza"] == ConfidenzaMatch.ALTA.value:
                        await self._collega_movimento_estratto(match["movimento_id"], fattura_id)
                        await self.db["invoices"].update_one(
                            {"id": fattura_id},
                            {"$set": {
                                "stato_riconciliazione": StatoRiconciliazione.RICONCILIATA.value,
                                "provvisorio": False,
                                "riconciliato": True,
                                "updated_at": datetime.now(timezone.utc).isoformat()
                            }}
                        )
                        risultato["riconciliate"].append({
                            "fattura_id": fattura_id,
                            "numero": numero_fattura
                        })
                    else:
                        risultato["anomalie"].append({
                            "fattura_id": fattura_id,
                            "numero": numero_fattura,
                            "motivo": f"Match incerto: {match['note']}"
                        })
            
            else:
                # Non trovato
                if metodo_confermato == "cassa":
                    # Confermato cassa
                    await self.db["invoices"].update_one(
                        {"id": fattura_id},
                        {"$set": {
                            "stato_riconciliazione": StatoRiconciliazione.CONFERMATA_CASSA.value,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }}
                    )
                else:
                    # Banca non trovata → anomalia
                    risultato["anomalie"].append({
                        "fattura_id": fattura_id,
                        "numero": numero_fattura,
                        "motivo": "Pagamento banca non trovato in estratto"
                    })
        
        logger.info(
            f"✅ Ri-analisi completata: {risultato['analizzate']} fatture, "
            f"{len(risultato['spostamenti_proposti'])} spostamenti proposti, "
            f"{len(risultato['riconciliate'])} riconciliate"
        )
        
        return risultato

    # =========================================================================
    # CASI ESTESI: PAGAMENTI PARZIALI
    # =========================================================================
    
    async def registra_pagamento_parziale(
        self,
        fattura_id: str,
        importo_pagato: float,
        metodo: str,
        data_pagamento: str = None,
        note: str = ""
    ) -> Dict[str, Any]:
        """
        Registra un pagamento parziale su una fattura.
        
        Caso 19: Fattura €1.000, pago solo €500 ora, resto dopo.
        
        Args:
            fattura_id: ID fattura
            importo_pagato: Importo di questo pagamento
            metodo: "cassa" o "banca"
            data_pagamento: Data pagamento
            note: Note
            
        Returns:
            Dict con risultato e residuo
        """
        fattura = await self.db["invoices"].find_one(
            {"id": fattura_id}, {"_id": 0}
        )
        
        if not fattura:
            return {"success": False, "error": "Fattura non trovata"}
        
        importo_totale = float(fattura.get("importo_totale") or fattura.get("total_amount") or 0)
        importi_pagati = fattura.get("pagamenti_parziali", [])
        totale_gia_pagato = sum(p.get("importo", 0) for p in importi_pagati)
        
        if importo_pagato <= 0:
            return {"success": False, "error": "Importo deve essere positivo"}
        
        if importo_pagato + totale_gia_pagato > importo_totale:
            return {"success": False, "error": f"Importo supera il residuo di €{importo_totale - totale_gia_pagato:.2f}"}
        
        if not data_pagamento:
            data_pagamento = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Crea record pagamento
        pagamento_id = str(uuid.uuid4())
        pagamento = {
            "id": pagamento_id,
            "importo": importo_pagato,
            "metodo": metodo,
            "data": data_pagamento,
            "note": note,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        # Crea movimento in prima nota
        numero_fattura = fattura.get("numero_documento") or fattura.get("invoice_number") or ""
        fornitore_nome = fattura.get("fornitore_ragione_sociale") or fattura.get("supplier_name") or ""
        
        collection = f"prima_nota_{metodo}"
        movimento = {
            "id": str(uuid.uuid4()),
            "data": data_pagamento,
            "tipo": "uscita",
            "categoria": "Pagamento parziale fornitore",
            "descrizione": f"Pagamento parziale Fatt. {numero_fattura} - {fornitore_nome}",
            "importo": importo_pagato,
            "fattura_id": fattura_id,
            "pagamento_parziale_id": pagamento_id,
            "metodo_pagamento": metodo,
            "source": "pagamento_parziale",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await self.db[collection].insert_one(movimento.copy())
        
        # Aggiorna fattura
        nuovo_totale_pagato = totale_gia_pagato + importo_pagato
        residuo = importo_totale - nuovo_totale_pagato
        
        nuovo_stato = StatoRiconciliazione.RICONCILIATA.value if residuo <= 0.01 else StatoRiconciliazione.PARZIALMENTE_PAGATA.value
        
        await self.db["invoices"].update_one(
            {"id": fattura_id},
            {
                "$push": {"pagamenti_parziali": pagamento},
                "$set": {
                    "totale_pagato": nuovo_totale_pagato,
                    "residuo_da_pagare": max(0, residuo),
                    "stato_riconciliazione": nuovo_stato,
                    "parzialmente_pagata": residuo > 0.01,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        logger.info(f"✅ Pagamento parziale: €{importo_pagato:.2f} su Fatt. {numero_fattura}. Residuo: €{residuo:.2f}")
        
        return {
            "success": True,
            "pagamento_id": pagamento_id,
            "importo_pagato": importo_pagato,
            "totale_pagato": nuovo_totale_pagato,
            "residuo": max(0, residuo),
            "stato": nuovo_stato
        }
    
    # =========================================================================
    # CASI ESTESI: NOTE DI CREDITO
    # =========================================================================
    
    async def applica_nota_credito(
        self,
        fattura_id: str,
        nota_credito_id: str = None,
        importo_nc: float = None,
        numero_nc: str = None
    ) -> Dict[str, Any]:
        """
        Applica una nota di credito a una fattura.
        
        Caso 21: Fattura €1.000, poi NC €200, importo dovuto diventa €800.
        
        Args:
            fattura_id: ID fattura da creditare
            nota_credito_id: ID nota credito (se già in sistema)
            importo_nc: Importo NC (se inserimento manuale)
            numero_nc: Numero NC (se inserimento manuale)
            
        Returns:
            Dict con nuovo importo dovuto
        """
        fattura = await self.db["invoices"].find_one(
            {"id": fattura_id}, {"_id": 0}
        )
        
        if not fattura:
            return {"success": False, "error": "Fattura non trovata"}
        
        importo_totale = float(fattura.get("importo_totale") or fattura.get("total_amount") or 0)
        note_credito = fattura.get("note_credito_collegate", [])
        totale_nc = sum(nc.get("importo", 0) for nc in note_credito)
        
        # Recupera o crea nota credito
        if nota_credito_id:
            nc = await self.db["invoices"].find_one(
                {"id": nota_credito_id, "tipo_documento": "nota_credito"},
                {"_id": 0}
            )
            if not nc:
                return {"success": False, "error": "Nota credito non trovata"}
            importo_nc = float(nc.get("importo_totale") or nc.get("total_amount") or 0)
            numero_nc = nc.get("numero_documento") or nc.get("invoice_number") or ""
        
        if not importo_nc or importo_nc <= 0:
            return {"success": False, "error": "Importo nota credito non valido"}
        
        # Record nota credito
        nc_record = {
            "id": nota_credito_id or str(uuid.uuid4()),
            "numero": numero_nc,
            "importo": importo_nc,
            "data_applicazione": datetime.now(timezone.utc).isoformat()
        }
        
        nuovo_totale_nc = totale_nc + importo_nc
        nuovo_importo_dovuto = importo_totale - nuovo_totale_nc
        
        if nuovo_importo_dovuto < 0:
            return {"success": False, "error": f"La NC supera l'importo fattura. Credito risultante: €{abs(nuovo_importo_dovuto):.2f}"}
        
        # Aggiorna fattura
        await self.db["invoices"].update_one(
            {"id": fattura_id},
            {
                "$push": {"note_credito_collegate": nc_record},
                "$set": {
                    "totale_note_credito": nuovo_totale_nc,
                    "importo_dovuto_netto": nuovo_importo_dovuto,
                    "stato_riconciliazione": StatoRiconciliazione.CON_NOTA_CREDITO.value if nuovo_importo_dovuto > 0 else StatoRiconciliazione.RICONCILIATA.value,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        numero_fattura = fattura.get("numero_documento") or fattura.get("invoice_number") or ""
        logger.info(f"✅ NC €{importo_nc:.2f} applicata a Fatt. {numero_fattura}. Nuovo dovuto: €{nuovo_importo_dovuto:.2f}")
        
        return {
            "success": True,
            "importo_originale": importo_totale,
            "totale_note_credito": nuovo_totale_nc,
            "importo_dovuto_netto": nuovo_importo_dovuto
        }
    
    # =========================================================================
    # CASI ESTESI: BONIFICO CUMULATIVO
    # =========================================================================
    
    async def cerca_bonifico_cumulativo(
        self,
        importo_movimento: float,
        data_movimento: str,
        descrizione_movimento: str
    ) -> Dict[str, Any]:
        """
        Cerca fatture che insieme matchano un bonifico cumulativo.
        
        Caso 23: Un bonifico €3.000 per 3 fatture da €1.000 ciascuna.
        
        Args:
            importo_movimento: Importo del movimento bancario
            data_movimento: Data del movimento
            descrizione_movimento: Descrizione/causale
            
        Returns:
            Dict con fatture candidate
        """
        risultato = {
            "trovato": False,
            "fatture_candidate": [],
            "somma_fatture": 0,
            "differenza": 0,
            "confidenza": ConfidenzaMatch.NESSUNA.value
        }
        
        # Estrai info dalla descrizione
        descrizione_lower = descrizione_movimento.lower()
        
        # Cerca fatture non pagate dello stesso fornitore
        # Prova a estrarre nome fornitore dalla descrizione
        parole_comuni = {"bonifico", "pagamento", "saldo", "fattura", "fatture", "fatt"}
        parole_desc = [p for p in descrizione_lower.split() if len(p) >= 3 and p not in parole_comuni]
        
        if not parole_desc:
            return risultato
        
        # Cerca fatture con fornitore simile e non pagate
        query = {
            "stato_riconciliazione": StatoRiconciliazione.IN_ATTESA_CONFERMA.value,
            "$or": [
                {"fornitore_ragione_sociale": {"$regex": "|".join(parole_desc[:3]), "$options": "i"}},
                {"supplier_name": {"$regex": "|".join(parole_desc[:3]), "$options": "i"}}
            ]
        }
        
        fatture = await self.db["invoices"].find(
            query,
            {"_id": 0, "id": 1, "numero_documento": 1, "invoice_number": 1,
             "importo_totale": 1, "total_amount": 1, "data_documento": 1, "invoice_date": 1,
             "fornitore_ragione_sociale": 1, "supplier_name": 1}
        ).to_list(50)
        
        if not fatture:
            return risultato
        
        # Ordina per importo discendente
        for f in fatture:
            f["_importo"] = float(f.get("importo_totale") or f.get("total_amount") or 0)
        fatture.sort(key=lambda x: x["_importo"], reverse=True)
        
        # Cerca combinazione che matcha l'importo
        tolleranza = max(5.0, importo_movimento * 0.005)  # 0.5% o €5
        
        # Prova combinazioni
        from itertools import combinations
        
        for n in range(1, min(len(fatture) + 1, 6)):  # Max 5 fatture
            for combo in combinations(range(len(fatture)), n):
                somma = sum(fatture[i]["_importo"] for i in combo)
                if abs(somma - importo_movimento) <= tolleranza:
                    risultato["trovato"] = True
                    risultato["fatture_candidate"] = [
                        {
                            "id": fatture[i]["id"],
                            "numero": fatture[i].get("numero_documento") or fatture[i].get("invoice_number"),
                            "importo": fatture[i]["_importo"],
                            "fornitore": fatture[i].get("fornitore_ragione_sociale") or fatture[i].get("supplier_name")
                        }
                        for i in combo
                    ]
                    risultato["somma_fatture"] = somma
                    risultato["differenza"] = abs(somma - importo_movimento)
                    risultato["confidenza"] = ConfidenzaMatch.ALTA.value if risultato["differenza"] < 1 else ConfidenzaMatch.MEDIA.value
                    return risultato
        
        return risultato
    
    async def riconcilia_bonifico_cumulativo(
        self,
        movimento_id: str,
        fatture_ids: List[str]
    ) -> Dict[str, Any]:
        """
        Riconcilia un bonifico cumulativo con multiple fatture.
        
        Args:
            movimento_id: ID movimento in estratto conto
            fatture_ids: Lista ID fatture da collegare
            
        Returns:
            Dict con risultato
        """
        risultato = {
            "success": False,
            "fatture_riconciliate": [],
            "importo_totale": 0
        }
        
        # Recupera movimento
        movimento = await self.db["estratto_conto_movimenti"].find_one(
            {"id": movimento_id}, {"_id": 0}
        )
        
        if not movimento:
            return {"success": False, "error": "Movimento non trovato"}
        
        importo_movimento = abs(float(movimento.get("importo", 0)))
        
        # Verifica fatture
        totale_fatture = 0
        fatture_valide = []
        
        for fid in fatture_ids:
            f = await self.db["invoices"].find_one({"id": fid}, {"_id": 0})
            if f:
                importo = float(f.get("importo_totale") or f.get("total_amount") or 0)
                totale_fatture += importo
                fatture_valide.append({
                    "id": fid,
                    "numero": f.get("numero_documento") or f.get("invoice_number"),
                    "importo": importo
                })
        
        if not fatture_valide:
            return {"success": False, "error": "Nessuna fattura valida"}
        
        # Verifica corrispondenza importi
        if abs(totale_fatture - importo_movimento) > 5.0:
            return {
                "success": False, 
                "error": f"Importo fatture (€{totale_fatture:.2f}) non corrisponde a movimento (€{importo_movimento:.2f})"
            }
        
        # Riconcilia tutte le fatture
        for f in fatture_valide:
            # Crea movimento in prima nota banca
            pn_id = str(uuid.uuid4())
            pn = {
                "id": pn_id,
                "data": movimento.get("data"),
                "tipo": "uscita",
                "categoria": "Pagamento fornitore (cumulativo)",
                "descrizione": f"Bonifico cumulativo - Fatt. {f['numero']}",
                "importo": f["importo"],
                "fattura_id": f["id"],
                "movimento_estratto_id": movimento_id,
                "bonifico_cumulativo": True,
                "source": "riconciliazione_cumulativa",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await self.db["prima_nota_banca"].insert_one(pn.copy())
            
            # Aggiorna fattura
            await self.db["invoices"].update_one(
                {"id": f["id"]},
                {"$set": {
                    "stato_riconciliazione": StatoRiconciliazione.RICONCILIATA.value,
                    "metodo_pagamento_confermato": "banca",
                    "prima_nota_banca_id": pn_id,
                    "pagato": True,
                    "riconciliato": True,
                    "bonifico_cumulativo_id": movimento_id,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            risultato["fatture_riconciliate"].append(f)
        
        # Aggiorna movimento estratto
        await self.db["estratto_conto_movimenti"].update_one(
            {"id": movimento_id},
            {"$set": {
                "riconciliato": True,
                "bonifico_cumulativo": True,
                "fatture_collegate": [f["id"] for f in fatture_valide],
                "riconciliato_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        risultato["success"] = True
        risultato["importo_totale"] = totale_fatture
        
        logger.info(f"✅ Bonifico cumulativo riconciliato: {len(fatture_valide)} fatture, €{totale_fatture:.2f}")
        
        return risultato
    
    # =========================================================================
    # CASI ESTESI: SCONTO CASSA
    # =========================================================================
    
    async def registra_pagamento_con_sconto(
        self,
        fattura_id: str,
        importo_pagato: float,
        metodo: str,
        percentuale_sconto: float = None,
        data_pagamento: str = None
    ) -> Dict[str, Any]:
        """
        Registra un pagamento con sconto cassa.
        
        Caso 31: Fattura €1.000, pago €980 (sconto 2%).
        
        Args:
            fattura_id: ID fattura
            importo_pagato: Importo effettivamente pagato
            metodo: "cassa" o "banca"
            percentuale_sconto: Percentuale sconto applicato (calcolata se non fornita)
            data_pagamento: Data pagamento
            
        Returns:
            Dict con risultato
        """
        fattura = await self.db["invoices"].find_one(
            {"id": fattura_id}, {"_id": 0}
        )
        
        if not fattura:
            return {"success": False, "error": "Fattura non trovata"}
        
        importo_originale = float(fattura.get("importo_totale") or fattura.get("total_amount") or 0)
        
        if importo_pagato >= importo_originale:
            return {"success": False, "error": "Per sconto, importo pagato deve essere < importo fattura"}
        
        # Calcola sconto
        importo_sconto = importo_originale - importo_pagato
        if not percentuale_sconto:
            percentuale_sconto = round((importo_sconto / importo_originale) * 100, 2)
        
        if not data_pagamento:
            data_pagamento = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        numero_fattura = fattura.get("numero_documento") or fattura.get("invoice_number") or ""
        fornitore_nome = fattura.get("fornitore_ragione_sociale") or fattura.get("supplier_name") or ""
        
        # Crea movimento in prima nota
        collection = f"prima_nota_{metodo}"
        pn_id = str(uuid.uuid4())
        movimento = {
            "id": pn_id,
            "data": data_pagamento,
            "tipo": "uscita",
            "categoria": "Pagamento fornitore con sconto",
            "descrizione": f"Pagamento Fatt. {numero_fattura} - {fornitore_nome} (sconto {percentuale_sconto}%)",
            "importo": importo_pagato,
            "importo_originale": importo_originale,
            "sconto_applicato": importo_sconto,
            "percentuale_sconto": percentuale_sconto,
            "fattura_id": fattura_id,
            "metodo_pagamento": metodo,
            "source": "pagamento_con_sconto",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await self.db[collection].insert_one(movimento.copy())
        
        # Aggiorna fattura
        await self.db["invoices"].update_one(
            {"id": fattura_id},
            {"$set": {
                "stato_riconciliazione": StatoRiconciliazione.SCONTO_APPLICATO.value,
                "metodo_pagamento_confermato": metodo,
                f"prima_nota_{metodo}_id": pn_id,
                "pagato": True,
                "riconciliato": True,
                "sconto_cassa_applicato": True,
                "importo_pagato_effettivo": importo_pagato,
                "sconto_importo": importo_sconto,
                "sconto_percentuale": percentuale_sconto,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        logger.info(f"✅ Pagamento con sconto: Fatt. {numero_fattura}, €{importo_pagato:.2f} (sconto €{importo_sconto:.2f})")
        
        return {
            "success": True,
            "importo_originale": importo_originale,
            "importo_pagato": importo_pagato,
            "sconto_importo": importo_sconto,
            "sconto_percentuale": percentuale_sconto
        }

    # =========================================================================
    # CASO 36: GESTIONE ASSEGNI MULTIPLI
    # =========================================================================
    
    async def registra_assegni_multipli(
        self,
        fattura_id: str,
        assegni: List[Dict[str, Any]],
        metodo: str = "banca"
    ) -> Dict[str, Any]:
        """
        Registra pagamento con assegni multipli per una singola fattura.
        
        Caso 36: 2 assegni (€1.028,82 + €1.421,77) = €2.450,59 → Fattura €2.450,00
        
        Args:
            fattura_id: ID fattura da pagare
            assegni: Lista di assegni [{"numero": "123", "importo": 1028.82, "data": "2026-01-15", "banca": "BPM"}]
            metodo: "banca" o "cassa" (default: banca)
            
        Returns:
            Dict con risultato operazione
        """
        risultato = {
            "success": False,
            "fattura_id": fattura_id,
            "assegni": [],
            "totale_assegni": 0,
            "differenza": 0
        }
        
        # Recupera fattura
        fattura = await self.db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
        if not fattura:
            risultato["error"] = "Fattura non trovata"
            return risultato
        
        # Dati fattura
        importo_fattura = float(fattura.get("importo_totale") or fattura.get("total_amount") or 0)
        numero_fattura = fattura.get("numero_documento") or fattura.get("invoice_number") or ""
        fornitore_nome = fattura.get("fornitore_ragione_sociale") or fattura.get("supplier_name") or ""
        fornitore_id = fattura.get("fornitore_id")
        
        # Calcola totale assegni
        totale_assegni = sum(float(a.get("importo", 0)) for a in assegni)
        differenza = abs(totale_assegni - importo_fattura)
        
        risultato["totale_assegni"] = totale_assegni
        risultato["importo_fattura"] = importo_fattura
        risultato["differenza"] = differenza
        
        # Verifica tolleranza (max €5 di differenza per arrotondamenti)
        if differenza > TOLLERANZA_ARROTONDAMENTO_MAX:
            risultato["error"] = f"Somma assegni (€{totale_assegni:.2f}) troppo diversa da fattura (€{importo_fattura:.2f}). Differenza: €{differenza:.2f}"
            return risultato
        
        # Registra gruppo assegni
        gruppo_id = str(uuid.uuid4())
        assegni_registrati = []
        
        for idx, assegno in enumerate(assegni):
            assegno_id = str(uuid.uuid4())
            assegno_record = {
                "id": assegno_id,
                "gruppo_id": gruppo_id,
                "fattura_id": fattura_id,
                "numero_assegno": assegno.get("numero", f"ASS-{idx+1}"),
                "importo": float(assegno.get("importo", 0)),
                "data_assegno": assegno.get("data", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
                "banca_emittente": assegno.get("banca", ""),
                "note": assegno.get("note", ""),
                "stato": "registrato",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await self.db["assegni"].insert_one(assegno_record.copy())
            assegni_registrati.append(assegno_record)
        
        # Crea movimento in Prima Nota
        pn_id = str(uuid.uuid4())
        movimento = {
            "id": pn_id,
            "data": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "tipo": "uscita",
            "categoria": "Pagamento fornitore (assegni multipli)",
            "descrizione": f"Pagamento Fatt. {numero_fattura} - {fornitore_nome} ({len(assegni)} assegni)",
            "importo": totale_assegni,
            "fattura_id": fattura_id,
            "fattura_numero": numero_fattura,
            "fornitore_id": fornitore_id,
            "fornitore_nome": fornitore_nome,
            "metodo_pagamento": "assegni_multipli",
            "gruppo_assegni_id": gruppo_id,
            "num_assegni": len(assegni),
            "stato": "registrato",
            "provvisorio": False,
            "source": "assegni_multipli",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        collection = f"prima_nota_{metodo}"
        await self.db[collection].insert_one(movimento.copy())
        
        # Se c'è differenza (arrotondamento), registra abbuono
        if differenza > 0.01:
            abbuono_tipo = "attivo" if totale_assegni > importo_fattura else "passivo"
            abbuono = {
                "id": str(uuid.uuid4()),
                "data": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "tipo": abbuono_tipo,
                "importo": differenza,
                "fattura_id": fattura_id,
                "descrizione": f"Arrotondamento assegni Fatt. {numero_fattura}",
                "source": "assegni_multipli_arrotondamento",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await self.db["abbuoni_arrotondamenti"].insert_one(abbuono.copy())
            risultato["arrotondamento"] = {
                "tipo": abbuono_tipo,
                "importo": differenza
            }
        
        # Aggiorna fattura
        await self.db["invoices"].update_one(
            {"id": fattura_id},
            {"$set": {
                "stato_riconciliazione": StatoRiconciliazione.ASSEGNI_MULTIPLI.value,
                "metodo_pagamento_confermato": "assegni_multipli",
                f"prima_nota_{metodo}_id": pn_id,
                "gruppo_assegni_id": gruppo_id,
                "num_assegni": len(assegni),
                "pagato": True,
                "riconciliato": True,
                "importo_pagato_effettivo": totale_assegni,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        logger.info(f"✅ Assegni multipli: Fatt. {numero_fattura}, {len(assegni)} assegni, totale €{totale_assegni:.2f}")
        
        risultato["success"] = True
        risultato["assegni"] = assegni_registrati
        risultato["gruppo_id"] = gruppo_id
        risultato["movimento_prima_nota_id"] = pn_id
        
        return risultato

    # =========================================================================
    # CASO 37: ARROTONDAMENTI AUTOMATICI
    # =========================================================================
    
    async def riconcilia_con_arrotondamento(
        self,
        fattura_id: str,
        importo_pagato: float,
        metodo: str,
        tolleranza: float = None,
        data_pagamento: str = None
    ) -> Dict[str, Any]:
        """
        Riconcilia fattura con tolleranza per arrotondamenti.
        
        Caso 37: Fattura €999.99, bonifico €1000.00 → riconcilia automaticamente
        
        Args:
            fattura_id: ID fattura
            importo_pagato: Importo effettivamente pagato
            metodo: "cassa" o "banca"
            tolleranza: Tolleranza massima (default: €1.00)
            data_pagamento: Data pagamento (opzionale)
            
        Returns:
            Dict con risultato operazione
        """
        risultato = {
            "success": False,
            "fattura_id": fattura_id
        }
        
        if tolleranza is None:
            tolleranza = TOLLERANZA_ARROTONDAMENTO_DEFAULT
        
        # Limita tolleranza massima
        tolleranza = min(tolleranza, TOLLERANZA_ARROTONDAMENTO_MAX)
        
        # Recupera fattura
        fattura = await self.db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
        if not fattura:
            risultato["error"] = "Fattura non trovata"
            return risultato
        
        # Dati fattura
        importo_fattura = float(fattura.get("importo_totale") or fattura.get("total_amount") or 0)
        numero_fattura = fattura.get("numero_documento") or fattura.get("invoice_number") or ""
        fornitore_nome = fattura.get("fornitore_ragione_sociale") or fattura.get("supplier_name") or ""
        fornitore_id = fattura.get("fornitore_id")
        
        if not data_pagamento:
            data_pagamento = fattura.get("data_documento") or fattura.get("invoice_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Calcola differenza
        differenza = importo_pagato - importo_fattura
        differenza_abs = abs(differenza)
        
        risultato["importo_fattura"] = importo_fattura
        risultato["importo_pagato"] = importo_pagato
        risultato["differenza"] = differenza
        risultato["tolleranza"] = tolleranza
        
        # Verifica se entro tolleranza
        if differenza_abs > tolleranza:
            risultato["error"] = f"Differenza €{differenza_abs:.2f} supera tolleranza €{tolleranza:.2f}"
            return risultato
        
        # Crea movimento Prima Nota
        pn_id = str(uuid.uuid4())
        movimento = {
            "id": pn_id,
            "data": data_pagamento,
            "tipo": "uscita",
            "categoria": "Pagamento fornitore",
            "descrizione": f"Pagamento Fatt. {numero_fattura} - {fornitore_nome}",
            "importo": importo_pagato,
            "fattura_id": fattura_id,
            "fattura_numero": numero_fattura,
            "fornitore_id": fornitore_id,
            "fornitore_nome": fornitore_nome,
            "metodo_pagamento": metodo,
            "stato": "registrato",
            "provvisorio": False,
            "con_arrotondamento": True,
            "arrotondamento_importo": differenza,
            "source": "riconciliazione_arrotondamento",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        collection = f"prima_nota_{metodo}"
        await self.db[collection].insert_one(movimento.copy())
        
        # Registra arrotondamento se significativo
        if differenza_abs > 0.01:
            # Abbuono attivo se pagato più della fattura, passivo se pagato meno
            abbuono_tipo = "attivo" if differenza > 0 else "passivo"
            abbuono = {
                "id": str(uuid.uuid4()),
                "data": data_pagamento,
                "tipo": abbuono_tipo,
                "importo": differenza_abs,
                "fattura_id": fattura_id,
                "fattura_numero": numero_fattura,
                "fornitore_id": fornitore_id,
                "fornitore_nome": fornitore_nome,
                "descrizione": f"Arrotondamento Fatt. {numero_fattura}" + 
                              (f" (pagato €{importo_pagato:.2f} invece di €{importo_fattura:.2f})" if differenza_abs > 0.05 else ""),
                "source": "arrotondamento_automatico",
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            await self.db["abbuoni_arrotondamenti"].insert_one(abbuono.copy())
            
            risultato["arrotondamento"] = {
                "tipo": abbuono_tipo,
                "importo": differenza_abs,
                "descrizione": "Abbuono attivo (pagato più)" if differenza > 0 else "Abbuono passivo (pagato meno)"
            }
        
        # Aggiorna fattura
        await self.db["invoices"].update_one(
            {"id": fattura_id},
            {"$set": {
                "stato_riconciliazione": StatoRiconciliazione.ARROTONDAMENTO_APPLICATO.value,
                "metodo_pagamento_confermato": metodo,
                f"prima_nota_{metodo}_id": pn_id,
                "pagato": True,
                "riconciliato": True,
                "importo_pagato_effettivo": importo_pagato,
                "arrotondamento_applicato": True,
                "arrotondamento_importo": differenza,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        logger.info(f"✅ Arrotondamento: Fatt. {numero_fattura}, pagato €{importo_pagato:.2f} (diff: €{differenza:.2f})")
        
        risultato["success"] = True
        risultato["movimento_prima_nota_id"] = pn_id
        
        return risultato

    # =========================================================================
    # CASO 38: PAGAMENTO ANTICIPATO
    # =========================================================================
    
    async def registra_pagamento_anticipato(
        self,
        fornitore_id: str = None,
        fornitore_nome: str = None,
        fornitore_piva: str = None,
        importo: float = 0,
        metodo: str = "banca",
        data_pagamento: str = None,
        riferimento: str = "",
        note: str = ""
    ) -> Dict[str, Any]:
        """
        Registra un pagamento anticipato (prima della fattura).
        
        Caso 38: Bonifico €500 il 10/01, Fattura €500 arriva il 15/01
        
        Args:
            fornitore_id: ID fornitore (opzionale)
            fornitore_nome: Nome fornitore
            fornitore_piva: P.IVA fornitore
            importo: Importo pagamento
            metodo: "cassa" o "banca"
            data_pagamento: Data pagamento
            riferimento: Riferimento ordine/contratto
            note: Note aggiuntive
            
        Returns:
            Dict con ID pagamento anticipato
        """
        risultato = {
            "success": False
        }
        
        if not importo or importo <= 0:
            risultato["error"] = "Importo deve essere maggiore di zero"
            return risultato
        
        if not fornitore_nome and not fornitore_id and not fornitore_piva:
            risultato["error"] = "Specificare almeno un identificativo fornitore"
            return risultato
        
        if not data_pagamento:
            data_pagamento = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Crea record pagamento anticipato
        pagamento_id = str(uuid.uuid4())
        pagamento = {
            "id": pagamento_id,
            "tipo": "pagamento_anticipato",
            "fornitore_id": fornitore_id,
            "fornitore_nome": fornitore_nome,
            "fornitore_piva": fornitore_piva,
            "importo": importo,
            "importo_residuo": importo,  # Inizialmente tutto il pagamento è residuo
            "metodo": metodo,
            "data_pagamento": data_pagamento,
            "riferimento": riferimento,
            "note": note,
            "stato": "in_attesa_fattura",
            "fatture_collegate": [],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await self.db["pagamenti_anticipati"].insert_one(pagamento.copy())
        
        # Crea movimento in Prima Nota
        pn_id = str(uuid.uuid4())
        movimento = {
            "id": pn_id,
            "data": data_pagamento,
            "tipo": "uscita",
            "categoria": "Pagamento anticipato fornitore",
            "descrizione": f"Pagamento anticipato - {fornitore_nome or 'N/D'}" + (f" - Rif: {riferimento}" if riferimento else ""),
            "importo": importo,
            "pagamento_anticipato_id": pagamento_id,
            "fornitore_id": fornitore_id,
            "fornitore_nome": fornitore_nome,
            "metodo_pagamento": metodo,
            "stato": "registrato",
            "provvisorio": False,
            "source": "pagamento_anticipato",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        collection = f"prima_nota_{metodo}"
        await self.db[collection].insert_one(movimento.copy())
        
        logger.info(f"✅ Pagamento anticipato: {fornitore_nome}, €{importo:.2f}")
        
        risultato["success"] = True
        risultato["pagamento_anticipato_id"] = pagamento_id
        risultato["movimento_prima_nota_id"] = pn_id
        risultato["importo"] = importo
        risultato["stato"] = "in_attesa_fattura"
        
        return risultato

    async def cerca_pagamenti_anticipati_per_fattura(
        self,
        fattura_id: str
    ) -> Dict[str, Any]:
        """
        Cerca pagamenti anticipati che potrebbero corrispondere a una fattura.
        
        Cerca per:
        - Fornitore (ID, nome, P.IVA)
        - Importo simile (con tolleranza)
        - Data pagamento precedente alla fattura
        
        Args:
            fattura_id: ID fattura
            
        Returns:
            Lista di pagamenti anticipati candidati
        """
        risultato = {
            "success": False,
            "fattura_id": fattura_id,
            "pagamenti_trovati": []
        }
        
        # Recupera fattura
        fattura = await self.db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
        if not fattura:
            risultato["error"] = "Fattura non trovata"
            return risultato
        
        # Dati fattura
        importo_fattura = float(fattura.get("importo_totale") or fattura.get("total_amount") or 0)
        data_fattura = fattura.get("data_documento") or fattura.get("invoice_date") or ""
        fornitore_nome = fattura.get("fornitore_ragione_sociale") or fattura.get("supplier_name") or ""
        fornitore_piva = fattura.get("fornitore_partita_iva") or fattura.get("supplier_vat") or ""
        fornitore_id = fattura.get("fornitore_id")
        
        # Cerca pagamenti anticipati in attesa
        query = {
            "stato": "in_attesa_fattura",
            "importo_residuo": {"$gt": 0}
        }
        
        # Filtra per fornitore se disponibile
        if fornitore_id:
            query["$or"] = [
                {"fornitore_id": fornitore_id},
                {"fornitore_piva": fornitore_piva},
                {"fornitore_nome": {"$regex": fornitore_nome[:10], "$options": "i"}} if fornitore_nome else {}
            ]
        elif fornitore_piva:
            query["fornitore_piva"] = fornitore_piva
        
        pagamenti = await self.db["pagamenti_anticipati"].find(query, {"_id": 0}).to_list(50)
        
        # Filtra e ordina per rilevanza
        candidati = []
        for pag in pagamenti:
            pag_importo = float(pag.get("importo_residuo", 0))
            differenza = abs(pag_importo - importo_fattura)
            
            # Calcola score di match
            score = 0
            
            # Match importo esatto
            if differenza <= 0.01:
                score += 100
            elif differenza <= 1.00:
                score += 80
            elif differenza <= 5.00:
                score += 50
            elif differenza <= importo_fattura * 0.05:  # 5%
                score += 30
            else:
                continue  # Troppo diverso
            
            # Match fornitore
            if pag.get("fornitore_id") == fornitore_id:
                score += 50
            if pag.get("fornitore_piva") == fornitore_piva:
                score += 40
            
            # Data pagamento precedente alla fattura
            pag_data = pag.get("data_pagamento", "")
            if pag_data and data_fattura and pag_data <= data_fattura:
                score += 20
            
            candidati.append({
                **pag,
                "score_match": score,
                "differenza_importo": differenza
            })
        
        # Ordina per score decrescente
        candidati.sort(key=lambda x: x["score_match"], reverse=True)
        
        risultato["success"] = True
        risultato["pagamenti_trovati"] = candidati[:10]  # Max 10 risultati
        risultato["importo_fattura"] = importo_fattura
        
        return risultato

    async def collega_pagamento_anticipato_a_fattura(
        self,
        pagamento_anticipato_id: str,
        fattura_id: str,
        importo_da_collegare: float = None
    ) -> Dict[str, Any]:
        """
        Collega un pagamento anticipato a una fattura.
        
        Args:
            pagamento_anticipato_id: ID pagamento anticipato
            fattura_id: ID fattura
            importo_da_collegare: Importo da collegare (default: tutto il residuo)
            
        Returns:
            Dict con risultato operazione
        """
        risultato = {
            "success": False,
            "pagamento_anticipato_id": pagamento_anticipato_id,
            "fattura_id": fattura_id
        }
        
        # Recupera pagamento anticipato
        pagamento = await self.db["pagamenti_anticipati"].find_one(
            {"id": pagamento_anticipato_id}, {"_id": 0}
        )
        if not pagamento:
            risultato["error"] = "Pagamento anticipato non trovato"
            return risultato
        
        # Recupera fattura
        fattura = await self.db["invoices"].find_one({"id": fattura_id}, {"_id": 0})
        if not fattura:
            risultato["error"] = "Fattura non trovata"
            return risultato
        
        # Dati
        importo_residuo = float(pagamento.get("importo_residuo", 0))
        importo_fattura = float(fattura.get("importo_totale") or fattura.get("total_amount") or 0)
        numero_fattura = fattura.get("numero_documento") or fattura.get("invoice_number") or ""
        
        if importo_da_collegare is None:
            importo_da_collegare = min(importo_residuo, importo_fattura)
        
        if importo_da_collegare > importo_residuo:
            risultato["error"] = f"Importo da collegare (€{importo_da_collegare:.2f}) supera residuo disponibile (€{importo_residuo:.2f})"
            return risultato
        
        # Aggiorna pagamento anticipato
        nuovo_residuo = importo_residuo - importo_da_collegare
        fatture_collegate = pagamento.get("fatture_collegate", [])
        fatture_collegate.append({
            "fattura_id": fattura_id,
            "fattura_numero": numero_fattura,
            "importo_collegato": importo_da_collegare,
            "data_collegamento": datetime.now(timezone.utc).isoformat()
        })
        
        nuovo_stato = "completato" if nuovo_residuo <= 0.01 else "parzialmente_utilizzato"
        
        await self.db["pagamenti_anticipati"].update_one(
            {"id": pagamento_anticipato_id},
            {"$set": {
                "importo_residuo": nuovo_residuo,
                "fatture_collegate": fatture_collegate,
                "stato": nuovo_stato,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        # Determina se fattura completamente pagata
        importo_residuo_fattura = importo_fattura - importo_da_collegare
        fattura_completata = importo_residuo_fattura <= 0.01
        
        # Aggiorna fattura
        update_fattura = {
            "pagamento_anticipato_id": pagamento_anticipato_id,
            "importo_da_anticipato": importo_da_collegare,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        if fattura_completata:
            update_fattura.update({
                "stato_riconciliazione": StatoRiconciliazione.PAGAMENTO_ANTICIPATO.value,
                "metodo_pagamento_confermato": pagamento.get("metodo", "banca"),
                "pagato": True,
                "riconciliato": True,
                "importo_pagato_effettivo": importo_da_collegare
            })
        else:
            update_fattura.update({
                "stato_riconciliazione": StatoRiconciliazione.PARZIALMENTE_PAGATA.value,
                "importo_residuo": importo_residuo_fattura
            })
        
        await self.db["invoices"].update_one({"id": fattura_id}, {"$set": update_fattura})
        
        logger.info(f"✅ Collegato pagamento anticipato a Fatt. {numero_fattura}: €{importo_da_collegare:.2f}")
        
        risultato["success"] = True
        risultato["importo_collegato"] = importo_da_collegare
        risultato["residuo_pagamento"] = nuovo_residuo
        risultato["residuo_fattura"] = importo_residuo_fattura if not fattura_completata else 0
        risultato["fattura_completata"] = fattura_completata
        risultato["stato_pagamento"] = nuovo_stato
        
        return risultato

    async def get_pagamenti_anticipati_in_attesa(self) -> Dict[str, Any]:
        """
        Ritorna tutti i pagamenti anticipati in attesa di fattura.
        """
        pagamenti = await self.db["pagamenti_anticipati"].find(
            {"stato": {"$in": ["in_attesa_fattura", "parzialmente_utilizzato"]}},
            {"_id": 0}
        ).sort("data_pagamento", -1).to_list(100)
        
        totale = sum(float(p.get("importo_residuo", 0)) for p in pagamenti)
        
        return {
            "success": True,
            "count": len(pagamenti),
            "totale_residuo": totale,
            "pagamenti": pagamenti
        }




# =============================================================================
# FUNZIONI HELPER GLOBALI
# =============================================================================

def get_riconciliazione_service(db) -> RiconciliazioneIntelligente:
    """Factory per ottenere il servizio di riconciliazione."""
    return RiconciliazioneIntelligente(db)
