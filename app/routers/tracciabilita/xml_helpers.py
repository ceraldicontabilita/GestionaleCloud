"""
Funzioni helper condivise per il parsing XML di fatture elettroniche
e le utility di normalizzazione testo.
"""
import re
import xml.etree.ElementTree as ET
try:
    from thefuzz import fuzz
except ImportError:
    from fuzzywuzzy import fuzz


def parse_fattura_xml(xml_content: bytes) -> dict:
    """Parse fattura elettronica XML e estrae i dati, inclusi lotti fornitori"""
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        root = ET.fromstring(xml_content.decode('utf-8'))

    result = {
        'fornitore': '',
        'piva': '',
        'numero_fattura': '',
        'data_fattura': '',
        'prodotti': []
    }

    for elem in root.iter():
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if tag == 'Denominazione' and not result['fornitore']:
            result['fornitore'] = (elem.text or '').strip().strip('"').strip("'")
        if tag == 'IdCodice' and not result['piva']:
            result['piva'] = elem.text or ''
        if tag == 'Numero' and not result['numero_fattura']:
            result['numero_fattura'] = elem.text or ''
        if tag == 'Data' and not result['data_fattura']:
            result['data_fattura'] = elem.text or ''

    for elem in root.iter():
        tag = elem.tag.split('}')[-1] if '}' in elem.tag else elem.tag
        if tag == 'DettaglioLinee':
            prodotto = {
                'descrizione': '', 'quantita': '', 'prezzo': '',
                'unita_misura': '', '_lotto_data': {}
            }
            altri_dati = []
            for child in elem:
                child_tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if child_tag == 'Descrizione':
                    prodotto['descrizione'] = (child.text or '').strip()
                elif child_tag == 'Quantita':
                    prodotto['quantita'] = child.text or ''
                elif child_tag == 'PrezzoUnitario':
                    prodotto['prezzo'] = child.text or ''
                elif child_tag == 'UnitaMisura':
                    prodotto['unita_misura'] = (child.text or '').strip().upper()
                elif child_tag == 'AltriDatiGestionali':
                    tipo = ''
                    rif_testo = ''
                    rif_data = ''
                    for sub in child:
                        sub_tag = sub.tag.split('}')[-1] if '}' in sub.tag else sub.tag
                        if sub_tag == 'TipoDato':
                            tipo = (sub.text or '').strip().upper()
                        elif sub_tag == 'RiferimentoTesto':
                            rif_testo = (sub.text or '').strip()
                        elif sub_tag == 'RiferimentoData':
                            rif_data = (sub.text or '').strip()

                    if tipo == 'DATI LOTTO' and rif_testo:
                        # SAIMA: 'Id: 617435 - Scadenza: 04/04/2026 - Qtà: 2' o 'Qt: 2'
                        # Nota: 'Qtà' può avere encoding corrotto (à fuori ASCII),
                        # quindi usiamo \S* per catturare qualsiasi carattere non-spazio dopo Qt
                        lotto_data = {}
                        id_m = re.search(r'Id:\s*(\w+)', rif_testo, re.IGNORECASE)
                        scad_m = re.search(r'Scadenza:\s*(\d{2}/\d{2}/\d{4})', rif_testo, re.IGNORECASE)
                        qt_m = re.search(r'Qt[^\s:]*\s*:\s*([\d.,]+)', rif_testo, re.IGNORECASE)
                        if id_m:
                            lotto_data['lotto_id_fornitore'] = id_m.group(1)
                        if scad_m:
                            lotto_data['data_scadenza'] = scad_m.group(1)
                        if qt_m:
                            qt_val = qt_m.group(1).replace(',', '.')
                            try:
                                lotto_data['quantita_originale'] = float(qt_val)
                            except ValueError:
                                pass
                        if lotto_data:
                            prodotto['_lotto_data'] = lotto_data

                    elif rif_testo and not prodotto['_lotto_data']:
                        # Naturissime / altro: testo lotto generico + data
                        lotto_data = {}
                        if re.match(r'^[A-Z]{2}\s*\d+', rif_testo):
                            lotto_data['lotto_id_fornitore'] = rif_testo
                            if rif_data:
                                lotto_data['data_scadenza'] = rif_data
                            prodotto['_lotto_data'] = lotto_data

            if prodotto['descrizione'] and _e_prodotto_valido(prodotto):
                result['prodotti'].append(prodotto)

    return result


