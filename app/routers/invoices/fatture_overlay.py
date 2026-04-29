"""
Compatibility overlay for legacy /api/fatture routes.

This router intercepts the most fragile legacy endpoints before the old
fatture_upload router. It keeps the supplier payment method on the invoice,
prevents automatic definitive prima nota registration when payment certainty is
missing, and serves invoice detail through a more tolerant lookup.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import io
import re
import uuid
import zipfile

from fastapi import APIRouter, Body, File, HTTPException, UploadFile

from app.database import Database
from app.parsers.fattura_elettronica_parser import parse_fattura_xml
from app.routers.fatture_module.common import (
    COL_ALLEGATI,
    COL_DETTAGLIO_RIGHE,
    COL_FATTURE_RICEVUTE,
)
from app.routers.fatture_module.crud import get_fattura_dettaglio, update_fattura
from app.routers.fatture_module.helpers import (
    get_or_create_fornitore,
    salva_allegato_pdf,
    salva_dettaglio_righe,
)
from app.routers.invoices.fatture_upload import riconcilia_con_estratto_conto

router = APIRouter()


def _decode_xml_bytes(content: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1", "iso-8859-1", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper().replace(" ", "")


def _normalize_invoice_number(value: Any) -> str:
    normalized = _normalize_text(value)
    normalized = normalized.replace("/", "-")
    normalized = re.sub(r"[^A-Z0-9-]", "", normalized)
    return normalized


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _invoice_score(invoice: Dict[str, Any]) -> int:
    score = 0
    if _as_float(invoice.get("imponibile")) > 0:
        score += 4
    if _as_float(invoice.get("iva")) > 0:
        score += 4
    if invoice.get("riepilogo_iva"):
        score += 3
    if invoice.get("linee"):
        score += 3
    if invoice.get("xml_content"):
        score += 2
    if invoice.get("filename"):
        score += 1
    if invoice.get("supplier_name") or invoice.get("fornitore_ragione_sociale"):
        score += 1
    return score


def _build_invoice_key(numero: str, partita_iva: str, data_documento: str) -> str:
    return f"{_normalize_invoice_number(numero)}_{_normalize_text(partita_iva)}_{(data_documento or '').strip()}"


async def _find_existing_duplicate(
    db,
    partita_iva: str,
    numero_documento: str,
    data_documento: str,
    importo_totale: float,
) -> Optional[Dict[str, Any]]:
    if not partita_iva or not numero_documento:
        return None

    normalized_number = _normalize_invoice_number(numero_documento)
    query = {
        "$and": [
            {
                "$or": [
                    {"supplier_vat": partita_iva},
                    {"fornitore_partita_iva": partita_iva},
                    {"cedente_piva": partita_iva},
                ]
            },
            {
                "$or": [
                    {"invoice_date": data_documento},
                    {"data_documento": data_documento},
                    {"data_fattura": data_documento},
                ]
            },
            {
                "$or": [
                    {"invoice_number": {"$regex": f"^{re.escape(numero_documento)}$", "$options": "i"}},
                    {"numero_documento": {"$regex": f"^{re.escape(numero_documento)}$", "$options": "i"}},
                    {"numero_fattura": {"$regex": f"^{re.escape(numero_documento)}$", "$options": "i"}},
                ]
            },
        ]
    }
    candidates = await db[COL_FATTURE_RICEVUTE].find(query, {"_id": 0}).to_list(20)
    if not candidates:
        existing = await db[COL_FATTURE_RICEVUTE].find_one(
            {"invoice_key": _build_invoice_key(numero_documento, partita_iva, data_documento)},
            {"_id": 0},
        )
        return existing

    def matches(candidate: Dict[str, Any]) -> bool:
        candidate_number = (
            candidate.get("invoice_number")
            or candidate.get("numero_documento")
            or candidate.get("numero_fattura")
        )
        if _normalize_invoice_number(candidate_number) != normalized_number:
            return False
        candidate_total = _as_float(candidate.get("total_amount") or candidate.get("importo_totale"))
        return abs(candidate_total - importo_totale) <= 0.01 or candidate_total == 0 or importo_totale == 0

    matching = [candidate for candidate in candidates if matches(candidate)]
    if not matching:
        matching = candidates

    matching.sort(key=lambda item: (_invoice_score(item), item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return matching[0]


async def _upsert_invoice_from_xml(
    xml_content: str,
    filename: str,
) -> Dict[str, Any]:
    db = Database.get_db()
    parsed = parse_fattura_xml(xml_content)
    if parsed.get("error"):
        raise HTTPException(status_code=400, detail=f"Errore parsing XML: {parsed['error']}")

    partita_iva = (parsed.get("supplier_vat") or "").strip().upper()
    numero_doc = parsed.get("invoice_number") or ""
    data_documento = parsed.get("invoice_date") or ""
    importo_totale = _as_float(parsed.get("total_amount"))

    duplicate = await _find_existing_duplicate(db, partita_iva, numero_doc, data_documento, importo_totale)

    fornitore_result = await get_or_create_fornitore(db, parsed)
    if fornitore_result.get("error"):
        raise HTTPException(status_code=400, detail=fornitore_result["error"])

    supplier_doc = None
    if partita_iva:
        supplier_doc = await db["fornitori"].find_one(
            {"partita_iva": partita_iva},
            {"_id": 0, "metodo_pagamento": 1, "metodo_pagamento_predefinito": 1, "iban": 1, "giorni_pagamento": 1},
        )

    metodo_pagamento = "da_configurare"
    if supplier_doc:
        metodo_pagamento = (
            supplier_doc.get("metodo_pagamento_predefinito")
            or supplier_doc.get("metodo_pagamento")
            or "da_configurare"
        )

    riconciliazione = await riconcilia_con_estratto_conto(
        db,
        importo_totale,
        data_documento,
        parsed.get("supplier_name", ""),
        numero_doc,
    )
    riconciliato = bool(riconciliazione.get("trovato"))

    invoice_id = duplicate.get("id") if duplicate else str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    invoice_doc = {
        "id": invoice_id,
        "invoice_key": _build_invoice_key(numero_doc, partita_iva, data_documento),
        "tipo": "passiva",
        "invoice_number": numero_doc,
        "numero_documento": numero_doc,
        "numero_fattura": numero_doc,
        "invoice_date": data_documento,
        "data_documento": data_documento,
        "data_fattura": data_documento,
        "supplier_id": fornitore_result.get("fornitore_id"),
        "fornitore_id": fornitore_result.get("fornitore_id"),
        "supplier_vat": partita_iva,
        "fornitore_partita_iva": partita_iva,
        "cedente_piva": partita_iva,
        "supplier_name": parsed.get("supplier_name", ""),
        "fornitore_ragione_sociale": fornitore_result.get("ragione_sociale") or parsed.get("supplier_name", ""),
        "cedente_denominazione": parsed.get("supplier_name", ""),
        "fornitore": parsed.get("fornitore", {}),
        "cliente": parsed.get("cliente", {}),
        "pagamento": parsed.get("pagamento", {}),
        "linee": parsed.get("linee", []),
        "riepilogo_iva": parsed.get("riepilogo_iva", []),
        "causali": parsed.get("causali", []),
        "tipo_documento": parsed.get("tipo_documento", "TD01"),
        "tipo_documento_desc": parsed.get("tipo_documento_desc", "Fattura"),
        "divisa": parsed.get("divisa", "EUR"),
        "total_amount": importo_totale,
        "importo_totale": importo_totale,
        "imponibile": _as_float(parsed.get("imponibile")),
        "iva": _as_float(parsed.get("iva")),
        "metodo_pagamento": metodo_pagamento,
        "metodo_pagamento_effettivo": "banca" if riconciliato else None,
        "provvisorio": not riconciliato,
        "riconciliato": riconciliato,
        "pagato": riconciliato,
        "data_pagamento": riconciliazione.get("data_pagamento") if riconciliato else None,
        "stato": "pagata" if riconciliato else "importata",
        "stato_pagamento": "pagata" if riconciliato else "in_attesa",
        "status": "paid" if riconciliato else "imported",
        "riconciliazione_auto": riconciliazione if riconciliato else None,
        "movimento_bancario_id": riconciliazione.get("movimento_banca_id") if riconciliato else None,
        "filename": filename,
        "xml_content": xml_content,
        "source": "legacy_fatture_overlay",
        "updated_at": now,
    }

    if duplicate:
        update_fields = invoice_doc.copy()
        update_fields.pop("id", None)
        update_fields["source"] = duplicate.get("source") or "legacy_fatture_overlay"
        update_fields["created_at"] = duplicate.get("created_at") or now
        if duplicate.get("metodo_pagamento_modificato_manualmente"):
            update_fields["metodo_pagamento"] = duplicate.get("metodo_pagamento") or metodo_pagamento
        if duplicate.get("pagato") and not riconciliato:
            update_fields["pagato"] = True
            update_fields["provvisorio"] = duplicate.get("provvisorio", False)
            update_fields["riconciliato"] = duplicate.get("riconciliato", False)
            update_fields["data_pagamento"] = duplicate.get("data_pagamento")
            update_fields["stato"] = duplicate.get("stato") or update_fields["stato"]
            update_fields["status"] = duplicate.get("status") or update_fields["status"]
            update_fields["stato_pagamento"] = duplicate.get("stato_pagamento") or update_fields["stato_pagamento"]
        await db[COL_FATTURE_RICEVUTE].update_one({"id": invoice_id}, {"$set": update_fields})
        await db[COL_DETTAGLIO_RIGHE].delete_many({"fattura_id": invoice_id})
        await db[COL_ALLEGATI].delete_many({"fattura_id": invoice_id})
        action = "aggiornata"
    else:
        invoice_doc["created_at"] = now
        await db[COL_FATTURE_RICEVUTE].insert_one(invoice_doc.copy())
        action = "importata"

    await salva_dettaglio_righe(db, invoice_id, parsed.get("linee", []))
    for allegato in parsed.get("allegati", []):
        await salva_allegato_pdf(db, invoice_id, allegato)

    warnings: List[str] = []
    if metodo_pagamento in ("", "da_configurare", None):
        warnings.append("Fornitore senza metodo pagamento configurato")
    elif not riconciliato:
        warnings.append("Pagamento non confermato: fattura lasciata in stato provvisorio")

    return {
        "success": True,
        "azione": action,
        "fattura_id": invoice_id,
        "numero_documento": numero_doc,
        "data_documento": data_documento,
        "fornitore": {
            "partita_iva": partita_iva,
            "ragione_sociale": fornitore_result.get("ragione_sociale"),
            "nuovo": fornitore_result.get("nuovo"),
        },
        "metodo_pagamento": metodo_pagamento,
        "provvisorio": not riconciliato,
        "riconciliato": riconciliato,
        "warnings": warnings or None,
    }


@router.post("/upload-xml")
async def upload_fattura_xml_overlay(file: UploadFile = File(...)) -> Dict[str, Any]:
    if not (file.filename or "").lower().endswith(".xml"):
        raise HTTPException(status_code=400, detail="Il file deve essere in formato XML")
    content = await file.read()
    return await _upsert_invoice_from_xml(_decode_xml_bytes(content), file.filename or "upload.xml")


@router.post("/upload-xml-bulk")
async def upload_fatture_xml_bulk_overlay(files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    results: Dict[str, Any] = {
        "totale": 0,
        "importate": 0,
        "duplicate_aggiornate": 0,
        "errori": 0,
        "dettagli": [],
    }

    xml_items: List[Dict[str, Any]] = []
    for file in files:
        filename = file.filename or "unknown"
        content = await file.read()
        if filename.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    for nested_name in archive.namelist():
                        if nested_name.lower().endswith(".xml") and not nested_name.startswith("__MACOSX"):
                            xml_items.append({
                                "filename": nested_name,
                                "content": archive.read(nested_name),
                            })
            except zipfile.BadZipFile as exc:
                results["errori"] += 1
                results["dettagli"].append({"filename": filename, "status": "errore", "error": str(exc)})
        elif filename.lower().endswith(".xml"):
            xml_items.append({"filename": filename, "content": content})
        else:
            results["errori"] += 1
            results["dettagli"].append({"filename": filename, "status": "errore", "error": "Formato non supportato"})

    results["totale"] = len(xml_items)
    for item in xml_items:
        try:
            outcome = await _upsert_invoice_from_xml(_decode_xml_bytes(item["content"]), item["filename"])
            results["dettagli"].append({"filename": item["filename"], "status": outcome.get("azione"), "fattura_id": outcome.get("fattura_id")})
            if outcome.get("azione") == "aggiornata":
                results["duplicate_aggiornate"] += 1
            else:
                results["importate"] += 1
        except Exception as exc:
            results["errori"] += 1
            results["dettagli"].append({"filename": item["filename"], "status": "errore", "error": str(exc)})

    return results


@router.post("/cleanup-duplicates")
async def cleanup_duplicate_invoices_overlay() -> Dict[str, Any]:
    db = Database.get_db()
    invoices = await db[COL_FATTURE_RICEVUTE].find({}, {"_id": 0}).to_list(10000)

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for invoice in invoices:
        number = invoice.get("invoice_number") or invoice.get("numero_documento") or invoice.get("numero_fattura")
        vat = invoice.get("supplier_vat") or invoice.get("fornitore_partita_iva") or invoice.get("cedente_piva")
        date_value = invoice.get("invoice_date") or invoice.get("data_documento") or invoice.get("data_fattura")
        total = _as_float(invoice.get("total_amount") or invoice.get("importo_totale"))
        if not number or not vat or not date_value:
            continue
        key = f"{_normalize_invoice_number(number)}|{_normalize_text(vat)}|{date_value}|{total:.2f}"
        grouped.setdefault(key, []).append(invoice)

    duplicate_groups = [items for items in grouped.values() if len(items) > 1]
    removed = 0
    merged = 0
    for items in duplicate_groups:
        items.sort(key=lambda item: (_invoice_score(item), item.get("updated_at") or item.get("created_at") or ""), reverse=True)
        keeper = items[0]
        keeper_id = keeper["id"]
        keeper_updates: Dict[str, Any] = {}

        for candidate in items[1:]:
            if _invoice_score(candidate) > _invoice_score({**keeper, **keeper_updates}):
                for field in ("imponibile", "iva", "riepilogo_iva", "linee", "xml_content", "filename", "fornitore", "cliente", "pagamento"):
                    if candidate.get(field) and not keeper_updates.get(field) and not keeper.get(field):
                        keeper_updates[field] = candidate.get(field)
            result = await db[COL_FATTURE_RICEVUTE].delete_one({"id": candidate["id"]})
            removed += result.deleted_count
        if keeper_updates:
            keeper_updates["updated_at"] = datetime.now(timezone.utc).isoformat()
            await db[COL_FATTURE_RICEVUTE].update_one({"id": keeper_id}, {"$set": keeper_updates})
            merged += 1

    return {
        "duplicate_groups_found": len(duplicate_groups),
        "invoices_deleted": removed,
        "keepers_enriched": merged,
    }


@router.get("/{invoice_id}")
async def get_fattura_overlay(invoice_id: str) -> Dict[str, Any]:
    return await get_fattura_dettaglio(invoice_id)


@router.put("/{invoice_id}")
async def update_fattura_overlay(invoice_id: str, data: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    return await update_fattura(invoice_id, data)
