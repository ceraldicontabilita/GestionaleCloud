"""Import idempotente e probatorio degli archivi PartenoPay navigabili."""
from __future__ import annotations

import hashlib
import io
import json
import posixpath
import re
import zipfile
import asyncio
import base64
from datetime import datetime, timedelta, timezone
from typing import Any, Dict


ROOT = "package_clean/"
DATA_PATH = ROOT + "data.json"
MANIFEST_PATH = ROOT + "documenti/MANIFEST_SHA256.csv"
_VERBALE_RE = re.compile(r"VERBALE\s+N(?:[.:°])*\s*([A-Z0-9/-]+)", re.I)
_TARGA_RE = re.compile(r"TARGA:\s*([A-Z]{2}\d{3}[A-Z]{2})", re.I)


def is_partenopay_archive(content: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return DATA_PATH in archive.namelist() and MANIFEST_PATH in archive.namelist()
    except (OSError, zipfile.BadZipFile):
        return False


def _safe_name(name: str) -> str:
    normalized = posixpath.normpath(str(name or "").replace("\\", "/"))
    if normalized.startswith("../") or normalized.startswith("/") or normalized == "..":
        raise ValueError(f"Percorso ZIP non sicuro: {name}")
    return normalized


def _iso_date(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return None


def inspect_partenopay_archive(content: bytes) -> Dict[str, Any]:
    """Valida struttura, nomi, manifest SHA-256 e restituisce il piano import."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"Archivio PartenoPay non valido: {exc}") from exc
    with archive:
        if archive.testzip() is not None:
            raise ValueError("Archivio PartenoPay corrotto")
        names = {_safe_name(item.filename) for item in archive.infolist() if not item.is_dir()}
        if DATA_PATH not in names or MANIFEST_PATH not in names:
            raise ValueError("data.json o manifest SHA-256 assente")
        payload = json.loads(archive.read(DATA_PATH))
        required = {"summary", "records", "emails", "files"}
        if not isinstance(payload, dict) or not required.issubset(payload):
            raise ValueError("Schema data.json PartenoPay non riconosciuto")
        file_rows = payload.get("files") or []
        errors = []
        verified = 0
        for row in file_rows:
            relative = _safe_name(row.get("file"))
            full = relative if relative.startswith(ROOT) else ROOT + relative
            if full not in names:
                errors.append({"file": relative, "errore": "assente_nello_zip"})
                continue
            expected = str(row.get("sha256") or "").lower()
            actual = hashlib.sha256(archive.read(full)).hexdigest()
            if expected and expected != actual:
                errors.append({"file": relative, "errore": "sha256_non_coincide"})
            else:
                verified += 1
        return {
            "payload": payload,
            "files_verified": verified,
            "integrity_errors": errors,
            "archive_sha256": hashlib.sha256(content).hexdigest(),
        }


def _record_identity(record: Dict[str, Any]) -> tuple[str, str | None, str | None]:
    notice = str(record.get("codice_avviso") or "").strip()
    text = str(record.get("oggetto_pagamento") or "")
    number_match = _VERBALE_RE.search(text)
    number = number_match.group(1).upper().rstrip("-./") if number_match else None
    plate = (_TARGA_RE.search(text).group(1).upper() if _TARGA_RE.search(text) else None)
    key = notice or number or hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:24]
    return key, number, plate


async def import_partenopay_archive(db, content: bytes, *, dry_run: bool = True) -> Dict[str, Any]:
    plan = inspect_partenopay_archive(content)
    if plan["integrity_errors"]:
        return {"success": False, "dry_run": dry_run, **{k: v for k, v in plan.items() if k != "payload"}}
    payload = plan.pop("payload")
    result: Dict[str, Any] = {
        "success": True,
        "dry_run": dry_run,
        **plan,
        "records": len(payload.get("records") or []),
        "emails": len(payload.get("emails") or []),
        "files": len(payload.get("files") or []),
        "inserted_or_updated": 0,
        "ambiguous": 0,
    }
    if dry_run:
        return result

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    archive_sha = result["archive_sha256"]

    for email in payload.get("emails") or []:
        email_id = str(email.get("id") or "").strip() or hashlib.sha256(
            json.dumps(email, sort_keys=True).encode()
        ).hexdigest()[:32]
        await db["verbali_email_archive"].update_one(
            {"id": email_id},
            {"$set": {
                "id": email_id, "gmail_message_id": email.get("id"),
                "gmail_url": email.get("gmail_url"), "thread_id": email.get("thread_id"),
                "mittente": email.get("mittente"), "destinatario": email.get("destinatario"),
                "oggetto": email.get("oggetto_email"), "testo": email.get("testo"),
                "data_email": email.get("data_email"), "etichette": email.get("etichette"),
                "allegati": email.get("allegati") or [], "fonte": "partenopay_zip",
                "archive_sha256": archive_sha, "updated_at": now_iso,
            }, "$setOnInsert": {"created_at": now_iso}}, upsert=True,
        )

    file_by_path = {str(item.get("file")): item for item in payload.get("files") or []}
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for relative, item in file_by_path.items():
            full = relative if relative.startswith(ROOT) else ROOT + relative
            raw = archive.read(full)
            sha = hashlib.sha256(raw).hexdigest()
            doc_id = f"partenopay_{sha[:32]}"
            await db["documents_inbox"].update_one(
                {"id": doc_id},
                {"$set": {
                    "id": doc_id, "filename": item.get("nome") or posixpath.basename(relative),
                    "file_hash": sha, "sha256": sha, "source": "partenopay_zip",
                    "fonte": "partenopay_zip", "archive_path": relative,
                    "archive_sha256": archive_sha, "categoria_partenopay": item.get("categoria"),
                    "codice_avviso_estratto": item.get("codice_avviso"),
                    "original_preserved": True, "updated_at": now_iso,
                }, "$setOnInsert": {"created_at": now_iso, "processed": False, "status": "importato"}},
                upsert=True,
            )
            # Copia non distruttiva nell'area Drive Verbali. Il file originale
            # nel pacchetto e l'email sorgente non vengono mai spostati/eliminati.
            try:
                from app.services.email_drive_archive import archive_document_copy
                drive_result = await asyncio.to_thread(
                    archive_document_copy,
                    {"id": doc_id, "filename": item.get("nome") or posixpath.basename(relative),
                     "file_hash": sha, "pdf_data": base64.b64encode(raw).decode("ascii")},
                    "verbale",
                )
            except Exception as exc:
                drive_result = {"status": "error", "reason": str(exc)}
            await db["documents_inbox"].update_one(
                {"id": doc_id},
                {"$set": {"drive_archive_status": drive_result.get("status"),
                           "drive_archive_area": drive_result.get("area"),
                           "drive_archive_reason": drive_result.get("reason"),
                           "drive_archived_at": drive_result.get("archived_at")}},
            )
            if str(item.get("estensione") or "").lower() == "pdf":
                from app.services.verbali_document_import import process_verbale_document
                await process_verbale_document(
                    db, document_id=doc_id, content=raw,
                    filename=item.get("nome") or posixpath.basename(relative),
                    source="partenopay_zip",
                    parsed_metadata={"identificativo_bolletta": item.get("codice_avviso")},
                )

    for record in payload.get("records") or []:
        key, number, plate = _record_identity(record)
        linked_files = list(record.get("files") or [])
        states = str(record.get("stati") or "").casefold()
        has_receipt = any("02_quietanze" in str(path).casefold() for path in linked_files)
        payment_verified = has_receipt and "pagamento eseguito" in states
        record_id = f"verbale_{hashlib.sha256(('partenopay:' + key).encode()).hexdigest()[:32]}"
        query = {"codice_avviso": str(record.get("codice_avviso"))} if record.get("codice_avviso") else {"id": record_id}
        existing = await db["verbali_noleggio"].find_one(query, {"_id": 0})
        if existing and number and existing.get("numero_verbale") not in (None, "", number):
            result["ambiguous"] += 1
            await db["verbali_match_candidates"].update_one(
                {"id": f"candidate_{record_id}"},
                {"$set": {"id": f"candidate_{record_id}", "tipo": "VERBALE", "record": record,
                          "motivo": "numero_verbale_in_conflitto", "status": "scelta_manual_required",
                          "updated_at": now_iso}}, upsert=True,
            )
            continue
        values = {
            "id": (existing or {}).get("id") or record_id,
            "numero_verbale": number or (existing or {}).get("numero_verbale"),
            "codice_avviso": str(record.get("codice_avviso") or "") or None,
            "iuv": str(record.get("codice_avviso") or "") or None,
            "targa": plate, "importo": record.get("importo"),
            "importo_verificato": record.get("importo") is not None,
            "data_pagamento": _iso_date(record.get("data_pagamento")),
            "ente_creditore": record.get("ente"), "intestatario": record.get("intestatario"),
            "cf_piva": record.get("cf_piva"), "oggetto_pagamento": record.get("oggetto_pagamento"),
            "source": "partenopay_zip", "archive_sha256": archive_sha,
            "source_files": linked_files, "pagato_documentalmente": payment_verified,
            "stato_pagamento_documentale": "PAGATO_VERIFICATO" if payment_verified else "DA_VERIFICARE",
            "stato": "pagato_attesa_fattura" if payment_verified else ((existing or {}).get("stato") or "salvato"),
            "scadenza_operativa": (now + timedelta(days=5)).date().isoformat(),
            "scadenza_operativa_motivo": "5 giorni dalla scoperta; distinta dalla scadenza legale",
            "updated_at": now_iso,
        }
        await db["verbali_noleggio"].update_one(
            query, {"$set": {k: v for k, v in values.items() if v not in (None, "")},
                    "$setOnInsert": {"created_at": now_iso}}, upsert=True,
        )
        for offset, kind in ((0, "scoperta"), (3, "promemoria_3_giorni"), (4, "promemoria_1_giorno"), (5, "scadenza")):
            notification_id = f"{record_id}:{kind}:{now.date().isoformat()}"
            await db["notification_log"].update_one(
                {"id": notification_id},
                {"$setOnInsert": {"id": notification_id, "tipo": "verbale", "verbale_id": record_id,
                                  "evento": kind, "scheduled_for": (now + timedelta(days=offset)).isoformat(),
                                  "status": "pending", "created_at": now_iso}}, upsert=True,
            )
        result["inserted_or_updated"] += 1
    return result


async def dispatch_due_verbali_notifications(db) -> Dict[str, Any]:
    """Invia una sola volta i promemoria maturati; conserva sempre il log."""
    now = datetime.now(timezone.utc)
    due = await db["notification_log"].find({
        "tipo": "verbale", "status": "pending", "scheduled_for": {"$lte": now.isoformat()},
    }, {"_id": 0}).limit(200).to_list(200)
    sent = failed = 0
    for item in due:
        verbale = await db["verbali_noleggio"].find_one({"id": item.get("verbale_id")}, {"_id": 0})
        number = (verbale or {}).get("numero_verbale") or item.get("verbale_id")
        message = f"Verbale {number}: {item.get('evento')}. Verifica scadenza, driver e pagamento nel gestionale."
        channels = []
        try:
            from app.services.websocket_manager import notify_data_change
            await notify_data_change("verbali_scan", {"verbale_id": item.get("verbale_id"),
                                                     "evento": item.get("evento"), "message": message},
                                     "notifications")
            channels.append("websocket")
        except Exception:
            pass
        try:
            from app.services.telegram_notifications import is_configured, send_notification
            if is_configured() and await send_notification(message):
                channels.append("telegram")
        except Exception:
            pass
        status = "sent" if channels else "failed_no_channel"
        await db["notification_log"].update_one(
            {"id": item["id"]}, {"$set": {"status": status, "channels": channels,
                                             "attempted_at": now.isoformat()}},
        )
        if channels:
            sent += 1
        else:
            failed += 1
    return {"due": len(due), "sent": sent, "failed": failed}
