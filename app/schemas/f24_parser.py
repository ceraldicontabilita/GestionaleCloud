"""
Sistema Completo di Parsing e Matching F24
Gestisce il matching movimento bancario <-> F24 salvato
Legge i codici tributo dall'XML/PDF F24
Genera scritture contabili splittate per ogni codice tributo
"""

import xml.etree.ElementTree as ET
from typing import Dict, List, Optional
from datetime import datetime, date
import re

from schemas.accounting_rules import F24_ERARIO_CODES, F24_INPS_CODES


# ============================================================================
# STRUTTURA F24 XML - NODI STANDARD
# ============================================================================

F24_XML_STRUCTURE = {
    "sezione_erario": {
        "path": ".//SezioneErario/ElementoPagamento",
        "fields": {
            "codice_tributo": "CodiceTributo",
            "anno_riferimento": "AnnoRiferimento",
            "rateazione": "Rateazione",
            "importo_debito": "ImportoDebito",
            "importo_credito": "ImportoCredito"
        }
    },
    "sezione_inps": {
        "path": ".//SezioneINPS/ElementoPagamento",
        "fields": {
            "codice_tributo": "CodiceTributo",
            "matricola_inps": "MatricolaINPS",
            "causale_contributo": "CausaleContributo",
            "anno_riferimento": "AnnoRiferimento",
            "rateazione": "Rateazione",
            "importo_debito": "ImportoDebito",
            "importo_credito": "ImportoCredito"
        }
    },
    "sezione_regioni": {
        "path": ".//SezioneRegioni/ElementoPagamento",
        "fields": {
            "codice_tributo": "CodiceTributo",
            "anno_riferimento": "AnnoRiferimento",
            "importo_debito": "ImportoDebito",
            "importo_credito": "ImportoCredito"
        }
    }
}


# ============================================================================
# CLASSE F24 ELEMENT
# ============================================================================

class F24Element:
    """Rappresenta un singolo elemento di pagamento dentro l'F24"""
    
    def __init__(self, sezione: str, codice_tributo: str, importo: float, 
                 anno_riferimento: Optional[str] = None,
                 rateazione: Optional[str] = None,
                 matricola_inps: Optional[str] = None,
                 causale_contributo: Optional[str] = None):
        self.sezione = sezione  # 'erario', 'inps', 'regioni'
        self.codice_tributo = codice_tributo
        self.importo = importo
        self.anno_riferimento = anno_riferimento
        self.rateazione = rateazione
        self.matricola_inps = matricola_inps
        self.causale_contributo = causale_contributo
        
        # Determina conto contabile e descrizione
        self.conto_contabile = None
        self.descrizione_tributo = None
        self.categoria = None
        self._determina_conto()
    
    def _determina_conto(self):
        """Determina il conto contabile basandosi sul codice tributo"""
        if self.sezione == "erario":
            if self.codice_tributo in F24_ERARIO_CODES:
                info = F24_ERARIO_CODES[self.codice_tributo]
                self.conto_contabile = info["conto"]
                self.descrizione_tributo = info["descrizione"]
                self.categoria = info["tipo"]
            else:
                # Codice erario non riconosciuto
                self.conto_contabile = "4.3.02"  # Imposte generico
                self.descrizione_tributo = f"Tributo erario {self.codice_tributo} (non catalogato)"
                self.categoria = "imposte"
        
        elif self.sezione == "inps":
            if self.codice_tributo in F24_INPS_CODES:
                info = F24_INPS_CODES[self.codice_tributo]
                self.conto_contabile = info["conto"]
                self.descrizione_tributo = info["descrizione"]
                self.categoria = info["tipo"]
            else:
                # Codice INPS non riconosciuto
                self.conto_contabile = "4.2.01"  # Costo personale generico
                self.descrizione_tributo = f"Contributo INPS {self.codice_tributo} (non catalogato)"
                self.categoria = "costo_personale"
        
        else:
            # Altre sezioni (regioni, etc)
            self.conto_contabile = "4.3.02"
            self.descrizione_tributo = f"Tributo {self.sezione} - {self.codice_tributo}"
            self.categoria = "imposte"
    
    def to_dict(self):
        return {
            "sezione": self.sezione,
            "codice_tributo": self.codice_tributo,
            "importo": self.importo,
            "anno_riferimento": self.anno_riferimento,
            "rateazione": self.rateazione,
            "matricola_inps": self.matricola_inps,
            "causale_contributo": self.causale_contributo,
            "conto_contabile": self.conto_contabile,
            "descrizione_tributo": self.descrizione_tributo,
            "categoria": self.categoria
        }


# ============================================================================
# CLASSE F24 DOCUMENT
# ============================================================================

