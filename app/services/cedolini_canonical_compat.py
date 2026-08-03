"""Compatibilita' tra la UI storica e il modello cedolini canonico.

Il database condiviso conserva i cedolini con periodo ``MM/AAAA``, codice
fiscale e PDF in GridFS. Questo modulo traduce quel modello in lettura per la
vecchia pagina e, per i nuovi import Drive, continua a scrivere nello stesso
modello senza creare una seconda anagrafica parallela.
"""

from __future__ import annotations

import base64
import hashlib
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, Optional

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from pymongo import DESCENDING
from pymongo.errors import DuplicateKeyError


CANONICAL_PAY_KINDS = {
    "mensile": "ordinario",
    "ordinario": "ordinario",
    "tredicesima": "tredicesima",
    "quattordicesima": "quattordicesima",
    "tfr": "tfr_cessazione",
    "tfr_cessazione": "tfr_cessazione",
}


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0").replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _money(value: Any) -> float:
    return float(_decimal(value).quantize(Decimal("0.01")))


def _period_parts(reference_period: str) -> tuple[int, int]:
    try:
        month, year = (int(part) for part in reference_period.split("/", 1))
        return month, year
    except (AttributeError, TypeError, ValueError):
        return 0, 0


def _person_key(record: Dict[str, Any]) -> str:
    return str(record.get("tax_code") or record.get("employee_name") or "").strip().upper()


def _operational_key(record: Dict[str, Any]) -> tuple[str, str, str]:
    return (
        _person_key(record),
        str(record.get("reference_period") or ""),
        str(record.get("pay_kind") or "ordinario"),
    )


def _record_order(record: Dict[str, Any]) -> tuple[datetime, str]:
    created = record.get("created_at")
    if not isinstance(created, datetime):
        created = datetime.min.replace(tzinfo=timezone.utc)
    elif created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created, str(record.get("_id") or "")


def _current_records(records: Iterable[Dict[str, Any]]) -> tuple[list[Dict[str, Any]], Dict[str, str]]:
    current: Dict[tuple[str, str, str], Dict[str, Any]] = {}
    all_records = list(records)
    for record in all_records:
        key = _operational_key(record)
        previous = current.get(key)
        if previous is None or _record_order(record) > _record_order(previous):
            current[key] = record
    legacy_to_current = {
        str(record.get("_id")): str(current[_operational_key(record)].get("_id"))
        for record in all_records
    }
    return list(current.values()), legacy_to_current


def _optional_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


async def uses_canonical_payroll_schema(db) -> bool:
    return await db["cedolini"].find_one(
        {"reference_period": {"$type": "string"}}, {"_id": 1}
    ) is not None


