"""
ACCOUNTING ENGINE - Sistema Contabile con Partita Doppia
=========================================================

Implementa le regole di ragioneria italiana:
- Partita doppia (DARE = AVERE sempre)
- Piano dei conti italiano
- Validazione transazioni
- Reversibilità (storno)
- Audit trail completo

Autore: Sistema Gestionale Ceraldi
Data: 21 Gennaio 2026
"""

import pandas as pd
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import hashlib
import uuid
import logging

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS E COSTANTI
# =============================================================================

class TipoConto(Enum):
    """Classificazione conti secondo piano dei conti italiano"""
    ATTIVO = "attivo"           # Beni, crediti (DARE aumenta, AVERE diminuisce)
    PASSIVO = "passivo"         # Debiti, capitale (AVERE aumenta, DARE diminuisce)
    COSTO = "costo"             # Costi/spese (DARE aumenta)
    RICAVO = "ricavo"           # Ricavi/entrate (AVERE aumenta)
    

class TipoOperazione(Enum):
    """Tipo di operazione contabile"""
    CASSA = "cassa"             # Operazioni in contanti
    BANCA = "banca"             # Operazioni bancarie
    STORNO = "storno"           # Storno di operazione precedente


class StatoTransazione(Enum):
    """Stato della transazione"""
    VALIDA = "valida"
    STORNATA = "stornata"
    PROVVISORIA = "provvisoria"


# =============================================================================
# PIANO DEI CONTI ITALIANO (Semplificato per PMI)
# =============================================================================

PIANO_DEI_CONTI = {
    # ATTIVITÀ (Classe 1-2)
    "1.1.1": {"nome": "Cassa contanti", "tipo": TipoConto.ATTIVO, "descrizione": "Denaro in cassa"},
    "1.1.2": {"nome": "Cassa POS", "tipo": TipoConto.ATTIVO, "descrizione": "Incassi POS da accreditare"},
    "1.2.1": {"nome": "Banca c/c", "tipo": TipoConto.ATTIVO, "descrizione": "Conto corrente bancario"},
    "1.2.2": {"nome": "Banca c/anticipi", "tipo": TipoConto.ATTIVO, "descrizione": "Anticipi bancari"},
    "1.3.1": {"nome": "Crediti vs clienti", "tipo": TipoConto.ATTIVO, "descrizione": "Crediti commerciali"},
    "1.3.2": {"nome": "Crediti diversi", "tipo": TipoConto.ATTIVO, "descrizione": "Altri crediti"},
    "1.4.1": {"nome": "IVA a credito", "tipo": TipoConto.ATTIVO, "descrizione": "IVA su acquisti"},
    
    # PASSIVITÀ (Classe 3-4)
    "3.1.1": {"nome": "Debiti vs fornitori", "tipo": TipoConto.PASSIVO, "descrizione": "Debiti commerciali"},
    "3.1.2": {"nome": "Debiti diversi", "tipo": TipoConto.PASSIVO, "descrizione": "Altri debiti"},
    "3.2.1": {"nome": "Debiti tributari", "tipo": TipoConto.PASSIVO, "descrizione": "Debiti per imposte"},
    "3.2.2": {"nome": "Debiti previdenziali", "tipo": TipoConto.PASSIVO, "descrizione": "Debiti INPS/INAIL"},
    "3.3.1": {"nome": "IVA a debito", "tipo": TipoConto.PASSIVO, "descrizione": "IVA su vendite"},
    "3.4.1": {"nome": "Debiti vs dipendenti", "tipo": TipoConto.PASSIVO, "descrizione": "Stipendi da pagare"},
    
    # COSTI (Classe 6)
    "6.1.1": {"nome": "Acquisti merci", "tipo": TipoConto.COSTO, "descrizione": "Acquisto merci"},
    "6.1.2": {"nome": "Acquisti materie prime", "tipo": TipoConto.COSTO, "descrizione": "Materie prime"},
    "6.2.1": {"nome": "Spese per servizi", "tipo": TipoConto.COSTO, "descrizione": "Servizi esterni"},
    "6.2.2": {"nome": "Utenze", "tipo": TipoConto.COSTO, "descrizione": "Luce, gas, acqua"},
    "6.3.1": {"nome": "Costi del personale", "tipo": TipoConto.COSTO, "descrizione": "Stipendi e contributi"},
    "6.4.1": {"nome": "Ammortamenti", "tipo": TipoConto.COSTO, "descrizione": "Ammortamenti beni"},
    "6.5.1": {"nome": "Oneri finanziari", "tipo": TipoConto.COSTO, "descrizione": "Interessi passivi"},
    "6.6.1": {"nome": "Imposte e tasse", "tipo": TipoConto.COSTO, "descrizione": "Tributi vari"},
    "6.7.1": {"nome": "Sanzioni e multe", "tipo": TipoConto.COSTO, "descrizione": "Verbali e sanzioni"},
    "6.8.1": {"nome": "Costi noleggio", "tipo": TipoConto.COSTO, "descrizione": "Canoni noleggio auto"},
    
    # RICAVI (Classe 7)
    "7.1.1": {"nome": "Ricavi vendite", "tipo": TipoConto.RICAVO, "descrizione": "Vendite merci"},
    "7.1.2": {"nome": "Ricavi servizi", "tipo": TipoConto.RICAVO, "descrizione": "Prestazioni servizi"},
    "7.2.1": {"nome": "Altri ricavi", "tipo": TipoConto.RICAVO, "descrizione": "Proventi diversi"},
    "7.3.1": {"nome": "Rimborsi attivi", "tipo": TipoConto.RICAVO, "descrizione": "Rimborsi ricevuti"},
    "7.4.1": {"nome": "Proventi finanziari", "tipo": TipoConto.RICAVO, "descrizione": "Interessi attivi"},
}


