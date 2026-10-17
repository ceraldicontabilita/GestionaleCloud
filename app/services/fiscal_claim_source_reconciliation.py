"""Collega una pretesa di riscossione alle obbligazioni che l'hanno generata.

Il collegamento e' deliberatamente piu' stretto della normale ricerca:

* un verbale e' confermato solo con numero completo e targa coerente;
* un avviso INPS e' collegato solo col numero integrale dell'atto;
* un versamento F24 prova una riga originaria solo con quietanza e identita'
  contributiva/periodo coerenti. L'importo puo' essere maggiore quando RC01
  documenta il ravvedimento del DM10 originario; il solo modello F24 non basta;
* un residuo AdeR pari a zero non viene trasformato in pagamento.

Il risultato viene salvato sulla pretesa per rendere visibili sia i collegamenti
confermati sia i documenti mancanti. Solo una quietanza esatta o un ravvedimento
documentato puo' generare un invito a verificare sgravio/rimborso.
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
    COLL_TAX_PAYMENTS,
)
from app.services.f24_canonico import normalizza_righe_tributo
from app.services.f24_controllo_incrociato import modello_attivo, parse_periodo_avviso
from app.services.f24_fiscal_evidence import normalize_reference_period


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
    try:
        period = parse_periodo_avviso(value)
    except ValueError:
        return normalize_reference_period({"periodo_riferimento": value})
    if not period["mese"]:
        return None
    return f"{period['anno']:04d}-{period['mese']:02d}"


def _period_range(source: dict[str, Any]) -> tuple[str, str] | None:
    """Un mese singolo storico vale da=a; una fine esplicita va verificata."""
    start = _period(source.get("periodo_da") or source.get("periodo")
                    or source.get("periodo_riferimento"))
    raw_end = source.get("periodo_a")
    end = _period(raw_end) if raw_end not in (None, "") else start
    if not start or not end or end < start:
        return None
    return start, end


def _active_model(document: dict[str, Any]) -> bool:
    # Stesse due condizioni di carica_registro(), anche per i matcher diretti.
    return document.get("status") != "eliminato" and modello_attivo(document)


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
    # La vista canonica recupera anche le righe INPS archiviate in Erario.
    # Si normalizza in memoria: il documento fiscale originale resta intatto.
    try:
        normalized_rows = normalizza_righe_tributo(document)
    except (InvalidOperation, TypeError, ValueError, OverflowError):
        # Un documento con importi illeggibili non certifica un abbinamento.
        return
    for normalized in normalized_rows:
        row = dict(normalized["source_fields"])
        # La vista canonica usa zero anche per un importo non letto. Qui una
        # delega incompleta non puo' certificare l'identita' del ravvedimento.
        raw_debit = next((row[key] for key in ("importo_debito", "debito", "importo")
                          if row.get(key) not in (None, "")), None)
        if isinstance(raw_debit, str):
            raw_debit = raw_debit.replace("€", "").replace(" ", "")
        debit_known = isinstance(row.get("importo_debito_cents"), int) or (
            _money_cents(raw_debit) is not None
        )
        debit_cents = normalized["debit_cents"] if debit_known else None
        row["importo_debito_cents"] = debit_cents
        if normalized["section"] == "INPS":
            row.update({
                "causale": normalized["tax_code"],
                "matricola": normalized["matricola"],
                "periodo_da": normalized["periodo_da"] or normalized["reference_period"],
                "periodo_a": normalized["periodo_a"],
            })
        else:
            row["periodo_riferimento"] = normalized["reference_period"]
        yield {
            "section": normalized["section"],
            "tax_code": normalized["tax_code"],
            "period": _period_range(row),
            "identity": _identifier(normalized.get("matricola")),
            "debit_cents": debit_cents,
            "row": row,
        }


def _payment_reference(
    document: dict[str, Any], row: dict[str, Any], *, basis: str,
    original_amount_cents: int, ravvedimento: bool,
    supporting_f24: dict[str, Any] | None = None,
) -> dict[str, Any]:
    bank = document.get("riscontro_banca") or {}
    general = document.get("dati_generali") or {}
    paid_amount_cents = row.get("importo_debito_cents") if isinstance(
        row.get("importo_debito_cents"), int
    ) else _money_cents(row.get("importo_debito"))
    return {
        "quietanza_id": document.get("id"),
        "protocollo": document.get("protocollo_telematico") or general.get("protocollo_telematico"),
        "data_pagamento": document.get("data_pagamento") or general.get("data_pagamento"),
        "filename": document.get("filename"),
        "drive_file_id": document.get("drive_file_id"),
        "bank_verified": bank.get("stato") == "RISCONTRATO_BANCA",
        "bank_movement_id": bank.get("movimento_id"),
        "matched_row": row,
        "basis": basis,
        "match_type": "RAVVEDIMENTO" if ravvedimento else "EXACT",
        "ravvedimento": ravvedimento,
        "original_amount_cents": original_amount_cents,
        "paid_amount_cents": paid_amount_cents,
        "increase_cents": (
            paid_amount_cents - original_amount_cents
            if paid_amount_cents is not None else None
        ),
        "supporting_f24": supporting_f24,
    }


def _rows_by_semantic_key(document: dict[str, Any]) -> dict[tuple[str, ...], list[int]] | None:
    """Raggruppa tutte le righe di una delega per identita' fiscale verificabile."""
    grouped: dict[tuple[str, ...], list[int]] = {}
    rows = list(_quietanza_rows(document))
    if not rows:
        return None
    for row in rows:
        amount = row.get("debit_cents")
        if not row.get("tax_code") or not row.get("period") or amount is None:
            return None
        key = (
            str(row.get("section") or ""),
            str(row.get("tax_code") or ""),
            str(row.get("identity") or ""),
            *row["period"],
        )
        grouped.setdefault(key, []).append(int(amount))
    for amounts in grouped.values():
        amounts.sort()
    return grouped


