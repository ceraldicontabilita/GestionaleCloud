"""
Parser F24 Commercialista
Estrae dati da PDF F24 compilati dalla commercialista
Distingue correttamente debiti da crediti basandosi sulle coordinate X
Distingue le sezioni basandosi sulle coordinate Y
"""
import re
import fitz  # PyMuPDF
from typing import Dict, Any
import logging
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from app.utils.numeri_italiani import parse_importo_ita

logger = logging.getLogger(__name__)


def _rateazione_e_anno(tokens):
    """Separa la rateazione (anche ``0101``) dall'anno d'imposta."""
    values = [str(token).strip() for token in tokens]
    anno = next((value for value in values if re.fullmatch(r"20\d{2}", value)), "")
    before_year = values[:values.index(anno)] if anno in values else values
    rateazione = next(
        (value.replace("/", "") for value in before_year if re.fullmatch(r"\d{2}/\d{2}", value)),
        "",
    )
    if not rateazione:
        rateazione = next((value for value in before_year if re.fullmatch(r"\d{4}", value)), "")
    if not rateazione:
        months = [value for value in before_year if re.fullmatch(r"\d{1,2}", value) and int(value) > 0]
        if months:
            rateazione = f"00{months[-1].zfill(2)}"
    return rateazione, anno


def _data_versamento_da_testo(text: str) -> str:
    """Estrae la data bancaria anche quando il PDF separa ogni cifra."""
    patterns = [
        r'[Ss]cadenza\s*(\d{2})/(\d{2})/(\d{4})',
        r'data\s*di\s*pagamento[:\s]*(\d{2})[/\s-](\d{2})[/\s-](\d{4})',
        r'(\d{2})\s+(\d{2})\s+(\d{4})\s*(?:SALDO|codice)',
        r'giorno\s*mese\s*anno\s*(\d{2})\s*(\d{2})\s*(\d{4})',
    ]
    for pattern in patterns:
        trovato = re.search(pattern, text, re.IGNORECASE)
        if trovato:
            gg, mm, yyyy = trovato.groups()
            try:
                return datetime(int(yyyy), int(mm), int(gg)).date().isoformat()
            except ValueError:
                continue

    candidati = re.findall(
        r'(?m)^\s*([0-3])\s+(\d)\s+([01])\s+(\d)\s+(2)\s+(0)\s+(\d)\s+(\d)\s*$',
        text,
    )
    for gruppi in reversed(candidati):
        try:
            return datetime.strptime("".join(gruppi), "%d%m%Y").date().isoformat()
        except ValueError:
            continue
    return ""


def parse_importo(value: str) -> float:
    """Converte stringa importo italiano in float."""
    return parse_importo_ita(value)


def parse_periodo(mese: str, anno: str) -> str:
    """Formatta periodo riferimento."""
    mese = mese.strip().zfill(2) if mese else ""
    anno = anno.strip() if anno else ""
    return f"{mese}/{anno}" if mese and anno and mese != "00" else anno or mese


