"""Classificazione e collegamento conservativo dei PDF Verbali/PagoPA da Drive."""
from __future__ import annotations

import base64
import hashlib
import io
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Optional

from app.services.noleggio.controlli import driver_alla_data
from app.services.payment_invoice_matching import amounts_equal_to_cent


_IUV_RE = re.compile(r"\b(3\d{17}|0\d{16,17})\b")
_TARGA_RE = re.compile(r"\b([A-Z]{2}\d{3}[A-Z]{2})\b", re.IGNORECASE)
# Numero con barre («111/V/2025», «2025/000123»): serie, sigla e anno separati da «/».
_NUMERO_CON_BARRE = r"\d{1,8}(?:/[A-Z0-9]{1,8}){1,3}"
_DATA_GG_MM_AAAA_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")
_VERBALE_PATTERNS = (
    re.compile(
        r"\bverbale\s+(?:di\s+accertamento\s+)?(?:n(?:r)?[.°º]?|numero)?\s*[:#-]?\s*"
        r"([A-Z]{0,3}[/-]?\d{6,20}|" + _NUMERO_CON_BARRE + r")(?![\w/])",
        re.I,
    ),
    re.compile(r"(?:numero|n[.°º]?|nr[.]?)?\s*verbale\s*[:#-]?\s*([A-Z0-9/-]{6,30})", re.I),
    re.compile(r"\b([A-Z]\d{8,14})\b", re.I),
)
_RICEVUTA_MARKERS = (
    "ricevuta di pagamento", "pagamento eseguito", "pagamento effettuato",
    "importo totale pagato", "attestazione di pagamento",
)
_NEGATIVE_PAYMENT_MARKERS = (
    "pagamento non eseguito", "pagamento rifiutato", "pagamento annullato",
)


def _extract_text(content: bytes) -> str:
    text = ""
    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = "\n".join((page.extract_text() or "") for page in pdf.pages)
    except Exception:
        pass
    # Gli avvisi PagoPA generati con structure tree non valido possono perdere
    # tutti i valori con pdfplumber pur restando PDF vettoriali leggibili.
    if len(text.strip()) < 120:
        try:
            import fitz
            with fitz.open(stream=content, filetype="pdf") as document:
                fitz_text = "\n".join(page.get_text() or "" for page in document)
            if len(fitz_text.strip()) > len(text.strip()):
                text = fitz_text
        except Exception:
            pass
    return text


def _extract_numero(text: str) -> Optional[str]:
    for pattern in _VERBALE_PATTERNS:
        for match in pattern.finditer(text or ""):
            value = match.group(1).strip(" .:-").upper()
            # «verbale 12/03/2025» e' una data, non un numero.
            if _DATA_GG_MM_AAAA_RE.match(value):
                continue
            if value and value not in {"NUMERO", "VERBALE"}:
                return value
    return None


def _normalizza_numero(value: Any) -> Optional[str]:
    numero = str(value or "").strip().upper()
    numero = re.sub(r"^VERBALE\s*(?:N(?:R)?[.°º]?|NUMERO)?\s*", "", numero)
    numero = re.sub(r"\s*/\s*", "/", numero)
    numero = numero.strip(" .:-")
    return numero or None


def normalizza_numero_verbale(value: Any) -> Optional[str]:
    """Numero verbale come chiave: maiuscolo, barre senza spazi, mai una data."""
    numero = _normalizza_numero(value)
    if numero and _DATA_GG_MM_AAAA_RE.match(numero):
        return None
    return numero


def normalizza_iuv(value: Any) -> Optional[str]:
    """L'IUV e' sempre una stringa di cifre, mai un numero.

    Un intero o un float ha gia' perso lo zero iniziale (gli IUV da 17 cifre
    cominciano per 0) o l'esattezza: si accetta solo se rispetta da solo la
    forma dell'IUV, altrimenti non si indovina e si restituisce None.
    """
    if value in (None, "") or isinstance(value, (bool, float)):
        return None
    testo = re.sub(r"\s+", "", str(value)).upper()
    if isinstance(value, int):
        return testo if _IUV_RE.fullmatch(testo) else None
    return testo if re.fullmatch(r"[0-9A-Z]{15,35}", testo) else None


