"""Voci del cedolino e foglio presenze: le letture di dettaglio del motore unico.

Erano il parser del Libro Unico (`services/libro_unico_workflow.py`), un
secondo motore con un suo scrittore su tabelle che in produzione non sono mai
esistite (`buste_paga`, `presenze_mensili`, `scadenze`). Dello scrittore non
resta nulla; le letture restano perche' sono le uniche che conoscono le voci
codificate (C00001, F09081...) e i dati chiave del titolare (ratei 13a e 14a,
indennita' L.207/24, trattamento integrativo L.21), e le chiama il motore unico
`services/cedolini_motore.py` sulla stessa busta, non su un secondo giro.
"""
import re
from typing import Dict, List, Optional


# Pattern per filtrare la filigrana Zucchetti
WATERMARK_PATTERNS = [
    r'^[A-Z]$',  # Singole lettere
    r'^[a-z]{1,4}$',  # Brevi sequenze minuscole
    r'Zucchetti',
    r'zucchetti',
    r'www\.',
    r'http',
    r'\.it',
    r'itte',
    r'ccu',
    r'lle',
    r'rid',
    r'tth',
    r'//:p',
    r'\)ti',
    r'n re',
    r'tn$',
    r'^I o',
    r'^o L',
    r'^id$',
    r'alle',
    r'^d$',
    r'^e ',
    r'ru$',
    r'co$',
    r'rp ',
    r're$',
    r'p o',
]


def is_watermark_line(line: str) -> bool:
    """Verifica se una linea è parte della filigrana"""
    line = line.strip()
    if not line:
        return True
    if len(line) <= 3 and not line.isdigit():
        return True
    for pattern in WATERMARK_PATTERNS:
        if re.search(pattern, line):
            return True
    return False


def clean_text_lines(text: str) -> List[str]:
    """Pulisce il testo rimuovendo le linee della filigrana"""
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        if not is_watermark_line(line):
            cleaned.append(line.strip())
    return [riga for riga in cleaned if riga]


def parse_presenze_line(line: str) -> Optional[Dict]:
    """
    Parsa una linea del foglio presenze.
    Gestisce anche linee con residui della filigrana all'inizio.
    Formato: "[garbage] GG N [ORE] [GIUST] [ORE_GIUST]"
    """
    # Prima pulisci la linea dalla filigrana all'inizio
    # Pattern per estrarre: giorno_settimana numero [giustificativo] [ore]
    
    # Pattern complessi che gestiscono la filigrana
    patterns = [
        # Con giustificativo e ore: "... LU 19 AI 6,40"
        r'.*?([A-Z]{2})\s+(\d{1,2})\s+([A-Z]{2})\s+([\d,]+)$',
        # Solo ore: "... VE 2 6,40"
        r'.*?([A-Z]{2})\s+(\d{1,2})\s+([\d,]+)$',
        # Solo giorno: "... SA 3"
        r'.*?([A-Z]{2})\s+(\d{1,2})$',
    ]
    
    # Lista dei giorni validi
    giorni_validi = ['LU', 'MA', 'ME', 'GI', 'VE', 'SA', 'DO']
    
    for pattern in patterns:
        match = re.search(pattern, line.strip())
        if match:
            groups = match.groups()
            giorno_sett = groups[0]
            
            # Verifica che sia un giorno valido
            if giorno_sett not in giorni_validi:
                continue
                
            result = {
                "giorno_settimana": giorno_sett,
                "giorno": int(groups[1]),
                "ore_ordinarie": None,
                "ore_straordinarie": None,
                "giustificativo": None
            }
            
            if len(groups) == 4:  # Con giustificativo e ore
                result["giustificativo"] = groups[2]
                result["ore_ordinarie"] = groups[3]
            elif len(groups) == 3:  # Solo ore
                # Verifica se il terzo gruppo è un codice giustificativo o ore
                if re.match(r'^[\d,]+$', groups[2]):
                    result["ore_ordinarie"] = groups[2]
                else:
                    result["giustificativo"] = groups[2]
            # len == 2: solo giorno, nessuna ora
            
            return result
    
    return None


