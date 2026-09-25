"""Import del report ufficiale ``Fatture ricevute``.

Il file esportato dal portale fiscale non contiene gli XML: e' un indice
ufficiale che permette di misurare gli XML mancanti e di proporre collegamenti
senza inventare una fattura completa.  Le righe restano quindi separate dalla
collezione canonica ``invoices`` finche' non arriva il relativo XML.

Il titolare aggiunge al report tre colonne sue (metodo con cui ha pagato,
«carta di credito», numero dell'assegno): sono i dati veri del pagamento e li
porta in Prima Nota ``pagamenti_dichiarati_titolare``.
"""

from __future__ import annotations

import hashlib
import io
import math
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd


COLLECTION_REPORT = "fatture_report_ae"

REQUIRED_COLUMNS = {
    "Numero",
    "Nome file",
    "ID SdI",
    "Data documento",
    "Fornitore",
    "P.IVA",
    "Metodo di pagamento",
    "Totale documento",
    "Netto a pagare",
}

# Colonne che il titolare aggiunge al report: si cercano per nome, senza
# badare a maiuscole e spazi («assegno numero » nel file vero).
COLONNE_TITOLARE = {
    "metodo": ("metodo di pagamento canonico", "metodo pagamento titolare"),
    "carta": ("carta di credito",),
    "assegno": ("assegno numero", "numero assegno"),
}

# Stesso criterio di «fattura attiva» del giornale: una copia archiviata o
# in collisione non riceve pagamenti. `$nin` su un campo assente passa.
FILTRO_FATTURE_ATTIVE = {
    "status": {"$nin": ["archived", "archiviata", "deleted"]},
    "stato_import": {"$nin": ["archivio_storico", "collisione_identita_da_verificare"]},
    "entity_status": {"$ne": "deleted"},
    "deleted": {"$ne": True},
}

_PROIEZIONE_IDENTITA = {
    "_id": 0, "id": 1, "filename": 1, "invoice_number": 1, "numero_fattura": 1,
    "invoice_date": 1, "data_documento": 1, "data_fattura": 1,
    "supplier_vat": 1, "cedente_piva": 1, "fornitore_partita_iva": 1,
}


