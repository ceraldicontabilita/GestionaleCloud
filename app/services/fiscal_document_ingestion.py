"""Pipeline unica per documenti fiscali provenienti da Documenti o Drive."""

from __future__ import annotations

import base64
import io
import re
from functools import lru_cache
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

CATEGORY_DOCUMENT_TYPES = {
    "dichiarazione_iva": "DICHIARAZIONE_IVA",
    "lipe": "LIPE",
    "modello_770": "MODELLO_770",
    "redditi_sc": "REDDITI_SC",
    "dichiarazione_irap": "DICHIARAZIONE_IRAP",
    "elenco_percipienti": "ELENCO_PERCIPIENTI",
}


@lru_cache(maxsize=1)
def _ocr_engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def _layout_word(box, text: str) -> dict[str, Any]:
    return {
        "x0": round(float(box[0]), 2),
        "y0": round(float(box[1]), 2),
        "x1": round(float(box[2]), 2),
        "y1": round(float(box[3]), 2),
        "text": str(text),
    }


def _looks_like_lipe_module(text: str) -> bool:
    normalized = str(text or "").upper()
    return all(field in normalized for field in ("VP1", "VP4", "VP14"))


def _ocr_page(page) -> tuple[str, float | None, list[dict[str, Any]]]:
    """OCR locale della singola pagina, senza inviare il documento a terzi."""
    import numpy as np
    from PIL import Image

    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    image = np.array(Image.open(io.BytesIO(pixmap.tobytes("png"))))
    result, _ = _ocr_engine()(image)
    rows = [item for item in (result or []) if len(item) >= 3 and str(item[1]).strip()]
    text = "\n".join(str(item[1]).strip() for item in rows)
    scores = [float(item[2]) for item in rows if item[2] is not None]
    layout_words = []
    for box, row_text, *_rest in rows:
        xs = [point[0] / 2 for point in box]
        ys = [point[1] / 2 for point in box]
        layout_words.append(_layout_word((min(xs), min(ys), max(xs), max(ys)), row_text))
    return text, (sum(scores) / len(scores) if scores else None), layout_words


def extract_pdf_pages(content: bytes, *, use_ocr: bool = True) -> list[dict[str, Any]]:
    try:
        pdf = fitz.open(stream=content, filetype="pdf")
    except Exception as exc:
        raise ValueError("PDF non leggibile") from exc
    pages = []
    for index, page in enumerate(pdf):
        text = page.get_text("text")[:MAX_EXTRACTED_PAGE_CHARS]
        layout_words = [
            _layout_word(word[:4], word[4])
            for word in page.get_text("words")
            if str(word[4]).strip()
        ]
        ocr_used = False
        ocr_confidence = None
        if use_ocr and len(text.strip()) < 20:
            try:
                ocr_text, ocr_confidence, ocr_words = _ocr_page(page)
                if ocr_text.strip():
                    text = ocr_text[:MAX_EXTRACTED_PAGE_CHARS]
                    layout_words = ocr_words
                    ocr_used = True
            except Exception:
                # Il documento resta in revisione: nessun fallimento OCR può
                # trasformarsi in un dato fiscale certo o bloccare l'import.
                pass
        pages.append({
            "page_number": index + 1,
            "text": text,
            "text_source": "rapidocr_locale" if ocr_used else "pdf_text",
            "ocr_used": ocr_used,
            "ocr_confidence": ocr_confidence,
            # Le coordinate servono al quadro VP; non gonfiano le righe Sheets
            # degli altri documenti fiscali.
            "layout_words": layout_words if _looks_like_lipe_module(text) else [],
            "requires_ocr": len(text.strip()) < 20,
        })
    pdf.close()
    return pages


