"""Classificazione e collegamento conservativo dei PDF Verbali/PagoPA da Drive."""
from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from app.services.payment_invoice_matching import amounts_equal_to_cent


_IUV_RE = re.compile(r"\b(3\d{17}|0\d{16,17})\b")
_TARGA_RE = re.compile(r"\b([A-Z]{2}\d{3}[A-Z]{2})\b", re.IGNORECASE)
_VERBALE_PATTERNS = (
    re.compile(
        r"\bverbale\s+(?:n(?:r)?[.°º]?|numero)?\s*[:#-]?\s*"
        r"([A-Z]{0,3}[/-]?\d{6,20})\b",
        re.I,
    ),
    re.compile(r"(?:numero|n[.°º]?|nr[.]?)?\s*verbale\s*[:#-]?\s*([A-Z0-9/-]{6,30})", re.I),
    re.compile(r"\b([A-Z]\d{8,14})\b", re.I),
)
_RICEVUTA_MARKERS = (
    "ricevuta di pagamento", "pagamento eseguito", "pagamento effettuato",
    "importo totale pagato", "attestazione di pagamento",
)
_NEGATIVE_PAYMENT_MARKERS = (
    "pagamento non eseguito", "pagamento rifiutato", "pagamento annullato",
)


def _extract_text(content: bytes) -> str:
    text = ""
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception:
        pass
    # Gli avvisi PagoPA generati con structure tree non valido possono perdere
    # tutti i valori con pdfplumber pur restando PDF vettoriali leggibili.
    if len(text.strip()) < 120:
        try:
            import fitz
            with fitz.open(stream=content, filetype="pdf") as document:
                fitz_text = "\n".join(page.get_text() or "" for page in document)
            if len(fitz_text.strip()) > len(text.strip()):
                text = fitz_text
        except Exception:
            pass
    return text


def _extract_numero(text: str) -> Optional[str]:
    for pattern in _VERBALE_PATTERNS:
        match = pattern.search(text or "")
        if match:
            value = match.group(1).strip(" .:-").upper()
            if value and value not in {"NUMERO", "VERBALE"}:
                return value
    return None


def _normalizza_numero(value: Any) -> Optional[str]:
    numero = str(value or "").strip().upper()
    numero = re.sub(r"^VERBALE\s*(?:N(?:R)?[.°º]?|NUMERO)?\s*", "", numero)
    numero = numero.strip(" .:-")
    return numero or None


def _float_or_none(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, str):
            raw = value.strip().replace("€", "").replace(" ", "")
            if "," in raw:
                raw = raw.replace(".", "").replace(",", ".")
            return float(raw)
        return float(value)
    except (TypeError, ValueError):
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


async def _vehicle_context(
    db, targa: Optional[str], event_date: Optional[str] = None,
) -> Dict[str, Any]:
    if not targa:
        return {}
    vehicle = await db["veicoli_noleggio"].find_one(
        {"targa": {"$regex": f"^{re.escape(targa)}$", "$options": "i"}},
        {"_id": 0},
    )
    if not vehicle:
        return {}
    context = {
        "veicolo_id": vehicle.get("id"),
        "contratto": vehicle.get("contratto"),
        "fornitore_noleggio": vehicle.get("fornitore_noleggio"),
    }
    # La targa identifica il veicolo, non il conducente. Il driver viene
    # proposto solo da una assegnazione storica valida alla data del fatto.
    if not event_date:
        return context
    assignments = await db["storico_assegnazioni_veicoli"].find({
        "targa": {"$regex": f"^{re.escape(targa)}$", "$options": "i"},
        "data_inizio": {"$lte": event_date},
        "$or": [
            {"data_fine": {"$gte": event_date}},
            {"data_fine": {"$exists": False}},
            {"data_fine": None},
            {"data_fine": ""},
        ],
    }, {"_id": 0}).limit(10).to_list(10)
    candidates = {
        str(item.get("driver_id") or item.get("driver") or item.get("driver_nome")): item
        for item in assignments
        if item.get("driver_id") or item.get("driver") or item.get("driver_nome")
    }
    if len(candidates) == 1:
        assignment = next(iter(candidates.values()))
        context.update({
            "driver_id": assignment.get("driver_id"),
            "driver": assignment.get("driver") or assignment.get("driver_nome"),
            "driver_match_basis": "assegnazione_storica_alla_data",
        })
    elif len(candidates) > 1:
        context["driver_requires_review"] = True
    return context


def _extract_violation_date(text: str) -> Optional[str]:
    match = re.search(
        r"(?:data\s+(?:verbale|violazione)?|in\s+data)\s*:?[ ]*(\d{2}/\d{2}/\d{4})",
        text or "", re.I,
    )
    if not match:
        return None
    day, month, year = match.group(1).split("/")
    return f"{year}-{month}-{day}"


