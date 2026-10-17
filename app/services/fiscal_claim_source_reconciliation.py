"""Collega una pretesa di riscossione alle obbligazioni che l'hanno generata.

Il collegamento e' deliberatamente piu' stretto della normale ricerca:

* un verbale e' confermato solo con numero completo e targa coerente;
* un avviso INPS e' collegato solo col numero integrale dell'atto;
* un versamento F24 prova una riga originaria solo con quietanza, identita'
  contributiva, periodo e importo al centesimo. Il solo modello F24 non basta;
* un residuo AdeR pari a zero non viene trasformato in pagamento.

Il risultato viene salvato sulla pretesa per rendere visibili sia i collegamenti
confermati sia i documenti mancanti. Solo una quietanza esatta puo' generare
un invito a verificare sgravio/rimborso.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable

from app.db_collections import (
    COLL_DOCUMENTS_INBOX,
    COLL_F24,
    COLL_QUIETANZE_F24,
    COLL_TAX_COLLECTION_CLAIMS,
)


CENT = Decimal("0.01")
ACTIONABLE_STATUSES = {"PAYABLE", "MICRO_RESIDUAL_REVIEW", "REVIEW_REQUIRED"}
ALERT_RELIEF = "FISCAL_CLAIM_SOURCE_ALREADY_PAID"
ALERT_REFUND = "FISCAL_CLAIM_POSSIBLE_DOUBLE_PAYMENT"


def _identifier(value: Any) -> str:
    return re.sub(r"[^0-9A-Z]", "", str(value or "").upper())


def _verbale_key(value: Any) -> str:
    return _identifier(value)


def _money_cents(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        amount = Decimal(str(value).replace(".", "").replace(",", ".")) if (
            isinstance(value, str) and "," in value
        ) else Decimal(str(value))
        return int(amount.quantize(CENT, rounding=ROUND_HALF_UP) * 100)
    except (InvalidOperation, TypeError, ValueError):
        return None


def _period(value: Any) -> str | None:
    text = str(value or "").strip()
    match = re.search(r"\b(0?[1-9]|1[0-2])[/.-](20\d{2})\b", text)
    return f"{int(match.group(1)):02d}/{match.group(2)}" if match else None


_INPS_ROW = re.compile(
    r"(?ms)^\s*(?P<progressivo>\d{3})\s+"
    r"(?P<codice>8050|8055)-(?P<descrizione>[^\n]+)\n"
    r"[^\n]*?\bDA\s+(?P<da>\d{2}/\d{4})\s+A\s+(?P<a>\d{2}/\d{4})"
    r"\s+(?P<dovuto>[\d.]+,\d{2})\s+(?P<versato>[\d.]+,\d{2})"
    r"\s+(?P<richiesto>[\d.]+,\d{2})"
)


def parse_inps_notice_lines(text: str) -> list[dict[str, Any]]:
    """Estrae soltanto le righe INPS con periodo e tre importi leggibili."""
    rows: list[dict[str, Any]] = []
    for match in _INPS_ROW.finditer(text or ""):
        rows.append({
            "progressivo": match.group("progressivo"),
            "codice_tributo": match.group("codice"),
            "descrizione": match.group("descrizione").strip(),
            "periodo_da": match.group("da"),
            "periodo_a": match.group("a"),
            "importo_dovuto_cents": _money_cents(match.group("dovuto")),
            "importo_versato_nell_avviso_cents": _money_cents(match.group("versato")),
            "importo_richiesto_cents": _money_cents(match.group("richiesto")),
        })
    return rows


def _quietanza_rows(document: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for row in document.get("sezione_inps") or []:
        yield {
            "section": "INPS",
            "tax_code": str(row.get("causale") or "").upper(),
            "period": _period(row.get("periodo_riferimento") or row.get("periodo_da")),
            "identity": _identifier(row.get("matricola")),
            "debit_cents": row.get("importo_debito_cents") if isinstance(
                row.get("importo_debito_cents"), int
            ) else _money_cents(row.get("importo_debito")),
            "row": row,
        }
    for section in ("sezione_erario", "sezione_regioni", "sezione_tributi_locali"):
        for row in document.get(section) or []:
            yield {
                "section": section,
                "tax_code": str(row.get("codice_tributo") or "").upper(),
                "period": _period(row.get("periodo_riferimento")),
                "identity": None,
                "debit_cents": row.get("importo_debito_cents") if isinstance(
                    row.get("importo_debito_cents"), int
                ) else _money_cents(row.get("importo_debito")),
                "row": row,
            }


def _payment_reference(document: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    bank = document.get("riscontro_banca") or {}
    general = document.get("dati_generali") or {}
    return {
        "quietanza_id": document.get("id"),
        "protocollo": document.get("protocollo_telematico") or general.get("protocollo_telematico"),
        "data_pagamento": document.get("data_pagamento") or general.get("data_pagamento"),
        "filename": document.get("filename"),
        "drive_file_id": document.get("drive_file_id"),
        "bank_verified": bank.get("stato") == "RISCONTRATO_BANCA",
        "bank_movement_id": bank.get("movimento_id"),
        "matched_row": row,
        "basis": "QUIETANZA_EXACT_IDENTITY_PERIOD_AMOUNT",
    }


def match_quietanza_for_obligation(
    obligation: dict[str, Any], quietanze: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Trova prove univoche; importo, data o causale da soli non bastano."""
    matches: dict[str, dict[str, Any]] = {}
    period = _period(obligation.get("periodo_da") or obligation.get("periodo"))
    amount = obligation.get("importo_richiesto_cents")
    if amount is None:
        amount = obligation.get("importo_cents")
    identity = _identifier(obligation.get("matricola_inps"))
    source_code = str(obligation.get("codice_tributo") or "").upper()
    allowed_codes = {source_code}
    if source_code == "8050":
        allowed_codes = {"DM10", "RC01"}
    # Le sanzioni 8055 non vengono dichiarate pagate da una riga DM10/RC01
    # aggregata: serve una prova che le identifichi separatamente.
    if source_code == "8055":
        return []
    if not period or amount is None:
        return []
    for document in quietanze:
        for row in _quietanza_rows(document):
            if row["tax_code"] not in allowed_codes or row["period"] != period:
                continue
            if row["debit_cents"] != amount:
                continue
            if identity and row["identity"] != identity:
                continue
            key = str(document.get("protocollo_telematico") or document.get("id") or "")
            if not key:
                continue
            matches.setdefault(key, _payment_reference(document, row["row"]))
    return list(matches.values())


