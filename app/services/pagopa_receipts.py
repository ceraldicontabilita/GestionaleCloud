"""Import canonico e parsing conservativo delle ricevute PagoPA/CBILL."""
from __future__ import annotations

import base64
import hashlib
import inspect
import io
import logging
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.services.ocr_locale import MemoriaInsufficiente, motore
from app.services.payment_invoice_matching import amounts_equal_to_cent

logger = logging.getLogger(__name__)


def non_collegato(campo: str) -> dict[str, Any]:
    """«Non ancora collegato»: campo assente, null o vuoto.

    `$in: [None, ""]` da solo non prende le righe che il campo non l'hanno
    mai avuto, cioe' proprio quelle mai collegate.
    """
    return {"$or": [{campo: {"$exists": False}}, {campo: {"$in": [None, ""]}}]}


COLLECTION_RICEVUTE = "ricevute_pagopa"

# Campi che una ricevuta di intermediario porta oltre a quelli pagoPA/CBILL.
CAMPI_INTERMEDIARIO = (
    "intermediario", "metodo_pagamento", "paypal_transaction_id", "payment_id",
    "ente_creditore", "id_ricevuta", "id_operazione", "identificativo_riscossione",
    "causale", "ora_pagamento", "importi_quadrano",
    "agente_riscossione", "intestatario", "psp_bic", "psp_nome", "documenti",
    "cartella_number", "importo_tributi", "interessi_mora", "diritti_notifica",
    "natura", "natura_fonte",
)

# Che cos'e' il pagamento verso l'ente: lo dice il titolare, la ricevuta no.
NATURE_RICEVUTA = {
    "tributo": "Tributo",
    "rata_rateizzazione": "Rata di rateizzazione",
    "onere_pratica": "Diritti o oneri di una pratica",
    "sanzione_interessi": "Sanzione o interessi",
    "altro": "Altro",
}
PARSER_VERSION = "payment-receipt-layout-v5"


