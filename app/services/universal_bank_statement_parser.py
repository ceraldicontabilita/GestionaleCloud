"""
Universal Bank Statement PDF Parser
Parser universale per estratti conto bancari italiani.

Supporta:
- BANCO BPM (conto corrente)
- BNL (conto corrente e carta di credito)
- Nexi (carta di credito)

Usa pdfplumber per un'estrazione più accurata delle tabelle.
"""
import pdfplumber
import re
import logging
from typing import Dict, Any, List, Optional
from io import BytesIO

logger = logging.getLogger(__name__)


class UniversalBankStatementParser:
    """Parser universale per estratti conto bancari italiani."""
    
    BANK_PATTERNS = {
        "BANCO_BPM": [
            r"BANCO\s*BPM",
            r"BANCODIBRESCIA",
            r"BANCA\s*POPOLARE\s*DI\s*MILANO",
            r"WeBank"
        ],
        "BNL": [
            r"BNL\s+Gruppo\s+BNP\s+Paribas",
            r"BANCA\s*NAZIONALE\s*DEL\s*LAVORO",
            r"BNL\s+BNP"
        ],
        "NEXI": [
            r"NEXI\s+S\.p\.A",
            r"CartaSi",
            r"NEXI\s+PAYMENTS"
        ],
        "INTESA": [
            r"INTESA\s*SANPAOLO",
            r"BANCA\s*INTESA"
        ],
        "UNICREDIT": [
            r"UNICREDIT",
            r"CREDITO\s*ITALIANO"
        ]
    }
    
    def __init__(self):
        self.transactions: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {}
        self.detected_bank: str = "SCONOSCIUTA"
        self.raw_text: str = ""
    
    def detect_bank(self, text: str) -> str:
        """Rileva automaticamente la banca dal testo del PDF."""
        text_upper = text.upper()
        
        for bank, patterns in self.BANK_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, text_upper, re.IGNORECASE):
                    return bank
        
        # Fallback: cerca altri indicatori
        if "ESTRATTO CONTO CORRENTE" in text_upper:
            if "BPM" in text_upper or "POPOLARE" in text_upper:
                return "BANCO_BPM"
        
        return "GENERICA"
    
    def parse_pdf(self, pdf_content: bytes) -> Dict[str, Any]:
        """
        Parse un estratto conto PDF usando pdfplumber.
        
        Args:
            pdf_content: Contenuto binario del file PDF
            
        Returns:
            Dizionario con metadata, transazioni estratte e info parsing
        """
        try:
            pdf_file = BytesIO(pdf_content)
            
            with pdfplumber.open(pdf_file) as pdf:
                # Estrai tutto il testo per rilevare la banca
                all_text = ""
                all_tables = []
                
                for page_num, page in enumerate(pdf.pages):
                    page_text = page.extract_text() or ""
                    all_text += page_text + "\n"
                    
                    # Estrai tabelle da ogni pagina
                    tables = page.extract_tables() or []
                    for table in tables:
                        all_tables.append({
                            "page": page_num + 1,
                            "data": table
                        })
                
                self.raw_text = all_text
                self.detected_bank = self.detect_bank(all_text)
                
                # Estrai metadata comuni
                self._extract_common_metadata(all_text)
                
                # Parse in base alla banca rilevata
                if self.detected_bank == "BANCO_BPM":
                    self._parse_banco_bpm(all_text, all_tables)
                elif self.detected_bank == "BNL":
                    self._parse_bnl(all_text, all_tables)
                elif self.detected_bank == "NEXI":
                    self._parse_nexi(all_text, all_tables)
                else:
                    # Parser generico
                    self._parse_generic(all_text, all_tables)
                
                # Rimuovi duplicati
                self._deduplicate_transactions()
                
                # Calcola totali
                totale_entrate = sum(t.get("entrata", 0) or 0 for t in self.transactions)
                totale_uscite = sum(t.get("uscita", 0) or 0 for t in self.transactions)
                
                return {
                    "success": True,
                    "banca": self.detected_bank,
                    "metadata": self.metadata,
                    "transazioni": self.transactions,
                    "totale_transazioni": len(self.transactions),
                    "totale_entrate": round(totale_entrate, 2),
                    "totale_uscite": round(totale_uscite, 2),
                    "num_pagine": len(pdf.pages)
                }
                
        except Exception as e:
            logger.exception(f"Errore parsing PDF: {e}")
            return {
                "success": False,
                "error": str(e),
                "banca": self.detected_bank
            }
    
    def _extract_common_metadata(self, text: str) -> None:
        """Estrae metadata comuni a tutti i formati."""
        
        # IBAN
        iban_match = re.search(r'IT\s*\d{2}\s*[A-Z]\s*\d{5}\s*\d{5}\s*[\d\s]{12,}', text)
        if iban_match:
            self.metadata["iban"] = iban_match.group(0).replace(" ", "").replace("\n", "")[:27]
        
        # Periodo
        periodo_patterns = [
            r'(?:DAL|dal)\s+(\d{2}[./]\d{2}[./]\d{4})\s+(?:AL|al)\s+(\d{2}[./]\d{2}[./]\d{4})',
            r'PERIODO[:\s]+(\d{2}[./]\d{2}[./]\d{4})\s*[-–]\s*(\d{2}[./]\d{2}[./]\d{4})',
            r'MOVIMENTI\s+DAL\s+(\d{2}[./]\d{2}[./]\d{4})\s+AL\s+(\d{2}[./]\d{2}[./]\d{4})'
        ]
        for pattern in periodo_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                self.metadata["periodo_da"] = self._parse_date(match.group(1))
                self.metadata["periodo_a"] = self._parse_date(match.group(2))
                break
        
        # Intestatario - cerca pattern comuni
        intestatario_patterns = [
            r'(?:Intestato a|INTESTATARIO|Spett\.le)[:\s]*\n?([A-Z][A-Z\s\.]+(?:S\.?R\.?L\.?|S\.?P\.?A\.?|S\.?N\.?C\.?))',
            r'CERALDI\s*GROUP[^\n]*',
        ]
        for pattern in intestatario_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                self.metadata["intestatario"] = match.group(1).strip() if match.lastindex else match.group(0).strip()
                break
        
        # Saldo iniziale
        saldo_init_patterns = [
            r'SALDO\s+INIZIALE[^\d]*([\d.,]+)',
            r'saldo\s+iniziale[^\d]*([\d.,]+)',
            r'Saldo\s+al\s+\d{2}[./]\d{2}[./]\d{4}[^\d]*([\d.,]+)'
        ]
        for pattern in saldo_init_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                self.metadata["saldo_iniziale"] = self._parse_amount(match.group(1))
                break
        
        # Saldo finale
        saldo_fin_patterns = [
            r'SALDO\s+(?:CONTABILE\s+)?FINALE[^\d]*([\d.,]+)',
            r'Saldo\s+liquido\s+finale[^\d]*([\d.,]+)',
            r'saldo\s+finale[^\d]*([\d.,]+)'
        ]
        for pattern in saldo_fin_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                self.metadata["saldo_finale"] = self._parse_amount(match.group(1))
                break
    
    def _parse_banco_bpm(self, text: str, tables: List[Dict]) -> None:
        """Parse specifico per estratti conto BANCO BPM."""
        
        # Prima prova con le tabelle estratte da pdfplumber
        for table_info in tables:
            table = table_info["data"]
            if not table or len(table) < 2:
                continue
            
            for row in table:
                if not row or len(row) < 4:
                    continue
                
                # Cerca righe con pattern data DD/MM/YY nella prima colonna
                first_cell = str(row[0]) if row[0] else ""
                if not re.match(r'^\d{2}/\d{2}/\d{2,4}$', first_cell.strip()):
                    continue
                
                try:
                    data_contabile = first_cell.strip()
                    data_valuta = str(row[1]).strip() if row[1] else data_contabile
                    
                    # Cerca importo nelle colonne (può essere col 3 o 4)
                    importo = None
                    is_uscita = False
                    descrizione = ""
                    
                    for idx, cell in enumerate(row):
                        cell_str = str(cell).strip() if cell else ""
                        
                        # Pattern importo: "1.234,56-" o "1.234,56"
                        amount_match = re.match(r'^([\d.]+,\d{2})(-)?$', cell_str)
                        if amount_match:
                            importo = self._parse_amount(amount_match.group(1))
                            is_uscita = amount_match.group(2) == '-'
                            continue
                        
                        # Se è l'ultima colonna e non è un numero, è la descrizione
                        if idx >= 4 and cell_str and not re.match(r'^[\d.,\-]+$', cell_str):
                            descrizione = cell_str
                    
                    # Ultima colonna è spesso la descrizione
                    if not descrizione and len(row) > 5:
                        last_cell = str(row[-1]).strip() if row[-1] else ""
                        if last_cell and not re.match(r'^[\d.,\-]+$', last_cell):
                            descrizione = last_cell
                    
                    if importo and importo > 0:
                        # Salta saldi e dati dal riassunto scalare
                        if any(x in descrizione.upper() for x in ['SALDO INIZIALE', 'SALDO FINALE', 'COMPETENZE']):
                            continue
                        
                        # Salta righe senza descrizione significativa (probabilmente dal riassunto scalare)
                        if not descrizione or descrizione == "Movimento":
                            # Verifica se è un importo troppo grande (saldi, non transazioni)
                            if importo > 50000:
                                continue
                        
                        transaction = {
                            "data": self._parse_date(data_contabile),
                            "data_valuta": self._parse_date(data_valuta),
                            "descrizione": descrizione[:500] if descrizione else "Movimento",
                            "entrata": None if is_uscita else importo,
                            "uscita": importo if is_uscita else None,
                            "importo": -importo if is_uscita else importo,
                            "banca": "BANCO_BPM"
                        }
                        
                        if transaction["data"]:
                            self.transactions.append(transaction)
                except Exception as e:
                    logger.debug(f"Errore parsing riga BPM: {e}")
                    continue
        
        # Se non ha trovato con le tabelle, prova con regex sul testo
        if not self.transactions:
            self._parse_banco_bpm_regex(text)
    
    def _parse_banco_bpm_regex(self, text: str) -> None:
        """Parse BANCO BPM usando regex sul testo."""
        
        # Pattern: DD/MM/YY DD/MM/YY DD/MM/YY importo- descrizione
        # o: DD/MM/YY DD/MM/YY DD/MM/YY descrizione importo
        lines = text.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Pattern completo su una riga
            # Es: "03/10/20 03/10/20 03/10/20 8,20- IMP.BOLLO CC..."
            match = re.match(
                r'^(\d{2}/\d{2}/\d{2})\s+(\d{2}/\d{2}/\d{2})\s+\d{2}/\d{2}/\d{2}\s+([\d.,]+)(-?)\s+(.+)$',
                line
            )
            
            if match:
                data_contabile = match.group(1)
                data_valuta = match.group(2)
                importo = self._parse_amount(match.group(3))
                is_uscita = match.group(4) == '-'
                descrizione = match.group(5).strip()
                
                if importo > 0:
                    if any(x in descrizione.upper() for x in ['SALDO INIZIALE', 'SALDO FINALE', 'COMPETENZE']):
                        i += 1
                        continue
                    
                    transaction = {
                        "data": self._parse_date(data_contabile),
                        "data_valuta": self._parse_date(data_valuta),
                        "descrizione": descrizione[:500],
                        "entrata": None if is_uscita else importo,
                        "uscita": importo if is_uscita else None,
                        "importo": -importo if is_uscita else importo,
                        "banca": "BANCO_BPM"
                    }
                    
                    if transaction["data"]:
                        self.transactions.append(transaction)
            
            # Pattern alternativo: descrizione prima dell'importo
            # Es: "14/12/20 14/12/20 14/12/20 2.145,00 BON.DA AG..."
            match2 = re.match(
                r'^(\d{2}/\d{2}/\d{2})\s+(\d{2}/\d{2}/\d{2})\s+\d{2}/\d{2}/\d{2}\s+([\d.,]+)\s+(.+)$',
                line
            )
            
            if match2 and not match:
                data_contabile = match2.group(1)
                data_valuta = match2.group(2)
                importo = self._parse_amount(match2.group(3))
                descrizione = match2.group(4).strip()
                
                # Senza "-" è un'entrata
                if importo > 0:
                    if any(x in descrizione.upper() for x in ['SALDO INIZIALE', 'SALDO FINALE', 'COMPETENZE']):
                        i += 1
                        continue
                    
                    transaction = {
                        "data": self._parse_date(data_contabile),
                        "data_valuta": self._parse_date(data_valuta),
                        "descrizione": descrizione[:500],
                        "entrata": importo,
                        "uscita": None,
                        "importo": importo,
                        "banca": "BANCO_BPM"
                    }
                    
                    if transaction["data"]:
                        self.transactions.append(transaction)
            
            i += 1
    
    def _parse_bnl(self, text: str, tables: List[Dict]) -> None:
        """Parse specifico per estratti conto BNL."""
        
        # Pattern per transazioni BNL
        # DATA CONTABILE | DATA VALUTA | CAUS ABI | DESCRIZIONE | IMPORTO €
        
        pattern = r'(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(\d+)\s+(.+?)\s+([\d.,]+)\s*€?'
        
        for match in re.finditer(pattern, text):
            data_contabile = match.group(1)
            data_valuta = match.group(2)
            causale_abi = match.group(3)
            descrizione = match.group(4).strip()
            importo = self._parse_amount(match.group(5))
            
            # Salta saldi
            if any(x in descrizione.upper() for x in ['SALDO INIZIALE', 'SALDO FINALE']):
                continue
            
            # Determina tipo (entrata/uscita) dalla causale e descrizione
            causali_entrate = ['18', '78', '26', '48']  # Interessi, versamenti, accrediti
            is_entrata = causale_abi in causali_entrate
            
            desc_lower = descrizione.lower()
            if any(x in desc_lower for x in ['versamento', 'accredito', 'bonifico a nostro favore', 
                    'interessi creditori', 'giroconto in entrata']):
                is_entrata = True
            elif any(x in desc_lower for x in ['addebito', 'spese', 'commissione', 'pagamento',
                    'bonifico a favore', 'prelievo']):
                is_entrata = False
            
            transaction = {
                "data": self._parse_date(data_contabile),
                "data_valuta": self._parse_date(data_valuta),
                "causale_abi": causale_abi,
                "descrizione": descrizione[:500],
                "entrata": importo if is_entrata else None,
                "uscita": importo if not is_entrata else None,
                "importo": importo if is_entrata else -importo,
                "banca": "BNL"
            }
            
            if transaction["data"]:
                self.transactions.append(transaction)
    
    def _parse_nexi(self, text: str, tables: List[Dict]) -> None:
        """Parse specifico per estratti conto Nexi (carte di credito)."""
        
        # Pattern per movimenti Nexi
        pattern = r'(\d{2}[./]\d{2}[./]\d{2,4})\s+(.+?)\s+([\d.,]+)\s*(?:€|EUR)?'
        
        for match in re.finditer(pattern, text):
            data = match.group(1)
            descrizione = match.group(2).strip()
            importo = self._parse_amount(match.group(3))
            
            # Salta righe non rilevanti
            if any(x in descrizione.upper() for x in ['SALDO', 'TOTALE', 'LIMITE']):
                continue
            
            transaction = {
                "data": self._parse_date(data),
                "descrizione": descrizione[:500],
                "entrata": None,
                "uscita": importo,  # Carta = sempre uscite
                "importo": -importo,
                "banca": "NEXI"
            }
            
            if transaction["data"]:
                self.transactions.append(transaction)
    
    def _parse_generic(self, text: str, tables: List[Dict]) -> None:
        """Parser generico per banche non riconosciute."""
        
        # Prova prima con le tabelle estratte
        for table_info in tables:
            table = table_info["data"]
            if not table or len(table) < 2:
                continue
            
            # Cerca header con date e importi
            header = table[0] if table else []
            header_str = ' '.join(str(h) for h in header if h).lower()
            
            if any(x in header_str for x in ['data', 'valuta', 'importo', 'dare', 'avere']):
                # Trova indici colonne
                date_col = None
                desc_col = None
                dare_col = None
                avere_col = None
                
                for idx, h in enumerate(header):
                    h_lower = str(h).lower() if h else ""
                    if 'data' in h_lower and date_col is None:
                        date_col = idx
                    elif any(x in h_lower for x in ['descrizione', 'operazione', 'causale']):
                        desc_col = idx
                    elif any(x in h_lower for x in ['dare', 'uscita', 'debito']):
                        dare_col = idx
                    elif any(x in h_lower for x in ['avere', 'entrata', 'credito']):
                        avere_col = idx
                
                # Estrai righe
                for row in table[1:]:
                    if not row or len(row) < 3:
                        continue
                    
                    try:
                        data = self._parse_date(str(row[date_col])) if date_col is not None else None
                        descrizione = str(row[desc_col]) if desc_col is not None else ""
                        dare = self._parse_amount(str(row[dare_col])) if dare_col is not None and row[dare_col] else 0
                        avere = self._parse_amount(str(row[avere_col])) if avere_col is not None and row[avere_col] else 0
                        
                        if data and (dare or avere):
                            self.transactions.append({
                                "data": data,
                                "descrizione": descrizione[:500],
                                "entrata": avere if avere else None,
                                "uscita": dare if dare else None,
                                "importo": avere - dare,
                                "banca": "GENERICA"
                            })
                    except:
                        continue
        
        # Se nessuna tabella ha funzionato, prova regex
        if not self.transactions:
            self._parse_generic_regex(text)
    
    def _parse_generic_regex(self, text: str) -> None:
        """Fallback regex per estratti conto generici."""
        
        # Pattern generico: data + testo + importo
        pattern = r'(\d{2}[./]\d{2}[./]\d{2,4})\s+(.{10,100}?)\s+([\d.,]+)(?:\s*[-€])?'
        
        for match in re.finditer(pattern, text):
            data = match.group(1)
            descrizione = match.group(2).strip()
            importo_str = match.group(3)
            
            # Salta righe non rilevanti
            if any(x in descrizione.upper() for x in ['SALDO', 'TOTALE', 'PAGINA', 'ESTRATTO']):
                continue
            
            importo = self._parse_amount(importo_str)
            if importo == 0:
                continue
            
            # Euristica per determinare entrata/uscita
            desc_lower = descrizione.lower()
            is_entrata = any(x in desc_lower for x in ['accredito', 'versamento', 'bonifico da',
                    'stipendio', 'rimborso', 'interessi'])
            
            transaction = {
                "data": self._parse_date(data),
                "descrizione": descrizione[:500],
                "entrata": importo if is_entrata else None,
                "uscita": importo if not is_entrata else None,
                "importo": importo if is_entrata else -importo,
                "banca": "GENERICA"
            }
            
            if transaction["data"]:
                self.transactions.append(transaction)
    
    def _deduplicate_transactions(self) -> None:
        """Rimuove transazioni duplicate e dati invalidi."""
        seen = set()
        unique = []
        
        for t in self.transactions:
            desc = t.get("descrizione", "")
            importo = abs(t.get("importo", 0))
            data_valuta = t.get("data_valuta")
            
            # Filtra dati dal riassunto scalare:
            # - Hanno descrizione generica "Movimento" 
            # - Non hanno data_valuta
            # - Sono generalmente importi alti (saldi)
            if (not desc or desc == "Movimento" or len(desc) < 5):
                # Se non ha data valuta, è quasi certamente un dato dal riassunto scalare
                if not data_valuta:
                    continue
                # Se ha importo molto alto senza descrizione, è un saldo
                if importo > 10000:
                    continue
            
            key = (t.get("data"), desc[:50], t.get("importo"))
            if key not in seen:
                seen.add(key)
                unique.append(t)
        
        self.transactions = unique
    
    def _parse_date(self, date_str: str) -> Optional[str]:
        """Converte una data in formato ISO YYYY-MM-DD."""
        if not date_str:
            return None
        
        try:
            date_str = date_str.strip()
            
            # Rimuovi caratteri non numerici extra
            date_str = re.sub(r'[^\d./\-]', '', date_str)
            
            # Supporta vari formati
            for sep in ['/', '.', '-']:
                if sep in date_str:
                    parts = date_str.split(sep)
                    if len(parts) == 3:
                        day = int(parts[0])
                        month = int(parts[1])
                        year = int(parts[2])
                        
                        # Normalizza anno
                        if year < 100:
                            year = 2000 + year if year < 50 else 1900 + year
                        
                        # Valida
                        if 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100:
                            return f"{year}-{month:02d}-{day:02d}"
            
            return None
        except:
            return None
    
    def _parse_amount(self, amount_str: str) -> float:
        """Converte un importo stringa in float."""
        if not amount_str:
            return 0.0
        
        try:
            # Pulisci la stringa
            amount_str = str(amount_str).strip()
            amount_str = amount_str.replace('€', '').replace(' ', '')
            
            # Gestisci negativo
            is_negative = amount_str.startswith('-') or amount_str.endswith('-')
            amount_str = amount_str.replace('-', '')
            
            # Formato italiano: 1.234,56 -> 1234.56
            if ',' in amount_str:
                # Rimuovi i punti delle migliaia e sostituisci virgola con punto
                amount_str = amount_str.replace('.', '').replace(',', '.')
            
            value = float(amount_str)
            return -value if is_negative else value
        except:
            return 0.0


def parse_bank_statement(pdf_content: bytes) -> Dict[str, Any]:
    """
    Funzione wrapper per il parsing universale di estratti conto.
    
    Args:
        pdf_content: Contenuto binario del file PDF
        
    Returns:
        Dizionario con metadata e lista transazioni
    """
    parser = UniversalBankStatementParser()
    return parser.parse_pdf(pdf_content)
