"""
Parser per Estratti Conto Carta di Credito Nexi/Banco BPM
Estrae le transazioni dai PDF degli estratti conto Nexi.

Formato supportato:
- Estratti conto mensili Nexi con carta di credito Banco BPM
- Struttura: Data | Descrizione | Importo in Euro | Importo in altre valute | Cambio
"""
import fitz  # PyMuPDF
import re
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class EstrattoContoNexiParser:
    """Parser per estratti conto carta di credito Nexi/Banco BPM."""
    
    def __init__(self):
        self.transactions: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}
        
    def parse_pdf(self, pdf_content: bytes) -> Dict[str, Any]:
        """
        Parse un estratto conto Nexi da PDF.
        
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
            
            # Estrai metadata
            self._extract_metadata(full_text)
            
            # Estrai transazioni
            self._extract_transactions(full_text)
            
            return {
                "success": True,
                "tipo_documento": "estratto_conto_nexi",
                "metadata": self.metadata,
                "transazioni": self.transactions,
                "totale_transazioni": len(self.transactions),
                "totale_importo": sum(t.get("importo", 0) for t in self.transactions)
            }
            
        except Exception as e:
            logger.exception(f"Errore parsing estratto conto Nexi: {e}")
            return {
                "success": False,
                "error": str(e),
                "tipo_documento": "estratto_conto_nexi"
            }
    
    def _extract_metadata(self, text: str) -> None:
        """Estrae i metadata dall'estratto conto."""
        
        # Data estratto conto (es. "Milano, 31 Dicembre 2025")
        date_match = re.search(r'Milano,\s+(\d{1,2}\s+\w+\s+\d{4})', text)
        if date_match:
            self.metadata["data_estratto"] = date_match.group(1)
            # Converti in formato ISO
            try:
                mesi = {
                    "gennaio": "01", "febbraio": "02", "marzo": "03", "aprile": "04",
                    "maggio": "05", "giugno": "06", "luglio": "07", "agosto": "08",
                    "settembre": "09", "ottobre": "10", "novembre": "11", "dicembre": "12"
                }
                parts = date_match.group(1).lower().split()
                if len(parts) == 3:
                    giorno = parts[0].zfill(2)
                    mese = mesi.get(parts[1], "01")
                    anno = parts[2]
                    self.metadata["data_estratto_iso"] = f"{anno}-{mese}-{giorno}"
            except:
                pass
        
        # Numero carta (mascherato)
        card_match = re.search(r'\*{4}\s*\*{4}\s*\*{4}\s*(\d{4})', text)
        if card_match:
            self.metadata["numero_carta_ultime4"] = card_match.group(1)
            self.metadata["numero_carta_mascherato"] = f"**** **** **** {card_match.group(1)}"
        
        # Scadenza carta
        exp_match = re.search(r'SCADENZA\s+(\d{2}/\d{2})', text)
        if exp_match:
            self.metadata["scadenza_carta"] = exp_match.group(1)
        
        # Intestatario
        # Cerca "CERALDI GROUP S.R.L." o pattern simile prima dell'indirizzo
        intestatario_match = re.search(r'([A-Z\s\.]+(?:S\.R\.L\.?|S\.P\.A\.?|S\.N\.C\.?|S\.A\.S\.?))\s*\n', text)
        if intestatario_match:
            self.metadata["intestatario"] = intestatario_match.group(1).strip()
        
        # Totale spese del mese
        spese_match = re.search(r'QUESTO MESE HA SPESO[^\d]*(\d+[.,]\d{2})', text, re.IGNORECASE)
        if spese_match:
            self.metadata["totale_spese_mese"] = self._parse_amount(spese_match.group(1))
        
        # Totale addebito
        addebito_match = re.search(r'QUESTO MESE LE SARANNO ADDEBITATI[^\d]*(\d+[.,]\d{2})', text, re.IGNORECASE)
        if addebito_match:
            self.metadata["totale_addebito"] = self._parse_amount(addebito_match.group(1))
        
        # IBAN
        iban_match = re.search(r'(IT\d{2}[A-Z]\d{10}[A-Z0-9]{12})', text)
        if iban_match:
            self.metadata["iban"] = iban_match.group(1)
    
    def _extract_transactions(self, text: str) -> None:
        """Estrae le transazioni dall'estratto conto."""
        
        # Trova la sezione "DETTAGLIO DEI SUOI MOVIMENTI"
        dettaglio_start = text.find("DETTAGLIO DEI SUOI MOVIMENTI")
        if dettaglio_start == -1:
            # Prova varianti
            dettaglio_start = text.find("DETTAGLIO MOVIMENTI")
        
        if dettaglio_start == -1:
            logger.warning("Sezione dettaglio movimenti non trovata")
            return
        
        # Estrai solo la parte dopo l'inizio del dettaglio
        text_dettaglio = text[dettaglio_start:]
        
        # Trova la fine della sezione (prima di "TOTALE SPESE" o "SERVIZIO CLIENTI")
        end_markers = ["TOTALE SPESE", "SERVIZIO CLIENTI NEXI", "Blocco Carta"]
        end_pos = len(text_dettaglio)
        for marker in end_markers:
            pos = text_dettaglio.find(marker)
            if pos != -1 and pos < end_pos:
                end_pos = pos
        
        text_dettaglio = text_dettaglio[:end_pos]
        
        # Le transazioni nel PDF Nexi sono strutturate così (su righe separate):
        # Riga 1: Data (DD/MM/YY)
        # Riga 2: Descrizione
        # Riga 3: Importo (X,XX o - X,XX)
        # (poi si ripete)
        
        lines = [line.strip() for line in text_dettaglio.split('\n') if line.strip()]
        
        # Salta le righe di header
        skip_lines = ["Data", "Descrizione", "Importo in Euro", "Importo in altre valute", "Cambio",
                      "DETTAGLIO DEI SUOI MOVIMENTI"]
        lines = [l for l in lines if l not in skip_lines]
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Cerca una data come inizio di transazione
            if re.match(r'^\d{2}/\d{2}/\d{2,4}$', line):
                data_str = line
                descrizione = ""
                importo = None
                
                # La prossima riga dovrebbe essere la descrizione
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    
                    # Verifica che non sia un'altra data o un importo
                    if not re.match(r'^\d{2}/\d{2}/\d{2,4}$', next_line):
                        # Verifica se è un importo
                        if re.match(r'^-?\s*\d+[\d\.,]*\d{2}$', next_line.replace('.', '').replace(',', '').replace('-', '').replace(' ', '')):
                            # È un importo, quindi la descrizione era vuota
                            importo = self._parse_amount(next_line)
                            i += 2
                        else:
                            # È la descrizione
                            descrizione = next_line
                            i += 2
                            
                            # L'importo dovrebbe essere nella riga successiva
                            if i < len(lines):
                                amount_line = lines[i]
                                # Verifica se è un importo
                                if re.match(r'^-?\s*[\d\.,]+$', amount_line.replace(' ', '')):
                                    importo = self._parse_amount(amount_line)
                                    i += 1
                    else:
                        i += 1
                else:
                    i += 1
                
                # Se abbiamo trovato dati validi, crea la transazione
                if importo is not None and importo != 0:
                    transaction = {
                        "data": self._parse_date(data_str),
                        "data_originale": data_str,
                        "descrizione": descrizione or "Movimento",
                        "importo": importo,
                        "tipo": "addebito" if importo >= 0 else "accredito",
                        "categoria": self._categorize_transaction(descrizione)
                    }
                    self.transactions.append(transaction)
            else:
                i += 1
    
    def _parse_date(self, date_str: str) -> str:
        """Converte una data da DD/MM/YY a YYYY-MM-DD."""
        try:
            parts = date_str.split('/')
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
            # Rimuovi spazi
            amount_str = amount_str.replace(' ', '')
            # Gestisci formato italiano (virgola decimale)
            amount_str = amount_str.replace('.', '').replace(',', '.')
            return float(amount_str)
        except:
            return 0.0
    
    def _categorize_transaction(self, descrizione: str) -> str:
        """Categorizza la transazione in base alla descrizione."""
        desc_upper = descrizione.upper()
        
        # Amazon
        if any(x in desc_upper for x in ["AMAZON", "AMZN", "AMZNBUSINESS"]):
            return "E-commerce Amazon"
        
        # PayPal / Servizi digitali
        if "PAYPAL" in desc_upper:
            if "SPOTIFY" in desc_upper:
                return "Abbonamento Spotify"
            elif "NETFLIX" in desc_upper:
                return "Abbonamento Netflix"
            return "PayPal"
        
        # Carburante
        if any(x in desc_upper for x in ["ESSO", "ENI", "Q8", "IP ", "SHELL", "TAMOIL", "TOTAL", "CARBURANTE", "BENZINA"]):
            return "Carburante"
        
        # Supermercati
        if any(x in desc_upper for x in ["COOP", "CONAD", "LIDL", "EUROSPIN", "MD ", "ALDI", "ESSELUNGA", "CARREFOUR"]):
            return "Supermercato"
        
        # Ristoranti
        if any(x in desc_upper for x in ["RISTORANTE", "PIZZERIA", "BAR ", "CAFFE", "MCDONALDS", "BURGER"]):
            return "Ristorazione"
        
        # Trasporti
        if any(x in desc_upper for x in ["TRENITALIA", "ITALO", "AUTOSTRADA", "TELEPASS"]):
            return "Trasporti"
        
        # Assicurazioni
        if any(x in desc_upper for x in ["ASSICURA", "UNIPOL", "GENERALI", "ALLIANZ", "AXA"]):
            return "Assicurazione"
        
        # Utenze
        if any(x in desc_upper for x in ["ENEL", "A2A", "EDISON", "TIM", "VODAFONE", "WIND", "FASTWEB"]):
            return "Utenze"
        
        # IBA (probabile bonifico internazionale)
        if "IBA IT" in desc_upper:
            return "Bonifico Internazionale"
        
        # Default
        return "Altro"


def parse_estratto_conto_nexi(pdf_content: bytes) -> Dict[str, Any]:
    """
    Funzione wrapper per il parsing di estratti conto Nexi.
    
    Args:
        pdf_content: Contenuto binario del file PDF
        
    Returns:
        Dizionario con metadata e lista transazioni
    """
    parser = EstrattoContoNexiParser()
    return parser.parse_pdf(pdf_content)


async def parse_estratto_conto_nexi_from_file(file_path: str) -> Dict[str, Any]:
    """
    Parse un estratto conto Nexi da un file.
    
    Args:
        file_path: Percorso del file PDF
        
    Returns:
        Dizionario con metadata e lista transazioni
    """
    with open(file_path, "rb") as f:
        return parse_estratto_conto_nexi(f.read())