class FiscalDocumentIngestionService:
    """Acquisizione idempotente; non crea obblighi o pagamenti per inferenza."""

    PARSER_VERSION = "fiscal-ingestion-v2-ocr"

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
            pages = await self.db[COLL_FISCAL_PAGES].find(
                {"company_id": self.company_id, "version_id": existing_version["id"]},
                {"_id": 0},
            ).to_list(1000)
            refreshed = False
            if not pages or any(
                page.get("requires_ocr")
                or len(str(page.get("text") or "").strip()) < 20
                or (
                    _looks_like_lipe_module(page.get("text") or "")
                    and not page.get("layout_words")
                )
                for page in pages
            ):
                now = utc_now()
                for page in extract_pdf_pages(content):
                    page_id = stable_id("fiscal_page", existing_version["id"], page["page_number"])
                    await self.db[COLL_FISCAL_PAGES].update_one(
                        {"company_id": self.company_id, "version_id": existing_version["id"],
                         "page_number": page["page_number"]},
                        {"$set": {"id": page_id, "company_id": self.company_id,
                                  "document_id": existing_version["document_id"],
                                  "version_id": existing_version["id"], **page,
                                  "updated_at": now}},
                        upsert=True,
                    )
                refreshed = True
            source_metadata = dict(source_metadata or {})
            if source_metadata.get("drive_document_id") or source_metadata.get("drive_file_id"):
                inbox_id = stable_id("document", self.company_id, digest)
                await self.db[COLL_DOCUMENTS_INBOX].update_one(
                    {"company_id": self.company_id, "sha256": digest},
                    {"$setOnInsert": {
                        "id": inbox_id,
                        "company_id": self.company_id,
                        "filename": filename,
                        "file_hash": digest,
                        "hash_algorithm": "sha256",
                        "sha256": digest,
                        "file_size": len(content),
                        "category": category_hint or "fiscale",
                        "status": "processato",
                        "processed": True,
                        "processed_to": "fiscal_documents",
                        "fiscal_document_id": existing_version["document_id"],
                        "fiscal_version_id": existing_version["id"],
                        "source": source,
                        "created_at": utc_now(),
                    }, "$set": {
                        "fiscal_document_id": existing_version["document_id"],
                        "fiscal_version_id": existing_version["id"],
                        "processed": True,
                        "processed_to": "fiscal_documents",
                        "drive_document_id": source_metadata.get("drive_document_id"),
                        "drive_file_id": source_metadata.get("drive_file_id"),
                        "drive_path": source_metadata.get("drive_path"),
                        "source_metadata": source_metadata,
                    }, "$unset": {"pdf_data": ""}},
                    upsert=True,
                )
            return {
                "status": "duplicate",
                "document_id": existing_version["document_id"],
                "version_id": existing_version["id"],
                "sha256": digest,
                "derived_text_refreshed": refreshed,
            }

        if not filename.lower().endswith(".pdf"):
            raise ValueError("La pipeline fiscale accetta al momento solo PDF")
        pages = extract_pdf_pages(content)
        full_text = "\n".join(page["text"] for page in pages)
        classification = classify_document(filename, full_text)
        if category_hint in CATEGORY_DOCUMENT_TYPES:
            classification = {
                "document_type": CATEGORY_DOCUMENT_TYPES[category_hint],
                "confidence": 1.0,
                "reasons": [f"categoria_manuale:{category_hint}"],
                "requires_review": False,
            }
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
        drive_backed = bool(
            source_metadata.get("drive_document_id") or source_metadata.get("drive_file_id")
        )
        inbox_record = {
            "id": inbox_id,
            "company_id": self.company_id,
            "filename": filename,
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
            "drive_document_id": source_metadata.get("drive_document_id"),
            "drive_file_id": source_metadata.get("drive_file_id"),
            "drive_path": source_metadata.get("drive_path"),
            "source": source,
            "source_metadata": source_metadata,
            "created_at": now,
        }
        if not drive_backed:
            inbox_record["pdf_data"] = base64.b64encode(content).decode("ascii")
        inbox_update: dict[str, Any] = {"$setOnInsert": inbox_record}
        if drive_backed:
            inbox_update["$set"] = {
                "drive_document_id": source_metadata.get("drive_document_id"),
                "drive_file_id": source_metadata.get("drive_file_id"),
                "drive_path": source_metadata.get("drive_path"),
                "source_metadata": source_metadata,
            }
            inbox_update["$unset"] = {"pdf_data": ""}
        await self.db[COLL_DOCUMENTS_INBOX].update_one(
            {"company_id": self.company_id, "sha256": digest}, inbox_update, upsert=True,
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
