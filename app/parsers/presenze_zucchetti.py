"""
Parser Foglio Presenze Zucchetti (Aut. 301)
============================================
Estrae dal foglio presenze mensile:
  - Anagrafica dipendente (CF, nome, periodo, indirizzo, cessato)
  - Dettaglio giornaliero: giorno, giorno_settimana, ore_ordinarie, codici giustificativi
  - Totali: ore_ordinarie, ore per codice (AI, FE, MA, PE, ST, ecc.)
  - Legenda codici (descrizione)

Codici giustificativi Zucchetti:
  AI = Assenza ingiustificata
  FE = Ferie
  MA = Malattia
  PE = Permesso
  MT = Maternità
  RO = ROL (riduzione orario di lavoro)
  ST = Straordinario
  FS = Festività soppressa
  AP = Aspettativa

Struttura documento MongoDB (collection: presenze):
{
  codice_fiscale, codice_dipendente, cognome, nome,
  mese, anno, periodo_label,
  indirizzo, cessato, data_cessazione,
  giorni: [
    { giorno: 1, giorno_settimana: "LU",
      ore_ordinarie: 6.67,
      giustificativi: [{ codice: "AI", ore: 6.67 }] }
  ],
  totali: {
    ore_ordinarie: 93.33,
    "AI": 40.0,
    "FE": 26.67,
    ...
  },
  legenda: { "AI": "Ass.za ingiustif.", "FE": "Ferie", ... },
  dedup_key: "VSPVCN67T26F839P_09_2024"
}
"""
import re
import logging
from typing import Dict, Any, List, Optional
from datetime import date

logger = logging.getLogger(__name__)

MESI_IT = {
    'gennaio': 1, 'febbraio': 2, 'marzo': 3, 'aprile': 4,
    'maggio': 5, 'giugno': 6, 'luglio': 7, 'agosto': 8,
    'settembre': 9, 'ottobre': 10, 'novembre': 11, 'dicembre': 12,
}

CF_PATTERN = re.compile(r'([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])')

# Converti hm (ore,minuti) in ore decimali: "6,40" → 6.67
def _hm_to_ore(s: str) -> float:
    """Converte formato Zucchetti HH,MM in ore decimali."""
    try:
        s = s.replace('hm', '').strip()
        if ',' in s:
            ore_str, min_str = s.split(',')
            ore = int(ore_str)
            minuti = int(min_str.ljust(2, '0')[:2])
            return round(ore + minuti / 60, 4)
        return float(s)
    except (ValueError, AttributeError):
        return 0.0

def _parse_importo(s: str) -> float:
    try:
        return float(s.replace('.', '').replace(',', '.'))
    except (ValueError, AttributeError):
        return 0.0


