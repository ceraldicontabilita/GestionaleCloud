"""Import canonico e parsing conservativo delle ricevute PagoPA/CBILL."""
from __future__ import annotations

import base64
import hashlib
import inspect
import io
import re
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any

from app.services.payment_invoice_matching import amounts_equal_to_cent


COLLECTION_RICEVUTE = "ricevute_pagopa"


@lru_cache(maxsize=1)
def _get_ocr_engine():
    from rapidocr_onnxruntime import RapidOCR

    return RapidOCR()


def _extract_receipt_text(content: bytes) -> tuple[str, bool]:
    """Estrae il testo e usa OCR locale solo per le attestazioni raster."""
    text = ""
    try:
        from pypdf import PdfReader

        text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)
    except Exception:
        pass
    upper_native = re.sub(r"\s+", " ", text).upper()
    native_notice = any(marker in upper_native for marker in (
        "AVVISO DI PAGAMENTO", "QUANTO E QUANDO PAGARE", "RATA UNICA ENTRO IL",
    ))
    native_notice_has_code = bool(re.search(r"3(?:\s*\d){17}", text))
    if len(text.strip()) >= 150 and (not native_notice or native_notice_has_code):
        return text, False

    # Alcuni avvisi hanno un albero strutturale PDF difettoso: pypdf legge le
    # etichette ma perde proprio valori, QR e codici. PyMuPDF riesce spesso a
    # recuperare il testo vettoriale, evitando un OCR costoso e meno preciso.
    try:
        import fitz
        with fitz.open(stream=content, filetype="pdf") as document:
            fitz_text = "\n".join(page.get_text() or "" for page in document)
        fitz_upper = re.sub(r"\s+", " ", fitz_text).upper()
        fitz_notice = any(marker in fitz_upper for marker in (
            "AVVISO DI PAGAMENTO", "QUANTO E QUANDO PAGARE", "RATA UNICA ENTRO IL",
        ))
        fitz_notice_has_code = bool(re.search(r"3(?:\s*\d){17}", fitz_text))
        if len(fitz_text.strip()) >= 150 and (not fitz_notice or fitz_notice_has_code):
            return fitz_text, False
        if len(fitz_text.strip()) > len(text.strip()):
            text = fitz_text
    except Exception:
        pass

    try:
        import fitz
        import numpy as np
        from PIL import Image
        engine = _get_ocr_engine()
        lines: list[str] = []
        with fitz.open(stream=content, filetype="pdf") as document:
            for page in document:
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = np.array(Image.open(io.BytesIO(pixmap.tobytes("png"))))
                result, _ = engine(image)
                lines.extend(item[1] for item in (result or []) if item[1].strip())
        if lines:
            return "\n".join(lines), True
    except Exception:
        # Senza dati leggibili la ricevuta resta da verificare e non produce
        # mai automaticamente uno stato PAGATO o CHIUSO.
        pass
    return text, False