def _money_decimal(value: str | None) -> Decimal | None:
    if not value:
        return None
    try:
        return Decimal(
            value.replace("EUR", "").replace("€", "").replace(".", "")
            .replace(",", ".").replace("-", "").strip()
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


def _bank_amounts(text: str) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """Separa importo operazione, commissione e totale addebitato.

    I layout BPM dispongono spesso tutte le etichette prima dei valori. La
    relazione aritmetica operazione + commissione = totale e' quindi piu'
    affidabile della vicinanza nel testo estratto.
    """
    clean = "\n".join(
        line for line in text.splitlines() if not line.strip().upper().startswith("INDEX:")
    )
    # pypdf concatena talvolta data e importo ("01/08/2024438,95").
    clean = re.sub(r"(\d{2}/\d{2}/\d{4})(?=\d{1,3}(?:\.\d{3})*,\d{2})", r"\1 ", clean)
    values = [
        amount for token in re.findall(r"(?<!\d)(\d{1,3}(?:\.\d{3})*,\d{2})-?", clean)
        if (amount := _money_decimal(token)) is not None
    ]
    candidates: list[tuple[int, Decimal, Decimal, Decimal]] = []
    for operation_index, operation in enumerate(values):
        for fee_index, fee in enumerate(values):
            if fee_index == operation_index or fee > Decimal("50.00"):
                continue
            for total_index, total in enumerate(values):
                if total_index in (operation_index, fee_index):
                    continue
                if operation + fee != total:
                    continue
                score = 0
                score += 3 if total >= operation else 0
                score += 2 if fee <= operation else 0
                score += 1 if fee <= Decimal("10.00") else 0
                candidates.append((score, operation, fee, total))
    if candidates:
        _score, operation, fee, total = max(candidates, key=lambda item: item[0])
        return operation, fee, total

    operation_match = re.search(
        r"IMPORTO\s+OPERAZIONE\s*([\d.]+,\d{2})-?", clean, re.IGNORECASE,
    )
    fee_match = re.search(r"COMMISSIONI\s*([\d.]+,\d{2})-?", clean, re.IGNORECASE)
    operation = _money_decimal(operation_match.group(1)) if operation_match else None
    fee = _money_decimal(fee_match.group(1)) if fee_match else Decimal("0.00")
    if operation is None:
        return None, fee, None
    # Il totale non si ricalcola in silenzio: se la ricevuta ne stampa uno (o piu') e nessuno e'
    # operazione + commissione (o la sola operazione) al centesimo, la somma delle voci non
    # torna e il pagamento resta da verificare (totale ignoto), mai «corretto» dal lettore.
    stampati = [
        _money_decimal(valore) for valore in re.findall(
            r"(?:TOTALE\s+ADDEBITO|IMPORTO\s+TOTALE|TOTALE)\s*:?\s*([\d.]+,\d{2})-?", clean, re.IGNORECASE,
        )
    ]
    stampati = [valore for valore in stampati if valore is not None]
    if stampati and not any(valore in (operation + fee, operation) for valore in stampati):
        return operation, fee, None
    return operation, fee, operation + fee


def _parse_bpm_payment(text: str) -> dict[str, Any]:
    compact = re.sub(r"\s+", " ", text).strip()
    upper = compact.upper()
    document_kind = None
    if any(marker in upper for marker in (
        "CODICE IDENTIFICATIVO CBILL", "CBILL - PAGOPA", "CODICE TRANSAZIONE CBILL",
    )):
        document_kind = "RICEVUTA_CBILL"
    elif "PAGAMENTO MAV" in upper:
        document_kind = "RICEVUTA_MAV"
    elif "PAGAMENTO RAV" in upper:
        document_kind = "RICEVUTA_RAV"
    elif "BOLLETTINO POSTALE" in upper and ("COD.RIF" in upper or "ID. POSTE" in upper):
        document_kind = "RICEVUTA_BOLLETTINO_POSTALE"
    if not document_kind:
        return {}

    operation, fee, total = _bank_amounts(text)
    patterns = {
        "identificativo_bolletta": (
            r"(?:CODICE\s+IDENTIFICATIVO\s+CBILL|IDENTIFICATIVO\s+BOLLETTA\s*:?)\s*(\d{15,20})",
            r"\b(1[038]\d{15,18}|30\d{16})\b",
        ),
        "numero_bollettino": (r"NUMERO\s+BOLLETTINO\s*[:#-]?\s*(\d{10,20})",),
        "transaction_code": (r"CODICE\s+TRANSAZIONE(?:\s+CBILL)?\s*[:#-]?\s*([A-Z0-9]{8,20})",),
        "operation_code": (
            r"CODICE\s+OPERAZIONE\s*[:#-]?\s*([A-Z0-9]{8,20})",
            r"N\.\s*VERSAMENTO\s*[:#-]?\s*([A-Z0-9]{8,20})",
        ),
        "nop": (r"\bNOP\s*[:#-]?\s*([A-Z0-9]{6,30})",),
        "sia_biller": (r"CODICE\s+SIA\s+BILLER\s*[:#-]?\s*([A-Z0-9]{4,10})",),
        "reference_code": (r"COD\.\s*RIF\s*[:#-]?\s*([A-Z0-9]{8,30})",),
        "poste_id": (r"ID\.\s*POSTE\s*[:#-]?\s*([A-Z0-9]{6,30})",),
        "operation_number": (r"N\.\s*OP\s*([A-Z0-9]{6,30})",),
        "postal_account_number": (
            r"(?:C/C|CONTO\s+CORRENTE)\s*POSTALE\s*(?:N\.?|NUMERO)?\s*[:#-]?\s*(\d{5,20})",
        ),
        "cv_code": (r"\bC\.\s*V\.\s*[:#-]?\s*([A-Z0-9]{2,30})",),
    }
    parsed: dict[str, Any] = {}
    raw_identifiers: dict[str, str] = {}
    for field, field_patterns in patterns.items():
        for pattern in field_patterns:
            match = re.search(pattern, compact, re.IGNORECASE)
            if match:
                raw_value = match.group(1).strip()
                raw_identifiers[field] = raw_value
                parsed[field] = re.sub(r"\s+", "", raw_value).upper()
                break
    if parsed.get("sia_biller") in {"IMPORTO", "UFFICIO", "DEBITO", "VALUTA"}:
        parsed.pop("sia_biller", None)
    if not parsed.get("sia_biller"):
        sia_candidate = re.search(r"\b([A-Z]{2,4}\d[A-Z0-9])\b", compact)
        if sia_candidate:
            parsed["sia_biller"] = sia_candidate.group(1)
            raw_identifiers["sia_biller"] = sia_candidate.group(1)
    if document_kind == "RICEVUTA_CBILL" and not parsed.get("numero_bollettino"):
        number_candidate = re.search(
            r"\b\d{18}\b\s+(\d{10})\b", compact,
        )
        if number_candidate:
            parsed["numero_bollettino"] = number_candidate.group(1)
            raw_identifiers["numero_bollettino"] = number_candidate.group(1)

    dates = []
    for day, month, year in re.findall(r"\b([0-3]\d)/([01]\d)/(20\d{2})\b", compact):
        try:
            value = datetime(int(year), int(month), int(day)).date().isoformat()
        except ValueError:
            continue
        if value not in dates:
            dates.append(value)
    beneficiary_match = re.search(
        r"BENEFICIARIO\s*:\s*(.+?)\s+CODICE\s+BENEF\.", compact, re.IGNORECASE,
    ) or re.search(r"BENEFICIARIO\s*-\s*(.+?)(?:\s+UTENZE|\s+EUR\d)", compact, re.IGNORECASE)
    if not beneficiary_match and document_kind == "RICEVUTA_BOLLETTINO_POSTALE":
        beneficiary_match = re.search(
            r"BOLLETTINO\s+POSTALE.+?\s+([A-Z][A-Z0-9 .'-]{8,}?)\s+EUR\d",
            compact, re.IGNORECASE,
        )
    causale_match = re.search(
        r"(?:CODICE\s+OPERAZIONE|N\.\s*OP)[^\n]*\n(.+?)(?:\nEUR\d|\nCERALDI GROUP)",
        text, re.IGNORECASE | re.DOTALL,
    )
    identifier = (
        parsed.get("identificativo_bolletta") or parsed.get("numero_bollettino")
        or parsed.get("reference_code") or parsed.get("operation_number")
    )
    payer_tax_id = next(iter(re.findall(r"\b\d{11}\b", compact)), None)
    if payer_tax_id:
        raw_identifiers.setdefault("payer_tax_id", payer_tax_id)
        parsed.setdefault("payer_tax_id", payer_tax_id)
    amount_float = float(operation) if operation is not None else None
    fee_float = float(fee) if fee is not None else None
    total_float = float(total) if total is not None else None
    def source_line(value: Any) -> str:
        needle = (
            f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
            if isinstance(value, float) else str(value)
        )
        return next(
            (line.strip() for line in text.splitlines() if needle in line),
            needle,
        )

    evidence = {
        field: {
            "page_number": 1,
            "source_text": source_line(value),
            "normalized_value": value,
            "parser_version": PARSER_VERSION,
        }
        for field, value in {
            "identificativo_bolletta": identifier,
            "importo_operazione": amount_float,
            "commissione": fee_float,
            "totale_addebito": total_float,
            "data_pagamento": dates[0] if dates else None,
        }.items() if value is not None
    }
    for field, raw_value in raw_identifiers.items():
        evidence[field] = {
            "page_number": 1,
            "source_text": raw_value,
            "raw_value": raw_value,
            "normalized_value": parsed.get(field),
            "parser_version": PARSER_VERSION,
        }
    return {
        **parsed,
        "document_kind": document_kind,
        "identificativo_bolletta": identifier,
        "codice_cbill": parsed.get("identificativo_bolletta") if document_kind == "RICEVUTA_CBILL" else None,
        "importo": amount_float,
        "operation_amount": amount_float,
        "operation_amount_cents": int(operation * 100) if operation is not None else None,
        "fee_amount": fee_float,
        "fee_amount_cents": int(fee * 100) if fee is not None else None,
        "bank_debit_total": total_float,
        "bank_debit_total_cents": int(total * 100) if total is not None else None,
        "data_pagamento": dates[0] if dates else None,
        "beneficiario": beneficiary_match.group(1).strip(" -") if beneficiary_match else None,
        "payer_tax_id": payer_tax_id,
        "causale": re.sub(r"\s+", " ", causale_match.group(1)).strip() if causale_match else None,
        "is_payment_receipt": operation is not None and total is not None,
        "raw_identifiers": raw_identifiers,
        "identifiers": {
            field: {"raw": raw_value, "normalized": parsed.get(field)}
            for field, raw_value in raw_identifiers.items()
        },
        "parser_version": PARSER_VERSION,
        "field_evidence": evidence,
    }


# --- Ricevuta «per l'utente» di Mooney (pagoPA pagato con PayPal) -----------
#
# Mooney scrive nel livello testo solo il riquadro degli importi e l'ID
# ricevuta; tutto il resto (data e ora, beneficiario, ente creditore, IUV,
# PayPal ID) e' un'immagine. Con 226 caratteri di testo il lettore generico si
# fermava li' e non trovava ne' IUV ne' data: la ricevuta non risultava un
# pagamento. Qui si riconosce dal marchio, si legge l'immagine con l'OCR gia'
# usato per gli avvisi e le righe si ricostruiscono per posizione: colonna
# sinistra (dati del servizio) e destra (importi, PayPal), etichetta e valore
# sulla stessa riga.
_MOONEY_MARCHIO = re.compile(r"MOONEY", re.IGNORECASE)
_MOONEY_TITOLO = re.compile(r"RICEVUTA\s*PER\s*L.?\s*UTENTE", re.IGNORECASE)


def e_ricevuta_mooney(text: str) -> bool:
    return bool(_MOONEY_MARCHIO.search(text or "") and _MOONEY_TITOLO.search(text or ""))


def _righe_ocr_per_posizione(content: bytes) -> str:
    """OCR della prima pagina con le righe rimesse in ordine di lettura.

    Il motore restituisce le scritte in un ordine che separa spesso l'etichetta
    dal suo valore (``Totale:`` e ``7,38`` a mille pixel di distanza): si
    raggruppano per colonna e per altezza, mai per ordine di uscita.
    """
    import fitz
    import numpy as np
    from PIL import Image

    from app.services.ocr_locale import motore

    righe: list[str] = []
    # Il motore vive solo per questo documento (ocr_locale): mai una quota permanente di memoria.
    with motore() as engine, fitz.open(stream=content, filetype="pdf") as document:
        for page in document:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = np.array(Image.open(io.BytesIO(pixmap.tobytes("png"))))
            risultato, _ = engine(image)
            metà = pixmap.width / 2
            voci = []
            for riquadro, testo, _confidenza in (risultato or []):
                if not str(testo).strip():
                    continue
                x = min(punto[0] for punto in riquadro)
                y = sum(punto[1] for punto in riquadro) / len(riquadro)
                voci.append((0 if x < metà else 1, y, x, str(testo).strip()))
            for colonna in (0, 1):
                gruppo = sorted((v for v in voci if v[0] == colonna), key=lambda v: (v[1], v[2]))
                corrente: list[tuple[float, str]] = []
                y_corrente = None
                for _, y, x, testo in gruppo:
                    if y_corrente is not None and abs(y - y_corrente) > 10:
                        righe.append(" ".join(t for _, t in sorted(corrente)))
                        corrente = []
                    if not corrente:
                        y_corrente = y
                    corrente.append((x, testo))
                if corrente:
                    righe.append(" ".join(t for _, t in sorted(corrente)))
    return "\n".join(righe)


def _importo_mooney(righe: str, etichetta: str) -> Decimal | None:
    trovato = re.search(
        rf"^\s*{etichetta}\s*:?\s*(\d{{1,3}}(?:\.\d{{3}})*[,.]\d{{2}})\s*€?\s*$",
        righe, re.IGNORECASE | re.MULTILINE,
    )
    if not trovato:
        return None
    testo = trovato.group(1)
    if "," in testo:
        testo = testo.replace(".", "").replace(",", ".")
    try:
        return Decimal(testo)
    except InvalidOperation:
        return None


def _parse_mooney_payment(text: str) -> dict[str, Any]:
    """Campi della ricevuta Mooney, o ``{}`` se il testo non e' la sua.

    La somma importo + diritti deve fare il totale al centesimo: una lettura
    dell'immagine che non torna non e' un pagamento, resta da verificare.
    """
    if not e_ricevuta_mooney(text):
        return {}
    righe = text

    def campo(modello: str) -> str | None:
        trovato = re.search(modello, righe, re.IGNORECASE | re.MULTILINE)
        return trovato.group(1).strip() if trovato else None

    importo = _importo_mooney(righe, "Importo")
    diritti = _importo_mooney(righe, "Diritti")
    totale = _importo_mooney(righe, "Totale")
    quadra = (
        importo is not None and diritti is not None and totale is not None
        and importo + diritti == totale
    )
    iuv = campo(r"\bIUV\s*:?\s*(\d{15,20})")
    data_ora = re.search(
        r"Data\s*e\s*[0o]ra\s*:?\s*(\d{2})/(\d{2})/(\d{4})\s*(\d{2}):(\d{2})",
        righe, re.IGNORECASE,
    )
    data_pagamento = ora = None
    if data_ora:
        giorno, mese, anno, ore, minuti = data_ora.groups()
        try:
            data_pagamento = datetime(int(anno), int(mese), int(giorno)).date().isoformat()
            ora = f"{ore}:{minuti}"
        except ValueError:
            data_pagamento = None
    paypal_id = campo(r"PayPal\s*ID\s*:?\s*([A-Z0-9]{15,20})")
    esito_positivo = bool(re.search(
        r"immediatamente\s*assolto|costituisce\s*attestazione\s*di\s*pagamento",
        righe, re.IGNORECASE,
    ))
    cifre = lambda valore: float(valore) if valore is not None else None  # noqa: E731
    centesimi = lambda valore: int(valore * 100) if valore is not None else None  # noqa: E731
    evidenze = {
        nome: {"page_number": 1, "source_text": valore, "normalized_value": valore,
               "parser_version": PARSER_VERSION}
        for nome, valore in (("iuv", iuv), ("beneficiario", campo(r"Beneficiario\s*:?\s*(.+)$")))
    }
    return {
        "document_kind": "RICEVUTA_PAGOPA",
        "intermediario": "Mooney",
        "metodo_pagamento": "PayPal" if paypal_id else None,
        "paypal_transaction_id": paypal_id,
        "identificativo_bolletta": iuv,
        "operation_amount": cifre(importo),
        "operation_amount_cents": centesimi(importo),
        "fee_amount": cifre(diritti),
        "fee_amount_cents": centesimi(diritti),
        "bank_debit_total": cifre(totale),
        "bank_debit_total_cents": centesimi(totale),
        "data_pagamento": data_pagamento,
        "ora_pagamento": ora,
        "beneficiario": campo(r"Beneficiario\s*:?\s*(.+)$"),
        "ente_creditore": campo(r"Ente\s*Creditore\s*:?\s*(\d{11})"),
        "id_ricevuta": campo(r"ID\s*Ricevuta\s*:?\s*([A-Z0-9]{6,20})"),
        "id_operazione": campo(r"ID\s*Operazione\s*:?\s*(\d{4,20})"),
        "payment_id": campo(r"Payment\s*ID\s*:?\s*(\d{10,25})"),
        "identificativo_riscossione": campo(r"Identificativo\s*Risc[o0]ssione\s*:?\s*([0-9a-f]{20,40})"),
        "causale": campo(r"Causale\s*:?\s*(.+)$"),
        "importi_quadrano": quadra,
        "is_payment_receipt": bool(quadra and iuv and data_pagamento and esito_positivo),
        "field_evidence": evidenze,
    }


# --- «Ricevuta di pagamento» dell'Agenzia delle Entrate-Riscossione ---------
#
# Il portale dell'Agente della Riscossione rilascia dopo ogni pagamento pagoPA
# un'attestazione col dettaglio per cartella: importo dei tributi e diritti di
# notifica separati. Ha il testo vero (niente OCR): una riga «etichetta: valore».
# Puo' pagare una cartella sola o piu' documenti con lo stesso IUV (pagina 1 col
# totale, poi un «Dettaglio documento» per ognuno). I diritti di notifica sono
# scritti dal documento stesso: quella e' l'unica volta in cui la natura del
# pagamento si legge invece di chiederla.
_ADER_TITOLO = re.compile(r"Ricevuta\s+di\s+pagamento", re.IGNORECASE)


def e_attestazione_ader(text: str) -> bool:
    testo = text or ""
    return bool(
        _ADER_TITOLO.search(testo)
        and re.search(r"Agente\s+della\s+Riscossione", testo, re.IGNORECASE)
        and re.search(r"Dettaglio\s+transazione", testo, re.IGNORECASE)
    )


def _importo_ader(valore: str | None) -> Decimal | None:
    if not valore:
        return None
    testo = valore.strip()
    if "," in testo:
        testo = testo.replace(".", "").replace(",", ".")
    try:
        return Decimal(testo).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _parse_ader_attestazione(text: str) -> dict[str, Any]:
    """Campi dell'attestazione AdER, o ``{}`` se il testo non e' la sua.

    Ogni documento deve far tornare tributi + diritti = totale e la somma dei
    documenti deve fare il totale del pagamento al centesimo: se non torna,
    non e' un pagamento riconosciuto, resta da verificare.
    """
    if not e_attestazione_ader(text):
        return {}

    def campo(modello: str, blocco: str = text) -> str | None:
        trovato = re.search(modello, blocco, re.IGNORECASE)
        return trovato.group(1).strip() if trovato else None

    def cifra(etichetta: str, blocco: str = text) -> Decimal | None:
        return _importo_ader(campo(rf"{etichetta}\s*:\s*€\s*([\d.,]+)", blocco))

    prima, *dettagli = re.split(r"Dettaglio\s+documento\s+n\.", text, flags=re.IGNORECASE)
    documenti: list[dict[str, Any]] = []
    for blocco in (dettagli or [prima]):
        # Ogni voce e' una riga «etichetta: € importo»; il totale e' l'unica che
        # comincia per «Totale». Nessun elenco chiuso di voci: una voce che
        # l'Agente aggiunge domani entra nella somma o fa fallire la quadratura.
        voci = [
            {"etichetta": re.sub(r"\s+", " ", etichetta).strip(),
             "importo": float(_importo_ader(valore) or 0)}
            for etichetta, valore in re.findall(
                r"^\s*([A-Za-zÀ-ÿ' ./]+?)\s*:\s*€\s*([\d.,]+)\s*$", blocco, re.MULTILINE)
            if not etichetta.strip().lower().startswith(("totale", "importo originario"))
        ]
        totale = cifra("Totale pagato", blocco)
        if totale is None:
            totale = cifra("Totale Cartella/Avviso", blocco)
        somma_voci = sum((Decimal(str(v["importo"])) for v in voci), Decimal("0")).quantize(Decimal("0.01"))

        def voce(nome: str, voci=voci) -> float | None:
            trovate = [v["importo"] for v in voci if v["etichetta"].lower() == nome]
            return trovate[0] if trovate else None

        documenti.append({
            "numero": campo(r"Cartella/Avviso\s+n\.\s*:\s*(\d{15,25})", blocco),
            "ente_creditore": campo(r"Ente\s+creditore\s*:\s*(.+)", blocco),
            "voci": voci,
            "importo_tributi": voce("importo tributi"),
            "interessi_mora": voce("interessi di mora"),
            "diritti_notifica": voce("diritti di notifica"),
            "totale": float(totale) if totale is not None else None,
            "quadra": bool(voci) and totale is not None and somma_voci == totale,
        })
    totale_pagamento = cifra("Totale pagamento", prima) if dettagli else cifra("Totale Cartella/Avviso", prima)
    somma = sum((Decimal(str(d["totale"])) for d in documenti if d["totale"] is not None), Decimal("0"))
    quadra = bool(
        totale_pagamento is not None and all(d["quadra"] for d in documenti)
        and somma == totale_pagamento
    )

    def totale_voce(chiave: str) -> Decimal:
        return sum((Decimal(str(d[chiave] or 0)) for d in documenti), Decimal("0"))

    tributi_totali = totale_voce("importo_tributi")
    interessi_totali = totale_voce("interessi_mora")
    diritti_totali = totale_voce("diritti_notifica")
    solo_diritti = bool(
        quadra and diritti_totali > 0 and tributi_totali == 0 and interessi_totali == 0
        and all(v["etichetta"].lower() == "diritti di notifica" for d in documenti for v in d["voci"])
    )
    data_ora = re.search(r"Data/ora\s*:\s*(\d{2})/(\d{2})/(\d{4})\s+(\d{2}:\d{2}(?::\d{2})?)", text)
    data_pagamento = ora = None
    if data_ora:
        giorno, mese, anno, ora = data_ora.groups()
        try:
            data_pagamento = datetime(int(anno), int(mese), int(giorno)).date().isoformat()
        except ValueError:
            data_pagamento = None
    iuv = campo(r"IUV[^:\n]{0,3}:\s*(\d{15,20})")
    psp = re.search(r"Identificativo\s+PSP\s*:\s*([A-Z0-9]{6,11})\s*-\s*(.+)", text)
    eseguita = bool(
        re.search(r"Transazione\s+eseguita", text, re.IGNORECASE)
        and re.search(r"registrato\s+correttamente", text, re.IGNORECASE)
    )
    numeri = [d["numero"] for d in documenti if d["numero"]]
    return {
        "document_kind": "RICEVUTA_PAGOPA",
        "intermediario": "Agenzia delle Entrate-Riscossione",
        "agente_riscossione": campo(r"Agente\s+della\s+Riscossione\s*:\s*(.+)"),
        "intestatario": campo(r"Intestata\s+a\s*:\s*(.+)"),
        "identificativo_bolletta": iuv,
        "operation_amount": float(totale_pagamento) if totale_pagamento is not None else None,
        "operation_amount_cents": int(totale_pagamento * 100) if totale_pagamento is not None else None,
        "bank_debit_total": float(totale_pagamento) if totale_pagamento is not None else None,
        "bank_debit_total_cents": int(totale_pagamento * 100) if totale_pagamento is not None else None,
        "data_pagamento": data_pagamento,
        "ora_pagamento": ora,
        "beneficiario": "ADER",
        "ente_creditore": campo(r"Cod\.\s*Fisc\.\s*Agente\s*Risc\.\s*:\s*(\d{11})"),
        "psp_bic": psp.group(1) if psp else None,
        "psp_nome": psp.group(2).strip() if psp else None,
        "documenti": documenti,
        "cartella_number": numeri[0] if numeri else None,
        "importo_tributi": float(tributi_totali),
        "interessi_mora": float(interessi_totali),
        "diritti_notifica": float(diritti_totali),
        "natura": "onere_pratica" if solo_diritti else None,
        "natura_fonte": "documento" if solo_diritti else None,
        "importi_quadrano": quadra,
        "is_payment_receipt": bool(quadra and iuv and data_pagamento and eseguita),
        "field_evidence": {
            nome: {"page_number": 1, "source_text": valore, "normalized_value": valore,
                   "parser_version": PARSER_VERSION}
            for nome, valore in (("iuv", iuv),)
        },
    }


def _attach_pdf_coordinates(content: bytes, parsed: dict[str, Any]) -> None:
    evidence = parsed.get("field_evidence") or {}
    if not evidence:
        return
    try:
        import fitz

        with fitz.open(stream=content, filetype="pdf") as document:
            for item in evidence.values():
                source_text = str(item.get("source_text") or "").strip()
                candidates = [source_text]
                value = item.get("normalized_value")
                if isinstance(value, float):
                    candidates.append(
                        f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
                    )
                for page_number, page in enumerate(document, start=1):
                    rectangles = []
                    for candidate in candidates:
                        rectangles = page.search_for(candidate) if candidate else []
                        if rectangles:
                            break
                    if rectangles:
                        item["page_number"] = page_number
                        rect = rectangles[0]
                        item["bbox"] = [round(rect.x0, 2), round(rect.y0, 2), round(rect.x1, 2), round(rect.y1, 2)]
                        break
    except Exception:
        # La provenienza testuale resta disponibile; coordinate mancanti non
        # trasformano mai il documento in una prova piu' forte.
        return


def _extract_receipt_text(content: bytes) -> tuple[str, bool]:
    """Estrae il testo e usa OCR locale solo per le attestazioni raster."""
    text = ""
    try:
        from pypdf import PdfReader

        text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)
    except Exception as exc:  # noqa: BLE001 - si prova PyMuPDF/OCR
        logger.warning(
            "Ricevuta pagoPA: testo vettoriale pypdf non letto (%s: %s)", type(exc).__name__, exc)
    if e_ricevuta_mooney(text):
        try:
            righe = _righe_ocr_per_posizione(content)
            if righe.strip():
                return f"{text}\n{righe}", True
        except MemoriaInsufficiente:
            raise            # non e' un OCR fallito: la ricevuta va riprovata, non letta a meta'
        except Exception as exc:  # noqa: BLE001 - senza OCR resta il solo testo vettoriale
            import logging

            logging.getLogger(__name__).warning(
                "OCR ricevuta Mooney non riuscito (%s: %s)", type(exc).__name__, exc)
    upper_native = re.sub(r"\s+", " ", text).upper()
    native_notice = any(marker in upper_native for marker in (
        "AVVISO DI PAGAMENTO", "QUANTO E QUANDO PAGARE", "RATA UNICA ENTRO IL",
    ))
    native_notice_has_code = bool(re.search(r"3(?:\s*\d){17}", text))
    if len(text.strip()) >= 150 and (not native_notice or native_notice_has_code):
        return text, False

    # Alcuni avvisi hanno un albero strutturale PDF difettoso: pypdf legge le
    # etichette ma perde proprio valori, QR e codici. PyMuPDF riesce spesso a
    # recuperare il testo vettoriale, evitando un OCR costoso e meno preciso.
    try:
        import fitz
        with fitz.open(stream=content, filetype="pdf") as document:
            fitz_text = "\n".join(page.get_text() or "" for page in document)
        fitz_upper = re.sub(r"\s+", " ", fitz_text).upper()
        fitz_notice = any(marker in fitz_upper for marker in (
            "AVVISO DI PAGAMENTO", "QUANTO E QUANDO PAGARE", "RATA UNICA ENTRO IL",
        ))
        fitz_notice_has_code = bool(re.search(r"3(?:\s*\d){17}", fitz_text))
        if len(fitz_text.strip()) >= 150 and (not fitz_notice or fitz_notice_has_code):
            return fitz_text, False
        if len(fitz_text.strip()) > len(text.strip()):
            text = fitz_text
    except Exception as exc:  # noqa: BLE001 - resta il testo di pypdf
        logger.warning(
            "Ricevuta pagoPA: testo PyMuPDF non letto (%s: %s)", type(exc).__name__, exc)

    try:
        import fitz
        import numpy as np
        from PIL import Image
        lines: list[str] = []
        with motore() as engine, fitz.open(stream=content, filetype="pdf") as document:
            for page in document:
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = np.array(Image.open(io.BytesIO(pixmap.tobytes("png"))))
                result, _ = engine(image)
                lines.extend(item[1] for item in (result or []) if item[1].strip())
        if lines:
            return "\n".join(lines), True
    except MemoriaInsufficiente:
        raise                # da riprovare, non da lasciare «da verificare» per sempre
    except Exception:
        # Senza dati leggibili la ricevuta resta da verificare e non produce
        # mai automaticamente uno stato PAGATO o CHIUSO.
        pass
    return text, False


