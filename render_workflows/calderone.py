"""Anteprima non distruttiva del CALDERONE cedolini su Google Drive."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import zipfile
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable


LABELS = (("TOTALE", "NETTO"), ("NETTO", "DEL", "MESE"),
          ("NETTO", "IN", "BUSTA"), ("NETTO", "BUSTA"))
MONEY = re.compile(r"(?<!\d)(?:EUR\s*)?(-?\d{1,3}(?:\.\d{3})*,\d{2}|-?\d+[.,]\d{2})(?!\d)", re.I)


def _money(value: str) -> Decimal | None:
    value = re.sub(r"(?i)EUR\s*", "", value).strip()
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _token(value: str) -> str:
    token = re.sub(r"[^A-Z0-9]", "", value.upper())
    return {
        "NETTOSDELSMESE": "NETTODELMESE",
        "NETTOSINSBUSTA": "NETTOINBUSTA",
        "TOTALESNETTO": "TOTALENETTO",
    }.get(token, token)


def extract_net_from_words(words: list[dict[str, Any]]) -> list[Decimal]:
    """Trova il primo importo a destra dell'etichetta nella medesima riga."""
    rows: list[list[dict[str, Any]]] = []
    for word in sorted(words, key=lambda w: (round(float(w["top"]), 1), float(w["x0"]))):
        row = next((r for r in rows if abs(float(r[0]["top"]) - float(word["top"])) <= 3), None)
        (row if row is not None else rows.append([word]) or rows[-1]).append(word)

    found: list[Decimal] = []
    for row in rows:
        row.sort(key=lambda w: float(w["x0"]))
        tokens = [_token(str(w["text"])) for w in row]
        label_end_index = None
        for index in range(len(row)):
            # Alcuni PDF codificano gli spazi come caratteri anomali e
            # pdfplumber restituisce NETTOsDELsMESE in una sola parola.
            compact = tokens[index]
            if compact in {"TOTALENETTO", "NETTODELMESE", "NETTOINBUSTA", "NETTOBUSTA"}:
                label_end_index = index
                break
            for label in LABELS:
                if tuple(tokens[index:index + len(label)]) == label:
                    label_end_index = index + len(label) - 1
                    break
            if label_end_index is not None:
                break
        if label_end_index is None:
            continue
        matched = False
        for word in row[label_end_index + 1:]:
            match = MONEY.search(str(word["text"]))
            if match:
                value = _money(match.group(1))
                if value is not None:
                    found.append(value)
                    matched = True
                break
        if matched:
            continue
        # Nei modelli paghe più comuni il valore è nella cella subito sotto
        # l'etichetta, allineato alla colonna NETTO (non sulla stessa baseline).
        anchor = row[label_end_index]
        below = []
        for word in words:
            dy = float(word["top"]) - float(anchor["top"])
            dx = abs(float(word["x0"]) - float(anchor["x0"]))
            if 3 < dy <= 22 and dx <= 65 and MONEY.search(str(word["text"])):
                below.append((dy, dx, word))
        if below:
            word = min(below, key=lambda item: (item[0], item[1]))[2]
            match = MONEY.search(str(word["text"]))
            value = _money(match.group(1)) if match else None
            if value is not None:
                found.append(value)
    return found


def extract_verified_net(pdf_bytes: bytes) -> dict[str, Any]:
    """Legge solo importi sulla stessa riga grafica di un'etichetta canonica."""
    import pdfplumber

    candidates: list[Decimal] = []
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                candidates.extend(extract_net_from_words(
                    page.extract_words(use_text_flow=False, keep_blank_chars=False)
                ))
    except Exception as exc:
        return {"status": "ERRORE_PARSER", "error": type(exc).__name__}

    unique = sorted(set(candidates))
    if len(unique) == 1:
        return {"status": "NETTO_VERIFICATO_DA_CEDOLINO", "net_amount": str(unique[0])}
    if len(unique) > 1:
        return {"status": "MULTIPLE_NETS_DA_VERIFICARE", "candidate_count": len(unique)}
    return {"status": "NETTO_NON_PRESENTE_O_NON_LEGGIBILE"}


def iter_pdfs(name: str, content: bytes) -> Iterable[tuple[str, bytes]]:
    if name.lower().endswith(".pdf"):
        if not content.startswith(b"%PDF"):
            raise ValueError("contenuto PDF non valido")
        yield name, content
        return
    if not name.lower().endswith(".zip"):
        return
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for info in archive.infolist():
            normalized = info.filename.replace("\\", "/")
            if info.is_dir() or not normalized.lower().endswith(".pdf"):
                continue
            if normalized.startswith("/") or ".." in normalized.split("/") or info.flag_bits & 1:
                raise ValueError("membro ZIP non sicuro")
            data = archive.read(info)
            if not data.startswith(b"%PDF"):
                raise ValueError("membro PDF non valido")
            yield normalized, data


def _drive_service():
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    raw = os.environ["GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON"]
    credentials = service_account.Credentials.from_service_account_info(
        json.loads(raw), scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def scan_calderone_preview(max_documents: int = 10000) -> dict[str, Any]:
    """Inventaria e analizza senza scrivere, rinominare o spostare file."""
    service = _drive_service()
    folder_id = os.environ["GOOGLE_DRIVE_INBOX_FOLDER_ID"]
    response = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id,name,mimeType,size,modifiedTime)", pageSize=1000,
        supportsAllDrives=True, includeItemsFromAllDrives=True,
    ).execute()
    files = response.get("files", [])
    statuses: Counter[str] = Counter()
    hashes: Counter[str] = Counter()
    source_count = pdf_count = errors = 0
    verified_total = Decimal("0")
    for item in files:
        if not item["name"].lower().endswith((".pdf", ".zip")):
            continue
        source_count += 1
        content = service.files().get_media(fileId=item["id"]).execute()
        try:
            for _path, pdf in iter_pdfs(item["name"], content):
                if pdf_count >= max_documents:
                    raise RuntimeError("limite documenti superato")
                pdf_count += 1
                hashes[hashlib.sha256(pdf).hexdigest()] += 1
                parsed = extract_verified_net(pdf)
                statuses[parsed["status"]] += 1
                if parsed["status"] == "NETTO_VERIFICATO_DA_CEDOLINO":
                    verified_total += Decimal(parsed["net_amount"])
        except Exception:
            errors += 1
            statuses["ERRORE_PARSER"] += 1
    return {
        "mode": "preview", "read_only": True,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "source_files": source_count, "pdf_documents": pdf_count,
        "unique_sha256": len(hashes),
        "exact_duplicate_occurrences": sum(n - 1 for n in hashes.values() if n > 1),
        "statuses": dict(statuses), "verified_net_total_eur": str(verified_total),
        "source_errors": errors,
        "next_action": "conferma richiesta prima della trasmissione al gestionale live",
    }