# =============================================================================
# REGOLE CONTABILI - MAPPING OPERAZIONI
# =============================================================================

REGOLE_CONTABILI = {
    # Operazioni CASSA
    "corrispettivo": {
        "descrizione": "Incasso corrispettivo giornaliero",
        "dare": "1.1.1",  # Cassa contanti
        "avere": "7.1.1", # Ricavi vendite
        "prima_nota": "cassa",
        "tipo_movimento": "entrata"
    },
    "incasso_pos": {
        "descrizione": "Incasso tramite POS",
        "dare": "1.1.2",  # Cassa POS
        "avere": "7.1.1", # Ricavi vendite
        "prima_nota": "cassa",
        "tipo_movimento": "entrata"
    },
    "pagamento_fornitore_contanti": {
        "descrizione": "Pagamento fornitore in contanti",
        "dare": "3.1.1",  # Debiti vs fornitori
        "avere": "1.1.1", # Cassa contanti
        "prima_nota": "cassa",
        "tipo_movimento": "uscita"
    },
    "versamento_banca": {
        "descrizione": "Versamento contanti in banca",
        "dare": "1.2.1",  # Banca c/c
        "avere": "1.1.1", # Cassa contanti
        "prima_nota": "cassa",
        "tipo_movimento": "uscita"
    },
    "prelievo_banca": {
        "descrizione": "Prelievo contanti da banca",
        "dare": "1.1.1",  # Cassa contanti
        "avere": "1.2.1", # Banca c/c
        "prima_nota": "cassa",
        "tipo_movimento": "entrata"
    },
    
    # Operazioni BANCA
    "pagamento_fornitore_bonifico": {
        "descrizione": "Pagamento fornitore tramite bonifico",
        "dare": "3.1.1",  # Debiti vs fornitori
        "avere": "1.2.1", # Banca c/c
        "prima_nota": "banca",
        "tipo_movimento": "uscita"
    },
    "incasso_cliente_bonifico": {
        "descrizione": "Incasso da cliente tramite bonifico",
        "dare": "1.2.1",  # Banca c/c
        "avere": "1.3.1", # Crediti vs clienti
        "prima_nota": "banca",
        "tipo_movimento": "entrata"
    },
    "accredito_pos": {
        "descrizione": "Accredito POS su conto corrente",
        "dare": "1.2.1",  # Banca c/c
        "avere": "1.1.2", # Cassa POS
        "prima_nota": "banca",
        "tipo_movimento": "entrata"
    },
    "pagamento_f24": {
        "descrizione": "Pagamento F24 tributi",
        "dare": "3.2.1",  # Debiti tributari
        "avere": "1.2.1", # Banca c/c
        "prima_nota": "banca",
        "tipo_movimento": "uscita"
    },
    "pagamento_stipendi": {
        "descrizione": "Pagamento stipendi dipendenti",
        "dare": "3.4.1",  # Debiti vs dipendenti
        "avere": "1.2.1", # Banca c/c
        "prima_nota": "banca",
        "tipo_movimento": "uscita"
    },
    "rimborso_ricevuto": {
        "descrizione": "Rimborso ricevuto (entrata)",
        "dare": "1.2.1",  # Banca c/c (ENTRATA!)
        "avere": "7.3.1", # Rimborsi attivi
        "prima_nota": "banca",
        "tipo_movimento": "entrata"
    },
    "pagamento_verbale": {
        "descrizione": "Pagamento verbale/multa",
        "dare": "6.7.1",  # Sanzioni e multe
        "avere": "1.2.1", # Banca c/c
        "prima_nota": "banca",
        "tipo_movimento": "uscita"
    },
    "canone_noleggio": {
        "descrizione": "Pagamento canone noleggio auto",
        "dare": "6.8.1",  # Costi noleggio
        "avere": "1.2.1", # Banca c/c
        "prima_nota": "banca",
        "tipo_movimento": "uscita"
    },
}