def _pdf_page_count(content: bytes) -> int | None:
    """Numero pagine della fonte, mantenuto anche per PDF con OCR."""
    try:
        from pypdf import PdfReader

        return len(PdfReader(io.BytesIO(content)).pages)
    except Exception:
        try:
            import fitz

            with fitz.open(stream=content, filetype="pdf") as document:
                return document.page_count
        except Exception:
            return None


def parse_receipt_pdf(content: bytes, filename: str | None = None) -> dict[str, Any]:
    text, ocr_used = _extract_receipt_text(content)
    page_count = _pdf_page_count(content)
    compact = re.sub(r"\s+", " ", text)
    upper = compact.upper()
    marker_text = re.sub(r"[^A-Z0-9]", "", upper)
    bpm_payment = (_parse_bpm_payment(text) or _parse_mooney_payment(text)
                   or _parse_ader_attestazione(text))
    if bpm_payment:
        _attach_pdf_coordinates(content, bpm_payment)
    is_notice = any(marker in marker_text for marker in (
        "AVVISODIPAGAMENTO", "QUANTOEQUANDOPAGARE", "RATAUNICAENTROIL",
    ))
    is_receipt = any(marker in marker_text for marker in (
        "ATTESTAZIONEDIPAGAMENTO", "PAGAMENTOESEGUITO",
        "IMPORTOTOTALEPAGATO", "RICEVUTATELEMATICA",
    ))
    is_negative_outcome = any(marker in marker_text for marker in (
        "PAGAMENTONONESEGUITO", "PAGAMENTORIFIUTATO",
        "PAGAMENTOANNULLATO", "ESITONEGATIVO",
    ))
    code = bpm_payment.get("identificativo_bolletta")
    code_source = f"{compact} {filename or ''}"
    for pattern in (
        r"(?:identificativo\s+(?:univoco\s+)?(?:versamento|bolletta)|id\s+univoco\s+versamento|IUV|CBILL)\s*[:#-]?\s*(\d{15,20})",
        r"\b(3(?:\s*\d){17})\b",
        r"\b([03]\d{16,17})\b",
    ):
        if code:
            break
        match = re.search(pattern, code_source, re.IGNORECASE)
        if match:
            code = re.sub(r"\s+", "", match.group(1))
            break
    notice_code = code if code and len(code) == 18 and code.startswith("3") else None
    normalized_iuv = code[1:] if notice_code else code
    amount = bpm_payment.get("operation_amount")
    amount_match = re.search(
        r"(?:importo\s+totale\s+pagato|importo\s+(?:pagato|versato|totale)|totale)\s*[:€EUR ]*([\d.]+,\d{2})",
        compact, re.IGNORECASE,
    )
    if amount_match and amount is None:
        amount = float(amount_match.group(1).replace(".", "").replace(",", "."))
    if amount is None and is_notice:
        notice_amount = re.search(
            r"(?:importo\s+(?:totale\s+)?da\s+pagare|rata\s+unica)\s*[:€EUR ]*([\d.]+,\d{2})",
            compact, re.IGNORECASE,
        )
        if notice_amount:
            amount = float(notice_amount.group(1).replace(".", "").replace(",", "."))
        else:
            unique_amounts = {
                match.replace(".", "")
                for match in re.findall(r"\b\d{1,3}(?:\.\d{3})*,\d{2}\b", compact)
            }
            if len(unique_amounts) == 1:
                amount = float(next(iter(unique_amounts)).replace(",", "."))
    payment_date = bpm_payment.get("data_pagamento")
    date_match = re.search(
        r"(?:data\s+(?:del\s+)?pagamento|pagato\s+il|data\s+ricevuta)\s*:?\s*(\d{2}/\d{2}/\d{4})",
        compact, re.IGNORECASE,
    )
    if date_match and not payment_date:
        day, month, year = date_match.group(1).split("/")
        payment_date = f"{year}-{month}-{day}"
    targa_match = re.search(r"\bTARGA\s*:\s*([A-Z]{2}\d{3}[A-Z]{2})\b", compact, re.IGNORECASE)
    verbale_match = re.search(
        r"\bVERBALE\s+N[.°º]?\s*:\s*([A-Z0-9/-]{6,30})",
        compact, re.IGNORECASE,
    )
    violation_date_match = re.search(
        r"\bTARGA\s*:\s*[A-Z]{2}\d{3}[A-Z]{2}\s*-\s*DATA\s*:\s*(\d{2}/\d{2}/\d{2,4})",
        compact, re.IGNORECASE,
    )
    violation_date = None
    if violation_date_match:
        day, month, year = violation_date_match.group(1).split("/")
        if len(year) == 2:
            year = f"20{year}"
        violation_date = f"{year}-{month}-{day}"
    beneficiary_match = re.search(
        r"ENTE\s+BENEFICIARIO.*?DENOMINAZIONE\s*:\s*(.+?)\s+(?:TIPO|ANAGRAFICA)\s*:",
        compact, re.IGNORECASE,
    )
    if not beneficiary_match:
        beneficiary_match = re.search(
            r"\b(COMUNE\s+DI\s+[A-ZÀ-Ü]+(?:\s+[A-ZÀ-Ü]+)*?)(?=\s+(?:CERALDI|SERVIZIO|\d{4,}|VIOLAZIONE)|$)",
            compact, re.IGNORECASE,
        )
    detected_dates = []
    for day, month, year in re.findall(r"\b([0-3]\d)/([01]\d)/(20\d{2})\b", compact):
        try:
            detected_dates.append(datetime(int(year), int(month), int(day)).date().isoformat())
        except ValueError:
            continue
    due_candidates = [value for value in detected_dates if value != violation_date]
    data_scadenza = max(due_candidates) if is_notice and due_candidates else None
    cbill_candidates = [
        value.upper()
        for value in re.findall(r"(?m)^\s*([A-Z0-9]{5})\s*$", text, re.IGNORECASE)
        if re.search(r"[A-Z]", value, re.IGNORECASE) and re.search(r"\d", value)
    ]
    codici_fiscali = list(dict.fromkeys(re.findall(r"(?m)^\s*(\d{11})\s*$", text)))
    document_kind = bpm_payment.get("document_kind") or (
        "ESITO_PAGOPA_NEGATIVO" if is_negative_outcome
        else "AVVISO_PAGOPA" if is_notice and not is_receipt
        else "RICEVUTA_PAGOPA"
    )
    beneficiary = (
        bpm_payment.get("beneficiario")
        or (beneficiary_match.group(1).strip() if beneficiary_match else None)
    )
    generic_evidence = {
        "iuv": {"page_number": 1, "source_text": normalized_iuv, "normalized_value": normalized_iuv, "parser_version": PARSER_VERSION},
        "codice_avviso": {"page_number": 1, "source_text": notice_code, "normalized_value": notice_code, "parser_version": PARSER_VERSION},
        "numero_verbale": {"page_number": 1, "source_text": verbale_match.group(1) if verbale_match else None, "normalized_value": verbale_match.group(1).upper().rstrip("-") if verbale_match else None, "parser_version": PARSER_VERSION},
        "targa": {"page_number": 1, "source_text": targa_match.group(1) if targa_match else None, "normalized_value": targa_match.group(1).upper() if targa_match else None, "parser_version": PARSER_VERSION},
        "importo": {"page_number": 1, "source_text": amount_match.group(0) if amount_match else None, "normalized_value": amount, "parser_version": PARSER_VERSION},
        "data_scadenza": {"page_number": 1, "source_text": data_scadenza, "normalized_value": data_scadenza, "parser_version": PARSER_VERSION},
        "beneficiario": {"page_number": 1, "source_text": beneficiary, "normalized_value": beneficiary, "parser_version": PARSER_VERSION},
        "codice_cbill": {"page_number": 1, "source_text": cbill_candidates[0] if cbill_candidates else None, "normalized_value": cbill_candidates[0] if cbill_candidates else None, "parser_version": PARSER_VERSION},
    }
    result = {
        **bpm_payment,
        "identificativo_bolletta": normalized_iuv,
        "codice_avviso": notice_code,
        "importo": amount,
        "operation_amount": amount,
        "operation_amount_cents": int(Decimal(str(amount)) * 100) if amount is not None else None,
        "bank_debit_total": bpm_payment.get("bank_debit_total") or amount,
        "bank_debit_total_cents": (
            bpm_payment.get("bank_debit_total_cents")
            or (int(Decimal(str(amount)) * 100) if amount is not None else None)
        ),
        "data_pagamento": payment_date,
        "targa": targa_match.group(1).upper() if targa_match else None,
        "numero_verbale": verbale_match.group(1).upper().rstrip("-") if verbale_match else None,
        "data_violazione": violation_date,
        "beneficiario": beneficiary,
        "data_scadenza": data_scadenza,
        "codice_cbill": bpm_payment.get("codice_cbill") or (cbill_candidates[0] if cbill_candidates else None),
        "codici_fiscali_rilevati": codici_fiscali,
        "text_detected": bool(text.strip()),
        "ocr_used": ocr_used,
        "page_count": page_count,
        "document_kind": document_kind,
        "is_payment_receipt": bool(
            bpm_payment.get("is_payment_receipt")
            or (is_receipt and not is_notice and not is_negative_outcome)
        ),
        "parser_version": PARSER_VERSION,
        "field_evidence": {**(bpm_payment.get("field_evidence") or {}), **generic_evidence},
    }
    _attach_pdf_coordinates(content, result)
    return result


