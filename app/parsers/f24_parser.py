"""
Parser F24 Entratel — Ceraldi ERP
Estrae dati strutturati da PDF F24 generati dal software dello studio
(formato: Azienda 000026 Scadenza DD/MM/YYYY ...)

Struttura document MongoDB `f24`:
{
  _id, azienda_id, codice_fiscale,
  scadenza: "2025-02-16",          # ISO
  data_pagamento: "2025-02-17",    # ISO (da ESTREMI DEL VERSAMENTO)
  pagina: 1,                        # numero pagina (alcuni F24 hanno pag.1+pag.2)
  pagine_totali: 1,
  saldo_finale: 9216.12,
  banca: "BANCO BPM S.P.A.",
  agenzia: "NAPOLI - PIAZZA CARITA'",
  firmato_da: "PANE GIUSEPPINA",
  sezione_erario: [
    { codice_tributo, descrizione, mese_rif, anno_rif,
      debito, credito, tipo_rigo }
  ],
  sezione_inps: [
    { sede, causale, matricola, da, a, debito, credito }
  ],
  sezione_regioni: [
    { codice_regione, codice_tributo, mese_rif, anno_rif, debito, credito }
  ],
  sezione_imu: [
    { codice_ente, codice_tributo, mese_rif, anno_rif, debito, credito }
  ],
  sezione_inail: [
    { sede, codice_ditta, cc, numero_rif, causale, debito, credito }
  ],
  totali: { A, B, C, D, E, F, G, H, I, L, M, N },
  saldi: { AB, CD, EF, GH, IL, MN },
  note_ravvedimento: bool,  # True se ci sono codici ravvedimento (es. 1713)
  stato: "pagato",          # sempre "pagato" se importato
  pdf_filename: str,
  xml_source: str,          # "pdf_upload"
  created_at, updated_at,
  tributi_flat: [           # lista piatta per ricerca rapida
    { sezione, codice, descrizione, mese_rif, anno_rif, debito, credito }
  ]
}
"""

import re
import io
from datetime import datetime
from typing import Optional

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

# ── Tabella codici tributo (Erario) ──────────────────────────
CODICI_ERARIO = {
    "1001": "IRPEF ritenute lavoro dipendente",
    "1002": "IRPEF ritenute lavoro autonomo",
    "1040": "IRPEF ritenute autonomi occasionali",
    "1301": "IRES acconto",
    "1627": "IRES/IRPEF 2° acconto",
    "1628": "IRES/IRPEF saldo",
    "1629": "IRES/IRPEF 1° acconto",
    "1631": "IRES/IRPEF saldo anno precedente (comp.)",
    "1668": "Interessi dilazione/rateazione",
    "1701": "Add. regionale IRPEF - ritenute dipendenti",
    "1704": "Add. comunale IRPEF - ritenute dipendenti",
    "1712": "Add. regionale IRPEF saldo",
    "1713": "Add. comunale IRPEF saldo",
    "2003": "IVA versamento mensile",
    "6001": "IVA versamento mensile gennaio",
    "6002": "IVA versamento mensile febbraio",
    "3800": "IRAP",
    "3801": "IRAP saldo",
    "3813": "IRAP acconto 2°",
}

CODICI_IMU = {
    "3832": "IMU abitazione principale",
    "3847": "IMU - tributo locale (acconto)",
    "3848": "IMU - tributo locale (saldo)",
    "3850": "IMU terreni agricoli",
    "3851": "IMU aree fabbricabili",
    "3796": "IMU - credito compensazione",
    "3797": "IMU - credito compensazione",
}

CODICI_INPS = {
    "CXX": "Contributi INPS sede",
    "DM10": "Contributi INPS DM10",
    "F24": "INPS gestione separata",
}

ENTI_NOTI = {
    "F839": "Comune Napoli (F839)",
    "B990": "Comune Napoli - altro tributo (B990)",
}