# =============================================================================
# CLASSE PRINCIPALE: AccountingEngine
# =============================================================================

class AccountingEngine:
    """
    Motore contabile con partita doppia.
    
    Principi implementati:
    1. Ogni transazione ha DARE = AVERE (partita doppia)
    2. Le date sono sempre DATA DOCUMENTO (non ricezione)
    3. Ogni operazione è reversibile tramite storno
    4. Audit trail completo di ogni modifica
    """
    
    def __init__(self, db=None):
        """
        Inizializza il motore contabile.
        
        Args:
            db: Connessione al database MongoDB (opzionale per test)
        """
        self.db = db
        self.piano_conti = PIANO_DEI_CONTI
        self.regole = REGOLE_CONTABILI
    
    # =========================================================================
    # VALIDAZIONE
    # =========================================================================
    
    def valida_transazione(self, dare: float, avere: float, tolleranza: float = 0.01) -> Tuple[bool, str]:
        """
        Valida che DARE = AVERE (partita doppia).
        
        Args:
            dare: Totale importi in DARE
            avere: Totale importi in AVERE
            tolleranza: Tolleranza per arrotondamenti (default 0.01€)
            
        Returns:
            Tuple (valido, messaggio)
        """
        differenza = abs(dare - avere)
        if differenza <= tolleranza:
            return True, "Transazione valida: DARE = AVERE"
        else:
            return False, f"Transazione NON valida: DARE ({dare:.2f}) ≠ AVERE ({avere:.2f}), differenza: {differenza:.2f}"
    
    def valida_data_documento(self, data_documento: str, data_registrazione: str = None) -> Tuple[bool, str]:
        """
        Valida che la data sia la DATA DOCUMENTO e non la data di ricezione.
        
        Args:
            data_documento: Data del documento (fattura, verbale, ecc.)
            data_registrazione: Data di registrazione (opzionale)
            
        Returns:
            Tuple (valido, messaggio)
        """
        if not data_documento:
            return False, "Data documento obbligatoria"
        
        try:
            # Accetta formati: YYYY-MM-DD, DD/MM/YYYY
            if "/" in data_documento:
                parts = data_documento.split("/")
                if len(parts[0]) == 4:  # YYYY/MM/DD
                    data_doc = datetime.strptime(data_documento, "%Y/%m/%d")
                else:  # DD/MM/YYYY
                    data_doc = datetime.strptime(data_documento, "%d/%m/%Y")
            else:
                data_doc = datetime.strptime(data_documento[:10], "%Y-%m-%d")
            
            # Verifica che non sia futura
            if data_doc.date() > datetime.now().date():
                return False, f"Data documento nel futuro: {data_documento}"
            
            return True, "Data documento valida"
            
        except ValueError as e:
            return False, f"Formato data non valido: {data_documento} - {e}"
    
    def valida_conto(self, codice_conto: str) -> Tuple[bool, str]:
        """
        Valida che il conto esista nel piano dei conti.
        
        Args:
            codice_conto: Codice del conto (es. "1.1.1")
            
        Returns:
            Tuple (valido, messaggio)
        """
        if codice_conto in self.piano_conti:
            conto = self.piano_conti[codice_conto]
            return True, f"Conto valido: {conto['nome']}"
        else:
            return False, f"Conto non trovato: {codice_conto}"
    
    def determina_tipo_operazione(self, descrizione: str, importo: float, 
                                   keywords_bancarie: List[str] = None) -> str:
        """
        Determina automaticamente il tipo di operazione dalla descrizione.
        
        Args:
            descrizione: Descrizione dell'operazione
            importo: Importo dell'operazione
            keywords_bancarie: Lista keyword per operazioni bancarie
            
        Returns:
            Tipo operazione (chiave di REGOLE_CONTABILI)
        """
        if keywords_bancarie is None:
            keywords_bancarie = [
                "BONIFICO", "SEPA", "ADDEBITO", "POS", "INCAS", 
                "NUMIA", "BANK", "F24", "STIPEND", "RID"
            ]
        
        desc_upper = descrizione.upper() if descrizione else ""
        
        # Corrispettivi
        if "CORRISPETTIV" in desc_upper:
            return "corrispettivo"
        
        # POS
        if "POS" in desc_upper or "CARTA" in desc_upper:
            if "ACCREDITO" in desc_upper or "BANCA" in desc_upper:
                return "accredito_pos"
            return "incasso_pos"
        
        # Rimborsi (IMPORTANTE: sono ENTRATE!)
        if "RIMBORSO" in desc_upper:
            return "rimborso_ricevuto"
        
        # F24
        if "F24" in desc_upper or "TRIBUT" in desc_upper:
            return "pagamento_f24"
        
        # Stipendi
        if "STIPEND" in desc_upper or "CEDOLIN" in desc_upper:
            return "pagamento_stipendi"
        
        # Verbali/Multe
        if "VERBALE" in desc_upper or "MULTA" in desc_upper or "SANZIONE" in desc_upper:
            return "pagamento_verbale"
        
        # Noleggio
        if "NOLEGGIO" in desc_upper or "CANONE" in desc_upper or "ALD" in desc_upper or "LEASYS" in desc_upper:
            return "canone_noleggio"
        
        # Operazioni bancarie generiche
        if any(kw in desc_upper for kw in keywords_bancarie):
            if importo > 0:
                return "incasso_cliente_bonifico"
            else:
                return "pagamento_fornitore_bonifico"
        
        # Default: pagamento fornitore
        if importo < 0 or "PAGAMENTO" in desc_upper:
            return "pagamento_fornitore_bonifico"
        
        return "incasso_cliente_bonifico"
    
    def rileva_duplicati(self, transazioni: List[Dict]) -> pd.DataFrame:
        """
        Rileva duplicati usando pandas.
        
        Args:
            transazioni: Lista di transazioni da verificare
            
        Returns:
            DataFrame con i duplicati trovati
        """
        if not transazioni:
            return pd.DataFrame()
        
        df = pd.DataFrame(transazioni)
        
        # Crea hash per ogni transazione
        def crea_hash(row):
            chiave = f"{row.get('data', '')}{row.get('importo', '')}{row.get('descrizione', '')[:50]}"
            return hashlib.md5(chiave.encode()).hexdigest()
        
        df['hash'] = df.apply(crea_hash, axis=1)
        
        # Trova duplicati
        duplicati = df[df.duplicated(subset=['hash'], keep=False)]
        
        return duplicati
    
    # =========================================================================
    # OPERAZIONI CONTABILI
    # =========================================================================
    
    def crea_scrittura_contabile(self, 
                                  tipo_operazione: str,
                                  importo: float,
                                  data_documento: str,
                                  descrizione: str,
                                  riferimento_documento: str = None,
                                  fornitore: str = None,
                                  fattura_id: str = None) -> Dict[str, Any]:
        """
        Crea una scrittura contabile in partita doppia.
        
        Args:
            tipo_operazione: Tipo operazione (chiave di REGOLE_CONTABILI)
            importo: Importo dell'operazione (sempre positivo)
            data_documento: Data del documento
            descrizione: Descrizione operazione
            riferimento_documento: Numero documento di riferimento
            fornitore: Nome fornitore (se applicabile)
            fattura_id: ID fattura collegata
            
        Returns:
            Dizionario con la scrittura contabile completa
        """
        # Valida tipo operazione
        if tipo_operazione not in self.regole:
            raise ValueError(f"Tipo operazione non valido: {tipo_operazione}")
        
        regola = self.regole[tipo_operazione]
        
        # Valida data
        valido, msg = self.valida_data_documento(data_documento)
        if not valido:
            raise ValueError(msg)
        
        # Valida conti
        valido_dare, _ = self.valida_conto(regola["dare"])
        valido_avere, _ = self.valida_conto(regola["avere"])
        if not valido_dare or not valido_avere:
            raise ValueError(f"Conti non validi per operazione {tipo_operazione}")
        
        # Importo sempre positivo
        importo_abs = abs(importo)
        
        # Valida partita doppia
        valido, msg = self.valida_transazione(importo_abs, importo_abs)
        if not valido:
            raise ValueError(msg)
        
        # Crea scrittura
        scrittura = {
            "id": str(uuid.uuid4()),
            "data_documento": data_documento,
            "data_registrazione": datetime.now(timezone.utc).isoformat(),
            "tipo_operazione": tipo_operazione,
            "descrizione": descrizione,
            "riferimento_documento": riferimento_documento,
            
            # Partita doppia
            "conto_dare": regola["dare"],
            "conto_dare_nome": self.piano_conti[regola["dare"]]["nome"],
            "conto_avere": regola["avere"],
            "conto_avere_nome": self.piano_conti[regola["avere"]]["nome"],
            "importo_dare": importo_abs,
            "importo_avere": importo_abs,
            
            # Metadata
            "prima_nota": regola["prima_nota"],
            "tipo_movimento": regola["tipo_movimento"],
            "fornitore": fornitore,
            "fattura_id": fattura_id,
            "stato": StatoTransazione.VALIDA.value,
            
            # Audit
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "system",
            "storno_di": None,
            "stornato_da": None,
        }
        
        # Calcola hash per deduplicazione
        hash_chiave = f"{data_documento}{importo_abs}{descrizione[:50]}{tipo_operazione}"
        scrittura["hash"] = hashlib.md5(hash_chiave.encode()).hexdigest()
        
        return scrittura
    
    def crea_storno(self, scrittura_originale: Dict[str, Any], motivo: str) -> Dict[str, Any]:
        """
        Crea uno storno (reversione) di una scrittura esistente.
        
        Lo storno inverte DARE e AVERE per annullare l'effetto contabile.
        
        Args:
            scrittura_originale: Scrittura da stornare
            motivo: Motivo dello storno
            
        Returns:
            Scrittura di storno
        """
        storno = {
            "id": str(uuid.uuid4()),
            "data_documento": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "data_registrazione": datetime.now(timezone.utc).isoformat(),
            "tipo_operazione": "storno",
            "descrizione": f"STORNO: {scrittura_originale.get('descrizione', '')} - {motivo}",
            "riferimento_documento": scrittura_originale.get("riferimento_documento"),
            
            # Partita doppia INVERTITA
            "conto_dare": scrittura_originale.get("conto_avere"),
            "conto_dare_nome": scrittura_originale.get("conto_avere_nome"),
            "conto_avere": scrittura_originale.get("conto_dare"),
            "conto_avere_nome": scrittura_originale.get("conto_dare_nome"),
            "importo_dare": scrittura_originale.get("importo_avere"),
            "importo_avere": scrittura_originale.get("importo_dare"),
            
            # Metadata
            "prima_nota": scrittura_originale.get("prima_nota"),
            "tipo_movimento": "storno",
            "stato": StatoTransazione.VALIDA.value,
            
            # Collegamento
            "storno_di": scrittura_originale.get("id"),
            
            # Audit
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": "system",
            "motivo_storno": motivo,
        }
        
        return storno
    
    # =========================================================================
    # ANALISI E REPORT
    # =========================================================================
    
    def calcola_saldo_conto(self, transazioni: List[Dict], codice_conto: str) -> float:
        """
        Calcola il saldo di un conto dalle transazioni.
        
        Args:
            transazioni: Lista transazioni
            codice_conto: Codice del conto
            
        Returns:
            Saldo del conto
        """
        if not transazioni:
            return 0.0
        
        df = pd.DataFrame(transazioni)
        
        # Solo transazioni valide
        df = df[df.get('stato', StatoTransazione.VALIDA.value) == StatoTransazione.VALIDA.value]
        
        tipo_conto = self.piano_conti.get(codice_conto, {}).get("tipo")
        
        # Somma DARE
        dare = df[df['conto_dare'] == codice_conto]['importo_dare'].sum()
        
        # Somma AVERE
        avere = df[df['conto_avere'] == codice_conto]['importo_avere'].sum()
        
        # Calcola saldo in base al tipo conto
        if tipo_conto in [TipoConto.ATTIVO, TipoConto.COSTO]:
            # DARE aumenta, AVERE diminuisce
            return dare - avere
        else:
            # AVERE aumenta, DARE diminuisce
            return avere - dare
    
    def genera_bilancio_verifica(self, transazioni: List[Dict]) -> pd.DataFrame:
        """
        Genera un bilancio di verifica.
        
        Args:
            transazioni: Lista transazioni
            
        Returns:
            DataFrame con bilancio di verifica
        """
        risultati = []
        
        for codice, info in self.piano_conti.items():
            saldo = self.calcola_saldo_conto(transazioni, codice)
            if saldo != 0:
                risultati.append({
                    "codice": codice,
                    "nome": info["nome"],
                    "tipo": info["tipo"].value,
                    "dare": saldo if saldo > 0 and info["tipo"] in [TipoConto.ATTIVO, TipoConto.COSTO] else 0,
                    "avere": abs(saldo) if saldo < 0 or info["tipo"] in [TipoConto.PASSIVO, TipoConto.RICAVO] else 0,
                    "saldo": saldo
                })
        
        df = pd.DataFrame(risultati)
        
        # Verifica quadratura
        if not df.empty:
            totale_dare = df['dare'].sum()
            totale_avere = df['avere'].sum()
            logger.info(f"Bilancio di verifica - DARE: {totale_dare:.2f}, AVERE: {totale_avere:.2f}")
        
        return df
    
    def analizza_prima_nota(self, movimenti: List[Dict], tipo: str = "cassa") -> Dict[str, Any]:
        """
        Analizza i movimenti di prima nota usando pandas.
        
        Args:
            movimenti: Lista movimenti prima nota
            tipo: "cassa" o "banca"
            
        Returns:
            Dizionario con analisi completa
        """
        if not movimenti:
            return {
                "totale_movimenti": 0,
                "totale_dare": 0,
                "totale_avere": 0,
                "saldo": 0,
                "duplicati": 0,
                "errori": []
            }
        
        df = pd.DataFrame(movimenti)
        
        # Analisi
        analisi = {
            "totale_movimenti": len(df),
            "totale_dare": df[df['tipo'] == 'entrata']['importo'].sum() if 'tipo' in df.columns else 0,
            "totale_avere": df[df['tipo'] == 'uscita']['importo'].sum() if 'tipo' in df.columns else 0,
        }
        analisi["saldo"] = analisi["totale_dare"] - analisi["totale_avere"]
        
        # Rileva duplicati
        duplicati = self.rileva_duplicati(movimenti)
        analisi["duplicati"] = len(duplicati) // 2  # Ogni duplicato appare 2 volte
        
        # Rileva errori
        errori = []
        
        # Verifica operazioni bancarie in cassa
        if tipo == "cassa":
            keywords_bancarie = ["BONIFICO", "SEPA", "ADDEBITO", "RID", "F24"]
            for _, row in df.iterrows():
                desc = str(row.get('descrizione', '')).upper()
                if any(kw in desc for kw in keywords_bancarie):
                    errori.append({
                        "tipo": "OPERAZIONE_BANCARIA_IN_CASSA",
                        "descrizione": row.get('descrizione'),
                        "data": row.get('data'),
                        "importo": row.get('importo')
                    })
        
        analisi["errori"] = errori
        
        return analisi