def parse_presenze_pdf(pdf_path: str = None, pdf_bytes: bytes = None) -> Optional[Dict[str, Any]]:
    """
    Parsa un foglio presenze Zucchetti Aut.301.
    Ritorna None se il file non è un foglio presenze valido.
    """
    import fitz

    if pdf_path:
        doc = fitz.open(pdf_path)
    elif pdf_bytes:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    else:
        raise ValueError("Serve pdf_path o pdf_bytes")

    # Cerca pagina Aut.301
    page_301 = None
    for page in doc:
        t = page.get_text()
        if 'Autorizzazione Inail n.' in t and '301' in t:
            # Verifica che NON sia Aut.299 (cedolino)
            if '299' not in t.split('301')[0][-50:]:
                page_301 = page
                break
        elif 'Autorizzazione Inail n.        301' in t:
            page_301 = page
            break
        # Fallback: foglio con "GIORNO" e "GIUSTIFICATIVI" ma senza voci paga
        elif 'GIUSTIFICATIVI' in t and 'GIORNO' in t and 'NETTOsDELsMESE' not in t:
            page_301 = page
            break

    if page_301 is None:
        doc.close()
        return None

    text = page_301.get_text()
    words = [(round(w[0]), round(w[1]), w[4]) for w in page_301.get_text("words")]
    doc.close()

    result: Dict[str, Any] = {
        "codice_fiscale": "",
        "codice_dipendente": "",
        "cognome": "",
        "nome": "",
        "mese": 0,
        "anno": 0,
        "periodo_label": "",
        "indirizzo": "",
        "cessato": False,
        "data_cessazione": "",
        "giorni": [],
        "totali": {},
        "legenda": {},
        "dedup_key": "",
    }

    # ── Anagrafica ────────────────────────────────────────────────────
    # Cessato
    m = re.search(r'Cessato\s+il\s*[:\s]*(\d{2}-\d{2}-\d{4})', text, re.I)
    if m:
        result["cessato"] = True
        result["data_cessazione"] = m.group(1)

    # Codice fiscale
    ceraldi_piva = "04523831214"
    for m_cf in CF_PATTERN.finditer(text):
        cf = m_cf.group(1)
        if cf != ceraldi_piva:
            result["codice_fiscale"] = cf
            break

    # Periodo
    for m_name, m_num in MESI_IT.items():
        m = re.search(rf'{m_name}\s+(\d{{4}})', text, re.I)
        if m:
            result["mese"] = m_num
            result["anno"] = int(m.group(1))
            result["periodo_label"] = f"{m_name.capitalize()} {m.group(1)}"
            break

    # Codice dipendente + nome dal pattern "000026/0300001/0000000001/"
    m = re.search(r'\d{6}/(\d{7})/\d{10}/', text)
    if m:
        result["codice_dipendente"] = m.group(1)

    # Nome dipendente (riga dopo il codice pattern)
    m = re.search(r'\d{6}/\d{7}/\d{10}/\s*\n([A-ZÀÈÌÒÙ\'][A-ZÀÈÌÒÙ\' ]+(?:\n[A-ZÀÈÌÒÙ\'][A-ZÀÈÌÒÙ\' ]+)?)\n', text)
    if m:
        nome_full = m.group(1).replace('\n', ' ').strip()
        parts = nome_full.split()
        if len(parts) >= 2:
            result["cognome"] = parts[0].title()
            result["nome"] = " ".join(parts[1:]).title()

    # Indirizzo
    m = re.search(r'(VIA|VICO|CORSO|PIAZZA|VICOLO|VLE)\s+.+\n\d{5}\s+\w+', text, re.I)
    if m:
        result["indirizzo"] = m.group(0).replace('\n', ', ').strip()

    # ── Parsing giorni per coordinate X ───────────────────────────────
    # Struttura coordinate (da analisi):
    #   x ~30-49: giorno settimana + numero giorno
    #   x ~70: ore ordinarie
    #   x ~143-145: codice giustificativo 1
    #   x ~164-165: ore giustificativo 1
    #   x ~215: codice giustificativo 2
    #   x ~235: ore giustificativo 2
    # ecc.

    GIORNI_SETTIMANA = {'LU', 'MA', 'ME', 'GI', 'VE', 'SA', 'DO'}
    ORE_RE = re.compile(r'^\d+,\d{2}$')
    CODICI_GIUST = {'AI', 'FE', 'MA', 'PE', 'MT', 'RO', 'ST', 'FS', 'AP', 'MG', 'PF', 'PP'}

    # Raggruppa words per riga (y)
    from collections import defaultdict
    righe: Dict[int, List] = defaultdict(list)
    for x, y, t in words:
        righe[y].append((x, t))

    giorni = []
    for y in sorted(righe.keys()):
        row = sorted(righe[y], key=lambda r: r[0])

        # Cerca giorno settimana nella riga
        gg_sett = None
        gg_num = None
        for i, (x, t) in enumerate(row):
            if t in GIORNI_SETTIMANA and x < 55:
                gg_sett = t
            if gg_sett and re.match(r'^\d{1,2}$', t) and x < 65:
                gg_num = int(t)
                break

        if not gg_sett or not gg_num:
            continue

        # Ore ordinarie (x ~70)
        ore_ord = 0.0
        giust = []

        for x, t in row:
            if x > 60 and ORE_RE.match(t):
                if 60 <= x <= 120 and ore_ord == 0.0:
                    ore_ord = _hm_to_ore(t)
                elif x > 120:
                    # è ore di un giustificativo
                    if giust and giust[-1].get("ore", None) is None:
                        giust[-1]["ore"] = _hm_to_ore(t)
            elif t in CODICI_GIUST and x > 100:
                giust.append({"codice": t, "ore": None})

        # Ore a None → 0
        for g in giust:
            if g["ore"] is None:
                g["ore"] = 0.0

        giorni.append({
            "giorno": gg_num,
            "giorno_settimana": gg_sett,
            "ore_ordinarie": ore_ord,
            "giustificativi": giust,
            "festivo": gg_sett in ('SA', 'DO'),
        })

    result["giorni"] = sorted(giorni, key=lambda d: d["giorno"])

    # ── Totali dal footer ─────────────────────────────────────────────
    # Pattern footer: "Ore ordinarie  93,20hm  AI  Ass.za ingiustif.  40,00hm  FE  Ferie  26,40hm"
    totali = {}
    legenda = {}

    # Metodo più robusto: cerca "Ore ordinarie X,XXhm" poi coppie "CODICE Descrizione X,XXhm"
    m = re.search(r'Ore\s+ordinarie\s+([\d,]+)hm', text, re.I)
    if m:
        totali["ore_ordinarie"] = _hm_to_ore(m.group(1))

    # Cerca tutte le occorrenze di "CODICE  Descrizione  X,XXhm" nella riga footer
    footer_pattern = re.finditer(
        r'\b([A-Z]{2})\b\s+([\w\.za\s]+?)\s+([\d,]+)hm',
        text
    )
    for fm in footer_pattern:
        codice = fm.group(1)
        if codice in CODICI_GIUST:
            desc = fm.group(2).strip().rstrip('.')
            ore = _hm_to_ore(fm.group(3))
            totali[codice] = ore
            legenda[codice] = desc

    result["totali"] = totali
    result["legenda"] = legenda

    # Calcola totali anche dai giorni (verifica incrociata)
    totali_calc = {"ore_ordinarie": 0.0}
    for g in result["giorni"]:
        totali_calc["ore_ordinarie"] += g["ore_ordinarie"]
        for gj in g["giustificativi"]:
            cod = gj["codice"]
            totali_calc[cod] = totali_calc.get(cod, 0.0) + gj["ore"]
    # Usa i totali del footer se disponibili, altrimenti calcoli
    for k, v in totali_calc.items():
        if k not in result["totali"] or result["totali"][k] == 0:
            result["totali"][k] = round(v, 2)

    result["dedup_key"] = f"{result['codice_fiscale']}_{result['mese']:02d}_{result['anno']}"

    # Valida: deve avere CF e almeno qualche giorno
    if not result["codice_fiscale"] or not result["giorni"]:
        return None

    return result


def is_presenze_pdf(pdf_bytes: bytes) -> bool:
    """Verifica rapidamente se un PDF è un foglio presenze Aut.301."""
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            t = page.get_text()
            if ('301' in t and 'GIUSTIFICATIVI' in t and 'GIORNO' in t
                    and 'NETTOsDELsMESE' not in t and 'TOTALEsCOMPETENZE' not in t):
                doc.close()
                return True
        doc.close()
    except Exception:
        pass
    return False