def leggi_foglio_presenze(text: str) -> Dict:
    """Giorni, ore e giustificativi di un foglio presenze Zucchetti."""
    lines = clean_text_lines(text)
    
    result = {
        "tipo": "foglio_presenze",
        "azienda": {},
        "dipendente": {},
        "presenze": [],
        "riepilogo_giustificativi": []
    }
    
    # Estrai dati azienda
    for i, line in enumerate(lines):
        if "CERALDI GROUP" in line:
            result["azienda"]["ragione_sociale"] = line
        elif re.match(r'^PIAZZA|^VIA|^CORSO', line) and not result["azienda"].get("indirizzo"):
            result["azienda"]["indirizzo"] = line
        elif re.match(r'^\d{5}\s+[A-Z]+', line) and "NAPOLI" in line:
            # Es: "80143 NAPOLI (NA) Aut. 35685"
            match = re.match(r'^(\d{5})\s+([A-Z]+)\s+\(([A-Z]{2})\)\s*(?:Aut\.\s*(\d+))?', line)
            if match:
                result["azienda"]["cap"] = match.group(1)
                result["azienda"]["citta"] = match.group(2)
                result["azienda"]["provincia"] = match.group(3)
                if match.group(4):
                    result["azienda"]["autorizzazione"] = match.group(4)
        elif "Del " in line and "Sede" in line:
            match = re.search(r'Del\s+([\d-]+)\s+Sede\s+(\d+)', line)
            if match:
                result["azienda"]["data_autorizzazione"] = match.group(1)
                result["azienda"]["sede"] = match.group(2)
        elif line.startswith("Nr."):
            result["azienda"]["nr_documento"] = line.replace("Nr.", "").strip()
        elif re.match(r'^\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}$', line):
            result["azienda"]["data_stampa"] = line
    
    # Estrai dati dipendente
    for i, line in enumerate(lines):
        if re.match(r'^\d{6}/\d{7}/\d{10}', line):
            result["dipendente"]["codice"] = line.rstrip('/')
        elif re.match(r'^[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]$', line):
            result["dipendente"]["codice_fiscale"] = line
        elif "P.A.T. INAIL" in lines[i-1] if i > 0 else False:
            # La riga dopo "PERIODO DI RIFERIMENTO CODICE FISCALE P.A.T. INAIL"
            match = re.match(r'^([A-Za-z]+\s+\d{4})\s+([A-Z0-9]+)\s+([\d/]+)\s+(.+)$', line)
            if match:
                result["dipendente"]["periodo"] = match.group(1)
                result["dipendente"]["codice_fiscale"] = match.group(2)
                result["dipendente"]["pat_inail"] = match.group(3)
                result["dipendente"]["tipo_rapporto"] = match.group(4)
    
    # Cerca nome dipendente (di solito dopo il codice)
    for i, line in enumerate(lines):
        if result["dipendente"].get("codice") and i > 0:
            # Il nome è tipicamente la riga dopo il codice
            prev_line = lines[i-1] if i > 0 else ""
            if result["dipendente"]["codice"] in prev_line:
                if re.match(r'^[A-Z]+\s+[A-Z]+$', line):
                    result["dipendente"]["cognome_nome"] = line
                    # L'indirizzo è la riga successiva
                    if i + 1 < len(lines):
                        next_line = lines[i+1]
                        if re.match(r'^VIA|^PIAZZA|^CORSO|^VIALE', next_line):
                            result["dipendente"]["indirizzo"] = next_line
                            if i + 2 < len(lines):
                                result["dipendente"]["citta"] = lines[i+2]
                    break
    
    # Estrai presenze giornaliere
    for line in lines:
        presenza = parse_presenze_line(line)
        if presenza:
            result["presenze"].append(presenza)
    
    # Estrai riepilogo giustificativi
    # Pattern: "Ore ordinarie 113,20hm AI Ass.za ingiustif. 6,40hm FE Ferie 40,00hm"
    for line in lines:
        if "Ore ordinarie" in line or "hm" in line.lower():
            # Parse della riga riepilogo
            # Ore ordinarie
            match = re.search(r'Ore ordinarie\s+([\d,]+)hm', line)
            if match:
                result["riepilogo_giustificativi"].append({
                    "codice": "",
                    "descrizione": "Ore ordinarie",
                    "quantita": match.group(1),
                    "unita": "hm"
                })
            
            # Altri giustificativi
            giust_pattern = r'([A-Z]{2})\s+([A-Za-z.\s]+?)\s+([\d,]+)hm'
            for match in re.finditer(giust_pattern, line):
                result["riepilogo_giustificativi"].append({
                    "codice": match.group(1),
                    "descrizione": match.group(2).strip(),
                    "quantita": match.group(3),
                    "unita": "hm"
                })

    # Giorni EFFETTIVAMENTE lavorati = giorni con ore ordinarie e senza
    # giustificativo di assenza. Conteggio portato qui dalla copia `app/hr`
    # il 19/09/2026: la copia HR non e' mai stata usata (le sue tabelle
    # `app_employees`/`app_buste_paga` non esistono in Supabase), quindi il
    # dato non era mai arrivato in produzione.
    pres = result.get("presenze", [])
    result["giorni_lavorati"] = sum(
        1 for p in pres if p.get("ore_ordinarie") and not p.get("giustificativo")
    )
    result["giorni_con_giustificativo"] = sum(
        1 for p in pres if p.get("giustificativo")
    )

    return result