def _importo_cents_da_token(parts) -> int:
    """Ricompone un campo F24 direttamente in centesimi interi.

    I modelli a caselle possono esporre migliaia, virgola e centesimi come
    parole PDF separate.  La normalizzazione passa da ``Decimal`` una sola
    volta; il valore canonico restituito al parser e' sempre un intero.
    """
    if not parts:
        return 0
    ordered = sorted(parts, key=lambda item: item[0])
    values = [str(value).strip() for _x, value in ordered]
    joined = "".join(values)
    # PyMuPDF colloca spesso la virgola su una baseline diversa e quindi in
    # un'altra riga. Due caselle finali sono i centesimi, non altre centinaia.
    if (
        "," not in joined
        and len(values) >= 2
        and re.fullmatch(r"\d{2}", values[-1])
        and ordered[-1][0] - ordered[-2][0] <= 45
    ):
        joined = "".join(values[:-1]) + "," + values[-1]
    joined = re.sub(r"[^0-9.,]", "", joined)
    joined = re.sub(r",+", ",", joined)
    # I modelli F24 storici contengono talvolta una seconda virgola grafica
    # dopo un importo gia' completo ("137,37" + ","). Non e' un'altra
    # casella decimale e non deve azzerare il valore.
    joined = re.sub(r"^[.,]+|[.,]+$", "", joined)
    if not re.search(r"\d", joined):
        return 0
    # Nei campi a caselle dell'F24 una sequenza compatta senza separatore e'
    # espressa in centesimi: le ultime due cifre sono sempre i decimali.
    # Esempi reali: 123 -> 1,23; 1234 -> 12,34.
    if re.fullmatch(r"\d+", joined):
        return int(joined)
    try:
        normalized = joined.replace(".", "").replace(",", ".")
        return int((Decimal(normalized) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return 0


def _importo_da_token(parts) -> float:
    """Compatibilita' API: visualizzazione derivata dai centesimi canonici."""
    return _importo_cents_da_token(parts) / 100


def _dati_anagrafici_da_coordinate(doc) -> Dict[str, str]:
    """Legge contribuente e intermediario da aree distinte del modello."""
    result: Dict[str, str] = {}
    for page in doc:
        rows = {}
        for x0, y0, x1, _y1, word, *_rest in page.get_text("words"):
            # Nei modelli 2026 l'etichetta e le caselle del codice fiscale
            # hanno baseline differenti di 1-2 punti. Una fascia da 8 punti
            # le ricompone senza inglobare la riga anagrafica successiva.
            rows.setdefault(round(y0 / 8) * 8, []).append((x0, x1, word.strip()))
        for row in rows.values():
            ordered = sorted(row, key=lambda item: item[0])
            compact = "".join(item[2] for item in ordered).upper()
            if "INTERMEDIARIO:" in compact:
                for _x0, _x1, token in ordered:
                    candidate = re.sub(r"\W", "", token.upper())
                    if re.fullmatch(r"[A-Z0-9]{16}|\d{11}", candidate):
                        result.setdefault("intermediario_codice_fiscale", candidate)
                        break
            if "FISCALE" not in compact:
                continue
            # Il vecchio layout spezza CODICE FISCALE in token come
            # ``C O D ICE FIS C A LE``. Individuiamo quindi la fine
            # dell'etichetta sulla stringa cumulativa, non sul singolo token:
            # in caso contrario le lettere CODCA venivano anteposte al CF.
            label_end = 0
            label_text = ""
            for _x0, x1, token in ordered:
                label_text += re.sub(r"[^A-Z0-9]", "", token.upper())
                if "CODICEFISCALE" in label_text:
                    label_end = x1
                    break
            if not label_end:
                continue
            box_chars = []
            for x0, _x1, token in ordered:
                normalized = re.sub(r"[^A-Z0-9]", "", token.upper())
                if label_end < x0 < 330 and len(normalized) == 1:
                    box_chars.append(normalized)
            chars = "".join(box_chars)
            if len(chars) == 16 and re.fullmatch(r"[A-Z0-9]{16}", chars):
                result.setdefault("codice_fiscale", chars)
            elif len(chars) == 11 and chars.isdigit():
                result.setdefault("codice_fiscale", chars)
    return result


def _codice_regione_da_riga(row) -> str:
    """Estrae il codice regione anche se a sinistra c'e' testo marginale.

    Alcuni PDF sovrappongono alla prima colonna frammenti dell'indirizzo del
    software produttore. Basarsi sui primi token faceva perdere ``05`` nelle
    prime righe IRAP pur essendo chiaramente presente nel modulo.
    """
    candidati = sorted(
        (
            (float(item.get("x", 0)), str(item.get("word", "")).strip())
            for item in row
            if 28 <= float(item.get("x", 0)) <= 95
        ),
        key=lambda item: item[0],
    )
    for index, (_x, value) in enumerate(candidati):
        if re.fullmatch(r"0[1-9]|1\d|2[0-1]", value):
            return value
        if value != "0" or index + 1 >= len(candidati):
            continue
        next_x, next_value = candidati[index + 1]
        if re.fullmatch(r"\d", next_value) and next_x - candidati[index][0] <= 24:
            combined = value + next_value
            if re.fullmatch(r"0[1-9]", combined):
                return combined
    return ""


def _saldo_da_coordinate(page) -> float | None:
    rows = {}
    for x0, y0, x1, _y1, word, *_rest in page.get_text("words"):
        rows.setdefault(round(y0 / 4) * 4, []).append((x0, x1, word.strip()))
    label_y = None
    for y, row in rows.items():
        compact = "".join(token for _x0, _x1, token in sorted(row)).upper()
        if "SALDOFINALE" in compact:
            label_y = y
    if label_y is None:
        return None
    parts = []
    for y, row in rows.items():
        if label_y - 12 <= y <= label_y + 28:
            for x0, _x1, token in row:
                if x0 >= 515 and re.fullmatch(r"[\d.,]+", token):
                    parts.append((x0, token))
    return _importo_cents_da_token(parts) / 100 if parts else None


def extract_text_from_pdf(pdf_path: str = None, pdf_content: bytes = None) -> str:
    """
    Estrae tutto il testo da un PDF.
    Supporta sia filepath che bytes (architettura Drive/Supabase).
    """
    try:
        from app.services.pdf_text_extraction import extract_pdf_text

        if pdf_content:
            content = pdf_content
        elif pdf_path:
            with open(pdf_path, "rb") as stream:
                content = stream.read()
        else:
            return ""
        return extract_pdf_text(content, max_pages=None, include_tail=False)
    except Exception as e:
        logger.error(f"Errore estrazione PDF: {e}")
        return ""


def parse_f24_commercialista(pdf_path: str = None, pdf_content: bytes = None) -> Dict[str, Any]:
    """
    Parsa un F24 PDF della commercialista ed estrae tutti i dati.
    Supporta sia filepath che bytes (architettura Drive/Supabase).

    Args:
        pdf_path: Percorso file PDF (legacy)
        pdf_content: Contenuto PDF in bytes (Drive/Supabase)

    Layout F24 standard:
    - Colonna DEBITO: X ~357-389 (euro + centesimi)
    - Colonna CREDITO: X ~443-475 (euro + centesimi)
    - Sezioni separate per coordinata Y
    """
    result = {
        "dati_generali": {},
        "sezione_erario": [],
        "sezione_inps": [],
        "sezione_regioni": [],
        "sezione_tributi_locali": [],
        "sezione_imu": [],
        "sezione_inail": [],
        "totali": {},
        "has_ravvedimento": False,
        "codici_ravvedimento": [],
        "modelli": [],
        "diagnostica_pagine": [],
    }

    from app.constants.codici_ravvedimento import CODICI_RAVVEDIMENTO

    try:
        if pdf_content:
            doc = fitz.open(stream=pdf_content, filetype="pdf")
        elif pdf_path:
            doc = fitz.open(pdf_path)
        else:
            return {"error": "Nessun PDF fornito"}
    except Exception as e:
        logger.error(f"Errore apertura PDF: {e}")
        return {"error": f"Impossibile aprire il PDF: {e}"}

    text = extract_text_from_pdf(pdf_path=pdf_path, pdf_content=pdf_content)
    if not text:
        doc.close()
        return {"error": "Impossibile estrarre testo dal PDF"}

    # ============================================
    # DATI GENERALI
    # ============================================

    coordinate_identity = _dati_anagrafici_da_coordinate(doc)
    result["dati_generali"].update(coordinate_identity)

    upper_text = text.upper()
    if "STAMPA DI PROVA" in upper_text:
        result["dati_generali"]["natura_documento"] = "F24_STAMPA_DI_PROVA"
    elif "PRESENTAZIONE INTERMEDIARIO" in upper_text:
        result["dati_generali"]["natura_documento"] = "F24_MODELLO_PRESENTATO"
    else:
        result["dati_generali"]["natura_documento"] = "F24_MODELLO"

    cf_patterns = [
        r'CODICE\s*FISCALE\s*[\n\s]*([A-Z0-9]{11,16})',
        r'(\d{11})\s*(?:cognome|ragione)',
        r'\b([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b',
        r'(\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d\s*\d)',
    ]
    if not result["dati_generali"].get("codice_fiscale"):
        intermediary = result["dati_generali"].get("intermediario_codice_fiscale")
        for pattern in cf_patterns:
            cf_match = re.search(pattern, text, re.IGNORECASE)
            if cf_match:
                cf = cf_match.group(1).replace(' ', '').upper()
                if (len(cf) == 11 or len(cf) == 16) and cf != intermediary:
                    result["dati_generali"]["codice_fiscale"] = cf
                    break

    ragione_sociale_match = re.search(r'CERALDI\s+GROUP\s+S\.?R\.?L\.?', text, re.IGNORECASE)
    if ragione_sociale_match:
        result["dati_generali"]["ragione_sociale"] = "CERALDI GROUP S.R.L."

    coobligor_match = re.search(
        r"COOBBLIGATO(?:\s+CODICE\s+FISCALE)?\s*[:\s]*([A-Z0-9]{11,16})",
        text, re.IGNORECASE,
    )
    result["dati_generali"].update({
        "taxpayer_id": result["dati_generali"].get("codice_fiscale"),
        "intermediary_id": result["dati_generali"].get("intermediario_codice_fiscale"),
        "coobbligato_codice_fiscale": coobligor_match.group(1).upper() if coobligor_match else None,
        "conto_addebito": None,
        "iban_addebito": None,
        "banca_addebito": None,
        "identita_stato": "VERIFICATA" if result["dati_generali"].get("codice_fiscale") else "IDENTITA_AMBIGUA",
        "identita_conflitti": [],
    })

    data_stampa = _data_versamento_da_testo(text)
    if data_stampa:
        # Un modello/stampa non e' una quietanza: la data e' conservata come
        # data di stampa/compilazione.  L'alias legacy resta solo per le viste
        # storiche, marcato esplicitamente come non probatorio.
        result["dati_generali"]["data_stampa"] = data_stampa
        result["dati_generali"]["data_compilazione"] = data_stampa
        result["dati_generali"]["scadenza_nominale"] = data_stampa
        result["dati_generali"]["data_pagamento"] = None
        result["dati_generali"]["data_versamento"] = data_stampa
        result["dati_generali"]["data_versamento_provenienza"] = "MODELLO_NON_PAGAMENTO"

    if 'SEMPLIFICATO' in text.upper():
        result["dati_generali"]["tipo_f24"] = "F24 Semplificato"
    elif 'ORDINARIO' in text.upper():
        result["dati_generali"]["tipo_f24"] = "F24 Ordinario"
    else:
        result["dati_generali"]["tipo_f24"] = "F24"

    # ============================================
    # COORDINATE PER ESTRAZIONE IMPORTI
    # ============================================
    # Layout F24: importi iniziano dopo X=340
    IMPORTO_X_START = 340
    DEBITO_X_MAX = 410
    CREDITO_X_MIN = 440

    # Soglie Y per sezioni (approssimate, variano per PDF)
    # Le determineremo dinamicamente cercando le intestazioni

    tributi_visti = set()
    page_models: dict[int, int | None] = {}
    page_balances: dict[int, float] = {}

    def _extract_importo_cents_coordinate(row):
        """Estrae debito e credito da una riga basandosi sulle coordinate."""
        debito_parts = []
        credito_parts = []

        for item in row:
            x = item['x']
            word = item['word']

            if word in ['+/–', '+/-', '+', '-']:
                continue
            if not re.match(r'^[\d.,]+$', word):
                continue

            if x > IMPORTO_X_START and x <= DEBITO_X_MAX:
                debito_parts.append((x, word))
            elif x >= CREDITO_X_MIN:
                credito_parts.append((x, word))

        return _importo_cents_da_token(debito_parts), _importo_cents_da_token(credito_parts)

    def extract_importo_cents(row):
        """Estrae gli importi canonici come interi di centesimi."""
        debito_parts = []
        credito_parts = []
        for item in row:
            x = item['x']
            word = item['word']
            if word in ['+/â€“', '+/-', '+', '-'] or not re.match(r'^[\d.,]+$', word):
                continue
            if x > IMPORTO_X_START and x <= DEBITO_X_MAX:
                debito_parts.append((x, word))
            elif x >= CREDITO_X_MIN:
                credito_parts.append((x, word))
        return _importo_cents_da_token(debito_parts), _importo_cents_da_token(credito_parts)

    # ============================================
    # ESTRAZIONE PER PAGINA
    # ============================================

    for page_num, page in enumerate(doc):
        page_number = page_num + 1
        page_text = page.get_text()
        words = page.get_text('words')
        model_match = re.search(r"MOD\s*NUM\s*:\s*(\d+)", page_text, re.IGNORECASE)
        model_number = int(model_match.group(1)) if model_match else None
        page_models[page_number] = model_number
        result["diagnostica_pagine"].append({
            "pagina": page_number,
            "stato": "bianca" if not words and not page_text.strip() else "elaborata",
            "numero_modello": model_number,
            "caratteri_testo": len(page_text.strip()),
            "parole": len(words),
        })
        saldo_coordinate = _saldo_da_coordinate(page)
        if saldo_coordinate is not None:
            result["dati_generali"]["saldo_delega"] = saldo_coordinate
            page_balances[page_number] = saldo_coordinate

        # Raggruppa per riga (tolleranza 8 pixel)
        rows = {}
        for w in words:
            x0, y0, x1, y1, word, block, line, word_n = w
            y_key = round(y0 / 8) * 8
            if y_key not in rows:
                rows[y_key] = []
            rows[y_key].append({'x': round(x0), 'y': round(y0), 'word': word.strip()})

        # Processa ogni riga
        for y_key in sorted(rows.keys()):
            row = sorted(rows[y_key], key=lambda r: r['x'])
            row_text = ' '.join([r['word'] for r in row])
            if "EURO" in row_text and "+" in row_text:
                _unused_cents, saldo_documento_cents = extract_importo_cents(row)
                if saldo_documento_cents or "0,00" in row_text:
                    result["dati_generali"]["saldo_delega"] = saldo_documento_cents / 100
                    result["dati_generali"]["saldo_delega_cents"] = saldo_documento_cents

            # ============================================
            # SEZIONE ERARIO - Codici 1xxx, 2xxx, 6xxx, 8xxx
            # Pattern: codice [rateazione] anno debito/credito
            # IMPORTANTE:
            # - I codici 3xxx (IRAP) vanno SEMPRE nella sezione REGIONI
            # - Non processare se la riga ha un codice regione
            # ============================================

            # Lista codici che vanno SEMPRE nella sezione REGIONI (IRAP)
            CODICI_SOLO_REGIONI = {'3800', '3801', '3802', '3803', '3805', '3812', '3813',
                                  '3858', '3881', '3882', '3883', '4070', '1868',
                                  '1993', '8907'}  # Ravvedimento IRAP

            # Check se la riga inizia con codice regione (0 X o 0X o XX dove XX è 01-21)
            first_words = [r['word'] for r in row[:4]] if len(row) >= 4 else []
            is_riga_regioni = False

            if len(first_words) >= 2:
                # Pattern "0 X" dove X è cifra (0 5 -> 05)
                if first_words[0] == '0' and re.match(r'^\d$', first_words[1]):
                    is_riga_regioni = True
                # Pattern "0X" codice regione diretto (01-09)
                elif re.match(r'^0[1-9]$', first_words[0]):
                    is_riga_regioni = True
                # Pattern "XX" codice regione 10-21
                elif re.match(r'^(1[0-9]|2[0-1])$', first_words[0]):
                    is_riga_regioni = True

            # Processa ERARIO solo se NON è una riga regioni
            if not is_riga_regioni:
                for i, item in enumerate(row):
                    word = item['word']

                    # Codici ERARIO: 1xxx, 2xxx, 6xxx, 8xxx
                    # ESCLUDI i codici 3xxx (IRAP) che vanno in REGIONI
                    # ESCLUDI anche codici IRAP specifici (1993, 8907) senza codice regione
                    if re.match(r'^(1\d{3}|2\d{3}|6\d{3}|7\d{3}|8\d{3}|9\d{3})$', word):
                        codice = word

                        # Se è un codice IRAP (1993, 8907), salta - andrà in REGIONI
                        if codice in CODICI_SOLO_REGIONI:
                            continue

                        rateazione = ""
                        anno = ""

                        # Cerca rateazione e anno
                        for j in range(i+1, min(i+5, len(row))):
                            nw = row[j]['word']
                            if nw in [',', '+/–']:
                                continue
                            if re.match(r'^\d{4}$', nw) and not re.match(r'^20\d{2}$', nw) and not rateazione:
                                rateazione = nw
                            elif re.match(r'^20\d{2}$', nw) and not anno:
                                anno = nw
                        rateazione, anno = _rateazione_e_anno(
                            [entry["word"] for entry in row[i + 1:min(i + 8, len(row))]]
                        )

                        debito_cents, credito_cents = extract_importo_cents(row)
                        debito, credito = debito_cents / 100, credito_cents / 100

                        if anno and (debito > 0 or credito > 0):
                            mese = rateazione[2:4] if len(rateazione) == 4 else "00"
                            key = f"E_{codice}_{anno}_{rateazione}_{debito}_{credito}"

                            if key not in tributi_visti:
                                tributi_visti.add(key)
                                result["sezione_erario"].append({
                                    "codice_tributo": codice,
                                    "rateazione": rateazione,
                                    "periodo_riferimento": parse_periodo(mese, anno),
                                    "anno": anno,
                                    "mese": mese,
                                    "importo_debito": debito,
                                    "importo_credito": credito,
                                    "importo_debito_cents": debito_cents,
                                    "importo_credito_cents": credito_cents,
                                    "pagina": page_num + 1,
                                    "riga_y": y_key,
                                    "testo_sorgente": row_text,
                                    "descrizione": get_descrizione_tributo(codice)
                                })

                                if codice in CODICI_RAVVEDIMENTO:
                                    result["has_ravvedimento"] = True
                                    result["codici_ravvedimento"].append(codice)
                        break

            # ============================================
            # SEZIONE INPS - Pattern: 5100 causale matricola mese anno debito
            # ============================================
            if '5100' in row_text and any(c in row_text for c in ['CXX', 'DM10', 'RC01']):
                for i, item in enumerate(row):
                    word = item['word']

                    if word in ['CXX', 'DM10', 'RC01', 'C10', 'CF10']:
                        causale = word
                        matricola = ""
                        mese = ""
                        anno = ""

                        # Cerca matricola, mese, anno
                        for j in range(i+1, len(row)):
                            nw = row[j]['word']
                            if nw in [',', '+/–']:
                                continue
                            if re.match(r'^[A-Z0-9]{8,15}$', nw) and not matricola:
                                matricola = nw
                            elif re.match(r'^(0[1-9]|1[0-2])$', nw) and not mese:
                                mese = nw
                            elif re.match(r'^20\d{2}$', nw) and not anno:
                                anno = nw

                        # Estrai importo (per INPS solo debito, X > 340)
                        importo_cents = 0
                        numero_parts = []
                        for r in row:
                            if r['x'] > 340 and re.match(r'^[\d.]+$', r['word']):
                                numero_parts.append((r['x'], r['word']))

                        if len(numero_parts) >= 2:
                            numero_parts.sort()
                            importo_cents = _importo_cents_da_token(numero_parts)

                        if causale and matricola and anno and importo_cents > 0:
                            key = f"I_{causale}_{matricola}_{anno}_{mese}"
                            if key not in tributi_visti:
                                tributi_visti.add(key)
                                result["sezione_inps"].append({
                                    "codice_sede": "5100",
                                    "causale": causale,
                                    "matricola": matricola,
                                    "periodo_riferimento": f"{mese}/{anno}",
                                    "mese": mese,
                                    "anno": anno,
                                    "importo_debito": importo_cents / 100,
                                    "importo_credito": 0.0,
                                    "importo_debito_cents": importo_cents,
                                    "importo_credito_cents": 0,
                                    "pagina": page_num + 1,
                                    "riga_y": y_key,
                                    "testo_sorgente": row_text,
                                    "descrizione": get_descrizione_causale_inps(causale)
                                })
                        break

            # ============================================
            # SEZIONE INAIL - Pattern: cod_sede cod_ditta cc num_rif causale importo
            # Es: "33400 13882560 91 902025 P 365 11"
            # ============================================
            # Riconosce righe INAIL: iniziano con codice sede 5 cifre seguito da codice ditta
            is_inail_row = False
            cod_sede_inail = ""
            cod_ditta = ""

            if len(row) >= 5:
                first_words = [r['word'] for r in row[:6]]
                # Pattern: codice sede (5 cifre), codice ditta (8 cifre)
                if (len(first_words) >= 2 and
                    re.match(r'^\d{5}$', first_words[0]) and
                    re.match(r'^\d{7,10}$', first_words[1])):
                    cod_sede_inail = first_words[0]
                    cod_ditta = first_words[1]
                    is_inail_row = True

            if is_inail_row:
                cc = ""
                num_riferimento = ""
                causale_inail = ""

                # Cerca cc, numero riferimento, causale
                for i, item in enumerate(row):
                    word = item['word']
                    if word in [',', '+/–']:
                        continue

                    if re.match(r'^\d{2}$', word) and not cc and i > 1:
                        cc = word
                    elif re.match(r'^\d{6}$', word) and not num_riferimento:
                        num_riferimento = word
                    elif re.match(r'^[A-Z]$', word) and not causale_inail:
                        causale_inail = word

                importo_inail_cents, credito_inail_cents = extract_importo_cents(row)
                importo_inail = importo_inail_cents / 100
                credito_inail = credito_inail_cents / 100

                if cod_sede_inail and cod_ditta and importo_inail > 0:
                    key = f"INAIL_{cod_sede_inail}_{cod_ditta}_{num_riferimento}"
                    if key not in tributi_visti:
                        tributi_visti.add(key)
                        result["sezione_inail"].append({
                            "codice_sede": cod_sede_inail,
                            "codice_ditta": cod_ditta,
                            "cc": cc,
                            "numero_riferimento": num_riferimento,
                            "causale": causale_inail,
                            "importo_debito": importo_inail,
                            "importo_credito": credito_inail,
                            "importo_debito_cents": importo_inail_cents,
                            "importo_credito_cents": credito_inail_cents,
                            "pagina": page_num + 1,
                            "riga_y": y_key,
                            "testo_sorgente": row_text,
                            "descrizione": f"Premio INAIL - Causale {causale_inail}"
                        })

            # ============================================
            # SEZIONE REGIONI - Pattern: cod_regione codice rateazione anno debito/credito
            # Codici 3xxx = IRAP, addizionali regionali
            # Codici 8xxx = Sanzioni IRAP (quando hanno codice regione)
            # Codici 1xxx = Interessi ravvedimento (quando hanno codice regione)
            # Riconosce righe con "0 X" dove X è una cifra (es: "0 5" = regione 05)
            # ============================================

            # Lista codici IRAP che vanno SEMPRE in REGIONI
            CODICI_IRAP = {'1868', '3800', '3801', '3802', '3803', '3805', '3812', '3813',
                          '3858', '3881', '3882', '3883', '4070', '1993', '8907'}

            cod_regione = _codice_regione_da_riga(row)
            is_regioni_row = bool(cod_regione)
            if len(row) >= 3 and not cod_regione:
                first_words = [r['word'] for r in row[:4]]
                # Pattern "0 X" dove X è una cifra = codice regione
                if len(first_words) >= 2 and first_words[0] == '0' and re.match(r'^\d$', first_words[1]):
                    cod_regione = first_words[0] + first_words[1]
                    is_regioni_row = True
                # Pattern "XX" come codice regione diretto (01-21)
                elif len(first_words) >= 1 and re.match(r'^(0[1-9]|1\d|2[0-1])$', first_words[0]):
                    cod_regione = first_words[0]
                    is_regioni_row = True

            # Processa righe con codice regione esplicito
            if is_regioni_row:
                for i, item in enumerate(row):
                    word = item['word']

                    # Codici regionali:
                    # - 3xxx (IRAP, addizionale IRPEF)
                    # - 8xxx (sanzioni IRAP - es. 8907)
                    # - 1xxx (interessi ravvedimento - es. 1993)
                    if re.match(r'^(3\d{3}|8\d{3}|1\d{3})$', word):
                        codice = word
                        rateazione = ""
                        anno = ""

                        for j in range(i+1, min(i+5, len(row))):
                            nw = row[j]['word']
                            if nw in [',', '+/–']:
                                continue
                            if re.match(r'^0[0-9]{3}$', nw) and not rateazione:
                                rateazione = nw
                            elif re.match(r'^20\d{2}$', nw) and not anno:
                                anno = nw
                        rateazione, anno = _rateazione_e_anno(
                            [entry["word"] for entry in row[i + 1:min(i + 8, len(row))]]
                        )

                        debito_cents, credito_cents = extract_importo_cents(row)
                        debito, credito = debito_cents / 100, credito_cents / 100

                        if anno and (debito > 0 or credito > 0):
                            mese = rateazione[2:4] if len(rateazione) == 4 else "00"
                            key = f"R_{codice}_{cod_regione}_{anno}_{rateazione}_{debito}_{credito}"

                            if key not in tributi_visti:
                                tributi_visti.add(key)
                                result["sezione_regioni"].append({
                                    "codice_tributo": codice,
                                    "codice_regione": cod_regione,
                                    "rateazione": rateazione,
                                    "periodo_riferimento": parse_periodo(mese, anno),
                                    "anno": anno,
                                    "mese": mese,
                                    "importo_debito": debito,
                                    "importo_credito": credito,
                                    "importo_debito_cents": debito_cents,
                                    "importo_credito_cents": credito_cents,
                                    "pagina": page_num + 1,
                                    "riga_y": y_key,
                                    "testo_sorgente": row_text,
                                    "descrizione": get_descrizione_tributo_regioni(codice)
                                })
                        break

            # ============================================
            # FALLBACK REGIONI: Cattura codici IRAP senza codice regione esplicito
            # Alcuni PDF F24 non mostrano il codice regione nella stessa riga
            # ============================================
            if not is_regioni_row:
                for i, item in enumerate(row):
                    word = item['word']

                    # Codici IRAP che vanno SEMPRE in REGIONI
                    if word in CODICI_IRAP:
                        codice = word
                        rateazione = ""
                        anno = ""

                        for j in range(i+1, min(i+5, len(row))):
                            nw = row[j]['word']
                            if nw in [',', '+/–']:
                                continue
                            if re.match(r'^0[0-9]{3}$', nw) and not rateazione:
                                rateazione = nw
                            elif re.match(r'^20\d{2}$', nw) and not anno:
                                anno = nw
                        rateazione, anno = _rateazione_e_anno(
                            [entry["word"] for entry in row[i + 1:min(i + 8, len(row))]]
                        )

                        debito_cents, credito_cents = extract_importo_cents(row)
                        debito, credito = debito_cents / 100, credito_cents / 100

                        if anno and (debito > 0 or credito > 0):
                            mese = rateazione[2:4] if len(rateazione) == 4 else "00"
                            # Usa "00" come codice regione placeholder
                            key = f"R_{codice}_00_{anno}_{rateazione}_{debito}_{credito}"

                            if key not in tributi_visti:
                                tributi_visti.add(key)
                                result["sezione_regioni"].append({
                                    "codice_tributo": codice,
                                    "codice_regione": "",  # Non presente nel PDF
                                    "rateazione": rateazione,
                                    "periodo_riferimento": parse_periodo(mese, anno),
                                    "anno": anno,
                                    "mese": mese,
                                    "importo_debito": debito,
                                    "importo_credito": credito,
                                    "importo_debito_cents": debito_cents,
                                    "importo_credito_cents": credito_cents,
                                    "pagina": page_num + 1,
                                    "riga_y": y_key,
                                    "testo_sorgente": row_text,
                                    "descrizione": get_descrizione_tributo_regioni(codice)
                                })
                        break

            # ============================================
            # SEZIONE TRIBUTI LOCALI - Pattern: cod_comune/cod_ente codice rateazione anno debito/credito
            # Riconosce righe con lettere all'inizio:
            # - "B 9 9 0" o "F 8 3 9" = codice comune (4 caratteri)
            # - "N A" = codice ente (es. NA = Napoli per Camera di Commercio)
            # Include codici: 37xx, 38xx (Camera Commercio), 391x (IMU)
            # ============================================
            is_locali_row = False
            cod_comune = ""
            cod_ente = ""

            if len(row) >= 4:
                first_words = [r['word'] for r in row[:5]]

                # Pattern 1: "B 9 9 0" o "F 8 3 9" = codice comune (4 caratteri separati)
                if (len(first_words) >= 4 and
                    re.match(r'^[A-Z]$', first_words[0]) and
                    all(re.match(r'^\d$', w) for w in first_words[1:4])):
                    cod_comune = ''.join(first_words[:4])
                    is_locali_row = True

                # Pattern 2: "N A" = codice ente (2 lettere separate, es. NA = Napoli)
                elif (len(first_words) >= 2 and
                      re.match(r'^[A-Z]$', first_words[0]) and
                      re.match(r'^[A-Z]$', first_words[1])):
                    cod_ente = first_words[0] + first_words[1]
                    is_locali_row = True

                # Pattern 3: "NA" = codice ente diretto (2 lettere insieme)
                elif (len(first_words) >= 1 and
                      re.match(r'^[A-Z]{2}$', first_words[0])):
                    cod_ente = first_words[0]
                    is_locali_row = True

            if is_locali_row:
                for i, item in enumerate(row):
                    word = item['word']

                    # Codici tributi locali: 37xx, 38xx (Camera Commercio), 391x (IMU), 39xx (altri)
                    if re.match(r'^(37\d{2}|38\d{2}|39\d{2})$', word):
                        codice = word
                        rateazione = ""
                        anno = ""

                        for j in range(i+1, min(i+5, len(row))):
                            nw = row[j]['word']
                            if nw in [',', '+/–']:
                                continue
                            if re.match(r'^00\d{2}$', nw) and not rateazione:
                                rateazione = nw
                            elif re.match(r'^20\d{2}$', nw) and not anno:
                                anno = nw
                        rateazione, anno = _rateazione_e_anno(
                            [entry["word"] for entry in row[i + 1:min(i + 8, len(row))]]
                        )

                        debito_cents, credito_cents = extract_importo_cents(row)
                        debito, credito = debito_cents / 100, credito_cents / 100

                        if anno and (debito > 0 or credito > 0):
                            mese = rateazione[2:4] if len(rateazione) == 4 else "00"
                            ente_ref = cod_comune or cod_ente or ""
                            key = f"L_{codice}_{ente_ref}_{anno}_{rateazione}_{debito}_{credito}"

                            if key not in tributi_visti:
                                tributi_visti.add(key)
                                result["sezione_tributi_locali"].append({
                                    "codice_tributo": codice,
                                    "codice_comune": cod_comune,
                                    "codice_ente": cod_ente,
                                    "rateazione": rateazione,
                                    "periodo_riferimento": parse_periodo(mese, anno),
                                    "anno": anno,
                                    "mese": mese,
                                    "importo_debito": debito,
                                    "importo_credito": credito,
                                    "importo_debito_cents": debito_cents,
                                    "importo_credito_cents": credito_cents,
                                    "pagina": page_num + 1,
                                    "riga_y": y_key,
                                    "testo_sorgente": row_text,
                                    "descrizione": get_descrizione_tributo_locale(codice)
                                })
                        break

    # Provenienza completa e importi canonici: ogni riga mantiene il testo
    # originale, la pagina e il rettangolo delle parole che l'hanno generata.
    for section_name in (
        "sezione_erario", "sezione_inps", "sezione_regioni",
        "sezione_tributi_locali", "sezione_inail",
    ):
        for row in result[section_name]:
            debit_cents = row.get("importo_debito_cents")
            credit_cents = row.get("importo_credito_cents")
            if debit_cents is None:
                debit_cents = int(Decimal(str(row.get("importo_debito") or 0)) * 100)
            if credit_cents is None:
                credit_cents = int(Decimal(str(row.get("importo_credito") or 0)) * 100)
            row["importo_debito_cents"] = int(debit_cents)
            row["importo_credito_cents"] = int(credit_cents)
            row["importo_debito"] = row["importo_debito_cents"] / 100
            row["importo_credito"] = row["importo_credito_cents"] / 100
            row["net_cents"] = row["importo_debito_cents"] - row["importo_credito_cents"]
            row["raw_text"] = row.get("testo_sorgente") or ""
            row["parser_version"] = "f24-coordinate-v4"
            page_number = int(row.get("pagina") or 1)
            page = doc[page_number - 1]
            y = float(row.get("riga_y") or 0)
            words_on_row = [
                word for word in page.get_text("words")
                if abs(float(word[1]) - y) <= 9
            ]
            if words_on_row:
                bbox = [
                    round(min(float(word[0]) for word in words_on_row), 2),
                    round(min(float(word[1]) for word in words_on_row), 2),
                    round(max(float(word[2]) for word in words_on_row), 2),
                    round(max(float(word[3]) for word in words_on_row), 2),
                ]
                row["bbox"] = bbox
                row["field_evidence"] = {
                    "page": page_number, "x0": bbox[0], "y0": bbox[1],
                    "x1": bbox[2], "y1": bbox[3],
                    "raw_text": row["raw_text"],
                    "normalized_value": {
                        "debit_cents": row["importo_debito_cents"],
                        "credit_cents": row["importo_credito_cents"],
                    },
                    "parser_version": row["parser_version"],
                    "confidence": 1.0,
                }
            if section_name == "sezione_tributi_locali" and str(row.get("codice_tributo") or "").startswith("39"):
                source_text = str(row.get("raw_text") or "")
                row["flag_x"] = bool(re.search(r"\bX\b", source_text, re.IGNORECASE))
                row["ravvedimento"] = row["flag_x"]
                row["has_ravvedimento"] = row["flag_x"]
                row["immobili_variati"] = row["flag_x"]
                row["acconto"] = False
                row["saldo"] = True
                number_match = re.search(r"\b(\d{1,2})\s+" + re.escape(str(row.get("codice_tributo"))), source_text)
                row["numero_immobili"] = int(number_match.group(1)) if number_match else None
                row["detrazione_cents"] = 0

    # Il nome semantico IMU e' un alias della sezione tributi locali. Evita
    # copie divergenti: il ledger canonico usa una sola riga sorgente.
    result["sezione_imu"] = result["sezione_tributi_locali"]
    if any(row.get("has_ravvedimento") for row in result["sezione_imu"]):
        result["has_ravvedimento"] = True

    doc.close()

    sections = (
        "sezione_erario", "sezione_inps", "sezione_regioni",
        "sezione_tributi_locali", "sezione_inail",
    )
    for section_name in sections:
        for row in result[section_name]:
            row["numero_modello"] = page_models.get(int(row.get("pagina") or 1))

    # Una delega PDF puo' contenere piu' modelli separati da pagine bianche.
    # La quadratura va verificata per modello e poi sull'intero documento:
    # confrontare tutte le righe con il solo saldo dell'ultima pagina produce
    # un falso non-quadrato sul campione IMU + ritenuta.
    model_keys = []
    for page_number, model_number in page_models.items():
        if model_number is not None and model_number not in model_keys:
            model_keys.append(model_number)
    if not model_keys and any(item["stato"] == "elaborata" for item in result["diagnostica_pagine"]):
        model_keys = [1]

    model_summaries = []
    for model_number in model_keys:
        model_pages = [
            page_number for page_number, value in page_models.items()
            if value == model_number or (len(model_keys) == 1 and value is None)
        ]
        model_rows = [
            row for section_name in sections for row in result[section_name]
            if int(row.get("pagina") or 1) in model_pages
        ]
        debit_cents = sum(int(row.get("importo_debito_cents") or 0) for row in model_rows)
        credit_cents = sum(int(row.get("importo_credito_cents") or 0) for row in model_rows)
        debits = debit_cents / 100
        credits = credit_cents / 100
        balance = next((page_balances[page] for page in model_pages if page in page_balances), None)
        balance_cents = None if balance is None else int(Decimal(str(balance)) * 100)
        difference_cents = None if balance_cents is None else debit_cents - credit_cents - balance_cents
        model_summaries.append({
            "numero_modello": model_number,
            "pagine": model_pages,
            "saldo_delega": balance,
            "saldo_delega_cents": balance_cents,
            "totale_debito": debits,
            "totale_credito": credits,
            "totale_debito_cents": debit_cents,
            "totale_credito_cents": credit_cents,
            "differenza_saldo": None if difference_cents is None else difference_cents / 100,
            "differenza_saldo_cents": difference_cents,
            "saldo_quadrato": difference_cents == 0,
        })
    result["modelli"] = model_summaries
    result["dati_generali"]["numero_modelli"] = len(model_summaries)
    if model_summaries and all(item["saldo_delega"] is not None for item in model_summaries):
        saldo_delega_cents = sum(
            int(item.get("saldo_delega_cents") or 0) for item in model_summaries
        )
        result["dati_generali"]["saldo_delega"] = saldo_delega_cents / 100
        result["dati_generali"]["saldo_delega_cents"] = saldo_delega_cents

    # Il ravvedimento appartiene alla delega e puo' essere rappresentato in
    # qualunque sezione. Derivarlo da tutte le righe evita di perdere, per
    # esempio, interessi 1993 e sanzioni 8907 nella sezione Regioni.
    codici_presenti = {
        str(item.get("codice_tributo") or "")
        for nome_sezione in (
            "sezione_erario", "sezione_regioni", "sezione_tributi_locali",
        )
        for item in result[nome_sezione]
    }
    codici_ravvedimento = sorted(codici_presenti.intersection(CODICI_RAVVEDIMENTO))
    result["codici_ravvedimento"] = codici_ravvedimento
    result["has_ravvedimento"] = bool(codici_ravvedimento)

    # ============================================
    # CALCOLO TOTALI
    # ============================================

    totale_debito_cents = 0
    totale_credito_cents = 0

    for sezione in [result["sezione_erario"], result["sezione_inps"],
                    result["sezione_regioni"], result["sezione_tributi_locali"],
                    result["sezione_inail"]]:
        for item in sezione:
            totale_debito_cents += int(item.get("importo_debito_cents") or 0)
            totale_credito_cents += int(item.get("importo_credito_cents") or 0)

    saldo_netto_cents = totale_debito_cents - totale_credito_cents
    totale_debito = totale_debito_cents / 100
    totale_credito = totale_credito_cents / 100
    saldo_netto = saldo_netto_cents / 100

    saldo_documento = result["dati_generali"].get("saldo_delega")
    result["totali"] = {
        "totale_debito": round(totale_debito, 2),
        "totale_credito": round(totale_credito, 2),
        "saldo_netto": round(saldo_netto, 2),
        "saldo_finale": round(saldo_netto, 2),
        "saldo_delega": saldo_documento,
        "totale_debito_cents": totale_debito_cents,
        "totale_credito_cents": totale_credito_cents,
        "saldo_netto_cents": saldo_netto_cents,
        "saldo_finale_cents": saldo_netto_cents,
        "saldo_delega_cents": None if saldo_documento is None else int(Decimal(str(saldo_documento)) * 100),
    }
    difference_cents = None if saldo_documento is None else (
        saldo_netto_cents - int(Decimal(str(saldo_documento)) * 100)
    )
    section_quadratures = {}
    for section_name in (
        "sezione_erario", "sezione_inps", "sezione_regioni",
        "sezione_tributi_locali", "sezione_inail",
    ):
        section_rows = result[section_name]
        debit_cents = sum(int(row.get("importo_debito_cents") or 0) for row in section_rows)
        credit_cents = sum(int(row.get("importo_credito_cents") or 0) for row in section_rows)
        section_quadratures[section_name] = {
            "debit_cents": debit_cents,
            "credit_cents": credit_cents,
            "net_cents": debit_cents - credit_cents,
            # I PDF commercialista non stampano un totale per ogni sezione:
            # il dato resta esplicito e non viene inventato.
            "printed_available": False,
            "printed_debit_cents": None,
            "printed_credit_cents": None,
            # Il totale delle righe e' calcolato, ma il PDF non stampa un
            # subtotale confrontabile per questa sezione. Non e' quindi una
            # quadratura "verificata": lo stato resta esplicito.
            "stato": "NON_VERIFICABILE",
            "quadrata": None,
        }
    section_states = {value["stato"] for value in section_quadratures.values()}
    result["validazione"] = {
        "righe_estratte": sum(len(result[name]) for name in (
            "sezione_erario", "sezione_inps", "sezione_regioni",
            "sezione_tributi_locali", "sezione_inail",
        )),
        "saldo_quadrato": difference_cents == 0,
        "differenza_saldo_cents": difference_cents,
        "differenza_saldo": None if difference_cents is None else difference_cents / 100,
        "modelli_quadrati": bool(model_summaries) and all(
            item["saldo_quadrato"] for item in model_summaries
        ),
        "pagine_bianche": [
            item["pagina"] for item in result["diagnostica_pagine"] if item["stato"] == "bianca"
        ],
        "quadrature_sezioni": section_quadratures,
        # Compatibilita' con i consumer legacy: True significa che non c'e'
        # un errore aritmetico sulle righe. La verifica contro i totali
        # stampati e' esposta separatamente in `sezioni_stato`.
        "sezioni_quadrate": "ERRORE" not in section_states,
        "sezioni_verificate": all(value["stato"] == "VERIFICATA" for value in section_quadratures.values()),
        "sezioni_stato": "ERRORE" if "ERRORE" in section_states else (
            "NON_VERIFICABILE" if "NON_VERIFICABILE" in section_states else "VERIFICATA"
        ),
        "parser_version": "f24-coordinate-v4",
    }

    return result


def get_descrizione_tributo(codice: str) -> str:
    """
    Descrizione del codice tributo Erario.

    Delega al registro unico versionato in `app.services.codici_tributo_f24`
    (CLAUDE.md: un solo registro codice tributo -> descrizione, mai due tabelle
    indipendenti che possano divergere). Tutti i codici che questa funzione
    copriva sono stati migrati in quel registro.
    """
    from app.services.codici_tributo_f24 import get_descrizione_tributo as _get_descrizione_tributo_canonica

    return _get_descrizione_tributo_canonica(codice)


def get_descrizione_causale_inps(causale: str) -> str:
    """Descrizione causali INPS."""
    descrizioni = {
        "DM10": "Contributi previdenziali dipendenti",
        "CXX": "Contributi gestione separata",
        "RC01": "Contributi artigiani/commercianti",
        "C10": "Contributi cassa edile",
        "CF10": "Contributi fondo pensione",
    }
    return descrizioni.get(causale, f"Contributo {causale}")


def get_descrizione_tributo_regioni(codice: str) -> str:
    """
    Descrizione codici tributo regionali (sezione REGIONI F24).
    Include IRAP, addizionali regionali e relativi ravvedimenti/sanzioni.
    Fonte: https://www1.agenziaentrate.gov.it/servizi/codici/ricerca/
    """
    descrizioni = {
        # ============================================
        # IRAP - Autoliquidazione
        # ============================================
        "1868": "IRAP riallineamento principi contabili (D.Lgs. 192/2024)",
        "3800": "IRAP saldo",
        "3805": "Interessi pagamento dilazionato tributi regionali",
        "3812": "IRAP acconto prima rata",
        "3813": "IRAP acconto seconda rata o unica soluzione",
        "3858": "IRAP versamento mensile (art.10-bis D.Lgs. 446/97)",
        "3881": "Maggior acconto I rata IRAP (L. 207/2024)",
        "3882": "Maggior acconto II rata IRAP (L. 207/2024)",
        "3883": "IRAP compensazione credito (L. 190/2014)",
        "4070": "CPB maggiorazione acconto IRAP (D.Lgs. 13/2024)",

        # ============================================
        # IRAP - Ravvedimento operoso
        # ============================================
        "1993": "Interessi ravvedimento IRAP (art.13 D.Lgs. 472/97)",
        "8907": "Sanzione pecuniaria IRAP",

        # ============================================
        # IRAP - Accertamento e contenzioso
        # ============================================
        "1987": "Ravvedimento importi rateizzati IRAP - interessi",
        "5063": "Recupero aiuto Stato esonero IRAP saldo - imposta/interessi",
        "5064": "Recupero aiuto Stato esonero IRAP saldo - sanzione",
        "5065": "Recupero aiuto Stato esonero IRAP acconto - imposta/interessi",
        "5066": "Recupero aiuto Stato esonero IRAP acconto - sanzione",
        "7452": "IRAP recupero credito compensazione - imposta/interessi",
        "7453": "IRAP recupero credito compensazione - sanzione",
        "9400": "Spese di notifica atti impositivi",
        "9415": "IRAP accertamento con adesione - imposta/interessi",
        "9416": "IRAP accertamento con adesione - sanzione",
        "9424": "Sanzione anagrafe tributaria codice fiscale",
        "9466": "IRAP omessa impugnazione - imposta/interessi",
        "9467": "IRAP omessa impugnazione - sanzione",
        "9478": "Sanzione decadenza rateazione IRAP (art.29 DL 78/2010)",
        "9512": "IRAP conciliazione giudiziale - imposta/interessi",
        "9513": "IRAP conciliazione giudiziale - sanzione",
        "9607": "Sanzione pecuniaria IRAP definizione sanzioni",
        "9695": "Sanzione componenti reddituali negativi non scambiati",
        "9908": "IRAP adesione verbale constatazione - imposta/interessi",
        "9909": "IRAP adesione verbale constatazione - sanzione",
        "9920": "IRAP adesione invito comparire - imposta/interessi",
        "9921": "IRAP adesione invito comparire - sanzione",
        "9934": "IRAP contenzioso art.29 DL 78/2010 - imposta",
        "9935": "IRAP contenzioso art.29 DL 78/2010 - interessi",
        "9949": "Ravvedimento importi rateizzati IRAP - sanzione",
        "9955": "IRAP reclamo/mediazione art.17-bis - imposta/interessi",
        "9956": "IRAP reclamo/mediazione - sanzioni",
        "9971": "Sanzioni IRAP contenzioso art.29 DL 78/2010",
        "9988": "IRAP definizione agevolata PVC - imposta/interessi",
        "9990": "IRAP definizione agevolata PVC - sanzione",

        # ============================================
        # Addizionale regionale IRPEF
        # ============================================
        "3801": "Addizionale regionale IRPEF - autotassazione",
        "3802": "Addizionale regionale IRPEF - sostituto d'imposta",
        "3803": "Addizionale regionale IRPEF - autotassazione acconto",
        "8902": "Interessi ravvedimento addizionale regionale IRPEF",
        "8903": "Sanzione pecuniaria addizionale regionale IRPEF",

        # ============================================
        # Sanatorie e definizioni regionali
        # ============================================
        "LP33": "IRAP/Add.reg. IRPEF definizione controversie (L. 130/2022) - imposta",
        "LP34": "IRAP/Add.reg. IRPEF definizione controversie (L. 130/2022) - sanzioni",
        "PF11": "IRAP definizione agevolata PVC (DL 119/2018)",
        "PF33": "IRAP/Add.reg. IRPEF definizione controversie (DL 119/2018) - imposta",
        "PF34": "IRAP/Add.reg. IRPEF definizione controversie (DL 119/2018) - sanzioni",
        "TF23": "IRAP/Add.reg. IRPEF definizione controversie (L. 197/2022) - imposta",
        "TF24": "IRAP/Add.reg. IRPEF definizione controversie (L. 197/2022) - sanzioni",
        "TF42": "IRAP/Add.reg. IRPEF regolarizzazione pagamenti (L. 197/2022)",
        "TF50": "IRAP ravvedimento speciale (L. 197/2022) - sanzioni",
        "8124": "IRAP/Add.reg. IRPEF definizione controversie (DL 50/2017) - imposta",
        "8125": "IRAP/Add.reg. IRPEF definizione controversie (DL 50/2017) - sanzioni",
    }
    return descrizioni.get(codice, f"Tributo regionale {codice}")


def get_descrizione_tributo_locale(codice: str) -> str:
    """
    Descrizione codici tributo locali (sezione IMU/LOCALI F24).
    Include IMU, TASI, TARI, addizionali comunali, ecc.
    Fonte: https://www1.agenziaentrate.gov.it/servizi/codici/ricerca/
    """
    descrizioni = {
        # ============================================
        # Addizionale comunale IRPEF
        # ============================================
        "1671": "Addizionale comunale IRPEF - sostituto d'imposta",
        "3797": "Addizionale comunale IRPEF - acconto autotassazione",
        "3843": "Addizionale comunale IRPEF - acconto autotassazione",
        "3844": "Addizionale comunale IRPEF - saldo autotassazione",
        "3847": "Addizionale comunale IRPEF trattenuta sostituto - acconto",
        "3848": "Addizionale comunale IRPEF trattenuta sostituto - saldo",

        # ============================================
        # IMU - Imposta Municipale Unica
        # ============================================
        "3912": "IMU abitazione principale e pertinenze",
        "3913": "IMU fabbricati rurali strumentali - comune",
        "3914": "IMU terreni - comune",
        "3915": "IMU terreni - Stato",
        "3916": "IMU aree fabbricabili - comune",
        "3917": "IMU aree fabbricabili - Stato",
        "3918": "IMU altri fabbricati - comune",
        "3919": "IMU interessi accertamento - comune",
        "3920": "IMU sanzioni accertamento - comune",
        "3923": "IMU imposta - comune",
        "3924": "IMU imposta - Stato",
        "3925": "IMU fabbricati gruppo D - Stato",
        "3926": "ISCOP imposta di scopo",
        "3927": "ISCOP interessi",
        "3928": "ISCOP sanzioni",
        "3930": "IMU fabbricati gruppo D - comune (incremento)",

        # ============================================
        # TOSAP/COSAP
        # ============================================
        "3931": "TOSAP/COSAP occupazione permanente",
        "3932": "TOSAP/COSAP occupazione temporanea",
        "3933": "TOSAP/COSAP interessi",
        "3934": "TOSAP/COSAP sanzioni",

        # ============================================
        # ICI (vecchia imposta - pre IMU)
        # ============================================
        "3901": "ICI abitazione principale",
        "3902": "ICI terreni agricoli",
        "3903": "ICI aree fabbricabili",
        "3904": "ICI altri fabbricati",
        "3906": "ICI interessi",
        "3907": "ICI sanzioni",

        # ============================================
        # TARES
        # ============================================
        "3944": "TARES imposta",
        "3945": "TARES interessi",
        "3946": "TARES sanzioni",
        "3950": "TARI tariffa rifiuti",
        "3951": "TARI interessi",
        "3952": "TARI sanzioni",
        "3955": "TARES maggiorazione",
        "3956": "TARES maggiorazione interessi",
        "3957": "TARES maggiorazione sanzioni",

        # ============================================
        # TASI
        # ============================================
        "3958": "TASI abitazione principale e pertinenze",
        "3959": "TASI fabbricati rurali strumentali",
        "3960": "TASI aree fabbricabili",
        "3961": "TASI altri fabbricati",
        "3962": "TASI interessi accertamento",
        "3963": "TASI sanzioni accertamento",

        # ============================================
        # ICP/CIMP (Pubblicità)
        # ============================================
        "3964": "ICP/CIMP imposta pubblicità",
        "3965": "ICP/CIMP interessi",
        "3966": "ICP/CIMP sanzioni",

        # ============================================
        # Camera di Commercio
        # ============================================
        "3850": "Diritto camerale annuale",
        "3851": "Diritto camerale interessi",
        "3852": "Diritto camerale sanzioni",
    }
    return descrizioni.get(codice, f"Tributo locale {codice}")


def confronta_codici_tributo(f24_commercialista: Dict, quietanza: Dict) -> Dict[str, Any]:
    """
    Confronta i codici tributo tra F24 commercialista e quietanza.

    Logica di riconciliazione:
    1. Estrae i codici tributo (senza periodo) da entrambi i documenti
    2. Confronta codice per codice
    3. Se i codici base sono uguali → stesso F24
    4. Se la quietanza ha codici extra di sanzione/interessi → RAVVEDIMENTO

    Codici sanzione ravvedimento:
    - 8901 (IRPEF), 8902 (Add. Regionale), 8903 (Add. Comunale), 8904 (IVA)
    - 8906 (Sostituti), 8907 (IRAP), 8908 (Altre imposte)

    Codici interessi ravvedimento:
    - 1989 (IRPEF), 1990 (Add. Regionale), 1991 (IVA), 1993 (IRAP)
    - 1994 (Sostituti), 1668 (Interessi dilazione), 3805 (IRAP regionale)
    """
    # Codici che indicano sanzioni e interessi per ravvedimento
    CODICI_SANZIONI = {'8901', '8902', '8903', '8904', '8905', '8906', '8907', '8908', '8909', '8910', '8911', '8913', '8918', '8926', '8929'}
    CODICI_INTERESSI = {'1989', '1990', '1991', '1993', '1994', '1668', '3805', '3857'}
    CODICI_RAVVEDIMENTO = CODICI_SANZIONI.union(CODICI_INTERESSI)

    # Estrai codici tributo da F24 commercialista
    codici_f24 = set()
    codici_f24_con_periodo = set()
    importi_f24 = {}

    for sezione in ['sezione_erario', 'sezione_inps', 'sezione_regioni', 'sezione_tributi_locali']:
        for item in f24_commercialista.get(sezione, []):
            codice = item.get('codice_tributo') or item.get('causale') or ''
            codice = str(codice).strip()
            if codice:
                codici_f24.add(codice)
                periodo = item.get('periodo_riferimento', item.get('anno_riferimento', ''))
                codici_f24_con_periodo.add(f"{codice}_{periodo}")
                importi_f24[codice] = importi_f24.get(codice, 0) + (item.get('debito', 0) or 0)

    # Estrai codici tributo da quietanza
    codici_quietanza = set()
    codici_quietanza_con_periodo = set()
    importi_quietanza = {}

    for sezione in ['sezione_erario', 'sezione_inps', 'sezione_regioni', 'sezione_tributi_locali']:
        for item in quietanza.get(sezione, []):
            codice = item.get('codice_tributo') or item.get('causale') or ''
            codice = str(codice).strip()
            if codice:
                codici_quietanza.add(codice)
                periodo = item.get('periodo_riferimento', item.get('anno_riferimento', ''))
                codici_quietanza_con_periodo.add(f"{codice}_{periodo}")
                importi_quietanza[codice] = importi_quietanza.get(codice, 0) + (item.get('debito', 0) or 0)

    # Analisi dei codici
    codici_match = codici_f24.intersection(codici_quietanza)
    codici_mancanti_in_quietanza = codici_f24 - codici_quietanza
    codici_extra_in_quietanza = codici_quietanza - codici_f24

    # Identifica codici ravvedimento negli extra
    codici_ravv_trovati = codici_extra_in_quietanza.intersection(CODICI_RAVVEDIMENTO)
    codici_sanzioni_trovati = codici_extra_in_quietanza.intersection(CODICI_SANZIONI)
    codici_interessi_trovati = codici_extra_in_quietanza.intersection(CODICI_INTERESSI)

    # Calcola importi
    importo_f24 = f24_commercialista.get("totali", {}).get("saldo_netto", 0) or \
                  f24_commercialista.get("totali", {}).get("saldo_finale", 0) or 0
    importo_quietanza = quietanza.get("totali", {}).get("saldo_delega", 0) or \
                        quietanza.get("totali", {}).get("totale_debito", 0) or \
                        abs(quietanza.get("totali", {}).get("saldo_netto", 0) or 0)
    differenza = round(importo_quietanza - importo_f24, 2)

    # Logica di matching
    # 1. Se tutti i codici base dell'F24 sono presenti nella quietanza → MATCH
    codici_base_f24 = codici_f24 - CODICI_RAVVEDIMENTO
    codici_base_quietanza = codici_quietanza - CODICI_RAVVEDIMENTO

    match_codici_base = codici_base_f24.issubset(codici_base_quietanza)

    # 2. Calcola percentuale di match
    if len(codici_base_f24) > 0:
        match_percentage = len(codici_base_f24.intersection(codici_base_quietanza)) / len(codici_base_f24) * 100
    else:
        match_percentage = 0

    # 3. Determina se è un ravvedimento
    is_ravvedimento = False
    tipo_ravvedimento = None

    if match_codici_base and len(codici_ravv_trovati) > 0:
        is_ravvedimento = True
        if codici_sanzioni_trovati and codici_interessi_trovati:
            tipo_ravvedimento = "COMPLETO"
        elif codici_sanzioni_trovati:
            tipo_ravvedimento = "SOLO_SANZIONI"
        elif codici_interessi_trovati:
            tipo_ravvedimento = "SOLO_INTERESSI"

    # 4. Determina il match finale
    # Match se: codici base corrispondono (con o senza ravvedimento)
    is_match = match_percentage >= 70 or (match_codici_base and len(codici_base_f24) > 0)

    return {
        "match": is_match,
        "match_percentage": round(match_percentage, 1),
        "codici_match": list(codici_match),
        "codici_mancanti": list(codici_mancanti_in_quietanza),
        "codici_extra": list(codici_extra_in_quietanza),
        "importo_f24": importo_f24,
        "importo_quietanza": importo_quietanza,
        "differenza_importo": differenza,
        "is_ravvedimento": is_ravvedimento,
        "tipo_ravvedimento": tipo_ravvedimento,
        "codici_sanzioni_trovati": list(codici_sanzioni_trovati),
        "codici_interessi_trovati": list(codici_interessi_trovati),
        "importo_sanzioni": sum(importi_quietanza.get(c, 0) for c in codici_sanzioni_trovati),
        "importo_interessi": sum(importi_quietanza.get(c, 0) for c in codici_interessi_trovati)
    }
