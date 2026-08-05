"""Classificazione e collegamento conservativo dei PDF Verbali/PagoPA da Drive."""
from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.services.payment_invoice_matching import amounts_equal_to_cent


_IUV_RE = re.compile(r"\b([03]\d{17})\b")
_TARGA_RE = re.compile(r"\b([A-Z]{2}\d{3}[A-Z]{2})\b", re.IGNORECASE)
_VERBALE_PATTERNS = (
    re.compile(r"(?:numero|n[.°º]?|nr[.]?)?\s*verbale\s*[:#-]?\s*([A-Z0-9/-]{6,30})", re.I),
    re.compile(r"\b([A-Z]\d{8,14})\b", re.I),
)
_RICEVUTA_MARKERS = (
    "ricevuta di pagamento", "pagamento eseguito", "pagamento effettuato",
    "esito del pagamento", "quietanza", "data del pagamento",
)


def _extract_text(content: bytes) -> str:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(content)) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def _extract_numero(text: str) -> Optional[str]:
    for pattern in _VERBALE_PATTERNS:
        match = pattern.search(text or "")
        if match:
            value = match.group(1).strip(" .:-").upper()
            if value and value not in {"NUMERO", "VERBALE"}:
                return value
    return None


def _extract_amount(text: str) -> Optional[float]:
    patterns = (
        r"(?:totale|importo\s+pagato|da\s+pagare)\s*[:€]*\s*([\d.]+,\d{2})",
        r"€\s*([\d.]+,\d{2})",
    )
    for pattern in patterns:
        match = re.search(pattern, text or "", re.I)
        if not match:
            continue
        try:
            return float(match.group(1).replace(".", "").replace(",", "."))
        except ValueError:
            continue
    return None


def _extract_payment_date(text: str) -> Optional[str]:
    match = re.search(
        r"(?:data\s+(?:del\s+)?pagamento|pagato\s+il)\s*:?\s*(\d{2}[/-]\d{2}[/-]\d{4})",
        text or "",
        re.I,
    )
    if not match:
        return None
    raw = match.group(1).replace("-", "/")
    day, month, year = raw.split("/")
    return f"{year}-{month}-{day}"


async def _vehicle_context(db, targa: Optional[str]) -> Dict[str, Any]:
    if not targa:
        return {}
    vehicle = await db["veicoli_noleggio"].find_one(
        {"targa": {"$regex": f"^{re.escape(targa)}$", "$options": "i"}},
        {"_id": 0},
    )
    if not vehicle:
        return {}
    return {
        "veicolo_id": vehicle.get("id"),
        "driver_id": vehicle.get("driver_id"),
        "driver": vehicle.get("driver") or vehicle.get("driver_nome"),
        "contratto": vehicle.get("contratto"),
        "fornitore_noleggio": vehicle.get("fornitore_noleggio"),
    }


