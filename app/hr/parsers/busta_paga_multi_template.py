"""
Parser Buste Paga Multi-Template
Supporta 4 formati diversi usati nel tempo:
- Template 1 (fino 2018): Software CSC - Napoli
- Template 2 (2018-2022): Zucchetti spa (layout classico)
- Template 3 (dal 2022): Zucchetti nuovo (con separatori 's')
- Template 4: Teamsystem S.p.A.
"""
import re
from typing import Dict, Any, Optional, Tuple
import fitz  # PyMuPDF


def detect_template(text: str) -> str:
    """Rileva quale template è in uso basandosi sul contenuto del PDF."""
    # Foglio presenze Zucchetti (Aut. 301) — NON è un cedolino
    # Ha layout tabellare GIORNO/ORE/GIUSTIFICATIVI/TIMBRATURE
    if ("Autorizzazione Inail n." in text and "301 del 15/01/2009" in text
            and "GIUSTIFICATIVI" in text and "TIMBRATURE" in text):
        return "zucchetti_presenze"
    # Template 4 (Teamsystem)
    if "Teamsystem S.p.A" in text or "Teamsystem" in text or "NETTO BUSTA" in text:
        return "teamsystem"
    # Template 3 (nuovo Zucchetti): ha "s" come separatore di parole
    if "COGNOMEsEsNOME" in text or "PERIODOsDIsRETRIBUZIONE" in text:
        return "zucchetti_new"
    # Template 1 (CSC Napoli)
    if "Software CSC" in text or "CSC - Napoli" in text:
        return "csc_napoli"
    # Template 2 (Zucchetti classico)
    if "Zucchetti spa" in text or "LIBRO UNICO DEL LAVORO" in text:
        return "zucchetti_classic"
    # Default al classico
    return "zucchetti_classic"


def parse_template_zucchetti_presenze(text: str) -> Dict[str, Any]:
    """
    Foglio presenze Zucchetti (Aut. 301) — NON è un cedolino contabile.
    Contiene giustificativi giornalieri e timbrature.
    Può contenere l'indicazione "Cessato il:DD-MM-YYYY" se dipendente cessato.

    Ritorna struttura compatibile con extract_summary ma marcata come
    tipo_documento='foglio_presenze' e parse_success=False sui totali
    (non ha lordo/netto), ma True sui dati anagrafici.
    """
    result = {
        "template": "zucchetti_presenze",
        "tipo_documento": "foglio_presenze",  # Distingue dal cedolino vero
        "dipendente": {},
        "periodo": {},
        "totali": {},  # volutamente vuoto: un foglio presenze non ha netto/lordo
        "tfr": {},
        "ferie_permessi": {},
        "presenze": {},
    }

    # Periodo (es. "Maggio 2024", "Aprile 2023")
    mesi = ['Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
            'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre']
    for i, mese in enumerate(mesi):
        match = re.search(rf'{mese}\s+(\d{{4}})', text)
        if match:
            result["periodo"]["mese"] = i + 1
            result["periodo"]["mese_nome"] = mese
            result["periodo"]["anno"] = int(match.group(1))
            break

    # Codice fiscale (pattern italiano)
    cf_match = re.search(r'\b([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b', text)
    if cf_match:
        result["dipendente"]["codice_fiscale"] = cf_match.group(1)

    # Nome: cerca dopo il pattern numerico progressivo "NNNN/NNNN/NNNN/" (es. "000026/0300006/0000000001/")
    # La riga successiva è il nome del dipendente in MAIUSCOLO
    nome_match = re.search(r'\d{6}/\d{7}/\d{10}/\s*\n([A-ZÀÈÌÒÙ][A-ZÀÈÌÒÙ\'\s]+?)\n', text)
    if nome_match:
        result["dipendente"]["nome_completo"] = nome_match.group(1).strip()

    # Totali giustificativi dal riepilogo finale (es. "Ore ordinarie 120,00hm")
    # Estrae codici e quantità per tracciare presenze
    for m in re.finditer(r'([A-Z]{2,3}|Ore\s+\w+)\s+([\w\s\.]+?)\s+(\d+[.,]\d+)\s*(?:hm|ore|gg|ORE)?\b', text):
        codice = m.group(1).strip()
        descrizione = m.group(2).strip()
        quantita = parse_importo(m.group(3))
        result["presenze"].setdefault("giustificativi", []).append({
            "codice": codice, "descrizione": descrizione, "quantita": quantita
        })

    return result


def parse_importo(value_str: str) -> float:
    """Converte una stringa importo in float."""
    if not value_str:
        return 0.0
    clean = value_str.strip().replace(' ', '').replace('+', '').replace('-', '')
    if ',' in clean and '.' in clean:
        if clean.index('.') < clean.index(','):
            clean = clean.replace('.', '').replace(',', '.')
        else:
            clean = clean.replace(',', '')
    elif ',' in clean:
        clean = clean.replace(',', '.')
    try:
        return float(clean)
    except ValueError:
        return 0.0


