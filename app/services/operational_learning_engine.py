"""Assistente operativo fail-closed per GestionaleCloud.

Il servizio osserva le collezioni di dominio in sola lettura e scrive soltanto
nelle collezioni di memoria dell'assistente.  Non riconcilia, non paga e non
modifica fatture, movimenti bancari, F24, cedolini o dipendenti.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from app.db_collections import (
    COLL_ADMIN_ANOMALIES,
    COLL_CASE_MEMORY,
    COLL_CEDOLINI,
    COLL_DECISION_QUESTIONS,
    COLL_DIPENDENTI,
    COLL_EXPECTED_EVENTS,
    COLL_F24,
    COLL_KNOWLEDGE_SOURCES,
    COLL_LEARNED_PATTERNS,
    COLL_OPERATIONAL_FACTS,
    COLL_PRIMA_NOTA_SALARI,
)


CENT = Decimal("0.01")
ASSISTANT_WRITE_COLLECTIONS = frozenset(
    {
        COLL_OPERATIONAL_FACTS,
        COLL_LEARNED_PATTERNS,
        COLL_EXPECTED_EVENTS,
        COLL_ADMIN_ANOMALIES,
        COLL_DECISION_QUESTIONS,
        COLL_CASE_MEMORY,
        COLL_KNOWLEDGE_SOURCES,
    }
)
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
TERMINAL_REVIEW_STATUSES = frozenset({"answered", "resolved", "dismissed", "closed"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _id(prefix: str, *parts: Any) -> str:
    return f"{prefix}_{_hash(list(parts))[:24]}"


def _decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(CENT, rounding=ROUND_HALF_UP)
    if value in (None, ""):
        return Decimal("0.00")
    raw = str(value).strip().replace("€", "").replace(" ", "")
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return Decimal(raw).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _cents(value: Any) -> int:
    return int(_decimal(value) * 100)


def _money(value: Any) -> float:
    return float(_decimal(value))


def _first(doc: Dict[str, Any], paths: Sequence[str], default: Any = None) -> Any:
    for path in paths:
        current: Any = doc
        for part in path.split("."):
            if not isinstance(current, dict) or part not in current:
                current = None
                break
            current = current[part]
        if current not in (None, ""):
            return current
    return default


def _parse_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _section_rows(value: Any) -> List[Dict[str, Any]]:
    """Restituisce le righe di una sezione F24 nelle forme canoniche e legacy."""
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict):
        for key in ("righe", "tributi", "dettaglio", "items"):
            rows = value.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
        if any(value.get(key) not in (None, "") for key in ("codice", "codice_tributo", "causale")):
            return [value]
    return []


def _period_year_month(row: Dict[str, Any]) -> tuple[Optional[int], Optional[int]]:
    """Normalizza annualita' e mese fiscali senza usare la data di pagamento.

    La data dell'addebito F24 e il periodo del tributo sono evidenze diverse:
    la prima non puo' colmare un'annualita' o un mese assenti nella singola riga.
    """
    raw_year = str(
        _first(row, ("anno_riferimento", "anno", "anno_di_riferimento"), "") or ""
    ).strip()
    year_digits = re.sub(r"\D", "", raw_year)
    year = int(year_digits[:4]) if len(year_digits) >= 4 else None

    raw_period = str(
        _first(
            row,
            ("periodo_riferimento", "riferimento", "mese_riferimento", "mese", "periodo"),
            "",
        )
        or ""
    ).strip()
    digits = re.sub(r"\D", "", raw_period)
    month: Optional[int] = None

    if len(digits) == 6:
        if digits[:4].startswith(("19", "20", "21", "22")):
            year = int(digits[:4])
            month = int(digits[4:6])
        elif digits[-4:].startswith(("19", "20", "21", "22")):
            month = int(digits[:2])
            year = int(digits[-4:])
    elif len(digits) == 4:
        if digits.startswith(("19", "20", "21", "22")) and year is None:
            year = int(digits)
        elif year is not None:
            # Il campo F24 "rateazione/regione/prov./mese rif." puo'
            # arrivare come 0101: il primo gruppo identifica il mese.
            first = int(digits[:2])
            last = int(digits[-2:])
            month = first if 1 <= first <= 12 else last
    elif 1 <= len(digits) <= 2:
        month = int(digits)

    if month is not None and not 1 <= month <= 12:
        month = None
    return year, month


def confidence_from_evidence(positive: int, negative: int = 0, base: float = 0.50) -> float:
    """Curva volutamente prudente: una controprova pesa più di una conferma."""
    score = base + 0.08 * min(max(positive, 0), 5) - 0.18 * min(max(negative, 0), 4)
    return round(max(0.05, min(0.97, score)), 3)


def learning_level(confidence: float, confirmations: int) -> str:
    if confidence < 0.70:
        return "osservazione"
    if confidence < 0.88:
        return "proposta"
    if confidence < 0.96 or confirmations < 5:
        return "proposta_forte"
    return "candidata_automazione"


def expected_vs_actual(expected: Any, actual: Any) -> Dict[str, Any]:
    expected_cents = _cents(expected)
    actual_cents = _cents(actual)
    delta_cents = expected_cents - actual_cents
    if expected_cents <= 0:
        status = "not_measurable"
    elif actual_cents <= 0:
        status = "missing"
    elif delta_cents > 0:
        status = "partial"
    elif delta_cents < 0:
        status = "overpaid"
    else:
        status = "matched"
    return {
        "expected": expected_cents / 100,
        "actual": actual_cents / 100,
        "delta": delta_cents / 100,
        "status": status,
        "comparison": "exact_cents",
    }


def build_driver_fact(
    targa: str,
    driver_id: str,
    *,
    valid_from: str,
    valid_to: Optional[str] = None,
    confirmations: int = 1,
    contradictions: int = 0,
    sources: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    plate = re.sub(r"\s+", "", str(targa or "")).upper()
    if not plate or not driver_id or not _parse_date(valid_from):
        raise ValueError("Targa, dipendente e data iniziale sono obbligatori")
    confidence = confidence_from_evidence(confirmations, contradictions, base=0.66)
    return {
        "id": _id("fact", "targa_driver", plate, driver_id, valid_from),
        "fact_type": "targa_driver",
        "subject": {"type": "veicolo", "key": plate},
        "predicate": "driver_assegnato",
        "object": {"type": "dipendente", "id": driver_id},
        "valid_from": _parse_date(valid_from).isoformat(),
        "valid_to": _parse_date(valid_to).isoformat() if _parse_date(valid_to) else None,
        "confirmations": max(confirmations, 0),
        "contradictions": max(contradictions, 0),
        "confidence": confidence,
        "learning_level": learning_level(confidence, confirmations),
        "sources": sources or [],
        "status": "active",
        "updated_at": _now(),
    }


def infer_periodic_pattern(
    observations: Iterable[Dict[str, Any]],
    *,
    pattern_type: str,
    key: str,
    min_months: int = 3,
) -> Optional[Dict[str, Any]]:
    parsed: List[tuple[date, int]] = []
    for item in observations:
        observed_on = _parse_date(item.get("date") or item.get("data"))
        if observed_on:
            parsed.append((observed_on, _cents(item.get("amount") or item.get("importo"))))
    if len(parsed) < min_months:
        return None
    months = sorted({(day.year, day.month) for day, _ in parsed})
    span = (months[-1][0] - months[0][0]) * 12 + months[-1][1] - months[0][1] + 1
    density = len(months) / max(span, 1)
    if len(months) < min_months or density < 0.75:
        return None
    days = sorted(day.day for day, _ in parsed)
    amounts = sorted(value for _, value in parsed if value > 0)
    median_cents = amounts[len(amounts) // 2] if amounts else 0
    confidence = confidence_from_evidence(len(months), 0, base=0.54)
    return {
        "id": _id("pattern", pattern_type, key),
        "pattern_type": pattern_type,
        "key": key,
        "frequency": "monthly",
        "observations": len(parsed),
        "distinct_months": len(months),
        "density": round(density, 3),
        "expected_day_from": max(1, min(days) - 2),
        "expected_day_to": min(28, max(days) + 2),
        "median_amount": median_cents / 100,
        "confidence": confidence,
        "learning_level": learning_level(confidence, len(months)),
        "status": "learned",
        "updated_at": _now(),
    }


def expected_event_from_pattern(pattern: Dict[str, Any], year: int, month: int) -> Dict[str, Any]:
    if not 1 <= int(month) <= 12:
        raise ValueError("Mese non valido")
    event_id = _id("expected", pattern["id"], f"{int(year):04d}-{int(month):02d}")
    return {
        "id": event_id,
        "pattern_id": pattern["id"],
        "event_type": pattern["pattern_type"],
        "key": pattern["key"],
        "year": int(year),
        "month": int(month),
        "expected_day_from": pattern.get("expected_day_from"),
        "expected_day_to": pattern.get("expected_day_to"),
        "expected_amount": _money(pattern.get("median_amount")),
        "confidence": pattern.get("confidence", 0),
        "status": "expected",
        "evidence": [],
        "created_at": _now(),
        "updated_at": _now(),
    }


def build_tax_obligation(
    *,
    tax_code: str,
    year: int,
    due_date: str,
    expected_amount: Any,
    source_id: str,
    period: Optional[str] = None,
    entity: Optional[str] = None,
) -> Dict[str, Any]:
    """Costruisce un obbligo atteso senza creare o simulare un pagamento.

    L'identificativo incorpora la fonte e il periodo, mentre l'importo viene
    normalizzato al centesimo. Una fonte vuota o una scadenza non valida sono
    respinte: un obbligo fiscale senza provenienza non entra in memoria.
    """
    code = str(tax_code or "").strip().upper()
    parsed_due_date = _parse_date(due_date)
    source = str(source_id or "").strip()
    if not code or not parsed_due_date or not source or int(year) < 2000:
        raise ValueError("Codice tributo, anno, scadenza e fonte sono obbligatori")
    if _cents(expected_amount) <= 0:
        raise ValueError("L'importo atteso deve essere maggiore di zero")
    raw_period = str(period or "").strip()
    period_year, period_month = _period_year_month(
        {"periodo_riferimento": raw_period, "anno_riferimento": int(year)}
    )
    if period_year is not None and period_year != int(year):
        raise ValueError("L'anno del periodo non coincide con l'annualita' dichiarata")
    period_key = (
        f"{int(year):04d}-{period_month:02d}"
        if period_month is not None
        else raw_period or f"{int(year):04d}"
    )
    return {
        "id": _id("expected", "tax_obligation", code, int(year), period_key, source),
        "event_type": "tax_obligation",
        "key": code,
        "year": int(year),
        "month": period_month,
        "period": period_key,
        "due_date": parsed_due_date.isoformat(),
        "expected_amount": _money(expected_amount),
        "actual_amount": 0.0,
        "status": "expected",
        "entity": entity,
        "source": {"id": source},
        "comparison": "exact_cents",
        "must_not_auto_pay": True,
        "created_at": _now(),
        "updated_at": _now(),
    }


def reconcile_expected_event(
    event: Dict[str, Any],
    actual_amount: Any,
    *,
    evidence: Optional[List[Dict[str, Any]]] = None,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    """Confronta un evento atteso con evidenze reali, sempre al centesimo."""
    comparison = expected_vs_actual(event.get("expected_amount"), actual_amount)
    status = comparison["status"]
    due_date = _parse_date(event.get("due_date"))
    if status == "missing" and due_date and (today or date.today()) > due_date:
        status = "overdue"
    return {
        **event,
        "actual_amount": comparison["actual"],
        "delta_amount": comparison["delta"],
        "status": status,
        "comparison": "exact_cents",
        "evidence": evidence or [],
        "last_reconciled_at": _now(),
        "updated_at": _now(),
    }


def payroll_residual_question(cedolino: Dict[str, Any], paid_amount: Any) -> Optional[Dict[str, Any]]:
    expected = _first(
        cedolino,
        ("netto", "netto_mese", "importo_netto", "importo_busta", "netto_da_pagare"),
        0,
    )
    comparison = expected_vs_actual(expected, paid_amount)
    if comparison["status"] not in {"missing", "partial"}:
        return None
    employee = _first(
        cedolino,
        ("nome_dipendente", "dipendente_nome", "dipendente", "beneficiario"),
        "Dipendente",
    )
    year = _first(cedolino, ("anno", "periodo.anno"))
    month = _first(cedolino, ("mese", "periodo.mese"))
    subject_id = str(cedolino.get("id") or cedolino.get("_id") or _id("cedolino", employee, year, month))
    residual = comparison["delta"]
    return {
        "id": _id("question", "payroll_residual", subject_id, _cents(residual)),
        "question_type": "payroll_residual",
        "severity": "high" if _cents(residual) >= 10000 else "medium",
        "title": f"Saldo stipendio ancora da verificare: {employee}",
        "question": (
            f"Il netto del periodo {month}/{year} è € {comparison['expected']:.2f}; "
            f"i pagamenti documentati sono € {comparison['actual']:.2f}. "
            f"Verificare il residuo di € {residual:.2f}."
        ),
        "options": [
            {"id": "verifica_pagamenti", "label": "Verifica altri pagamenti", "action": "reconcile"},
            {"id": "accordo", "label": "Documenta accordo o compensazione", "action": "request_details"},
            {"id": "consulente", "label": "Chiedi al consulente", "action": "escalate"},
        ],
        "subject": {"type": "cedolino", "id": subject_id},
        "evidence": {
            **comparison,
            "residuo": residual,
            "regola": "pagamento_parziale_non_chiude_il_cedolino",
        },
        "status": "open",
        "created_at": _now(),
    }


def _expiry_question(
    employee: Dict[str, Any], expiry: date, *, question_type: str, label: str, today: Optional[date] = None
) -> Optional[Dict[str, Any]]:
    today = today or date.today()
    days = (expiry - today).days
    if days > 30:
        return None
    name = _first(employee, ("nome_completo", "cognome_nome", "nome"), "Dipendente")
    employee_id = str(employee.get("id") or employee.get("_id") or name)
    if days < 0:
        title = f"{label} scaduto: {name}"
        question_text = (
            f"{label} e' scaduto da {abs(days)} giorni ({expiry.isoformat()}). "
            "Verificare subito l'azione amministrativa."
        )
    elif days == 0:
        title = f"{label} in scadenza: {name}"
        question_text = (
            f"{label} scade oggi ({expiry.isoformat()}). "
            "Verificare subito l'azione amministrativa."
        )
    else:
        title = f"{label} in scadenza: {name}"
        question_text = (
            f"{label} scade tra {days} giorni ({expiry.isoformat()}). "
            "Verificare l'azione amministrativa."
        )
    return {
        "id": _id("question", question_type, employee_id, expiry.isoformat()),
        "question_type": question_type,
        "severity": "critical" if days <= 3 else ("high" if days <= 14 else "medium"),
        "title": title,
        "question": question_text,
        "options": (
            [
                {"id": "proroga", "label": "Valuta proroga", "action": "request_details"},
                {"id": "trasforma", "label": "Valuta trasformazione", "action": "request_details"},
                {"id": "cessa", "label": "Valuta cessazione", "action": "request_details"},
                {"id": "consulente", "label": "Chiedi al consulente", "action": "escalate"},
            ]
            if question_type == "contract_expiry"
            else [
                {"id": "rinnova", "label": "Avvia rinnovo", "action": "request_details"},
                {"id": "consulente", "label": "Chiedi al consulente", "action": "escalate"},
                {"id": "gia_risolto", "label": "Già risolto", "action": "confirm_outcome"},
            ]
        ),
        "subject": {"type": "dipendente", "id": employee_id},
        "evidence": {"expiry": expiry.isoformat(), "days_to_expiry": days},
        "requires_source_refresh": True,
        "requires_normative_refresh": True,
        "status": "open",
        "created_at": _now(),
    }


def contract_expiry_question(
    employee: Dict[str, Any], expiry: date, today: Optional[date] = None
) -> Optional[Dict[str, Any]]:
    return _expiry_question(
        employee, expiry, question_type="contract_expiry", label="Contratto", today=today
    )


def identity_document_expiry_question(
    employee: Dict[str, Any], expiry: date, today: Optional[date] = None
) -> Optional[Dict[str, Any]]:
    return _expiry_question(
        employee, expiry, question_type="identity_document_expiry", label="Documento di identità", today=today
    )


def tax_misallocation_assessment(
    *,
    expected_year: int,
    declared_year: int,
    tax_code: str,
    expected_amount: Any,
    paid_amount: Any,
    bank_verified: bool,
    period_match: bool = True,
    compatible_declared_year_debt: bool = False,
) -> Dict[str, Any]:
    """Valuta, senza concludere troppo, un F24 con annualità differente.

    L'esistenza di un debito compatibile nell'anno dichiarato è una vera
    contro-ipotesi: abbassa la confidenza e rende la conclusione ambigua.
    """
    amount_match = _cents(expected_amount) == _cents(paid_amount)
    year_mismatch = int(expected_year) != int(declared_year)
    prerequisites = amount_match and bool(period_match) and bool(bank_verified) and year_mismatch
    negatives = 1 if compatible_declared_year_debt else 0
    positives = sum(bool(value) for value in (amount_match, period_match, bank_verified, year_mismatch))
    confidence = confidence_from_evidence(positives, negatives, base=0.48)
    if not prerequisites:
        conclusion = "not_supported"
        confidence = min(confidence, 0.45)
    elif compatible_declared_year_debt:
        conclusion = "ambiguous_compatible_declared_year_debt"
        confidence = min(confidence, 0.62)
    else:
        conclusion = "possible_year_misallocation"
    return {
        "hypothesis": "f24_possible_year_misallocation",
        "conclusion": conclusion,
        "confidence": round(confidence, 3),
        "severity": "critical" if prerequisites and not compatible_declared_year_debt else "high",
        "evidence": {
            "codice_tributo": str(tax_code),
            "anno_atteso": int(expected_year),
            "anno_f24": int(declared_year),
            "importo_atteso": _money(expected_amount),
            "importo_pagato": _money(paid_amount),
            "importo_coincide_al_centesimo": amount_match,
            "periodo_compatibile": bool(period_match),
            "banca_verificata": bool(bank_verified),
        },
        "counter_hypotheses": [
            {
                "id": "compatible_declared_year_debt",
                "supported": bool(compatible_declared_year_debt),
                "description": "Esiste un debito compatibile nell'anno effettivamente dichiarato.",
            }
        ],
        "recommended_next_step": "verify_current_official_f24_correction_procedure",
        "requires_official_source_refresh": True,
        "must_not_auto_pay_again": bool(prerequisites),
    }


tax_misallocation_hypothesis = tax_misallocation_assessment


class OperationalLearningEngine:
    def __init__(self, db):
        self.db = db

    def _write_collection(self, name: str):
        if name not in ASSISTANT_WRITE_COLLECTIONS:
            raise RuntimeError(f"Scrittura vietata alla collezione di dominio: {name}")
        return self.db[name]

    async def _upsert(self, collection: str, doc: Dict[str, Any]) -> Dict[str, Any]:
        if not doc.get("id"):
            raise ValueError("Ogni record dell'assistente deve avere un id stabile")
        stored = {**doc, "updated_at": _now()}
        await self._write_collection(collection).update_one(
            {"id": stored["id"]},
            {"$set": stored, "$setOnInsert": {"created_at": doc.get("created_at") or _now()}},
            upsert=True,
        )
        return stored

    async def upsert_fact(self, fact: Dict[str, Any]) -> Dict[str, Any]:
        return await self._upsert(COLL_OPERATIONAL_FACTS, fact)

    async def upsert_pattern(self, pattern: Dict[str, Any]) -> Dict[str, Any]:
        return await self._upsert(COLL_LEARNED_PATTERNS, pattern)

    async def upsert_expected_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        return await self._upsert(COLL_EXPECTED_EVENTS, event)

    async def _open_review_item(self, collection_name: str, item: Dict[str, Any]) -> Dict[str, Any]:
        """Apre o aggiorna un caso senza riaprire una decisione gia' conclusa."""
        if not item.get("id"):
            raise ValueError("Ogni elemento di revisione deve avere un id stabile")
        collection = self._write_collection(collection_name)
        existing = await collection.find_one({"id": item["id"]}, {"_id": 0})
        seen_at = _now()
        if existing and str(existing.get("status") or "").lower() in TERMINAL_REVIEW_STATUSES:
            await collection.update_one(
                {"id": item["id"]},
                {"$set": {"last_seen_at": seen_at, "updated_at": seen_at}},
            )
            return {**existing, "last_seen_at": seen_at, "updated_at": seen_at}
        return await self._upsert(
            collection_name,
            {**item, "last_seen_at": seen_at},
        )

    async def open_anomaly(self, anomaly: Dict[str, Any]) -> Dict[str, Any]:
        return await self._open_review_item(COLL_ADMIN_ANOMALIES, anomaly)

    async def open_question(self, question: Dict[str, Any]) -> Dict[str, Any]:
        return await self._open_review_item(COLL_DECISION_QUESTIONS, question)

    async def answer_question(
        self, question_id: str, option_id: str, actor: str, notes: str = ""
    ) -> Optional[Dict[str, Any]]:
        collection = self._write_collection(COLL_DECISION_QUESTIONS)
        question = await collection.find_one({"id": question_id}, {"_id": 0})
        if not question:
            return None
        valid_options = {str(item.get("id")) for item in question.get("options", [])}
        if option_id not in valid_options:
            raise ValueError("Opzione non valida per questa domanda")
        answer = {"option_id": option_id, "actor": actor, "notes": notes, "answered_at": _now()}
        await collection.update_one(
            {"id": question_id},
            {"$set": {"status": "answered", "answer": answer, "updated_at": _now()}},
        )
        return {**question, "status": "answered", "answer": answer}

    async def remember_case(self, case: Dict[str, Any]) -> Dict[str, Any]:
        if case.get("outcome_status") != "confirmed" and case.get("confirmed") is not True:
            raise ValueError("Un caso entra in memoria solo dopo un esito umano confermato")
        resolution = case.get("resolution") or case.get("outcome")
        if not resolution:
            raise ValueError("La risoluzione confermata è obbligatoria")
        case_id = case.get("id") or _id(
            "case", case.get("case_type"), case.get("title"), resolution, case.get("source_id")
        )
        return await self._upsert(
            COLL_CASE_MEMORY,
            {**case, "id": case_id, "outcome_status": "confirmed", "resolution": resolution},
        )

    async def record_observation(
        self,
        *,
        source: str,
        source_version: str,
        payload: Dict[str, Any],
        observed_at: Optional[str] = None,
        supersedes: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not source.strip() or not source_version.strip():
            raise ValueError("Fonte e versione della fonte sono obbligatorie")
        content_hash = _hash(payload)
        document = {
            "id": _id("source", source.strip().lower(), source_version.strip(), content_hash),
            "source": source.strip(),
            "source_version": source_version.strip(),
            "content_hash": content_hash,
            "payload": payload,
            "observed_at": observed_at or _now(),
            "supersedes": supersedes,
            "provenance": {"kind": "observation", "immutable_payload_hash": content_hash},
        }
        return await self._upsert(COLL_KNOWLEDGE_SOURCES, document)

    async def scan_payroll_residuals(self, limit: int = 500) -> List[Dict[str, Any]]:
        salary_rows = await self.db[COLL_PRIMA_NOTA_SALARI].find(
            {"entity_status": {"$ne": "deleted"}}, {"_id": 0}
        ).limit(limit).to_list(length=limit)
        questions: List[Dict[str, Any]] = []
        for row in salary_rows:
            expected = _first(row, ("importo_busta", "netto", "netto_da_pagare", "importo_netto"), 0)
            actual = _first(row, ("importo_bonifico", "importo_pagato", "pagato"), 0)
            source = {
                **row,
                "id": str(row.get("id") or _id("salario", row.get("dipendente_id"), row.get("anno"), row.get("mese"))),
                "netto": expected,
            }
            question = payroll_residual_question(source, actual)
            if question:
                question["evidence"]["source_collection"] = COLL_PRIMA_NOTA_SALARI
                question["evidence"]["source_id"] = source["id"]
                await self.open_question(question)
                questions.append(question)
        return questions

    async def scan_employee_expiries(
        self, limit: int = 1000, today: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        employees = await self.db[COLL_DIPENDENTI].find(
            {"entity_status": {"$ne": "deleted"}}, {"_id": 0}
        ).limit(limit).to_list(length=limit)
        questions: List[Dict[str, Any]] = []
        for employee in employees:
            contract_date = _parse_date(
                _first(employee, ("data_scadenza_contratto", "contratto.data_scadenza", "contratto_scadenza"))
            )
            identity_date = _parse_date(
                _first(
                    employee,
                    (
                        "data_scadenza_documento",
                        "documento_identita.data_scadenza",
                        "documenti.identita.scadenza",
                    ),
                )
            )
            for question in (
                contract_expiry_question(employee, contract_date, today) if contract_date else None,
                identity_document_expiry_question(employee, identity_date, today) if identity_date else None,
            ):
                if question:
                    question["evidence"]["source_collection"] = COLL_DIPENDENTI
                    await self.open_question(question)
                    questions.append(question)
        return questions

    @staticmethod
    def _f24_rows(document: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Normalizza tutte le rappresentazioni F24 evitando doppie letture."""
        sources = (
            "sezione_erario",
            "sezione_inps",
            "sezione_regioni",
            "sezione_tributi_locali",
            "sezione_imu",
            "sezione_inail",
            "tributi",
            "righe",
            "dettaglio_tributi",
        )
        rows: List[Dict[str, Any]] = []
        max_occurrences: Dict[tuple[str, int, Optional[int], Optional[int]], int] = {}
        for section in sources:
            section_occurrences: Dict[tuple[str, int, Optional[int], Optional[int]], int] = {}
            for section_index, original in enumerate(_section_rows(document.get(section))):
                code = str(
                    _first(original, ("codice_tributo", "codice", "causale", "codice_causale"), "")
                    or ""
                ).strip().upper()
                amount_cents = _cents(
                    _first(
                        original,
                        ("importo_debito", "debito", "importo", "importo_contributi"),
                        0,
                    )
                )
                tax_year, tax_month = _period_year_month(original)
                signature = (code, amount_cents, tax_year, tax_month)
                if not code:
                    continue
                occurrence = section_occurrences.get(signature, 0) + 1
                section_occurrences[signature] = occurrence
                # Alcuni parser espongono la stessa riga sia nella sezione
                # specifica sia negli alias generici. Manteniamo pero' la
                # molteplicità reale quando due tributi identici compaiono
                # davvero nello stesso F24.
                if occurrence <= max_occurrences.get(signature, 0):
                    continue
                max_occurrences[signature] = occurrence
                rows.append(
                    {
                        **original,
                        "_assistant_section": section,
                        "_assistant_section_index": section_index,
                    }
                )
        return rows

    async def scan_f24_misallocations(self, limit: int = 1000) -> List[Dict[str, Any]]:
        documents = await self.db[COLL_F24].find(
            {"entity_status": {"$ne": "deleted"}}, {"_id": 0}
        ).limit(limit).to_list(length=limit)
        obligations = await self.db[COLL_EXPECTED_EVENTS].find(
            {
                "event_type": "tax_obligation",
                "status": {"$nin": ["cancelled", "archived"]},
            },
            {"_id": 0},
        ).limit(limit).to_list(length=limit)
        declared_year_obligations: Dict[tuple[str, int, int], set[str]] = {}
        for obligation in obligations:
            code = str(obligation.get("key") or obligation.get("tax_code") or "").strip().upper()
            year = obligation.get("year")
            amount_cents = _cents(obligation.get("expected_amount"))
            if not code or not str(year or "").isdigit() or amount_cents <= 0:
                continue
            source = obligation.get("source") or {}
            source_id = str(source.get("id") if isinstance(source, dict) else source or obligation["id"])
            declared_year_obligations.setdefault((code, int(year), amount_cents), set()).add(source_id)

        anomalies: List[Dict[str, Any]] = []
        for document in documents:
            document_id = str(document.get("id") or document.get("_id") or _id("f24", document))
            bank_verified = bool(
                _first(document, ("bank_verified", "riconciliato_banca", "quietanza_verificata"), False)
            )
            for row in self._f24_rows(document):
                expected_year = _first(row, ("anno_atteso", "expected_year"), _first(document, ("anno_atteso",)))
                declared_year = _first(row, ("anno_riferimento", "anno", "anno_di_riferimento"))
                if not (str(expected_year).isdigit() and str(declared_year).isdigit()):
                    continue
                code = str(_first(row, ("codice_tributo", "codice"), ""))
                expected_amount = _first(row, ("importo_atteso", "expected_amount"), _first(document, ("importo_atteso",)))
                paid_amount = _first(row, ("importo_debito", "importo", "debito"), 0)
                debt_key = (code.strip().upper(), int(declared_year), _cents(paid_amount))
                # La riga F24 che stiamo valutando non e' una controprova di
                # se stessa. Esiste un debito compatibile nell'anno dichiarato
                # soltanto se il dominio lo afferma esplicitamente oppure se
                # esiste un'obbligazione fiscale attesa, proveniente da una
                # fonte distinta dal pagamento che stiamo valutando, con la
                # stessa terna codice/anno/importo. Un secondo pagamento non
                # prova l'esistenza del debito.
                obligation_sources = declared_year_obligations.get(debt_key, set())
                compatible = bool(row.get("compatible_declared_year_debt")) or any(
                    source_id != document_id for source_id in obligation_sources
                )
                assessment = tax_misallocation_assessment(
                    expected_year=int(expected_year),
                    declared_year=int(declared_year),
                    tax_code=code,
                    expected_amount=expected_amount,
                    paid_amount=paid_amount,
                    bank_verified=bank_verified,
                    compatible_declared_year_debt=compatible,
                )
                if assessment["conclusion"] == "not_supported":
                    continue
                anomaly = {
                    "id": _id("anomaly", "f24_year", document_id, code, expected_year, declared_year),
                    "anomaly_type": "f24_possible_year_misallocation",
                    "severity": assessment["severity"],
                    "status": "to_verify",
                    "title": f"F24 {code}: annualità da verificare",
                    "subject": {"type": "f24", "id": document_id},
                    "assessment": assessment,
                    "source": {"collection": COLL_F24, "id": document_id},
                    "must_not_auto_pay_again": assessment["must_not_auto_pay_again"],
                }
                await self.open_anomaly(anomaly)
                anomalies.append(anomaly)
        return anomalies

    async def learn_periodic_f24(self, limit: int = 2000) -> List[Dict[str, Any]]:
        documents = await self.db[COLL_F24].find(
            {"entity_status": {"$ne": "deleted"}}, {"_id": 0}
        ).limit(limit).to_list(length=limit)
        by_code: Dict[str, List[Dict[str, Any]]] = {}
        for document in documents:
            event_date = _first(document, ("data_versamento", "data_pagamento", "data"))
            for row in self._f24_rows(document):
                code = str(_first(row, ("codice_tributo", "codice"), "")).strip()
                if code and event_date:
                    by_code.setdefault(code, []).append(
                        {"date": event_date, "amount": _first(row, ("importo_debito", "importo", "debito"), 0)}
                    )
        learned: List[Dict[str, Any]] = []
        next_month = (date.today().replace(day=1) + timedelta(days=32)).replace(day=1)
        for code, observations in by_code.items():
            pattern = infer_periodic_pattern(
                observations, pattern_type="f24_periodic_tax", key=code, min_months=3
            )
            if not pattern:
                continue
            await self.upsert_pattern(pattern)
            await self.upsert_expected_event(
                expected_event_from_pattern(pattern, next_month.year, next_month.month)
            )
            learned.append(pattern)
        return learned

    @staticmethod
    def _f24_event_date(document: Dict[str, Any]) -> Optional[date]:
        return _parse_date(
            _first(
                document,
                (
                    "data_versamento",
                    "data_pagamento",
                    "dati_generali.data_versamento",
                    "dati_generali.data_pagamento",
                    "data_scadenza",
                    "scadenza",
                    "data",
                ),
            )
        )

    async def reconcile_expected_tax_events(self, limit: int = 2000) -> List[Dict[str, Any]]:
        """Confronta obblighi/eventi fiscali attesi con gli F24 reali.

        Il match e' volutamente restrittivo: codice tributo, annualita' e,
        quando disponibile nell'evento, mese devono coincidere. Gli importi
        vengono sommati in centesimi e ogni evidenza conserva documento e riga.
        Il metodo aggiorna soltanto ``expected_events`` e non modifica gli F24.
        """
        events = await self.db[COLL_EXPECTED_EVENTS].find(
            {
                "event_type": {"$in": ["f24_periodic_tax", "tax_obligation"]},
                "status": {"$nin": ["cancelled", "archived"]},
            },
            {"_id": 0},
        ).limit(limit).to_list(length=limit)
        documents = await self.db[COLL_F24].find(
            {"entity_status": {"$ne": "deleted"}}, {"_id": 0}
        ).limit(limit).to_list(length=limit)

        actual_by_code: Dict[str, List[Dict[str, Any]]] = {}
        for document in documents:
            event_date = self._f24_event_date(document)
            document_id = str(
                document.get("id")
                or document.get("f24_id")
                or document.get("file_hash")
                or _id("f24", document)
            )
            for row_index, row in enumerate(self._f24_rows(document)):
                code = str(_first(row, ("codice_tributo", "codice"), "")).strip().upper()
                amount_cents = _cents(_first(row, ("importo_debito", "importo", "debito"), 0))
                tax_year, tax_month = _period_year_month(row)
                if not code or amount_cents <= 0:
                    continue
                actual_by_code.setdefault(code, []).append(
                    {
                        "document_id": document_id,
                        "row_index": row_index,
                        "tax_code": code,
                        "tax_year": tax_year,
                        "tax_month": tax_month,
                        "payment_year": event_date.year if event_date else None,
                        "payment_month": event_date.month if event_date else None,
                        "payment_date": event_date.isoformat() if event_date else None,
                        "amount": amount_cents / 100,
                        "source_collection": COLL_F24,
                    }
                )

        reconciled: List[Dict[str, Any]] = []
        tax_groups: Dict[tuple[str, int, Optional[int]], List[str]] = {}
        tax_group_amount_counts: Dict[tuple[str, int, Optional[int], int], int] = {}
        for event in events:
            if event.get("event_type") != "tax_obligation":
                continue
            code = str(event.get("key") or event.get("tax_code") or "").strip().upper()
            raw_year = event.get("year")
            raw_month = event.get("month")
            if not code or not str(raw_year or "").isdigit():
                continue
            month = int(raw_month) if str(raw_month or "").isdigit() else None
            tax_groups.setdefault((code, int(raw_year), month), []).append(str(event.get("id")))
            amount_key = (code, int(raw_year), month, _cents(event.get("expected_amount")))
            tax_group_amount_counts[amount_key] = tax_group_amount_counts.get(amount_key, 0) + 1
        used_tax_evidence: set[tuple[str, int]] = set()

        for event in events:
            code = str(event.get("key") or event.get("tax_code") or "").strip().upper()
            raw_year = event.get("year")
            if not code or not str(raw_year or "").isdigit():
                continue
            event_year = int(raw_year)
            raw_month = event.get("month")
            event_month = int(raw_month) if str(raw_month or "").isdigit() else None
            candidates = list(actual_by_code.get(code, []))
            if event.get("event_type") == "tax_obligation":
                candidates = [item for item in candidates if item.get("tax_year") == event_year]
                if event_month:
                    # Una riga senza periodo fiscale non prova un obbligo
                    # mensile, anche se l'F24 e' stato pagato in quel mese.
                    candidates = [item for item in candidates if item.get("tax_month") == event_month]
            else:
                # I pattern periodici sono appresi sulla data di pagamento,
                # quindi si confrontano col mese dell'addebito e non con
                # l'annualita' fiscale contenuta nella riga.
                candidates = [item for item in candidates if item.get("payment_year") == event_year]
                if event_month:
                    candidates = [
                        item for item in candidates if item.get("payment_month") == event_month
                    ]

            evidence: List[Dict[str, Any]] = []
            seen_evidence: set[tuple[str, int]] = set()
            for item in candidates:
                evidence_key = (str(item["document_id"]), int(item["row_index"]))
                if evidence_key in seen_evidence:
                    continue
                seen_evidence.add(evidence_key)
                evidence.append(item)

            if event.get("event_type") == "tax_obligation":
                group_key = (code, event_year, event_month)
                group_size = len(tax_groups.get(group_key, []))
                available = [
                    item
                    for item in evidence
                    if (str(item["document_id"]), int(item["row_index"]))
                    not in used_tax_evidence
                ]
                if group_size > 1:
                    expected_cents = _cents(event.get("expected_amount"))
                    exact = [item for item in available if _cents(item["amount"]) == expected_cents]
                    same_amount_events = tax_group_amount_counts.get(
                        (code, event_year, event_month, expected_cents), 0
                    )
                    if len(exact) != 1 or same_amount_events != 1:
                        updated = {
                            **event,
                            "actual_amount": 0.0,
                            "delta_amount": _money(event.get("expected_amount")),
                            "status": "ambiguous",
                            "comparison": "exact_cents_plus_unique_tax_identity",
                            "evidence": [],
                            "candidate_evidence": available,
                            "matching_reason": (
                                "piu_obblighi_nello_stesso_periodo_senza_riga_univoca_al_centesimo"
                            ),
                            "last_reconciled_at": _now(),
                            "updated_at": _now(),
                        }
                        await self.upsert_expected_event(updated)
                        reconciled.append(updated)
                        continue
                    evidence = exact
                else:
                    evidence = available

                for item in evidence:
                    used_tax_evidence.add((str(item["document_id"]), int(item["row_index"])))

            actual_cents = sum(_cents(item["amount"]) for item in evidence)

            updated = reconcile_expected_event(
                event,
                Decimal(actual_cents) / Decimal(100),
                evidence=evidence,
            )
            await self.upsert_expected_event(updated)
            reconciled.append(updated)
        return reconciled

    async def run_sentinel(self) -> Dict[str, Any]:
        payroll = await self.scan_payroll_residuals()
        employees = await self.scan_employee_expiries()
        f24 = await self.scan_f24_misallocations()
        patterns = await self.learn_periodic_f24()
        expected_tax = await self.reconcile_expected_tax_events()
        return {
            "generated_at": _now(),
            "payroll_questions": len(payroll),
            "employee_questions": len(employees),
            "f24_anomalies": len(f24),
            "learned_patterns": len(patterns),
            "reconciled_tax_events": len(expected_tax),
        }

    async def dashboard(self, limit: int = 100) -> Dict[str, Any]:
        questions = await self.db[COLL_DECISION_QUESTIONS].find(
            {"status": "open"}, {"_id": 0}
        ).limit(limit).to_list(length=limit)
        anomalies = await self.db[COLL_ADMIN_ANOMALIES].find(
            {"status": {"$in": ["open", "to_verify"]}}, {"_id": 0}
        ).limit(limit).to_list(length=limit)
        expected = await self.db[COLL_EXPECTED_EVENTS].find(
            {"status": {"$in": ["expected", "overdue", "partial", "ambiguous"]}}, {"_id": 0}
        ).limit(limit).to_list(length=limit)
        patterns = await self.db[COLL_LEARNED_PATTERNS].find(
            {"status": "learned"}, {"_id": 0}
        ).limit(20).to_list(length=20)
        questions.sort(key=lambda item: (SEVERITY_RANK.get(item.get("severity"), 99), item.get("created_at", "")))
        anomalies.sort(key=lambda item: (SEVERITY_RANK.get(item.get("severity"), 99), item.get("updated_at", "")))
        patterns.sort(key=lambda item: float(item.get("confidence", 0)), reverse=True)
        return {
            "generated_at": _now(),
            "questions": questions,
            "anomalies": anomalies,
            "expected_events": expected,
            "learned_patterns": patterns,
            "counts": {
                "questions": len(questions),
                "anomalies": len(anomalies),
                "expected_events": len(expected),
                "learned_patterns": len(patterns),
            },
            "safety": {
                "domain_collections_write": False,
                "automatic_payments": False,
                "matching_rule": "exact_cents_plus_identity",
            },
        }
