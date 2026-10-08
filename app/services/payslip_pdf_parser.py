"""
Parser per estrarre dati dalle buste paga PDF (Libro Unico del Lavoro).
Estrae: dipendente, retribuzione utile TFR, lordo, netto, periodo.
Versione migliorata con estrazione di: ore, paga oraria, straordinari, ferie, qualifica.
"""
import pdfplumber
import re
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class PayslipPDFParser:
    """Parser per PDF delle buste paga italiane (formato Zucchetti/standard)."""
    
    # Pattern per estrarre dati - MIGLIORATI per formato CSC/Zucchetti
    PATTERNS = {
        'codice_fiscale': r'[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]',
        'retribuzione_tfr': r'(?:Retribuzione\s+utile\s+T\.?F\.?R\.?|_RE_T_R_I_B_UZ_I_O_N_E_\s*T\.?F\.?R\.?|Retribuzione utile T\.F\.R\.)\s*[:\s_]*(?:\d+[,.]?\d*%?)?\s*([0-9.,]+)\+?',
        'netto_mese': r'(?:NETTO\s*(?:DEL\s*)?MESE|NETTO\s*IN\s*BUSTA|NETTO\s*DA\s*PAGARE|NETTOsDELsMESE)\s*[:\s€]*([0-9.,]+)',
        'totale_competenze': r'(?:_?TO_?T_?A_?L_?E_?\s*_?C_?O_?M_?P_?E_?T_?E_?N_?Z_?E_?|TOTALE\s*COMPETENZE|TOTALEsCOMPETENZE)\s*[:\s€_]*([0-9.,]+)',
        'totale_trattenute': r'(?:TOTALE\s*TRATTENUTE|_?TO_?TA_?LE_?\s*TR_?AT_?TE_?NU_?TE_?|TOTALEsTRATTENUTE)\s*[:\s€_]*([0-9.,]+)',
        'periodo': r'Periodo\s+di\s+riferimento[:\s]*(\w+\s+\d{4})',
        'mese_anno': r'(GENNAIO|FEBBRAIO|MARZO|APRILE|MAGGIO|GIUGNO|LUGLIO|AGOSTO|SETTEMBRE|OTTOBRE|NOVEMBRE|DICEMBRE)\s+(\d{4})|(?:Gennaio|Febbraio|Marzo|Aprile|Maggio|Giugno|Luglio|Agosto|Settembre|Ottobre|Novembre|Dicembre)\s+(\d{4})',
        # NUOVI PATTERN
        'ore_ordinarie': r'(?:Ore\s*ordinarie|ORE\s*ORD|ore\s*ord|Oreordinarie)[:\s]*(\d+(?:[.,]\d+)?)',
        'ore_straordinarie': r'(?:Ore\s*straordinarie|straordinarie|ORE\s*STRAORD|Orestraordinarie)[:\s]*(\d+(?:[.,]\d+)?)',
        'ore_lavorate_tabella': r'(\d+)\s+(\d+)\s+(\d+(?:[.,]\d+)?)\s+(?:ORE|ore)',
        'paga_base': r'(?:PAGA\s*BASE|\d\)\s*PAGA\s*BASE)[:\s]*([0-9.,]+)',
        'contingenza': r'(?:CONTINGENZA|CONTING\.?|\d\)\s*CONTINGENZA)[:\s]*([0-9.,]+)',
        'livello': r"(\d+'?\s*Livello|\d+°\s*Livello|Livello\s*\d+|\d+\s*LIV|\d+'\s*Livello)",
        'qualifica': r'(CAMERIERE|CUOCO|BARISTA|AIUTO CUOCO|LAVAPIATTI|PIZZAIOLO|COMMIS|CHEF|RECEPTIONIST|BANCONIERE|ADDETTO|OPE)',
        'part_time': r'(?:Part\s*Time|%P\.?T\.?)\s*(\d+)[,.]?(\d*)\s*%?',
        'iban': r'(?:IBAN)?\s*(IT[0-9]{2}[A-Z][0-9]{10}[0-9A-Z]{12})',
        'ferie_maturate': r'(?:Ferie|Mat\.)\s*([0-9.,]+)\+?\s*(?:God\.)\s*([0-9.,]+)',
        'permessi': r'Permessi[:\s]*([0-9.,]+)\s+([0-9.,]+)',
        'tfr_quota_anno': r'Quota\s*anno[:\s]*([0-9.,]+)',
        'tfr_fondo': r'T\.?F\.?R\.?\s*F\.?do[:\s]*([0-9.,]+)',
        'matricola': r'(?:Matricola|Mat\.)[:\s]*(\d+)|Nr\.\s*(\d+)',
        'data_assunzione': r'(?:Data\s*Assunzione|DATA\s*ASSUNZIONE|DatasAssunzione)[:\s]*(\d{2}[-/]\d{2}[-/]\d{4})',
        # Pattern per nome dipendente nel formato CSC
        'nome_dopo_data': r'\d{2}/\d{2}/\d{4}\s+([A-Z][A-Z\s]+[A-Z])\s+\d{2}/\d{2}/\d{4}',
    }
    
    MESI_MAP = {
        'Gennaio': 1, 'Febbraio': 2, 'Marzo': 3, 'Aprile': 4,
        'Maggio': 5, 'Giugno': 6, 'Luglio': 7, 'Agosto': 8,
        'Settembre': 9, 'Ottobre': 10, 'Novembre': 11, 'Dicembre': 12
    }
    
    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)
        self.extracted_data: List[Dict[str, Any]] = []
    
    def _parse_italian_number(self, value: str) -> float:
        """Converte numero italiano (1.234,56) in float."""
        if not value:
            return 0.0
        # Rimuovi spazi
        value = value.strip()
        # Formato italiano: 1.234,56 -> 1234.56
        value = value.replace('.', '').replace(',', '.')
        try:
            return float(value)
        except ValueError:
            return 0.0
    
    def _extract_employee_name(self, text: str) -> Optional[str]:
        """Estrae il nome del dipendente dal testo."""
        # Cerca pattern comune: "COGNOME NOME" dopo "Dipendente:" o all'inizio
        lines = text.split('\n')
        
        # Pattern 1: Cerca nel formato CSC "DATA NOME COGNOME DATA CF"
        # Es: "31/12/2019 VESPA VINCENZO 26/12/1967 VSPVCN67T26F839P"
        cf_pattern = re.compile(r'(\d{2}/\d{2}/\d{4})\s+([A-Z][A-Z\s]+)\s+(\d{2}/\d{2}/\d{4})\s+([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])')
        match = cf_pattern.search(text)
        if match:
            nome = match.group(2).strip()
            # Rimuovi eventuali caratteri extra
            nome = re.sub(r'\s+', ' ', nome)
            if len(nome) > 3:
                return nome.upper()
        
        # Pattern 2: Nome sulla stessa riga del CF
        for line in lines:
            cf_match = re.search(self.PATTERNS['codice_fiscale'], line)
            if cf_match:
                # Cerca nome prima del CF nella stessa riga
                before_cf = line[:cf_match.start()]
                # Trova parole che sembrano nomi (maiuscole)
                words = re.findall(r'[A-Z][A-Za-z]+', before_cf)
                if len(words) >= 2:
                    # Prendi ultime 2-3 parole come nome
                    nome = ' '.join(words[-3:] if len(words) >= 3 else words[-2:])
                    if len(nome) > 3:
                        return nome.upper()
        
        # Pattern 3: Cerca riga precedente al CF
        for i, line in enumerate(lines):
            if re.search(self.PATTERNS['codice_fiscale'], line):
                if i > 0:
                    potential_name = lines[i-1].strip()
                    if re.match(r'^[A-Za-zÀ-ú\s]+$', potential_name) and len(potential_name) > 3:
                        return potential_name.upper()
        
        # Pattern 4: cerca "Dipendente:"
        for line in lines:
            if 'Dipendente' in line or 'DIPENDENTE' in line:
                parts = line.split(':')
                if len(parts) > 1:
                    return parts[1].strip().upper()
        
        return None
    
    def _extract_codice_fiscale(self, text: str) -> Optional[str]:
        """Estrae il codice fiscale dal testo."""
        match = re.search(self.PATTERNS['codice_fiscale'], text)
        return match.group(0) if match else None
    
    def _extract_periodo(self, text: str) -> Dict[str, int]:
        """Estrae mese e anno dal testo."""
        # Cerca pattern "Maggio 2025"
        match = re.search(self.PATTERNS['mese_anno'], text, re.IGNORECASE)
        if match:
            mese_nome = match.group(1).capitalize()
            anno = int(match.group(2))
            mese = self.MESI_MAP.get(mese_nome, 0)
            return {'mese': mese, 'anno': anno}
        return {'mese': 0, 'anno': 0}
    
    def _extract_amount(self, text: str, pattern_name: str) -> float:
        """Estrae un importo usando un pattern specifico."""
        pattern = self.PATTERNS.get(pattern_name)
        if not pattern:
            return 0.0
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return self._parse_italian_number(match.group(1))
        return 0.0
    
    def _extract_pattern(self, text: str, pattern_name: str) -> Optional[str]:
        """Estrae un valore testuale usando un pattern specifico."""
        pattern = self.PATTERNS.get(pattern_name)
        if not pattern:
            return None
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            # Restituisce il primo gruppo o l'intero match
            return match.group(1) if match.lastindex else match.group(0)
        return None
    
    def _extract_ferie(self, text: str) -> Dict[str, float]:
        """Estrae dati ferie: residuo, maturato, goduto, saldo."""
        result = {'residuo': 0, 'maturato': 0, 'goduto': 0, 'saldo': 0}
        # Cerca riga ferie con numeri
        ferie_match = re.search(r'Ferie\s+([0-9.,]+)\s+([0-9.,]+)\s+([0-9.,]+)\s+([0-9.,]+)?', text, re.IGNORECASE)
        if ferie_match:
            result['residuo'] = self._parse_italian_number(ferie_match.group(1))
            result['maturato'] = self._parse_italian_number(ferie_match.group(2))
            result['goduto'] = self._parse_italian_number(ferie_match.group(3))
            if ferie_match.group(4):
                result['saldo'] = self._parse_italian_number(ferie_match.group(4))
            else:
                result['saldo'] = result['residuo'] + result['maturato'] - result['goduto']
        return result
    
    def _extract_permessi(self, text: str) -> Dict[str, float]:
        """Estrae dati permessi."""
        result = {'maturato': 0, 'goduto': 0, 'saldo': 0}
        permessi_match = re.search(r'Permessi\s+([0-9.,]+)\s+([0-9.,]+)\s*([0-9.,]+)?', text, re.IGNORECASE)
        if permessi_match:
            result['maturato'] = self._parse_italian_number(permessi_match.group(1))
            result['goduto'] = self._parse_italian_number(permessi_match.group(2))
            if permessi_match.group(3):
                result['saldo'] = self._parse_italian_number(permessi_match.group(3))
            else:
                result['saldo'] = result['maturato'] - result['goduto']
        return result
    
    def _extract_matricola(self, text: str) -> Optional[str]:
        """Estrae il numero di matricola."""
        # Prova pattern "Nr. 12345" o "Matricola: 12345"
        match = re.search(r'Nr\.\s*(\d+)|Matricola[:\s]*(\d+)', text)
        if match:
            return match.group(1) or match.group(2)
        return None
    
    def parse_page(self, page) -> Optional[Dict[str, Any]]:
        """Analizza una singola pagina del PDF."""
        text = page.extract_text() or ""
        
        if not text.strip():
            return None
        
        # Estrai codice fiscale (indica che è una busta paga)
        cf = self._extract_codice_fiscale(text)
        if not cf:
            return None
        
        # Estrai dati base
        nome = self._extract_employee_name(text)
        periodo = self._extract_periodo(text)
        
        # Per estrazione importi, usa testo pulito (senza underscore)
        text_clean = text.replace('_', ' ')
        text_clean = re.sub(r'\s+', ' ', text_clean)  # Normalizza spazi multipli
        
        # Estrai importi base dal testo pulito
        retrib_tfr = self._extract_amount(text_clean, 'retribuzione_tfr')
        netto = self._extract_amount(text_clean, 'netto_mese')
        competenze = self._extract_amount(text_clean, 'totale_competenze')
        trattenute = self._extract_amount(text_clean, 'totale_trattenute')
        
        # Fallback: cerca pattern specifici per formato CSC
        if competenze == 0:
            # Pattern per formato con underscore nell'importo
            comp_match = re.search(r'_?TO_?T_?A_?L_?E_?\s*_?C_?O_?M_?P_?E_?T_?E_?N_?Z_?E_?[_\s]*([0-9_.,]+)\+?', text, re.IGNORECASE)
            if comp_match:
                # Rimuovi underscore dall'importo
                importo_str = comp_match.group(1).replace('_', '')
                competenze = self._parse_italian_number(importo_str)
            else:
                # Pattern semplice
                comp_match = re.search(r'TOTALE\s*COMPETENZE[^\d]*([0-9.,]+)', text_clean, re.IGNORECASE)
                if comp_match:
                    competenze = self._parse_italian_number(comp_match.group(1))
        
        # Formato Zucchetti con 's' invece di spazi
        if competenze == 0:
            comp_match = re.search(r'TOTALEsCOMPETENZE\s*([0-9.,]+)', text, re.IGNORECASE)
            if comp_match:
                competenze = self._parse_italian_number(comp_match.group(1))
        
        if trattenute == 0:
            tratt_match = re.search(r'TOTALE\s*TRATTENUTE[^\d]*([0-9.,]+)', text_clean, re.IGNORECASE)
            if tratt_match:
                trattenute = self._parse_italian_number(tratt_match.group(1))
        
        # Formato Zucchetti con 's'
        if trattenute == 0:
            tratt_match = re.search(r'TOTALEsTRATTENUTE\s*([0-9.,]+)', text, re.IGNORECASE)
            if tratt_match:
                trattenute = self._parse_italian_number(tratt_match.group(1))
        
        # Netto formato Zucchetti
        if netto == 0:
            netto_match = re.search(r'NETTOsDELsMESE\s*([0-9.,]+)', text, re.IGNORECASE)
            if netto_match:
                netto = self._parse_italian_number(netto_match.group(1))
        
        # Se non c'è netto esplicito ma ci sono competenze e trattenute, calcolalo
        if netto == 0 and competenze > 0 and trattenute > 0:
            netto = competenze - trattenute
        
        # Pattern alternativo per netto: cerca "LIRE : X" o pattern finale
        if netto == 0:
            lire_match = re.search(r'LIRE\s*:\s*([0-9.,]+)', text)
            if lire_match:
                # Converti lire in euro (tasso fisso 1936.27)
                lire = self._parse_italian_number(lire_match.group(1))
                if lire > 10000:  # Probabilmente in lire
                    netto = round(lire / 1936.27, 2)
                else:
                    netto = lire
        
        # === NUOVI DATI ESTRATTI ===
        
        # Ore lavorate
        ore_ordinarie = self._extract_amount(text, 'ore_ordinarie')
        ore_straordinarie = self._extract_amount(text, 'ore_straordinarie')
        
        # Pattern alternativo per ore dalla tabella (formato Zucchetti)
        if ore_ordinarie == 0:
            ore_match = re.search(r'(\d+)\s+(\d+)\s+(\d+)[,.]?(\d*)\s+(?:ORE|ore|\d+[,.])', text)
            if ore_match:
                ore_ordinarie = float(ore_match.group(3) + ('.' + ore_match.group(4) if ore_match.group(4) else ''))
        
        # Paga
        paga_base = self._extract_amount(text, 'paga_base')
        contingenza = self._extract_amount(text, 'contingenza')
        paga_oraria = paga_base + contingenza if paga_base > 0 else 0
        
        # Qualifica e livello
        livello = self._extract_pattern(text, 'livello')
        qualifica = self._extract_pattern(text, 'qualifica')
        
        # Part-time
        part_time_match = re.search(self.PATTERNS['part_time'], text)
        if part_time_match:
            intero = part_time_match.group(1)
            decimale = part_time_match.group(2) if part_time_match.group(2) else '0'
            part_time_percent = float(f"{intero}.{decimale}")
        else:
            part_time_percent = 100.0
        
        # Ferie e permessi
        ferie_data = self._extract_ferie(text)
        permessi_data = self._extract_permessi(text)
        
        # TFR progressivi
        tfr_quota_anno = self._extract_amount(text, 'tfr_quota_anno')
        tfr_fondo = self._extract_amount(text, 'tfr_fondo')
        
        # Matricola
        matricola = self._extract_matricola(text)
        
        # Data assunzione
        data_assunzione = self._extract_pattern(text, 'data_assunzione')
        
        # IBAN (se presente)
        iban = self._extract_pattern(text, 'iban')
        
        # Se non ci sono dati significativi, salta
        if retrib_tfr == 0 and netto == 0 and competenze == 0:
            return None
        
        return {
            'codice_fiscale': cf,
            'nome_dipendente': nome or 'SCONOSCIUTO',
            'mese': periodo['mese'],
            'anno': periodo['anno'],
            'retribuzione_utile_tfr': round(retrib_tfr, 2),
            'netto_mese': round(netto, 2),
            'totale_competenze': round(competenze, 2),
            'totale_trattenute': round(trattenute, 2),
            # NUOVI CAMPI
            'ore_ordinarie': round(ore_ordinarie, 2),
            'ore_straordinarie': round(ore_straordinarie, 2),
            'ore_totali': round(ore_ordinarie + ore_straordinarie, 2),
            'paga_base': round(paga_base, 5),
            'contingenza': round(contingenza, 5),
            'paga_oraria': round(paga_oraria, 5),
            'livello': livello,
            'qualifica': qualifica,
            'part_time_percent': part_time_percent,
            'ferie': ferie_data,
            'permessi': permessi_data,
            'tfr_quota_anno': round(tfr_quota_anno, 2),
            'tfr_fondo': round(tfr_fondo, 2),
            'matricola': matricola,
            'data_assunzione': data_assunzione,
            'iban': iban,
            'raw_text_preview': text[:500]  # Per debug
        }
    
    def parse(self) -> List[Dict[str, Any]]:
        """Analizza l'intero PDF e restituisce i dati estratti."""
        if not self.pdf_path.exists():
            logger.error(f"File non trovato: {self.pdf_path}")
            return []
        
        try:
            with pdfplumber.open(self.pdf_path) as pdf:
                for i, page in enumerate(pdf.pages):
                    try:
                        data = self.parse_page(page)
                        if data:
                            data['page_number'] = i + 1
                            self.extracted_data.append(data)
                    except Exception as e:
                        logger.warning(f"Errore pagina {i+1}: {e}")
                        continue
        except Exception as e:
            logger.error(f"Errore apertura PDF {self.pdf_path}: {e}")
            return []
        
        return self.extracted_data
    
    def get_tfr_by_employee(self) -> Dict[str, Dict[str, Any]]:
        """
        Raggruppa i dati TFR per dipendente.
        Ritorna dizionario con codice_fiscale come chiave.
        """
        if not self.extracted_data:
            self.parse()
        
        result = {}
        for data in self.extracted_data:
            cf = data['codice_fiscale']
            if cf not in result:
                result[cf] = {
                    'codice_fiscale': cf,
                    'nome': data['nome_dipendente'],
                    'mesi': [],
                    'totale_retrib_tfr': 0
                }
            
            result[cf]['mesi'].append({
                'mese': data['mese'],
                'anno': data['anno'],
                'retribuzione_utile_tfr': data['retribuzione_utile_tfr']
            })
            result[cf]['totale_retrib_tfr'] += data['retribuzione_utile_tfr']
        
        # Arrotonda totali
        for cf in result:
            result[cf]['totale_retrib_tfr'] = round(result[cf]['totale_retrib_tfr'], 2)
        
        return result


def parse_all_payslips(folder_path: str) -> List[Dict[str, Any]]:
    """
    Analizza tutti i PDF in una cartella.
    Ritorna lista aggregata per dipendente.
    """
    folder = Path(folder_path)
    all_data = {}
    
    for pdf_file in folder.glob("*.pdf"):
        # Salta file F24 e Riepilogo
        if 'F24' in pdf_file.name or 'Riepilogo' in pdf_file.name:
            continue
        
        logger.info(f"Analizzando: {pdf_file.name}")
        parser = PayslipPDFParser(str(pdf_file))
        employee_data = parser.get_tfr_by_employee()
        
        # Merge data
        for cf, data in employee_data.items():
            if cf not in all_data:
                all_data[cf] = data
            else:
                # Aggiungi mesi e aggiorna totale
                all_data[cf]['mesi'].extend(data['mesi'])
                all_data[cf]['totale_retrib_tfr'] += data['totale_retrib_tfr']
    
    # Converti in lista e ordina per nome
    result = list(all_data.values())
    result.sort(key=lambda x: x.get('nome', ''))
    
    return result