def parse_template_csc_napoli(text: str) -> Dict[str, Any]:
    """
    Parser per Template 1: Software CSC - Napoli (fino 2018)
    Formato più vecchio con layout tabellare classico.
    Gestisce anche ACCONTI e TREDICESIME/QUATTORDICESIME.
    """
    result = {
        "template": "csc_napoli",
        "dipendente": {},
        "periodo": {},
        "totali": {},
        "tfr": {},
        "ferie_permessi": {}
    }
    
    # Rileva tipo cedolino
    is_acconto = 'ACCONTO' in text.upper()
    is_tredicesima = 'TREDICESIMA' in text.upper() or '13MA' in text.upper()
    is_quattordicesima = 'QUATTORDICESIMA' in text.upper() or '14MA' in text.upper()
    
    if is_acconto:
        result["tipo_cedolino"] = "acconto"
    elif is_tredicesima:
        result["tipo_cedolino"] = "tredicesima"
    elif is_quattordicesima:
        result["tipo_cedolino"] = "quattordicesima"
    else:
        result["tipo_cedolino"] = "mensile"
    
    # Estrai periodo (es: "DICEMBRE  2017" o "SETTEMBRE 2019")
    mesi = ['GENNAIO', 'FEBBRAIO', 'MARZO', 'APRILE', 'MAGGIO', 'GIUGNO',
            'LUGLIO', 'AGOSTO', 'SETTEMBRE', 'OTTOBRE', 'NOVEMBRE', 'DICEMBRE']
    for i, mese in enumerate(mesi):
        match = re.search(rf'{mese}\s+(\d{{4}})', text)
        if match:
            result["periodo"]["mese"] = i + 1
            result["periodo"]["mese_nome"] = mese.capitalize()
            result["periodo"]["anno"] = int(match.group(1))
            break
    
    # Estrai nome dipendente - pattern: DATA NOME_COGNOME DATA_NASCITA CODICE_FISCALE
    # Es: "31/01/2017 CERALDI VALERIO                14/06/1988 CRLVLR88H14F839O"
    nome_match = re.search(r'\d{2}/\d{2}/\d{4}\s+([A-Z][A-Z\'\s]+?)\s+\d{2}/\d{2}/\d{4}\s+([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])', text)
    if nome_match:
        nome = nome_match.group(1).strip()
        # Evita di prendere intestazioni come "BOLLO ISTITUTO"
        if nome and nome not in ['BOLLO ISTITUTO', 'COGNOME E NOME', 'CENTRO DI COSTO']:
            result["dipendente"]["nome_completo"] = nome
            result["dipendente"]["codice_fiscale"] = nome_match.group(2)
    
    # Se non trovato, prova pattern alternativo più permissivo
    if not result["dipendente"].get("nome_completo"):
        # Cerca codice fiscale e risali al nome
        cf_match = re.search(r'([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])', text)
        if cf_match:
            result["dipendente"]["codice_fiscale"] = cf_match.group(1)
            # Il nome è tipicamente prima del CF, dopo una data
            pos = text.find(cf_match.group(1))
            if pos > 0:
                # Cerca indietro per trovare il nome
                before_cf = text[max(0, pos-100):pos]
                nome_alt = re.search(r'\d{2}/\d{2}/\d{4}\s+([A-Z][A-Z\'\s]{3,40}?)\s*$', before_cf)
                if nome_alt:
                    nome = nome_alt.group(1).strip()
                    if nome and nome not in ['BOLLO ISTITUTO', 'COGNOME E NOME']:
                        result["dipendente"]["nome_completo"] = nome
    
    # Estrai codice fiscale (se non già trovato)
    cf_match = re.search(r'([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])', text)
    if cf_match:
        result["dipendente"]["codice_fiscale"] = cf_match.group(1)
    
    # Estrai livello (pattern: "O   5  BARISTA" o simile)
    livello_match = re.search(r'O\s+(\d+)\s+[A-Z]+', text)
    if livello_match:
        result["dipendente"]["livello"] = livello_match.group(1)
    
    # DATI PERIODO - Cerca la riga con formato: "GG.LAV  ORE.LAV  GG.RETR  ORE.RETR  ORE.CONTR  GG.ASS"
    # Esempio: "18   119,88   24   159,84    172,00  20,00"
    # Pattern: GG.LAV (1-31), ORE.LAV (decimale), GG.RETR (1-31), ORE.RETR (decimale), ORE.CONTR (intero), GG.ASS
    dati_periodo_match = re.search(
        r'(\d{1,2})\s+([\d]+[,\.]\d{2})\s+(\d{1,2})\s+([\d]+[,\.]\d{2})\s+(\d{2,3})[,\.]00\s+([\d,\.]+)',
        text
    )
    if dati_periodo_match:
        gg_lav = int(dati_periodo_match.group(1))
        ore_lav = parse_importo(dati_periodo_match.group(2))  # Ore effettivamente lavorate
        gg_retr = int(dati_periodo_match.group(3))
        ore_retr = parse_importo(dati_periodo_match.group(4))  # Ore retribuite
        ore_contr = int(dati_periodo_match.group(5))  # Ore contrattuali
        
        if 1 <= gg_lav <= 31:
            result["periodo"]["giorni_lavorati"] = gg_lav
        if 1 <= gg_retr <= 31:
            result["periodo"]["giorni_retribuiti"] = gg_retr
        if ore_lav > 0:
            result["periodo"]["ore_lavorate"] = ore_lav
        if ore_retr > 0:
            result["periodo"]["ore_retribuite"] = ore_retr
        if 50 <= ore_contr <= 250:
            result["periodo"]["ore_contrattuali"] = ore_contr
    
    # Controlla se è un mese di SOSPENSIONE (SOS ripetuto)
    sos_count = text.count('SOS')
    is_sospensione = sos_count >= 20  # Se ci sono molti SOS, è sospensione
    
    # PAGA BASE TEORICA - cerca "TOTALE :" dopo le voci paga (è la paga teorica, non il lordo effettivo)
    paga_base_match = re.search(r'TOTALE\s*:\s*([\d.,]+)', text)
    if paga_base_match:
        paga_base = parse_importo(paga_base_match.group(1))
        result["totali"]["paga_base_teorica"] = paga_base
    
    # TOTALE COMPETENZE - questo è il LORDO EFFETTIVO (quanto ha guadagnato realmente)
    comp_match = re.search(r'TOTALE COMPETENZE\s+([\d.,]+)\+?', text)
    if comp_match:
        competenze = parse_importo(comp_match.group(1))
        result["totali"]["competenze"] = competenze
        result["totali"]["lordo"] = competenze  # Il lordo effettivo è TOTALE COMPETENZE
    
    # TOTALE TRATTENUTE  
    tratt_match = re.search(r'TOTALE TRATTENUTE\s+([\d.,]+)-?', text)
    if tratt_match:
        result["totali"]["trattenute"] = parse_importo(tratt_match.group(1))
    
    # RITENUTE PREVIDENZIALI (Ritenute Dipendente)
    ritenute_match = re.search(r'RITENUTE PREVIDENZIALI\s+[\d,]+\s+[\d,]+\+?\s+([\d.,]+)-?', text)
    if ritenute_match:
        result["totali"]["ritenute_dipendente"] = parse_importo(ritenute_match.group(1))
    else:
        # Pattern alternativo: cerca "122,91-" dopo la riga RITENUTE PREVIDENZIALI
        ritenute_alt = re.search(r'RITENUTE PREVIDENZIALI.*?([\d]+[,\.]\d{2})-', text, re.DOTALL)
        if ritenute_alt:
            result["totali"]["ritenute_dipendente"] = parse_importo(ritenute_alt.group(1))
    
    # RITENUTE FISCALI (IRPEF)
    irpef_match = re.search(r'RITENUTE FISCALI\s+([\d.,]+)-?', text)
    if irpef_match:
        result["totali"]["irpef"] = parse_importo(irpef_match.group(1))
    
    # Per ACCONTI: cerca "IMPORTI ACCONTI SU TFR" o importo dopo ACCONTO
    if is_acconto:
        acconto_match = re.search(r'IMPORTI ACCONTI.*?([\d.,]+)\+', text)
        if acconto_match:
            result["totali"]["acconto"] = parse_importo(acconto_match.group(1))
    
    # NETTO - cerca LIRE (formato CSC)
    lire_match = re.search(r'LIRE\s*:\s*([\d.,]+)\+?', text)
    if lire_match:
        lire_str = lire_match.group(1).replace('.', '').replace(',', '.')
        lire_val = float(lire_str) if lire_str else 0
        
        if lire_val == 0:
            # LIRE:0 significa netto = 0 (o negativo se ci sono solo trattenute)
            if is_sospensione or result["totali"].get("competenze", 0) == 0:
                # Mese di sospensione: netto = -trattenute (il dipendente deve all'azienda)
                trattenute = result["totali"].get("trattenute", 0)
                if trattenute > 0:
                    result["totali"]["netto"] = -trattenute
                    result["tipo_cedolino"] = "sospensione"
                else:
                    result["totali"]["netto"] = 0
                    result["tipo_cedolino"] = "sospensione"
        elif lire_val > 1000:
            # Vecchio formato in lire - converti in euro
            result["totali"]["netto"] = round(lire_val / 1936.27, 2)
        else:
            # Già in euro (raro ma possibile)
            result["totali"]["netto"] = lire_val
    
    # Se non trovato con LIRE, cerca TOTALE NETTO esplicito
    if "netto" not in result["totali"]:
        netto_match = re.search(r'TOTALE NETTO\s+([\d.,]+)', text)
        if netto_match:
            result["totali"]["netto"] = parse_importo(netto_match.group(1))
    
    # Marca come sospensione se rilevato
    if is_sospensione:
        result["tipo_cedolino"] = "sospensione"
        result["note"] = f"Mese di sospensione ({sos_count} giorni SOS)"
    
    # Retribuzione TFR
    tfr_match = re.search(r'RETRIBUZIONE T\.?F\.?R\.?\s+([\d.,]+)', text)
    if tfr_match:
        result["tfr"]["retribuzione"] = parse_importo(tfr_match.group(1))
    
    # Ferie
    ferie_mat_match = re.search(r'Mat\.\s*([\d.,]+)\+?\s*Mat\.\s*([\d.,]+)', text)
    if ferie_mat_match:
        result["ferie_permessi"]["ferie_maturate"] = parse_importo(ferie_mat_match.group(1))
        result["ferie_permessi"]["permessi_maturati"] = parse_importo(ferie_mat_match.group(2))
    
    # Il lordo è già stato impostato da TOTALE COMPETENZE (sopra)
    # Se non è presente, gestisci i casi speciali
    if "lordo" not in result["totali"] or result["totali"].get("lordo") is None:
        if is_acconto and "acconto" in result["totali"]:
            result["totali"]["lordo"] = result["totali"]["acconto"]
            result["totali"]["netto"] = result["totali"]["acconto"]
        elif result.get("tipo_cedolino") in ["sospensione", "solo_trattenute"]:
            result["totali"]["lordo"] = 0
        else:
            result["totali"]["lordo"] = 0
    
    return result