async def canonical_salary_rows(
    db,
    *,
    anno: Optional[int] = None,
    mese: Optional[int] = None,
    dipendente: Optional[str] = None,
) -> list[Dict[str, Any]]:
    query: Dict[str, Any] = {"reference_period": {"$type": "string"}}
    if anno and mese:
        query["reference_period"] = f"{int(mese):02d}/{int(anno)}"
    elif anno:
        query["reference_period"] = {"$regex": f"/{int(anno)}$"}
    elif mese:
        query["reference_period"] = {"$regex": f"^{int(mese):02d}/"}
    if dipendente:
        query["employee_name"] = {"$regex": dipendente, "$options": "i"}

    records = await db["cedolini"].find(query, {"voices": 0}).sort(
        [("created_at", DESCENDING)]
    ).to_list(20_000)
    current, legacy_to_current = _current_records(records)
    if not current:
        return []

    current_ids = {str(record["_id"]) for record in current}
    paid_by_id = {record_id: Decimal("0") for record_id in current_ids}
    claims = await db["riconciliazioni_fonti"].find(
        {"module": "cedolini"}, {"_id": 0, "record_id": 1, "amount": 1}
    ).to_list(20_000)
    for claim in claims:
        target = legacy_to_current.get(str(claim.get("record_id")), str(claim.get("record_id") or ""))
        if target in paid_by_id:
            paid_by_id[target] += _decimal(claim.get("amount"))

    source_hashes = {record.get("source_hash") for record in current if record.get("source_hash")}
    available_hashes = set()
    if source_hashes:
        docs = await db["cedolini_documenti"].find(
            {"_id": {"$in": list(source_hashes)}}, {"_id": 1}
        ).to_list(len(source_hashes))
        available_hashes = {str(document["_id"]) for document in docs}

    rows: list[Dict[str, Any]] = []
    for record in current:
        month, year = _period_parts(record.get("reference_period") or "")
        if year < 2018:
            continue
        summary = record.get("summary") or {}
        total = _decimal(summary.get("total_entitlement"))
        if total == 0:
            total = _decimal(summary.get("net_pay")) + _decimal(summary.get("advance_amount"))
        advance = _decimal(summary.get("advance_amount"))
        due = max(total - advance, Decimal("0"))
        record_id = str(record["_id"])
        paid = paid_by_id.get(record_id, Decimal("0"))
        residual = max(due - paid, Decimal("0"))
        pay_kind = str(record.get("pay_kind") or "ordinario")
        ui_kind = "mensile" if pay_kind == "ordinario" else pay_kind
        rows.append({
            "id": f"canonical:{record_id}",
            "cedolino_id": f"canonical:{record_id}",
            "dipendente_id": record.get("tax_code") or _person_key(record),
            "dipendente": record.get("employee_name") or "Dipendente da identificare",
            "dipendente_nome": record.get("employee_name") or "Dipendente da identificare",
            "codice_fiscale": record.get("tax_code"),
            "mese": month,
            "anno": year,
            "tipo": "stipendio",
            "tipo_cedolino": ui_kind,
            "importo_busta": _money(due),
            "importo_bonifico": _money(paid),
            "importo_bonifico_documentato": _money(paid),
            "saldo": _money(-residual),
            "riconciliato": bool(due > 0 and residual <= Decimal("0.01")),
            "cedolino_disponibile": str(record.get("source_hash") or "") in available_hashes,
            "source_name": record.get("source_name"),
            "verification_status": record.get("verification_status"),
        })
    return rows


async def canonical_pdf_bytes(db, canonical_id: str) -> Optional[bytes]:
    if not ObjectId.is_valid(canonical_id):
        return None
    record = await db["cedolini"].find_one(
        {"_id": ObjectId(canonical_id)}, {"source_hash": 1}
    )
    source_hash = (record or {}).get("source_hash")
    if not source_hash:
        return None
    document = await db["cedolini_documenti"].find_one(
        {"_id": source_hash}, {"gridfs_id": 1}
    )
    if not document or not document.get("gridfs_id"):
        return None
    bucket = AsyncIOMotorGridFSBucket(db, bucket_name="cedolini_pdf")
    stream = await bucket.open_download_stream(document["gridfs_id"])
    return await stream.read()