async def find_bank_movement(db, code: str | list[str], amount: Any):
    codes = [str(item).strip() for item in ([code] if isinstance(code, str) else code) if str(item).strip()]
    if not codes or amount in (None, ""):
        return None
    references = []
    for item in codes:
        references.extend((
            {"descrizione_originale": {"$regex": re.escape(item)}},
            {"descrizione": {"$regex": re.escape(item)}},
        ))
    movements = await db.estratto_conto_movimenti.find({
        "$or": references,
        "$and": [non_collegato("ricevuta_pagopa_id")],
    }, {"_id": 0}).limit(20).to_list(20)
    exact = [item for item in movements if amounts_equal_to_cent(item.get("importo"), amount)]
    return exact[0] if len(exact) == 1 else None


async def _movimento_della_ricevuta(
    db, codes: list[str], values: dict[str, Any], amount: Any,
) -> dict[str, Any] | None:
    """Il movimento bancario della ricevuta: sempre per codice (IUV/CBILL o
    gli altri riferimenti forti) e importo al centesimo.

    L'importo si prova prima quello dell'operazione, poi l'addebito totale:
    la banca addebita l'importo netto (781,60) e la commissione a parte,
    mentre ``bank_debit_total`` lo somma (784,45) e non trovava mai niente.
    """
    tentati: list[Any] = []
    for importo in (values.get("operation_amount") or amount, values.get("bank_debit_total")):
        if importo in (None, "") or any(amounts_equal_to_cent(importo, t) for t in tentati):
            continue
        tentati.append(importo)
        movement = await find_bank_movement(db, codes, importo)
        if movement:
            return movement
    return None