def parse_receipt_pdf(content: bytes, filename: str | None = None) -> dict[str, Any]:
    text, ocr_used = _extract_receipt_text(content)
    compact = re.sub(r"\s+", " ", text)
    upper = compact.upper()
    marker_text = re.sub(r"[^A-Z0-9]", "", upper)
    is_notice = any(marker in marker_text for marker in (
        "AVVISODIPAGAMENTO", "QUANTOEQUANDOPAGARE", "RATAUNICAENTROIL",
    ))
    is_receipt = any(marker in marker_text for marker in (
        "ATTESTAZIONEDIPAGAMENTO", "PAGAMENTOESEGUITO",
        "IMPORTOTOTALEPAGATO", "RICEVUTATELEMATICA",
    ))
    is_negative_outcome = any(marker in marker_text for marker in (
        "PAGAMENTONONESEGUITO", "PAGAMENTORIFIUTATO",
        "PAGAMENTOANNULLATO", "ESITONEGATIVO",
    ))
    code = None
    code_source = f"{compact} {filename or ''}"
    for pattern in (
        r"(?:identificativo\s+(?:univoco\s+)?(?:versamento|bolletta)|id\s+univoco\s+versamento|IUV|CBILL)\s*[:#-]?\s*(\d{15,20})",
        r"\b(3(?:\s*\d){17})\b",
        r"\b([03]\d{16,17})\b",
    ):
        match = re.search(pattern, code_source, re.IGNORECASE)
        if match:
            code = re.sub(r"\s+", "", match.group(1))
            break
    notice_code = code if code and len(code) == 18 and code.startswith("3") else None
    normalized_iuv = code[1:] if notice_code else code
    amount = None
    amount_match = re.search(
        r"(?:importo\s+totale\s+pagato|importo\s+(?:pagato|versato|totale)|totale)\s*[:€EUR ]*([\d.]+,\d{2})",
        compact, re.IGNORECASE,
    )
    if amount_match:
        amount = float(amount_match.group(1).replace(".", "").replace(",", "."))
    if amount is None and is_notice:
        notice_amount = re.search(
            r"(?:importo\s+(?:totale\s+)?da\s+pagare|rata\s+unica)\s*[:€EUR ]*([\d.]+,\d{2})",
            compact, re.IGNORECASE,
        )
        if notice_amount:
            amount = float(notice_amount.group(1).replace(".", "").replace(",", "."))
        else:
            unique_amounts = {
                match.replace(".", "")
                for match in re.findall(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b", compact)
            }
            if len(unique_amounts) == 1:
                amount = float(next(iter(unique_amounts)).replace(",", "."))
    payment_date = None
    date_match = re.search(
        r"(?:data\s+(?:del\s+)?pagamento|pagato\s+il|data\s+ricevuta)\s*:?\s*(\d{2}/\d{2}/\d{4})",
        compact, re.IGNORECASE,
    )
    if date_match:
        day, month, year = date_match.group(1).split("/")
        payment_date = f"{year}-{month}-{day}"
    targa_match = re.search(r"\bTARGA\s*:\s*([A-Z]{2}\d{3}[A-Z]{2})\b", compact, re.IGNORECASE)
    verbale_match = re.search(
        r"\bVERBALE\s+N[.°º]?\s*:\s*([A-Z0-9/-]{6,30})",
        compact, re.IGNORECASE,
    )
    violation_date_match = re.search(
        r"\bTARGA\s*:\s*[A-Z]{2}\d{3}[A-Z]{2}\s*-\s*DATA\s*:\s*(\d{2}/\d{2}/\d{2,4})",
        compact, re.IGNORECASE,
    )
    violation_date = None
    if violation_date_match:
        day, month, year = violation_date_match.group(1).split("/")
        if len(year) == 2:
            year = f"20{year}"
        violation_date = f"{year}-{month}-{day}"
    beneficiary_match = re.search(
        r"ENTE\s+BENEFICIARIO.*?DENOMINAZIONE\s*:\s*(.+?)\s+(?:TIPO|ANAGRAFICA)\s*:",
        compact, re.IGNORECASE,
    )
    detected_dates = []
    for day, month, year in re.findall(r"\b([0-3]\d)/([01]\d)/(20\d{2})\b", compact):
        try:
            detected_dates.append(datetime(int(year), int(month), int(day)).date().isoformat())
        except ValueError:
            continue
    due_candidates = [value for value in detected_dates if value != violation_date]
    data_scadenza = max(due_candidates) if is_notice and due_candidates else None
    cbill_candidates = [
        value.upper()
        for value in re.findall(r"(?m)^\s*([A-Z0-9]{5})\s*$", text, re.IGNORECASE)
        if re.search(r"[A-Z]", value, re.IGNORECASE) and re.search(r"\d", value)
    ]
    codici_fiscali = list(dict.fromkeys(re.findall(r"(?m)^\s*(\d{11})\s*$", text)))
    return {
        "identificativo_bolletta": normalized_iuv,
        "codice_avviso": notice_code,
        "importo": amount,
        "data_pagamento": payment_date,
        "targa": targa_match.group(1).upper() if targa_match else None,
        "numero_verbale": verbale_match.group(1).upper().rstrip("-") if verbale_match else None,
        "data_violazione": violation_date,
        "beneficiario": beneficiary_match.group(1).strip() if beneficiary_match else None,
        "data_scadenza": data_scadenza,
        "codice_cbill": cbill_candidates[0] if cbill_candidates else None,
        "codici_fiscali_rilevati": codici_fiscali,
        "text_detected": bool(text.strip()),
        "ocr_used": ocr_used,
        "document_kind": (
            "ESITO_PAGOPA_NEGATIVO" if is_negative_outcome
            else "AVVISO_PAGOPA" if is_notice and not is_receipt
            else "RICEVUTA_PAGOPA"
        ),
        "is_payment_receipt": bool(is_receipt and not is_notice and not is_negative_outcome),
    }


async def find_bank_movement(db, code: str, amount: Any):
    if not code or amount in (None, ""):
        return None
    movements = await db.estratto_conto_movimenti.find({
        "$or": [
            {"descrizione_originale": {"$regex": re.escape(code)}},
            {"descrizione": {"$regex": re.escape(code)}},
        ],
        "ricevuta_pagopa_id": {"$in": [None, ""]},
    }, {"_id": 0}).limit(20).to_list(20)
    exact = [item for item in movements if amounts_equal_to_cent(item.get("importo"), amount)]
    return exact[0] if len(exact) == 1 else None


async def _associate_receipt_to_verbale(
    db, *, receipt_id: str, parsed: dict[str, Any], amount: Any,
) -> dict[str, Any]:
    """Collega solo identita' documentale esatta e importo al centesimo."""
    iuv = str(parsed.get("identificativo_bolletta") or "").strip()
    numero = str(parsed.get("numero_verbale") or "").strip().upper()
    references = []
    if iuv:
        references.extend(({"iuv": iuv}, {"codice_avviso": f"3{iuv}"}))
    if numero:
        references.append({"numero_verbale": numero})
    if not references or amount in (None, ""):
        return {"matched": False, "reason": "riferimenti_o_importo_assenti"}

    found = await db["verbali_noleggio"].find(
        {"$or": references}, {"_id": 0},
    ).limit(20).to_list(20)
    candidates: dict[str, dict[str, Any]] = {}
    for item in found:
        if not amounts_equal_to_cent(item.get("importo"), amount):
            continue
        key = str(item.get("id") or item.get("numero_verbale") or item.get("iuv"))
        candidates[key] = item
    if len(candidates) > 1:
        return {"matched": False, "reason": "candidati_ambigui", "candidate_count": len(candidates)}

    created = False
    if candidates:
        verbale = next(iter(candidates.values()))
    elif numero and iuv:
        now = datetime.now(timezone.utc).isoformat()
        verbale_id = f"verbale_{hashlib.sha256(f'{numero}:{iuv}'.encode()).hexdigest()[:32]}"
        verbale = {
            "id": verbale_id, "numero_verbale": numero, "iuv": iuv,
            "targa": parsed.get("targa"), "importo": float(amount),
            "data_violazione": parsed.get("data_violazione"),
            "source": "ricevuta_pagopa", "stato": "salvato",
            "created_at": now, "updated_at": now,
        }
        await db["verbali_noleggio"].update_one(
            {"id": verbale_id}, {"$setOnInsert": verbale}, upsert=True,
        )
        created = True
    else:
        return {"matched": False, "reason": "verbale_non_trovato"}

    from app.services.verbali_pagamento_finder import applica_pagamento_a_verbale

    verbale_id = verbale.get("id") or verbale.get("numero_verbale")
    applied = await applica_pagamento_a_verbale(db, verbale_id, {
        "fonte": "ricevuta_pagopa",
        "psp": "PagoPA",
        "importo": float(amount),
        "data_pagamento": parsed.get("data_pagamento"),
        "metodo_pagamento": "PagoPA",
        "ricevuta_pagopa_id": receipt_id,
        "iuv_usato": iuv,
    })
    return {
        "matched": bool(applied), "verbale_id": verbale_id,
        "numero_verbale": numero or verbale.get("numero_verbale"),
        "created_from_receipt": created,
        "rule": "iuv_o_numero_verbale_e_importo_esatto",
    }


async def import_receipt(
    db, *, content: bytes, filename: str, company_id: str,
    source: str = "upload_manuale", overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Mantiene compatibilita con parser/plugin preesistenti che espongono la
    # vecchia firma a un solo argomento, senza rinunciare al filename quando
    # il parser corrente puo usarlo come evidenza secondaria.
    parser_parameters = inspect.signature(parse_receipt_pdf).parameters
    parsed = (
        parse_receipt_pdf(content, filename=filename)
        if "filename" in parser_parameters
        else parse_receipt_pdf(content)
    )
    if "is_payment_receipt" not in parsed:
        parsed["is_payment_receipt"] = bool(parsed.get("data_pagamento"))
    if not parsed.get("is_payment_receipt"):
        return {
            "success": False, "filename": filename,
            "error": "Il documento non contiene un esito di pagamento PagoPA/CBILL",
            "requires_review": True,
            "document_kind": parsed.get("document_kind"),
            "parsed": parsed,
        }
    values = {**parsed, **{key: value for key, value in (overrides or {}).items() if value not in (None, "")}}
    code = str(values.get("identificativo_bolletta") or "").strip()
    amount = values.get("importo")
    if not code or amount in (None, ""):
        return {
            "success": False, "filename": filename,
            "error": "Ricevuta PagoPA/CBILL senza IUV/codice bolletta e importo leggibili",
            "requires_review": True,
        }

    pdf_hash = hashlib.sha256(content).hexdigest()
    existing = await db[COLLECTION_RICEVUTE].find_one(
        {"pdf_hash": pdf_hash}, {"_id": 0},
    )
    if existing:
        return {"success": True, "duplicate": True, "receipt": existing,
                "riconciliazione_fiscale": existing.get("riconciliazione_fiscale")}

    receipt_id = str(uuid.uuid4())
    movement = await find_bank_movement(db, code, amount)
    now = datetime.now(timezone.utc).isoformat()
    receipt = {
        "id": receipt_id, "filename": filename, "content_type": "application/pdf",
        "size": len(content), "pdf_data": base64.b64encode(content).decode("utf-8"),
        "pdf_hash": pdf_hash, "importo": float(amount),
        "data_pagamento": values.get("data_pagamento"),
        "identificativo_bolletta": code,
        "numero_verbale": parsed.get("numero_verbale"),
        "targa": parsed.get("targa"),
        "data_violazione": parsed.get("data_violazione"),
        "beneficiario": values.get("beneficiario") or "ENTE CREDITORE PAGOPA DA VERIFICARE",
        "note": values.get("note"), "source": source,
        "movimento_id": movement.get("id") if movement else None,
        "associazione_automatica": bool(movement), "created_at": now,
        "versato_documentalmente": True,
        "banca_verificata": bool(movement),
    }
    if movement:
        receipt.update({"movimento_data": movement.get("data"),
                        "movimento_importo": movement.get("importo")})
        await db.estratto_conto_movimenti.update_one(
            {"id": movement["id"]}, {"$set": {
                "ricevuta_pagopa_id": receipt_id, "ricevuta_filename": filename,
                "updated_at": now,
            }},
        )
    await db[COLLECTION_RICEVUTE].insert_one(receipt.copy())

    verbale_match = await _associate_receipt_to_verbale(
        db, receipt_id=receipt_id, parsed=parsed, amount=amount,
    )
    if verbale_match.get("matched"):
        receipt["verbale_id"] = verbale_match.get("verbale_id")
        receipt["riconciliazione_verbale"] = verbale_match
        await db[COLLECTION_RICEVUTE].update_one(
            {"id": receipt_id}, {"$set": {
                "verbale_id": receipt["verbale_id"],
                "riconciliazione_verbale": verbale_match,
            }},
        )

    from app.services.fiscal_evidence import register_document
    from app.services.fiscal_payment_reconciliation import reconcile_fiscal_payment

    document = await register_document(
        db, company_id=company_id, content=content, filename=filename, source=source,
        source_ref=receipt_id, category="riscossione",
        metadata={"receipt_collection": COLLECTION_RICEVUTE},
    )
    fiscal_match = await reconcile_fiscal_payment(
        db, company_id=company_id,
        payment={**receipt, "amount": amount, "payment_date": receipt.get("data_pagamento")},
        source_type="RICEVUTA_CBILL" if "CBILL" in filename.upper() else "RICEVUTA_PAGOPA",
        source_id=receipt_id, document_id=document.get("document_id"), version_id=document.get("id"),
    )
    if fiscal_match.get("matched"):
        patch = {
            "fiscal_payment_id": fiscal_match["payment_id"],
            "fiscal_target_id": fiscal_match["target_id"],
            "fiscal_target_type": fiscal_match["target_type"],
            "cartelle_collegate": fiscal_match["linked_claim_ids"],
            "riconciliazione_fiscale": fiscal_match,
        }
        receipt.update(patch)
        await db[COLLECTION_RICEVUTE].update_one({"id": receipt_id}, {"$set": patch})
    return {"success": True, "duplicate": False, "receipt": receipt,
            "riconciliazione_fiscale": fiscal_match,
            "riconciliazione_verbale": verbale_match}
