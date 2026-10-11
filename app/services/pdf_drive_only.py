"""PDF originali su Drive, metadati soltanto in Supabase."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import re
from typing import Any, Iterable

from app.document_repository import DOCUMENT_PAYLOAD_FIELDS


def _pdf_bytes(value: Any) -> bytes | None:
    if not value:
        return None
    if isinstance(value, (bytes, bytearray)):
        content = bytes(value)
    elif isinstance(value, str):
        try:
            content = base64.b64decode(value, validate=False)
        except (ValueError, TypeError):
            return None
    else:
        return None
    # Non basta un prefisso isolato (alcuni test e vecchi placeholder usano
    # ``%PDF-2``): un originale deve avere anche il marcatore di chiusura.
    return content if content.startswith(b"%PDF-") and b"%%EOF" in content[-4096:] else None


def _filename(doc: dict[str, Any], field: str) -> str:
    candidate = next((doc.get(key) for key in (
        "filename", "file_name", "nome_file", "pdf_filename", "source_file"
    ) if doc.get(key)), None)
    safe = re.sub(r"[\\/\r\n]+", "-", str(candidate or f"{doc.get('_id', 'documento')}-{field}.pdf")).strip()
    return safe if safe.lower().endswith(".pdf") else safe + ".pdf"


def verified_drive_source(content: bytes, source: dict[str, Any] | None) -> dict[str, Any]:
    """Riusa un originale solo se l'impronta identifica questi byte.

    Il bridge puo' indicare lo ZIP contenitore: quell'id resta provenienza,
    ma non puo' diventare il PDF da aprire o scaricare.
    """
    metadata = dict(source or {})
    if not metadata.get("drive_file_id"):
        return metadata
    if metadata.get("archive_member"):
        metadata["archive_drive_file_id"] = metadata.pop("drive_file_id")
        metadata.pop("drive_md5", None)
        return metadata
    sha256 = hashlib.sha256(content).hexdigest()
    md5 = hashlib.md5(content, usedforsecurity=False).hexdigest()
    expected_sha = metadata.get("source_sha256")
    expected_md5 = metadata.get("drive_md5")
    if (expected_sha and expected_sha != sha256) or (expected_md5 and expected_md5 != md5):
        raise ValueError("L'impronta dell'originale Drive non corrisponde al documento ricevuto")
    if not expected_sha and not expected_md5:
        metadata["unverified_drive_file_id"] = metadata.pop("drive_file_id")
        return metadata
    metadata["drive_md5"] = md5
    return metadata


def _drive_ref(doc: dict[str, Any], field: str) -> dict[str, Any]:
    refs = doc.get("_drive_payloads") or {}
    ref = refs.get(field) if isinstance(refs, dict) else None
    if isinstance(ref, dict) and ref.get("drive_file_id"):
        return ref
    if field == "pdf_data" and doc.get("drive_file_id"):
        return {
            "drive_file_id": doc.get("drive_file_id"),
            "md5": doc.get("drive_md5") or doc.get("md5"),
        }
    return {}


async def externalize_documents(collection: str, documents: list[dict[str, Any]]) -> None:
    """Sposta i soli payload che sono davvero PDF e muta i record in-place.

    Se Drive non conferma il contenuto, la scrittura fallisce chiusa: il PDF
    non viene silenziosamente rimesso in Supabase.
    """
    fields = DOCUMENT_PAYLOAD_FIELDS.get(collection, ())
    if not fields:
        return
    from app.services.email_drive_archive import archive_binary_copy

    for doc in documents:
        for field in fields:
            content = _pdf_bytes(doc.get(field))
            if content is None:
                continue
            ref = _drive_ref(doc, field)
            if not ref and field == "pdf_data" and doc.get("source_context"):
                source = verified_drive_source(content, doc["source_context"])
                if source.get("drive_file_id"):
                    ref = {"drive_file_id": source["drive_file_id"], "md5": source["drive_md5"]}
            expected_md5 = hashlib.md5(content, usedforsecurity=False).hexdigest()
            if not ref.get("drive_file_id") or ref.get("md5") != expected_md5:
                result = await asyncio.to_thread(
                    archive_binary_copy,
                    content,
                    _filename(doc, field),
                    source=f"supabase:{collection}:{field}",
                    area=collection,
                )
                if result.get("status") not in {"archived", "duplicate"} or not result.get("drive_file_id"):
                    raise RuntimeError(
                        f"PDF non salvato su Drive ({collection}.{field}): "
                        f"{result.get('reason') or result.get('status')}"
                    )
                ref = result
            refs_raw = doc.get("_drive_payloads")
            refs = dict(refs_raw) if isinstance(refs_raw, dict) else {}
            refs[field] = {
                "drive_file_id": ref["drive_file_id"],
                "md5": ref.get("md5") or expected_md5,
                "sha256": ref.get("sha256") or hashlib.sha256(content).hexdigest(),
                "bytes": ref.get("bytes") or len(content),
            }
            doc["_drive_payloads"] = refs
            stato_raw = doc.get("_payload_stato")
            stato = dict(stato_raw) if isinstance(stato_raw, dict) else {}
            stato[field] = "pieno"
            doc["_payload_stato"] = stato
            if field == "pdf_data":
                doc["drive_file_id"] = ref["drive_file_id"]
                doc["drive_md5"] = refs[field]["md5"]
                doc["pdf_disponibile"] = True
            doc.pop(field, None)


async def hydrate_document(
    collection: str,
    doc: dict[str, Any],
    excluded_fields: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Ricostruisce in memoria i payload richiesti, senza riscriverli nel DB."""
    excluded = set(excluded_fields or ())
    fields = DOCUMENT_PAYLOAD_FIELDS.get(collection, ())
    if not fields:
        return doc
    from app.services.drive_download import scarica_originale

    for field in fields:
        if field in excluded or doc.get(field):
            continue
        ref = _drive_ref(doc, field)
        drive_id = ref.get("drive_file_id")
        if not drive_id:
            continue
        content = await scarica_originale(str(drive_id), md5=ref.get("md5"))
        if not content.startswith(b"%PDF"):
            continue
        expected_md5 = ref.get("md5")
        actual_md5 = hashlib.md5(content, usedforsecurity=False).hexdigest()
        if expected_md5 and actual_md5 != expected_md5:
            raise RuntimeError(f"PDF Drive non corrispondente ({collection}.{field})")
        doc[field] = base64.b64encode(content).decode("ascii")
    return doc


async def hydrate_documents(
    collection: str,
    documents: list[dict[str, Any]],
    excluded_fields: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    for doc in documents:
        await hydrate_document(collection, doc, excluded_fields)
    return documents
