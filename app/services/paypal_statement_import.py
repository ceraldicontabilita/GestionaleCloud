"""Persistenza canonica degli estratti conto PayPal.

Il servizio e' condiviso dall'upload manuale e dall'import automatico Drive.
Conserva il PDF originale, usa impronte deterministiche e collega anche le
transazioni gia' acquisite dalle API PayPal invece di scartarle come duplicati.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.constants.tipi_documento import set_tassonomia_documento


COLL_DOCUMENTS = "documents_inbox"
COLL_STATEMENTS = "paypal_statements"
COLL_TRANSACTIONS = "paypal_transactions"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _infer_period_from_transactions(parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Ricava un periodo affidabile dalle date delle transazioni parse.

    Alcuni report PayPal annuali non espongono l'intestazione mensile usata
    dagli MSR italiani. In quel caso le date normalizzate delle transazioni
    sono la fonte strutturata piu' affidabile: usiamo il minimo e il massimo,
    senza dedurre il periodo dal nome del file.
    """
    transaction_dates = []
    for transaction in parsed.get("transazioni") or []:
        raw_date = (
            transaction.get("data")
            or transaction.get("data_operazione")
            or transaction.get("initiation_date")
        )
        if not raw_date:
            continue
        normalized = str(raw_date).strip()[:10]
        try:
            transaction_dates.append(datetime.strptime(normalized, "%Y-%m-%d").date())
        except (TypeError, ValueError):
            continue

    if not transaction_dates:
        return None

    period_start = min(transaction_dates)
    period_end = max(transaction_dates)
    same_month = (
        period_start.year == period_end.year
        and period_start.month == period_end.month
    )
    return {
        "periodo_inizio": period_start.isoformat(),
        "periodo_fine": period_end.isoformat(),
        "mese": period_start.month if same_month else None,
        "anno": period_start.year if period_start.year == period_end.year else None,
        "periodo_inferito": True,
        "fonte_periodo": "date_transazioni",
    }