async def process_verbale_document(
    db,
    *,
    document_id: str,
    content: bytes,
    filename: str,
    source: str = "drive_verbale",
    parsed_metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Conserva relazioni certe; senza numero/IUV lascia il PDF da rivedere."""
    sha256 = hashlib.sha256(content).hexdigest()
    try:
        text = _extract_text(content)
    except Exception:
        text = ""

    parsed_metadata = dict(parsed_metadata or {})
    ai_data: Dict[str, Any] = {
        "numero_verbale": parsed_metadata.get("numero_verbale"),
        "iuv": parsed_metadata.get("identificativo_bolletta") or parsed_metadata.get("iuv"),
        "targa": parsed_metadata.get("targa"),
        "importo_ridotto": parsed_metadata.get("importo"),
        "data_violazione": parsed_metadata.get("data_violazione"),
    }
    ai_data = {key: value for key, value in ai_data.items() if value not in (None, "")}
    ai_was_used = False
    ai_error: Optional[str] = None
    # Il fallback vision serve solo per veri PDF scansione. Questa guardia
    # evita chiamate esterne su payload corrotti o sui fixture testuali.
    if content.startswith(b"%PDF") and len(text.strip()) < 80:
        try:
            from app.services.ai_document_parser import parse_verbale_ai
            ai_result = await parse_verbale_ai(file_bytes=content)
            if ai_result.get("success"):
                ai_data.update(ai_result)
                ai_was_used = True
            else:
                ai_error = str(ai_result.get("error") or "estrazione AI non disponibile")
        except Exception as exc:
            ai_error = str(exc)

    combined = f"{filename}\n{text}"
    from app.services.pagopa_receipts import parse_receipt_pdf

    pagopa_data = parse_receipt_pdf(content, filename=filename)
    numero = (
        _normalizza_numero(ai_data.get("numero_verbale"))
        or _normalizza_numero(pagopa_data.get("numero_verbale"))
        or _extract_numero(combined)
    )
    iuv_match = _IUV_RE.search(combined)
    targa_match = _TARGA_RE.search(combined)
    iuv = (
        str(ai_data.get("iuv") or "").strip()
        or pagopa_data.get("identificativo_bolletta")
        or (iuv_match.group(1) if iuv_match else None)
    )
    targa_ai = str(ai_data.get("targa") or "").strip().upper()
    targa = (
        targa_ai if _TARGA_RE.fullmatch(targa_ai)
        else pagopa_data.get("targa")
        or (targa_match.group(1).upper() if targa_match else None)
    )
    importo = (
        _float_or_none(ai_data.get("importo_ridotto"))
        or _float_or_none(ai_data.get("importo_ordinario"))
        or pagopa_data.get("importo")
        or _extract_amount(text)
    )
    data_pagamento = _extract_payment_date(text)
    negative_payment = (
        pagopa_data.get("document_kind") == "ESITO_PAGOPA_NEGATIVO"
        or any(marker in combined.casefold() for marker in _NEGATIVE_PAYMENT_MARKERS)
    )
    is_receipt = not negative_payment and (
        pagopa_data.get("is_payment_receipt") is True
        or
        ai_data.get("tipo_documento") == "ricevuta_pagopa"
        or any(marker in combined.casefold() for marker in _RICEVUTA_MARKERS)
    )
    now = datetime.now(timezone.utc).isoformat()

    extracted = {
        "numero_verbale_estratto": numero,
        "iuv_estratto": iuv,
        "targa_estratta": targa,
        "importo_estratto": importo,
        "codice_avviso_estratto": pagopa_data.get("codice_avviso"),
        "codice_cbill_estratto": pagopa_data.get("codice_cbill"),
        "data_scadenza_estratta": pagopa_data.get("data_scadenza"),
        "document_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "estrazione_ai_usata": ai_was_used,
        "estrazione_parser_locale": bool(parsed_metadata),
        "estrazione_ai_errore": ai_error,
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
    violation_date = (
        ai_data.get("data_violazione")
        or pagopa_data.get("data_violazione")
        or _extract_violation_date(text)
    )
    vehicle = await _vehicle_context(db, targa, violation_date)
    values = {
        "id": verbale_id,
        "numero_verbale": numero,
        "iuv": iuv,
        "targa": targa,
        "importo": importo,
        "data_verbale": ai_data.get("data_verbale"),
        "data_violazione": violation_date,
        "data_scadenza": pagopa_data.get("data_scadenza"),
        "codice_avviso": pagopa_data.get("codice_avviso"),
        "codice_cbill": pagopa_data.get("codice_cbill"),
        "ora_violazione": ai_data.get("ora_violazione"),
        "numero_atto": ai_data.get("numero_atto"),
        "ente_creditore": ai_data.get("ente_creditore"),
        "articolo_cds": ai_data.get("articolo_cds"),
        "descrizione_violazione": ai_data.get("descrizione_violazione"),
        "responsabile": ai_data.get("responsabile"),
        "partita_iva_responsabile": ai_data.get("partita_iva_responsabile"),
        "indirizzo_violazione": ai_data.get("indirizzo_violazione"),
        "ambito": "veicolo" if targa else "amministrativo",
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