def match_f24_models_for_obligation(
    obligation: dict[str, Any], models: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collega il modello esatto, senza trasformarlo in prova di pagamento.

    Si applicano gli stessi vincoli della quietanza (identita' contributiva,
    periodo e importo al centesimo). La presenza del modello spiega quale F24
    si riferisce alla riga dell'avviso, ma ``payment_evidence`` resta sempre
    falso: soltanto quietanza e banca possono dimostrare il versamento.
    """
    period = _period(obligation.get("periodo_da") or obligation.get("periodo"))
    amount = obligation.get("importo_richiesto_cents")
    if amount is None:
        amount = obligation.get("importo_cents")
    identity = _identifier(obligation.get("matricola_inps"))
    source_code = str(obligation.get("codice_tributo") or "").upper()
    if source_code == "8055" or not period or amount is None:
        return []
    allowed_codes = {"DM10", "RC01"} if source_code == "8050" else {source_code}
    matches: dict[str, dict[str, Any]] = {}
    for document in models:
        for row in _quietanza_rows(document):
            if row["tax_code"] not in allowed_codes or row["period"] != period:
                continue
            if row["debit_cents"] != amount:
                continue
            if identity and row["identity"] != identity:
                continue
            key = str(document.get("id") or "")
            if not key:
                continue
            matches.setdefault(key, {
                "f24_id": key,
                "filename": document.get("filename") or document.get("file_name") or document.get("nome"),
                "drive_file_id": document.get("drive_file_id"),
                "matched_row": row["row"],
                "basis": "F24_MODEL_EXACT_IDENTITY_PERIOD_AMOUNT_NO_PAYMENT_PROOF",
                "payment_evidence": False,
            })
    return list(matches.values())


async def _find_exact_verbale(db, *, numero: str, targa: str) -> tuple[str, list[dict[str, Any]]]:
    found: list[dict[str, Any]] = []
    for collection in ("verbali_noleggio", "verbali_noleggio_completi"):
        async for item in db[collection].find(
            {}, {"_id": 0, "id": 1, "numero_verbale": 1, "targa": 1,
                 "expectation_status": 1, "stato_pagamento": 1, "document_id": 1},
        ):
            if _verbale_key(item.get("numero_verbale")) != _verbale_key(numero):
                continue
            if _identifier(item.get("targa")) != _identifier(targa):
                continue
            found.append({"collection": collection, **item})
    status = "CONFIRMED" if len(found) == 1 else ("SOURCE_DOCUMENT_MISSING" if not found else "REVIEW_REQUIRED")
    return status, found


async def _cartella_links(db, claim: dict[str, Any]) -> list[dict[str, Any]]:
    number = _identifier(claim.get("collection_number"))
    cartella = await db["cartelle_pagamento"].find_one(
        {"$or": [{"tax_collection_claim_id": claim.get("id")},
                 {"id": "cartella:" + number}]}, {"_id": 0},
    )
    if not cartella:
        return []
    links: list[dict[str, Any]] = []
    for reference in cartella.get("verbali") or []:
        numero = reference.get("numero_verbale")
        targa = reference.get("targa")
        if not numero or not targa:
            continue
        status, found = await _find_exact_verbale(db, numero=numero, targa=targa)
        related_lines = [
            row for row in cartella.get("righe") or []
            if _verbale_key(row.get("numero_verbale")) == _verbale_key(numero)
        ]
        links.append({
            "source_type": "VERBALE_AUTO",
            "relation_status": status,
            "basis": "EXACT_VERBALE_NUMBER_AND_PLATE",
            "numero_verbale": numero,
            "targa": targa,
            "data_verbale": next((row.get("data_verbale") for row in related_lines if row.get("data_verbale")), None),
            "data_notifica": next((row.get("data_notifica_verbale") for row in related_lines if row.get("data_notifica_verbale")), None),
            "tax_lines": related_lines,
            "matched_documents": found,
            "payment_evidence_status": (
                "PAID_DOCUMENTED" if any(
                    str(item.get("expectation_status") or item.get("stato_pagamento") or "").upper()
                    in {"SODDISFATTO", "PAGATO_DOCUMENTALE", "RICONCILIATO_BANCA"}
                    for item in found
                ) else "NO_PAYMENT_EVIDENCE"
            ),
        })
    return links


async def _notice_links(
    db, claim: dict[str, Any], quietanze: list[dict[str, Any]],
    f24_models: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    number = _identifier(claim.get("collection_number"))
    originals = await db[COLL_DOCUMENTS_INBOX].find(
        {"$or": [{"tax_collection_claim_id": claim.get("id")},
                 {"parsed_metadata.numero_atto": number}]},
        {"_id": 0, "pdf_data": 0, "contenuto_b64": 0},
    ).to_list(100)
    links: list[dict[str, Any]] = []
    seen: set[str] = set()
    for original in originals:
        metadata = original.get("parsed_metadata") or {}
        if _identifier(metadata.get("numero_atto")) != number:
            continue
        original_id = str(original.get("id") or "")
        if not original_id or original_id in seen:
            continue
        seen.add(original_id)
        text = metadata.get("testo_estratto") or ""
        rows = parse_inps_notice_lines(text)
        matricola = metadata.get("matricola_inps")
        enriched: list[dict[str, Any]] = []
        for row in rows:
            obligation = {**row, "matricola_inps": matricola}
            payment_matches = match_quietanza_for_obligation(obligation, quietanze)
            f24_model_matches = match_f24_models_for_obligation(obligation, f24_models)
            enriched.append({
                **obligation,
                "payment_evidence_status": (
                    "PAID_DOCUMENTED" if len(payment_matches) == 1 else
                    "REVIEW_REQUIRED" if len(payment_matches) > 1 else
                    "NO_PAYMENT_EVIDENCE"
                ),
                "payment_matches": payment_matches,
                "f24_model_matches": f24_model_matches,
            })
        links.append({
            "source_type": "AVVISO_ADDEBITO_INPS",
            "relation_status": "CONFIRMED",
            "basis": "EXACT_DOCUMENT_NUMBER",
            "document_number": number,
            "inbox_document_id": original_id,
            "filename": original.get("filename"),
            "drive_file_id": original.get("drive_file_id"),
            "sha256": original.get("sha256") or original.get("file_hash"),
            "matricola_inps": matricola,
            "tax_lines": enriched,
            "payment_evidence_status": (
                "PAID_DOCUMENTED" if enriched and all(
                    row["payment_evidence_status"] == "PAID_DOCUMENTED"
                    for row in enriched if row.get("codice_tributo") == "8050"
                ) and any(row.get("codice_tributo") == "8050" for row in enriched)
                else "NO_PAYMENT_EVIDENCE"
            ),
        })
    return links


def _remediation(claim: dict[str, Any], links: list[dict[str, Any]]) -> dict[str, Any] | None:
    exact_paid_rows = [
        {"source_type": link.get("source_type"), "document_number": link.get("document_number"), **row}
        for link in links for row in (link.get("tax_lines") or [])
        if row.get("payment_evidence_status") == "PAID_DOCUMENTED"
    ]
    if not exact_paid_rows or claim.get("business_status") not in ACTIONABLE_STATUSES:
        return None
    direct_claim_paid = claim.get("documentary_payment_status") in {"PAID_DOCUMENTED", "PARTIAL_DOCUMENTED"}
    action = "VERIFY_REFUND_REQUEST" if direct_claim_paid else "VERIFY_RELIEF_REQUEST"
    return {
        "action": action,
        "status": "ACTION_REQUIRED",
        "reason": (
            "Versamento originario e pagamento della riscossione risultano entrambi documentati: "
            "verificare duplicazione e istanza di rimborso/compensazione."
            if direct_claim_paid else
            "Una quietanza esatta documenta almeno una riga originaria, mentre la pretesa e' ancora "
            "esigibile: verificare con l'ente impositore e, se confermato, chiedere lo sgravio."
        ),
        "paid_source_rows": exact_paid_rows,
    }


async def build_claim_source_plan(db, *, company_id: str) -> list[dict[str, Any]]:
    claims = await db[COLL_TAX_COLLECTION_CLAIMS].find(
        {"company_id": company_id}, {"_id": 0},
    ).to_list(5000)
    quietanze = await db[COLL_QUIETANZE_F24].find(
        {"$or": [{"codice_fiscale": company_id}, {"dati_generali.codice_fiscale": company_id}]},
        {"_id": 0, "pdf_data": 0, "contenuto_b64": 0},
    ).to_list(10000)
    f24_models = await db[COLL_F24].find(
        {"$or": [
            {"codice_fiscale": company_id},
            {"dati_generali.codice_fiscale": company_id},
            {"dati_generali.taxpayer_id": company_id},
        ]},
        {"_id": 0, "pdf_data": 0, "contenuto_b64": 0},
    ).to_list(10000)
    plan: list[dict[str, Any]] = []
    for claim in claims:
        links = [
            *(await _cartella_links(db, claim)),
            *(await _notice_links(db, claim, quietanze, f24_models)),
        ]
        if not links:
            continue
        plan.append({
            "claim_id": claim["id"],
            "collection_number": claim.get("collection_number"),
            "source_obligation_links": links,
            "remediation_alert": _remediation(claim, links),
        })
    return plan


async def apply_claim_source_plan(db, *, company_id: str, actor: str) -> dict[str, Any]:
    from app.services.alert_engine import genera_alert, risolvi_alert

    plan = await build_claim_source_plan(db, company_id=company_id)
    now = datetime.now(timezone.utc).isoformat()
    alerts = 0
    for item in plan:
        remediation = item.get("remediation_alert")
        has_documented_source_payment = any(
            row.get("payment_evidence_status") == "PAID_DOCUMENTED"
            for link in item["source_obligation_links"]
            for row in (link.get("tax_lines") or [])
        )
        await db[COLL_TAX_COLLECTION_CLAIMS].update_one(
            {"company_id": company_id, "id": item["claim_id"]},
            {"$set": {
                "source_obligation_links": item["source_obligation_links"],
                "source_reconciliation_status": (
                    "ACTION_REQUIRED" if remediation else
                    "LINKED_PAYMENT_DOCUMENTED_NO_ACTION" if has_documented_source_payment else
                    "LINKED_NO_ACTION_WITHOUT_PAYMENT_EVIDENCE"
                ),
                "remediation_alert": remediation,
                "source_reconciled_at": now,
                "source_reconciled_by": actor,
                "updated_at": now,
            }},
        )
        code = ALERT_REFUND if remediation and remediation["action"] == "VERIFY_REFUND_REQUEST" else ALERT_RELIEF
        other = ALERT_RELIEF if code == ALERT_REFUND else ALERT_REFUND
        await risolvi_alert(other, item["claim_id"], db, resolved_by=actor)
        if remediation:
            created = await genera_alert(
                code, item["claim_id"], COLL_TAX_COLLECTION_CLAIMS,
                remediation["reason"], db,
                extra={"collection_number": item.get("collection_number"),
                       "paid_source_rows": remediation["paid_source_rows"]},
            )
            alerts += int(created is not None)
        else:
            await risolvi_alert(ALERT_RELIEF, item["claim_id"], db, resolved_by=actor)
            await risolvi_alert(ALERT_REFUND, item["claim_id"], db, resolved_by=actor)
    return {"examined": len(plan), "updated": len(plan), "alerts_created": alerts, "items": plan}