def parse_template_teamsystem(text: str) -> Dict[str, Any]:
    """
    Parser per Template 4: Teamsystem S.p.A.
    Formato usato in alcuni periodi con layout diverso.
    """
    result = {
        "template": "teamsystem",
        "dipendente": {},
        "periodo": {},
        "totali": {},
        "tfr": {},
        "ferie_permessi": {}
    }
    
    # Estrai periodo (es: "SETTEMBRE    2022")
    mesi = ['GENNAIO', 'FEBBRAIO', 'MARZO', 'APRILE', 'MAGGIO', 'GIUGNO',
            'LUGLIO', 'AGOSTO', 'SETTEMBRE', 'OTTOBRE', 'NOVEMBRE', 'DICEMBRE']
    for i, mese in enumerate(mesi):
        match = re.search(rf'{mese}\s+(\d{{4}})', text)
        if match:
            result["periodo"]["mese"] = i + 1
            result["periodo"]["mese_nome"] = mese.capitalize()
            result["periodo"]["anno"] = int(match.group(1))
            break
    
    # Nome dipendente (pattern: dopo anno, es "20     1   5124776507 91431211 24       15  ARIANTE MARCELLA")
    nome_match = re.search(r'\d{4}\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+([A-Z][A-Z\'\s]+)', text)
    if nome_match:
        result["dipendente"]["nome_completo"] = nome_match.group(1).strip()
    
    # Codice fiscale
    cf_match = re.search(r'([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])', text)
    if cf_match:
        result["dipendente"]["codice_fiscale"] = cf_match.group(1)
    
    # Livello (es: "6^" o "6")
    livello_match = re.search(r'(\d)\^?\s*$', text, re.MULTILINE)
    if livello_match:
        result["dipendente"]["livello"] = livello_match.group(1)
    
    # Ore lavorate (pattern: "26    172,00" dove 172 sono le ore)
    ore_match = re.search(r'\d{2}\s+(\d{2,3})[,\.]\d{2}\s*$', text, re.MULTILINE)
    if ore_match:
        result["periodo"]["ore_lavorate"] = int(ore_match.group(1))
    
    # Giorni lavorati
    giorni_match = re.search(r'GG\.\s*CONTR\.\s*(\d+)', text)
    if not giorni_match:
        # Pattern alternativo: cerca numero isolato che potrebbe essere giorni
        giorni_match = re.search(r'\s(\d{2})\s+\d{2,3}[,\.]\d{2}', text)
    if giorni_match:
        result["periodo"]["giorni_lavorati"] = int(giorni_match.group(1))
    
    # TOTALE LORDO - cerca pattern con importi affiancati
    lordo_match = re.search(r'(\d{3,4})[,\.](\d{2})\s+(\d{3,4})[,\.](\d{2})\s+(\d{2,3})[,\.](\d{2})', text)
    if lordo_match:
        # Il primo importo grande è il lordo
        lordo_str = f"{lordo_match.group(1)},{lordo_match.group(2)}"
        result["totali"]["lordo"] = parse_importo(lordo_str)
        result["totali"]["competenze"] = result["totali"]["lordo"]
        
        # Le trattenute sono il terzo valore
        tratt_str = f"{lordo_match.group(5)},{lordo_match.group(6)}"
        result["totali"]["trattenute"] = parse_importo(tratt_str)
    
    # NETTO BUSTA - cerca pattern finale
    # Pattern: cerca numero seguito da "GIORNO DI RIPOSO" o simile
    netto_match = re.search(r'(\d{2,4})[,\.](\d{2})\s*R?\s*GIORNO', text)
    if netto_match:
        netto_str = f"{netto_match.group(1)},{netto_match.group(2)}"
        result["totali"]["netto"] = parse_importo(netto_str)
    else:
        # Pattern alternativo: cerca in fondo al documento
        lines = text.split('\n')
        for line in reversed(lines[-20:]):
            netto_alt = re.search(r'(\d{2,4})[,\.](\d{2})\s*$', line)
            if netto_alt:
                val = parse_importo(f"{netto_alt.group(1)},{netto_alt.group(2)}")
                if 100 < val < 5000:  # Range ragionevole per netto
                    result["totali"]["netto"] = val
                    break
    
    # Se non abbiamo lordo ma abbiamo netto, usa netto come riferimento
    if "netto" in result["totali"] and "lordo" not in result["totali"]:
        result["totali"]["lordo"] = result["totali"]["netto"]
    
    # Ferie
    ferie_match = re.search(r'FERIE RES\.\s*([\d,]+)', text)
    if ferie_match:
        result["ferie_permessi"]["ferie_residuo"] = parse_importo(ferie_match.group(1))
    
    # Permessi (ROL)
    rol_match = re.search(r'ROL RES\s*([-\d,]+)', text)
    if rol_match:
        result["ferie_permessi"]["permessi_residuo"] = parse_importo(rol_match.group(1))
    
    # TFR
    tfr_match = re.search(r'TFR MESE\s*([\d,]+)', text)
    if tfr_match:
        result["tfr"]["quota_mese"] = parse_importo(tfr_match.group(1))
    
    return result


def parse_template_zucchetti_classic(text: str) -> Dict[str, Any]:
    """
    Parser per Template 2: Zucchetti spa classico (2018-2022)
    """
    result = {
        "template": "zucchetti_classic",
        "dipendente": {},
        "periodo": {},
        "totali": {},
        "tfr": {},
        "ferie_permessi": {}
    }
    
    # Estrai periodo
    mesi = ['GENNAIO', 'FEBBRAIO', 'MARZO', 'APRILE', 'MAGGIO', 'GIUGNO',
            'LUGLIO', 'AGOSTO', 'SETTEMBRE', 'OTTOBRE', 'NOVEMBRE', 'DICEMBRE']
    for i, mese in enumerate(mesi):
        match = re.search(rf'{mese}\s+(\d{{4}})', text, re.IGNORECASE)
        if match:
            result["periodo"]["mese"] = i + 1
            result["periodo"]["mese_nome"] = mese.capitalize()
            result["periodo"]["anno"] = int(match.group(1))
            break
    
    # Estrai nome dipendente
    nome_match = re.search(r'\d{2}/\d{2}/\d{4}\s+([A-Z][A-Z\'\s]+?)\s+\d{2}/\d{2}/\d{4}', text)
    if nome_match:
        result["dipendente"]["nome_completo"] = nome_match.group(1).strip()
    
    # Codice fiscale
    cf_match = re.search(r'([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])', text)
    if cf_match:
        result["dipendente"]["codice_fiscale"] = cf_match.group(1)
    
    # Livello
    livello_match = re.search(r'O\s+(\d+)\s+[A-Z]+', text)
    if livello_match:
        result["dipendente"]["livello"] = livello_match.group(1)
    
    # TOTALE COMPETENZE
    comp_match = re.search(r'TOTALE COMPETENZE\s+([\d.,]+)', text)
    if comp_match:
        result["totali"]["competenze"] = parse_importo(comp_match.group(1))
        result["totali"]["lordo"] = result["totali"]["competenze"]
    
    # TOTALE TRATTENUTE
    tratt_match = re.search(r'TOTALE TRATTENUTE\s+([\d.,]+)', text)
    if tratt_match:
        result["totali"]["trattenute"] = parse_importo(tratt_match.group(1))
    
    # NETTO - cerca LIRE
    lire_match = re.search(r'LIRE\s*:\s*([\d.,]+)\+', text)
    if lire_match:
        lire_val = parse_importo(lire_match.group(1))
        result["totali"]["netto"] = round(lire_val / 1936.27, 2)
    else:
        # Calcola da competenze - trattenute
        if "competenze" in result["totali"] and "trattenute" in result["totali"]:
            result["totali"]["netto"] = round(
                result["totali"]["competenze"] - result["totali"]["trattenute"], 2
            )
    
    # Ore lavorate - pattern "ORE LAVORATE" o dopo numeri
    ore_match = re.search(r'(\d{2,3})[.,]00\s+\d+\s+\d+\s+(\d{2,3})[.,]00', text)
    if ore_match:
        result["periodo"]["ore_lavorate"] = parse_importo(ore_match.group(2))
    
    # Giorni lavorati
    giorni_match = re.search(r'(\d+)\s+(\d+)[.,]00\s+\d+\s+\d+', text)
    if giorni_match:
        result["periodo"]["giorni_lavorati"] = int(giorni_match.group(1))
    
    # TFR
    tfr_match = re.search(r'RETRIBUZIONE T\.?F\.?R\.?\s+([\d.,]+)', text)
    if tfr_match:
        result["tfr"]["retribuzione"] = parse_importo(tfr_match.group(1))
    
    # Ferie maturate/godute
    ferie_mat = re.search(r'Mat\.\s*([\d.,]+)\+', text)
    if ferie_mat:
        result["ferie_permessi"]["ferie_maturate"] = parse_importo(ferie_mat.group(1))
    
    ferie_god = re.search(r'God\.\s*([\d.,]+)\+', text)
    if ferie_god:
        result["ferie_permessi"]["ferie_godute"] = parse_importo(ferie_god.group(1))
    
    return result


