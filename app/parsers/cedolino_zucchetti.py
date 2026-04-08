"""
Parser Cedolini Zucchetti (Paghe Web / CSC Napoli)
===================================================
Parsa PDF multi-dipendente con split per Nr. progressivo INAIL.
Ogni cedolino = 2 pagine: foglio presenze (Aut. 301) + busta paga (Aut. 299).

METODO: estrazione per coordinate X (non regex su testo lineare).
Layout colonne Aut. 299:
  x < 430        → Importo Base / informativo (non entra in totali)
  430 <= x <= 515 → TRATTENUTE
  x > 515        → COMPETENZE

Voci rilevate dai cedolini reali Ceraldi Group:
  000306 Recupero acconto     → TRATTENUTE (acconto dato precedentemente)
  Z00001 Retribuzione         → COMPETENZE
  Z00250 Ferie godute         → COMPETENZE
  Z01100/Z01138 Festivita'    → COMPETENZE
  Z50000 13ma | Z50022 14ma   → COMPETENZE
  Z40030 Straordinario 30%    → COMPETENZE
  009944 Magg.domenicale      → COMPETENZE
  Z00346/Z00347 Esonero IVS   → COMPETENZE
  F02703/F02702 Indennita'    → COMPETENZE
  000081 Anticipazione TFR    → COMPETENZE
  ZP8130 Fondo TFR 31/12      → COMPETENZE
  ZP8134 Quota TFR anno       → COMPETENZE
  Z00000 Contributo IVS       → TRATTENUTE
  Z00054 FIS                  → TRATTENUTE
  ZP8138 Fondo pensione       → TRATTENUTE
  F03020 Ritenute IRPEF       → TRATTENUTE
  F06020 Ritenute IRPEF Ts.   → TRATTENUTE
  F09110 Add. regionale       → TRATTENUTE (Residuo XX precede importo)
  F07020 IRPEF netta TFR      → TRATTENUTE
  F07030 Imposta rival. TFR   → TRATTENUTE
  F09600 IRPEF netta Lic.     → TRATTENUTE
  F09610/F09630 Rate add. Lic.→ TRATTENUTE
"""
import re
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

CF_PATTERN = re.compile(r'([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])')
IBAN_PATTERN = re.compile(r'(IT\d{2}[A-Z]\d{10}[0-9A-Z]{12})')
IMPORTO_RE = re.compile(r'^[\d.]+,\d{2}$')

MESI_IT = {
    'gennaio': 1, 'febbraio': 2, 'marzo': 3, 'aprile': 4,
    'maggio': 5, 'giugno': 6, 'luglio': 7, 'agosto': 8,
    'settembre': 9, 'ottobre': 10, 'novembre': 11, 'dicembre': 12,
}

# Soglie colonne (coordinate X)
X_TRATTENUTE_MIN = 430
X_TRATTENUTE_MAX = 515
X_COMPETENZE_MIN = 516

# Voci e il loro campo di destinazione
VOCE_MAP = {
    # COMPETENZE
    'Z00001': 'retribuzione',
    'Z00250': 'ferie_godute',
    'Z01100': 'festivita_godute',
    'Z01138': 'festivita_non_godute',
    'Z51001': 'ferie_godute',          # Recupero ferie godute +
    'Z50000': 'tredicesima',
    'Z50022': 'quattordicesima',
    'Z40030': 'straordinario',
    '009944': 'magg_domenicale',
    'Z00346': 'esonero_ivs',
    'Z00347': 'esonero_ivs',
    'F02703': 'indennita',
    'F02702': 'indennita',
    '000081': 'anticipo_tfr',
    'ZP8130': 'tfr_fondo_31_12',
    'ZP8134': 'tfr_quota_anno',
    'ZP8142': 'tfr_rivalutazione',
    # TRATTENUTE
    '000306': 'recupero_acconto',
    'Z00000': 'contributi_inps',
    'Z00054': 'fis',
    'ZP8138': 'fondo_pensione',
    'F03020': 'irpef',
    'F06020': 'irpef_tass_separata',
    'F07020': 'irpef_tfr',
    'F07030': 'imposta_rival_tfr',
    'F09110': 'add_regionale',
    'F09610': 'add_regionale',
    'F09600': 'irpef_liquidazione',
    'F09630': 'add_comunale',
    'ZP9960': 'arrotondamento',
    # INFORMATIVI (solo importo base — non in totali)
    'F02000': None, 'F02010': None, 'F02500': None,
    'F06000': None, 'F06010': None,
    'F06990': None, 'F06992': None,
    'F07017': None, 'F07530': None,
    'F08993': None, 'F09000': None,
    'F09443': None, 'F09500': None,
    'F09081': None, 'F09585': None,
    'F02702': 'indennita',   # Indennita' L.143/2024
}