# =============================================================================
# FUNZIONI HELPER GLOBALI
# =============================================================================

def get_accounting_engine(db=None) -> AccountingEngine:
    """Factory function per ottenere l'engine contabile."""
    return AccountingEngine(db)


def valida_operazione_prima_nota(operazione: Dict, tipo_prima_nota: str) -> Tuple[bool, List[str]]:
    """
    Valida un'operazione prima di inserirla in prima nota.
    
    Args:
        operazione: Dizionario con i dati dell'operazione
        tipo_prima_nota: "cassa" o "banca"
        
    Returns:
        Tuple (valido, lista_errori)
    """
    engine = AccountingEngine()
    errori = []
    
    # 1. Valida data
    data = operazione.get('data') or operazione.get('data_documento')
    valido, msg = engine.valida_data_documento(data)
    if not valido:
        errori.append(msg)
    
    # 2. Verifica tipo operazione corretto per prima nota
    descrizione = operazione.get('descrizione', '')
    tipo_op = engine.determina_tipo_operazione(descrizione, operazione.get('importo', 0))
    regola = engine.regole.get(tipo_op, {})
    
    if regola.get('prima_nota') != tipo_prima_nota:
        errori.append(f"Operazione '{tipo_op}' non appartiene a Prima Nota {tipo_prima_nota.upper()}")
    
    # 3. Verifica DARE/AVERE per rimborsi
    if "RIMBORSO" in descrizione.upper():
        if operazione.get('tipo') == 'uscita':
            errori.append("ERRORE CONTABILE: Un rimborso RICEVUTO è un'ENTRATA (DARE), non un'uscita")
    
    return len(errori) == 0, errori