async def collega_ricevuta_a_paypal(db, receipt: dict[str, Any]) -> dict[str, Any]:
    """Ricevuta pagata con PayPal -> il pagamento PayPal con lo stesso ID.

    L'identita' e' l'ID transazione scritto sulla ricevuta, mai l'importo da
    solo: senza quell'ID (o senza il pagamento in archivio) la ricevuta resta
    in attesa. L'importo dev'essere il totale addebitato al centesimo. Il
    movimento di banca si aggancia solo se e' quello gia' legato a quel
    pagamento PayPal e viene dall'estratto ufficiale.
    """
    from app.services.paypal_invoice_matching import transaction_amount

    paypal_id = str(receipt.get("paypal_transaction_id") or "").strip()
    if not paypal_id:
        return {"collegata": False, "motivo": "nessun_paypal_id"}
    transazione = await db["paypal_transactions"].find_one(
        {"$or": [{"transaction_id": paypal_id}, {"id": paypal_id}]}, {"_id": 0},
    )
    if not transazione:
        return {"collegata": False, "motivo": "paypal_non_ancora_in_archivio"}
    totale = receipt.get("bank_debit_total") or receipt.get("importo")
    if not amounts_equal_to_cent(transaction_amount(transazione), totale):
        return {"collegata": False, "motivo": "importo_paypal_diverso"}

    ora = datetime.now(timezone.utc).isoformat()
    campi: dict[str, Any] = {"paypal_collegato": True, "paypal_collegato_il": ora}
    movimento_id = transazione.get("movimento_banca_id") or transazione.get("estratto_conto_movimento_id")
    movimento = None
    if movimento_id and not receipt.get("movimento_id"):
        movimento = await db["estratto_conto_movimenti"].find_one({"id": movimento_id}, {"_id": 0})
        if not (movimento and movimento.get("evidenza_bancaria_ufficiale") is True
                and amounts_equal_to_cent(movimento.get("importo"), totale)):
            movimento = None
    if movimento:
        campi.update({"movimento_id": movimento["id"], "banca_verificata": True,
                      "movimento_data": movimento.get("data"), "movimento_importo": movimento.get("importo")})
        await db["estratto_conto_movimenti"].update_one(
            {"id": movimento["id"]},
            {"$set": {"ricevuta_pagopa_id": receipt["id"], "ricevuta_filename": receipt.get("filename"),
                      "updated_at": ora}},
        )
    await db[COLLECTION_RICEVUTE].update_one({"id": receipt["id"]}, {"$set": campi})
    # Un pagamento pagoPA non e' il pagamento di una fattura: fuori dall'abbinamento per importo.
    await db["paypal_transactions"].update_one(
        {"$or": [{"transaction_id": paypal_id}, {"id": paypal_id}]},
        {"$set": {"is_pagopa": True, "ricevuta_pagopa_id": receipt["id"]}},
    )
    return {"collegata": True, "campi": campi, "transaction_id": paypal_id, "banca": bool(movimento)}


