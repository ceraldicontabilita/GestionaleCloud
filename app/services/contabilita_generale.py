"""
================================================================================
RAGIONERIA GENERALE APPLICATA - MANUALE OPERATIVO ERP
================================================================================

Questo modulo contiene la logica contabile completa secondo:
- Principi Contabili OIC (aggiornamenti 2024)
- Codice Civile italiano
- Normativa fiscale IVA/IRES/IRAP
- Best practices contabilità aziendale

INDICE:
1. Principi Fondamentali
2. Piano dei Conti
3. Partita Doppia - Scritture Base
4. Ciclo Acquisti
5. Ciclo Vendite  
6. Gestione IVA
7. Ratei e Risconti
8. Ammortamenti
9. TFR e Fondi
10. Chiusura Esercizio
11. Operazioni Particolari

================================================================================
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional
from uuid import uuid4
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# 1. PRINCIPI FONDAMENTALI OIC
# ============================================================================

class PrincipiOIC:
    """
    Principi contabili OIC - Postulati di bilancio
    Riferimento: OIC 11 - Finalità e postulati del bilancio d'esercizio
    """
    
    PRUDENZA = """
    Principio di PRUDENZA (OIC 11):
    - Utili inclusi solo se REALIZZATI alla data di chiusura
    - Perdite e rischi inclusi anche se SOLO PRESUNTI
    - Non sopravvalutare attività/ricavi
    - Non sottovalutare passività/costi
    """
    
    COMPETENZA = """
    Principio di COMPETENZA ECONOMICA (OIC 11):
    - Costi e ricavi imputati all'esercizio di MATURAZIONE
    - Indipendentemente dalla data di incasso/pagamento
    - Uso di ratei e risconti per la corretta imputazione
    """
    
    CONTINUITA = """
    Principio di CONTINUITÀ AZIENDALE (OIC 11):
    - Bilancio redatto presumendo continuazione attività
    - Se in dubbio: informativa in nota integrativa
    - Se cessazione: criteri di liquidazione
    """
    
    PREVALENZA_SOSTANZA = """
    Principio di PREVALENZA DELLA SOSTANZA (OIC 11):
    - La sostanza economica prevale sulla forma giuridica
    - Leasing finanziario vs operativo
    - Sale and lease back
    """
    
    COSTANZA = """
    Principio di COSTANZA (OIC 11):
    - Criteri di valutazione costanti tra esercizi
    - Cambiamenti solo se giustificati e documentati
    - Effetti del cambiamento: OIC 29
    """


# ============================================================================
# 2. PIANO DEI CONTI STRUTTURATO
# ============================================================================

class CategoriaConti(Enum):
    """Macro-categorie piano dei conti secondo schema CE/SP civilistico"""
    # STATO PATRIMONIALE - ATTIVO
    IMMOBILIZZAZIONI_IMMATERIALI = "B.I"
    IMMOBILIZZAZIONI_MATERIALI = "B.II"
    IMMOBILIZZAZIONI_FINANZIARIE = "B.III"
    RIMANENZE = "C.I"
    CREDITI = "C.II"
    ATTIVITA_FINANZIARIE = "C.III"
    DISPONIBILITA_LIQUIDE = "C.IV"
    RATEI_RISCONTI_ATTIVI = "D"
    
    # STATO PATRIMONIALE - PASSIVO
    PATRIMONIO_NETTO = "A"
    FONDI_RISCHI_ONERI = "B"
    TFR = "C"
    DEBITI = "D"
    RATEI_RISCONTI_PASSIVI = "E"
    
    # CONTO ECONOMICO
    RICAVI_VENDITE = "A.1"
    VARIAZIONE_RIMANENZE = "A.2"
    ALTRI_RICAVI = "A.5"
    COSTI_MATERIE_PRIME = "B.6"
    COSTI_SERVIZI = "B.7"
    COSTI_GODIMENTO_TERZI = "B.8"
    COSTI_PERSONALE = "B.9"
    AMMORTAMENTI = "B.10"
    VARIAZIONE_RIMANENZE_MP = "B.11"
    ACCANTONAMENTI_RISCHI = "B.12"
    ALTRI_ACCANTONAMENTI = "B.13"
    ONERI_DIVERSI = "B.14"
    PROVENTI_FINANZIARI = "C.15-16"
    ONERI_FINANZIARI = "C.17"
    RETTIFICHE_ATTIVITA_FIN = "D.18-19"
    PROVENTI_ONERI_STRAORD = "E.20-21"  # Abolito ma utile per classificazione interna
    IMPOSTE = "22"


# Piano dei conti base per ristorazione/commercio
PIANO_CONTI_BASE = {
    # ===== ATTIVO =====
    "10": {"nome": "IMMOBILIZZAZIONI", "categoria": "B", "tipo": "patrimoniale"},
    "10.01": {"nome": "Terreni e fabbricati", "categoria": "B.II.1", "tipo": "patrimoniale"},
    "10.02": {"nome": "Impianti e macchinari", "categoria": "B.II.2", "tipo": "patrimoniale"},
    "10.03": {"nome": "Attrezzature", "categoria": "B.II.3", "tipo": "patrimoniale"},
    "10.04": {"nome": "Mobili e arredi", "categoria": "B.II.4", "tipo": "patrimoniale"},
    "10.05": {"nome": "Automezzi", "categoria": "B.II.4", "tipo": "patrimoniale"},
    "10.06": {"nome": "Macchine ufficio elettroniche", "categoria": "B.II.4", "tipo": "patrimoniale"},
    "10.10": {"nome": "F.do amm.to fabbricati", "categoria": "B.II.1", "tipo": "patrimoniale", "rettifica": True},
    "10.11": {"nome": "F.do amm.to impianti", "categoria": "B.II.2", "tipo": "patrimoniale", "rettifica": True},
    "10.12": {"nome": "F.do amm.to attrezzature", "categoria": "B.II.3", "tipo": "patrimoniale", "rettifica": True},
    "10.13": {"nome": "F.do amm.to mobili", "categoria": "B.II.4", "tipo": "patrimoniale", "rettifica": True},
    "10.14": {"nome": "F.do amm.to automezzi", "categoria": "B.II.4", "tipo": "patrimoniale", "rettifica": True},
    
    # Immobilizzazioni immateriali
    "11": {"nome": "IMMOBILIZZAZIONI IMMATERIALI", "categoria": "B.I", "tipo": "patrimoniale"},
    "11.01": {"nome": "Costi di impianto", "categoria": "B.I.1", "tipo": "patrimoniale"},
    "11.02": {"nome": "Avviamento", "categoria": "B.I.5", "tipo": "patrimoniale"},
    "11.03": {"nome": "Software e licenze", "categoria": "B.I.4", "tipo": "patrimoniale"},
    
    # Rimanenze
    "20": {"nome": "RIMANENZE", "categoria": "C.I", "tipo": "patrimoniale"},
    "20.01": {"nome": "Merci c/rimanenze", "categoria": "C.I.4", "tipo": "patrimoniale"},
    "20.02": {"nome": "Materie prime c/rimanenze", "categoria": "C.I.1", "tipo": "patrimoniale"},
    "20.03": {"nome": "Prodotti finiti c/rimanenze", "categoria": "C.I.4", "tipo": "patrimoniale"},
    
    # Crediti
    "30": {"nome": "CREDITI", "categoria": "C.II", "tipo": "patrimoniale"},
    "30.01": {"nome": "Crediti v/clienti", "categoria": "C.II.1", "tipo": "patrimoniale"},
    "30.02": {"nome": "Crediti v/clienti - fatture da emettere", "categoria": "C.II.1", "tipo": "patrimoniale"},
    "30.03": {"nome": "F.do svalutazione crediti", "categoria": "C.II.1", "tipo": "patrimoniale", "rettifica": True},
    "30.10": {"nome": "IVA ns/credito", "categoria": "C.II.4-bis", "tipo": "patrimoniale"},
    "30.11": {"nome": "Erario c/acconti IRES", "categoria": "C.II.4-bis", "tipo": "patrimoniale"},
    "30.12": {"nome": "Erario c/acconti IRAP", "categoria": "C.II.4-bis", "tipo": "patrimoniale"},
    "30.13": {"nome": "Erario c/ritenute subite", "categoria": "C.II.4-bis", "tipo": "patrimoniale"},
    "30.20": {"nome": "Crediti v/INPS", "categoria": "C.II.5", "tipo": "patrimoniale"},
    "30.21": {"nome": "Crediti v/INAIL", "categoria": "C.II.5", "tipo": "patrimoniale"},
    "30.30": {"nome": "Anticipi a fornitori", "categoria": "C.II.5", "tipo": "patrimoniale"},
    
    # Disponibilità liquide
    "40": {"nome": "DISPONIBILITA' LIQUIDE", "categoria": "C.IV", "tipo": "patrimoniale"},
    "40.01": {"nome": "Cassa", "categoria": "C.IV.3", "tipo": "patrimoniale"},
    "40.02": {"nome": "Banca c/c", "categoria": "C.IV.1", "tipo": "patrimoniale"},
    "40.03": {"nome": "Banca c/c (secondo conto)", "categoria": "C.IV.1", "tipo": "patrimoniale"},
    "40.10": {"nome": "Assegni", "categoria": "C.IV.2", "tipo": "patrimoniale"},
    "40.11": {"nome": "Valori bollati", "categoria": "C.IV.3", "tipo": "patrimoniale"},
    
    # Ratei e risconti attivi
    "45": {"nome": "RATEI E RISCONTI ATTIVI", "categoria": "D", "tipo": "patrimoniale"},
    "45.01": {"nome": "Ratei attivi", "categoria": "D", "tipo": "patrimoniale"},
    "45.02": {"nome": "Risconti attivi", "categoria": "D", "tipo": "patrimoniale"},
    
    # ===== PASSIVO =====
    # Patrimonio netto
    "50": {"nome": "PATRIMONIO NETTO", "categoria": "A", "tipo": "patrimoniale"},
    "50.01": {"nome": "Capitale sociale", "categoria": "A.I", "tipo": "patrimoniale"},
    "50.02": {"nome": "Riserva legale", "categoria": "A.IV", "tipo": "patrimoniale"},
    "50.03": {"nome": "Riserva straordinaria", "categoria": "A.VII", "tipo": "patrimoniale"},
    "50.04": {"nome": "Utile (perdita) esercizio", "categoria": "A.IX", "tipo": "patrimoniale"},
    "50.05": {"nome": "Utile (perdita) es. precedenti", "categoria": "A.VIII", "tipo": "patrimoniale"},
    
    # Fondi rischi e TFR
    "55": {"nome": "FONDI E TFR", "categoria": "B-C", "tipo": "patrimoniale"},
    "55.01": {"nome": "Fondo TFR", "categoria": "C", "tipo": "patrimoniale"},
    "55.02": {"nome": "Fondo rischi e oneri", "categoria": "B.3", "tipo": "patrimoniale"},
    "55.03": {"nome": "Fondo imposte differite", "categoria": "B.2", "tipo": "patrimoniale"},
    
    # Debiti
    "60": {"nome": "DEBITI", "categoria": "D", "tipo": "patrimoniale"},
    "60.01": {"nome": "Debiti v/fornitori", "categoria": "D.7", "tipo": "patrimoniale"},
    "60.02": {"nome": "Debiti v/fornitori - fatture da ricevere", "categoria": "D.7", "tipo": "patrimoniale"},
    "60.10": {"nome": "IVA ns/debito", "categoria": "D.12", "tipo": "patrimoniale"},
    "60.11": {"nome": "Erario c/IRES", "categoria": "D.12", "tipo": "patrimoniale"},
    "60.12": {"nome": "Erario c/IRAP", "categoria": "D.12", "tipo": "patrimoniale"},
    "60.13": {"nome": "Erario c/ritenute da versare", "categoria": "D.12", "tipo": "patrimoniale"},
    "60.14": {"nome": "Erario c/IVA", "categoria": "D.12", "tipo": "patrimoniale"},
    "60.20": {"nome": "Debiti v/INPS", "categoria": "D.13", "tipo": "patrimoniale"},
    "60.21": {"nome": "Debiti v/INAIL", "categoria": "D.13", "tipo": "patrimoniale"},
    "60.22": {"nome": "Debiti v/dipendenti", "categoria": "D.14", "tipo": "patrimoniale"},
    "60.30": {"nome": "Debiti v/banche", "categoria": "D.4", "tipo": "patrimoniale"},
    "60.31": {"nome": "Mutui passivi", "categoria": "D.4", "tipo": "patrimoniale"},
    "60.40": {"nome": "Anticipi da clienti", "categoria": "D.6", "tipo": "patrimoniale"},
    
    # Ratei e risconti passivi
    "65": {"nome": "RATEI E RISCONTI PASSIVI", "categoria": "E", "tipo": "patrimoniale"},
    "65.01": {"nome": "Ratei passivi", "categoria": "E", "tipo": "patrimoniale"},
    "65.02": {"nome": "Risconti passivi", "categoria": "E", "tipo": "patrimoniale"},
    
    # ===== CONTO ECONOMICO =====
    # Ricavi
    "70": {"nome": "RICAVI", "categoria": "A", "tipo": "economico"},
    "70.01": {"nome": "Ricavi vendite", "categoria": "A.1", "tipo": "economico"},
    "70.02": {"nome": "Ricavi prestazioni servizi", "categoria": "A.1", "tipo": "economico"},
    "70.03": {"nome": "Ricavi da corrispettivi", "categoria": "A.1", "tipo": "economico"},
    "70.10": {"nome": "Abbuoni e sconti attivi", "categoria": "A.1", "tipo": "economico", "rettifica": True},
    "70.11": {"nome": "Resi su vendite", "categoria": "A.1", "tipo": "economico", "rettifica": True},
    "70.20": {"nome": "Proventi vari", "categoria": "A.5", "tipo": "economico"},
    "70.21": {"nome": "Plusvalenze ordinarie", "categoria": "A.5", "tipo": "economico"},
    "70.22": {"nome": "Sopravvenienze attive", "categoria": "A.5", "tipo": "economico"},
    
    # Costi per acquisti
    "80": {"nome": "COSTI ACQUISTI", "categoria": "B.6", "tipo": "economico"},
    "80.01": {"nome": "Acquisti merci", "categoria": "B.6", "tipo": "economico"},
    "80.02": {"nome": "Acquisti materie prime", "categoria": "B.6", "tipo": "economico"},
    "80.03": {"nome": "Acquisti materie sussidiarie", "categoria": "B.6", "tipo": "economico"},
    "80.10": {"nome": "Abbuoni e sconti passivi", "categoria": "B.6", "tipo": "economico", "rettifica": True},
    "80.11": {"nome": "Resi su acquisti", "categoria": "B.6", "tipo": "economico", "rettifica": True},
    
    # Costi per servizi
    "81": {"nome": "COSTI SERVIZI", "categoria": "B.7", "tipo": "economico"},
    "81.01": {"nome": "Utenze (luce, gas, acqua)", "categoria": "B.7", "tipo": "economico"},
    "81.02": {"nome": "Telefono e internet", "categoria": "B.7", "tipo": "economico"},
    "81.03": {"nome": "Consulenze", "categoria": "B.7", "tipo": "economico"},
    "81.04": {"nome": "Compensi professionisti", "categoria": "B.7", "tipo": "economico"},
    "81.05": {"nome": "Manutenzioni e riparazioni", "categoria": "B.7", "tipo": "economico"},
    "81.06": {"nome": "Pulizie", "categoria": "B.7", "tipo": "economico"},
    "81.07": {"nome": "Trasporti", "categoria": "B.7", "tipo": "economico"},
    "81.08": {"nome": "Assicurazioni", "categoria": "B.7", "tipo": "economico"},
    "81.09": {"nome": "Pubblicità e promozione", "categoria": "B.7", "tipo": "economico"},
    "81.10": {"nome": "Spese bancarie", "categoria": "B.7", "tipo": "economico"},
    "81.11": {"nome": "Commissioni carte credito/POS", "categoria": "B.7", "tipo": "economico"},
    "81.12": {"nome": "Spese viaggi e trasferte", "categoria": "B.7", "tipo": "economico"},
    "81.13": {"nome": "Compensi amministratori", "categoria": "B.7", "tipo": "economico"},
    
    # Costi godimento beni terzi
    "82": {"nome": "COSTI GODIMENTO TERZI", "categoria": "B.8", "tipo": "economico"},
    "82.01": {"nome": "Affitti passivi", "categoria": "B.8", "tipo": "economico"},
    "82.02": {"nome": "Noleggi", "categoria": "B.8", "tipo": "economico"},
    "82.03": {"nome": "Leasing", "categoria": "B.8", "tipo": "economico"},
    
    # Costi del personale
    "83": {"nome": "COSTI PERSONALE", "categoria": "B.9", "tipo": "economico"},
    "83.01": {"nome": "Salari e stipendi", "categoria": "B.9.a", "tipo": "economico"},
    "83.02": {"nome": "Oneri sociali", "categoria": "B.9.b", "tipo": "economico"},
    "83.03": {"nome": "TFR", "categoria": "B.9.c", "tipo": "economico"},
    "83.04": {"nome": "Altri costi personale", "categoria": "B.9.e", "tipo": "economico"},
    
    # Ammortamenti e svalutazioni
    "84": {"nome": "AMMORTAMENTI", "categoria": "B.10", "tipo": "economico"},
    "84.01": {"nome": "Amm.to immobilizzazioni immateriali", "categoria": "B.10.a", "tipo": "economico"},
    "84.02": {"nome": "Amm.to immobilizzazioni materiali", "categoria": "B.10.b", "tipo": "economico"},
    "84.03": {"nome": "Svalutazione crediti", "categoria": "B.10.d", "tipo": "economico"},
    
    # Variazione rimanenze
    "85": {"nome": "VARIAZIONE RIMANENZE", "categoria": "B.11", "tipo": "economico"},
    "85.01": {"nome": "Variazione rimanenze merci", "categoria": "A.2/B.11", "tipo": "economico"},
    "85.02": {"nome": "Variazione rimanenze materie prime", "categoria": "B.11", "tipo": "economico"},
    
    # Accantonamenti
    "86": {"nome": "ACCANTONAMENTI", "categoria": "B.12-13", "tipo": "economico"},
    "86.01": {"nome": "Accantonamento rischi", "categoria": "B.12", "tipo": "economico"},
    "86.02": {"nome": "Altri accantonamenti", "categoria": "B.13", "tipo": "economico"},
    
    # Oneri diversi di gestione
    "87": {"nome": "ONERI DIVERSI", "categoria": "B.14", "tipo": "economico"},
    "87.01": {"nome": "IMU", "categoria": "B.14", "tipo": "economico"},
    "87.02": {"nome": "Tassa rifiuti (TARI)", "categoria": "B.14", "tipo": "economico"},
    "87.03": {"nome": "Bolli e vidimazioni", "categoria": "B.14", "tipo": "economico"},
    "87.04": {"nome": "Diritto annuale CCIAA", "categoria": "B.14", "tipo": "economico"},
    "87.05": {"nome": "Sanzioni e penalità", "categoria": "B.14", "tipo": "economico"},
    "87.06": {"nome": "Minusvalenze ordinarie", "categoria": "B.14", "tipo": "economico"},
    "87.07": {"nome": "Sopravvenienze passive", "categoria": "B.14", "tipo": "economico"},
    "87.08": {"nome": "IVA indetraibile", "categoria": "B.14", "tipo": "economico"},
    "87.09": {"nome": "Perdite su crediti", "categoria": "B.14", "tipo": "economico"},
    
    # Proventi e oneri finanziari
    "90": {"nome": "GESTIONE FINANZIARIA", "categoria": "C", "tipo": "economico"},
    "90.01": {"nome": "Interessi attivi bancari", "categoria": "C.16.d", "tipo": "economico"},
    "90.02": {"nome": "Interessi attivi da clienti", "categoria": "C.16.d", "tipo": "economico"},
    "90.03": {"nome": "Utili su cambi", "categoria": "C.16.d", "tipo": "economico"},
    "90.10": {"nome": "Interessi passivi bancari", "categoria": "C.17", "tipo": "economico"},
    "90.11": {"nome": "Interessi passivi su mutui", "categoria": "C.17", "tipo": "economico"},
    "90.12": {"nome": "Interessi passivi a fornitori", "categoria": "C.17", "tipo": "economico"},
    "90.13": {"nome": "Sconti finanziari passivi", "categoria": "C.17", "tipo": "economico"},
    "90.14": {"nome": "Perdite su cambi", "categoria": "C.17", "tipo": "economico"},
    
    # Imposte
    "95": {"nome": "IMPOSTE", "categoria": "22", "tipo": "economico"},
    "95.01": {"nome": "IRES", "categoria": "22", "tipo": "economico"},
    "95.02": {"nome": "IRAP", "categoria": "22", "tipo": "economico"},
    "95.03": {"nome": "Imposte anticipate", "categoria": "22", "tipo": "economico"},
    "95.04": {"nome": "Imposte differite", "categoria": "22", "tipo": "economico"},
}


# ============================================================================
# 3. SCRITTURE PARTITA DOPPIA - CLASSE BASE
# ============================================================================

class ScritturaContabile:
    """Rappresenta una scrittura contabile in partita doppia"""
    
    def __init__(
        self,
        data: str,
        descrizione: str,
        righe: List[Dict[str, Any]],
        documento_rif: Optional[str] = None,
        tipo_operazione: Optional[str] = None
    ):
        self.id = str(uuid4())
        self.data = data
        self.descrizione = descrizione
        self.righe = righe  # [{"conto": "...", "dare": 0, "avere": 0}]
        self.documento_rif = documento_rif
        self.tipo_operazione = tipo_operazione
        self.created_at = datetime.now(timezone.utc).isoformat()
        
        # Validazione partita doppia
        self._valida_quadratura()
    
    def _valida_quadratura(self):
        """Verifica che Totale Dare = Totale Avere"""
        totale_dare = sum(Decimal(str(r.get("dare", 0))) for r in self.righe)
        totale_avere = sum(Decimal(str(r.get("avere", 0))) for r in self.righe)
        
        if totale_dare != totale_avere:
            raise ValueError(
                f"Scrittura non quadra! Dare: {totale_dare}, Avere: {totale_avere}"
            )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "data": self.data,
            "descrizione": self.descrizione,
            "righe": self.righe,
            "documento_rif": self.documento_rif,
            "tipo_operazione": self.tipo_operazione,
            "created_at": self.created_at
        }


# ============================================================================
# 4. CICLO ACQUISTI
# ============================================================================

def scrittura_acquisto_merce(
    data: str,
    fornitore: str,
    imponibile: float,
    aliquota_iva: int = 22,
    descrizione: str = ""
) -> ScritturaContabile:
    """
    Scrittura acquisto merci con IVA
    
    DARE: Acquisti merci (costo)
    DARE: IVA a credito
    AVERE: Debiti v/fornitori
    """
    iva = round(imponibile * aliquota_iva / 100, 2)
    totale = round(imponibile + iva, 2)
    
    return ScritturaContabile(
        data=data,
        descrizione=f"Acquisto da {fornitore} - {descrizione}",
        tipo_operazione="acquisto_merce",
        righe=[
            {"conto": "80.01", "conto_nome": "Acquisti merci", "dare": imponibile, "avere": 0},
            {"conto": "30.10", "conto_nome": "IVA ns/credito", "dare": iva, "avere": 0},
            {"conto": "60.01", "conto_nome": "Debiti v/fornitori", "dare": 0, "avere": totale},
        ]
    )


def scrittura_pagamento_fornitore(
    data: str,
    fornitore: str,
    importo: float,
    mezzo_pagamento: str = "banca",  # banca, cassa, assegno
    numero_assegno: Optional[str] = None
) -> ScritturaContabile:
    """
    Scrittura pagamento a fornitore
    
    DARE: Debiti v/fornitori
    AVERE: Banca (o Cassa o Assegni)
    """
    conto_pagamento = {
        "banca": ("40.02", "Banca c/c"),
        "cassa": ("40.01", "Cassa"),
        "assegno": ("40.10", "Assegni")
    }
    
    conto, nome_conto = conto_pagamento.get(mezzo_pagamento, ("40.02", "Banca c/c"))
    desc_extra = f" - Assegno n. {numero_assegno}" if numero_assegno else ""
    
    return ScritturaContabile(
        data=data,
        descrizione=f"Pagamento a {fornitore}{desc_extra}",
        tipo_operazione="pagamento_fornitore",
        righe=[
            {"conto": "60.01", "conto_nome": "Debiti v/fornitori", "dare": importo, "avere": 0},
            {"conto": conto, "conto_nome": nome_conto, "dare": 0, "avere": importo},
        ]
    )


def scrittura_nota_credito_fornitore(
    data: str,
    fornitore: str,
    imponibile: float,
    aliquota_iva: int = 22,
    motivo: str = "reso"
) -> ScritturaContabile:
    """
    Scrittura nota di credito da fornitore (reso, sconto, abbuono)
    Art. 26 DPR 633/72
    
    DARE: Debiti v/fornitori (riduzione debito)
    AVERE: Resi su acquisti (o Abbuoni passivi)
    AVERE: IVA ns/credito (rettifica credito IVA)
    """
    iva = round(imponibile * aliquota_iva / 100, 2)
    totale = round(imponibile + iva, 2)
    
    conto_rettifica = "80.11" if motivo == "reso" else "80.10"
    nome_rettifica = "Resi su acquisti" if motivo == "reso" else "Abbuoni e sconti passivi"
    
    return ScritturaContabile(
        data=data,
        descrizione=f"Nota credito da {fornitore} per {motivo}",
        tipo_operazione="nota_credito_fornitore",
        righe=[
            {"conto": "60.01", "conto_nome": "Debiti v/fornitori", "dare": totale, "avere": 0},
            {"conto": conto_rettifica, "conto_nome": nome_rettifica, "dare": 0, "avere": imponibile},
            {"conto": "30.10", "conto_nome": "IVA ns/credito", "dare": 0, "avere": iva},
        ]
    )


# ============================================================================
# 5. CICLO VENDITE
# ============================================================================

def scrittura_vendita_merce(
    data: str,
    cliente: str,
    imponibile: float,
    aliquota_iva: int = 22,
    descrizione: str = ""
) -> ScritturaContabile:
    """
    Scrittura vendita con fattura
    
    DARE: Crediti v/clienti
    AVERE: Ricavi vendite
    AVERE: IVA ns/debito
    """
    iva = round(imponibile * aliquota_iva / 100, 2)
    totale = round(imponibile + iva, 2)
    
    return ScritturaContabile(
        data=data,
        descrizione=f"Vendita a {cliente} - {descrizione}",
        tipo_operazione="vendita_merce",
        righe=[
            {"conto": "30.01", "conto_nome": "Crediti v/clienti", "dare": totale, "avere": 0},
            {"conto": "70.01", "conto_nome": "Ricavi vendite", "dare": 0, "avere": imponibile},
            {"conto": "60.10", "conto_nome": "IVA ns/debito", "dare": 0, "avere": iva},
        ]
    )


def scrittura_corrispettivo(
    data: str,
    totale_ivato: float,
    aliquota_iva: int = 10,  # Ristorazione usa spesso 10%
    incasso_contanti: float = 0,
    incasso_pos: float = 0
) -> ScritturaContabile:
    """
    Scrittura corrispettivo giornaliero (scontrino/ricevuta fiscale)
    
    DARE: Cassa (contanti)
    DARE: Banca (POS)
    AVERE: Ricavi da corrispettivi (scorporati)
    AVERE: IVA ns/debito
    
    Nota: L'IVA è inclusa nel totale e va scorporata
    """
    # Scorporo IVA
    imponibile = round(totale_ivato / (1 + aliquota_iva / 100), 2)
    iva = round(totale_ivato - imponibile, 2)
    
    righe = []
    
    if incasso_contanti > 0:
        righe.append({"conto": "40.01", "conto_nome": "Cassa", "dare": incasso_contanti, "avere": 0})
    
    if incasso_pos > 0:
        righe.append({"conto": "40.02", "conto_nome": "Banca c/c", "dare": incasso_pos, "avere": 0})
    
    # Se non specificato, tutto in cassa
    if incasso_contanti == 0 and incasso_pos == 0:
        righe.append({"conto": "40.01", "conto_nome": "Cassa", "dare": totale_ivato, "avere": 0})
    
    righe.extend([
        {"conto": "70.03", "conto_nome": "Ricavi da corrispettivi", "dare": 0, "avere": imponibile},
        {"conto": "60.10", "conto_nome": "IVA ns/debito", "dare": 0, "avere": iva},
    ])
    
    return ScritturaContabile(
        data=data,
        descrizione=f"Corrispettivo del {data}",
        tipo_operazione="corrispettivo",
        righe=righe
    )


def scrittura_fattura_su_corrispettivo(
    data: str,
    cliente: str,
    imponibile: float,
    aliquota_iva: int = 10,
    corrispettivo_data: str = None
) -> Dict[str, Any]:
    """
    CASO SPECIALE: Fattura emessa su richiesta cliente DOPO lo scontrino
    
    PROBLEMA: L'IVA è già stata assolta con il corrispettivo.
    Se conteggiamo anche la fattura, l'IVA viene duplicata!
    
    SOLUZIONE:
    1. Emettere fattura per documentare l'operazione al cliente
    2. Marcare la fattura come "già in corrispettivo"
    3. NON conteggiare questa fattura nel calcolo IVA periodica
    4. Lo scontrino originale rimane nel registro corrispettivi
    """
    iva = round(imponibile * aliquota_iva / 100, 2)
    totale = round(imponibile + iva, 2)
    
    return {
        "tipo": "fattura_su_corrispettivo",
        "data": data,
        "cliente": cliente,
        "imponibile": imponibile,
        "aliquota_iva": aliquota_iva,
        "iva": iva,
        "totale": totale,
        "corrispettivo_data": corrispettivo_data,
        "inclusa_in_corrispettivo": True,  # FLAG CRITICO
        "escludere_da_liquidazione_iva": True,  # FLAG CRITICO
        "nota": "Fattura emessa su richiesta cliente. IVA già assolta con corrispettivo.",
        "registrazione_contabile": None,  # Nessuna scrittura contabile aggiuntiva!
        "solo_documento_fiscale": True
    }


def scrittura_incasso_cliente(
    data: str,
    cliente: str,
    importo: float,
    mezzo_incasso: str = "banca"  # banca, cassa, assegno
) -> ScritturaContabile:
    """
    Scrittura incasso da cliente
    
    DARE: Banca (o Cassa o Assegni)
    AVERE: Crediti v/clienti
    """
    conto_incasso = {
        "banca": ("40.02", "Banca c/c"),
        "cassa": ("40.01", "Cassa"),
        "assegno": ("40.10", "Assegni")
    }
    
    conto, nome_conto = conto_incasso.get(mezzo_incasso, ("40.02", "Banca c/c"))
    
    return ScritturaContabile(
        data=data,
        descrizione=f"Incasso da {cliente}",
        tipo_operazione="incasso_cliente",
        righe=[
            {"conto": conto, "conto_nome": nome_conto, "dare": importo, "avere": 0},
            {"conto": "30.01", "conto_nome": "Crediti v/clienti", "dare": 0, "avere": importo},
        ]
    )


def scrittura_nota_credito_cliente(
    data: str,
    cliente: str,
    imponibile: float,
    aliquota_iva: int = 22,
    motivo: str = "reso"
) -> ScritturaContabile:
    """
    Scrittura nota di credito a cliente (reso, sconto, abbuono)
    Art. 26 DPR 633/72
    
    DARE: Resi su vendite (o Abbuoni attivi)
    DARE: IVA ns/debito (rettifica debito IVA)
    AVERE: Crediti v/clienti (riduzione credito)
    """
    iva = round(imponibile * aliquota_iva / 100, 2)
    totale = round(imponibile + iva, 2)
    
    conto_rettifica = "70.11" if motivo == "reso" else "70.10"
    nome_rettifica = "Resi su vendite" if motivo == "reso" else "Abbuoni e sconti attivi"
    
    return ScritturaContabile(
        data=data,
        descrizione=f"Nota credito a {cliente} per {motivo}",
        tipo_operazione="nota_credito_cliente",
        righe=[
            {"conto": conto_rettifica, "conto_nome": nome_rettifica, "dare": imponibile, "avere": 0},
            {"conto": "60.10", "conto_nome": "IVA ns/debito", "dare": iva, "avere": 0},
            {"conto": "30.01", "conto_nome": "Crediti v/clienti", "dare": 0, "avere": totale},
        ]
    )


# ============================================================================
# 6. GESTIONE IVA
# ============================================================================

class LiquidazioneIVA:
    """
    Liquidazione IVA periodica secondo DPR 633/72
    
    Periodicità:
    - Mensile: se volume d'affari > €400.000 (servizi) o €700.000 (altre attività)
    - Trimestrale: sotto le soglie
    
    Scadenze versamento:
    - Mensile: 16 del mese successivo
    - Trimestrale: 16 del secondo mese successivo al trimestre
    - Acconto dicembre: 27 dicembre
    """
    
    @staticmethod
    def calcola_liquidazione(
        iva_debito: float,
        iva_credito: float,
        credito_periodo_precedente: float = 0
    ) -> Dict[str, float]:
        """
        Calcola la liquidazione IVA del periodo
        
        IVA a debito - IVA a credito - Credito precedente = Saldo
        """
        saldo = iva_debito - iva_credito - credito_periodo_precedente
        
        if saldo > 0:
            return {
                "iva_debito": iva_debito,
                "iva_credito": iva_credito,
                "credito_precedente": credito_periodo_precedente,
                "iva_da_versare": round(saldo, 2),
                "credito_da_riportare": 0
            }
        else:
            return {
                "iva_debito": iva_debito,
                "iva_credito": iva_credito,
                "credito_precedente": credito_periodo_precedente,
                "iva_da_versare": 0,
                "credito_da_riportare": round(abs(saldo), 2)
            }
    
    @staticmethod
    def scrittura_versamento_iva(data: str, importo: float) -> ScritturaContabile:
        """
        Scrittura versamento IVA periodica
        
        DARE: Erario c/IVA
        AVERE: Banca c/c
        """
        return ScritturaContabile(
            data=data,
            descrizione="Versamento IVA periodica",
            tipo_operazione="versamento_iva",
            righe=[
                {"conto": "60.14", "conto_nome": "Erario c/IVA", "dare": importo, "avere": 0},
                {"conto": "40.02", "conto_nome": "Banca c/c", "dare": 0, "avere": importo},
            ]
        )
    
    @staticmethod
    def scrittura_giroconto_iva(
        data: str,
        iva_debito: float,
        iva_credito: float
    ) -> ScritturaContabile:
        """
        Giroconto IVA fine periodo per chiusura conti IVA
        
        DARE: IVA ns/debito (chiusura)
        AVERE: IVA ns/credito (chiusura)
        AVERE: Erario c/IVA (debito netto) oppure DARE se credito
        """
        saldo = iva_debito - iva_credito
        
        righe = [
            {"conto": "60.10", "conto_nome": "IVA ns/debito", "dare": iva_debito, "avere": 0},
            {"conto": "30.10", "conto_nome": "IVA ns/credito", "dare": 0, "avere": iva_credito},
        ]
        
        if saldo > 0:
            righe.append({"conto": "60.14", "conto_nome": "Erario c/IVA", "dare": 0, "avere": saldo})
        else:
            righe.append({"conto": "60.14", "conto_nome": "Erario c/IVA", "dare": abs(saldo), "avere": 0})
        
        return ScritturaContabile(
            data=data,
            descrizione="Giroconto chiusura IVA periodica",
            tipo_operazione="giroconto_iva",
            righe=righe
        )


# ============================================================================
# 7. RATEI E RISCONTI
# ============================================================================

def calcola_rateo_risconto(
    importo_totale: float,
    data_inizio: str,
    data_fine: str,
    data_bilancio: str
) -> Dict[str, Any]:
    """
    Calcola rateo o risconto in base alle date
    
    Principio di competenza economica:
    - RATEO: quota maturata ma non ancora incassata/pagata
    - RISCONTO: quota pagata/incassata ma di competenza futura
    """
    from datetime import datetime
    
    inizio = datetime.strptime(data_inizio, "%Y-%m-%d").date()
    fine = datetime.strptime(data_fine, "%Y-%m-%d").date()
    bilancio = datetime.strptime(data_bilancio, "%Y-%m-%d").date()
    
    giorni_totali = (fine - inizio).days + 1
    importo_giornaliero = importo_totale / giorni_totali
    
    if bilancio < inizio:
        # Tutto di competenza futura
        return {
            "tipo": "risconto",
            "importo": importo_totale,
            "giorni_competenza_futura": giorni_totali
        }
    elif bilancio >= fine:
        # Tutto di competenza passata
        return {
            "tipo": None,
            "importo": 0,
            "nota": "Interamente di competenza dell'esercizio"
        }
    else:
        # Parte di competenza, parte futura
        giorni_competenza = (bilancio - inizio).days + 1
        giorni_futuri = (fine - bilancio).days
        
        quota_competenza = round(importo_giornaliero * giorni_competenza, 2)
        quota_futura = round(importo_giornaliero * giorni_futuri, 2)
        
        return {
            "tipo": "risconto",
            "importo": quota_futura,
            "quota_competenza": quota_competenza,
            "giorni_competenza": giorni_competenza,
            "giorni_futuri": giorni_futuri
        }


def scrittura_risconto_attivo(
    data: str,
    importo: float,
    descrizione: str
) -> ScritturaContabile:
    """
    Scrittura risconto attivo (es: assicurazione pagata in anticipo)
    
    DARE: Risconti attivi
    AVERE: Costo (es: Assicurazioni)
    """
    return ScritturaContabile(
        data=data,
        descrizione=f"Risconto attivo - {descrizione}",
        tipo_operazione="risconto_attivo",
        righe=[
            {"conto": "45.02", "conto_nome": "Risconti attivi", "dare": importo, "avere": 0},
            {"conto": "81.08", "conto_nome": "Assicurazioni", "dare": 0, "avere": importo},
        ]
    )


def scrittura_rateo_passivo(
    data: str,
    importo: float,
    descrizione: str
) -> ScritturaContabile:
    """
    Scrittura rateo passivo (es: interessi su mutuo maturati non pagati)
    
    DARE: Interessi passivi (costo)
    AVERE: Ratei passivi
    """
    return ScritturaContabile(
        data=data,
        descrizione=f"Rateo passivo - {descrizione}",
        tipo_operazione="rateo_passivo",
        righe=[
            {"conto": "90.11", "conto_nome": "Interessi passivi su mutui", "dare": importo, "avere": 0},
            {"conto": "65.01", "conto_nome": "Ratei passivi", "dare": 0, "avere": importo},
        ]
    )


# ============================================================================
# 8. AMMORTAMENTI
# ============================================================================

# Coefficienti ammortamento fiscali (DM 31/12/1988 e succ. mod.)
COEFFICIENTI_AMMORTAMENTO = {
    "fabbricati_industriali": 3,
    "fabbricati_commerciali": 3,
    "impianti_generici": 10,
    "impianti_specifici": 12,
    "attrezzature": 15,
    "mobili_arredi": 12,
    "macchine_ufficio": 20,
    "automezzi": 20,
    "autovetture": 25,
    "software": 20,
    "avviamento": 5.56,  # 18 anni
    "costi_impianto": 20,
}


def calcola_ammortamento(
    valore_originario: float,
    fondo_ammortamento_precedente: float,
    categoria: str,
    anno_acquisto: int,
    anno_corrente: int
) -> Dict[str, Any]:
    """
    Calcola la quota di ammortamento annuale
    
    OIC 16: L'ammortamento deve riflettere la residua possibilità
    di utilizzazione del bene.
    
    Primo anno: quota dimezzata (prassi fiscale)
    """
    coeff = COEFFICIENTI_AMMORTAMENTO.get(categoria, 10)
    
    # Valore residuo
    valore_residuo = valore_originario - fondo_ammortamento_precedente
    
    if valore_residuo <= 0:
        return {
            "quota_ammortamento": 0,
            "ammortamento_completo": True,
            "valore_residuo": 0
        }
    
    # Calcolo quota
    quota_ordinaria = valore_originario * coeff / 100
    
    # Primo anno: dimezzata
    if anno_acquisto == anno_corrente:
        quota = quota_ordinaria / 2
    else:
        quota = quota_ordinaria
    
    # Non superare il valore residuo
    quota = min(quota, valore_residuo)
    
    return {
        "valore_originario": valore_originario,
        "fondo_precedente": fondo_ammortamento_precedente,
        "coefficiente": coeff,
        "quota_ammortamento": round(quota, 2),
        "nuovo_fondo": round(fondo_ammortamento_precedente + quota, 2),
        "valore_residuo": round(valore_residuo - quota, 2),
        "ammortamento_completo": (valore_residuo - quota) <= 0
    }


def scrittura_ammortamento(
    data: str,
    categoria_bene: str,
    quota: float,
    conto_ammortamento: str,
    conto_fondo: str
) -> ScritturaContabile:
    """
    Scrittura ammortamento
    
    DARE: Ammortamento ... (costo CE)
    AVERE: Fondo ammortamento ... (rettifica SP)
    """
    return ScritturaContabile(
        data=data,
        descrizione=f"Ammortamento {categoria_bene}",
        tipo_operazione="ammortamento",
        righe=[
            {"conto": conto_ammortamento, "conto_nome": f"Amm.to {categoria_bene}", "dare": quota, "avere": 0},
            {"conto": conto_fondo, "conto_nome": f"F.do amm.to {categoria_bene}", "dare": 0, "avere": quota},
        ]
    )


# ============================================================================
# 9. TFR E FONDI
# ============================================================================

def calcola_tfr_annuale(
    retribuzione_annua_lorda: float,
    anni_servizio: int = 1
) -> Dict[str, Any]:
    """
    Calcolo TFR secondo art. 2120 c.c.
    
    Formula: Retribuzione annua / 13.5
    Rivalutazione: ISTAT + 1.5%
    """
    quota_annuale = retribuzione_annua_lorda / 13.5
    
    return {
        "retribuzione_annua": retribuzione_annua_lorda,
        "quota_tfr_annuale": round(quota_annuale, 2),
        "divisore": 13.5,
        "nota": "Da rivalutare annualmente con indice ISTAT + 1.5%"
    }


def scrittura_accantonamento_tfr(
    data: str,
    importo: float
) -> ScritturaContabile:
    """
    Scrittura accantonamento TFR annuale
    
    DARE: TFR (costo B.9.c)
    AVERE: Fondo TFR (passivo)
    """
    return ScritturaContabile(
        data=data,
        descrizione="Accantonamento TFR esercizio",
        tipo_operazione="accantonamento_tfr",
        righe=[
            {"conto": "83.03", "conto_nome": "TFR", "dare": importo, "avere": 0},
            {"conto": "55.01", "conto_nome": "Fondo TFR", "dare": 0, "avere": importo},
        ]
    )


def scrittura_pagamento_tfr(
    data: str,
    dipendente: str,
    importo_lordo: float,
    ritenuta_fiscale: float
) -> ScritturaContabile:
    """
    Scrittura pagamento TFR a dipendente
    
    DARE: Fondo TFR
    AVERE: Banca (netto)
    AVERE: Erario c/ritenute (ritenuta fiscale)
    """
    netto = importo_lordo - ritenuta_fiscale
    
    return ScritturaContabile(
        data=data,
        descrizione=f"Liquidazione TFR a {dipendente}",
        tipo_operazione="pagamento_tfr",
        righe=[
            {"conto": "55.01", "conto_nome": "Fondo TFR", "dare": importo_lordo, "avere": 0},
            {"conto": "40.02", "conto_nome": "Banca c/c", "dare": 0, "avere": netto},
            {"conto": "60.13", "conto_nome": "Erario c/ritenute", "dare": 0, "avere": ritenuta_fiscale},
        ]
    )


# ============================================================================
# 10. CHIUSURA ESERCIZIO
# ============================================================================

class ChiusuraEsercizio:
    """
    Operazioni di chiusura annuale secondo OIC e Codice Civile
    
    Sequenza operazioni:
    1. Scritture di assestamento (ratei, risconti, ammortamenti)
    2. Rilevazione rimanenze finali
    3. Accantonamenti (TFR, rischi, svalutazioni)
    4. Calcolo imposte
    5. Chiusura conti economici a conto economico
    6. Chiusura conto economico a stato patrimoniale
    7. Epilogo utile/perdita
    """
    
    @staticmethod
    def scrittura_rimanenze_finali(
        data: str,
        rimanenze_merci: float,
        rimanenze_materie: float = 0
    ) -> List[ScritturaContabile]:
        """
        Rilevazione rimanenze finali
        
        DARE: Merci c/rimanenze (SP)
        AVERE: Variazione rimanenze (CE)
        """
        scritture = []
        
        if rimanenze_merci > 0:
            scritture.append(ScritturaContabile(
                data=data,
                descrizione="Rimanenze finali merci",
                tipo_operazione="rimanenze_finali",
                righe=[
                    {"conto": "20.01", "conto_nome": "Merci c/rimanenze", "dare": rimanenze_merci, "avere": 0},
                    {"conto": "85.01", "conto_nome": "Variazione rimanenze merci", "dare": 0, "avere": rimanenze_merci},
                ]
            ))
        
        if rimanenze_materie > 0:
            scritture.append(ScritturaContabile(
                data=data,
                descrizione="Rimanenze finali materie prime",
                tipo_operazione="rimanenze_finali",
                righe=[
                    {"conto": "20.02", "conto_nome": "Materie prime c/rimanenze", "dare": rimanenze_materie, "avere": 0},
                    {"conto": "85.02", "conto_nome": "Variazione rimanenze materie", "dare": 0, "avere": rimanenze_materie},
                ]
            ))
        
        return scritture
    
    @staticmethod
    def calcola_imposte(
        utile_ante_imposte: float,
        aliquota_ires: float = 24,
        aliquota_irap: float = 3.9
    ) -> Dict[str, float]:
        """
        Calcolo IRES e IRAP
        
        IRES: 24% dell'imponibile
        IRAP: 3.9% del valore della produzione (semplificato)
        """
        ires = max(0, utile_ante_imposte * aliquota_ires / 100)
        irap = max(0, utile_ante_imposte * aliquota_irap / 100)
        
        return {
            "utile_ante_imposte": utile_ante_imposte,
            "ires": round(ires, 2),
            "irap": round(irap, 2),
            "totale_imposte": round(ires + irap, 2),
            "utile_netto": round(utile_ante_imposte - ires - irap, 2)
        }
    
    @staticmethod
    def scrittura_imposte(
        data: str,
        ires: float,
        irap: float
    ) -> ScritturaContabile:
        """
        Rilevazione imposte d'esercizio
        
        DARE: IRES (costo)
        DARE: IRAP (costo)
        AVERE: Erario c/IRES (debito)
        AVERE: Erario c/IRAP (debito)
        """
        return ScritturaContabile(
            data=data,
            descrizione="Rilevazione imposte esercizio",
            tipo_operazione="imposte_esercizio",
            righe=[
                {"conto": "95.01", "conto_nome": "IRES", "dare": ires, "avere": 0},
                {"conto": "95.02", "conto_nome": "IRAP", "dare": irap, "avere": 0},
                {"conto": "60.11", "conto_nome": "Erario c/IRES", "dare": 0, "avere": ires},
                {"conto": "60.12", "conto_nome": "Erario c/IRAP", "dare": 0, "avere": irap},
            ]
        )


# ============================================================================
# 11. OPERAZIONI PARTICOLARI
# ============================================================================

class OperazioniParticolari:
    """
    Gestione operazioni contabili speciali
    """
    
    @staticmethod
    def storno_totale(
        scrittura_originale: Dict[str, Any],
        data_storno: str,
        motivo: str
    ) -> ScritturaContabile:
        """
        Storno totale di una scrittura
        Inverte dare/avere di ogni riga
        """
        righe_storno = []
        for riga in scrittura_originale.get("righe", []):
            righe_storno.append({
                "conto": riga["conto"],
                "conto_nome": riga.get("conto_nome", ""),
                "dare": riga.get("avere", 0),
                "avere": riga.get("dare", 0)
            })
        
        return ScritturaContabile(
            data=data_storno,
            descrizione=f"STORNO: {scrittura_originale.get('descrizione', '')} - {motivo}",
            tipo_operazione="storno",
            documento_rif=scrittura_originale.get("id"),
            righe=righe_storno
        )
    
    @staticmethod
    def cessione_bene_ammortizzabile(
        data: str,
        descrizione_bene: str,
        valore_originario: float,
        fondo_ammortamento: float,
        prezzo_cessione: float
    ) -> ScritturaContabile:
        """
        Cessione bene strumentale
        
        Calcola plusvalenza/minusvalenza
        """
        valore_netto = valore_originario - fondo_ammortamento
        
        if prezzo_cessione > valore_netto:
            # PLUSVALENZA
            plusvalenza = prezzo_cessione - valore_netto
            return ScritturaContabile(
                data=data,
                descrizione=f"Cessione {descrizione_bene} con plusvalenza",
                tipo_operazione="cessione_bene",
                righe=[
                    {"conto": "40.02", "conto_nome": "Banca c/c", "dare": prezzo_cessione, "avere": 0},
                    {"conto": "10.12", "conto_nome": "F.do amm.to", "dare": fondo_ammortamento, "avere": 0},
                    {"conto": "10.03", "conto_nome": "Bene", "dare": 0, "avere": valore_originario},
                    {"conto": "70.21", "conto_nome": "Plusvalenze", "dare": 0, "avere": plusvalenza},
                ]
            )
        else:
            # MINUSVALENZA
            minusvalenza = valore_netto - prezzo_cessione
            return ScritturaContabile(
                data=data,
                descrizione=f"Cessione {descrizione_bene} con minusvalenza",
                tipo_operazione="cessione_bene",
                righe=[
                    {"conto": "40.02", "conto_nome": "Banca c/c", "dare": prezzo_cessione, "avere": 0},
                    {"conto": "10.12", "conto_nome": "F.do amm.to", "dare": fondo_ammortamento, "avere": 0},
                    {"conto": "87.06", "conto_nome": "Minusvalenze", "dare": minusvalenza, "avere": 0},
                    {"conto": "10.03", "conto_nome": "Bene", "dare": 0, "avere": valore_originario},
                ]
            )
    
    @staticmethod
    def svalutazione_crediti(
        data: str,
        importo_svalutazione: float,
        motivo: str = "rischio inesigibilità"
    ) -> ScritturaContabile:
        """
        Svalutazione crediti per rischio inesigibilità
        
        DARE: Svalutazione crediti (costo)
        AVERE: Fondo svalutazione crediti (rettifica attivo)
        """
        return ScritturaContabile(
            data=data,
            descrizione=f"Svalutazione crediti - {motivo}",
            tipo_operazione="svalutazione_crediti",
            righe=[
                {"conto": "84.03", "conto_nome": "Svalutazione crediti", "dare": importo_svalutazione, "avere": 0},
                {"conto": "30.03", "conto_nome": "F.do svalutazione crediti", "dare": 0, "avere": importo_svalutazione},
            ]
        )
    
    @staticmethod
    def perdita_su_crediti(
        data: str,
        cliente: str,
        importo: float
    ) -> ScritturaContabile:
        """
        Perdita su crediti (credito definitivamente inesigibile)
        
        Se c'è fondo: usa il fondo
        Se non c'è: direttamente a perdite su crediti
        """
        return ScritturaContabile(
            data=data,
            descrizione=f"Perdita su crediti - {cliente}",
            tipo_operazione="perdita_crediti",
            righe=[
                {"conto": "87.09", "conto_nome": "Perdite su crediti", "dare": importo, "avere": 0},
                {"conto": "30.01", "conto_nome": "Crediti v/clienti", "dare": 0, "avere": importo},
            ]
        )


# ============================================================================
# EXPORT FUNZIONI PRINCIPALI
# ============================================================================

__all__ = [
    # Principi
    "PrincipiOIC",
    "CategoriaConti",
    "PIANO_CONTI_BASE",
    
    # Scritture base
    "ScritturaContabile",
    
    # Ciclo acquisti
    "scrittura_acquisto_merce",
    "scrittura_pagamento_fornitore",
    "scrittura_nota_credito_fornitore",
    
    # Ciclo vendite
    "scrittura_vendita_merce",
    "scrittura_corrispettivo",
    "scrittura_fattura_su_corrispettivo",
    "scrittura_incasso_cliente",
    "scrittura_nota_credito_cliente",
    
    # IVA
    "LiquidazioneIVA",
    
    # Assestamento
    "calcola_rateo_risconto",
    "scrittura_risconto_attivo",
    "scrittura_rateo_passivo",
    "calcola_ammortamento",
    "scrittura_ammortamento",
    "COEFFICIENTI_AMMORTAMENTO",
    
    # TFR
    "calcola_tfr_annuale",
    "scrittura_accantonamento_tfr",
    "scrittura_pagamento_tfr",
    
    # Chiusura
    "ChiusuraEsercizio",
    
    # Operazioni particolari
    "OperazioniParticolari",
]
