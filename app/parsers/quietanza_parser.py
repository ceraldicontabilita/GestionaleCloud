"""
Parser Quietanza di Versamento ADE — Ceraldi ERP
Documento ufficiale Agenzia Entrate (provvedimento 2014/13917)
Contiene il PROTOCOLLO TELEMATICO = prova definitiva del pagamento.
Collection MongoDB: quietanze (separata da f24)
Chiave unica: protocollo_telematico
"""

import re, io
from datetime import datetime
from typing import Optional

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

from app.parsers.f24_parser import (
    CODICI_ERARIO, CODICI_REGIONI, CODICI_INPS,
    _parse_euro,
)

CODICI_TRIB_LOCALI_Q = {
    "3847": "IMU tributo locale acconto",
    "3848": "IMU tributo locale saldo",
    "3918": "IMU fabbricati altri",
    "8952": "IMU interessi ravvedimento",
    "1671": "Credito tributo locale in compensazione",
}

CODICI_RAVVEDIMENTO = {
    "1713","1668","8947","8948","8949","8906","8907","1993","8950","8952"
}
CODICI_AVVISO_BONARIO = {"9001","9002"}


def _parse_data_versamento(text: str) -> Optional[str]:
    """Estrae data versamento dalla quietanza ADE."""
    # Cerca pattern: cifre separate da spazi/pipe nel blocco estremi
    # "1 7 0 1 2 0 2 5" = 17/01/2025
    m = re.search(r'DATA DEL VERSAMENTO[\s\S]{0,200}?(\d)\s*(\d)\s*[\|]?\s*(\d)\s*(\d)\s*[\|]?\s*(\d)\s*(\d)\s*(\d)\s*(\d)', text)
    if m:
        g = m.group(1) + m.group(2)
        mo = m.group(3) + m.group(4)
        a = m.group(5) + m.group(6) + m.group(7) + m.group(8)
        try:
            return f"{a}-{mo}-{g}"
        except:
            pass
    return None