def _same_codes_only_higher_amounts(
    model: dict[str, Any], quietanza: dict[str, Any],
) -> bool:
    """Vero solo se tutte le posizioni coincidono e la quietanza e' aumentata.

    Serve per il ravvedimento compilato lasciando erroneamente DM10: non basta
    che una singola riga abbia lo stesso importo o la stessa causale.
    """
    model_rows = _rows_by_semantic_key(model)
    receipt_rows = _rows_by_semantic_key(quietanza)
    if not model_rows or not receipt_rows or model_rows.keys() != receipt_rows.keys():
        return False
    increased = False
    for key, model_amounts in model_rows.items():
        receipt_amounts = receipt_rows[key]
        if len(model_amounts) != len(receipt_amounts):
            return False
        for model_amount, receipt_amount in zip(model_amounts, receipt_amounts):
            if receipt_amount < model_amount:
                return False
            increased = increased or receipt_amount > model_amount
    return increased


def _wrong_code_ravvedimento_support(
    *, obligation_amount: int, period: tuple[str, str], identity: str,
    quietanza: dict[str, Any], models: Iterable[dict[str, Any]],
) -> dict[str, Any] | None:
    """Trova il modello DM10 originario quando la quietanza aumentata resta DM10."""
    for model in models:
        if not _active_model(model):
            continue
        if not _same_codes_only_higher_amounts(model, quietanza):
            continue
        exact_original = any(
            row["tax_code"] == "DM10"
            and row["period"] == period
            and row["debit_cents"] == obligation_amount
            and row["identity"] == identity
            for row in _quietanza_rows(model)
        )
        if not exact_original:
            continue
        return {
            "f24_id": model.get("id"),
            "filename": model.get("filename") or model.get("file_name") or model.get("nome"),
            "drive_file_id": model.get("drive_file_id"),
            "basis": "F24_QUIETANZA_SAME_CODES_ONLY_HIGHER_AMOUNTS",
        }
    return None