async def ricollega_ricevute_paypal(db) -> dict[str, int]:
    """Rete: le ricevute Mooney arrivate prima del pagamento PayPal lo trovano
    appena la sincronizzazione lo porta (giro PayPal e importazione)."""
    esito = {"in_attesa": 0, "collegate": 0}
    attese = await db[COLLECTION_RICEVUTE].find({
        "paypal_transaction_id": {"$nin": [None, ""]},
        "paypal_collegato": {"$ne": True},
    }, {"_id": 0, "pdf_data": 0}).to_list(500)
    for ricevuta in attese:
        esito["in_attesa"] += 1
        if (await collega_ricevuta_a_paypal(db, ricevuta)).get("collegata"):
            esito["collegate"] += 1
    return esito


async def _associate_receipt_to_verbale(
    db, *, receipt_id: str, parsed: dict[str, Any], amount: Any,
) -> dict[str, Any]:
    """Collega solo identita' documentale esatta e importo al centesimo."""
    iuv = str(parsed.get("identificativo_bolletta") or "").strip()
    numero = str(parsed.get("numero_verbale") or "").strip().upper()
    references = []
    if iuv:
        references.extend(({"iuv": iuv}, {"codice_avviso": f"3{iuv}"}))
    if numero:
        references.append({"numero_verbale": numero})
    if not references or amount in (None, ""):
        return {"matched": False, "reason": "riferimenti_o_importo_assenti"}

    found = await db["verbali_noleggio"].find(
        {"$or": references}, {"_id": 0},
    ).limit(20).to_list(20)
    candidates: dict[str, dict[str, Any]] = {}
    for item in found:
        if not amounts_equal_to_cent(item.get("importo"), amount):
            continue
        key = str(item.get("id") or item.get("numero_verbale") or item.get("iuv"))
        candidates[key] = item
    if len(candidates) > 1:
        return {"matched": False, "reason": "candidati_ambigui", "candidate_count": len(candidates)}

    created = False
    if candidates:
        verbale = next(iter(candidates.values()))
    elif numero and iuv:
        now = datetime.now(timezone.utc).isoformat()
        verbale_id = f"verbale_{hashlib.sha256(f'{numero}:{iuv}'.encode()).hexdigest()[:32]}"
        verbale = {
            "id": verbale_id, "numero_verbale": numero, "iuv": iuv,
            "targa": parsed.get("targa"), "importo": float(amount),
            "data_violazione": parsed.get("data_violazione"),
            "source": "ricevuta_pagopa", "stato": "salvato",
            "created_at": now, "updated_at": now,
        }
        await db["verbali_noleggio"].update_one(
            {"id": verbale_id}, {"$setOnInsert": verbale}, upsert=True,
        )
        created = True
    else:
        return {"matched": False, "reason": "verbale_non_trovato"}

    from app.services.verbali_pagamento_finder import applica_pagamento_a_verbale

    verbale_id = verbale.get("id") or verbale.get("numero_verbale")
    applied = await applica_pagamento_a_verbale(db, verbale_id, {
        "fonte": "ricevuta_pagopa",
        "psp": "PagoPA",
        "importo": float(amount),
        "data_pagamento": parsed.get("data_pagamento"),
        "metodo_pagamento": "PagoPA",
        "ricevuta_pagopa_id": receipt_id,
        "iuv_usato": iuv,
    })
    return {
        "matched": bool(applied), "verbale_id": verbale_id,
        "numero_verbale": numero or verbale.get("numero_verbale"),
        "created_from_receipt": created,
        "rule": "iuv_o_numero_verbale_e_importo_esatto",
    }