def parse_template_zucchetti_new(text: str) -> Dict[str, Any]:
    """
    Parser per Template 3: Zucchetti nuovo (dal 2022)
    Questo template usa 's' come separatore nelle etichette.
    """
    result = {
        "template": "zucchetti_new",
        "dipendente": {},
        "periodo": {},
        "totali": {},
        "tfr": {},
        "ferie_permessi": {},
        "irpef": {}
    }
    
    # Rileva tipo cedolino
    text_upper = text.upper()
    if 'TREDICESIMA' in text_upper or '13MA' in text_upper:
        result["tipo_cedolino"] = "tredicesima"
    elif 'QUATTORDICESIMA' in text_upper or '14MA' in text_upper:
        result["tipo_cedolino"] = "quattordicesima"
    else:
        result["tipo_cedolino"] = "mensile"
    
    # Estrai periodo (es: "Ottobre 2023")
    mesi = ['Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
            'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre']
    for i, mese in enumerate(mesi):
        match = re.search(rf'{mese}\s+(\d{{4}})', text, re.IGNORECASE)
        if match:
            result["periodo"]["mese"] = i + 1
            result["periodo"]["mese_nome"] = mese
            result["periodo"]["anno"] = int(match.group(1))
            break
    
    # Nome dipendente — Zucchetti_new ha sempre il nome dopo il codice
    # dipendente (formato "0300NNN\n{NOME COGNOME}\n{CF}\n")
    # Pattern robusto: cattura solo fino a prima della riga con il CF
    nome_match = re.search(
        r"\b0\d{6}\s*\n\s*([A-ZÀÈÌÒÙ][A-ZÀÈÌÒÙ'\s]+?)\s*\n\s*[A-Z]{6}\d{2}[A-Z]",
        text
    )
    if nome_match:
        result["dipendente"]["nome_completo"] = re.sub(r'\s+', ' ', nome_match.group(1).strip())
    else:
        # Fallback: nome dopo "COGNOME E NOME" label
        nome_match2 = re.search(
            r"COGNOME[sE\s]*NOME\s*\n+\s*([A-ZÀÈÌÒÙ][A-ZÀÈÌÒÙ'\s]+?)\s*\n",
            text
        )
        if nome_match2:
            candidate = re.sub(r'\s+', ' ', nome_match2.group(1).strip())
            # Filtra etichette spurie ("CODICE", "PERIODO" ecc.)
            if candidate and not any(k in candidate for k in ("CODICE", "PERIODO", "COGNOME", "NOME")):
                result["dipendente"]["nome_completo"] = candidate
    
    # Codice fiscale
    cf_match = re.search(r'([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])', text)
    if cf_match:
        result["dipendente"]["codice_fiscale"] = cf_match.group(1)
    
    # Livello (es: "5' Livello")
    livello_match = re.search(r"(\d+)['\s]*Livello", text)
    if livello_match:
        result["dipendente"]["livello"] = livello_match.group(1)
    
    # Part Time
    pt_match = re.search(r'Part\s*Time\s+([\d.,]+)%', text)
    if pt_match:
        result["dipendente"]["part_time_perc"] = parse_importo(pt_match.group(1))
    
    # ORE e GIORNI lavorati (cerca dopo "LAVORATO")
    lavorato_match = re.search(r'LAVORATO.*?(\d+)\s+(\d+)\s+(\d+)\s+(\d+)', text, re.DOTALL)
    if lavorato_match:
        result["periodo"]["ore_lavorate"] = int(lavorato_match.group(1))
        result["periodo"]["giorni_lavorati"] = int(lavorato_match.group(2))
    
    # Pattern alternativo per ore: "135,00000 ORE" o "135,00 ORE"
    ore_match = re.search(r'(\d+)[,\.]\d+\s*ORE', text)
    if ore_match and "ore_lavorate" not in result["periodo"]:
        result["periodo"]["ore_lavorate"] = int(ore_match.group(1))
    
    # TOTALE COMPETENZE - cerca valore numerico che termina con cifre grandi
    # Pattern: cerca riga con solo numero grande (>500) che potrebbe essere competenze
    competenze_patterns = [
        r'TOTALEsCOMPETENZE.*?(\d{1,3}[.,]\d{2})\s*$',  # Inline
        r'(\d{1,3}[.,]\d{3}[.,]\d{2})\s*$',  # 1.228,13
        r'\n(\d{3,4}[.,]\d{2})\n',  # Standalone come 1.228,13 su riga
    ]
    
    # Cerca NETTO DEL MESE esplicito (più affidabile)
    # Pattern con segno negativo: "-32,85 €"
    netto_match = re.search(r'(-?\d{1,3}[.,]?\d{0,3}[.,]\d{2})\s*€', text)
    if netto_match:
        netto_val = parse_importo(netto_match.group(1).replace('-', ''))
        if '-' in netto_match.group(1):
            result["totali"]["netto"] = -netto_val
            result["tipo_cedolino"] = "solo_trattenute"
        else:
            result["totali"]["netto"] = netto_val
    
    # Cerca pattern competenze/trattenute dalla struttura del documento
    # Il formato è: trattenute \n competenze (es: 114,71 \n 1.228,13)
    tratt_comp_match = re.search(r'(\d{1,3}[.,]\d{2})\s*\n\s*(\d{1,3}[.,]?\d{0,3}[.,]\d{2})\s*\n', text)
    if tratt_comp_match:
        tratt_val = parse_importo(tratt_comp_match.group(1))
        comp_val = parse_importo(tratt_comp_match.group(2))
        # Solo se competenze > trattenute (altrimenti sono invertiti)
        if comp_val > tratt_val:
            result["totali"]["trattenute"] = tratt_val
            result["totali"]["competenze"] = comp_val
            result["totali"]["lordo"] = comp_val
    
    # Pattern alternativo: cerca "Z00001 Retribuzione" seguito da importo
    retrib_match = re.search(r'Z00001\s+Retribuzione.*?([\d.,]+)\s*$', text, re.MULTILINE)
    if retrib_match and "lordo" not in result["totali"]:
        result["totali"]["lordo"] = parse_importo(retrib_match.group(1))
    
    # IRPEF
    irpef_match = re.search(r'Ritenute IRPEF\s*([\d.,]+)', text)
    if irpef_match:
        result["irpef"]["ritenute"] = parse_importo(irpef_match.group(1))
    
    # Contributo IVS (INPS)
    ivs_match = re.search(r'Contributo IVS.*?(\d+[.,]\d{2})\s*$', text, re.MULTILINE)
    if ivs_match:
        result["totali"]["inps_dipendente"] = parse_importo(ivs_match.group(1))
    
    # TFR
    tfr_quota = re.search(r'Quota T\.?F\.?R\.?\s*([\d.,]+)', text)
    if tfr_quota:
        result["tfr"]["quota_anno"] = parse_importo(tfr_quota.group(1))
    
    tfr_fondo = re.search(r'F\.?do 31/12\s*([\d.,]+)', text)
    if tfr_fondo:
        result["tfr"]["fondo_31_12"] = parse_importo(tfr_fondo.group(1))
    
    # Ferie e Permessi (formato: "Ferie 8,66666 14,00000 -5,33334 GG.")
    ferie_match = re.search(r'Ferie\s+([-\d.,]+)\s+([-\d.,]+)\s+([-\d.,]+)', text)
    if ferie_match:
        result["ferie_permessi"]["ferie_residuo_ap"] = parse_importo(ferie_match.group(1))
        result["ferie_permessi"]["ferie_godute"] = parse_importo(ferie_match.group(2))
        result["ferie_permessi"]["ferie_saldo"] = parse_importo(ferie_match.group(3))
    
    permessi_match = re.search(r'Permessi\s+([-\d.,]+)\s+([-\d.,]+)', text)
    if permessi_match:
        result["ferie_permessi"]["permessi_residuo"] = parse_importo(permessi_match.group(1))
        result["ferie_permessi"]["permessi_goduti"] = parse_importo(permessi_match.group(2))
    
    # Calcola trattenute se mancanti
    if "trattenute" not in result["totali"]:
        trattenute = 0
        if "inps_dipendente" in result["totali"]:
            trattenute += result["totali"]["inps_dipendente"]
        if "ritenute" in result.get("irpef", {}):
            trattenute += result["irpef"]["ritenute"]
        if trattenute > 0:
            result["totali"]["trattenute"] = trattenute
    
    # Calcola netto se mancante
    if "netto" not in result["totali"] and "lordo" in result["totali"] and "trattenute" in result["totali"]:
        result["totali"]["netto"] = round(
            result["totali"]["lordo"] - result["totali"]["trattenute"], 2
        )
    
    # Se abbiamo competenze ma non lordo, usa competenze come lordo
    if "competenze" in result["totali"] and "lordo" not in result["totali"]:
        result["totali"]["lordo"] = result["totali"]["competenze"]
    
    # Per cedolini solo trattenute (netto negativo o 0), imposta lordo = 0
    if result.get("tipo_cedolino") == "solo_trattenute":
        result["totali"]["lordo"] = 0
    
    # Se abbiamo netto (anche negativo) ma non lordo, consideriamo comunque valido
    if "netto" in result["totali"] and "lordo" not in result["totali"]:
        if result["totali"]["netto"] <= 0:
            result["totali"]["lordo"] = 0
        else:
            result["totali"]["lordo"] = result["totali"]["netto"]
    
    return result