# Campi che vanno in COMPETENZE (per classificare voci non in VOCE_MAP)
CAMPI_COMPETENZE = {
    'retribuzione', 'ferie_godute', 'festivita_godute', 'festivita_non_godute',
    'tredicesima', 'quattordicesima', 'straordinario', 'magg_domenicale',
    'esonero_ivs', 'indennita', 'anticipo_tfr',
    'tfr_fondo_31_12', 'tfr_quota_anno', 'tfr_rivalutazione',
}


def _parse_importo(s: str) -> float:
    try:
        return float(s.replace(".", "").replace(",", "."))
    except (ValueError, TypeError):
        return 0.0


def _parse_data(s: str) -> str:
    for fmt in ("%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s


def _extract_periodo_from_text(text: str) -> tuple:
    for m_name, m_num in MESI_IT.items():
        m = re.search(rf'{m_name}\s+(\d{{4}})', text, re.I)
        if m:
            return m_num, int(m.group(1))
    return 0, 0


def _parse_page_words(page) -> List[tuple]:
    """Estrae words con coordinate (x0, y0, text)."""
    return [(w[0], w[1], w[4]) for w in page.get_text("words")]


def _group_by_row(words: List[tuple], y_tolerance: int = 3) -> List[List[tuple]]:
    """Raggruppa words per riga (y simile)."""
    if not words:
        return []
    rows = []
    current_y = words[0][1]
    current_row = []
    for w in sorted(words, key=lambda w: (round(w[1] / y_tolerance), w[0])):
        x, y, text = w
        if abs(y - current_y) > y_tolerance:
            if current_row:
                rows.append(sorted(current_row, key=lambda r: r[0]))
            current_row = [w]
            current_y = y
        else:
            current_row.append(w)
    if current_row:
        rows.append(sorted(current_row, key=lambda r: r[0]))
    return rows


def _is_importo(s: str) -> bool:
    return bool(IMPORTO_RE.match(s.replace(".", "", 1)))


def parse_cedolino_pdf(pdf_path: str = None, pdf_bytes: bytes = None) -> List[Dict[str, Any]]:
    """
    Parsa PDF cedolini Zucchetti multi-dipendente.
    Usa coordinate X per distinguere TRATTENUTE da COMPETENZE.
    Ritorna lista di cedolini (uno per dipendente).
    """
    import fitz

    if pdf_path:
        doc = fitz.open(pdf_path)
    elif pdf_bytes:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    else:
        raise ValueError("Serve pdf_path o pdf_bytes")

    # Raggruppa pagine per dipendente usando Nr. progressivo
    # Ogni dipendente ha Aut.301 (presenze) + Aut.299 (cedolino) — usiamo solo 299
    pages_299 = []
    for page in doc:
        text = page.get_text()
        if 'Aut. 299' in text or 'Autorizzazione Inail n. 299' in text or 'Autorizzazione Inail n.        299' in text:
            pages_299.append(page)

    if not pages_299:
        # Fallback: usa tutte le pagine
        pages_299 = list(doc.pages())

    cedolini = []
    for page in pages_299:
        ced = _parse_cedolino_page(page)
        if ced and (ced.get("codice_fiscale") or ced.get("codice_dipendente")):
            cedolini.append(ced)

    doc.close()
    logger.info(f"Parsati {len(cedolini)} cedolini da {len(pages_299)} pagine Aut.299")
    return cedolini


def _parse_cedolino_page(page) -> Optional[Dict[str, Any]]:
    """Parsa una singola pagina Aut.299 usando coordinate X."""
    text = page.get_text()
    words = _parse_page_words(page)

    result: Dict[str, Any] = {
        # Anagrafica
        "nr_progressivo": "",
        "codice_dipendente": "",
        "codice_fiscale": "",
        "cognome": "",
        "nome": "",
        "mese": 0,
        "anno": 0,
        "livello": "",
        "mansione": "",
        "part_time_perc": None,
        "data_assunzione": "",
        "data_cessazione": "",
        "iban": "",
        # Competenze
        "retribuzione": 0.0,
        "ferie_godute": 0.0,
        "festivita_godute": 0.0,
        "festivita_non_godute": 0.0,
        "tredicesima": 0.0,
        "quattordicesima": 0.0,
        "straordinario": 0.0,
        "magg_domenicale": 0.0,
        "esonero_ivs": 0.0,
        "indennita": 0.0,
        "anticipo_tfr": 0.0,
        "tfr_fondo_31_12": 0.0,
        "tfr_quota_anno": 0.0,
        "tfr_rivalutazione": 0.0,
        "altre_competenze": 0.0,
        "totale_competenze": 0.0,
        # Trattenute
        "recupero_acconto": 0.0,      # 000306 acconto dato
        "contributi_inps": 0.0,
        "fis": 0.0,
        "fondo_pensione": 0.0,
        "irpef": 0.0,
        "irpef_tass_separata": 0.0,
        "irpef_tfr": 0.0,
        "imposta_rival_tfr": 0.0,
        "add_regionale": 0.0,
        "add_comunale": 0.0,
        "irpef_liquidazione": 0.0,
        "arrotondamento": 0.0,
        "altre_trattenute": 0.0,
        "totale_trattenute": 0.0,
        # Netto/Lordo
        "netto": 0.0,
        "lordo": 0.0,
        # Progressivi anno
        "imp_inps_anno": 0.0,
        "imp_irpef_anno": 0.0,
        "irpef_pagata_anno": 0.0,
        # Ore
        "ore_ordinarie": 0.0,
        "ore_straordinario": 0.0,
        # Dedup
        "paga_base": 0.0,
        "imp_inail_anno": 0.0,
        "dedup_key": "",
    }

    # ── Anagrafica da testo grezzo ────────────────────────────────────
    # Nr. progressivo
    m = re.search(r'Nr\.\s*(\d{5,6})', text)
    if m:
        result["nr_progressivo"] = m.group(1)

    # Periodo
    result["mese"], result["anno"] = _extract_periodo_from_text(text)

    # Codice fiscale dipendente
    ceraldi_piva = "04523831214"
    for m in CF_PATTERN.finditer(text):
        cf = m.group(1)
        if ceraldi_piva not in cf:
            result["codice_fiscale"] = cf
            break

    # IBAN
    m = IBAN_PATTERN.search(text)
    if m:
        result["iban"] = m.group(1)

    # Part time
    m = re.search(r'Part\s*Time\s*([\d,]+)\s*%', text, re.I)
    if m:
        result["part_time_perc"] = float(m.group(1).replace(",", "."))

    # Codice dipendente + nome/cognome
    # Formato: "0300015\nCAPEZZUTO ALESSANDRO\nCPZLSN86D02F839I"
    m = re.search(r'(\d{7})\s*\n\s*([A-ZÀÈÌÒÙ\'][A-ZÀÈÌÒÙ\' ]+?)\s*\n\s*([A-Z]{6}\d{2})', text)
    if m:
        result["codice_dipendente"] = m.group(1)
        nome_completo = m.group(2).strip()
        parts = nome_completo.split()
        if len(parts) >= 2:
            result["cognome"] = parts[0].title()
            result["nome"] = " ".join(parts[1:]).title()

    # Date assunzione/cessazione
    dates = re.findall(r'(\d{2}-\d{2}-\d{4})', text)
    if len(dates) >= 2:
        result["data_assunzione"] = _parse_data(dates[1])
    if len(dates) >= 3:
        result["data_cessazione"] = _parse_data(dates[2])

    # Livello e mansione
    m = re.search(r"(\d['°]?\s*Livello)", text, re.I)
    if m:
        result["livello"] = m.group(1).strip()
    m = re.search(r"(?:\d['°]?\s*Livello)\s*\n\s*([A-ZÀÈÌÒÙ][A-ZÀÈÌÒÙ ]{2,35})", text)
    if m:
        result["mansione"] = m.group(1).strip().title()

    # Ore ordinarie (dalla sezione LAVORATO)
    m = re.search(r'(\d+)\s+([\d,]+)\s+([\d,]+)\s+([\d.,]+)\s+(\d+)', text)
    if m:
        try:
            result["ore_ordinarie"] = float(m.group(4).replace(",", ".").replace(".", "", m.group(4).count(".")-1) if m.group(4).count(".") > 1 else m.group(4).replace(",", "."))
        except ValueError:
            pass

    # ── Parse voci per coordinate X ──────────────────────────────────
    rows = _group_by_row(words, y_tolerance=5)

    for row in rows:
        if not row:
            continue

        # Il codice voce è sempre a x~39 (tra 35 e 60)
        # Le righe possono iniziare con '*' a x=25 — quindi non usiamo row[0]
        codice = None
        for x, y, word in row:
            if 35 <= x <= 60:
                w = word.strip()
                if 4 <= len(w) <= 7 and re.match(r'^[A-Z0-9]+$', w):
                    codice = w
                    break
        if codice is None:
            continue

        # Trova importi sulla stessa riga classificati per X
        importi_trattenute = []
        importi_competenze = []

        for x, y, word in row:
            if _is_importo(word):
                if X_TRATTENUTE_MIN <= x <= X_TRATTENUTE_MAX:
                    importi_trattenute.append(_parse_importo(word))
                elif x > X_COMPETENZE_MIN:
                    importi_competenze.append(_parse_importo(word))

        # Determina campo di destinazione
        campo = VOCE_MAP.get(codice)

        if campo is None and codice not in VOCE_MAP:
            # Voce sconosciuta — classifica per posizione X
            if importi_trattenute and not importi_competenze:
                campo = 'altre_trattenute'
            elif importi_competenze and not importi_trattenute:
                campo = 'altre_competenze'
        
        if campo is None:
            continue  # Voce informativa, skip

        # Assegna importo al campo
        if campo in CAMPI_COMPETENZE or campo in ('tfr_fondo_31_12', 'tfr_quota_anno', 'tfr_rivalutazione', 'altre_competenze'):
            if importi_competenze:
                result[campo] = round(result.get(campo, 0.0) + importi_competenze[-1], 2)
        else:
            # Trattenuta
            if importi_trattenute:
                result[campo] = round(result.get(campo, 0.0) + importi_trattenute[-1], 2)
            elif importi_competenze and campo == 'recupero_acconto':
                # Caso edge: l'importo potrebbe essere classificato diversamente
                result[campo] = round(result.get(campo, 0.0) + importi_competenze[-1], 2)

    # ── Totali per coordinate (testo usa 's' come separatore) ──────────
    # TOTALEsCOMPETENZE e TOTALEsTRATTENUTE → cerca importo vicino (y±5, x>500)
    IMPORTO_RE_STR = re.compile(r'^[\d.]+,\d{2}$')
    for x, y, word in words:
        word_up = word.upper()
        if 'COMPETENZE' in word_up and 'TOTALE' in word_up:
            importi = [(wx, _parse_importo(wt)) for wx, wy, wt in words
                       if IMPORTO_RE_STR.match(wt) and abs(wy - y) <= 5 and wx > 500]
            if importi:
                result["totale_competenze"] = importi[0][1]
        elif 'TRATTENUTE' in word_up and 'TOTALE' in word_up:
            importi = [(wx, _parse_importo(wt)) for wx, wy, wt in words
                       if IMPORTO_RE_STR.match(wt) and abs(wy - y) <= 5 and wx > 500]
            if importi:
                result["totale_trattenute"] = importi[0][1]
        elif 'NETTO' in word_up and ('MESE' in word_up or 'BUSTA' in word_up or 'PAGARE' in word_up):
            importi = [(wx, _parse_importo(wt)) for wx, wy, wt in words
                       if IMPORTO_RE_STR.match(wt) and abs(wy - y) <= 5 and wx > 400]
            if importi:
                result["netto"] = importi[0][1]

    # Fallback netto: importo prima del simbolo €
    if result["netto"] == 0.0:
        m = re.search(r'([\d.]+,\d{2})\s*€', text, re.I)
        if m:
            result["netto"] = _parse_importo(m.group(1))

    # Paga base oraria (da intestazione elementi retribuzione)
    # Layout: "PAGA BASE\n5,46494" oppure "PAGA BASE 5,46494"
    m = re.search(r'PAGA\s+BASE[^\d]+(\d+,\d{5})', text, re.I)
    if m:
        result["paga_base"] = _parse_importo(m.group(1))

    # Progressivi anno
    m = re.search(r'Imp\.\s*INPS\s+([\d.]+,\d{2})', text, re.I)
    if m:
        result["imp_inps_anno"] = _parse_importo(m.group(1))
    m = re.search(r'Imp\.\s*IRPEF\s+([\d.]+,\d{2})', text, re.I)
    if m:
        result["imp_irpef_anno"] = _parse_importo(m.group(1))
    m = re.search(r'IRPEF\s+pagata\s+([\d.]+,\d{2})', text, re.I)
    if m:
        result["irpef_pagata_anno"] = _parse_importo(m.group(1))
    # Imp. INAIL progressivo
    m = re.search(r'Imp\.\s*INAIL\s+([\d.]+,\d{2})', text, re.I)
    if m:
        result["imp_inail_anno"] = _parse_importo(m.group(1))

    # TFR dalla sezione PROGRESSIVI in fondo al cedolino
    # Layout riga: "F.do 31/12  <fondo>   Rivalutaz.  <rival>  Imp.rival.  <imp>  Quota anno  <quota>"
    m = re.search(r'F\.do\s+31/12[^\d]+(\d[\d.]+,\d{2})', text, re.I)
    if m:
        result["tfr_fondo_31_12"] = _parse_importo(m.group(1))
    m = re.search(r'Quota\s+anno[^\d]+(\d[\d.]+,\d{2})', text, re.I)
    if m:
        result["tfr_quota_anno"] = _parse_importo(m.group(1))
    m = re.search(r'Rivalutaz\.\s+(\d[\d.]+,\d{2})', text, re.I)
    if m:
        result["tfr_rivalutazione"] = _parse_importo(m.group(1))

    # Lordo = totale_competenze se disponibile
    result["lordo"] = result["totale_competenze"] if result["totale_competenze"] > 0 else round(
        result["retribuzione"] + result["ferie_godute"] + result["festivita_godute"] +
        result["tredicesima"] + result["quattordicesima"] + result["straordinario"] +
        result["indennita"] + result["esonero_ivs"], 2
    )

    result["dedup_key"] = f"{result['codice_fiscale']}_{result['mese']:02d}_{result['anno']}"
    return result
