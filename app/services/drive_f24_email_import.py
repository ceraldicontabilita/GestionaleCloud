"""Acquisizione degli F24 da email verificata nel Drive canonico."""
from __future__ import annotations

import os
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any

from app.services.drive_f24_model_upload import upload_f24_accountant_model
from app.services.f24_parser import parse_quietanza_f24


def _email_year(value: Any) -> int:
    try:
        return parsedate_to_datetime(str(value)).year
    except (TypeError, ValueError, OverflowError):
        return datetime.now().year


def import_downloaded_accountant_attachments(result: dict[str, Any], *, service=None) -> dict[str, Any]:
    """Importa solo allegati di mittenti gia classificati come commercialista.

    La classificazione del mittente prova la provenienza del modello, non il
    pagamento. Gli altri mittenti restano esclusi e dichiarati nel risultato.
    """
    imported: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for attachment in result.get("allegati") or []:
        path = str(attachment.get("file_path") or "")
        filename = str(attachment.get("original_filename") or "f24.pdf")
        try:
            if attachment.get("mittente_tipo") != "commercialista":
                skipped.append({"file": filename, "reason": "MITTENTE_NON_COMMERCIALISTA"})
                continue
            if not path or not os.path.isfile(path):
                raise ValueError("Allegato temporaneo non disponibile")
            with open(path, "rb") as handle:
                content = handle.read()
            parsed_receipt = parse_quietanza_f24(pdf_content=content)
            receipt_general = parsed_receipt.get("dati_generali") or {}
            receipt_protocol = "".join(
                character for character in str(receipt_general.get("protocollo_telematico") or "")
                if character.isdigit()
            )
            if len(receipt_protocol) >= 12 and (
                receipt_general.get("data_pagamento") or receipt_general.get("abi")
            ):
                skipped.append({
                    "file": filename,
                    "reason": "QUIETANZA_ADE_NON_IMPORTATA_COME_MODELLO",
                    "protocol": receipt_protocol,
                })
                continue
            imported.append(upload_f24_accountant_model(
                content=content,
                filename=filename,
                filing_year=_email_year(attachment.get("email_date")),
                note="F24 acquisito automaticamente da email del commercialista configurato",
                service=service,
                source_metadata={
                    "source_kind": "trusted_accountant_email",
                    "email_from": attachment.get("email_from"),
                    "email_subject": attachment.get("email_subject"),
                    "email_date": attachment.get("email_date"),
                },
            ))
        except Exception as exc:
            errors.append({"file": filename, "error": str(exc)})
        finally:
            if path and os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
    return {
        "success": not errors,
        "email_found": result.get("totale_email", 0),
        "attachments_found": result.get("totale_allegati", 0),
        "imported": imported,
        "imported_count": len(imported),
        "skipped": skipped,
        "error_count": len(errors),
        "errors": errors,
        "storage": "google_drive",
        "payment_proven": False,
    }