def detect_cessazione(text: str) -> Dict[str, Any]:
    """
    Rileva se il cedolino indica cessazione del rapporto di lavoro.

    Pattern REALI trovati analizzando i cedolini della Ceraldi Group
    (Zucchetti Aut.299, Aut.301, TeamSystem Aut.92267):

    1. Foglio presenze Zucchetti: "Cessato il:DD-MM-YYYY"
    2. Cedolino Zucchetti: riga anagrafica contiene DUE date consecutive
       (Data Assunzione + Data Cessazione) separate da spazio prima di "OPE"
       Es. "25-11-2023 24-05-2024\nOPE"
       vs. dipendente attivo: "25-11-2023\nOPE" (solo assunzione)
    3. Cedolino di cessazione: contiene "Licenz." nella tabella conguaglio
       (riga riepilogativa di licenziamento/cessazione)
    4. T.Deter.DD/MM/YYYY seguito da una data che è la fine contratto a termine

    Non cerca "LIQUIDAZIONE TFR" / "SALDO TFR" perché nei cedolini reali della
    Ceraldi Group non compaiono mai (il consulente usa le altre diciture).

    Returns:
        {
            "cessato": bool,
            "diciture_trovate": [str],
            "data_cessazione_rilevata": str | None  (normalizzata YYYY-MM-DD)
        }
    """
    if not text:
        return {"cessato": False, "diciture_trovate": [], "data_cessazione_rilevata": None}

    diciture = []
    data_rilevata = None

    # Pattern 1: "Cessato il:DD-MM-YYYY" (foglio presenze)
    m1 = re.search(r'Cessat[oi]\s+il\s*:?\s*(\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4})', text, re.IGNORECASE)
    if m1:
        diciture.append("CESSATO IL (foglio presenze)")
        data_rilevata = _normalize_data(m1.group(1))

    # Pattern 2: Riga anagrafica con DUE date sulla STESSA riga poi "OPE" (Zucchetti)
    # Cedolino CESSATO:   "25-11-2023 24-05-2024\nOPE"  (date assunz+cess unite)
    # Cedolino ATTIVO:    "02-04-1986\n18-09-2024\nOPE" (date su righe diverse)
    # Uso [ \t]+ (non \s+) per escludere il newline.
    m2 = re.search(
        r'(\d{2}-\d{2}-\d{4})[ \t]+(\d{2}-\d{2}-\d{4})\s*\n\s*OPE\b',
        text
    )
    if m2:
        # La seconda data è la cessazione (la prima è assunzione)
        diciture.append("DATA CESSAZIONE IN ANAGRAFICA (Zucchetti)")
        if not data_rilevata:
            data_rilevata = _normalize_data(m2.group(2))

    # Pattern 3: "Licenz." nella tabella conguaglio (cedolino cessazione Zucchetti)
    # Questo è molto affidabile: compare solo quando c'è chiusura del conguaglio IRPEF
    if re.search(r'\bLicenz\.', text):
        diciture.append("LICENZ. (conguaglio cessazione)")

    # Pattern 4 (TeamSystem): "CESS. RAPP." nella sezione conguaglio
    # Vale solo se seguito da valori numerici o se la data cessazione è stampata
    # Non usato standalone perché la label fa parte del template vuoto
    # → usato solo se c'è anche un valore di conguaglio valorizzato
    ts_cess = re.search(r'DATA\s+CESSAZIONE\s*\n\s*[A-Z][^\n]*\n\s*(\d{2}/\d{2}/\d{2,4})', text)
    if ts_cess:
        diciture.append("DATA CESSAZIONE (TeamSystem)")
        if not data_rilevata:
            data_rilevata = _normalize_data(ts_cess.group(1))

    # Pattern 4-bis (TeamSystem): 3 date consecutive sulla riga anagrafica
    # TeamSystem stampa "DD/MM/YY DD/MM/YY DD/MM/YY" = nascita, assunzione, cessazione.
    # Se ci sono solo 2 date = nascita + assunzione, dipendente attivo.
    # Il pattern deve evitare match su date troppo vecchie (tipo date competenza/IRPEF)
    # Quindi richiediamo che la prima data sia CF-compatibile (anno 40-05, cioè nati
    # tra 1940 e 2005) e che la terza sia coerente col mese del cedolino.
    ts_3date = re.search(
        r'(\d{2}/\d{2}/(?:[0-9]\d))\s+(\d{2}/\d{2}/\d{2})\s+(\d{2}/\d{2}/\d{2})\b',
        text
    )
    if ts_3date:
        # Verifica che le 3 date siano plausibili (nascita prima di ass, ass prima di cess)
        dn = _normalize_data(ts_3date.group(1))
        da = _normalize_data(ts_3date.group(2))
        dc = _normalize_data(ts_3date.group(3))
        if dn and da and dc and dn < da <= dc:
            diciture.append("3 DATE IN ANAGRAFICA (TeamSystem)")
            if not data_rilevata:
                data_rilevata = dc

    # Pattern 4-ter (TeamSystem): nome seguito da data di cessazione sulla stessa riga
    # Es. "ARIANTE MARCELLA                     12/07/22"
    # Affidabile solo se data è plausibile come cessazione (futura rispetto
    # alla data di nascita del dipendente)
    ts_nome_data = re.search(
        r'\b[A-Z]{3,}\s+[A-Z]{3,}\s{10,}(\d{2}/\d{2}/\d{2})\b',
        text
    )
    if ts_nome_data:
        # Distingui: se dopo la riga nome c'è un pattern tipo
        # "CF   COMUNE   13/05/97 12/07/22" (nascita + cessazione) è cessato.
        # Ariante ha proprio questo: "12/07/22" dopo il nome = cessazione
        # Filtro: considera solo se la data è successiva al 2015 (dipendenti
        # contemporanei) per evitare falsi positivi con date di nascita
        data_candidate = ts_nome_data.group(1)
        dc = _normalize_data(data_candidate)
        if dc and dc >= "2015-01-01":
            # Ulteriore conferma: presenza di "CESS. RAPP." o "CESSAZIONE" nel testo
            if "CESS. RAPP." in text.upper() or "DATA CESSAZIONE" in text.upper():
                # Attiva solo se non già rilevato da pattern 4/4-bis (meno specifici)
                if not any("TeamSystem" in d for d in diciture):
                    diciture.append("NOME + DATA CESSAZIONE (TeamSystem)")
                    if not data_rilevata:
                        data_rilevata = dc

    # Pattern 5: contratto a termine con data coincidente con mese cedolino.
    # Es. "T.Deter. 24/05/2024" + cedolino di Maggio 2024 → cessazione in corso
    # Questo è informativo ma NON scatena cessazione da solo
    # (altrimenti falso-positivo: un contratto T.Det. iniziale non è cessazione)
    # → Si attiva solo se AFFIANCATO da altri pattern

    # Pattern 6 (esplicito): "DATA CESSAZIONE: DD/MM/YYYY" come testo libero
    m6 = re.search(
        r'(?:DATA\s+)?CESSAZIONE\s*[:\s]+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
        text.upper()
    )
    if m6 and not data_rilevata:
        diciture.append("DATA CESSAZIONE ESPLICITA")
        data_rilevata = _normalize_data(m6.group(1))

    return {
        "cessato": bool(diciture),
        "diciture_trovate": diciture,
        "data_cessazione_rilevata": data_rilevata,
    }