def _e_prodotto_valido(prodotto: dict) -> bool:
    """Filtra righe XML che non sono prodotti reali."""
    desc = prodotto.get('descrizione', '').strip()
    if not desc:
        return False
    if desc.startswith('**') or desc.startswith('* '):
        return False
    PREFISSI_DA_SALTARE = [
        'LUOGO DI CONSEGNA', 'LUOGO CONSEGNA', 'INDIRIZZO DI CONSEGNA',
        'Rif. Doc.', 'Rif. Conferma', 'Rif. Ordine',
        'DESTINAZIONE MERCE', 'SEDE LEGALE', 'C/O ', 'c/o ',
    ]
    desc_upper = desc.upper()
    for prefisso in PREFISSI_DA_SALTARE:
        if desc_upper.startswith(prefisso.upper()) or prefisso in desc:
            return False
    if re.match(r'^\s*\(\d+\s+\d{2}/\d{2}/\d{2,4}\)', desc):
        return False
    if re.match(r'^\d{5}\s+[A-Z]', desc):
        return False
    if re.match(r'^\d{4,5}$', desc):
        return False
    try:
        prezzo = float(str(prodotto.get('prezzo', '0') or '0').replace(',', '.'))
        quantita = float(str(prodotto.get('quantita', '0') or '0').replace(',', '.'))
        if prezzo == 0 and quantita == 0:
            return False
    except (ValueError, TypeError):
        pass
    return True


def normalizza_testo(testo: str) -> str:
    """Normalizza testo per confronto"""
    if not testo:
        return ""
    testo = re.sub(r'\s+', ' ', testo.lower().strip())
    testo = re.sub(r'[^\w\s]', '', testo)
    return testo


def fuzzy_match(testo1: str, testo2: str, soglia: int = 70) -> bool:
    """Confronto fuzzy tra due stringhe con soglia di similarità"""
    if not testo1 or not testo2:
        return False
    t1 = normalizza_testo(testo1)
    t2 = normalizza_testo(testo2)
    ratio = fuzz.ratio(t1, t2)
    partial = fuzz.partial_ratio(t1, t2)
    token_sort = fuzz.token_sort_ratio(t1, t2)
    best_score = max(ratio, partial, token_sort)
    return best_score >= soglia


def cerca_match_ingrediente(ingrediente: str, prodotti_fattura: list, soglia: int = 70):
    """Cerca un match tra ingrediente e prodotti della fattura usando fuzzy matching"""
    ingrediente_norm = normalizza_testo(ingrediente)
    miglior_match = None
    miglior_score = 0
    for prodotto in prodotti_fattura:
        desc = prodotto.get('descrizione', '')
        desc_norm = normalizza_testo(desc)
        ratio = fuzz.ratio(ingrediente_norm, desc_norm)
        partial = fuzz.partial_ratio(ingrediente_norm, desc_norm)
        token_sort = fuzz.token_sort_ratio(ingrediente_norm, desc_norm)
        score = max(ratio, partial, token_sort)
        prima_parola = ingrediente_norm.split()[0] if ingrediente_norm else ""
        if prima_parola and len(prima_parola) > 2 and prima_parola in desc_norm:
            score += 15
        if score > miglior_score and score >= soglia:
            miglior_score = score
            miglior_match = {**prodotto, 'score': score}
    return miglior_match