async def import_receipt(
    db, *, content: bytes, filename: str, company_id: str,
    source: str = "upload_manuale", overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    # Mantiene compatibilita con parser/plugin preesistenti che espongono la
    # vecchia firma a un solo argomento, senza rinunciare al filename quando
    # il parser corrente puo usarlo come evidenza secondaria.
    parser_parameters = inspect.signature(parse_receipt_pdf).parameters
    parsed = (
        parse_receipt_pdf(content, filename=filename)
        if "filename" in parser_parameters
        else parse_receipt_pdf(content)
    )
    if "is_payment_receipt" not in parsed:
        parsed["is_payment_receipt"] = bool(parsed.get("data_pagamento"))
    if not parsed.get("is_payment_receipt"):
        return {
            "success": False, "filename": filename,
            "error": "Il documento non contiene un esito di pagamento PagoPA/CBILL",
            "requires_review": True,
            "document_kind": parsed.get("document_kind"),
            "parsed": parsed,
        }
    values = {**parsed, **{key: value for key, value in (overrides or {}).items() if value not in (None, "")}}
    code = str(values.get("identificativo_bolletta") or "").strip()
    amount = values.get("importo")
    if not code or amount in (None, ""):
        return {
            "success": False, "filename": filename,
            "error": "Ricevuta PagoPA/CBILL senza IUV/codice bolletta e importo leggibili",
            "requires_review": True,
        }

    pdf_hash = hashlib.sha256(content).hexdigest()
    existing = await db[COLLECTION_RICEVUTE].find_one(
        {"pdf_hash": pdf_hash}, {"_id": 0},
    )
    if existing:
        return {"success": True, "duplicate": True, "receipt": existing,
                "riconciliazione_fiscale": existing.get("riconciliazione_fiscale")}

    # Lo stesso pagamento documentato da un secondo file (l'attestazione del
    # portale dopo la ricevuta dell'intermediario): stesso IUV, stesso importo,
    # stesso giorno. Un solo record: il file nuovo non ne crea un secondo.
    stesso = await db[COLLECTION_RICEVUTE].find_one(
        {"identificativo_bolletta": code, "data_pagamento": values.get("data_pagamento")},
        {"_id": 0, "pdf_data": 0},
    )
    if stesso and amounts_equal_to_cent(stesso.get("importo"), amount):
        return {"success": True, "duplicate": True, "receipt": stesso,
                "duplicate_motivo": "stesso_iuv_importo_data",
                "riconciliazione_fiscale": stesso.get("riconciliazione_fiscale")}

    receipt_id = str(uuid.uuid4())
    strong_codes = list(dict.fromkeys(
        str(values.get(field) or "").strip()
        for field in (
            "identificativo_bolletta", "transaction_code", "operation_code",
            "reference_code", "poste_id", "operation_number",
        )
        if values.get(field)
    ))
    movement = await _movimento_della_ricevuta(db, strong_codes, values, amount)
    now = datetime.now(timezone.utc).isoformat()
    receipt = {
        "id": receipt_id, "filename": filename, "content_type": "application/pdf",
        "size": len(content), "pdf_data": base64.b64encode(content).decode("utf-8"),
        "pdf_hash": pdf_hash, "importo": float(amount),
        "operation_amount": float(amount),
        "operation_amount_cents": values.get("operation_amount_cents"),
        "fee_amount": values.get("fee_amount"),
        "fee_amount_cents": values.get("fee_amount_cents"),
        "bank_debit_total": values.get("bank_debit_total") or float(amount),
        "bank_debit_total_cents": values.get("bank_debit_total_cents"),
        "data_pagamento": values.get("data_pagamento"),
        "identificativo_bolletta": code,
        "codice_cbill": values.get("codice_cbill"),
        "numero_bollettino": values.get("numero_bollettino"),
        "transaction_code": values.get("transaction_code"),
        "operation_code": values.get("operation_code"),
        "nop": values.get("nop"),
        "sia_biller": values.get("sia_biller"),
        "reference_code": values.get("reference_code"),
        "poste_id": values.get("poste_id"),
        "operation_number": values.get("operation_number"),
        "postal_account_number": values.get("postal_account_number"),
        "cv_code": values.get("cv_code"),
        "raw_identifiers": values.get("raw_identifiers") or {},
        "identifiers": values.get("identifiers") or {},
        "document_kind": values.get("document_kind") or "RICEVUTA_PAGOPA",
        "parser_version": values.get("parser_version") or PARSER_VERSION,
        "field_evidence": values.get("field_evidence") or {},
        "numero_verbale": parsed.get("numero_verbale"),
        "targa": parsed.get("targa"),
        "data_violazione": parsed.get("data_violazione"),
        "beneficiario": values.get("beneficiario") or "ENTE CREDITORE PAGOPA DA VERIFICARE",
        "note": values.get("note"), "source": source,
        "movimento_id": movement.get("id") if movement else None,
        "associazione_automatica": bool(movement), "created_at": now,
        "versato_documentalmente": True,
        "banca_verificata": bool(movement),
        # Ricevuta di un intermediario (Mooney): chi ha incassato, con cosa e' stata
        # pagata e i riferimenti che la banca o PayPal potranno citare.
        **{campo: values.get(campo) for campo in CAMPI_INTERMEDIARIO if values.get(campo) not in (None, "")},
    }
    if receipt.get("natura") in NATURE_RICEVUTA:
        receipt["natura_label"] = NATURE_RICEVUTA[receipt["natura"]]
    if movement:
        receipt.update({"movimento_data": movement.get("data"),
                        "movimento_importo": movement.get("importo")})
        await db.estratto_conto_movimenti.update_one(
            {"id": movement["id"]}, {"$set": {
                "ricevuta_pagopa_id": receipt_id, "ricevuta_filename": filename,
                "updated_at": now,
            }},
        )
    await db[COLLECTION_RICEVUTE].insert_one(receipt.copy())
    try:
        import logging
        from app.services.cartelle_pagamento import chiudi_da_ricevuta

        await chiudi_da_ricevuta(db, receipt)
    except Exception as exc:  # la cartella non ferma l'import della ricevuta
        logging.getLogger(__name__).warning("Cartella non aggiornata dalla ricevuta %s (%s): %s",
                       receipt.get("id"), type(exc).__name__, exc)
    paypal = await collega_ricevuta_a_paypal(db, receipt)
    if paypal.get("collegata"):
        receipt.update(paypal["campi"])

    verbale_match = await _associate_receipt_to_verbale(
        db, receipt_id=receipt_id, parsed=parsed, amount=amount,
    )
    if verbale_match.get("matched"):
        receipt["verbale_id"] = verbale_match.get("verbale_id")
        receipt["riconciliazione_verbale"] = verbale_match
        await db[COLLECTION_RICEVUTE].update_one(
            {"id": receipt_id}, {"$set": {
                "verbale_id": receipt["verbale_id"],
                "riconciliazione_verbale": verbale_match,
            }},
        )

    from app.services.fiscal_evidence import register_document
    from app.services.fiscal_payment_reconciliation import reconcile_fiscal_payment

    document = await register_document(
        db, company_id=company_id, content=content, filename=filename, source=source,
        source_ref=receipt_id, category="riscossione",
        metadata={"receipt_collection": COLLECTION_RICEVUTE},
    )
    source_type = {
        "RICEVUTA_CBILL": "RICEVUTA_CBILL",
        "RICEVUTA_MAV": "RICEVUTA_MAV",
        "RICEVUTA_RAV": "RICEVUTA_RAV",
        "RICEVUTA_BOLLETTINO_POSTALE": "RICEVUTA_BOLLETTINO_POSTALE",
    }.get(receipt["document_kind"], "RICEVUTA_PAGOPA")
    fiscal_match = await reconcile_fiscal_payment(
        db, company_id=company_id,
        payment={**receipt, "amount": amount, "payment_date": receipt.get("data_pagamento")},
        source_type=source_type,
        source_id=receipt_id, document_id=document.get("document_id"), version_id=document.get("id"),
    )
    if fiscal_match.get("matched"):
        patch = {
            "fiscal_payment_id": fiscal_match["payment_id"],
            "fiscal_target_id": fiscal_match["target_id"],
            "fiscal_target_type": fiscal_match["target_type"],
            "cartelle_collegate": fiscal_match["linked_claim_ids"],
            "riconciliazione_fiscale": fiscal_match,
        }
        receipt.update(patch)
        await db[COLLECTION_RICEVUTE].update_one({"id": receipt_id}, {"$set": patch})
    return {"success": True, "duplicate": False, "receipt": receipt,
            "riconciliazione_fiscale": fiscal_match,
            "riconciliazione_verbale": verbale_match}
