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
from app.services.fiscal_collection_payment_context import load_collection_payment_context
from app.services.f24_controllo_incrociato import modello_attivo


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
    if re.fullmatch(r"(?:19|20)\d{2}", text):
        return text
    match = re.fullmatch(r"(0?[1-9]|1[0-2])[/.-]((?:19|20)\d{2})", text)
    if match:
        return f"{int(match.group(1)):02d}/{match.group(2)}"
    match = re.fullmatch(r"((?:19|20)\d{2})[/.-](0?[1-9]|1[0-2])", text)
    return f"{int(match.group(2)):02d}/{match.group(1)}" if match else None


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
    """Legge tutte le sezioni senza perdere gli identificativi della posizione.

    Le righe INAIL non hanno necessariamente un periodo fiscale: sede, ditta,
    codice di controllo, riferimento e causale identificano il versamento.
    Se questi dati sono incompleti il confronto dell'intera delega si ferma.
    """
    for section in ("sezione_inps", "sezione_erario", "sezione_regioni", "sezione_tributi_locali", "sezione_inail"):
        for row in document.get(section) or []:
            period = _period(
                row.get("periodo_riferimento") or row.get("periodo_da")
                or row.get("anno_riferimento") or row.get("anno")
            )
            if section == "sezione_regioni":
                entity = _identifier(row.get("codice_regione"))
            elif section == "sezione_tributi_locali":
                entity = _identifier(row.get("codice_comune") or row.get("codice_ente"))
            elif section == "sezione_inps":
                entity = _identifier(row.get("codice_sede"))
            elif section == "sezione_inail":
                entity = _identifier(row.get("codice_sede") or row.get("codice_ufficio"))
            else:
                entity = _identifier(row.get("codice_ufficio"))
            identity = _identifier(row.get("matricola")) if section == "sezione_inps" else ""
            code = str((row.get("causale") if section in {"sezione_inps", "sezione_inail"}
                        else row.get("codice_tributo")) or "").strip().upper()
            identity_complete = bool(identity and _inps_period_range(row)) if section == "sezione_inps" else True
            if section in {"sezione_regioni", "sezione_tributi_locali"}:
                identity_complete = bool(entity)
            if section == "sezione_inail":
                reference = _identifier(row.get("numero_riferimento"))
                parts = (
                    entity, _identifier(row.get("codice_ditta")),
                    _identifier(row.get("codice_controllo") or row.get("cc")), reference,
                )
                identity = "|".join(parts)
                identity_complete = all(parts) and bool(code)
                # Non inventare un mese per il premio INAIL.
                period = f"INAIL:{reference}" if reference else None
            debit = row.get("importo_debito_cents") if isinstance(
                row.get("importo_debito_cents"), int
            ) else _money_cents(row.get("importo_debito"))
            credit = row.get("importo_credito_cents") if isinstance(
                row.get("importo_credito_cents"), int
            ) else _money_cents(row.get("importo_credito", 0))
            if debit is None and credit is not None and credit > 0:
                debit = 0
            yield {
                "section": "INPS" if section == "sezione_inps" else section,
                "tax_code": code,
                "period": period,
                "period_end": (_period(row.get("periodo_a")) if row.get("periodo_a") else period),
                "identity": identity,
                "entity_code": entity,
                "identity_complete": identity_complete,
                "debit_cents": debit,
                "credit_cents": credit,
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


def _rows_by_semantic_key(document: dict[str, Any]) -> dict[tuple[str, ...], list[tuple[int, int]]] | None:
    """Raggruppa tutte le righe di una delega per identita' fiscale verificabile."""
    grouped: dict[tuple[str, ...], list[tuple[int, int]]] = {}
    rows = list(_quietanza_rows(document))
    if not rows:
        return None
    for row in rows:
        amount, credit = row.get("debit_cents"), row.get("credit_cents")
        if (not row.get("tax_code") or not row.get("period") or not row.get("period_end") or amount is None
                or credit is None or row.get("identity_complete") is False):
            return None
        key = (
            str(row.get("section") or ""),
            str(row.get("tax_code") or ""),
            str(row.get("identity") or ""),
            str(row.get("entity_code") or ""),
            str(row.get("period") or ""),
            str(row.get("period_end") or ""),
        )
        grouped.setdefault(key, []).append((int(amount), int(credit)))
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
        for (model_amount, model_credit), (receipt_amount, receipt_credit) in zip(model_amounts, receipt_amounts):
            if receipt_amount < model_amount or receipt_credit != model_credit:
                return False
            increased = increased or receipt_amount > model_amount
    return increased


def _wrong_code_ravvedimento_support(
    *, obligation_amount: int, period: str, identity: str,
    quietanza: dict[str, Any], models: Iterable[dict[str, Any]],
) -> dict[str, Any] | None:
    """Trova il modello DM10 originario quando la quietanza aumentata resta DM10."""
    if not identity:
        return None
    for model in models:
        if model.get("status") == "eliminato" or not modello_attivo(model):
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


def _inps_period_range(source: dict[str, Any]) -> tuple[str, str] | None:
    start = _period(source.get("periodo_da") or source.get("periodo")
                    or source.get("periodo_riferimento"))
    raw_end = source.get("periodo_a")
    end = _period(raw_end) if raw_end not in (None, "") else start
    # Un anno fiscale non identifica il mese di una posizione contributiva.
    if not start or not end or not re.fullmatch(r"\d{2}/\d{4}", start) or not re.fullmatch(r"\d{2}/\d{4}", end):
        return None
    if (end[3:], end[:2]) < (start[3:], start[:2]):
        return None
    return start, end


def _same_obligation_position(obligation: dict[str, Any], row: dict[str, Any]) -> bool:
    source_code = str(obligation.get("codice_tributo") or "").upper()
    if source_code in {"8050", "DM10", "RC01"}:
        identity = _identifier(obligation.get("matricola_inps"))
        period = _inps_period_range(obligation)
        return bool(identity and row["section"] == "INPS" and row["identity"] == identity
                    and period and _inps_period_range(row["row"]) == period)
    if row["section"] == "sezione_regioni":
        entity = _identifier(obligation.get("codice_regione"))
        return bool(entity and entity == row.get("entity_code"))
    if row["section"] == "sezione_tributi_locali":
        entity = _identifier(obligation.get("codice_comune") or obligation.get("codice_ente"))
        return bool(entity and entity == row.get("entity_code"))
    return not any(obligation.get(field) for field in ("codice_regione", "codice_comune", "codice_ente"))


def match_quietanza_for_obligation(
    obligation: dict[str, Any], quietanze: Iterable[dict[str, Any]],
    models: Iterable[dict[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Trova quietanze esatte o ravvedimenti univoci e documentati."""
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
    if not period or not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        return []
    model_list = list(models)
    for document in quietanze:
        if document.get("entity_status") == "deleted" or document.get("status") == "eliminato":
            continue
        for row_index, row in enumerate(_quietanza_rows(document)):
            if row["tax_code"] not in allowed_codes or row["period"] != period:
                continue
            if not _same_obligation_position(obligation, row):
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
            general = document.get("dati_generali") or {}
            document_key = str(document.get("protocollo_telematico") or general.get("protocollo_telematico")
                               or document.get("id") or "")
            if not document_key:
                continue
            # Due righe della stessa quietanza non sono un unico candidato.
            # La stessa riga duplicata in archivio con lo stesso protocollo si
            # deduplica; contenuti discordanti restano candidati distinti.
            key = repr((document_key, row_index, row["section"], row["tax_code"],
                        row["identity"], row["period"], row.get("entity_code"), paid_amount))
            matches.setdefault(key, _payment_reference(
                document,
                row["row"],
                basis=basis,
                original_amount_cents=amount,
                ravvedimento=ravvedimento,
                supporting_f24=support,
            ))
            matches[key]["receipt_row_key"] = repr((document_key, row_index, row["section"]))
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
    period = _period(obligation.get("periodo_da") or obligation.get("periodo"))
    amount = obligation.get("importo_richiesto_cents")
    if amount is None:
        amount = obligation.get("importo_cents")
    source_code = str(obligation.get("codice_tributo") or "").upper()
    if source_code == "8055" or not period or not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
        return []
    allowed_codes = {"DM10", "RC01"} if source_code == "8050" else {source_code}
    matches: dict[str, dict[str, Any]] = {}
    for document in models:
        if document.get("status") == "eliminato" or not modello_attivo(document):
            continue
        for row in _quietanza_rows(document):
            if row["tax_code"] not in allowed_codes or row["period"] != period:
                continue
            if not _same_obligation_position(obligation, row):
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
    ).to_list(None)
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
                    "REVIEW_REQUIRED" if row.get("codice_tributo") == "8050" and (
                        not _identifier(matricola) or not _inps_period_range(obligation)
                    ) else
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


def _resolve_payment_match_ambiguities(plan: list[dict[str, Any]]) -> None:
    """Una riga di quietanza non paga due obbligazioni diverse.

    Il controllo avviene sull'intero piano della societa', prima degli alert:
    scegliere il primo avviso letto nasconderebbe gli altri candidati.
    Copie dello stesso atto/riga non moltiplicano l'obbligazione.
    """
    uses: dict[str, set[tuple[Any, ...]]] = {}
    rows: list[tuple[dict[str, Any], set[str]]] = []
    for item in plan:
        for link in item["source_obligation_links"]:
            if link.get("source_type") != "AVVISO_ADDEBITO_INPS":
                continue
            for index, row in enumerate(link.get("tax_lines") or []):
                obligation_key = (
                    link.get("document_number"), row.get("progressivo", index),
                    row.get("codice_tributo"), _identifier(row.get("matricola_inps")),
                    row.get("periodo_da"), row.get("periodo_a"), row.get("importo_richiesto_cents"),
                )
                evidence_keys = {match["receipt_row_key"] for match in row.get("payment_matches") or []}
                rows.append((row, evidence_keys))
                for key in evidence_keys:
                    uses.setdefault(key, set()).add(obligation_key)
    for row, evidence_keys in rows:
        if any(len(uses[key]) > 1 for key in evidence_keys):
            row["payment_evidence_status"] = "REVIEW_REQUIRED"
            row["payment_evidence_review_reason"] = "RECEIPT_ROW_MATCHES_MULTIPLE_OBLIGATIONS"
    for item in plan:
        for link in item["source_obligation_links"]:
            if link.get("source_type") != "AVVISO_ADDEBITO_INPS":
                continue
            statuses = [row["payment_evidence_status"] for row in link.get("tax_lines") or []
                        if row.get("codice_tributo") == "8050"]
            link["payment_evidence_status"] = (
                "PAID_DOCUMENTED" if statuses and all(status == "PAID_DOCUMENTED" for status in statuses)
                else "REVIEW_REQUIRED" if "REVIEW_REQUIRED" in statuses else "NO_PAYMENT_EVIDENCE"
            )


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
    direct_claim_paid = bool(direct_payments)
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
    ).to_list(None)
    quietanze = await db[COLL_QUIETANZE_F24].find(
        {"$or": [{"codice_fiscale": company_id}, {"dati_generali.codice_fiscale": company_id}]},
        {"_id": 0, "pdf_data": 0, "contenuto_b64": 0},
    ).to_list(None)
    f24_models = await db[COLL_F24].find(
        {"$or": [
            {"codice_fiscale": company_id},
            {"dati_generali.codice_fiscale": company_id},
            {"dati_generali.taxpayer_id": company_id},
        ]},
        {"_id": 0, "pdf_data": 0, "contenuto_b64": 0},
    ).to_list(None)
    tax_payments = await db[COLL_TAX_PAYMENTS].find(
        {"company_id": company_id}, {"_id": 0, "pdf_data": 0, "contenuto_b64": 0},
    ).to_list(None)
    payments_by_id = {str(item.get("id")): item for item in tax_payments if item.get("id")}
    payment_context = await load_collection_payment_context(
        db, company_id=company_id, claims=claims, payments_by_id=payments_by_id,
    )
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
        })
    _resolve_payment_match_ambiguities(plan)
    claims_by_id = {str(claim["id"]): claim for claim in claims}
    for item in plan:
        context = payment_context.get(str(item["claim_id"]), {})
        ambiguous = context.get("ambiguous_payment_ids") or []
        item["collection_payment_review"] = {"ambiguous_payment_ids": ambiguous}
        item["remediation_alert"] = None if ambiguous else _remediation(
            claims_by_id[str(item["claim_id"])], item["source_obligation_links"],
            context.get("documented_payments") or [],
        )
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
                "collection_payment_review": item["collection_payment_review"],
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