def _float_or_none(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        if isinstance(value, str):
            raw = value.strip().replace("€", "").replace(" ", "")
            if "," in raw:
                raw = raw.replace(".", "").replace(",", ".")
            return float(raw)
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_amount(text: str) -> Optional[float]:
    patterns = (
        r"(?:totale|importo\s+pagato|da\s+pagare)\s*[:€]*\s*([\d.]+,\d{2})",
        r"€\s*([\d.]+,\d{2})",
    )
    for pattern in patterns:
        match = re.search(pattern, text or "", re.I)
        if not match:
            continue
        try:
            return float(match.group(1).replace(".", "").replace(",", "."))
        except ValueError:
            continue
    return None


def _select_document_amount(ai_data: Dict[str, Any], pagopa_data: Dict[str, Any], text: str) -> tuple[Optional[float], str, bool]:
    """Sceglie l'importo con provenienza, correggendo il tipico OCR 51,64 -> 5164.

    Il testo vettoriale/estratto dal PDF e il parser PagoPA sono evidenze piu'
    forti di un numero AI privo di separatore. Non effettua correzioni arbitrarie:
    risolve soltanto il conflitto esatto x100 tra le fonti.
    """
    ai_amount = _float_or_none(ai_data.get("importo_ridotto")) or _float_or_none(ai_data.get("importo_ordinario"))
    pagopa_amount = _float_or_none(pagopa_data.get("importo"))
    text_amount = _extract_amount(text)
    documentary = pagopa_amount or text_amount
    if ai_amount and documentary and round(ai_amount, 2) == round(documentary * 100, 2):
        return round(documentary, 2), "pdf_testo_conflitto_ocr_x100", True
    if pagopa_amount is not None:
        return round(pagopa_amount, 2), "parser_pagopa", bool(ai_amount and round(ai_amount, 2) != round(pagopa_amount, 2))
    if text_amount is not None:
        return round(text_amount, 2), "pdf_testo", bool(ai_amount and round(ai_amount, 2) != round(text_amount, 2))
    if ai_amount is not None:
        return round(ai_amount, 2), "parser_ai", False
    return None, "non_rilevato", False


def _extract_payment_date(text: str) -> Optional[str]:
    match = re.search(
        r"(?:data\s+(?:del\s+)?pagamento|pagato\s+il)\s*:?\s*(\d{2}[/-]\d{2}[/-]\d{4})",
        text or "",
        re.I,
    )
    if not match:
        return None
    raw = match.group(1).replace("-", "/")
    day, month, year = raw.split("/")
    return f"{year}-{month}-{day}"


async def _vehicle_context(
    db, targa: Optional[str], event_date: Optional[str] = None,
) -> Dict[str, Any]:
    if not targa:
        return {}
    vehicle = await db["veicoli_noleggio"].find_one(
        {"targa": {"$regex": f"^{re.escape(targa)}$", "$options": "i"}},
        {"_id": 0},
    )
    if not vehicle:
        return {}
    context = {
        "veicolo_id": vehicle.get("id"),
        "contratto": vehicle.get("contratto"),
        "fornitore_noleggio": vehicle.get("fornitore_noleggio"),
    }
    # La targa identifica il veicolo, non il conducente: il driver e' quello
    # dello storico assegnazioni alla data del fatto (motore unico
    # `driver_alla_data`). Senza data del fatto non si propone nessuno; senza
    # copertura dello storico resta da assegnare.
    if not event_date:
        return context
    prova = driver_alla_data(vehicle, event_date)
    if prova.get("fonte") == "storico_assegnazioni" and (prova.get("driver_id") or prova.get("driver")):
        context.update({
            "driver_id": prova.get("driver_id"),
            "driver": prova.get("driver"),
            "driver_match_basis": "assegnazione_storica_alla_data",
        })
    elif prova.get("fonte") == "da_assegnare":
        context["driver_requires_review"] = True
    return context


def _extract_violation_date(text: str) -> Optional[str]:
    # Solo le diciture del fatto: «data verbale» e' la data dell'atto redatto,
    # un'altra data (campo `data_verbale`), e non e' la violazione.
    match = re.search(
        r"(?:data\s+(?:della\s+)?(?:violazione|infrazione)|\bdata\s*:|violazione\s+del|"
        r"commess[ao]\s+il|accertat[ao]\s+il|in\s+data|il\s+giorno)\s*:?[ ]*(\d{2}/\d{2}/\d{4})",
        text or "", re.I,
    )
    if not match:
        return None
    day, month, year = match.group(1).split("/")
    return f"{year}-{month}-{day}"


def _extract_iso_date(pattern: str, text: str) -> Optional[str]:
    match = re.search(pattern, text or "", re.I)
    if not match:
        return None
    day, month, year = re.split(r"[/-]", match.group(1))
    return f"{year}-{month}-{day}"


def _extract_labeled_amount(pattern: str, text: str) -> Optional[float]:
    match = re.search(pattern + r"[^\d]{0,80}([\d.]+,\d{2})\s*(?:€|euro)?", text or "", re.I)
    return _float_or_none(match.group(1)) if match else None


def _extract_verbale_details(text: str) -> Dict[str, Any]:
    """Estrae i campi operativi senza trasformare l'avviso in pagamento."""
    compact = re.sub(r"\s+", " ", text or "")
    register = re.search(r"Registro\s+n[.°º]?\s*([A-Z0-9/-]+)", compact, re.I)
    time_match = re.search(r"(?:alle\s+ore|ore)\s*(\d{1,2}:\d{2})", compact, re.I)
    article = re.search(r"art(?:icolo)?[.\s]+(\d+)\s*(?:c(?:omma)?[.\s]+([\d, e]+))?", compact, re.I)
    location = re.search(
        r"(?:in|presso)\s+(?:via|viale|piazza|corso)\s+(.+?)(?=\s+(?:per\s+aver|in\s+violazione|ai\s+sensi|art[.\s]))",
        compact, re.I,
    )
    obligor = re.search(r"([A-Z][A-Z0-9 .'&-]+?)\s+(?:e['’]\s+)?indicat[oa]\s+come\s+obbligat[oa]\s+in\s+solido", compact, re.I)
    lessor = re.search(r"([A-Z][A-Z0-9 .'&-]+?)\s+(?:e['’]\s+)?indicat[oa]\s+come\s+societ[aà]\s+di\s+locazione", compact, re.I)
    reduced = _extract_labeled_amount(r"(?:riduzione\s+del\s+30%|entro\s+5\s+giorni)", compact)
    ordinary = _extract_labeled_amount(r"(?:dal\s+sesto\s+al\s+sessantesimo\s+giorno|entro\s+60\s+giorni)", compact)
    issue_date = _extract_iso_date(r"(?:emesso|redatto|verbale).*?(\d{2}[/-]\d{2}[/-]\d{4})", compact)
    return {
        "numero_registro": register.group(1).upper() if register else None,
        "data_emissione": issue_date,
        "ora_violazione": time_match.group(1) if time_match else None,
        "indirizzo_violazione": location.group(1).strip(" ,.;") if location else None,
        "articolo_cds": article.group(1) if article else None,
        "commi_cds": article.group(2).strip(" ,") if article and article.group(2) else None,
        "obbligato_in_solido": obligor.group(1).strip() if obligor else None,
        "societa_locazione": lessor.group(1).strip() if lessor else None,
        "importo_ridotto": reduced,
        "importo_ordinario": ordinary,
    }


def _verbale_expectations(
    *, verbale_id: str, source_document_id: str, notification_date: Optional[str],
    reduced_amount: Optional[float], ordinary_amount: Optional[float],
) -> list[Dict[str, Any]]:
    operation_id = f"verbale:{verbale_id}"
    discount_deadline = None
    if notification_date:
        try:
            discount_deadline = (date.fromisoformat(notification_date) + timedelta(days=5)).isoformat()
        except ValueError:
            pass
    common = {
        "operation_id": operation_id,
        "source_fact_id": source_document_id,
        "expectation_owner": "verbale",
        "expectation_status": "ATTESO",
        "mandatory": True,
    }
    return [
        {
            **common,
            "expectation_type": "DECISIONE_VERBALE",
            "discount_deadline": discount_deadline,
            "reduced_amount": reduced_amount,
            "ordinary_amount": ordinary_amount,
            "accepted_outcomes": ["PAGARE_RIDOTTO", "PAGARE_ORDINARIO", "RICORSO", "REINTESTAZIONE"],
        },
        {
            **common,
            "expectation_type": "EVIDENZA_PAGAMENTO_VERBALE",
            "accepted_evidence": ["ricevuta_pagopa", "bollettino", "carta_credito", "paypal", "nexi", "pagobancomat"],
        },
        {
            **common,
            "expectation_type": "RISCONTRO_FINANZIARIO_VERBALE",
            "accepted_evidence": ["movimento_bancario", "addebito_carta", "paypal", "nexi", "pagobancomat"],
        },
    ]


async def _schedule_verbale_notifications(
    db, *, verbale_id: str, notification_date: Optional[str], now_iso: str,
) -> None:
    """Pianifica alert idempotenti dalla ricezione; senza data non inventa scadenze."""
    if not notification_date:
        return
    try:
        received = datetime.combine(
            date.fromisoformat(notification_date), datetime.min.time(), tzinfo=timezone.utc,
        )
    except ValueError:
        return
    for offset, event in (
        (0, "verbale_ricevuto"),
        (3, "sconto_30_promemoria_2_giorni"),
        (4, "sconto_30_promemoria_1_giorno"),
        (5, "sconto_30_scaduto"),
    ):
        notification_id = f"{verbale_id}:{event}:{notification_date}"
        await db["notification_log"].update_one(
            {"id": notification_id},
            {"$setOnInsert": {
                "id": notification_id,
                "tipo": "verbale",
                "verbale_id": verbale_id,
                "evento": event,
                "scheduled_for": (received + timedelta(days=offset)).isoformat(),
                "status": "pending",
                "created_at": now_iso,
            }},
            upsert=True,
        )


async def leggi_documento_verbale(
    content: bytes,
    filename: str,
    parsed_metadata: Dict[str, Any] | None = None,
    *,
    usa_ai: bool = True,
) -> Dict[str, Any]:
    """Legge il PDF di un verbale/avviso/ricevuta: l'unico lettore, senza scrivere.

    Numero, IUV, targa e importo vengono dal **contenuto** (mai dal nome del file
    come fonte del numero se il testo lo contiene); l'importo ha la sua
    provenienza. `usa_ai=False` toglie il ripiego vision (anteprime e test).
    """
    sha256 = hashlib.sha256(content).hexdigest()
    try:
        text = _extract_text(content)
    except Exception:
        text = ""

    parsed_metadata = dict(parsed_metadata or {})
    ai_data: Dict[str, Any] = {
        "numero_verbale": parsed_metadata.get("numero_verbale"),
        "iuv": parsed_metadata.get("identificativo_bolletta") or parsed_metadata.get("iuv"),
        "targa": parsed_metadata.get("targa"),
        "importo_ridotto": parsed_metadata.get("importo"),
        "data_violazione": parsed_metadata.get("data_violazione"),
        "data_verbale": parsed_metadata.get("data_verbale") or parsed_metadata.get("data_emissione"),
        "ora_violazione": parsed_metadata.get("ora_violazione"),
        "numero_atto": parsed_metadata.get("numero_atto") or parsed_metadata.get("numero_registro"),
        "ente_creditore": parsed_metadata.get("ente_creditore"),
        "articolo_cds": parsed_metadata.get("articolo_cds"),
        "descrizione_violazione": parsed_metadata.get("descrizione_violazione"),
        "responsabile": parsed_metadata.get("responsabile") or parsed_metadata.get("obbligato_in_solido"),
        "partita_iva_responsabile": parsed_metadata.get("partita_iva_responsabile"),
        "indirizzo_violazione": parsed_metadata.get("indirizzo_violazione"),
    }
    ai_data = {key: value for key, value in ai_data.items() if value not in (None, "")}
    ai_was_used = False
    ai_error: Optional[str] = None
    # Il fallback vision serve solo per veri PDF scansione. Questa guardia
    # evita chiamate esterne su payload corrotti o sui fixture testuali.
    if usa_ai and content.startswith(b"%PDF") and len(text.strip()) < 80:
        try:
            from app.services.ai_document_parser import parse_verbale_ai
            ai_result = await parse_verbale_ai(file_bytes=content)
            if ai_result.get("success"):
                ai_data.update(ai_result)
                ai_was_used = True
            else:
                ai_error = str(ai_result.get("error") or "estrazione AI non disponibile")
        except Exception as exc:
            ai_error = str(exc)

    combined = f"{filename}\n{text}"
    local_details = _extract_verbale_details(combined)
    for key, value in local_details.items():
        if value not in (None, "") and ai_data.get(key) in (None, ""):
            ai_data[key] = value
    from app.services.pagopa_receipts import parse_receipt_pdf

    pagopa_data = parse_receipt_pdf(content, filename=filename)
    numero = (
        _normalizza_numero(ai_data.get("numero_verbale"))
        or _normalizza_numero(pagopa_data.get("numero_verbale"))
        or _extract_numero(combined)
    )
    iuv_match = _IUV_RE.search(combined)
    targa_match = _TARGA_RE.search(combined)
    iuv = (
        str(ai_data.get("iuv") or "").strip()
        or pagopa_data.get("identificativo_bolletta")
        or (iuv_match.group(1) if iuv_match else None)
    )
    targa_ai = str(ai_data.get("targa") or "").strip().upper()
    targa = (
        targa_ai if _TARGA_RE.fullmatch(targa_ai)
        else pagopa_data.get("targa")
        or (targa_match.group(1).upper() if targa_match else None)
    )
    importo, importo_fonte, importo_conflitto = _select_document_amount(ai_data, pagopa_data, text)
    data_pagamento = _extract_payment_date(text)
    negative_payment = (
        pagopa_data.get("document_kind") == "ESITO_PAGOPA_NEGATIVO"
        or any(marker in combined.casefold() for marker in _NEGATIVE_PAYMENT_MARKERS)
    )
    is_receipt = not negative_payment and (
        pagopa_data.get("is_payment_receipt") is True
        or
        ai_data.get("tipo_documento") == "ricevuta_pagopa"
        or any(marker in combined.casefold() for marker in _RICEVUTA_MARKERS)
    )
    is_notice = pagopa_data.get("document_kind") == "AVVISO_PAGOPA"
    numero = normalizza_numero_verbale(numero)
    iuv = normalizza_iuv(iuv)
    violation_date = (
        ai_data.get("data_violazione")
        or pagopa_data.get("data_violazione")
        or _extract_violation_date(text)
    )
    return {
        "sha256": sha256, "text": text, "parsed_metadata": parsed_metadata,
        "ai_data": ai_data, "ai_was_used": ai_was_used, "ai_error": ai_error,
        "pagopa_data": pagopa_data, "numero": numero, "iuv": iuv, "targa": targa,
        "importo": importo, "importo_fonte": importo_fonte,
        "importo_conflitto": importo_conflitto, "data_pagamento": data_pagamento,
        "data_violazione": violation_date, "is_receipt": is_receipt,
        "is_notice": is_notice, "negative_payment": negative_payment,
    }


async def process_verbale_document(
    db,
    *,
    document_id: str,
    content: bytes,
    filename: str,
    source: str = "drive_verbale",
    parsed_metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Conserva relazioni certe; senza numero/IUV lascia il PDF da rivedere."""
    letto = await leggi_documento_verbale(content, filename, parsed_metadata)
    sha256, text = letto["sha256"], letto["text"]
    parsed_metadata, ai_data = letto["parsed_metadata"], letto["ai_data"]
    ai_was_used, ai_error = letto["ai_was_used"], letto["ai_error"]
    pagopa_data = letto["pagopa_data"]
    numero, iuv, targa = letto["numero"], letto["iuv"], letto["targa"]
    importo, importo_fonte = letto["importo"], letto["importo_fonte"]
    importo_conflitto, data_pagamento = letto["importo_conflitto"], letto["data_pagamento"]
    is_receipt, is_notice = letto["is_receipt"], letto["is_notice"]
    now = datetime.now(timezone.utc).isoformat()

    extracted = {
        "numero_verbale_estratto": numero,
        "iuv_estratto": iuv,
        "targa_estratta": targa,
        "importo_estratto": importo,
        "importo_fonte": importo_fonte,
        "importo_conflitto_risolto": importo_conflitto,
        "codice_avviso_estratto": pagopa_data.get("codice_avviso"),
        "codice_cbill_estratto": pagopa_data.get("codice_cbill"),
        "data_scadenza_estratta": pagopa_data.get("data_scadenza"),
        "document_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "estrazione_ai_usata": ai_was_used,
        "estrazione_parser_locale": bool(parsed_metadata),
        "estrazione_ai_errore": ai_error,
        "updated_at": now,
    }

    if is_receipt:
        receipt_id = f"pagopa_{sha256[:32]}"
        receipt = {
            "id": receipt_id,
            "source_document_id": document_id,
            "source_sha256": sha256,
            "filename": filename,
            "numero_verbale": numero,
            "iuv": iuv,
            "targa": targa,
            "importo": importo,
            "data_pagamento": data_pagamento,
            "source": source,
            "stato": "non_associata",
            "updated_at": now,
        }
        await db["ricevute_pagopa"].update_one(
            {"id": receipt_id},
            {"$set": receipt, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        candidates = []
        references = []
        if numero:
            references.append({"numero_verbale": numero})
        if iuv:
            references.append({"iuv": iuv})
        if references and importo:
            candidates = await db["verbali_noleggio"].find(
                {"$or": references}, {"_id": 0}
            ).limit(20).to_list(20)
            candidates = [
                item for item in candidates
                if amounts_equal_to_cent(item.get("importo"), importo)
            ]
        linked_verbale = None
        if len(candidates) == 1:
            from app.services.verbali_pagamento_finder import applica_pagamento_a_verbale

            candidate = candidates[0]
            linked_verbale = candidate.get("id") or candidate.get("numero_verbale")
            applied = await applica_pagamento_a_verbale(db, linked_verbale, {
                "fonte": "gmail" if source.startswith("email") else "drive_pagopa",
                "psp": "PagoPA",
                "importo": importo,
                "data_pagamento": data_pagamento,
                "metodo_pagamento": "PagoPA",
                "ricevuta_pagopa_id": receipt_id,
                "iuv_usato": iuv,
            })
            if applied:
                await db["ricevute_pagopa"].update_one(
                    {"id": receipt_id},
                    {"$set": {"stato": "associata", "verbale_id": linked_verbale}},
                )
        await db["documents_inbox"].update_one(
            {"id": document_id},
            {"$set": {
                **extracted,
                "tipo_documento": "ricevuta_pagopa",
                "categoria": "ricevuta_pagopa",
                "category": "ricevuta_pagopa",
                "ricevuta_pagopa_id": receipt_id,
                "verbale_id": linked_verbale,
                "processed": bool(linked_verbale),
                "status": "processato" if linked_verbale else "da_revisionare",
            }},
        )
        return {
            "status": "linked" if linked_verbale else "review",
            "tipo": "ricevuta_pagopa",
            "receipt_id": receipt_id,
            "verbale_id": linked_verbale,
        }

    if not numero and not iuv:
        await db["documents_inbox"].update_one(
            {"id": document_id},
            {"$set": {**extracted, "processed": False, "status": "da_revisionare"}},
        )
        return {"status": "review", "tipo": "verbale", "reason": "numero_e_iuv_assenti"}

    identity = {"numero_verbale": numero} if numero else {"iuv": iuv}
    existing = await db["verbali_noleggio"].find_one(identity, {"_id": 0})
    verbale_id = str((existing or {}).get("id") or f"verbale_{hashlib.sha256(str(identity).encode()).hexdigest()[:32]}")
    violation_date = letto["data_violazione"]
    vehicle = await _vehicle_context(db, targa, violation_date)
    notification_date = (
        parsed_metadata.get("data_notifica")
        or parsed_metadata.get("email_received_date")
        or parsed_metadata.get("received_date")
    )
    reduced_amount = _float_or_none(ai_data.get("importo_ridotto"))
    ordinary_amount = _float_or_none(ai_data.get("importo_ordinario"))
    expectations = _verbale_expectations(
        verbale_id=verbale_id,
        source_document_id=document_id,
        notification_date=notification_date,
        reduced_amount=reduced_amount,
        ordinary_amount=ordinary_amount,
    )
    values = {
        "id": verbale_id,
        "numero_verbale": numero,
        "iuv": iuv,
        "targa": targa,
        "importo": importo,
        "importo_fonte": importo_fonte,
        "importo_conflitto_risolto": importo_conflitto,
        "data_verbale": ai_data.get("data_verbale"),
        "data_violazione": violation_date,
        "data_scadenza": pagopa_data.get("data_scadenza"),
        "codice_avviso": pagopa_data.get("codice_avviso"),
        "codice_cbill": pagopa_data.get("codice_cbill"),
        "ora_violazione": ai_data.get("ora_violazione"),
        "numero_atto": ai_data.get("numero_atto"),
        "numero_registro": ai_data.get("numero_registro"),
        "ente_creditore": ai_data.get("ente_creditore") or pagopa_data.get("beneficiario"),
        "articolo_cds": ai_data.get("articolo_cds"),
        "descrizione_violazione": ai_data.get("descrizione_violazione"),
        "responsabile": ai_data.get("responsabile"),
        "partita_iva_responsabile": ai_data.get("partita_iva_responsabile"),
        "indirizzo_violazione": ai_data.get("indirizzo_violazione"),
        "obbligato_in_solido": ai_data.get("obbligato_in_solido"),
        "societa_locazione": ai_data.get("societa_locazione"),
        "importo_ridotto": reduced_amount,
        "importo_ordinario": ordinary_amount,
        "data_notifica": notification_date,
        "workflow_expectations": expectations,
        "operation_id": f"verbale:{verbale_id}",
        "ambito": "veicolo" if targa else "amministrativo",
        "source_document_id": document_id,
        "source_sha256": sha256,
        # L'originale resta sul verbale (campo `pdf_data`, gia' letto da
        # `collect_verbale_pdfs`; il payload va in `gestionale.blobs`): la copia in
        # `documents_inbox` si perde quando l'inbox si svuota, il verbale no.
        "pdf_data": base64.b64encode(content).decode("ascii"),
        "pdf_filename": filename,
        "pdf_hash": sha256,
        "pdf_size": len(content),
        "source": source,
        # Un avviso cita numero/targa ma non e' il verbale originale. Mantieni
        # il legacy ``stato`` per le viste esistenti e usa questi campi come
        # stato probatorio autorevole.
        "origine": "AVVISO_PAGOPA" if is_notice else "VERBALE_ORIGINALE",
        "verbale_originale_acquisito": not is_notice,
        "numero_verbale_citato": numero if is_notice else None,
        "targa_citata": targa if is_notice else None,
        "stato_pratica": "DA_ACQUISIRE_VERBALE" if is_notice else ((existing or {}).get("stato_pratica") or "APERTO"),
        "review_questions": ([
            {"key": "verbale_originale", "question": "Esiste la copia del verbale originale?", "required": True},
            {"key": "indirizzo_risposta", "question": "Quale indirizzo/PEC ufficiale deve ricevere la risposta?", "required": False},
            {"key": "targa_confermata", "question": "Confermi la targa estratta dal documento?", "required": True},
            {"key": "driver_confermato", "question": "Esiste un'assegnazione o un viaggio compatibile con il driver alla data?", "required": True},
            {"key": "copia_pagamento", "question": "Esiste una copia del pagamento e qual e' la fonte?", "required": True},
            {"key": "movimento_bancario", "question": "Esiste un movimento bancario collegato al pagamento?", "required": True},
            {"key": "autorizza_chiusura", "question": "Autorizzi la chiusura solo dopo evidenza completa?", "required": True},
        ] if is_notice else []),
        "stato": (existing or {}).get("stato") or ("salvato" if is_notice else "aperto"),
        "updated_at": now,
        **vehicle,
    }
    if existing:
        values = {
            key: value for key, value in values.items()
            if value not in (None, "") and (existing.get(key) in (None, "") or key in {
                "source_document_id", "source_sha256", "updated_at",
                *(('importo', 'importo_fonte', 'importo_conflitto_risolto') if importo_conflitto else ()),
            })
        }
    verbale_query = (
        {"id": existing.get("id")}
        if existing and existing.get("id")
        else identity if existing
        else {"id": verbale_id}
    )
    await db["verbali_noleggio"].update_one(
        verbale_query,
        {
            "$set": values,
            "$setOnInsert": {"created_at": now},
            "$addToSet": {"document_ids": document_id},
        },
        upsert=True,
    )
    for expectation in expectations:
        expectation_id = f"{expectation['operation_id']}:{expectation['expectation_type']}"
        await db["workflow_expectations"].update_one(
            {"id": expectation_id},
            {"$set": {"id": expectation_id, **expectation, "updated_at": now},
             "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
    await _schedule_verbale_notifications(
        db, verbale_id=verbale_id, notification_date=notification_date, now_iso=now,
    )
    await db["documents_inbox"].update_one(
        {"id": document_id},
        {"$set": {
            **extracted,
            "verbale_id": verbale_id,
            "processed": True,
            "status": "processato",
        }},
    )
    return {"status": "linked", "tipo": "verbale", "verbale_id": verbale_id}
