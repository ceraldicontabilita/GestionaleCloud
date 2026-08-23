"""Upload probatorio dei modelli F24 del commercialista nel Drive canonico."""
from __future__ import annotations

import hashlib
import io
import re
from pathlib import PurePath
from typing import Any

from openpyxl import load_workbook

from app.services import drive_document_index as index
from app.services.f24_fiscal_evidence import (
    PARSER_KIND_PRINTABLE,
    normalize_f24_evidence_rows,
    parse_f24_evidence,
)
from app.services.drive_declaration_upload import _folder


def _safe_filename(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9À-ÿ._() -]+", "_", PurePath(value or "f24.pdf").name).strip(" .")
    if not name.lower().endswith(".pdf"):
        raise ValueError("Sono ammessi solo PDF")
    return name or "f24.pdf"


def _f24_index_values(document_id: str, digest: str, drive_path: str,
                      parsed: dict[str, Any], filing_year: int,
                      source_label: str = "UPLOAD_GESTIONALE_COMMERCIALISTA") -> list[dict[str, Any]]:
    values = []
    for row in normalize_f24_evidence_rows(parsed):
        values.append({
            "ID documento": document_id,
            "Anno pagamento": filing_year,
            "Data pagamento": "",
            "Sezione": row.get("section"),
            "Tipo riga": row.get("row_kind"),
            "Codice tributo": row.get("tax_code"),
            "Descrizione": row.get("description"),
            "Periodo tributo": row.get("reference_period") or row.get("reference_period_raw"),
            "Ente": row.get("entity_code"),
            "Debito": row.get("debit_amount"),
            "Credito": row.get("credit_amount"),
            "Protocollo": "",
            "Tipo documento": "MODELLO_F24_COMMERCIALISTA",
            "SHA-256": digest,
            "Percorso Drive": drive_path,
            "Pagina": row.get("page_number"),
            "Testo sorgente": row.get("source_text"),
            "Fonte": source_label,
        })
    return values


def upload_f24_accountant_model(*, content: bytes, filename: str, filing_year: int,
                                note: str | None = None, service=None,
                                source_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    if not content.startswith(b"%PDF"):
        raise ValueError("PDF non valido")
    if not 2000 <= int(filing_year) <= 2100:
        raise ValueError("Anno F24 non valido")
    filename = _safe_filename(filename)
    digest = hashlib.sha256(content).hexdigest()
    service = service or index.build_drive_service()
    source, catalog = index.load_full_catalog(service)
    duplicates = [row for row in catalog["documents"] if index._norm(row.get("SHA-256")) == digest]
    if duplicates:
        row = duplicates[0]
        return {
            "success": True, "duplicate": True,
            "document_id": row.get("ID documento"), "sha256": digest,
            "drive_path": row.get("Percorso Drive"),
        }

    parsed = parse_f24_evidence(content, document_kind=PARSER_KIND_PRINTABLE)
    source_metadata = source_metadata or {}
    sender = str(source_metadata.get("email_from") or "").strip().lower()
    source_kind = str(source_metadata.get("source_kind") or "manual_upload").strip().lower()
    email_source = source_kind == "trusted_accountant_email" and bool(sender)
    source_label = (
        f"EMAIL_COMMERCIALISTA_VERIFICATA:{sender}"
        if email_source else "UPLOAD_GESTIONALE_COMMERCIALISTA"
    )
    folders = ["02_F24_COMMERCIALISTA", str(filing_year)]
    if email_source:
        folders.append("EMAIL")
    parent = source["root_id"]
    for name in folders:
        parent = _folder(service, parent, name)

    from googleapiclient.http import MediaIoBaseUpload
    description_parts = [note or "Fonte dichiarata: commercialista"]
    if email_source:
        description_parts.extend(filter(None, [
            f"Mittente verificato: {sender}",
            f"Oggetto: {source_metadata.get('email_subject') or ''}",
            f"Data email: {source_metadata.get('email_date') or ''}",
        ]))
    created = service.files().create(
        body={"name": filename, "parents": [parent], "description": "\n".join(description_parts)},
        media_body=MediaIoBaseUpload(io.BytesIO(content), mimetype="application/pdf", resumable=False),
        fields="id,name,size,webViewLink", supportsAllDrives=True,
    ).execute()
    document_id = f"DOC-{digest[:24].upper()}"
    drive_path = "/".join([*folders, filename])
    try:
        original_index = index._download_index_sync(service, source["index"]["id"])
        workbook = load_workbook(io.BytesIO(original_index))
        documents = workbook[index.INDEX_SHEET_NAME]
        document_headers = [str(cell.value or "") for cell in documents[1]]
        document_values = {
            "ID documento": document_id, "Dominio": "FISCALE",
            "Categoria": "MODELLO_F24_COMMERCIALISTA", "Anno": filing_year,
            "Nome file": filename, "Estensione": ".pdf", "Dimensione byte": len(content),
            "SHA-256": digest, "Percorso Drive": drive_path,
            "Cartella Drive": "/".join(folders),
            "ZIP origine": "EMAIL_COMMERCIALISTA" if email_source else "UPLOAD_GESTIONALE",
            "Percorso nel pacchetto": filename, "Stato": "ATTIVO", "Numero documento": "",
        }
        documents.append([document_values.get(header, "") for header in document_headers])
        f24_sheet = workbook["F24_RIGHE"]
        f24_headers = [str(cell.value or "") for cell in f24_sheet[1]]
        rows = _f24_index_values(
            document_id, digest, drive_path, parsed, int(filing_year), source_label,
        )
        if not rows:
            raise ValueError("Nessuna riga tributaria F24 estratta")
        for row in rows:
            f24_sheet.append([row.get(header, "") for header in f24_headers])
        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)
        service.files().update(
            fileId=source["index"]["id"],
            media_body=MediaIoBaseUpload(
                output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                resumable=False,
            ),
            fields="id,modifiedTime", supportsAllDrives=True,
        ).execute()
    except Exception:
        # Evita originali orfani se l'aggiornamento atomico dell'indice fallisce.
        service.files().update(
            fileId=created["id"], body={"trashed": True}, fields="id,trashed",
            supportsAllDrives=True,
        ).execute()
        raise

    index._CACHE_KEY = None
    index._CACHE_CATALOG = None
    verified = service.files().get(
        fileId=created["id"], fields="id,name,size,webViewLink,trashed", supportsAllDrives=True,
    ).execute()
    return {
        "success": True, "duplicate": False, "document_id": document_id,
        "document_type": "MODELLO_F24_COMMERCIALISTA", "filing_year": filing_year,
        "sha256": digest, "drive_path": drive_path, "drive_file_id": verified["id"],
        "drive_url": verified.get("webViewLink"), "tax_rows": len(rows),
        "storage": "google_drive", "payment_proven": False,
        "source_provenance": "TRUSTED_ACCOUNTANT_EMAIL" if email_source else "MANUAL_ACCOUNTANT_UPLOAD",
        "source_sender": sender or None,
    }
