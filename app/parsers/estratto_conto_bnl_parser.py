"""
Parser per Estratti Conto BNL (Banca Nazionale del Lavoro)
Estrae movimenti bancari dai PDF degli estratti conto BNL.

Supporta:
- Estratti conto corrente BNL
- Estratti conto carta di credito BNL Business
"""
import fitz  # PyMuPDF
import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class EstrattoContoBNLParser:
    """Parser per estratti conto BNL (conto corrente e carta)."""
    
    def __init__(self):
        self.transactions: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}
        self.tipo_documento = "unknown"  # "conto_corrente" o "carta_credito"
    
    def parse_pdf(self, pdf_content: bytes) -> Dict[str, Any]:
        """
        Parse un estratto conto BNL da PDF.
        
        Args:
            pdf_content: Contenuto binario del file PDF
            
        Returns:
            Dizionario con metadata e lista transazioni
        """
        try:
            doc = fitz.open(stream=pdf_content, filetype="pdf")
            
            full_text = ""
            for page in doc:
                full_text += page.get_text() + "\n"
            
            doc.close()
            
            # Determina il tipo di documento
            if "CARTA BNL BUSINESS" in full_text or "CARTE DI CREDITO" in full_text:
                self.tipo_documento = "carta_credito"
                return self._parse_carta_credito(full_text)
            elif "ESTRATTO CONTO N." in full_text and "C/C N." in full_text:
                self.tipo_documento = "conto_corrente"
                return self._parse_conto_corrente(full_text)
            else:
                # Prova comunque come conto corrente
                self.tipo_documento = "conto_corrente"
                return self._parse_conto_corrente(full_text)
                
        except Exception as e:
            logger.exception(f"Errore parsing estratto conto BNL: {e}")
            return {
                "success": False,
                "error": str(e),
                "tipo_documento": "estratto_conto_bnl"
            }
    
    def _parse_conto_corrente(self, text: str) -> Dict[str, Any]:
        """Parse estratto conto corrente BNL."""
        
        # Estrai metadata
        self._extract_metadata_cc(text)
        
        # Estrai movimenti
        self._extract_transactions_cc(text)
        
        return {
            "success": True,
            "tipo_documento": "estratto_conto_bnl_cc",
            "banca": "BNL",
            "metadata": self.metadata,
            "transazioni": self.transactions,
            "totale_transazioni": len(self.transactions),
            "totale_entrate": sum(t.get("importo", 0) for t in self.transactions if t.get("tipo") == "entrata"),
            "totale_uscite": sum(abs(t.get("importo", 0)) for t in self.transactions if t.get("tipo") == "uscita")
        }
    
    def _parse_carta_credito(self, text: str) -> Dict[str, Any]:
        """Parse estratto conto carta di credito BNL Business."""
        
        # Estrai metadata carta
        self._extract_metadata_carta(text)
        
        # Estrai movimenti carta
        self._extract_transactions_carta(text)
        
        return {
            "success": True,
            "tipo_documento": "estratto_conto_bnl_carta",
            "banca": "BNL",
            "metadata": self.metadata,
            "transazioni": self.transactions,
            "totale_transazioni": len(self.transactions),
            "totale_importo": sum(t.get("importo", 0) for t in self.transactions)
        }
    
    def _extract_metadata_cc(self, text: str) -> None:
        """Estrae metadata dall'estratto conto corrente."""
        
        # Numero estratto conto
        match = re.search(r'ESTRATTO CONTO N\.\s*(\d+/\d+)', text)
        if match:
            self.metadata["numero_estratto"] = match.group(1)
        
        # Periodo
        match = re.search(r'AI MOVIMENTI DAL\s+(\d{2}/\d{2}/\d{4})\s+AL\s+(\d{2}/\d{2}/\d{4})', text)
        if match:
            self.metadata["periodo_da"] = self._parse_date(match.group(1))
            self.metadata["periodo_a"] = self._parse_date(match.group(2))
        
        # Numero conto
        match = re.search(r'C/C N\.\s*(\d+/\d+)', text)
        if match:
            self.metadata["numero_conto"] = match.group(1)
        
        # IBAN
        match = re.search(r'IBAN[¹]?:\s*(IT[A-Z0-9]+)', text)
        if match:
            self.metadata["iban"] = match.group(1)
        
        # BIC
        match = re.search(r'BIC[²]?:\s*([A-Z]+)', text)
        if match:
            self.metadata["bic"] = match.group(1)
        
        # Intestatario
        match = re.search(r'CERALDI GROUP[^\n]+', text)
        if match:
            self.metadata["intestatario"] = match.group(0).strip()
        
        # Saldo iniziale
        match = re.search(r'saldo iniziale[^\d]*\+?\s*([\d.,]+)\s*€', text, re.IGNORECASE)
        if match:
            self.metadata["saldo_iniziale"] = self._parse_amount(match.group(1))
        
        # Saldo finale
        match = re.search(r'SALDO FINALE[^\d]*\+?\s*([\d.,]+)\s*€', text, re.IGNORECASE)
        if match:
            self.metadata["saldo_finale"] = self._parse_amount(match.group(1))
        
        # Totale entrate
        match = re.search(r'TOTALE ENTRATE[^\d]*\+?\s*([\d.,]+)\s*€', text, re.IGNORECASE)
        if match:
            self.metadata["totale_entrate"] = self._parse_amount(match.group(1))
        
        # Totale uscite
        match = re.search(r'TOTALE USCITE[^\d]*-?\s*([\d.,]+)\s*€', text, re.IGNORECASE)
        if match:
            self.metadata["totale_uscite"] = self._parse_amount(match.group(1))
    
    def _extract_metadata_carta(self, text: str) -> None:
        """Estrae metadata dall'estratto conto carta di credito."""
        
        # Numero posizione carta
        match = re.search(r'Numero posizione\s*(\d+)', text)
        if match:
            self.metadata["numero_posizione"] = match.group(1)
        
        # Codice azienda
        match = re.search(r'Codice azienda\s*(\d+)', text)
        if match:
            self.metadata["codice_azienda"] = match.group(1)
        
        # Data estratto
        match = re.search(r'Estratto Conto n\.\s*\d+\s+del\s+(\d{2}\.\d{2}\.\d{4})', text)
        if match:
            self.metadata["data_estratto"] = match.group(1).replace(".", "/")
        
        # Limite di utilizzo
        match = re.search(r'Limite di utilizzo\s*([\d.,]+)\s*euro', text, re.IGNORECASE)
        if match:
            self.metadata["limite_utilizzo"] = self._parse_amount(match.group(1))
        
        # IBAN domiciliazione
        match = re.search(r'N\. conto corrente\s*(\d+)', text)
        if match:
            self.metadata["conto_addebito"] = match.group(1)
        
        # Valuta addebito
        match = re.search(r'Valuta di addebito in C/C\s*(\d{2}\.\d{2}\.\d{4})', text)
        if match:
            self.metadata["data_addebito"] = match.group(1).replace(".", "/")
    
    def _extract_transactions_cc(self, text: str) -> None:
        """Estrae le transazioni dall'estratto conto corrente BNL."""
        
        # Il formato BNL ha i movimenti in una tabella con questa struttura:
        # DATA CONTABILE | DATA VALUTA | CAUS ABI | DESCRIZIONE | USCITA | ENTRATA
        
        # Pattern per riga movimento
        # Es: "03/01/2022 31/12/2021 18 Interessi creditori 0,11 €"
        # Es: "11/01/2022 11/01/2022 45 Utilizzo carta di credito 95,53 €"
        
        lines = text.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Cerca pattern data all'inizio della riga
            date_match = re.match(r'^(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(\d+)\s+(.+)', line)
            
            if date_match:
                data_contabile = date_match.group(1)
                data_valuta = date_match.group(2)
                causale_abi = date_match.group(3)
                resto = date_match.group(4)
                
                # Cerca importo nella parte restante
                # Pattern: "descrizione 123,45 €" o "descrizione 1.234,56 €"
                amount_match = re.search(r'([\d.,]+)\s*€\s*$', resto)
                
                if amount_match:
                    importo_str = amount_match.group(1)
                    descrizione = resto[:amount_match.start()].strip()
                    importo = self._parse_amount(importo_str)
                    
                    # Determina se è entrata o uscita basandosi sulla posizione nel documento
                    # e sulla causale ABI
                    # Causali comuni: 18=interessi, 45=utilizzo carta, 50=addebito SEPA, 
                    # 66=spese, 78=versamento contante
                    
                    causali_entrate = ['18', '78']  # Interessi creditori, versamenti
                    tipo = "entrata" if causale_abi in causali_entrate else "uscita"
                    
                    # Controlla anche nella descrizione
                    desc_lower = descrizione.lower()
                    if any(x in desc_lower for x in ['versamento', 'accredito', 'bonifico a nostro favore', 'interessi creditori']):
                        tipo = "entrata"
                    elif any(x in desc_lower for x in ['addebito', 'spese', 'utilizzo carta', 'pagamento', 'commissione']):
                        tipo = "uscita"
                    
                    # Se è uscita, rendi l'importo negativo
                    if tipo == "uscita":
                        importo = -abs(importo)
                    
                    transaction = {
                        "data_contabile": self._parse_date(data_contabile),
                        "data_valuta": self._parse_date(data_valuta),
                        "causale_abi": causale_abi,
                        "descrizione": descrizione,
                        "importo": importo,
                        "tipo": tipo,
                        "banca": "BNL"
                    }
                    
                    # Salta SALDO INIZIALE
                    if "SALDO INIZIALE" not in descrizione:
                        self.transactions.append(transaction)
            
            i += 1
        
        # Se non ha trovato transazioni con il metodo sopra, prova un altro pattern
        if not self.transactions:
            self._extract_transactions_cc_alternate(text)
    
    def _extract_transactions_cc_alternate(self, text: str) -> None:
        """Metodo alternativo per estrarre transazioni da formati BNL diversi."""
        
        # Pattern più flessibile
        pattern = r'(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(\d+)\s+([^\d]+?)\s+([\d.,]+)\s*€'
        
        for match in re.finditer(pattern, text):
            data_contabile = match.group(1)
            data_valuta = match.group(2)
            causale_abi = match.group(3)
            descrizione = match.group(4).strip()
            importo = self._parse_amount(match.group(5))
            
            # Salta voci non rilevanti
            if "SALDO INIZIALE" in descrizione or "SALDO FINALE" in descrizione:
                continue
            
            causali_entrate = ['18', '78']
            tipo = "entrata" if causale_abi in causali_entrate else "uscita"
            
            desc_lower = descrizione.lower()
            if any(x in desc_lower for x in ['versamento', 'accredito']):
                tipo = "entrata"
            
            if tipo == "uscita":
                importo = -abs(importo)
            
            self.transactions.append({
                "data_contabile": self._parse_date(data_contabile),
                "data_valuta": self._parse_date(data_valuta),
                "causale_abi": causale_abi,
                "descrizione": descrizione,
                "importo": importo,
                "tipo": tipo,
                "banca": "BNL"
            })
    
    def _extract_transactions_carta(self, text: str) -> None:
        """Estrae le transazioni dall'estratto conto carta di credito BNL Business."""
        
        lines = text.split('\n')
        in_dettaglio = False
        current_carta = None
        current_titolare = None
        
        i = 0
        while i < len(lines):
            line_clean = lines[i].strip()
            
            # Rileva inizio sezione DETTAGLIO OPERAZIONI
            if "DETTAGLIO OPERAZIONI" in line_clean:
                in_dettaglio = True
                i += 1
                continue
            
            # Rileva carta attiva
            if "CARTA BNL BUSINESS n." in line_clean:
                match = re.search(r'CARTA BNL BUSINESS n\.\s*([\d\*\s]+)', line_clean)
                if match:
                    current_carta = match.group(1).strip()
                    # Il titolare è sulla riga successiva
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if next_line and not re.match(r'\d{2}\.\d{2}\.\d{4}', next_line):
                            current_titolare = next_line
                i += 1
                continue
            
            # Fine sezione - Saldo carta
            if in_dettaglio and line_clean.startswith("Saldo CARTA"):
                in_dettaglio = False
                i += 1
                continue
            
            if in_dettaglio:
                # Cerca pattern: data operazione (DD.MM.YYYY)
                if re.match(r'^\d{2}\.\d{2}\.\d{4}$', line_clean):
                    data_operazione = line_clean
                    
                    # Leggi le righe successive
                    data_contabile = None
                    num_riferimento = None
                    descrizione = None
                    importo = None
                    
                    # Riga +1: data contabile
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if re.match(r'^\d{2}\.\d{2}\.\d{4}$', next_line):
                            data_contabile = next_line
                    
                    # Riga +2: numero riferimento
                    if i + 2 < len(lines):
                        next_line = lines[i + 2].strip()
                        if re.match(r'^\d+$', next_line):
                            num_riferimento = next_line
                    
                    # Riga +3: descrizione
                    if i + 3 < len(lines):
                        descrizione = lines[i + 3].strip()
                    
                    # Riga +4: importo
                    if i + 4 < len(lines):
                        next_line = lines[i + 4].strip()
                        if re.match(r'^[\d.,]+$', next_line):
                            importo = self._parse_amount(next_line)
                    
                    # Se abbiamo i dati essenziali, crea transazione
                    if data_operazione and descrizione and importo is not None:
                        self.transactions.append({
                            "data": self._parse_date(data_operazione.replace(".", "/")),
                            "data_contabile": self._parse_date(data_contabile.replace(".", "/")) if data_contabile else None,
                            "numero_riferimento": num_riferimento,
                            "descrizione": descrizione,
                            "importo": -abs(importo),  # Sempre negativo per carta
                            "tipo": "addebito",
                            "banca": "BNL",
                            "tipo_carta": "BNL Business",
                            "carta_numero": current_carta,
                            "carta_titolare": current_titolare
                        })
                        i += 4  # Salta le righe già processate
                        continue
            
            i += 1
    
    def _parse_date(self, date_str: str) -> str:
        """Converte una data in formato ISO."""
        try:
            # Supporta DD/MM/YYYY e DD/MM/YY
            parts = date_str.replace(".", "/").split('/')
            if len(parts) == 3:
                day = parts[0].zfill(2)
                month = parts[1].zfill(2)
                year = parts[2]
                if len(year) == 2:
                    year = "20" + year if int(year) < 50 else "19" + year
                return f"{year}-{month}-{day}"
        except:
            pass
        return date_str
    
    def _parse_amount(self, amount_str: str) -> float:
        """Converte un importo stringa in float."""
        try:
            # Rimuovi spazi e gestisci formato italiano
            amount_str = amount_str.replace(' ', '').replace('.', '').replace(',', '.')
            return float(amount_str)
        except:
            return 0.0


def parse_estratto_conto_bnl(pdf_content: bytes) -> Dict[str, Any]:
    """
    Funzione wrapper per il parsing di estratti conto BNL.
    
    Args:
        pdf_content: Contenuto binario del file PDF
        
    Returns:
        Dizionario con metadata e lista transazioni
    """
    parser = EstrattoContoBNLParser()
    return parser.parse_pdf(pdf_content)


async def parse_estratto_conto_bnl_from_file(file_path: str) -> Dict[str, Any]:
    """
    Parse un estratto conto BNL da un file.
    
    Args:
        file_path: Percorso del file PDF
        
    Returns:
        Dizionario con metadata e lista transazioni
    """
    with open(file_path, "rb") as f:
        return parse_estratto_conto_bnl(f.read())