def _parse_euro(s: str) -> float:
    """Converte stringa euro italiana → float. '1.674 97' → 1674.97"""
    if not s:
        return 0.0
    # Rimuovi spazi, punti migliaia, sostituisci virgola con punto
    s = s.strip().replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except:
        return 0.0

def _parse_date_ita(s: str) -> Optional[str]:
    """'16/02/2025' → '2025-02-16'"""
    try:
        return datetime.strptime(s.strip(), "%d/%m/%Y").strftime("%Y-%m-%d")
    except:
        return None

def _descrizione_erario(codice: str) -> str:
    return CODICI_ERARIO.get(codice, f"Codice tributo {codice}")

def _descrizione_imu(codice: str, ente: str) -> str:
    desc = CODICI_IMU.get(codice, f"Tributo locale {codice}")
    ente_desc = ENTI_NOTI.get(ente, ente)
    return f"{desc} ({ente_desc})"

def parse_f24_text(text: str, pdf_filename: str = "") -> list[dict]:
    """
    Parsea il testo grezzo estratto da un PDF F24 Entratel.
    Restituisce lista di dict (uno per pagina logica).
    """
    results = []

    # Split per pagina (ogni pagina ha "Azienda 000026 Scadenza...")
    page_blocks = re.split(
        r'(?=Azienda\s+\d+\s+Scadenza\s+\d{2}/\d{2}/\d{4})', text
    )

    for block in page_blocks:
        if not block.strip():
            continue

        doc = {
            "pdf_filename": pdf_filename,
            "xml_source": "pdf_upload",
            "codice_fiscale": "04523831214",
            "stato": "pagato",
            "sezione_erario": [],
            "sezione_inps": [],
            "sezione_regioni": [],
            "sezione_imu": [],
            "sezione_inail": [],
            "totali": {},
            "saldi": {},
            "tributi_flat": [],
            "note_ravvedimento": False,
        }

        # Scadenza e numero pagina
        m = re.search(r'Scadenza\s+(\d{2}/\d{2}/\d{4}).*?Pag\.\s*(\d+)', block, re.S)
        if m:
            doc["scadenza"] = _parse_date_ita(m.group(1))
            doc["pagina"] = int(m.group(2))
        else:
            continue

        # Data pagamento (ESTREMI DEL VERSAMENTO)
        m = re.search(r'(\d{1,2})\s+(\d{2})\s+(\d{2})\s+(\d{2})\s+(\d{4})\s*\n', block)
        if m:
            g, mm1, mm2, m2, a = m.groups()
            try:
                day = int(g)
                mon = int(mm1 + mm2)  # giorno mese anno
                yr = int(m2 + a)
                doc["data_pagamento"] = f"{yr:04d}-{mon:02d}-{day:02d}"
            except:
                pass

        # Alternativa data pagamento più robusta
        if "data_pagamento" not in doc:
            m = re.search(r'\b(\d{1,2})\s*\|\s*(\d{2})\s*\|\s*(\d{4})\b', block)
            if m:
                doc["data_pagamento"] = f"{m.group(3)}-{m.group(2)}-{int(m.group(1)):02d}"

        # Banca
        m = re.search(r'DELEGA IRREVOCABILE A:\s*(.+?)(?:\n|AGENZIA)', block, re.S)
        if m:
            doc["banca"] = m.group(1).strip()

        # Saldo finale
        m = re.search(r'SALDO FINALE.*?EURO\s*\+\s*([\d\. ]+)', block, re.S)
        if m:
            doc["saldo_finale"] = _parse_euro(m.group(1))
        else:
            m = re.search(r'EURO\s*\+\s*([\d\. ]+)\s*$', block.strip())
            if m:
                doc["saldo_finale"] = _parse_euro(m.group(1))

        # Firma
        m = re.search(r'FIRMA\s*\n(.+)', block)
        if m:
            doc["firmato_da"] = m.group(1).strip()

        # ── SEZIONE ERARIO ──────────────────────────────────────
        erario_block = _extract_section(block, "SEZIONE ERARIO", "SEZIONE INPS")
        if erario_block:
            lines = erario_block.split("\n")
            for line in lines:
                # Pattern: codice tributo (4 cifre) + mese_rif (4 cifre) + anno + importi
                m = re.match(
                    r'\s*(\d{4})\s+(\d{4})?\s*(\d{4})?\s+([\d\. ]+)?\s*([\d\. ]+)?\s*$',
                    line.strip()
                )
                if m:
                    cod = m.group(1)
                    mese = m.group(2)
                    anno = m.group(3)
                    deb = _parse_euro(m.group(4) or "0")
                    cred = _parse_euro(m.group(5) or "0")
                    if cod and (deb or cred):
                        rigo = {
                            "codice_tributo": cod,
                            "descrizione": _descrizione_erario(cod),
                            "mese_rif": mese,
                            "anno_rif": anno,
                            "debito": deb,
                            "credito": cred,
                        }
                        doc["sezione_erario"].append(rigo)
                        doc["tributi_flat"].append({
                            "sezione": "ERARIO",
                            **rigo
                        })
                        if cod in ("1713", "1668"):
                            doc["note_ravvedimento"] = True

        # ── SEZIONE INPS ────────────────────────────────────────
        inps_block = _extract_section(block, "SEZIONE INPS", "SEZIONE REGIONI")
        if inps_block:
            lines = inps_block.split("\n")
            for line in lines:
                m = re.match(
                    r'\s*(5100|5200)\s+(CXX|DM10|F24)\s+(\S+)\s+(\d{2}/\d{4})\s+(\d{2}/\d{4})?\s+([\d\. ]+)',
                    line.strip()
                )
                if m:
                    rigo = {
                        "sede": m.group(1),
                        "causale": m.group(2),
                        "matricola": m.group(3),
                        "da": m.group(4),
                        "a": m.group(5) or m.group(4),
                        "debito": _parse_euro(m.group(6)),
                        "credito": 0.0,
                    }
                    doc["sezione_inps"].append(rigo)
                    doc["tributi_flat"].append({
                        "sezione": "INPS",
                        "codice_tributo": rigo["causale"],
                        "descrizione": CODICI_INPS.get(rigo["causale"], f"INPS {rigo['causale']}"),
                        "mese_rif": rigo["da"][:2] if rigo["da"] else None,
                        "anno_rif": rigo["da"][-4:] if rigo["da"] else None,
                        "debito": rigo["debito"],
                        "credito": 0.0,
                    })

        # ── SEZIONE REGIONI ────────────────────────────────────
        reg_block = _extract_section(block, "SEZIONE REGIONI", "SEZIONE IMU")
        if reg_block:
            for m in re.finditer(
                r'(\d\s*\d)\s+(3802|3800|3801|3813|3796)\s+(\d{4})\s+(\d{4})\s+([\d\. ]+)?\s*([\d\. ]+)?',
                reg_block
            ):
                rigo = {
                    "codice_regione": m.group(1).replace(" ", ""),
                    "codice_tributo": m.group(2),
                    "mese_rif": m.group(3),
                    "anno_rif": m.group(4),
                    "debito": _parse_euro(m.group(5) or "0"),
                    "credito": _parse_euro(m.group(6) or "0"),
                }
                doc["sezione_regioni"].append(rigo)
                doc["tributi_flat"].append({
                    "sezione": "REGIONI",
                    "codice_tributo": rigo["codice_tributo"],
                    "descrizione": f"IRAP Regione {rigo['codice_regione']}",
                    "mese_rif": rigo["mese_rif"],
                    "anno_rif": rigo["anno_rif"],
                    "debito": rigo["debito"],
                    "credito": rigo["credito"],
                })

        # ── SEZIONE IMU / TRIBUTI LOCALI ───────────────────────
        imu_block = _extract_section(block, "SEZIONE IMU", "SEZIONE ALTRI ENTI")
        if imu_block:
            for m in re.finditer(
                r'([A-Z]\d{3}|\w{4})\s+(3847|3848|3797|3832|3850|3851)\s+(\d{4})\s+(\d{4})\s+([\d\. ]+)?\s*([\d\. ]+)?',
                imu_block
            ):
                rigo = {
                    "codice_ente": m.group(1),
                    "codice_tributo": m.group(2),
                    "mese_rif": m.group(3),
                    "anno_rif": m.group(4),
                    "debito": _parse_euro(m.group(5) or "0"),
                    "credito": _parse_euro(m.group(6) or "0"),
                }
                doc["sezione_imu"].append(rigo)
                doc["tributi_flat"].append({
                    "sezione": "IMU",
                    "codice_tributo": rigo["codice_tributo"],
                    "descrizione": _descrizione_imu(rigo["codice_tributo"], rigo["codice_ente"]),
                    "mese_rif": rigo["mese_rif"],
                    "anno_rif": rigo["anno_rif"],
                    "debito": rigo["debito"],
                    "credito": rigo["credito"],
                })

        # ── SEZIONE INAIL ───────────────────────────────────────
        inail_block = _extract_section(block, "SEZIONE ALTRI ENTI", "FIRMA")
        if inail_block:
            m = re.search(
                r'(33400)\s+(\d+)\s+(\d+)\s+(\w+)\s+([A-Z])\s+([\d\. ]+)',
                inail_block
            )
            if m:
                rigo = {
                    "sede": m.group(1),
                    "codice_ditta": m.group(2),
                    "cc": m.group(3),
                    "numero_rif": m.group(4),
                    "causale": m.group(5),
                    "debito": _parse_euro(m.group(6)),
                    "credito": 0.0,
                }
                doc["sezione_inail"].append(rigo)
                doc["tributi_flat"].append({
                    "sezione": "INAIL",
                    "codice_tributo": "INAIL",
                    "descrizione": "INAIL premi assicurativi",
                    "mese_rif": None,
                    "anno_rif": None,
                    "debito": rigo["debito"],
                    "credito": 0.0,
                })

        # ── Totali sezionali ───────────────────────────────────
        for letter, pattern in [
            ("A", r'TOTALE\s+A\s+([\d\. ]+)'),
            ("B", r'(\d{1,3}(?:\.\d{3})*\s+\d{2})\s*\+'),
            ("C", r'TOTALE\s+C\s+([\d\. ]+)'),
            ("E", r'TOTALE\s+E\s+([\d\. ]+)'),
            ("G", r'TOTALE\s+G\s+([\d\. ]+)'),
            ("I", r'TOTALE\s+I\s+([\d\. ]+)'),
        ]:
            m = re.search(pattern, block)
            if m:
                doc["totali"][letter] = _parse_euro(m.group(1))

        results.append(doc)

    return results


def _extract_section(text: str, start: str, end: str) -> str:
    """Estrae il testo tra due intestazioni di sezione."""
    idx_start = text.find(start)
    if idx_start == -1:
        return ""
    idx_end = text.find(end, idx_start + len(start))
    if idx_end == -1:
        return text[idx_start + len(start):]
    return text[idx_start + len(start):idx_end]


def parse_f24_pdf(pdf_bytes: bytes, filename: str = "") -> list[dict]:
    """Entry point: legge PDF e restituisce lista documenti F24."""
    if not HAS_PDFPLUMBER:
        raise ImportError("pdfplumber non installato: pip install pdfplumber")

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        full_text = "\n".join(
            page.extract_text(layout=True) or "" for page in pdf.pages
        )

    return parse_f24_text(full_text, filename)


if __name__ == "__main__":
    print("Parser F24 Ceraldi ERP — OK")
    print(f"pdfplumber disponibile: {HAS_PDFPLUMBER}")