# =============================================================================
# PERSISTENZA DATABASE
# =============================================================================

class AccountingEnginePersistence(AccountingEngine):
    """
    Estende AccountingEngine con persistenza MongoDB.
    
    Collections utilizzate:
    - scritture_contabili: Tutte le scritture in partita doppia
    - bilancio_verifica: Snapshot periodici del bilancio
    """
    
    COLLECTION_SCRITTURE = "scritture_contabili"
    
    def __init__(self, db):
        """
        Inizializza con connessione database.
        
        Args:
            db: Connessione MongoDB
        """
        super().__init__(db)
        if not db:
            raise ValueError("Database connection required for persistence")
    
    async def salva_scrittura(self, scrittura: Dict[str, Any]) -> str:
        """
        Salva una scrittura contabile nel database.
        
        Args:
            scrittura: Scrittura da salvare
            
        Returns:
            ID della scrittura salvata
        """
        # Verifica duplicati tramite hash
        esistente = await self.db[self.COLLECTION_SCRITTURE].find_one(
            {"hash": scrittura.get("hash")},
            {"_id": 0, "id": 1}
        )
        
        if esistente:
            logger.warning(f"Scrittura duplicata ignorata: {scrittura.get('hash')[:8]}")
            return esistente.get("id")
        
        await self.db[self.COLLECTION_SCRITTURE].insert_one(scrittura.copy())
        logger.info(f"Scrittura salvata: {scrittura.get('id')} - {scrittura.get('descrizione')[:50]}")
        
        return scrittura.get("id")
    
    async def get_scritture(
        self, 
        data_da: str = None, 
        data_a: str = None,
        tipo_operazione: str = None,
        prima_nota: str = None,
        limit: int = 500
    ) -> List[Dict]:
        """
        Recupera scritture contabili con filtri.
        
        Args:
            data_da: Data inizio (YYYY-MM-DD)
            data_a: Data fine (YYYY-MM-DD)
            tipo_operazione: Filtro tipo operazione
            prima_nota: Filtro prima nota (cassa/banca)
            limit: Numero massimo risultati
            
        Returns:
            Lista scritture
        """
        query = {"stato": {"$ne": StatoTransazione.STORNATA.value}}
        
        if data_da:
            query["data_documento"] = {"$gte": data_da}
        if data_a:
            if "data_documento" in query:
                query["data_documento"]["$lte"] = data_a
            else:
                query["data_documento"] = {"$lte": data_a}
        if tipo_operazione:
            query["tipo_operazione"] = tipo_operazione
        if prima_nota:
            query["prima_nota"] = prima_nota
        
        scritture = await self.db[self.COLLECTION_SCRITTURE].find(
            query, {"_id": 0}
        ).sort("data_documento", -1).to_list(limit)
        
        return scritture
    
    async def get_scrittura_by_fattura(self, fattura_id: str) -> Optional[Dict]:
        """
        Recupera scrittura contabile collegata a una fattura.
        
        Args:
            fattura_id: ID fattura
            
        Returns:
            Scrittura o None
        """
        return await self.db[self.COLLECTION_SCRITTURE].find_one(
            {"fattura_id": fattura_id, "stato": {"$ne": StatoTransazione.STORNATA.value}},
            {"_id": 0}
        )
    
    async def storna_scrittura(self, scrittura_id: str, motivo: str) -> Dict[str, Any]:
        """
        Storna una scrittura esistente.
        
        Args:
            scrittura_id: ID scrittura da stornare
            motivo: Motivo dello storno
            
        Returns:
            Scrittura di storno creata
        """
        # Recupera scrittura originale
        originale = await self.db[self.COLLECTION_SCRITTURE].find_one(
            {"id": scrittura_id},
            {"_id": 0}
        )
        
        if not originale:
            raise ValueError(f"Scrittura non trovata: {scrittura_id}")
        
        if originale.get("stato") == StatoTransazione.STORNATA.value:
            raise ValueError("Scrittura già stornata")
        
        # Crea storno
        storno = self.crea_storno(originale, motivo)
        
        # Salva storno
        await self.db[self.COLLECTION_SCRITTURE].insert_one(storno.copy())
        
        # Aggiorna originale come stornata
        await self.db[self.COLLECTION_SCRITTURE].update_one(
            {"id": scrittura_id},
            {"$set": {
                "stato": StatoTransazione.STORNATA.value,
                "stornato_da": storno["id"],
                "stornato_at": datetime.now(timezone.utc).isoformat(),
                "motivo_storno": motivo
            }}
        )
        
        logger.info(f"Scrittura stornata: {scrittura_id} → {storno['id']}")
        
        return storno
    
    async def genera_scrittura_da_pagamento(
        self,
        fattura_id: str,
        metodo: str,  # "cassa" o "banca"
        importo: float,
        data_documento: str,
        numero_documento: str,
        fornitore_nome: str
    ) -> Dict[str, Any]:
        """
        Genera e salva una scrittura contabile da conferma pagamento.
        
        Integrato con Riconciliazione Intelligente.
        
        Args:
            fattura_id: ID fattura
            metodo: "cassa" o "banca"
            importo: Importo pagamento
            data_documento: Data documento
            numero_documento: Numero fattura
            fornitore_nome: Nome fornitore
            
        Returns:
            Scrittura creata e salvata
        """
        # Determina tipo operazione
        if metodo == "cassa":
            tipo_operazione = "pagamento_fornitore_contanti"
        else:
            tipo_operazione = "pagamento_fornitore_bonifico"
        
        descrizione = f"Pagamento Fatt. {numero_documento} - {fornitore_nome}"
        
        # Crea scrittura
        scrittura = self.crea_scrittura_contabile(
            tipo_operazione=tipo_operazione,
            importo=importo,
            data_documento=data_documento,
            descrizione=descrizione,
            riferimento_documento=numero_documento,
            fornitore=fornitore_nome,
            fattura_id=fattura_id
        )
        
        # Salva
        await self.salva_scrittura(scrittura)
        
        return scrittura
    
    async def calcola_bilancio_periodo(
        self, 
        data_da: str = None, 
        data_a: str = None
    ) -> Dict[str, Any]:
        """
        Calcola il bilancio di verifica per un periodo.
        
        Args:
            data_da: Data inizio
            data_a: Data fine
            
        Returns:
            Bilancio di verifica con totali
        """
        scritture = await self.get_scritture(data_da=data_da, data_a=data_a, limit=10000)
        
        if not scritture:
            return {
                "periodo": {"da": data_da, "a": data_a},
                "conti": [],
                "totale_dare": 0,
                "totale_avere": 0,
                "quadratura": True
            }
        
        # Calcola saldi per conto
        saldi = {}
        for s in scritture:
            conto_dare = s.get("conto_dare")
            conto_avere = s.get("conto_avere")
            importo = s.get("importo_dare", 0)
            
            if conto_dare:
                if conto_dare not in saldi:
                    saldi[conto_dare] = {"dare": 0, "avere": 0}
                saldi[conto_dare]["dare"] += importo
            
            if conto_avere:
                if conto_avere not in saldi:
                    saldi[conto_avere] = {"dare": 0, "avere": 0}
                saldi[conto_avere]["avere"] += importo
        
        # Costruisci risultato
        conti = []
        for codice, valori in saldi.items():
            info = self.piano_conti.get(codice, {})
            saldo = valori["dare"] - valori["avere"]
            conti.append({
                "codice": codice,
                "nome": info.get("nome", "Sconosciuto"),
                "tipo": info.get("tipo", TipoConto.ATTIVO).value if info.get("tipo") else "sconosciuto",
                "dare": valori["dare"],
                "avere": valori["avere"],
                "saldo": saldo
            })
        
        # Ordina per codice
        conti.sort(key=lambda x: x["codice"])
        
        totale_dare = sum(c["dare"] for c in conti)
        totale_avere = sum(c["avere"] for c in conti)
        
        return {
            "periodo": {"da": data_da, "a": data_a},
            "conti": conti,
            "totale_dare": round(totale_dare, 2),
            "totale_avere": round(totale_avere, 2),
            "quadratura": abs(totale_dare - totale_avere) < 0.01,
            "differenza": round(totale_dare - totale_avere, 2)
        }


def get_accounting_engine_persistent(db) -> AccountingEnginePersistence:
    """Factory per ottenere il motore contabile con persistenza."""
    return AccountingEnginePersistence(db)