def leggi_corpo_cedolino(text: str) -> Dict:
    """Voci codificate, IRPEF, ratei e dati chiave dal corpo di una busta."""
    lines = clean_text_lines(text)
    full_text = ' '.join(lines)
    
    result = {
        "tipo": "busta_paga",
        "dipendente": {},
        "competenze": [],
        "trattenute": [],
        "irpef": {},
        "progressivi": {},
        "tfr": {},
        "ratei": {},
        "totali": {},
        "pagamento": {}
    }
    
    # Estrai dati dipendente dalla busta paga
    for i, line in enumerate(lines):
        # Codice dipendente e nome
        match = re.match(r'^(\d{7})\s+([A-Z]+\s+[A-Z]+)\s+([A-Z0-9]+)$', line)
        if match:
            result["dipendente"]["codice"] = match.group(1)
            result["dipendente"]["cognome_nome"] = match.group(2)
            result["dipendente"]["codice_fiscale"] = match.group(3)
        
        # Qualifica e livello
        if "Livello" in line:
            match = re.search(r'(\w+)\s+(\d+)\s+Livello\s+(\w+)', line)
            if match:
                result["dipendente"]["qualifica_codice"] = match.group(1)
                result["dipendente"]["livello_numero"] = match.group(2)
                result["dipendente"]["livello_descrizione"] = match.group(3)
        
        # Mansione
        if "CAMERIERE" in line or "CUOCO" in line or "BARISTA" in line:
            result["dipendente"]["mansione"] = line.strip()
    
    # Estrai competenze
    competenze_patterns = [
        (r'Z00001.*?Retribuzione.*?([\d,]+)', "Retribuzione"),
        (r'Z00250.*?Ferie godute.*?([\d,]+)', "Ferie godute"),
        (r'Z01100.*?Festivita.*?godute.*?([\d,]+)', "Festività godute"),
        (r'Z50000.*?13ma Mensilita.*?([\d,]+)', "13ma Mensilità"),
        (r'Z50022.*?14ma Mensilita.*?([\d,]+)', "14ma Mensilità"),
        (r'ZP9960.*?Arrotond.*?([\d,]+)', "Arrotondamento mese prec."),
    ]
    
    for pattern, nome in competenze_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            result["competenze"].append({
                "voce": nome,
                "importo": match.group(1)
            })
    
    # Estrai trattenute contributive
    trattenute_patterns = [
        (r'Z00000.*?Contributo IVS.*?([\d.,]+)\s+([\d,]+)%\s+([\d,]+)', "Contributo IVS"),
        (r'Z00054.*?FIS.*?D\.?Lgs\.?148.*?([\d.,]+)\s+([\d,]+)%\s+([\d,]+)', "FIS D.Lgs.148/2015"),
    ]
    
    for pattern, nome in trattenute_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            result["trattenute"].append({
                "voce": nome,
                "imponibile": match.group(1),
                "aliquota": match.group(2),
                "importo": match.group(3)
            })
    
    # Estrai calcolo IRPEF
    irpef_patterns = [
        (r'F02000.*?Imponibile IRPEF\s+([\d.,]+)', "imponibile"),
        (r'F02010.*?IRPEF lorda\s+([\d.,]+)', "irpef_lorda"),
        (r'F02500.*?Detrazioni lav\.?dip\.?\s+([\d.,]+)', "detrazioni_lavdip"),
        (r'F02703.*?Indennit.*?L\.?207.*?([\d.,]+)', "indennita_l207"),
        (r'F03020.*?Ritenute IRPEF\s+([\d.,]+)', "ritenute_irpef"),
        (r'F06000.*?Imponibile Tass\.?aut\.?\s+([\d.,]+)', "imponibile_tass_aut"),
        (r'F06010.*?IRPEF lorda Tass\.?aut\.?\s+([\d.,]+)', "irpef_lorda_tass_aut"),
        (r'F06020.*?Ritenute IRPEF Tass\.?aut\.?\s+([\d.,]+)', "ritenute_tass_aut"),
    ]
    
    for pattern, campo in irpef_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            result["irpef"][campo] = match.group(1)
    
    # Estrai addizionali
    add_patterns = [
        (r'F09110.*?Addizionale regionale.*?(\d{4})\s+([A-Z]+).*?Residuo\s+([\d.,]+)\s+([\d.,]+)', "addizionale_regionale"),
        (r'F09130.*?Addizionale comunale.*?(\d{4})\s+([A-Z]+).*?Residuo\s+([\d.,]+)\s+([\d.,]+)', "addizionale_comunale"),
    ]
    
    for pattern, campo in add_patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            result["irpef"][campo] = {
                "anno": match.group(1),
                "regione_comune": match.group(2),
                "residuo": match.group(3),
                "trattenuta": match.group(4)
            }
    
    # Estrai progressivi
    prog_match = re.search(r'Imp\.\s*INPS\s+Imp\.\s*INAIL\s+Imp\.\s*IRPEF\s+IRPEF\s+pagata\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)', full_text)
    if prog_match:
        result["progressivi"] = {
            "imp_inps": prog_match.group(1),
            "imp_inail": prog_match.group(2),
            "imp_irpef": prog_match.group(3),
            "irpef_pagata": prog_match.group(4)
        }
    
    # Estrai TFR
    tfr_match = re.search(r'T\.?F\.?R\.?.*?F\.?do\s*31/12.*?Rivalutaz.*?Imp\.?rival.*?Quota anno.*?TFR a fondi.*?Anticipi\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)', full_text)
    if tfr_match:
        result["tfr"] = {
            "fondo_31_12": tfr_match.group(1),
            "rivalutazione": tfr_match.group(2),
            "imp_rivalutazione": tfr_match.group(3),
            "quota_anno": tfr_match.group(4)
        }
    
    # Estrai ratei ferie e permessi
    ferie_match = re.search(r'Ferie\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+GG', full_text)
    if ferie_match:
        result["ratei"]["ferie"] = {
            "residuo_ap": ferie_match.group(1),
            "maturato": ferie_match.group(2),
            "goduto": ferie_match.group(3),
            "saldo": ferie_match.group(4),
            "unita": "GG"
        }
    
    permessi_match = re.search(r'Permessi\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s+ORE', full_text)
    if permessi_match:
        result["ratei"]["permessi"] = {
            "residuo_ap": permessi_match.group(1),
            "maturato": permessi_match.group(2),
            "saldo": permessi_match.group(3),
            "unita": "ORE"
        }
    
    # Estrai totali - Pattern specifici per il formato Zucchetti
    # "RATEI TOTALEsCOMPETENZE 1.754,67"
    totale_comp_match = re.search(r'TOTALE.?COMPETENZE\s+([\d.,]+)', full_text)
    if totale_comp_match:
        result["totali"]["totale_competenze"] = totale_comp_match.group(1)
    
    # "TOTALEsTRATTENUTE 318,75"
    totale_tratt_match = re.search(r'TOTALE.?TRATTENUTE\s+([\d.,]+)', full_text)
    if totale_tratt_match:
        result["totali"]["totale_trattenute"] = totale_tratt_match.group(1)
    
    # "NETTOsDELsMESE" seguito da "1.436,00€"
    netto_match = re.search(r'NETTO.?DEL.?MESE.*?([\d.,]+)\s*€', full_text, re.DOTALL)
    if netto_match:
        result["totali"]["netto_mese"] = netto_match.group(1)
    else:
        # Prova pattern alternativo
        netto_match2 = re.search(r'([\d.,]+)\s*€\s*COMUNICAZIONI', full_text)
        if netto_match2:
            result["totali"]["netto_mese"] = netto_match2.group(1)
    
    # Estrai IBAN pagamento - pattern specifico Zucchetti "IBANIT20C..."
    iban_match = re.search(r'IBAN\s*([A-Z]{2}\d{2}[A-Z0-9]{23})', full_text)
    if not iban_match:
        iban_match = re.search(r'IBAN([A-Z]{2}\d{2}[A-Z0-9]{23})', full_text)  # Senza spazio
    if iban_match:
        result["pagamento"]["iban"] = iban_match.group(1)
    
    banca_match = re.search(r'(BANCO\s+BPM[^I]*)', full_text)
    if banca_match:
        result["pagamento"]["banca"] = banca_match.group(1).strip()

    # --- Cattura GENERICA di tutte le voci del cedolino (massimo dato salvato) ---
    # Riga tipo: "C00001 Retribuzione 9,54850 79,99992 ORE 763,48" → codice,
    # descrizione, importi. Prefisso flessibile (C/F/Z/...): non dipende dal
    # formato Zucchetti specifico.
    voci = []
    _num = re.compile(r'-?\d{1,3}(?:\.\d{3})*,\d{2,6}|-?\d+,\d{2,6}')
    for line in lines:
        m = re.match(r'^([A-Z]\d{4,5})\b\s*(.*)$', line.strip())
        if not m:
            continue
        codice, resto = m.group(1), m.group(2)
        valori = _num.findall(resto)
        descr = _num.split(resto)[0].strip(' .-')
        voci.append({"codice": codice, "descrizione": descr, "valori": valori})
    result["voci"] = voci

    def _voce(codici=None, testo=None):
        for v in voci:
            if codici and v["codice"] in codici:
                return v
            if testo and testo.lower() in v["descrizione"].lower():
                return v
        return None

    def _imp(v):
        return v["valori"][-1] if v and v["valori"] else None

    # --- Dati chiave richiesti dal titolare ---
    r13 = _voce(codici={"C50000", "Z50000"}, testo="13ma Mensilit")
    r14 = _voce(codici={"C50022", "Z50022"}, testo="14ma Mensilit")
    l207 = _voce(codici={"F02703"}, testo="L.207")
    l207c = _voce(codici={"F09088"}, testo="207/24 cng")
    ti = _voce(codici={"F09081"}, testo="integrativo L.21")
    tir = _voce(codici={"F09083"})
    tic = _voce(codici={"F09084"})
    result["dati_chiave"] = {
        "rateo_13ma_presente": bool(r13), "rateo_13ma_importo": _imp(r13),
        "rateo_14ma_presente": bool(r14), "rateo_14ma_importo": _imp(r14),
        "indennita_l207_24": _imp(l207),
        "indennita_l207_24_cng_ann": _imp(l207c),
        "tratt_integrativo_l21": _imp(ti),
        "tratt_integrativo_l21_rata": _imp(tir),
        "tratt_integrativo_l21_cng": _imp(tic),
    }

    # --- Ore lavorate e giorni retribuiti dal riquadro 'Lavorato' (best effort) ---
    # I giorni EFFETTIVAMENTE lavorati si contano dal foglio presenze (campo
    # giorni_lavorati lì).
    lav = re.search(
        r'(?:Lavorato|Ore\s*lavorat\w*)\D{0,15}?(\d{1,3},\d{2})\s+(\d{1,2})\b',
        full_text, re.IGNORECASE,
    )
    if lav:
        result["ore_lavorate"] = lav.group(1)
        result["giorni_retribuiti"] = lav.group(2)

    return result