def match_quietanza_for_obligation(
    obligation: dict[str, Any], quietanze: Iterable[dict[str, Any]],
    models: Iterable[dict[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Trova quietanze esatte o ravvedimenti univoci e documentati."""
    matches: dict[str, dict[str, Any]] = {}
    period = _period_range(obligation)
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
    if not period or amount is None or (source_code in {"8050", "DM10", "RC01"} and not identity):
        return []
    model_list = list(models)
    for document in quietanze:
        if document.get("entity_status") == "deleted":
            continue
        for row in _quietanza_rows(document):
            if row["tax_code"] not in allowed_codes or row["period"] != period:
                continue
            if identity and row["identity"] != identity:
                continue
            paid_amount = row.get("debit_cents")
            basis = "QUIETANZA_EXACT_IDENTITY_PERIOD_AMOUNT"
            ravvedimento = False
            support = None
            if paid_amount == amount:
                pass
            elif source_code == "8050" and paid_amount is not None and paid_amount > amount:
                if row["tax_code"] == "RC01":
                    basis = "QUIETANZA_RAVVEDIMENTO_RC01_IDENTITY_PERIOD_HIGHER_AMOUNT"
                    ravvedimento = True
                elif row["tax_code"] == "DM10":
                    support = _wrong_code_ravvedimento_support(
                        obligation_amount=amount,
                        period=period,
                        identity=identity,
                        quietanza=document,
                        models=model_list,
                    )
                    if not support:
                        continue
                    basis = "QUIETANZA_RAVVEDIMENTO_WRONG_DM10_SAME_CODES_HIGHER_AMOUNTS"
                    ravvedimento = True
                else:
                    continue
            else:
                continue
            key = str(document.get("protocollo_telematico") or document.get("id") or "")
            if not key:
                continue
            matches.setdefault(key, _payment_reference(
                document,
                row["row"],
                basis=basis,
                original_amount_cents=amount,
                ravvedimento=ravvedimento,
                supporting_f24=support,
            ))
    return list(matches.values())


def match_f24_models_for_obligation(
    obligation: dict[str, Any], models: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Collega il modello esatto, senza trasformarlo in prova di pagamento.

    Oltre alla coincidenza esatta, un RC01 dello stesso contribuente e periodo
    con importo maggiore identifica il ravvedimento del DM10 originario. Il
    modello spiega la regolarizzazione, ma ``payment_evidence`` resta sempre
    falso: soltanto quietanza e banca possono dimostrare il versamento.
    """
    period = _period_range(obligation)
    amount = obligation.get("importo_richiesto_cents")
    if amount is None:
        amount = obligation.get("importo_cents")
    identity = _identifier(obligation.get("matricola_inps"))
    source_code = str(obligation.get("codice_tributo") or "").upper()
    if source_code == "8055" or not period or amount is None or (
        source_code in {"8050", "DM10", "RC01"} and not identity
    ):
        return []
    allowed_codes = {"DM10", "RC01"} if source_code == "8050" else {source_code}
    matches: dict[str, dict[str, Any]] = {}
    for document in models:
        if not _active_model(document):
            continue
        for row in _quietanza_rows(document):
            if row["tax_code"] not in allowed_codes or row["period"] != period:
                continue
            if identity and row["identity"] != identity:
                continue
            model_amount = row.get("debit_cents")
            ravvedimento = (
                source_code == "8050"
                and row["tax_code"] == "RC01"
                and model_amount is not None
                and model_amount > amount
            )
            if model_amount != amount and not ravvedimento:
                continue
            key = str(document.get("id") or "")
            if not key:
                continue
            matches.setdefault(key, {
                "f24_id": key,
                "filename": document.get("filename") or document.get("file_name") or document.get("nome"),
                "drive_file_id": document.get("drive_file_id"),
                "matched_row": row["row"],
                "basis": (
                    "F24_MODEL_RAVVEDIMENTO_RC01_IDENTITY_PERIOD_HIGHER_AMOUNT_NO_PAYMENT_PROOF"
                    if ravvedimento else
                    "F24_MODEL_EXACT_IDENTITY_PERIOD_AMOUNT_NO_PAYMENT_PROOF"
                ),
                "match_type": "RAVVEDIMENTO" if ravvedimento else "EXACT",
                "ravvedimento": ravvedimento,
                "original_amount_cents": amount,
                "model_amount_cents": model_amount,
                "increase_cents": model_amount - amount if ravvedimento else 0,
                "payment_evidence": False,
            })
    return list(matches.values())


def partial_quietanza_candidates_for_obligation(
    obligation: dict[str, Any], quietanze: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Espone versamenti INPS inferiori come proposte di imputazione.

    La quietanza esiste, ma senza un'allocazione confermata non prova quale
    quota di questa specifica pretesa sia soddisfatta. Non entra nei match
    esatti, nei totali pagati o nelle richieste di sgravio automatiche.
    """
    period = _period_range(obligation)
    identity = _identifier(obligation.get("matricola_inps"))
    amount = obligation.get("importo_richiesto_cents")
    if amount is None:
        amount = obligation.get("importo_cents")
    if str(obligation.get("codice_tributo") or "").upper() != "8050" or (
        not period or not identity or not isinstance(amount, int) or amount <= 0
    ):
        return []
    candidates: dict[tuple[str, int, int], dict[str, Any]] = {}
    for document in quietanze:
        if document.get("entity_status") == "deleted":
            continue
        document_key = str(document.get("protocollo_telematico") or document.get("id") or "")
        if not document_key:
            continue
        for index, row in enumerate(_quietanza_rows(document)):
            paid = row.get("debit_cents")
            if row["tax_code"] not in {"DM10", "RC01"} or row["period"] != period or (
                row["identity"] != identity or paid is None or not 0 < paid < amount
            ):
                continue
            reference = _payment_reference(
                document, row["row"], basis="QUIETANZA_PARTIAL_IDENTITY_PERIOD_AMOUNT_REVIEW",
                original_amount_cents=amount, ravvedimento=False,
            )
            reference.pop("increase_cents", None)
            candidates.setdefault((document_key, index, paid), {
                **reference, "match_type": "PARTIAL_CANDIDATE",
                "relation_status": "REVIEW_REQUIRED", "payment_evidence": False,
                "row_index": index,
            })
    return list(candidates.values())


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
            payment_matches = match_quietanza_for_obligation(obligation, quietanze, f24_models)
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
                "partial_payment_candidates": partial_quietanza_candidates_for_obligation(
                    obligation, quietanze,
                ),
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


def _direct_collection_payments(
    claim: dict[str, Any], payments_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Restituisce solo prove documentali di pagamento gia' collegate alla pretesa.

    Lo stato del portale e il residuo zero non sono prove di pagamento. Inoltre
    una registrazione tecnica F24 non va ricontata come pagamento diretto della
    riscossione: qui servono ricevute della cartella o delle sue rate.
    """
    result: list[dict[str, Any]] = []
    for payment_id in claim.get("linked_payment_ids") or []:
        payment = payments_by_id.get(str(payment_id))
        if not payment or not payment.get("documentary_evidence"):
            continue
        if payment.get("source_kind") == "F24_DOCUMENT_EVIDENCE":
            continue
        result.append({
            "payment_id": payment.get("id"),
            "source_type": payment.get("source_type"),
            "source_id": payment.get("source_id"),
            "document_id": payment.get("document_id"),
            "amount": payment.get("operation_amount") or payment.get("amount"),
            "payment_date": payment.get("payment_date"),
            "bank_verified": bool(payment.get("bank_verified")),
        })
    return result


def _remediation(
    claim: dict[str, Any], links: list[dict[str, Any]],
    direct_collection_payments: Iterable[dict[str, Any]] = (),
) -> dict[str, Any] | None:
    exact_paid_rows = [
        {"source_type": link.get("source_type"), "document_number": link.get("document_number"), **row}
        for link in links for row in (link.get("tax_lines") or [])
        if row.get("payment_evidence_status") == "PAID_DOCUMENTED"
    ]
    if not exact_paid_rows:
        return None
    direct_payments = list(direct_collection_payments)
    direct_claim_paid = bool(direct_payments) or claim.get("documentary_payment_status") in {
        "PAID_DOCUMENTED", "PARTIAL_DOCUMENTED",
    }
    if not direct_claim_paid and claim.get("business_status") not in ACTIONABLE_STATUSES:
        return None
    action = "VERIFY_REFUND_REQUEST" if direct_claim_paid else "VERIFY_RELIEF_REQUEST"
    result = {
        "action": action,
        "status": "ACTION_REQUIRED",
        "reason": (
            "Versamento originario e pagamento della riscossione risultano entrambi documentati: "
            "verificare duplicazione e istanza di rimborso/compensazione."
            if direct_claim_paid else
            "Una quietanza esatta o di ravvedimento documenta almeno una riga originaria, mentre la pretesa e' ancora "
            "esigibile: verificare con l'ente impositore e, se confermato, chiedere lo sgravio."
        ),
        "paid_source_rows": exact_paid_rows,
    }
    if direct_payments:
        result["direct_collection_payments"] = direct_payments
    return result


async def build_claim_source_plan(db, *, company_id: str) -> list[dict[str, Any]]:
    claims = await db[COLL_TAX_COLLECTION_CLAIMS].find(
        {"company_id": company_id}, {"_id": 0},
    ).to_list(5000)
    quietanze = await db[COLL_QUIETANZE_F24].find(
        {"$or": [{"codice_fiscale": company_id}, {"dati_generali.codice_fiscale": company_id}]},
        {"_id": 0, "pdf_data": 0, "contenuto_b64": 0},
    ).to_list(10000)
    f24_models = await db[COLL_F24].find(
        {"status": {"$ne": "eliminato"}, "$or": [
            {"codice_fiscale": company_id},
            {"dati_generali.codice_fiscale": company_id},
            {"dati_generali.taxpayer_id": company_id},
        ]},
        {"_id": 0, "pdf_data": 0, "contenuto_b64": 0},
    ).to_list(10000)
    f24_models = [document for document in f24_models if _active_model(document)]
    tax_payments = await db[COLL_TAX_PAYMENTS].find(
        {"company_id": company_id}, {"_id": 0, "pdf_data": 0, "contenuto_b64": 0},
    ).to_list(10000)
    payments_by_id = {str(item.get("id")): item for item in tax_payments if item.get("id")}
    plan: list[dict[str, Any]] = []
    for claim in claims:
        links = [
            *(await _cartella_links(db, claim)),
            *(await _notice_links(db, claim, quietanze, f24_models)),
        ]
        if not links:
            continue
        direct_payments = _direct_collection_payments(claim, payments_by_id)
        plan.append({
            "claim_id": claim["id"],
            "collection_number": claim.get("collection_number"),
            "source_obligation_links": links,
            "remediation_alert": _remediation(claim, links, direct_payments),
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
                       "paid_source_rows": remediation["paid_source_rows"],
                       "direct_collection_payments": remediation.get(
                           "direct_collection_payments", []
                       )},
            )
            alerts += int(created is not None)
        else:
            await risolvi_alert(ALERT_RELIEF, item["claim_id"], db, resolved_by=actor)
            await risolvi_alert(ALERT_REFUND, item["claim_id"], db, resolved_by=actor)
    return {"examined": len(plan), "updated": len(plan), "alerts_created": alerts, "items": plan}