def _canonical_fingerprint(parsed: Dict[str, Any], source_sha256: str = "") -> str:
    """Identita' stabile dello statement, distinta anche per periodo.

    Un CSV puo' contenere piu' periodi e quindi condividere la stessa impronta
    del file. Il periodo e il conto fanno necessariamente parte della chiave.
    """
    periodo = parsed.get("periodo") or {}
    account = parsed.get("account_info") or {}
    transaction_ids = sorted(
        str(tx.get("transaction_id") or "")
        for tx in (parsed.get("transazioni") or [])
        if tx.get("transaction_id")
    )
    payload = {
        "source_sha256": source_sha256,
        "tipo": parsed.get("tipo_documento") or "MSR",
        "conto": account.get("codice_conto") or account.get("email_paypal"),
        "periodo_inizio": periodo.get("periodo_inizio"),
        "periodo_fine": periodo.get("periodo_fine"),
        "transaction_ids": transaction_ids,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _transaction_fingerprint(tx: Dict[str, Any], statement_id: str) -> str:
    payload = {
        "statement_id": statement_id,
        "data": tx.get("data"),
        "descrizione": tx.get("descrizione"),
        "nome": tx.get("nome_controparte"),
        "lordo": tx.get("lordo"),
        "netto": tx.get("netto"),
        "valuta": tx.get("valuta") or tx.get("currency"),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return "paypal_tx_" + hashlib.sha256(encoded).hexdigest()[:32]


async def _upsert_source_document(
    db,
    *,
    content: bytes,
    filename: str,
    source: str,
    drive_file_id: Optional[str],
    source_path: Optional[str],
) -> Dict[str, Any]:
    sha256 = hashlib.sha256(content).hexdigest()
    md5 = hashlib.md5(content).hexdigest()
    existing = await db[COLL_DOCUMENTS].find_one(
        {"$or": [{"sha256": sha256}, {"file_hash": md5}]},
        {"_id": 0, "id": 1},
    )
    document_id = str((existing or {}).get("id") or f"paypal_doc_{sha256[:32]}")
    now = _now_iso()
    doc = set_tassonomia_documento(
        {
            "id": document_id,
            "filename": filename,
            "pdf_data": base64.b64encode(content).decode("ascii"),
            "file_hash": md5,
            "sha256": sha256,
            "size_bytes": len(content),
            "mime_type": "application/pdf",
            "fonte": source,
            "source": source,
            "source_path": source_path or filename,
            "drive_file_id": drive_file_id,
            "stato": "elaborato",
            "status": "processato",
            "processed": True,
            "xml_processed": True,
            "downloaded_at": now,
            "updated_at": now,
        },
        "paypal_statement",
        label="Estratti conto PayPal",
    )
    await db[COLL_DOCUMENTS].update_one(
        {"id": document_id},
        {
            "$set": doc,
            "$setOnInsert": {"created_at": now},
            "$addToSet": {
                "source_paths": source_path or filename,
                **({"drive_file_ids": drive_file_id} if drive_file_id else {}),
            },
        },
        upsert=True,
    )
    return {"id": document_id, "sha256": sha256, "duplicate": bool(existing)}


async def save_parsed_statement(
    db,
    parsed: Dict[str, Any],
    *,
    content: Optional[bytes] = None,
    filename: Optional[str] = None,
    source: str = "paypal_upload_manuale",
    drive_file_id: Optional[str] = None,
    source_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Salva documento, statement e transazioni con relazioni bidirezionali."""
    periodo = parsed.get("periodo") or {}
    account = parsed.get("account_info") or {}
    filename = filename or parsed.get("file_name") or "estratto-paypal.pdf"
    now = _now_iso()

    source_document: Optional[Dict[str, Any]] = None
    if content is not None:
        source_document = await _upsert_source_document(
            db,
            content=content,
            filename=filename,
            source=source,
            drive_file_id=drive_file_id,
            source_path=source_path,
        )

    fingerprint = _canonical_fingerprint(
        parsed, (source_document or {}).get("sha256") or ""
    )
    deterministic_id = f"paypal_stmt_{fingerprint[:32]}"
    legacy_query = {
        "tipo_documento": parsed.get("tipo_documento", "MSR"),
        "codice_conto": account.get("codice_conto"),
        "periodo_inizio": periodo.get("periodo_inizio"),
        "periodo_fine": periodo.get("periodo_fine"),
    }
    existing_statement = await db[COLL_STATEMENTS].find_one(
        {"$or": [{"id": deterministic_id}, {"source_fingerprint": fingerprint}, legacy_query]},
        {"_id": 0, "id": 1},
    )
    statement_id = str((existing_statement or {}).get("id") or deterministic_id)
    document_id = (source_document or {}).get("id")

    parsed_transactions = [dict(tx) for tx in (parsed.get("transazioni") or [])]
    transaction_ids = [
        str(tx.get("transaction_id"))
        for tx in parsed_transactions
        if tx.get("transaction_id")
    ]
    statement_doc = {
        "id": statement_id,
        "tipo_documento": parsed.get("tipo_documento", "MSR"),
        "codice_conto": account.get("codice_conto"),
        "email_paypal": account.get("email_paypal"),
        "periodo_inizio": periodo.get("periodo_inizio"),
        "periodo_fine": periodo.get("periodo_fine"),
        "mese": periodo.get("mese"),
        "anno": periodo.get("anno"),
        "riepilogo": parsed.get("riepilogo_attivita") or {},
        "totale_transazioni": len(parsed_transactions),
        "transaction_ids": transaction_ids,
        "file_name": filename,
        "source": source,
        "source_path": source_path or filename,
        "drive_file_id": drive_file_id,
        "source_fingerprint": fingerprint,
        "source_sha256": (source_document or {}).get("sha256"),
        "document_id": document_id,
        "updated_at": now,
    }
    await db[COLL_STATEMENTS].update_one(
        {"id": statement_id},
        {"$set": statement_doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

    inserted = 0
    linked_existing = 0
    for parsed_tx in parsed_transactions:
        transaction_id = str(parsed_tx.get("transaction_id") or "").strip()
        source_key = transaction_id or _transaction_fingerprint(parsed_tx, statement_id)
        query = (
            {"transaction_id": transaction_id}
            if transaction_id
            else {"source_transaction_key": source_key}
        )
        existing_tx = await db[COLL_TRANSACTIONS].find_one(query, {"_id": 0})
        relation_fields = {
            "statement_id": statement_id,
            "document_id": document_id,
            "source_transaction_key": source_key,
            "updated_at": now,
        }
        if existing_tx:
            # L'API PayPal resta autorevole per i campi gia' valorizzati. Il
            # PDF completa solo dati mancanti e aggiunge la provenienza.
            for key, value in parsed_tx.items():
                if value not in (None, "") and existing_tx.get(key) in (None, ""):
                    relation_fields[key] = value
            if "riconciliato_banca" not in existing_tx:
                relation_fields["riconciliato_banca"] = False
            add_to_set: Dict[str, Any] = {
                "statement_ids": statement_id,
                "source_channels": source,
            }
            if document_id:
                add_to_set["document_ids"] = document_id
            if (source_document or {}).get("sha256"):
                add_to_set["source_file_sha256s"] = source_document["sha256"]
            await db[COLL_TRANSACTIONS].update_one(
                query, {"$set": relation_fields, "$addToSet": add_to_set}
            )
            linked_existing += 1
            continue

        new_tx = dict(parsed_tx)
        new_tx.update(relation_fields)
        new_tx.setdefault("id", source_key)
        new_tx.setdefault("source", source)
        new_tx.setdefault("riconciliato_banca", False)
        new_tx["statement_ids"] = [statement_id]
        new_tx["source_channels"] = [source]
        if document_id:
            new_tx["document_ids"] = [document_id]
        if (source_document or {}).get("sha256"):
            new_tx["source_file_sha256s"] = [source_document["sha256"]]
        new_tx["created_at"] = now
        await db[COLL_TRANSACTIONS].insert_one(new_tx)
        inserted += 1

    if document_id:
        await db[COLL_DOCUMENTS].update_one(
            {"id": document_id},
            {
                "$set": {
                    "paypal_statement_id": statement_id,
                    "paypal_transaction_ids": transaction_ids,
                    "updated_at": now,
                },
                "$addToSet": {"paypal_statement_ids": statement_id},
            },
        )

    try:
        from app.services.audit_logger import log_evento

        await log_evento(
            modulo="paypal",
            azione="estratto_importato" if not existing_statement else "estratto_ricollegato",
            entita_id=statement_id,
            entita_collection=COLL_STATEMENTS,
            db=db,
            fonte=source,
            nuovo_stato={
                "document_id": document_id,
                "transazioni_inserite": inserted,
                "transazioni_ricollegate": linked_existing,
            },
            extra={"source_sha256": (source_document or {}).get("sha256")},
        )
    except Exception:
        # L'import contabile non deve fallire se il log tecnico non e'
        # disponibile; audit_logger gestisce gia' internamente gli errori DB.
        pass

    return {
        "statement_id": statement_id,
        "document_id": document_id,
        "documento_duplicato": bool((source_document or {}).get("duplicate")),
        "statement_esistente": bool(existing_statement),
        "periodo": f"{periodo.get('periodo_inizio')} - {periodo.get('periodo_fine')}",
        "transazioni_inserite": inserted,
        "transazioni_ricollegate": linked_existing,
        # Compatibilita' con i contatori storici dell'endpoint.
        "transazioni_duplicate": linked_existing,
    }


async def import_paypal_statement_pdf(
    db,
    content: bytes,
    filename: str,
    *,
    source: str = "paypal_upload_manuale",
    drive_file_id: Optional[str] = None,
    source_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Parsa un PDF PayPal e lo salva; il file temporaneo viene sempre rimosso."""
    if not content:
        raise ValueError("file PayPal vuoto")
    if not content.lstrip().startswith(b"%PDF"):
        raise ValueError("il documento PayPal non e' un PDF valido")

    from app.parsers.paypal_msr_parser import parse_paypal_msr

    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            handle.write(content)
            temp_path = handle.name
        parsed = parse_paypal_msr(temp_path)
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass

    if not parsed.get("success"):
        raise ValueError(f"errore parsing PayPal: {parsed.get('errors') or 'documento non riconosciuto'}")
    periodo = parsed.get("periodo") or {}
    if not (periodo.get("periodo_inizio") and periodo.get("periodo_fine")):
        periodo = _infer_period_from_transactions(parsed)
        if not periodo:
            raise ValueError("periodo dell'estratto PayPal non riconosciuto")
        parsed["periodo"] = periodo
    parsed["file_name"] = os.path.basename(filename or "estratto-paypal.pdf")
    parsed.pop("file_path", None)
    return await save_parsed_statement(
        db,
        parsed,
        content=content,
        filename=parsed["file_name"],
        source=source,
        drive_file_id=drive_file_id,
        source_path=source_path,
    )