class F24Document:
    """Rappresenta un documento F24 completo con tutti i suoi elementi"""
    
    def __init__(self, f24_id: str, data_pagamento: Optional[str] = None):
        self.f24_id = f24_id
        self.data_pagamento = data_pagamento
        self.elementi: List[F24Element] = []
        self.importo_totale = 0.0
    
    def aggiungi_elemento(self, elemento: F24Element):
        """Aggiunge un elemento di pagamento"""
        self.elementi.append(elemento)
        self.importo_totale += elemento.importo
    
    def get_elementi_per_sezione(self, sezione: str) -> List[F24Element]:
        """Ritorna tutti gli elementi di una sezione specifica"""
        return [e for e in self.elementi if e.sezione == sezione]
    
    def get_elementi_per_categoria(self, categoria: str) -> List[F24Element]:
        """Raggruppa elementi per categoria contabile (imposte, contributi, etc)"""
        return [e for e in self.elementi if e.categoria == categoria]
    
    def genera_scrittura_contabile(self) -> Dict:
        """
        Genera la scrittura contabile completa in partita doppia
        
        Returns:
            Dict con righe della scrittura e verifica quadratura
        """
        righe = []
        
        # Per ogni elemento, crea una riga DARE al conto specifico
        for elemento in self.elementi:
            righe.append({
                "conto": elemento.conto_contabile,
                "dare": elemento.importo,
                "avere": 0,
                "descrizione": f"{elemento.descrizione_tributo} - Anno {elemento.anno_riferimento or 'N/D'}",
                "codice_tributo": elemento.codice_tributo,
                "sezione_f24": elemento.sezione
            })
        
        # Unica riga AVERE alla banca per l'importo totale
        righe.append({
            "conto": "1.2.02",
            "dare": 0,
            "avere": self.importo_totale,
            "descrizione": f"Pagamento F24 - {self.data_pagamento or 'N/D'}",
            "codice_tributo": None,
            "sezione_f24": None
        })
        
        # Verifica quadratura
        totale_dare = sum(r["dare"] for r in righe)
        totale_avere = sum(r["avere"] for r in righe)
        quadra = abs(totale_dare - totale_avere) < 0.01
        
        return {
            "f24_id": self.f24_id,
            "data_pagamento": self.data_pagamento,
            "importo_totale": self.importo_totale,
            "numero_elementi": len(self.elementi),
            "righe": righe,
            "verifica_quadratura": {
                "quadra": quadra,
                "totale_dare": totale_dare,
                "totale_avere": totale_avere,
                "differenza": abs(totale_dare - totale_avere)
            }
        }
    
    def to_dict(self):
        return {
            "f24_id": self.f24_id,
            "data_pagamento": self.data_pagamento,
            "importo_totale": self.importo_totale,
            "numero_elementi": len(self.elementi),
            "elementi": [e.to_dict() for e in self.elementi]
        }


# ============================================================================
# PARSER F24 XML
# ============================================================================

def parse_f24_xml(xml_content: str, f24_id: str) -> F24Document:
    """
    Parsa il contenuto XML di un F24 ed estrae tutti gli elementi di pagamento
    
    Args:
        xml_content: Contenuto XML del file F24
        f24_id: ID univoco dell'F24
    
    Returns:
        F24Document con tutti gli elementi parsati
    """
    try:
        root = ET.fromstring(xml_content)
        f24_doc = F24Document(f24_id)
        
        # Cerca data pagamento
        data_node = root.find(".//DataPagamento")
        if data_node is not None:
            f24_doc.data_pagamento = data_node.text
        
        # Parsa sezione Erario
        for elem in root.findall(".//SezioneErario/ElementoPagamento"):
            codice = elem.find("CodiceTributo")
            importo_deb = elem.find("ImportoDebito")
            importo_cred = elem.find("ImportoCredito")
            anno = elem.find("AnnoRiferimento")
            rateaz = elem.find("Rateazione")
            
            if codice is not None and importo_deb is not None:
                importo = float(importo_deb.text.replace(",", "."))
                
                # Se c'è credito, sottrailo
                if importo_cred is not None and importo_cred.text:
                    credito = float(importo_cred.text.replace(",", "."))
                    importo -= credito
                
                if importo > 0:
                    elemento = F24Element(
                        sezione="erario",
                        codice_tributo=codice.text,
                        importo=importo,
                        anno_riferimento=anno.text if anno is not None else None,
                        rateazione=rateaz.text if rateaz is not None else None
                    )
                    f24_doc.aggiungi_elemento(elemento)
        
        # Parsa sezione INPS
        for elem in root.findall(".//SezioneINPS/ElementoPagamento"):
            codice = elem.find("CodiceTributo")
            importo_deb = elem.find("ImportoDebito")
            importo_cred = elem.find("ImportoCredito")
            anno = elem.find("AnnoRiferimento")
            rateaz = elem.find("Rateazione")
            matricola = elem.find("MatricolaINPS")
            causale = elem.find("CausaleContributo")
            
            if codice is not None and importo_deb is not None:
                importo = float(importo_deb.text.replace(",", "."))
                
                if importo_cred is not None and importo_cred.text:
                    credito = float(importo_cred.text.replace(",", "."))
                    importo -= credito
                
                if importo > 0:
                    elemento = F24Element(
                        sezione="inps",
                        codice_tributo=codice.text,
                        importo=importo,
                        anno_riferimento=anno.text if anno is not None else None,
                        rateazione=rateaz.text if rateaz is not None else None,
                        matricola_inps=matricola.text if matricola is not None else None,
                        causale_contributo=causale.text if causale is not None else None
                    )
                    f24_doc.aggiungi_elemento(elemento)
        
        # Parsa sezione Regioni (se presente)
        for elem in root.findall(".//SezioneRegioni/ElementoPagamento"):
            codice = elem.find("CodiceTributo")
            importo_deb = elem.find("ImportoDebito")
            importo_cred = elem.find("ImportoCredito")
            anno = elem.find("AnnoRiferimento")
            
            if codice is not None and importo_deb is not None:
                importo = float(importo_deb.text.replace(",", "."))
                
                if importo_cred is not None and importo_cred.text:
                    credito = float(importo_cred.text.replace(",", "."))
                    importo -= credito
                
                if importo > 0:
                    elemento = F24Element(
                        sezione="regioni",
                        codice_tributo=codice.text,
                        importo=importo,
                        anno_riferimento=anno.text if anno is not None else None
                    )
                    f24_doc.aggiungi_elemento(elemento)
        
        return f24_doc
    
    except Exception as e:
        raise ValueError(f"Errore nel parsing F24 XML: {str(e)}")


