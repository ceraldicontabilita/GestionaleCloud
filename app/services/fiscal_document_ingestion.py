"""Pipeline unica per documenti fiscali provenienti da Documenti o Drive."""

from __future__ import annotations

import base64
import io
from typing import Any

import fitz

from app.config import settings
from app.db_collections import (
    COLL_DOCUMENTS_INBOX,
    COLL_FISCAL_DOCUMENTS,
    COLL_FISCAL_DOCUMENT_VERSIONS,
    COLL_FISCAL_EVIDENCE,
    COLL_FISCAL_PAGES,
)
from app.services.fiscal_domain import build_evidence, classify_document, sha256_bytes, stable_id, utc_now
from app.services.fiscal_evidence import register_document


MAX_EXTRACTED_PAGE_CHARS = 40_000


def extract_pdf_pages(content: bytes) -> list[dict[str, Any]]:
    try:
        pdf = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise ValueError("PDF non leggibile") from exc
    pages = []
    for index, page in enumerate(pdf):
        text = page.get_text("text")[:MAX_EXTRACTED_PAGE_CHARS]
        pages.append({
            "page_number": index + 1,
            "text": text,
            "requires_ocr": len(text.strip()) < 20,
        })
    pdf.close()
    return pages


class FiscalDocumentIngestionService:
    """Acquisizione idempotente; non crea obblighi o pagamenti per inferenza."""

    PARSER_VERSION = "fiscal-ingestion-v1"

    def __init__(self, db, company_id: str | None = None):
        self.db = db
        self.company_id = company_id or settings.FISCAL_COMPANY_ID
        if not self.company_id:
            raise ValueError("company_id fiscale obbligatorio")

    async def ingest(
        self,
        *,
        content: bytes,
        filename: str,
        source: str,
        source_metadata: dict[str, Any] | None = None,
        expected_sha256: str | None = None,
        category_hint: str | None = None,
    ) -> dict[str, Any]:
        if not content:
            raise ValueError("Documento vuoto")
        digest = sha256_bytes(content)
        if expected_sha256 and digest.lower() != expected_sha256.lower():
            raise ValueError("SHA-256 non coincide con il manifest")

        existing_version = await self.db[COLL_FISCAL_DOCUMENT_VERSIONS].find_one(
            {"company_id": self.company_id, "sha256": digest}, {"_id": 0}
        )
        if existing_version:
            return {
                "status": "duplicate",
                "document_id": existing_version["document_id"],
                "version_id": existing_version["id"],
                "sha256": digest,
            }

        if not filename.lower().endswith(".pdf"):
            raise ValueError("La pipeline fiscale accetta al momento solo PDF")
        pages = extract_pdf_pages(content)
        full_text = "\n".join(page["text"] for page in pages)
        classification = classify_document(filename, full_text)
        source_metadata = dict(source_metadata or {})
        source_key = source_metadata.get("drive_file_id") or digest
        registered = await register_document(
            self.db,
            company_id=self.company_id,
            content=content,
            filename=filename,
            source=source,
            source_ref=str(source_key),
            category=category_hint or classification["document_type"],
            page_count=len(pages),
            metadata=source_metadata,
        )
        if registered.get("duplicate"):
            return {
                "status": "duplicate",
                "document_id": registered["document_id"],
                "version_id": registered["id"],
                "sha256": digest,
            }
        document_id = registered["document_id"]
        version_id = registered["id"]
        now = utc_now()

        document = {
            "id": document_id,
            "company_id": self.company_id,
            "filename": filename,
            "document_type": classification["document_type"],
            "classification": classification,
            "current_version_id": version_id,
            "source": source,
            "source_metadata": source_metadata,
            "updated_at": now,
            "created_at": now,
            "review_status": "TO_VERIFY" if classification["requires_review"] else "CLASSIFIED",
        }
        await self.db[COLL_FISCAL_DOCUMENTS].update_one(
            {"company_id": self.company_id, "id": document_id},
            {"$set": document, "$setOnInsert": {"first_seen_at": now}},
            upsert=True,
        )

        for page in pages:
            page_id = stable_id("fiscal_page", version_id, page["page_number"])
            await self.db[COLL_FISCAL_PAGES].update_one(
                {"company_id": self.company_id, "version_id": version_id, "page_number": page["page_number"]},
                {"$set": {"id": page_id, "company_id": self.company_id, "document_id": document_id,
                           "version_id": version_id, **page, "updated_at": now}},
                upsert=True,
            )
        evidence = build_evidence(
            document_id=document_id,
            version_id=version_id,
            page_number=1,
            field_name="document_type",
            raw_value=classification["reasons"],
            normalized_value=classification["document_type"],
            parser_version=self.PARSER_VERSION,
            confidence=classification["confidence"],
            reason="classificazione_deterministica",
        )
        evidence["company_id"] = self.company_id
        await self.db[COLL_FISCAL_EVIDENCE].insert_one(evidence)

        # Documenti resta l'unico archivio di ingresso e l'unico proprietario
        # del payload. Il registro fiscale conserva solo metadati/versioni.
        inbox_id = stable_id("document", self.company_id, digest)
        await self.db[COLL_DOCUMENTS_INBOX].update_one(
            {"company_id": self.company_id, "sha256": digest},
            {"$setOnInsert": {
                "id": inbox_id,
                "company_id": self.company_id,
                "filename": filename,
                "pdf_data": base64.b64encode(content).decode("ascii"),
                "file_hash": digest,
                "hash_algorithm": "sha256",
                "sha256": digest,
                "file_size": len(content),
                "category": category_hint or "fiscale",
                "category_label": classification["document_type"],
                "status": "processato",
                "processed": True,
                "processed_to": "fiscal_documents",
                "fiscal_document_id": document_id,
                "fiscal_version_id": version_id,
                "source": source,
                "source_metadata": source_metadata,
                "created_at": now,
            }},
            upsert=True,
        )
        return {
            "status": "inserted",
            "document_id": document_id,
            "version_id": version_id,
            "inbox_id": inbox_id,
            "sha256": digest,
            "pages": len(pages),
            "classification": classification,
        }

    async def mark_source_deleted(self, drive_file_id: str, deleted_at: str | None = None) -> int:
        result = await self.db[COLL_FISCAL_DOCUMENTS].update_many(
            {"company_id": self.company_id, "source_metadata.drive_file_id": drive_file_id},
            {"$set": {"source_deleted_at": deleted_at or utc_now(), "updated_at": utc_now()}},
        )
        return result.modified_count


def download_drive_file(service, file_id: str) -> bytes:
    from googleapiclient.http import MediaIoBaseDownload

    output = io.BytesIO()
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    downloader = MediaIoBaseDownload(output, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return output.getvalue()
