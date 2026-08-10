"""Parser deterministici per documenti amministrativi acquisiti da Documenti.

I parser estraggono identita' e riferimenti, ma non modificano stati reali e
non trasformano avvisi, istanze o moduli in prove di pagamento.
"""
from __future__ import annotations

import hashlib
import io
import re
from typing import Any


def _pdf_text(content: bytes) -> tuple[str, bool]:
    text = ""
    try:
        from pypdf import PdfReader

        text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)
    except Exception:
        pass
    if len(text.strip()) >= 80:
        return text, False
    try:
        from app.services.pagopa_receipts import _extract_receipt_text

        ocr_text, ocr_used = _extract_receipt_text(content)
        return ocr_text or text, ocr_used
    except Exception:
        return text, False


def _iso_date(value: str | None) -> str | None:
    if not value:
        return None
    parts = re.split(r"[/-]", value)
    if len(parts) != 3:
        return None
    day, month, year = parts
    if len(year) == 2:
        year = f"20{year}"
    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"


def _match(pattern: str, text: str, flags: int = re.I) -> str | None:
    found = re.search(pattern, text, flags)
    return found.group(1).strip() if found else None


def parse_dimissioni(text: str) -> dict[str, Any]:
    compact = re.sub(r"\s+", " ", text)
    worker = _match(
        r"Sezione\s*1\s*[–-]\s*Lavoratore\s+Codice\s+Fiscale\s+([A-Z0-9]{16})",
        compact,
    )
    employer = _match(
        r"Sezione\s*2\s*[–-]\s*Datore\s+di\s+Lavoro\s+Codice\s+Fiscale\s+(\d{11})",
        compact,
    )
    surname = _match(r"Sezione\s*1.*?Cognome\s+([A-ZÀ-ÖØ-Ý' -]+?)\s+Nome\s+", compact)
    name = _match(r"\sNome\s+([A-ZÀ-ÖØ-Ý' -]+?)\s+E-?Mail\s+", compact)
    start = _match(r"Data\s+Inizio\s+(\d{2}/\d{2}/\d{4})", compact)
    end = _match(r"Data\s+Decorrenza\s+(\d{2}/\d{2}/\d{4})", compact)
    module_id = _match(r"Codice\s+Identificativo\s+Modulo\s+(\d{17})", compact)
    sent = _match(r"Data\s+Trasmissione\s+(\d{2}/\d{2}/\d{4})", compact)
    communication = _match(
        r"Tipo\s+Comunicazione\s+(.+?)\s+Sezione\s*5", compact,
    )
    return {
        "tipo_documento": "dimissioni_telematiche",
        "lavoratore_cf": worker,
        "lavoratore_cognome": surname,
        "lavoratore_nome": name,
        "datore_cf": employer,
        "data_inizio_rapporto": _iso_date(start),
        "data_decorrenza_recesso": _iso_date(end),
        "tipo_comunicazione": communication,
        "codice_modulo": module_id,
        "data_trasmissione": _iso_date(sent),
        "association_key": worker,
        "requires_review": not all((worker, employer, end, module_id)),
        "mutates_employee_status": False,
    }


def parse_ader(text: str, document_type: str) -> dict[str, Any]:
    compact = re.sub(r"\s+", " ", text)
    company_cf = _match(
        r"del/della\s+.+?\s+codice\s+fiscale\s+(\d{11})", compact,
    )
    tax_codes = list(dict.fromkeys(re.findall(r"\b(?:\d{11}|[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b", compact, re.I)))
    claims = list(dict.fromkeys(re.findall(r"\b\d{20}\b", compact)))
    notification_dates = [
        _iso_date(value)
        for value in re.findall(r"\b\d{2}/\d{2}/\d{4}\b", compact)
    ]
    subtype = (
        "sospensione_legale_riscossione"
        if document_type == "ader_sospensione"
        else "definizione_agevolata"
    )
    return {
        "tipo_documento": document_type,
        "sottotipo": subtype,
        "contribuente_cf": company_cf or (tax_codes[0] if tax_codes else None),
        "codici_fiscali_presenti": tax_codes,
        "numeri_cartella": claims,
        "date_presenti": [value for value in notification_dates if value],
        "association_keys": claims,
        "requires_review": not bool(claims),
        "is_payment_evidence": False,
    }


