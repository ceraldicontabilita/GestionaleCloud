"""Import documentale mutui BPM con fonti separate e deduplica SHA-256.

Piano di ammortamento, estratto annuale e quietanza sono evidenze diverse.
La quietanza prova una rata; il flag di riconciliazione bancaria richiede
comunque il movimento reale dell'estratto conto.
"""
from __future__ import annotations

import hashlib
import os
import re
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import pdfplumber


def _money(value: str | None) -> float:
    raw = re.sub(r"[^0-9,.-]", "", str(value or ""))
    if not raw:
        return 0.0
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    return round(float(raw), 2)


def _date_iso(value: str | None) -> Optional[str]:
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def classify_mutuo_text(text: str) -> str:
    # I PDF bancari spesso spezzano le intestazioni fra righe o aggiungono
    # spazi non separabili: la classificazione deve essere indipendente dal
    # layout visuale del documento.
    upper = re.sub(r"\s+", " ", text.upper()).strip()
    if "PIANO DI AMMORTAMENTO" in upper or "NUMERO DELIBERA" in upper:
        return "piano_ammortamento"
    if (
        ("QUIETANZA" in upper and "PAGAMENTO" in upper)
        or ("FINANZIAMENTO N." in upper and "RATA N." in upper
            and "SCADENTE IL" in upper and "CAPITALE EUR" in upper)
    ):
        return "quietanza"
    if "CAPITALE INIZIALE AL" in upper and "CAPITALE FINALE AL" in upper:
        return "estratto_annuale"
    return "sconosciuto"


def parse_quietanza_text(text: str, filename: str = "") -> Dict[str, Any]:
    # Alcune quietanze BPM contengono un secondo layer testuale con ogni
    # glifo duplicato (es. DDEEBBIITTOO ... 222233..336633,,4466). Lo si
    # normalizza solo sulle righe riconoscibili, senza alterare il resto.
    doubled_lines = []
    for line in text.splitlines():
        if line.startswith(("DDEE", "TTOOTTAALLEE", "AABBII")):
            doubled_lines.append(re.sub(r"(.)\1", r"\1", line))
    searchable = text + "\n" + "\n".join(doubled_lines)

    def find(pattern: str) -> Optional[str]:
        match = re.search(pattern, searchable, re.I | re.S)
        return match.group(1).strip() if match else None

    data_nome = re.search(r"_(\d{2}-\d{2}-\d{4})(?:_|\.)", filename)
    totale_nome = re.search(r"_([\d.]+,\d{2})\.pdf$", filename, re.I)
    capitale = _money(find(r"CAPITALE\s+EUR\s*([\d.,]+)"))
    interessi = _money(find(r"INTERESSI\s+EUR\s*([\d.,]+)"))
    spese = _money(find(r"CONTEGGIATE\s+([\d.,]+)\s+EURO\s+PER\s+SPESE"))
    totale = _money(totale_nome.group(1)) if totale_nome else round(capitale + interessi + spese, 2)
    numero_finanziamento = find(r"([0-9]{4}/[0-9]{7,14})\s*Finanziamento\s+n")
    if not numero_finanziamento:
        numero_finanziamento = find(r"Finanziamento\s+n[.°]?\s*([0-9/]+)")
    return {
        "tipo_documento": "quietanza",
        "numero_finanziamento": numero_finanziamento,
        "numero_rata": int(find(r"RATA\s+N[.°]?\s*(\d+)") or 0) or None,
        "data_scadenza": _date_iso(find(r"SCADENTE\s+IL\s+(\d{2}/\d{2}/\d{4})")),
        "data_pagamento": _date_iso(data_nome.group(1)) if data_nome else None,
        "quota_capitale": capitale,
        "quota_interessi": interessi,
        "spese_incasso": spese,
        "importo_totale": totale,
        "debito_residuo": (
            _money(residuo) if (residuo := find(
                r"DEBITO\s+RESIDUO\s+DOPO\s+INCASSO\s+EUR\s*([\d.,]+)"
            )) is not None else None
        ),
        "prova_pagamento": True,
        "riconciliato_banca": False,
    }