def _normalize_data(d: str) -> Optional[str]:
    """Normalizza DD-MM-YYYY o DD/MM/YYYY → YYYY-MM-DD."""
    if not d:
        return None
    m = re.match(r'(\d{1,2})[-/\.](\d{1,2})[-/\.](\d{2,4})', d.strip())
    if not m:
        return d
    dd, mm, yy = m.groups()
    if len(yy) == 2:
        yy = "20" + yy
    try:
        return f"{int(yy):04d}-{int(mm):02d}-{int(dd):02d}"
    except Exception:
        return d


def parse_busta_paga_multi(pdf_path: str) -> Dict[str, Any]:
    """
    Parser principale che rileva automaticamente il template e applica
    il parser corretto. Gestisce anche PDF multi-pagina.
    
    Args:
        pdf_path: Percorso del file PDF
        
    Returns:
        Dizionario con tutti i dati estratti
    """
    doc = fitz.open(pdf_path)
    
    # Estrai testo da tutte le pagine
    all_text = ""
    page_texts = []
    for page in doc:
        page_text = page.get_text()
        page_texts.append(page_text)
        all_text += page_text + "\n"
    
    num_pages = len(doc)
    doc.close()
    
    # Usa la prima pagina per rilevare il template
    text = page_texts[0] if page_texts else ""
    
    # Rileva il template dalla prima pagina
    template = detect_template(text)

    # Se la prima pagina è un foglio presenze (Aut.301), il cedolino vero può
    # essere nelle pagine successive (layout comune Zucchetti: p1=presenze,
    # p2+=cedolino). Cerca la prima pagina che NON è un foglio presenze.
    cedolino_page_idx = 0
    if template == "zucchetti_presenze" and num_pages > 1:
        for pidx, pt in enumerate(page_texts):
            sub_template = detect_template(pt)
            if sub_template != "zucchetti_presenze":
                cedolino_page_idx = pidx
                template = sub_template
                text = pt
                break
        else:
            # Tutte le pagine sono presenze → parse solo presenze, no cedolino
            cedolino_page_idx = None

    # Applica il parser corretto
    # IMPORTANTE: per zucchetti_new e zucchetti_classic passiamo il testo di
    # TUTTE le pagine (o dal cedolino in poi) perché i totali/netto sono
    # spesso distribuiti tra pagine 2-3 (es. Chakir 3pag il netto è a pag3,
    # Solla 2pag il netto è a pag2).
    if cedolino_page_idx is not None and cedolino_page_idx >= 0:
        # Concatena da cedolino_page_idx fino a fine documento
        # escludendo eventuali cedolini aggiuntivi (multi-contratto stesso dip.)
        # Per ora usiamo tutto il rimanente, la separazione multi-cedolino
        # viene fatta nell'euristica additional_cedolini più sotto
        cedolino_text = "\n".join(page_texts[cedolino_page_idx:])
    else:
        cedolino_text = text

    if cedolino_page_idx is None:
        # Solo foglio presenze, nessun cedolino contabile
        result = parse_template_zucchetti_presenze(page_texts[0])
    elif template == "zucchetti_presenze":
        result = parse_template_zucchetti_presenze(text)
    elif template == "csc_napoli":
        result = parse_template_csc_napoli(cedolino_text)
    elif template == "zucchetti_new":
        result = parse_template_zucchetti_new(cedolino_text)
    elif template == "teamsystem":
        result = parse_template_teamsystem(cedolino_text)
    else:
        result = parse_template_zucchetti_classic(cedolino_text)

    # Se ci sono altre pagine di cedolino, estrai dati aggiuntivi
    # (pagina 2 dei PDF nuovi contiene ferie/permessi dettagliati)
    # Il controllo è sulla pagina successiva a quella del cedolino primario
    next_page_idx = (cedolino_page_idx + 1) if cedolino_page_idx is not None else 1
    if num_pages > next_page_idx and result.get("tipo_documento") != "foglio_presenze":
        page2_data = parse_page2_ore_lavorate(page_texts[next_page_idx])
        result["ore_ferie"] = page2_data

        # Aggiorna i totali con i dati della pagina 2
        if page2_data.get("ferie_residuo"):
            result.setdefault("ferie_permessi", {})["ferie_residuo"] = page2_data["ferie_residuo"]
        if page2_data.get("ferie_godute"):
            result.setdefault("ferie_permessi", {})["ferie_godute"] = page2_data["ferie_godute"]
        if page2_data.get("permessi_residuo"):
            result.setdefault("ferie_permessi", {})["permessi_residuo"] = page2_data["permessi_residuo"]
        if page2_data.get("permessi_goduti"):
            result.setdefault("ferie_permessi", {})["permessi_goduti"] = page2_data["permessi_goduti"]

    result["raw_text_length"] = len(all_text)
    result["num_pages"] = num_pages
    result["parse_success"] = True

    # --- RILEVAMENTO CESSAZIONE RAPPORTO ---
    # Cerca diciture di cessazione in TUTTO il testo del PDF (prima + altre pagine)
    # Non fa calcoli: legge quanto stampato dal consulente del lavoro.
    result["cessazione"] = detect_cessazione(all_text)

    # --- RILEVAMENTO MULTI-CEDOLINO (cessazione + nuovo contratto) ---
    # Caso tipico: lo stesso dipendente ha cessato il vecchio contratto nel mese X
    # e ne ha iniziato uno nuovo sempre nel mese X. Il consulente stampa i due
    # cedolini come pagine separate nello stesso PDF. Le rileviamo e popoliamo
    # additional_cedolini[] con i dati dei cedolini aggiuntivi (oltre al primo).
    #
    # Euristica: due cedolini dello STESSO template con DUE date assunzione
    # diverse rilevate nelle rispettive pagine.
    additional_cedolini = []
    if template in ("zucchetti_new", "zucchetti_classic") and num_pages > 1:
        seen_assunzioni = set()
        # Aggiungi l'assunzione del cedolino primario se rilevata
        primary_assunz = re.search(r'\n(\d{2}-\d{2}-\d{4})[ \t]+\d{2}-\d{2}-\d{4}\s*\n\s*OPE\b', text)
        if primary_assunz:
            seen_assunzioni.add(primary_assunz.group(1))
        else:
            primary_assunz_single = re.search(r'\n(\d{2}-\d{2}-\d{4})\s*\n\s*OPE\b', text)
            if primary_assunz_single:
                seen_assunzioni.add(primary_assunz_single.group(1))

        for pidx, pt in enumerate(page_texts):
            if pidx == cedolino_page_idx:
                continue
            sub_t = detect_template(pt)
            if sub_t not in ("zucchetti_new", "zucchetti_classic"):
                continue
            # Estrai assunzione da questa pagina
            assunz_match = re.search(r'\n(\d{2}-\d{2}-\d{4})[ \t]+\d{2}-\d{2}-\d{4}\s*\n\s*OPE\b', pt)
            if not assunz_match:
                assunz_match = re.search(r'\n(\d{2}-\d{2}-\d{4})\s*\n\s*OPE\b', pt)
            if not assunz_match:
                continue
            ass = assunz_match.group(1)
            if ass in seen_assunzioni:
                continue
            seen_assunzioni.add(ass)
            # Parsa cedolino aggiuntivo
            if sub_t == "zucchetti_new":
                sub_result = parse_template_zucchetti_new(pt)
            else:
                sub_result = parse_template_zucchetti_classic(pt)
            sub_result["page_index"] = pidx
            additional_cedolini.append(sub_result)

    if additional_cedolini:
        result["additional_cedolini"] = additional_cedolini

    # Validazione minima
    # Accetta anche lordo = 0 per cedolini solo trattenute
    # Il foglio presenze è considerato parse_success=True anche senza netto/lordo
    totali = result.get("totali", {})
    has_netto = "netto" in totali
    has_lordo = "lordo" in totali
    is_solo_trattenute = result.get("tipo_cedolino") == "solo_trattenute"
    is_foglio_presenze = result.get("tipo_documento") == "foglio_presenze"

    if not has_netto and not has_lordo and not is_solo_trattenute and not is_foglio_presenze:
        result["parse_success"] = False
        result["parse_error"] = "Nessun importo estratto"

    # cedolino_text copre tutte le pagine del cedolino (netto, elementi
     # retributivi e anticipi TFR spesso stanno sulla seconda pagina, non
     # sulla prima usata per riconoscere il template)
    _verifica_netto(result, cedolino_text)
    _elementi_retributivi(result, cedolino_text)
    _acconti_e_anticipazioni(result, cedolino_text)
    if result.get("periodo", {}).get("giorni_lavorati"):
        result["giorni_lavorati"] = result["periodo"]["giorni_lavorati"]
    return result