# ============================================================================
# MATCHING MOVIMENTO BANCARIO <-> F24
# ============================================================================

def trova_f24_da_movimento_bancario(
    importo_movimento: float,
    data_movimento: date,
    f24_disponibili: List[Dict],
    tolleranza_giorni: int = 7,
    tolleranza_importo: float = 0.01
) -> Optional[Dict]:
    """
    Cerca l'F24 corrispondente a un movimento bancario
    
    Args:
        importo_movimento: Importo del movimento bancario (positivo)
        data_movimento: Data del movimento
        f24_disponibili: Lista di F24 salvati nel DB
        tolleranza_giorni: Giorni di tolleranza per il match della data
        tolleranza_importo: Tolleranza per il match dell'importo (euro)
    
    Returns:
        F24 matchato oppure None
    """
    candidati = []
    
    for f24 in f24_disponibili:
        # Verifica importo
        importo_f24 = f24.get("importo_totale", 0)
        diff_importo = abs(importo_movimento - importo_f24)
        
        if diff_importo > tolleranza_importo:
            continue
        
        # Verifica data (se disponibile)
        data_f24_str = f24.get("data_pagamento")
        if data_f24_str:
            try:
                data_f24 = datetime.fromisoformat(data_f24_str).date()
                diff_giorni = abs((data_movimento - data_f24).days)
                
                if diff_giorni > tolleranza_giorni:
                    continue
                
                # Candidato valido
                candidati.append({
                    "f24": f24,
                    "score": diff_giorni + (diff_importo * 10)  # Score: più basso = migliore
                })
            except:
                # Se la data non è parsabile, considera solo l'importo
                if diff_importo <= tolleranza_importo:
                    candidati.append({
                        "f24": f24,
                        "score": diff_importo * 10
                    })
        else:
            # Nessuna data disponibile, match solo su importo
            if diff_importo <= tolleranza_importo:
                candidati.append({
                    "f24": f24,
                    "score": diff_importo * 10 + 100  # Penalità per mancanza data
                })
    
    # Ritorna il miglior candidato (score più basso)
    if candidati:
        candidati.sort(key=lambda x: x["score"])
        return candidati[0]["f24"]
    
    return None


def estrai_info_da_descrizione_movimento(descrizione: str) -> Dict:
    """
    Estrae informazioni utili dalla descrizione del movimento bancario
    
    Cerca:
    - Pattern F24
    - Possibili codici tributo
    - Data
    
    Returns:
        Dict con informazioni estratte
    """
    info = {
        "is_f24": False,
        "codici_tributo_possibili": [],
        "data_possibile": None
    }
    
    descrizione_lower = descrizione.lower()
    
    # Verifica se è F24
    if any(kw in descrizione_lower for kw in ["f24", "f 24", "tributi", "modello f24"]):
        info["is_f24"] = True
    
    # Cerca codici tributo (4 cifre)
    codici_4_cifre = re.findall(r'\b(\d{4})\b', descrizione)
    for codice in codici_4_cifre:
        if codice in F24_ERARIO_CODES:
            info["codici_tributo_possibili"].append({
                "codice": codice,
                "tipo": "erario",
                "descrizione": F24_ERARIO_CODES[codice]["descrizione"]
            })
    
    # Cerca codici INPS (DMxx)
    codici_dm = re.findall(r'\b(DM\d{2})\b', descrizione.upper())
    for codice in codici_dm:
        if codice in F24_INPS_CODES:
            info["codici_tributo_possibili"].append({
                "codice": codice,
                "tipo": "inps",
                "descrizione": F24_INPS_CODES[codice]["descrizione"]
            })
    
    # Cerca data (formato gg/mm/aaaa o aaaa-mm-gg)
    date_patterns = [
        r'\b(\d{2})/(\d{2})/(\d{4})\b',
        r'\b(\d{4})-(\d{2})-(\d{2})\b'
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, descrizione)
        if match:
            info["data_possibile"] = match.group(0)
            break
    
    return info