def pulisci_nome_ingrediente(ingrediente: str) -> str:
    """Pulisce il nome dell'ingrediente rimuovendo codici lotto, fattura e info extra."""
    if not ingrediente:
        return ""
    testo = ingrediente.strip()
    testo = re.sub(r'\s+[xX]\s*\d+(?:[.,]\d+)?(?:\s*(?:kg|g|lt|ml|l))?(?=\s|$)', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+(non\s+)?contiene\s+allergeni.*$', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s*-\s*[A-Za-z\."]+(?:\s+[A-Za-z\."]+)*(?:\s+(?:S\.?[rR]\.?[lL]\.?|S\.?[pP]\.?[aA]\.?|srl|spa))?.*$', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+L\.?F?\.?\d*/?[\w\-]*', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+FVI/[\w\-]+', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+n°?\s*fatt\.?\s*[\w/\-]+', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s*-?\s*\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}', '', testo)
    testo = re.sub(r'\s+SACCHI\s+SALTECHNO.*$', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+DA\s+KG\.?\s*\d+(?:[.,]\d+)?', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+KG\.?\s*\d+(?:[.,]\d+)?', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+\d+(?:[.,]\d+)?\s*KG\b', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+\d+(?:[.,]\d+)?\s*(?:G|LT|ML|L)\b', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s*-\s*\d{5,}$', '', testo)
    testo = re.sub(r'\s+Orig\.?\s*\w+', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+RINFORZ\.?\w*', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+ASTUC\.?\w*', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+I\s+B\s+\w+', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+P[xX]\d+', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+\d+\^\s*\d*', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+\w*\d+\w*$', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+GR\.?\d+', '', testo, flags=re.IGNORECASE)
    testo = re.sub(r'\s+', ' ', testo)
    testo = re.sub(r'\s*-\s*$', '', testo)
    testo = re.sub(r'^\s*-\s*', '', testo)
    testo = testo.strip()
    if testo:
        parole = testo.split()
        parole_formattate = []
        for i, p in enumerate(parole):
            p_lower = p.lower()
            if p_lower in ['00', '0', 'man', 'man.', '0/man.']:
                parole_formattate.append(p_lower)
            elif i == 0:
                parole_formattate.append(p.capitalize())
            else:
                parole_formattate.append(p_lower)
        testo = ' '.join(parole_formattate)
    return testo


def estrai_quantita_da_descrizione(descrizione: str) -> tuple:
    """Estrae quantità e unità dalla descrizione del prodotto fattura.
    
    REGOLA: Legge SEMPRE la descrizione per trovare il peso fisico della confezione.
    Gestisce: KG, G, GR, GR., G., ML, LT + formati glued tipo G500, GR.9, BOSCOG500
    ESCLUDE: numeri seguiti da PORZIONI/PEZZI/PZ/NR (conteggi, non pesi)
    """
    if not descrizione:
        return (1, 'pz')
    desc = descrizione.upper()

    # Parole che indicano un conteggio di pezzi — NON un peso
    CONTEGGIO = {"PORZIONI", "PORZIONE", "PEZZI", "MONOPORZ", "MONODOSE",
                 "DOSE", "SLICE", "NR", "CONF"}

    patterns = [
        (r'(\d+(?:[.,]\d+)?)\s*KG\b', 'kg'),
        (r'\bKG[\.\s]*(\d+(?:[.,]\d+)?)', 'kg'),   # KG.0.250, KG 1.5
        (r'\bGR?[\.\s]+(\d+(?:[.,]\d+)?)\b', 'g'),
        (r'(?<=[A-Z])G(\d{3,})\b', 'g'),
        (r'\bG(\d{2,})\b', 'g'),
        (r'(\d+(?:[.,]\d+)?)\s*LT?\b', 'l'),
        (r'(\d+(?:[.,]\d+)?)\s*ML\b', 'ml'),
        (r'(\d+(?:[.,]\d+)?)\s*G\b', 'g'),
    ]
    for pattern, unita in patterns:
        match = re.search(pattern, desc)
        if not match:
            continue
        # Controlla la parola subito dopo il match
        end = match.end()
        rest = desc[end:end+20].strip()
        next_word = re.split(r'\W+', rest)[0] if rest else ""
        if next_word in CONTEGGIO:
            continue  # es. "G. 8 PORZIONI" → skip, è un conteggio
        qty = match.group(1).replace(',', '.')
        val = float(qty)
        if val > 0:
            return (val, unita)
    return (1, 'pz')