def _elementi_retributivi(result: Dict[str, Any], text: str) -> None:
    """Legge paga base, contingenza e scatti dal corpo della busta.

    Sono su ogni cedolino, ma come tariffa ORARIA a cinque decimali
    (`PAGA BASE 5,93890 ... CONTING. 3,03703`); il Libro Unico scrive invece gli
    stessi elementi in forma mensile (`PAGA BASE 1.396,08000`). Qui si prendono
    entrambe le forme e si distingue dal valore: sopra i 100 euro e' un mensile,
    sotto e' una tariffa oraria.

    Serve per sapere quale tranche di rinnovo e' stata applicata: la paga base
    che risulta dalla busta, confrontata con la tabella in vigore, dice se lo
    scarto e' comune a tutti i livelli (tranche vecchia) o riguarda una sola
    persona (allora e' un caso da guardare).
    """
    # Ogni studio paghe scrive le stesse voci a modo suo: CONTING. o CONTINGENZA,
    # SCATTI o SCATTI ANZIANITA'. L'importo deve avere i decimali, cosi' le
    # intestazioni di colonna ("SCATTI N. % G.G") non vengono scambiate per dati.
    voci = {
        "paga_base": r"PAGA\s+BASE\s+([\d.]+,\d{2,6})",
        "contingenza": r"CONTING(?:ENZA)?\.?\s+([\d.]+,\d{2,6})",
        "scatti": r"SCATTI(?:\s+ANZIANITA'?)?\s+([\d.]+,\d{2,6})",
        "superminimo": r"SUPERMINIMO(?:\s+ASSOR\.?)?\s+([\d.]+,\d{2,6})",
    }
    out: Dict[str, Any] = {}
    alto = text.upper()
    for nome, pattern in voci.items():
        m = re.search(pattern, alto)
        if not m:
            continue
        try:
            val = float(m.group(1).replace(".", "").replace(",", "."))
        except ValueError:
            continue
        if val <= 0:
            continue
        out[nome + ("_mensile" if val >= 100 else "_oraria")] = round(val, 5)
    if out:
        result.setdefault("retribuzione", {}).update(out)


def _verifica_netto(result: Dict[str, Any], text: str = "") -> None:
    """Controlla il netto con l'aritmetica della busta: competenze - trattenute.

    Nel template zucchetti_classic il netto veniva letto dalla zona delle
    coordinate bancarie, dove accanto all'importo vero stanno numeri piccoli:
    usciva 0,00 o 0,48 al posto di 1.354,00, e su tutto il 2021 il netto
    risultava nullo pur avendo il lordo corretto.

    Il netto di una busta e' competenze meno trattenute, a meno
    dell'arrotondamento all'euro. Quando il valore letto si scosta di piu' di un
    euro da quel conto — o e' assente, o supera le competenze — vince il calcolo,
    e il documento resta marcato per sapere che il numero e' ricostruito.
    """
    t = result.get("totali") or {}
    if result.get("tipo_documento") == "foglio_presenze":
        return
    if re.search(r"COMPENSO\s+AMMINISTRATORE|CO\.CO\.CO", text.upper()):
        # Cedolino di compenso amministratore (Co.Co.Co.), non busta paga
        # dipendente: "competenze" e "trattenute" qui intercettano campi del
        # tutto diversi (residui, arrotondamenti), non i totali del documento.
        # Il controllo aritmetico li confronterebbe a vuoto e sovrascriverebbe
        # un netto letto correttamente con un valore inventato — visto su
        # Ceraldi Valerio maggio 2026: netto vero 2.000,00, "ricostruito" 38,21.
        return
    competenze = t.get("competenze", t.get("lordo"))
    trattenute = t.get("trattenute")
    if competenze is None or trattenute is None:
        return
    try:
        calcolato = round(float(competenze) - float(trattenute), 2)
    except (TypeError, ValueError):
        return
    if calcolato <= 0:
        return                  # sospensioni e mesi a saldo negativo: lasciati stare
    letto = t.get("netto")
    if (letto is None or abs(float(letto) - calcolato) > 1.0
            or float(letto) > float(competenze)):
        t["netto_letto"] = letto
        t["netto"] = calcolato
        t["netto_ricostruito"] = True