def _clean(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _text(value: Any) -> str:
    value = _clean(value)
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _vat(value: Any) -> str:
    return re.sub(r"\D", "", _text(value))


def _number(value: Any) -> float:
    value = _clean(value)
    if value in (None, ""):
        return 0.0
    if isinstance(value, str):
        normalized = value.strip().replace(" ", "")
        if "," in normalized and "." in normalized:
            normalized = normalized.replace(".", "").replace(",", ".")
        elif "," in normalized:
            normalized = normalized.replace(",", ".")
        value = normalized
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(parsed, 2) if math.isfinite(parsed) else 0.0


def _date(value: Any) -> str:
    value = _clean(value)
    if value in (None, ""):
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    testo = str(value).strip()
    # Il portale esporta date italiane (gg/mm/aaaa). Senza dayfirst pandas
    # legge 01/12/2026 come 12 gennaio: sbaglierebbe il mese, quindi il
    # periodo IVA e la chiave di aggancio con l'XML canonico.
    dayfirst = "/" in testo or "-" in testo and not re.match(r"^\d{4}-", testo)
    try:
        parsed = pd.to_datetime(testo, errors="coerce", dayfirst=dayfirst)
    except (TypeError, ValueError):
        return ""
    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d")


def _invoice_identity(document: Dict[str, Any]) -> Tuple[str, str, str]:
    piva = _vat(
        document.get("supplier_vat")
        or document.get("cedente_piva")
        or document.get("fornitore_partita_iva")
    )
    numero = re.sub(
        r"[^A-Z0-9]",
        "",
        _text(document.get("invoice_number") or document.get("numero_fattura")).upper(),
    )
    data_documento = _text(
        document.get("invoice_date")
        or document.get("data_documento")
        or document.get("data_fattura")
    )[:10]
    return piva, numero, data_documento


def _row_identity(row: Dict[str, Any]) -> Tuple[str, str, str]:
    return _invoice_identity({
        "supplier_vat": row.get("P.IVA"),
        "invoice_number": row.get("Numero"),
        "invoice_date": _date(row.get("Data documento")),
    })


def _nome_colonna(nome: Any) -> str:
    return " ".join(str(nome or "").lower().split())


async def _indice_fatture_attive(db):
    fatture = await db["invoices"].find(
        FILTRO_FATTURE_ATTIVE, _PROIEZIONE_IDENTITA,
    ).to_list(50000)
    per_nome_file = {
        _text(f.get("filename")).lower(): f for f in fatture if _text(f.get("filename"))
    }
    per_identita = {
        _invoice_identity(f): f for f in fatture if all(_invoice_identity(f))
    }
    return per_nome_file, per_identita


async def collega_righe_a_fatture(
    db, righe: List[Dict[str, Any]], *, salva: bool = True,
) -> int:
    """Riaggancia le righe del report alle fatture attive di adesso.

    L'XML puo' arrivare dopo il report, o la copia agganciata puo' essere
    stata archiviata dalla dedup: l'aggancio si rifa' a ogni giro invece di
    fidarsi di quello salvato all'import. Aggiorna le righe in memoria e sul
    database; ritorna quante sono cambiate.
    """
    per_nome_file, per_identita = await _indice_fatture_attive(db)
    cambiate = 0
    for riga in righe:
        naturale = (
            _vat(riga.get("supplier_vat")),
            re.sub(r"[^A-Z0-9]", "", _text(riga.get("numero_fattura")).upper()),
            _text(riga.get("data_documento"))[:10],
        )
        trovata = (
            per_nome_file.get(_text(riga.get("filename_xml")).lower())
            or per_identita.get(naturale)
        )
        invoice_id = trovata.get("id") if trovata else None
        if invoice_id != riga.get("invoice_id"):
            riga["invoice_id"] = invoice_id
            riga["xml_presente"] = bool(invoice_id)
            cambiate += 1
            if not salva:
                continue
            await db[COLLECTION_REPORT].update_one(
                {"report_key": riga["report_key"]},
                {"$set": {"invoice_id": invoice_id, "xml_presente": bool(invoice_id)}},
            )
    return cambiate


def _read_report(content: bytes, filename: str) -> pd.DataFrame:
    suffix = Path(filename or "").suffix.lower()
    engine = "xlrd" if suffix == ".xls" else "openpyxl"
    try:
        frame = pd.read_excel(io.BytesIO(content), engine=engine, dtype=object)
    except Exception as exc:
        raise ValueError(f"Report fatture non leggibile: {exc}") from exc
    frame.columns = [str(column).strip() for column in frame.columns]
    missing = sorted(REQUIRED_COLUMNS - set(frame.columns))
    if missing:
        raise ValueError(
            "Il foglio non e' il report Fatture ricevute: colonne mancanti "
            + ", ".join(missing)
        )
    return frame


def report_headers_match(content: bytes, filename: str) -> bool:
    """Riconosce il formato senza modificare dati."""
    try:
        frame = _read_report(content, filename)
    except ValueError:
        return False
    return REQUIRED_COLUMNS.issubset(set(frame.columns))


async def importa_report_fatture_ricevute(
    db,
    content: bytes,
    filename: str,
) -> Dict[str, Any]:
    """Indicizza tutte le righe e misura quali XML canonici sono presenti.

    Non inserisce righe in ``invoices``: il report non contiene l'XML originale
    e non deve generare IVA, Prima Nota o pagamenti come se fosse una fattura
    completa.
    """
    frame = _read_report(content, filename)
    source_hash = hashlib.sha256(content).hexdigest()
    now = datetime.now(timezone.utc).isoformat()

    from app.services.pagamenti_dichiarati_titolare import normalizza_metodo_titolare, numero_da_data_excel

    invoices_by_filename, invoices_by_identity = await _indice_fatture_attive(db)
    colonne = {
        chiave: next((c for c in frame.columns if _nome_colonna(c) in nomi), None)
        for chiave, nomi in COLONNE_TITOLARE.items()
    }
    con_titolare = 0

    imported = updated = invalid = xml_present = 0
    details: List[Dict[str, Any]] = []
    for position, raw in enumerate(frame.to_dict(orient="records"), start=2):
        numero = _text(raw.get("Numero"))
        nome_file_xml = Path(_text(raw.get("Nome file"))).name
        sdi_id = _text(raw.get("ID SdI"))
        data_documento = _date(raw.get("Data documento"))
        piva = _vat(raw.get("P.IVA"))
        if not numero or not data_documento or not (piva or sdi_id):
            invalid += 1
            if len(details) < 100:
                details.append({
                    "row": position,
                    "numero_fattura": numero,
                    "status": "invalid",
                    "message": "Numero, data o identificativo fiscale/SdI mancante",
                })
            continue

        natural = (piva, re.sub(r"[^A-Z0-9]", "", numero.upper()), data_documento)
        canonical = invoices_by_filename.get(nome_file_xml.lower()) or invoices_by_identity.get(natural)
        canonical_id = canonical.get("id") if canonical else None
        if canonical_id:
            xml_present += 1

        stable = sdi_id or "|".join(natural)
        report_key = hashlib.sha256(stable.encode("utf-8")).hexdigest()
        method = _text(raw.get("Metodo di pagamento"))
        titolare = {}
        if colonne["metodo"]:
            metodo_titolare = normalizza_metodo_titolare(
                raw.get(colonne["metodo"]),
                raw.get(colonne["carta"]) if colonne["carta"] else None,
            )
            assegno_grezzo = raw.get(colonne["assegno"]) if colonne["assegno"] else None
            assegno = (numero_da_data_excel(assegno_grezzo) or _text(assegno_grezzo)) if colonne["assegno"] else ""
            titolare = {
                "metodo_pagamento_titolare": metodo_titolare,
                "metodo_pagamento_titolare_testo": _text(raw.get(colonne["metodo"])),
                "assegno_numero_titolare": assegno,
                "pagata_titolare": _text(raw.get("Pagamenti")).lower() == "pagata",
            }
            if metodo_titolare:
                con_titolare += 1
        document = {
            "id": f"AEFR-{report_key[:24]}",
            "report_key": report_key,
            "sdi_id": sdi_id,
            "numero_fattura": numero,
            "filename_xml": nome_file_xml,
            "data_ricezione": _date(raw.get("Data ricezione")),
            "data_documento": data_documento,
            "anno": int(data_documento[:4]),
            "tipo_documento": _text(raw.get("Tipo documento")),
            "supplier_name": _text(raw.get("Fornitore")),
            "supplier_vat": piva,
            "supplier_cf": _text(raw.get("Codice Fiscale")),
            "metodo_pagamento_dichiarato": method,
            "modalita_pagamento_xml": "MP02" if "MP02" in method.upper() else "",
            "imponibile": _number(raw.get("Totale imponibile")),
            "iva": _number(raw.get("Totale IVA")),
            "totale_documento": _number(raw.get("Totale documento")),
            "netto_pagare": _number(raw.get("Netto a pagare")),
            "stato_pagamento_report": _text(raw.get("Pagamenti")),
            "data_pagamento_report": _date(raw.get("Data pagamento")),
            "stato_lettura_report": _text(raw.get("Stato")),
            "xml_presente": bool(canonical_id),
            "invoice_id": canonical_id,
            "source": "agenzia_entrate_report_fatture_ricevute",
            "source_report_filename": Path(filename).name,
            "source_hash": source_hash,
            "last_seen_at": now,
            **titolare,
        }
        result = await db[COLLECTION_REPORT].update_one(
            {"report_key": report_key},
            {"$set": document, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        if result.upserted_id is not None:
            imported += 1
        else:
            updated += 1

    missing_xml = max(0, imported + updated - xml_present)
    await db["fatture_report_ae_imports"].update_one(
        {"source_hash": source_hash},
        {"$set": {
            "source_hash": source_hash,
            "filename": Path(filename).name,
            "rows": imported + updated,
            "invalid": invalid,
            "xml_present": xml_present,
            "xml_missing": missing_xml,
            "last_imported_at": now,
        }, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    return {
        "success": invalid == 0,
        "partial": invalid > 0 and imported + updated > 0,
        "workflow": "REPORT_FATTURE_RICEVUTE_AE",
        "rows": imported + updated,
        "imported": imported,
        "updated": updated,
        "invalid": invalid,
        "xml_present": xml_present,
        "xml_missing": missing_xml,
        "details": details,
        "pagamenti_dichiarati": con_titolare,
        "message": (
            f"Report fatture indicizzato: {imported + updated} righe, "
            f"{xml_present} XML presenti e {missing_xml} XML da acquisire"
        ),
    }