def parse_estratto_annuale_text(text: str, filename: str = "") -> Dict[str, Any]:
    def find(pattern: str) -> Optional[str]:
        match = re.search(pattern, text, re.I | re.S)
        return match.group(1).strip() if match else None

    anno = find(r"CAPITALE\s+FINALE\s+AL\s+\d{2}/\d{2}/(\d{4})")
    numero = find(r"Finanziamento\s+n[.]?\s*([0-9/]+)")
    pagamenti = []
    pattern = re.compile(
        r"PAGAMENTO\s+RATA\s+(\d{2}/\d{2}/\d{4})\s+"
        r"(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+([\d.,]+)",
        re.I,
    )
    for match in pattern.finditer(text):
        pagamenti.append({
            "data_operazione": _date_iso(match.group(1)),
            "data_scadenza": _date_iso(match.group(2)),
            "data_valuta": _date_iso(match.group(3)),
            "importo": _money(match.group(4)),
        })
    return {
        "tipo_documento": "estratto_annuale",
        "anno": int(anno) if anno else None,
        "numero_finanziamento": numero,
        "capitale_iniziale": _money(find(r"CAPITALE\s+INIZIALE\s+AL\s+\d{2}/\d{2}/\d{4}:?\s*([\d.,]+)")),
        "capitale_finale": _money(find(r"CAPITALE\s+FINALE\s+AL\s+\d{2}/\d{2}/\d{4}:?\s*([\d.,]+)")),
        "importo_stipulato": _money(find(r"IMPORTO\s+STIPULATO/RINEGOZIATO\s+([\d.,]+)")),
        "data_scadenza": _date_iso(find(r"DATA\s+SCADENZA\s+(\d{2}/\d{2}/\d{4})")),
        "pagamenti": pagamenti,
        "riconciliato_banca": False,
    }


def _extract_text(content: bytes) -> str:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(content)
        path = tmp.name
    try:
        with pdfplumber.open(path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    finally:
        os.unlink(path)


async def importa_documento_mutuo(
    db, content: bytes, filename: str, *, drive_file_id: Optional[str] = None,
) -> Dict[str, Any]:
    digest = hashlib.sha256(content).hexdigest()
    existing = await db["mutui_documenti_import"].find_one(
        {"sha256": digest}, {"_id": 0, "tipo_documento": 1}
    )
    if existing:
        return {"duplicate": True, "document_type": existing.get("tipo_documento")}

    text = _extract_text(content)
    tipo = classify_mutuo_text(text)
    if tipo == "sconosciuto":
        raise ValueError("Formato documento mutuo non riconosciuto")

    now = datetime.now(timezone.utc).isoformat()
    if tipo == "quietanza":
        parsed = parse_quietanza_text(text, filename)
        collection = "mutui_quietanze"
        key = {"sha256": digest}
    elif tipo == "estratto_annuale":
        parsed = parse_estratto_annuale_text(text, filename)
        collection = "mutui_estratti_annuali"
        key = {"sha256": digest}
    else:
        from app.routers.mutui_parser import parse_mutuo_pdf
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(content)
            path = tmp.name
        try:
            parsed = parse_mutuo_pdf(path)
        finally:
            os.unlink(path)
        if not parsed.get("numero_delibera") or not parsed.get("rate"):
            raise ValueError("Piano di ammortamento privo di delibera o rate")
        parsed["tipo_documento"] = tipo
        collection = "mutui_piani_documentali"
        key = {"numero_delibera": parsed["numero_delibera"], "sha256": digest}

    document = {
        **parsed,
        "sha256": digest,
        "filename": filename,
        "drive_file_id": drive_file_id,
        "source": "drive_estratti_conto_mutui",
        "updated_at": now,
    }
    await db[collection].update_one(
        key, {"$set": document, "$setOnInsert": {"created_at": now}}, upsert=True
    )
    await db["mutui_documenti_import"].insert_one({
        "sha256": digest, "tipo_documento": tipo, "filename": filename,
        "drive_file_id": drive_file_id, "created_at": now,
    })
    return {"duplicate": False, "document_type": tipo, "records": 1}
