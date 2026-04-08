"""
Parser Avvisi Tributi Locali — Ceraldi ERP
==========================================
Gestisce avvisi di pagamento emessi dal Comune di Napoli (e altri enti locali):
  - TARI (Tassa Rifiuti) — codice tributo 3944 + TEFA
  - IMU (Imposta Municipale Propria) — codice 3847/3848
  - Bollo auto, COSAP, ecc.

I documenti contengono:
  - Intestazione contribuente (CF, nome, indirizzo)
  - Dettaglio immobili/utenze
  - Rate di pagamento con F24 pre-compilati (Identificativo Operazione)
  - Componenti perequative ARERA (UR1/UR2/UR3) per TARI

ATTENZIONE: questi avvisi possono essere intestati a:
  - Ceraldi Group SRL (04523831214) → collection "tributi_azienda"
  - Persone fisiche della famiglia Ceraldi → collection "tributi_privati"

Il sistema deve chiedere all'utente dove archiviare se ambiguo.

Collection MongoDB:
  - tributi_azienda (CF 04523831214)
  - tributi_privati (altri CF)

Codici tributo APPRESI da avvisi reali Napoli:
  3944 = TARI (Tassa Rifiuti) — tributi locali, ente F839
  TEFA = Tributo Provinciale Ambientale (5% della TARI)
  3847 = IMU acconto (già in parser F24)
  3848 = IMU saldo (già in parser F24)
  1671 = Credito tributo locale compensazione (già noto)
  8952 = Interessi ravvedimento IMU (già noto)

Struttura F24 avvisi TARI Napoli:
  Sezione: E L (Tributi Locali — Elementi Identificativi)
  Codice tributo: 3944 (TARI) / TEFA
  Codice ente: F839 (Napoli)
  Anno riferimento: 4 cifre (es. 2025)
  Mese riferimento: 2 cifre (es. 0101 = mese 01, rata 01)
  Num. immobile: 1

Nota su codice mese/rata nei modelli F24 TARI Napoli:
  0101 = anno 2025, rata unica (mese 01, rata 01)
  0103 = anno 2025, rata 1 di 3 (mese 01, rata 03 = triennale)
  0203 = anno 2025, rata 2 di 3
  0303 = anno 2025, rata 3 di 3

Saldo/conguaglio arriverà con avviso separato (febbraio 2026).

Componenti perequative ARERA:
  UR1 = 0,10 euro/utenza (delibera 386/2023 ARERA)
  UR2 = 1,50 euro/utenza (delibera 386/2023 ARERA)
  UR3 = 6,00 euro/utenza 2025 (delibera 133/2025 ARERA — bonus sociale rifiuti)
  Tutte riversate alla CSEA.
"""

import re, io
from datetime import datetime, date
from typing import Optional

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

from app.parsers.f24_parser import _parse_euro


CF_AZIENDA = "04523831214"

# Mappa CF noti della famiglia Ceraldi
CF_NOTI = {
    "CRLMHL50R01F352F": {"nome": "Ceraldi Michele", "relazione": "familiare"},
    "CRLNNT75M55F352C": {"nome": "Ceraldi Antonietta", "relazione": "familiare"},
    "04523831214": {"nome": "Ceraldi Group SRL", "relazione": "azienda"},
}

CODICI_TARI = {
    "3944": "TARI — Tassa Rifiuti (tributo locale Comune Napoli)",
    "TEFA": "Tributo Provinciale Ambientale (5% della TARI)",
    "3847": "IMU acconto",
    "3848": "IMU saldo",
    "1671": "Credito tributo locale",
}

TIPO_AVVISO_MAP = {
    "AVVISO DI PAGAMENTO TARI": "TARI",
    "AVVISO DI ACCERTAMENTO": "ACCERTAMENTO",
    "AVVISO DI PAGAMENTO IMU": "IMU",
    "AVVISO DI LIQUIDAZIONE": "LIQUIDAZIONE",
}


