"""Proiezione read-only delle fatture Sheets per CeraldiApp/Lotti.

GestionaleCloud resta l'unico punto che legge e indicizza Drive. Lotti riceve
solo documenti gia' idratati dal registro Google Sheets e li importa con un
identificativo e un hash stabili. In questo modo un secondo giro non duplica
fatture, lotti o giacenze.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import date, datetime
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.database import Database


router = APIRouter(prefix="/integrations/lotti", tags=["Integrazione Lotti"])


def _text(value: Any) -> str:
    return str(value or "").strip()


def _invoice_date(document: dict[str, Any]) -> str:
    value = (
        document.get("invoice_date")
        or document.get("data_fattura")
        or document.get("data_documento")
        or ""
    )
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return _text(value)


def _year(value: str) -> Optional[int]:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value[:10], fmt).year
        except (TypeError, ValueError):
            continue
    return None


def _source_id(document: dict[str, Any]) -> str:
    explicit = _text(document.get("id") or document.get("invoice_key"))
    if explicit:
        return explicit
    identity = "|".join(
        (
            _text(document.get("supplier_vat") or document.get("fornitore_partita_iva")),
            _text(document.get("invoice_number") or document.get("numero_fattura") or document.get("numero_documento")),
            _invoice_date(document),
        )
    )
    return "invoice-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]


def _portable(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _portable(v) for k, v in value.items() if k != "_id"}
    if isinstance(value, list):
        return [_portable(v) for v in value]
    return value


def _projection(document: dict[str, Any], *, include_xml: bool) -> dict[str, Any]:
    lines = document.get("linee") or document.get("righe") or document.get("prodotti") or []
    xml_raw = _text(document.get("xml_raw"))
    projected = {
        "source_id": _source_id(document),
        "invoice_number": _text(
            document.get("invoice_number")
            or document.get("numero_fattura")
            or document.get("numero_documento")
        ),
        "invoice_date": _invoice_date(document),
        "supplier_name": _text(
            document.get("supplier_name")
            or document.get("cedente_denominazione")
            or document.get("fornitore_ragione_sociale")
        ),
        "supplier_vat": _text(
            document.get("supplier_vat")
            or document.get("cedente_piva")
            or document.get("fornitore_partita_iva")
        ),
        "total_amount": document.get("total_amount") or document.get("importo_totale") or 0,
        "document_type": _text(document.get("tipo_documento") or "TD01"),
        "lines": _portable(lines if isinstance(lines, list) else []),
        "has_xml": bool(xml_raw),
        "source": "gestionalecloud_sheets",
    }
    hash_payload = dict(projected)
    hash_payload["xml_sha256"] = hashlib.sha256(xml_raw.encode("utf-8")).hexdigest() if xml_raw else ""
    projected["source_hash"] = hashlib.sha256(
        json.dumps(hash_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
    if include_xml:
        projected["xml_raw"] = xml_raw
    return projected


def _authorized(x_lotti_key: Optional[str]) -> None:
    expected = _text(os.environ.get("LOTTI_INTEGRATION_KEY"))
    if not expected:
        raise HTTPException(status_code=503, detail="Integrazione Lotti non configurata")
    supplied = _text(x_lotti_key)
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Chiave integrazione non valida")


async def _documents() -> list[dict[str, Any]]:
    db = Database.get_db()
    docs = await db["invoices"].find({}, {"_id": 0}).to_list(10000)
    return [
        doc for doc in docs
        if doc.get("entity_status") != "deleted"
        and doc.get("status") != "deleted"
        and not doc.get("deleted")
    ]


@router.get("/invoices")
async def list_invoices_for_lotti(
    anno: Optional[int] = Query(None, ge=2000, le=2100),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=500),
    x_lotti_key: Optional[str] = Header(None, alias="X-Lotti-Key"),
) -> dict[str, Any]:
    """Elenco paginato senza XML, letto dalla collection Sheets ``invoices``."""
    _authorized(x_lotti_key)
    projected = [_projection(doc, include_xml=False) for doc in await _documents()]
    if anno is not None:
        projected = [item for item in projected if _year(item["invoice_date"]) == anno]
    projected.sort(key=lambda item: (item["invoice_date"], item["source_id"]))
    total = len(projected)
    return {"data": projected[skip: skip + limit], "total": total, "skip": skip, "limit": limit}


@router.get("/invoices/{source_id}")
async def get_invoice_for_lotti(
    source_id: str,
    x_lotti_key: Optional[str] = Header(None, alias="X-Lotti-Key"),
) -> dict[str, Any]:
    """Dettaglio con XML originale, sempre proveniente dal record Sheets."""
    _authorized(x_lotti_key)
    for document in await _documents():
        if _source_id(document) == source_id:
            return _projection(document, include_xml=True)
    raise HTTPException(status_code=404, detail="Fattura non trovata")