async def store_canonical_payroll(
    db,
    cedolino_data: Dict[str, Any],
    *,
    filename: str,
    pdf_data: str,
) -> Dict[str, Any]:
    content = base64.b64decode(pdf_data, validate=True)
    if not content.startswith(b"%PDF"):
        raise ValueError("Il documento sorgente non e' un PDF valido")
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("Il PDF supera il limite di 20 MB")
    source_hash = hashlib.sha256(content).hexdigest()
    tax_code = str(cedolino_data.get("codice_fiscale") or "").strip().upper()
    employee_name = str(cedolino_data.get("nome_dipendente") or "").strip()
    month = int(cedolino_data.get("mese"))
    year = int(cedolino_data.get("anno"))
    if year < 2018:
        return {
            "success": True,
            "cedolino_id": None,
            "canonical": True,
            "duplicate": False,
            "skipped": True,
            "skip_reason": "periodo_precedente_2018",
            "riconciliato": False,
        }
    employee_name = employee_name or tax_code or "Dipendente da identificare"
    reference_period = f"{month:02d}/{year}"
    pay_kind = CANONICAL_PAY_KINDS.get(
        str(cedolino_data.get("tipo_cedolino") or "mensile").lower(), "ordinario"
    )
    net = _money(cedolino_data.get("netto_mese") or cedolino_data.get("netto"))
    gross = _money(cedolino_data.get("lordo"))
    deductions = _money(cedolino_data.get("totale_trattenute"))
    identity_query: Dict[str, Any]
    if tax_code:
        identity_query = {"tax_code": tax_code}
    else:
        identity_query = {"employee_name": {"$regex": f"^{re.escape(employee_name)}$", "$options": "i"}}
    possible_matches = await db["cedolini"].find({
        **identity_query,
        "reference_period": reference_period,
        "pay_kind": pay_kind,
    }, {"summary.net_pay": 1}).to_list(100)
    logical_match = next(
        (
            item for item in possible_matches
            if _money((item.get("summary") or {}).get("net_pay")) == net
        ),
        None,
    )
    if logical_match:
        return {
            "success": True,
            "cedolino_id": str(logical_match["_id"]),
            "canonical": True,
            "duplicate": True,
            "riconciliato": False,
        }

    page = int(cedolino_data.get("source_page_start") or 1)
    identity = tax_code or employee_name.upper()
    duplicate_key = hashlib.sha256(
        f"{source_hash}:{page}:{identity}:{reference_period}".encode("utf-8")
    ).hexdigest()
    now = datetime.now(timezone.utc)
    document = {
        "employee_name": employee_name,
        "tax_code": tax_code or None,
        "reference_period": reference_period,
        "summary": {
            "net_pay": f"{net:.2f}",
            "total_entitlement": f"{net:.2f}",
            "advance_amount": None,
            "gross_total": f"{gross:.2f}",
            "total_deductions": f"{deductions:.2f}",
            "negative_net": "true" if net < 0 else "false",
        },
        "voices": [],
        "source_name": filename,
        "source_document_id": f"drive:{source_hash}",
        "source_hash": source_hash,
        "source_page": page,
        "duplicate_key": duplicate_key,
        "verification_status": "da_verificare",
        "hire_date": None,
        "termination_date": _optional_date(cedolino_data.get("data_cessazione_rilevata")),
        "termination_detected": bool(cedolino_data.get("cessato")),
        "termination_evidence": (
            "cedolino" if cedolino_data.get("cessato") else None
        ),
        "pay_kind": pay_kind,
        "created_at": now,
    }
    try:
        result = await db["cedolini"].insert_one(document)
    except DuplicateKeyError:
        existing = await db["cedolini"].find_one({"duplicate_key": duplicate_key}, {"_id": 1})
        return {
            "success": True,
            "cedolino_id": str((existing or {}).get("_id") or ""),
            "canonical": True,
            "duplicate": True,
            "riconciliato": False,
        }

    if await db["cedolini_documenti"].find_one({"_id": source_hash}, {"_id": 1}) is None:
        bucket = AsyncIOMotorGridFSBucket(db, bucket_name="cedolini_pdf")
        gridfs_id = await bucket.upload_from_stream(
            filename or f"{source_hash}.pdf",
            content,
            metadata={"source_hash": source_hash, "content_type": "application/pdf"},
        )
        try:
            await db["cedolini_documenti"].insert_one({
                "_id": source_hash,
                "source_name": filename,
                "gridfs_id": gridfs_id,
                "employee_names": [employee_name] if employee_name else [],
                "tax_codes": [tax_code] if tax_code else [],
                "reference_periods": [reference_period],
                "created_at": now,
            })
        except DuplicateKeyError:
            await bucket.delete(gridfs_id)

    return {
        "success": True,
        "cedolino_id": str(result.inserted_id),
        "canonical": True,
        "duplicate": False,
        "riconciliato": False,
    }