def parse_tari(text: str) -> dict[str, Any]:
    compact = re.sub(r"\s+", " ", text)
    taxpayer = _match(
        r"P\.IVA/C\.F\.\s*(\d{11}|[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])",
        compact,
    )
    protocol = _match(r"Prot\.\s*n[°º]?\s*([0-9/]+)", compact)
    contributor = _match(r"Cod\.\s*Contribuente\s*:\s*(\d+)", compact)
    kind_year = re.search(r"AVVISO\s+DI\s+PAGAMENTO\s+TARI\s*-\s*(ACCONTO|SALDO)\s+(\d{4})", compact, re.I)
    dates = list(dict.fromkeys(
        value for value in (_iso_date(raw) for raw in re.findall(r"\b\d{2}[/-]\d{2}[/-]\d{4}\b", compact)) if value
    ))
    amounts = sorted({
        float(raw.replace(".", "").replace(",", "."))
        for raw in re.findall(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b", compact)
    })
    return {
        "tipo_documento": "tari_avviso",
        "contribuente_cf": taxpayer,
        "protocollo": protocol,
        "codice_contribuente": contributor,
        "fase": kind_year.group(1).upper() if kind_year else None,
        "anno_tributo": int(kind_year.group(2)) if kind_year else None,
        "date_presenti": dates,
        "importi_presenti": amounts,
        "association_key": f"{taxpayer}:{kind_year.group(2)}:{kind_year.group(1).upper()}" if taxpayer and kind_year else None,
        "requires_review": not bool(taxpayer and kind_year),
        "is_payment_evidence": False,
    }


def parse_tari_application(text: str) -> dict[str, Any]:
    compact = re.sub(r"\s+", " ", text)
    marker = re.sub(r"[^A-Z0-9]", "", compact.upper())
    tax_codes = list(dict.fromkeys(re.findall(
        r"\b(?:\d{11}|[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z])\b",
        compact, re.I,
    )))
    years = sorted({int(value) for value in re.findall(r"\b20\d{2}\b", compact)})
    amounts = sorted({
        float(raw.replace(".", "").replace(",", "."))
        for raw in re.findall(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b", compact)
    })
    return {
        "tipo_documento": "tari_istanza_compensazione",
        "codici_fiscali_presenti": tax_codes,
        "anni_tributo_presenti": years,
        "importi_presenti": amounts,
        "richiesta_compensazione": "COMPENSA" in marker,
        "richiesta_rimborso": "RIMBORS" in marker,
        "association_keys": tax_codes,
        "requires_review": not bool(tax_codes),
        "is_payment_evidence": False,
    }


def parse_company_register(text: str) -> dict[str, Any]:
    compact = re.sub(r"\s+", " ", text)
    company_cf = _match(r"Codice\s+fiscale.*?Registro\s+Imprese\s+(\d{11})", compact)
    company_name = _match(r"VISURA\s+ORDINARIA\s+SOCIETA['’]?\s+DI\s+CAPITALE\s+(.+?)\s+\w{5,8}\b", compact)
    rea = _match(r"Numero\s+REA\s+([A-Z]{2}\s*-\s*\d+)", compact)
    return {
        "tipo_documento": "visura_camerale",
        "societa_cf": company_cf,
        "societa_denominazione": company_name,
        "numero_rea": rea,
        "association_key": company_cf,
        "requires_review": not bool(company_cf),
        "is_payment_evidence": False,
    }


def extract_administrative_metadata(
    *, content: bytes, filename: str, document_type: str,
) -> dict[str, Any]:
    text, ocr_used = _pdf_text(content)
    if document_type == "dimissioni_telematiche":
        parsed = parse_dimissioni(text)
    elif document_type in {"ader_sospensione", "ader_definizione_agevolata"}:
        parsed = parse_ader(text, document_type)
    elif document_type == "tari_avviso":
        parsed = parse_tari(text)
    elif document_type == "tari_istanza_compensazione":
        parsed = parse_tari_application(text)
    elif document_type == "visura_camerale":
        parsed = parse_company_register(text)
    elif document_type == "documento_identita":
        parsed = {
            "tipo_documento": document_type,
            "requires_review": True,
            "is_payment_evidence": False,
            "contains_sensitive_identity_data": True,
        }
    else:
        parsed = {"tipo_documento": document_type, "requires_review": True}
    parsed.update({
        "filename": filename,
        "ocr_used": ocr_used,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    })
    return parsed
