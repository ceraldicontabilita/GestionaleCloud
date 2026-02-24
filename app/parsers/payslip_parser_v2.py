"""
Parser Migliorato per Buste Paga - Multi-formato
Supporta: CSC, Zucchetti (con 's'), LUL, formati standard

Estrae e salva in riepilogo_cedolini:
- Nome dipendente
- Periodo busta paga
- Periodo competenza
- Netto in busta
- Lordo
- Detrazioni
- IBAN pagamento
"""
import fitz  # PyMuPDF
import re
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class PayslipParserMultiFormat:
    """Parser multi-formato per buste paga italiane."""
    
    MESI_MAP = {
        'gennaio': 1, 'febbraio': 2, 'marzo': 3, 'aprile': 4,
        'maggio': 5, 'giugno': 6, 'luglio': 7, 'agosto': 8,
        'settembre': 9, 'ottobre': 10, 'novembre': 11, 'dicembre': 12
    }
    
    def __init__(self, pdf_path: str = None, pdf_content: bytes = None):
        self.pdf_path = pdf_path
        self.pdf_content = pdf_content
        self.format_detected = None
    
    def _detect_format(self, text: str) -> str:
        """Rileva il formato della busta paga."""
        if "Software CSC" in text or "CSC - Napoli" in text:
            return "csc"
        elif "sZUCCHETTI" in text or "NETTOsDELsMESE" in text or "COGNOMEsEsNOME" in text:
            return "zucchetti_s"
        elif "ZUCCHETTI" in text or "zucchetti.it" in text:
            if "TIMBRATURE" in text or "GIUSTIFICATIVI" in text:
                return "lul_presenze"  # Foglio presenze, non busta paga
            return "zucchetti"
        elif "LIBRO UNICO" in text or "LUL" in text:
            return "lul"
        return "standard"
    
    def _clean_zucchetti_s(self, text: str) -> str:
        """Pulisce il testo Zucchetti con 's' al posto degli spazi."""
        # Sostituisci 's' isolate con spazi
        text = re.sub(r'(?<=[a-zA-Z])s(?=[A-Z])', ' ', text)
        text = re.sub(r'(?<=[a-z])s(?=[a-z])', ' ', text)
        return text
    
    def _parse_amount(self, value: str) -> float:
        """Converte importo italiano in float."""
        if not value:
            return 0.0
        value = str(value).strip()
        value = value.replace(' ', '').replace('.', '').replace(',', '.').replace('€', '').replace('+', '').replace('-', '')
        try:
            return float(value)
        except:
            return 0.0
    
    def _extract_mese_anno(self, text: str) -> Dict[str, int]:
        """Estrae mese e anno."""
        # Pattern per vari formati
        patterns = [
            r'(Gennaio|Febbraio|Marzo|Aprile|Maggio|Giugno|Luglio|Agosto|Settembre|Ottobre|Novembre|Dicembre)\s+(\d{4})',
            r'(GENNAIO|FEBBRAIO|MARZO|APRILE|MAGGIO|GIUGNO|LUGLIO|AGOSTO|SETTEMBRE|OTTOBRE|NOVEMBRE|DICEMBRE)\s+(\d{4})',
            r'Periodo.*?(\d{2})/(\d{4})',
            r'(\d{2})/(\d{4})\s+[A-Z]',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                if match.group(1).isdigit():
                    return {'mese': int(match.group(1)), 'anno': int(match.group(2))}
                else:
                    mese_nome = match.group(1).lower()
                    return {'mese': self.MESI_MAP.get(mese_nome, 0), 'anno': int(match.group(2))}
        
        return {'mese': 0, 'anno': 0}
    
    def _extract_cf(self, text: str) -> Optional[str]:
        """Estrae codice fiscale."""
        match = re.search(r'[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]', text)
        return match.group(0) if match else None
    
    def _extract_nome(self, text: str, formato: str) -> Optional[str]:
        """Estrae nome dipendente in base al formato."""
        
        if formato == "csc":
            # Formato CSC: DATA NOME DATA CF
            match = re.search(r'\d{2}/\d{2}/\d{4}\s+([A-Z][A-Z\s]+[A-Z])\s+\d{2}/\d{2}/\d{4}\s+[A-Z]{6}\d{2}', text)
            if match:
                return match.group(1).strip()
        
        elif formato == "zucchetti_s" or formato == "zucchetti":
            # Pattern Zucchetti: cerca "000XXXX COGNOME NOME CF"
            cf = self._extract_cf(text)
            if cf:
                # Cerca il pattern con codice dipendente prima del nome
                pattern = re.compile(r'(\d{7})\s+([A-Z][A-Z]+\s+[A-Z][A-Z]+)\s+' + cf)
                match = pattern.search(text)
                if match:
                    return match.group(2).strip()
                
                # Pattern alternativo: COGNOME NOME su riga separata prima del CF
                lines = text.split('\n')
                for i, line in enumerate(lines):
                    if cf in line:
                        # Guarda le righe precedenti per il nome
                        for j in range(max(0, i-3), i):
                            prev_line = lines[j].strip()
                            # Cerca riga con solo nome (2-3 parole maiuscole)
                            if re.match(r'^[A-Z][A-Z]+\s+[A-Z][A-Z]+\s*$', prev_line):
                                return prev_line.strip()
                        # Cerca nella stessa riga
                        before_cf = line[:line.index(cf)]
                        words = re.findall(r'[A-Z]{2,}', before_cf)
                        if len(words) >= 2:
                            # Prendi le ultime 2 parole come cognome nome
                            return ' '.join(words[-2:])
        
        # Pattern generico: cerca CF e nome vicino
        cf = self._extract_cf(text)
        if cf:
            lines = text.split('\n')
            for i, line in enumerate(lines):
                if cf in line:
                    # Cerca pattern COGNOME NOME CF
                    match = re.search(r'([A-Z][A-Z]+\s+[A-Z][A-Z]+)\s+' + cf, line)
                    if match:
                        return match.group(1).strip()
                    
                    # Estrai parole maiuscole prima del CF
                    before_cf = line[:line.index(cf)]
                    words = re.findall(r'[A-Z]{2,}', before_cf)
                    if len(words) >= 2:
                        return ' '.join(words[-2:])
        
        return None
    
    def _extract_netto(self, text: str, formato: str) -> float:
        """Estrae il netto in busta."""
        patterns = [
            r'NETTO\s*(?:DEL\s*)?MESE\s*[:\s€]*([0-9.,]+)',
            r'NETTOsDELsMESE\s*[:\s€]*([0-9.,]+)',
            r'NETTO\s*IN\s*BUSTA\s*[:\s€]*([0-9.,]+)',
            r'TOTALE\s*NETTO\s*[:\s€]*([0-9.,]+)',
            r'NETTO\s*DA\s*PAGARE\s*[:\s€]*([0-9.,]+)',
            r'([0-9.,]+)\s*€\s*$',  # Importo finale con €
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
            if match:
                val = self._parse_amount(match.group(1))
                if val > 0:
                    return val
        
        return 0.0
    
    def _extract_lordo(self, text: str) -> float:
        """Estrae il lordo / totale competenze."""
        patterns = [
            r'TOTALE\s*COMPETENZE\s*[:\s€]*([0-9.,]+)',
            r'TOTALEsCOMPETENZE\s*[:\s€]*([0-9.,]+)',
            r'IMPONIBILE\s*FISCALE\s*[:\s€]*([0-9.,]+)',
            r'TOTALE\s*LORDO\s*[:\s€]*([0-9.,]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = self._parse_amount(match.group(1))
                if val > 0:
                    return val
        
        return 0.0
    
    def _extract_trattenute(self, text: str) -> float:
        """Estrae le trattenute totali."""
        patterns = [
            r'TOTALE\s*TRATTENUTE\s*[:\s€]*([0-9.,]+)',
            r'TOTALEsTRATTENUTE\s*[:\s€]*([0-9.,]+)',
            r'RITENUTE\s*PREVIDENZIALI\s*[:\s€]*[0-9.,]+\s*[0-9.,]+\s*([0-9.,]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val = self._parse_amount(match.group(1))
                if val > 0:
                    return val
        
        return 0.0
    
    def _extract_detrazioni(self, text: str) -> float:
        """Estrae le detrazioni fiscali."""
        patterns = [
            r'Detrazioni\s*lav\.?\s*dip\.?\s*([0-9.,]+)',
            r'DETRAZIONI\s*[:\s€]*([0-9.,]+)',
            r'Detraz\.\s*fiscali\s*([0-9.,]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return self._parse_amount(match.group(1))
        
        return 0.0
    
    def _extract_iban(self, text: str) -> Optional[str]:
        """Estrae IBAN."""
        match = re.search(r'(IT[0-9]{2}[A-Z][0-9A-Z]{22})', text)
        return match.group(1) if match else None
    
    def _extract_tfr(self, text: str) -> float:
        """Estrae TFR quota anno."""
        patterns = [
            r'Quota\s*anno\s*([0-9.,]+)',
            r'T\.?F\.?R\.?\s*quota\s*([0-9.,]+)',
            r'RETRIBUZIONE\s*T\.?F\.?R\.?\s*[0-9.,]+\s*([0-9.,]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return self._parse_amount(match.group(1))
        
        return 0.0
    
    def _extract_ore_lavorate(self, text: str) -> float:
        """Estrae ore lavorate."""
        patterns = [
            r'Ore\s*ordinarie\s*([0-9.,]+)',
            r'ORE\s*LAVORATE\s*([0-9.,]+)',
            r'(\d+)[,.](\d+)\s*hm',  # Formato ore/minuti
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if match.lastindex == 2:
                    # Formato ore,minuti
                    ore = int(match.group(1))
                    minuti = int(match.group(2)) / 60 if match.group(2) else 0
                    return ore + minuti
                return self._parse_amount(match.group(1))
        
        return 0.0
    
    def parse(self) -> List[Dict[str, Any]]:
        """Analizza il PDF e restituisce lista di cedolini."""
        results = []
        
        try:
            if self.pdf_content:
                doc = fitz.open(stream=self.pdf_content, filetype="pdf")
            else:
                doc = fitz.open(self.pdf_path)
            
            for page_num, page in enumerate(doc):
                text = page.get_text()
                
                if not text.strip():
                    continue
                
                # Rileva formato
                formato = self._detect_format(text)
                self.format_detected = formato
                
                # Se è un foglio presenze (LUL), salta
                if formato == "lul_presenze":
                    continue
                
                # Pulisci testo se formato Zucchetti con 's'
                if formato == "zucchetti_s":
                    text_clean = self._clean_zucchetti_s(text)
                else:
                    text_clean = text
                
                # Estrai codice fiscale (indica busta paga valida)
                cf = self._extract_cf(text)
                if not cf:
                    continue
                
                # Estrai dati
                nome = self._extract_nome(text, formato)
                periodo = self._extract_mese_anno(text)
                netto = self._extract_netto(text, formato)
                lordo = self._extract_lordo(text)
                trattenute = self._extract_trattenute(text)
                detrazioni = self._extract_detrazioni(text)
                iban = self._extract_iban(text)
                tfr = self._extract_tfr(text)
                ore = self._extract_ore_lavorate(text)
                
                # Se non ha netto, potrebbe essere foglio presenze
                if netto == 0 and lordo == 0:
                    continue
                
                cedolino = {
                    "nome_dipendente": nome,
                    "codice_fiscale": cf,
                    "mese": periodo.get('mese'),
                    "anno": periodo.get('anno'),
                    "periodo_competenza": f"{periodo.get('mese', 0):02d}/{periodo.get('anno', 0)}",
                    "netto_mese": netto,
                    "lordo": lordo,
                    "totale_trattenute": trattenute,
                    "detrazioni_fiscali": detrazioni,
                    "tfr_quota": tfr,
                    "ore_lavorate": ore,
                    "iban": iban,
                    "formato_rilevato": formato,
                    "pagina": page_num + 1
                }
                
                results.append(cedolino)
            
            doc.close()
            
        except Exception as e:
            logger.error(f"Errore parsing busta paga: {e}")
        
        return results


def parse_payslip_pdf(pdf_path: str = None, pdf_content: bytes = None) -> List[Dict[str, Any]]:
    """Funzione wrapper per parsing buste paga."""
    parser = PayslipParserMultiFormat(pdf_path=pdf_path, pdf_content=pdf_content)
    return parser.parse()