def parse_quietanza_pdf(pdf_bytes: bytes, filename: str = "") -> Optional[dict]:
    if not HAS_PDFPLUMBER:
        raise ImportError("pdfplumber non installato")
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        # Usa extract_words per precisione colonne
        pages_text = []
        all_words = []
        for page in pdf.pages:
            txt = page.extract_text(layout=True) or ""
            pages_text.append(txt)
            words = page.extract_words(x_tolerance=3, y_tolerance=3)
            all_words.extend(words)
        text = "\n".join(pages_text)

    if "QUIETANZA DI VERSAMENTO" not in text:
        return None

    doc = {
        "tipo_documento": "QUIETANZA",
        "pdf_filename": filename,
        "codice_fiscale": "04523831214",
        "contribuente": "CERALDI GROUP S.R.L.",
        "stato": "pagato",
        "tributi_flat": [],
        "note_ravvedimento": False,
        "note_avviso_bonario": False,
    }

    # Protocollo telematico (18 cifre)
    m = re.search(r'\b(\d{17,20})\b', text)
    if m:
        doc["protocollo_telematico"] = m.group(1)

    # Data versamento
    doc["data_versamento"] = _parse_data_versamento(text)

    # Saldo delega
    m = re.search(r'Saldo delega[\s\S]{0,60}?([\d\.]+,\d{2})', text)
    if m:
        doc["saldo_finale"] = _parse_euro(m.group(1))

    # Codice atto (avviso bonario)
    m = re.search(r'CODICE ATTO[\s\S]{0,100}?(\d{8,12})\b', text)
    if m:
        doc["codice_atto"] = m.group(1)
        doc["note_avviso_bonario"] = True

    # ABI/CAB
    m = re.search(r'ABI\s+(\d+).*?CAB\s+(\d+)', text, re.S)
    if m:
        doc["abi"] = m.group(1)
        doc["cab"] = m.group(2)

    # Data e ora generazione documento
    m = re.search(r'Data:\s*(\d{2}/\d{2}/\d{4})\s*-\s*Ore:\s*([\d:]+)', text)
    if m:
        doc["data_generazione"] = m.group(1)
        doc["ora_generazione"] = m.group(2)

    # ── Dettaglio tributi ─────────────────────────────────────
    tributi = []
    lines = text.split("\n")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # ERARIO
        m = re.match(
            r'ERARIO\s+(\d{4})\s*(\d{2})?\s+(\d{4})\s+([\d\.]+,\d{2})\s+([\d\.]+,\d{2})',
            line
        )
        if m:
            cod = m.group(1)
            mese = m.group(2)
            anno = m.group(3)
            deb = _parse_euro(m.group(4))
            cred = _parse_euro(m.group(5))
            rigo = {
                "sezione": "ERARIO",
                "codice_tributo": cod,
                "descrizione": CODICI_ERARIO.get(cod, f"Codice {cod}"),
                "mese_rif": mese,
                "anno_rif": anno,
                "debito": deb,
                "credito": cred,
            }
            tributi.append(rigo)
            if cod in CODICI_RAVVEDIMENTO:
                doc["note_ravvedimento"] = True
            if cod in CODICI_AVVISO_BONARIO:
                doc["note_avviso_bonario"] = True
            continue

        # INPS
        m = re.match(
            r'INPS\s+(\d{4})\s+(\S+)\s+(\S+)\s+([\d/]+\s*\d{0,4})\s+([\d\.]+,\d{2})\s+([\d\.]+,\d{2})',
            line
        )
        if m:
            causale = m.group(2)
            deb = _parse_euro(m.group(5))
            rigo = {
                "sezione": "INPS",
                "codice_tributo": causale,
                "descrizione": CODICI_INPS.get(causale, f"INPS {causale}"),
                "sede": m.group(1),
                "matricola": m.group(3),
                "periodo": m.group(4).strip(),
                "debito": deb,
                "credito": 0.0,
            }
            tributi.append(rigo)
            continue

        # INAIL
        m = re.match(r'INAIL\s+(\d+)\s+(\S+)\s+(\S+)\s+([\d\.]+,\d{2})\s+([\d\.]+,\d{2})', line)
        if m:
            rigo = {
                "sezione": "INAIL",
                "codice_tributo": "INAIL",
                "descrizione": "INAIL premi assicurativi",
                "sede": m.group(1),
                "causale_rif": m.group(2),
                "ditta": m.group(3),
                "debito": _parse_euro(m.group(4)),
                "credito": 0.0,
            }
            tributi.append(rigo)
            continue

        # REGIONI
        m = re.match(
            r'REGIONI\s+(\d+)\s+(\d{4})\s+([\S/]+)?\s+(\d{4})\s+([\d\.]+,\d{2})\s+([\d\.]+,\d{2})',
            line
        )
        if m:
            cod = m.group(2)
            rigo = {
                "sezione": "REGIONI",
                "codice_tributo": cod,
                "descrizione": CODICI_REGIONI.get(cod, f"Regioni {cod}"),
                "codice_regione": m.group(1),
                "mese_rif": m.group(3),
                "anno_rif": m.group(4),
                "debito": _parse_euro(m.group(5)),
                "credito": _parse_euro(m.group(6)),
            }
            tributi.append(rigo)
            if cod in {"8950"}:
                doc["note_ravvedimento"] = True
            continue

        # TRIB.LOCALI
        m = re.match(
            r'TRIB\.LOCALI\s+(\S+)\s+(\d{4})\s+([\S/]+)?\s+(\d{4})\s+([\d\.]+,\d{2})\s+([\d\.]+,\d{2})',
            line
        )
        if m:
            cod = m.group(2)
            rigo = {
                "sezione": "TRIB_LOCALI",
                "codice_tributo": cod,
                "descrizione": CODICI_TRIB_LOCALI_Q.get(cod, f"Tributo locale {cod}"),
                "codice_ente": m.group(1),
                "mese_rif": m.group(3),
                "anno_rif": m.group(4),
                "debito": _parse_euro(m.group(5)),
                "credito": _parse_euro(m.group(6)),
            }
            tributi.append(rigo)
            if cod in {"8952"}:
                doc["note_ravvedimento"] = True
            continue

    doc["tributi_flat"] = tributi
    doc["n_tributi"] = len(tributi)
    doc["updated_at"] = datetime.utcnow()
    return doc