def parse_page2_ore_lavorate(text: str) -> Dict[str, Any]:
    """
    Estrae i dati di ferie/permessi/ore dalla seconda pagina dei PDF recenti.
    """
    result = {}
    
    # Pattern per ferie: "Ferie -1,00000 -1,00000 GG."
    ferie_match = re.search(r'Ferie\s+([-\d,\.]+)\s+([-\d,\.]+)\s*GG', text)
    if ferie_match:
        result["ferie_residuo"] = parse_importo(ferie_match.group(1))
        result["ferie_saldo"] = parse_importo(ferie_match.group(2))
    
    # Pattern per permessi: "Permessi 12,00000 12,00000 ORE"
    permessi_match = re.search(r'Permessi\s+([-\d,\.]+)\s+([-\d,\.]+)\s*ORE', text)
    if permessi_match:
        result["permessi_residuo"] = parse_importo(permessi_match.group(1))
        result["permessi_saldo"] = parse_importo(permessi_match.group(2))
    
    # Pattern per "Residuo AP Goduto Saldo Maturato" seguito da valori
    residuo_match = re.search(r'Residuo AP\s+Goduto\s+Saldo\s+Maturato', text)
    if residuo_match:
        # I valori sono nelle righe successive
        values = re.findall(r'([\d,\.]+)\s+([\d,\.]+)', text[residuo_match.end():residuo_match.end()+200])
        if values:
            result["ferie_residuo_ap"] = parse_importo(values[0][0])
            result["ferie_godute"] = parse_importo(values[0][1])
    
    # Imponibili dalla pagina 2
    imp_inps = re.search(r'Imp\.\s*INPS\s+([\d,\.]+)', text)
    if imp_inps:
        result["imponibile_inps"] = parse_importo(imp_inps.group(1))
    
    imp_irpef = re.search(r'Imp\.\s*IRPEF\s+([\d,\.]+)', text)
    if imp_irpef:
        result["imponibile_irpef"] = parse_importo(imp_irpef.group(1))
    
    # Ore lavorate (se presente)
    ore_lav = re.search(r'ORE\s+LAVORATE\s*([\d,\.]+)', text, re.IGNORECASE)
    if ore_lav:
        result["ore_lavorate_mese"] = parse_importo(ore_lav.group(1))
    
    # Giorni lavorati
    giorni_lav = re.search(r'GIORNI\s+LAVORATI\s*([\d]+)', text, re.IGNORECASE)
    if giorni_lav:
        result["giorni_lavorati_mese"] = int(giorni_lav.group(1))
    
    return result


def parse_busta_paga_from_bytes(pdf_bytes: bytes) -> Dict[str, Any]:
    """Parse busta paga da bytes (per upload via API o dati da Mongo)."""
    import tempfile
    import os
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        tmp.write(pdf_bytes)
        tmp_path = tmp.name
    
    try:
        result = parse_busta_paga_multi(tmp_path)
    finally:
        os.unlink(tmp_path)
    
    return result


def extract_summary(parsed_data: Dict[str, Any]) -> Dict[str, Any]:
    """Estrae un riepilogo per aggiornamento database."""
    totali = parsed_data.get("totali", {})
    dipendente = parsed_data.get("dipendente", {})
    periodo = parsed_data.get("periodo", {})
    ferie = parsed_data.get("ferie_permessi", {})
    ore_ferie = parsed_data.get("ore_ferie", {})  # Dati da pagina 2
    cessazione = parsed_data.get("cessazione", {})

    return {
        "template": parsed_data.get("template", "unknown"),
        "num_pages": parsed_data.get("num_pages", 1),
        "dipendente_nome": dipendente.get("nome_completo"),
        "codice_fiscale": dipendente.get("codice_fiscale"),
        "livello": dipendente.get("livello"),
        "mese": periodo.get("mese"),
        "anno": periodo.get("anno"),
        "lordo": totali.get("lordo") or totali.get("competenze"),
        "trattenute": totali.get("trattenute"),
        "netto": totali.get("netto"),
        "ore_lavorate": periodo.get("ore_lavorate") or ore_ferie.get("ore_lavorate_mese"),
        "giorni_lavorati": periodo.get("giorni_lavorati") or ore_ferie.get("giorni_lavorati_mese"),
        "inps_dipendente": totali.get("inps_dipendente"),
        "irpef": parsed_data.get("irpef", {}).get("ritenute"),
        "tfr_quota": parsed_data.get("tfr", {}).get("quota_anno"),
        # Dati ferie/permessi
        "ferie_residuo": ferie.get("ferie_residuo") or ore_ferie.get("ferie_residuo"),
        "ferie_godute": ferie.get("ferie_godute") or ore_ferie.get("ferie_godute"),
        "permessi_residuo": ferie.get("permessi_residuo") or ore_ferie.get("permessi_residuo"),
        "permessi_goduti": ferie.get("permessi_goduti") or ore_ferie.get("permessi_goduti"),
        # Rilevamento cessazione rapporto (da testo PDF)
        "cessato": cessazione.get("cessato", False),
        "cessazione_diciture": cessazione.get("diciture_trovate", []),
        "data_cessazione_rilevata": cessazione.get("data_cessazione_rilevata"),
    }


def _acconti_e_anticipazioni(result: Dict[str, Any], text: str) -> None:
    """Legge acconti sulla retribuzione e anticipi TFR erogati o recuperati.

    Il campo "TFR a fondi / Anticipi" e' presente su quasi ogni busta ma quasi
    sempre vicino allo zero (mediana 0,50 su 425 buste controllate): e' un
    residuo tecnico, non un anticipo del mese. Un anticipo TFR vero fa
    schizzare quel valore molto piu' in alto (undici casi sopra i 50 euro,
    fino a 5.300) — la soglia di 50 euro separa il rumore dall'evento reale.

    "ACCONTO TRATT. RETRIB." e "Recupero acconto" sono voci distinte e ben
    popolate (21 e 47 occorrenze, importi tondi: 500, 600, 1.000...): il primo
    e' l'acconto erogato nel mese, il secondo la sua restituzione trattenuta
    in busta un mese successivo.
    """
    U = text.upper()
    out: Dict[str, Any] = {}

    m = re.search(r"ACCONTO\s+TRATT\.?\s*RETRIB\.?\s+([\d.]+,\d{2})", U)
    if m:
        out["acconto_erogato"] = parse_importo(m.group(1))

    m = re.search(r"RECUPERO\s+ACCONTO\s+([\d.]+,\d{2})", U)
    if m:
        out["acconto_recuperato"] = parse_importo(m.group(1))

    m = re.search(r"TFR\s+A\s+FONDI\s+ANTICIPI\s+([\d.]+,\d{2})", U)
    if not m:
        m = re.search(r"\bANTICIPI\s+([\d.]+,\d{2})", U)
    if m:
        valore = parse_importo(m.group(1))
        out["tfr_anticipi_residuo"] = valore
        if valore >= 50:
            out["tfr_anticipo_erogato"] = valore

    if result.get("tipo_cedolino") == "acconto":
        out["intero_cedolino_acconto"] = True

    if out:
        result["acconti"] = out