def _determina_collezione(cf: str) -> str:
    """Determina la collection MongoDB in base al CF."""
    if cf == CF_AZIENDA:
        return "tributi_azienda"
    return "tributi_privati"


def _determina_intestatario(cf: str) -> dict:
    """Ritorna info sul contribuente dal CF."""
    info = CF_NOTI.get(cf, {"nome": f"CF {cf}", "relazione": "sconosciuto"})
    return {
        "cf": cf,
        "nome": info["nome"],
        "relazione": info["relazione"],
        "collezione": _determina_collezione(cf),
    }


def parse_avviso_tari_pdf(pdf_bytes: bytes, filename: str = "") -> Optional[dict]:
    """Entry point: parsea avviso TARI/IMU del Comune."""
    if not HAS_PDFPLUMBER:
        raise ImportError("pdfplumber non installato")
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = "\n".join(p.extract_text(layout=True) or "" for p in pdf.pages)
    return parse_avviso_tari_text(text, filename)


def parse_avviso_tari_text(text: str, filename: str = "") -> Optional[dict]:
    """Parsea il testo estratto da un avviso tributo locale."""

    # Determina tipo avviso
    tipo_tributo = None
    for keyword, tipo in TIPO_AVVISO_MAP.items():
        if keyword in text.upper():
            tipo_tributo = tipo
            break
    if not tipo_tributo:
        return None  # non è un avviso tributo locale

    doc = {
        "tipo_documento": "AVVISO_TRIBUTO_LOCALE",
        "tipo_tributo": tipo_tributo,
        "pdf_filename": filename,
        "stato": "da_pagare",
        "rate": [],
        "arretrati": False,
        "arretrati_importo": 0.0,
        "componenti_perequative": {},
        "immobili": [],
        "updated_at": datetime.utcnow(),
    }

    # ── Protocollo ─────────────────────────────────────────────
    m = re.search(r"Prot\.?\s*n°?\s*([\d/]+)\s+del\s+(\d{2}/\d{2}/\d{4})", text)
    if m:
        doc["protocollo"] = m.group(1)
        doc["data_emissione"] = m.group(2)

    # ── Codice contribuente ─────────────────────────────────────
    m = re.search(r"Cod\.?\s*Contribuente[:\s]+(\d+)", text)
    if m:
        doc["cod_contribuente"] = m.group(1)

    # ── CF contribuente ─────────────────────────────────────────
    # Formato CF persona fisica: CRLNNT75M55F352C (16 char alfanumerico)
    m = re.search(r"P\.IVA/C\.F\.?\s+([A-Z0-9]{16})", text)
    if not m:
        m = re.search(r"\b([A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b", text)
    if m:
        cf = m.group(1)
        doc["codice_fiscale"] = cf
        intestatario = _determina_intestatario(cf)
        doc["intestatario"] = intestatario
        doc["collezione_target"] = intestatario["collezione"]

    # ── Anno di riferimento ─────────────────────────────────────
    m = re.search(r"TARI[^\d]*(\d{4})", text)
    if m:
        doc["anno"] = int(m.group(1))
    else:
        doc["anno"] = date.today().year

    # ── Totale dovuto ───────────────────────────────────────────
    m = re.search(r"TOTALE DOVUTO IN ACCONTO[\s\S]{0,20}(€\s*[\d\.]+,[\d]{2}|[\d\.]+,[\d]{2})", text)
    if m:
        doc["totale_acconto"] = _parse_euro(m.group(1).replace("€", "").strip())

    # ── Scadenza saldo ──────────────────────────────────────────
    m = re.search(r"[Ss]aldo[/a-z]*[\s:]+(?:la\s+scadenza\s+è\s+fissata\s+al\s+)?(\d{1,2}/\d{2}/\d{4})", text)
    if m:
        doc["scadenza_saldo"] = m.group(1)

    # ── Componenti perequative ARERA ────────────────────────────
    ur1 = re.search(r"UR1[^€]*€\s*([\d,]+)", text)
    ur2 = re.search(r"UR2[^€]*€\s*([\d,]+)", text)
    ur3 = re.search(r"UR3[^€]*€\s*([\d,]+)", text)
    totale_uc = re.search(r"COMPONENTI PEREQUATIVE[\s\S]{0,30}€\s*([\d\.]+,[\d]{2})", text)
    if ur1 or ur2 or ur3:
        doc["componenti_perequative"] = {
            "UR1": _parse_euro(ur1.group(1)) if ur1 else 0.10,
            "UR2": _parse_euro(ur2.group(1)) if ur2 else 1.50,
            "UR3": _parse_euro(ur3.group(1)) if ur3 else 6.00,
            "totale": _parse_euro(totale_uc.group(1)) if totale_uc else 7.60,
        }

    # ── TEFA ────────────────────────────────────────────────────
    m = re.search(r"TEFA[^€\d]*(5%)?[\s\S]{0,20}€\s*([\d\.]+,[\d]{2})", text)
    if m:
        doc["tefa_totale"] = _parse_euro(m.group(2))

    # ── Arretrati ───────────────────────────────────────────────
    # Verifica se ci sono importi versati o crediti compensati significativi
    versato = re.search(r"IMPORTO VERSATO[\s\S]{0,20}€\s*([\d\.]+,[\d]{2})", text)
    if versato:
        v = _parse_euro(versato.group(1))
        if v > 0.50:
            doc["arretrati"] = False  # se versato, c'è già un pagamento parziale
            doc["importo_gia_versato"] = v

    # ── Rate di pagamento ────────────────────────────────────────
    # Pattern: RATA | IMPORTO TARI | IMPORTO TEFA | SCADENZA | ID_OPERAZIONE
    rate_pattern = re.findall(
        r"(UNICA|PRIMA|SECONDA|TERZA|1|2|3)\s*[|]?\s*€?\s*([\d\.]+,[\d]{2})[\s|]*€?\s*([\d\.]+,[\d]{2})\s+([\d/]+)\s+(\d{18,20})",
        text
    )
    for rp in rate_pattern:
        doc["rate"].append({
            "numero": rp[0],
            "importo_tari": _parse_euro(rp[1]),
            "importo_tefa": _parse_euro(rp[2]),
            "importo_totale": round(_parse_euro(rp[1]) + _parse_euro(rp[2]), 2),
            "scadenza": rp[3],
            "id_operazione": rp[4],
            "stato": "da_pagare",
        })

    # ── Immobili/Utenze ─────────────────────────────────────────
    # Pattern: Immobile n.X: VIA ... / mq. N / Dati Catastali: ...
    immobili_pattern = re.findall(
        r"Immobile n\.\d+:\s*([^/]+)/\s*mq\.\s*(\d+)\s*/\s*Dati Catastali:\s*([^\n]+)",
        text
    )
    for im in immobili_pattern:
        doc["immobili"].append({
            "indirizzo": im[0].strip(),
            "mq": int(im[1]),
            "dati_catastali": im[2].strip(),
        })

    # Categoria utenza non domestica
    m = re.search(r"Categoria:\s*(\d+)\s*[-–]\s*([^\n]+)", text)
    if m:
        doc["categoria_utenza"] = {
            "codice": m.group(1),
            "descrizione": m.group(2).strip()[:100],
        }

    # Parti fissa e variabile TARI
    pf = re.search(r"Parte fissa[\s\S]{0,50}€\s*([\d\.]+,[\d]{2})", text)
    pv = re.search(r"Parte Variabile[\s\S]{0,50}€\s*([\d\.]+,[\d]{2})", text)
    if pf:
        doc["tari_parte_fissa"] = _parse_euro(pf.group(1))
    if pv:
        doc["tari_parte_variabile"] = _parse_euro(pv.group(1))

    return doc