async def process_verbale_document(
    db,
    *,
    document_id: str,
    content: bytes,
    filename: str,
    source: str = "drive_verbale",
) -> Dict[str, Any]:
    """Conserva relazioni certe; senza numero/IUV lascia il PDF da rivedere."""
    sha256 = hashlib.sha256(content).hexdigest()
    try:
        text = _extract_text(content)
    except Exception as exc:
        await db["documents_inbox"].update_one(
            {"id": document_id},
            {"$set": {"status": "errore", "processed": False, "processing_error": str(exc)}},
        )
        return {"status": "error", "error": str(exc)}

    combined = f"{filename}\n{text}"
    numero = _extract_numero(combined)
    iuv_match = _IUV_RE.search(combined)
    targa_match = _TARGA_RE.search(combined)
    iuv = iuv_match.group(1) if iuv_match else None
    targa = targa_match.group(1).upper() if targa_match else None
    importo = _extract_amount(text)
    data_pagamento = _extract_payment_date(text)
    is_receipt = any(marker in combined.casefold() for marker in _RICEVUTA_MARKERS)
    now = datetime.now(timezone.utc).isoformat()

    extracted = {
        "numero_verbale_estratto": numero,
        "iuv_estratto": iuv,
        "targa_estratta": targa,
        "importo_estratto": importo,
        "document_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "updated_at": now,
    }

    if is_receipt:
        receipt_id = f"pagopa_{sha256[:32]}"
        receipt = {
            "id": receipt_id,
            "source_document_id": document_id,
            "source_sha256": sha256,
            "filename": filename,
            "numero_verbale": numero,
            "iuv": iuv,
            "targa": targa,
            "importo": importo,
            "data_pagamento": data_pagamento,
            "source": source,
            "stato": "non_associata",
            "updated_at": now,
        }
        await db["ricevute_pagopa"].update_one(
            {"id": receipt_id},
            {"$set": receipt, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        candidates = []
        references = []
        if numero:
            references.append({"numero_verbale": numero})
        if iuv:
            references.append({"iuv": iuv})
        if references and importo:
            candidates = await db["verbali_noleggio"].find(
                {"$or": references}, {"_id": 0}
            ).limit(20).to_list(20)
            candidates = [
                item for item in candidates
                if amounts_equal_to_cent(item.get("importo"), importo)
            ]
        linked_verbale = None
        if len(candidates) == 1:
            from app.services.verbali_pagamento_finder import applica_pagamento_a_verbale

            candidate = candidates[0]
            linked_verbale = candidate.get("id") or candidate.get("numero_verbale")
            applied = await applica_pagamento_a_verbale(db, linked_verbale, {
                "fonte": "gmail" if source.startswith("email") else "drive_pagopa",
                "psp": "PagoPA",
                "importo": importo,
                "data_pagamento": data_pagamento,
                "metodo_pagamento": "PagoPA",
                "ricevuta_pagopa_id": receipt_id,
                "iuv_usato": iuv,
            })
            if applied:
                await db["ricevute_pagopa"].update_one(
                    {"id": receipt_id},
                    {"$set": {"stato": "associata", "verbale_id": linked_verbale}},
                )
        await db["documents_inbox"].update_one(
            {"id": document_id},
            {"$set": {
                **extracted,
                "tipo_documento": "ricevuta_pagopa",
                "categoria": "ricevuta_pagopa",
                "category": "ricevuta_pagopa",
                "ricevuta_pagopa_id": receipt_id,
                "verbale_id": linked_verbale,
                "processed": bool(linked_verbale),
                "status": "processato" if linked_verbale else "da_revisionare",
            }},
        )
        return {
            "status": "linked" if linked_verbale else "review",
            "tipo": "ricevuta_pagopa",
            "receipt_id": receipt_id,
            "verbale_id": linked_verbale,
        }

    if not numero and not iuv:
        await db["documents_inbox"].update_one(
            {"id": document_id},
            {"$set": {**extracted, "processed": False, "status": "da_revisionare"}},
        )
        return {"status": "review", "tipo": "verbale", "reason": "numero_e_iuv_assenti"}

    identity = {"numero_verbale": numero} if numero else {"iuv": iuv}
    existing = await db["verbali_noleggio"].find_one(identity, {"_id": 0})
    verbale_id = str((existing or {}).get("id") or f"verbale_{hashlib.sha256(str(identity).encode()).hexdigest()[:32]}")
    vehicle = await _vehicle_context(db, targa)
    values = {
        "id": verbale_id,
        "numero_verbale": numero,
        "iuv": iuv,
        "targa": targa,
        "importo": importo,
        "source_document_id": document_id,
        "source_sha256": sha256,
        "source": source,
        "stato": (existing or {}).get("stato") or "salvato",
        "updated_at": now,
        **vehicle,
    }
    if existing:
        values = {
            key: value for key, value in values.items()
            if value not in (None, "") and (existing.get(key) in (None, "") or key in {
                "source_document_id", "source_sha256", "updated_at"
            })
        }
    verbale_query = (
        {"id": existing.get("id")}
        if existing and existing.get("id")
        else identity if existing
        else {"id": verbale_id}
    )
    await db["verbali_noleggio"].update_one(
        verbale_query,
        {
            "$set": values,
            "$setOnInsert": {"created_at": now},
            "$addToSet": {"document_ids": document_id},
        },
        upsert=True,
    )
    await db["documents_inbox"].update_one(
        {"id": document_id},
        {"$set": {
            **extracted,
            "verbale_id": verbale_id,
            "processed": True,
            "status": "processato",
        }},
    )
    return {"status": "linked", "tipo": "verbale", "verbale_id": verbale_id}
