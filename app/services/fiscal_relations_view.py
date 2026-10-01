"""Vista relazionale delle prove fiscali collegate al Libro giornale.

La scrittura giornaliera rileva l'IVA, ma il pagamento o la compensazione
avvengono per periodo tramite F24. Questa vista collega soltanto periodi e
codici tributo espliciti: nessun abbinamento per somiglianza o solo importo.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, Optional

from app.services.originale_documento import url_originale
from app.services.tax_payment_query import TaxPaymentQueryService


_MESI = {
    "gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4,
    "maggio": 5, "giugno": 6, "luglio": 7, "agosto": 8,
    "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12,
}


def _periodo(value: Any) -> Optional[str]:
    """Accetta solo un mese/anno esplicito e restituisce ``YYYY-MM``."""
    text = str(value or "").strip().lower()
    if not text:
        return None
    match = re.search(r"\b((?:19|20)\d{2})[-/]([01]?\d)\b", text)
    if match and 1 <= int(match.group(2)) <= 12:
        return f"{match.group(1)}-{int(match.group(2)):02d}"
    match = re.search(r"\b([01]?\d)[-/]((?:19|20)\d{2})\b", text)
    if match and 1 <= int(match.group(1)) <= 12:
        return f"{match.group(2)}-{int(match.group(1)):02d}"
    for nome, mese in _MESI.items():
        match = re.search(rf"\b{nome}\s+((?:19|20)\d{{2}})\b", text)
        if match:
            return f"{match.group(1)}-{mese:02d}"
    return None


def _periodo_avviso(documento: Dict[str, Any], segnalazione: Optional[Dict[str, Any]]) -> Optional[str]:
    dati = (segnalazione or {}).get("dati_riferimento") or {}
    for value in (
        dati.get("periodo"),
        documento.get("periodo_riferimento"),
        documento.get("periodo_competenza"),
        documento.get("periodo"),
        (documento.get("extracted_data") or {}).get("periodo_riferimento"),
    ):
        parsed = _periodo(value)
        if parsed:
            return parsed

    # Il nome del file e' utilizzabile soltanto quando contiene un mese e un
    # anno espliciti (es. "Avviso gennaio 2025.pdf"). Le date generiche del
    # documento non vengono interpretate come periodo fiscale.
    return _periodo(documento.get("filename") or documento.get("file_name"))


def _codice_avviso(documento: Dict[str, Any], segnalazione: Optional[Dict[str, Any]]) -> Optional[str]:
    dati = (segnalazione or {}).get("dati_riferimento") or {}
    value = (
        dati.get("codice_tributo")
        or documento.get("codice_tributo")
        or (documento.get("extracted_data") or {}).get("codice_tributo")
    )
    code = re.sub(r"\D", "", str(value or ""))
    return code if len(code) == 4 else None


def _is_iva(code: Any) -> bool:
    normalized = str(code or "").strip()
    return normalized == "6099" or normalized.startswith("60")


async def _to_list(cursor, limit: int = 10000) -> list[dict]:
    if hasattr(cursor, "to_list"):
        return await cursor.to_list(limit)
    return [item async for item in cursor]


async def _avvisi(db, anno: int) -> list[dict]:
    docs = await _to_list(db["documents_inbox"].find({
        "$or": [
            {"category": "avviso_bonario"},
            {"categoria": "avviso_bonario"},
            {"agente_fiscale_tipo": "avviso_bonario"},
        ]
    }, {"_id": 0, "pdf_data": 0, "content_base64": 0}), 2000)
    signals = await _to_list(db["agenti_segnalazioni"].find({
        "agente": "FiscaleSentinella",
    }, {"_id": 0}), 5000)
    signal_by_doc = {
        str((signal.get("dati_riferimento") or {}).get("documento_id")): signal
        for signal in signals
        if (signal.get("dati_riferimento") or {}).get("documento_id")
    }
    result = []
    for doc in docs:
        doc_id = str(doc.get("id") or "")
        signal = signal_by_doc.get(doc_id)
        period = _periodo_avviso(doc, signal)
        if not period or not period.startswith(f"{anno}-"):
            continue
        result.append({
            "id": doc_id,
            "filename": doc.get("filename") or doc.get("file_name") or "Avviso Agenzia delle Entrate",
            "periodo": period,
            "codice_tributo": _codice_avviso(doc, signal),
            "url": url_originale("documento", doc_id),
        })
    return result


async def _receipt_urls(db, ids: Iterable[str]) -> dict[str, str]:
    ids = sorted({str(value) for value in ids if value})
    if not ids:
        return {}
    result: dict[str, str] = {}
    fiscal = await _to_list(db["fiscal_documents"].find(
        {"id": {"$in": ids}}, {"_id": 0, "id": 1},
    ), len(ids))
    for receipt in fiscal:
        result[str(receipt["id"])] = url_originale("documento_fiscale", receipt["id"])
    legacy = await _to_list(db["quietanze_f24"].find(
        {"id": {"$in": ids}}, {"_id": 0, "id": 1},
    ), len(ids))
    for receipt in legacy:
        result.setdefault(
            str(receipt["id"]),
            f"/api/f24-riconciliazione/quietanze/{receipt['id']}",
        )
    return result


def _model_view(
    document: Dict[str, Any], rows: Iterable[Dict[str, Any]], receipt_urls: Dict[str, str],
) -> dict:
    rows = list(rows)
    evidence = document.get("evidenza_pagamento") or {}
    chain = document.get("payment_chain") or {}
    bank = chain.get("bank_movement") or {}
    debit = sum(int(row.get("debit_cents") or 0) for row in rows)
    credit = sum(int(row.get("credit_cents") or 0) for row in rows)
    has_receipt = bool(evidence.get("quietanza_presente"))
    bank_verified = bool(evidence.get("verificato_banca"))
    if has_receipt and bank_verified:
        status = "PAGATA_E_VERIFICATA"
        message = "IVA versata con F24: quietanza e movimento bancario verificati"
    elif has_receipt:
        status = "QUIETANZA_PRESENTE"
        message = "IVA versata o compensata con F24 quietanzato; movimento bancario da verificare"
    elif bank_verified:
        status = "BANCA_VERIFICATA"
        message = "Pagamento IVA verificato in banca; quietanza non trovata"
    else:
        status = "DA_VERIFICARE"
        message = "Modello F24 presente, ma nessuna quietanza o prova bancaria verificata"
    receipt_id = document.get("quietanza_id") or (document.get("quietanza") or {}).get("id")
    return {
        "f24_id": document.get("id"),
        "filename": document.get("file_name") or document.get("filename") or "F24",
        "codici_tributo": sorted({str(row.get("tax_code") or "") for row in rows if row.get("tax_code")}),
        "debito_iva": debit / 100,
        "credito_compensato": credit / 100,
        "stato": status,
        "messaggio": message,
        "f24_url": f"/api/f24/pdf/{document.get('id')}",
        "quietanza_id": receipt_id,
        "quietanza_url": receipt_urls.get(str(receipt_id)) if receipt_id else None,
        "movimento_bancario_id": bank.get("id") or evidence.get("movimento_bancario_id"),
        "data_pagamento": evidence.get("data_pagamento") or evidence.get("data_versamento_documentale"),
        "quietanza_presente": has_receipt,
        "banca_verificata": bank_verified,
    }


async def prove_fiscali_periodo(db, anno: int) -> Dict[str, Any]:
    """Restituisce F24 IVA, quietanze, banca e avvisi uniti per chiave periodo."""
    documents = await TaxPaymentQueryService(db).list_documents()
    receipt_urls = await _receipt_urls(db, (
        document.get("quietanza_id") or (document.get("quietanza") or {}).get("id")
        for document in documents
    ))
    periods: dict[str, dict] = {}
    for document in documents:
        rows_by_period: dict[str, list] = defaultdict(list)
        for row in document.get("righe_tributo_normalizzate") or []:
            period = row.get("reference_period")
            if period and period.startswith(f"{anno}-") and _is_iva(row.get("tax_code")):
                rows_by_period[period].append(row)
        for period, rows in rows_by_period.items():
            item = periods.setdefault(period, {"periodo": period, "f24": [], "avvisi_ade": []})
            item["f24"].append(_model_view(document, rows, receipt_urls))

    for notice in await _avvisi(db, anno):
        item = periods.setdefault(notice["periodo"], {
            "periodo": notice["periodo"], "f24": [], "avvisi_ade": [],
        })
        matching = [
            model for model in item["f24"]
            if not notice.get("codice_tributo")
            or notice["codice_tributo"] in model.get("codici_tributo", [])
        ]
        documented = [model for model in matching if model.get("quietanza_presente")]
        notice["associazione_certa"] = bool(matching) and (
            not notice.get("codice_tributo") or len(matching) == 1
        )
        notice["f24_ids"] = [model["f24_id"] for model in matching]
        notice["messaggio_pagamento"] = (
            "Pagamento richiesto da Agenzia delle Entrate pagato — vedi quietanza"
            if documented and notice["associazione_certa"] else None
        )
        notice["quietanza_url"] = documented[0].get("quietanza_url") if len(documented) == 1 else None
        item["avvisi_ade"].append(notice)

    ordered = []
    for period in sorted(periods, reverse=True):
        item = periods[period]
        models = item["f24"]
        if any(model["stato"] == "PAGATA_E_VERIFICATA" for model in models):
            item["stato_iva"] = "PAGATA_E_VERIFICATA"
        elif any(model["quietanza_presente"] for model in models):
            item["stato_iva"] = "VERSATA_O_COMPENSATA_CON_QUIETANZA"
        elif models:
            item["stato_iva"] = "DA_VERIFICARE"
        else:
            item["stato_iva"] = "NESSUN_F24_IVA_TROVATO"
        ordered.append(item)
    return {
        "anno": anno,
        "periodi": ordered,
        "criterio": "periodo e codice tributo espliciti; nessun abbinamento per importo o somiglianza",
    }
