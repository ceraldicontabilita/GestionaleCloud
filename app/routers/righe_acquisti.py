"""Vista canonica, in sola lettura, delle righe delle fatture passive.

La pagina ``Righe acquisti`` non crea un secondo archivio: ogni riga viene
costruita al momento dai documenti di ``invoices`` e conserva i riferimenti
alla fattura e all'originale.  Le classificazioni mancanti restano
esplicitamente ``DA_VERIFICARE``; non si estende mai una scelta del fornitore a
tutte le sue righe.
"""

from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from app.database import Database
from app.services import agenti_proposte
from app.utils.dependencies import get_current_admin_user


router = APIRouter()


MODALITA_PAGAMENTO = {
    "MP01": "Contanti",
    "MP02": "Assegno",
    "MP03": "Assegno circolare",
    "MP04": "Contanti presso Tesoreria",
    "MP05": "Bonifico",
    "MP06": "Vaglia cambiario",
    "MP07": "Bollettino bancario",
    "MP08": "Carta di pagamento",
    "MP09": "RID",
    "MP10": "RID utenze",
    "MP11": "RID veloce",
    "MP12": "RIBA",
    "MP13": "MAV",
    "MP14": "Quietanza erario",
    "MP15": "Giroconto su conti di contabilita speciale",
    "MP16": "Domiciliazione bancaria",
    "MP17": "Domiciliazione postale",
    "MP18": "Bollettino di conto corrente postale",
    "MP19": "SEPA Direct Debit",
    "MP20": "SEPA Direct Debit CORE",
    "MP21": "SEPA Direct Debit B2B",
    "MP22": "Trattenuta su somme gia riscosse",
    "MP23": "PagoPA",
}

TIPI_NOTA_CREDITO = {"TD04", "TD08"}


def _testo(value: Any) -> str:
    return str(value or "").strip()


def _normalizza_testo(value: Any) -> str:
    text = unicodedata.normalize("NFKD", _testo(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip().upper()


def _normalizza_numero(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]", "", _normalizza_testo(value))


def _decimale(value: Any) -> Optional[Decimal]:
    try:
        return Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, AttributeError, TypeError, ValueError):
        return None


def _numero(value: Any) -> Optional[float]:
    parsed = _decimale(value)
    return float(parsed) if parsed is not None else None


def _denaro(value: Any) -> Optional[float]:
    parsed = _decimale(value)
    if parsed is None:
        return None
    return float(parsed.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _valori_riferimento(items: Any, *keys: str) -> List[str]:
    values: List[str] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        for key in keys:
            value = _testo(item.get(key))
            if value and value not in values:
                values.append(value)
    return values


def _codici_articolo(linea: Dict[str, Any]) -> List[Dict[str, str]]:
    raw = linea.get("codici_articolo") or linea.get("codice_articolo") or []
    if isinstance(raw, (str, int, float)):
        raw = [{"valore": str(raw)}]
    elif isinstance(raw, dict):
        raw = [raw]
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        valore = _testo(item.get("valore") or item.get("codice_valore") or item.get("codice"))
        if valore:
            result.append({"tipo": _testo(item.get("tipo") or item.get("codice_tipo")), "valore": valore})
    return result


def _piano_pagamento(invoice: Dict[str, Any]) -> List[Dict[str, Any]]:
    result = []
    for rata in invoice.get("pagamento_rate") or []:
        if not isinstance(rata, dict):
            continue
        codice = _testo(rata.get("modalita")).upper()
        result.append({
            "codice": codice,
            "descrizione": MODALITA_PAGAMENTO.get(codice, "Modalita non descritta nell'archivio"),
            "importo": _denaro(rata.get("importo")),
            "scadenza": _testo(rata.get("data_scadenza")) or None,
            "condizioni": _testo(rata.get("condizioni_pagamento")) or None,
        })
    if result:
        return result
    for codice in invoice.get("modalita_pagamento_xml") or []:
        codice = _testo(codice).upper()
        if codice:
            result.append({
                "codice": codice,
                "descrizione": MODALITA_PAGAMENTO.get(codice, "Modalita non descritta nell'archivio"),
                "importo": None,
                "scadenza": None,
                "condizioni": None,
            })
    return result


def _chiave_fattura(invoice: Dict[str, Any]) -> Tuple[str, str]:
    piva = invoice.get("supplier_vat") or invoice.get("fornitore_partita_iva") or invoice.get("cedente_piva")
    numero = invoice.get("invoice_number") or invoice.get("numero_fattura") or invoice.get("numero_documento")
    return _normalizza_testo(piva), _normalizza_numero(numero)


def _indice_originali(invoices: Iterable[Dict[str, Any]]) -> Dict[Tuple[str, str], List[Dict[str, Any]]]:
    result: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for invoice in invoices:
        if _testo(invoice.get("tipo_documento")).upper() in TIPI_NOTA_CREDITO:
            continue
        key = _chiave_fattura(invoice)
        if all(key):
            result.setdefault(key, []).append(invoice)
    return result


def _stato_nota_credito(
    invoice: Dict[str, Any], originali: Dict[Tuple[str, str], List[Dict[str, Any]]]
) -> Optional[Dict[str, Any]]:
    if _testo(invoice.get("tipo_documento")).upper() not in TIPI_NOTA_CREDITO:
        return None
    riferimenti = invoice.get("dati_fatture_collegate") or []
    if invoice.get("fattura_collegata_id"):
        return {
            "stato": "collegata",
            "fattura_id": _testo(invoice.get("fattura_collegata_id")),
            "messaggio": "Fattura originaria collegata; verifica lo storno sulla classificazione confermata.",
        }
    supplier = _chiave_fattura(invoice)[0]
    for riferimento in riferimenti:
        if not isinstance(riferimento, dict):
            continue
        numero = _testo(riferimento.get("id_documento"))
        data = _testo(riferimento.get("data"))
        candidati = originali.get((supplier, _normalizza_numero(numero)), [])
        if candidati:
            candidata = sorted(
                candidati,
                key=lambda doc: _testo(doc.get("invoice_date") or doc.get("data_fattura")),
                reverse=True,
            )[0]
            return {
                "stato": "trovata_da_collegare",
                "fattura_id": _testo(candidata.get("id")),
                "numero": numero,
                "data": data or None,
                "messaggio": "Fattura originaria trovata: verifica identita e righe prima del collegamento.",
            }
        return {
            "stato": "da_recuperare",
            "fattura_id": None,
            "numero": numero or None,
            "data": data or None,
            "messaggio": (
                f"Carica o recupera la fattura {numero or 'indicata nel documento'}"
                f"{f' del {data}' if data else ''}; la nota di credito resta DA_VERIFICARE."
            ),
        }
    return {
        "stato": "riferimento_assente",
        "fattura_id": None,
        "messaggio": "Nota di credito senza DatiFattureCollegate: fattura originaria DA_VERIFICARE.",
    }


def _classificazione_linea(linea: Dict[str, Any]) -> Dict[str, Any]:
    proposta = linea.get("proposta_ai") or linea.get("classificazione_ai") or {}
    if not isinstance(proposta, dict):
        proposta = {}
    confermata = linea.get("classificazione_confermata") or {}
    if not isinstance(confermata, dict):
        confermata = {}
    source = confermata or proposta
    stato = "CONFERMATA" if confermata else ("PROPOSTA" if proposta else "DA_VERIFICARE")
    return {
        "stato": stato,
        "natura": source.get("natura"),
        "categoria": source.get("categoria"),
        "conto": source.get("conto"),
        "centro_costo": source.get("centro_costo"),
        "destinazione_operativa": source.get("destinazione_operativa"),
        "confidenza": source.get("confidenza"),
        "spiegazione": source.get("spiegazione"),
        "regola": source.get("regola"),
        "versione": source.get("versione"),
    }


def costruisci_righe(invoices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Appiattisce fatture e righe senza persistere copie o classificazioni."""
    originali = _indice_originali(invoices)
    result: List[Dict[str, Any]] = []
    for invoice in invoices:
        invoice_id = _testo(invoice.get("id"))
        data = _testo(invoice.get("invoice_date") or invoice.get("data_fattura") or invoice.get("data_documento"))
        numero = _testo(invoice.get("invoice_number") or invoice.get("numero_fattura") or invoice.get("numero_documento"))
        supplier_name = _testo(invoice.get("supplier_name") or invoice.get("fornitore_ragione_sociale") or invoice.get("cedente_denominazione"))
        supplier_vat = _testo(invoice.get("supplier_vat") or invoice.get("fornitore_partita_iva") or invoice.get("cedente_piva"))
        tipo_documento = _testo(invoice.get("tipo_documento") or invoice.get("document_type") or "TD01").upper()
        hash_originale = _testo(
            invoice.get("content_hash") or invoice.get("file_hash") or invoice.get("sha256") or invoice.get("xml_hash")
        )
        documento_id = _testo(
            invoice.get("source_document_id") or invoice.get("document_id") or invoice.get("documents_inbox_id")
        )
        nota_credito = _stato_nota_credito(invoice, originali)
        pagamenti = _piano_pagamento(invoice)
        ordini = _valori_riferimento(invoice.get("dati_ordine_acquisto"), "id_documento")
        contratti = _valori_riferimento(invoice.get("dati_contratto"), "id_documento")
        ddt = _valori_riferimento(invoice.get("dati_ddt"), "numero")
        linee = invoice.get("linee") or []
        if not isinstance(linee, list):
            linee = []
        for index, linea in enumerate(linee):
            if not isinstance(linea, dict):
                continue
            descrizione = _testo(linea.get("descrizione_originale") or linea.get("descrizione"))
            imponibile = _denaro(linea.get("prezzo_totale") or linea.get("imponibile"))
            aliquota = _numero(linea.get("aliquota_iva") or linea.get("iva"))
            imposta = None
            totale = imponibile
            if imponibile is not None and aliquota is not None and not _testo(linea.get("natura")):
                imposta = _denaro(Decimal(str(imponibile)) * Decimal(str(aliquota)) / Decimal("100"))
                totale = _denaro(Decimal(str(imponibile)) + Decimal(str(imposta or 0)))
            classificazione = _classificazione_linea(linea)
            anomalie = []
            if not descrizione:
                anomalie.append("descrizione_assente")
            if not hash_originale:
                anomalie.append("hash_originale_assente")
            if invoice.get("duplicate_review_required") or invoice.get("identity_collision_with_ids"):
                anomalie.append("identita_documentale_da_verificare")
            if nota_credito and nota_credito.get("stato") != "collegata":
                anomalie.append(f"nota_credito_{nota_credito.get('stato')}")
            result.append({
                "id": f"{invoice_id}:{_testo(linea.get('numero_linea')) or index + 1}",
                "fattura_id": invoice_id,
                "documento_id": documento_id or None,
                "hash_originale": hash_originale or None,
                "url_originale": f"/api/fatture-ricevute/fattura/{invoice_id}/view-assoinvoice" if invoice_id else None,
                "numero_linea": _testo(linea.get("numero_linea")) or str(index + 1),
                "descrizione_originale": descrizione,
                "descrizione_normalizzata": _normalizza_testo(linea.get("descrizione_normalizzata") or descrizione),
                "codici_articolo": _codici_articolo(linea),
                "fornitore": supplier_name,
                "partita_iva": supplier_vat,
                "numero_fattura": numero,
                "data_fattura": data,
                "anno": int(data[:4]) if len(data) >= 4 and data[:4].isdigit() else None,
                "tipo_documento": tipo_documento,
                "ordini": ordini,
                "contratti": contratti,
                "ddt": ddt,
                "quantita": _numero(linea.get("quantita")),
                "unita_misura": _testo(linea.get("unita_misura")) or None,
                "prezzo_unitario": _denaro(linea.get("prezzo_unitario")),
                "sconti_maggiorazioni": linea.get("sconti_maggiorazioni") or [],
                "imponibile": imponibile,
                "aliquota_iva": aliquota,
                "natura_iva": _testo(linea.get("natura")) or None,
                "imposta": imposta,
                "totale": totale,
                "valuta": _testo(invoice.get("divisa") or "EUR"),
                "pagamenti_dichiarati": pagamenti,
                "metodo_previsto": _testo(invoice.get("metodo_pagamento")) or None,
                "metodo_effettivo": _testo(invoice.get("metodo_pagamento_effettivo")) or None,
                "classificazione": classificazione,
                "nota_credito": nota_credito,
                "anomalie": anomalie,
            })
    return sorted(
        result,
        key=lambda row: (row.get("data_fattura") or "", row.get("numero_fattura") or "", row.get("numero_linea") or ""),
        reverse=True,
    )


def _filtra(
    rows: List[Dict[str, Any]], *, anno: Optional[int], fornitore: str, testo: str,
    natura: str, conto: str, metodo: str, stato_ai: str, anomalie: bool,
) -> List[Dict[str, Any]]:
    supplier_q = _normalizza_testo(fornitore)
    text_q = _normalizza_testo(testo)
    natura_q = _normalizza_testo(natura)
    conto_q = _normalizza_testo(conto)
    metodo_q = _normalizza_testo(metodo)
    stato_q = _normalizza_testo(stato_ai)
    result = []
    for row in rows:
        if anno is not None and row.get("anno") != anno:
            continue
        if supplier_q and supplier_q not in _normalizza_testo(f"{row.get('fornitore')} {row.get('partita_iva')}"):
            continue
        haystack = _normalizza_testo(
            " ".join([
                _testo(row.get("descrizione_originale")),
                _testo(row.get("numero_fattura")),
                " ".join(row.get("ordini") or []),
                " ".join(c.get("valore", "") for c in row.get("codici_articolo") or []),
            ])
        )
        if text_q and text_q not in haystack:
            continue
        classif = row.get("classificazione") or {}
        if natura_q and natura_q not in _normalizza_testo(
            f"{row.get('natura_iva')} {classif.get('natura')} {classif.get('categoria')}"
        ):
            continue
        if conto_q and conto_q not in _normalizza_testo(
            f"{classif.get('conto')} {classif.get('centro_costo')} {classif.get('destinazione_operativa')}"
        ):
            continue
        if metodo_q and not any(
            metodo_q in _normalizza_testo(f"{p.get('codice')} {p.get('descrizione')}")
            for p in row.get("pagamenti_dichiarati") or []
        ):
            continue
        if stato_q and stato_q != _normalizza_testo(classif.get("stato")):
            continue
        if anomalie and not row.get("anomalie"):
            continue
        result.append(row)
    return result


@router.get("")
async def lista_righe_acquisti(
    anno: Optional[int] = Query(None, ge=1900, le=2200),
    fornitore: str = Query("", max_length=120),
    testo: str = Query("", max_length=200),
    natura: str = Query("", max_length=100),
    conto: str = Query("", max_length=100),
    metodo: str = Query("", max_length=80),
    stato_ai: str = Query("", max_length=40),
    anomalie: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=200),
) -> Dict[str, Any]:
    db = Database.get_db()
    invoices = await db["invoices"].find(
        {"status": {"$nin": ["deleted", "archived"]}},
        {
            "_id": 0,
            "xml_raw": 0,
            "xml_content": 0,
            "fattura_allegata": 0,
            "document_original_ref": 0,
            "foto": 0,
        },
    ).sort("invoice_date", -1).to_list(None)
    rows_costruite = costruisci_righe(invoices)
    # Le classificazioni sono sparse: leggerle in un'unica query evita un
    # filtro ``IN`` con migliaia di id fattura/riga su PostgREST.
    classificazioni = await agenti_proposte.classificazioni_righe(db)
    rows = _filtra(
        agenti_proposte.sovrapponi_classificazioni(rows_costruite, classificazioni),
        anno=anno, fornitore=fornitore, testo=testo,
        natura=natura, conto=conto, metodo=metodo, stato_ai=stato_ai, anomalie=anomalie,
    )
    total = len(rows)
    page = rows[skip: skip + limit]
    return {
        "righe": page,
        "totale": total,
        "skip": skip,
        "limit": limit,
        "has_more": skip + len(page) < total,
        "da_verificare": sum(1 for row in rows if row["classificazione"]["stato"] == "DA_VERIFICARE"),
        "anomalie": sum(1 for row in rows if row.get("anomalie")),
    }


@router.get("/classificazione/stato")
async def stato_classificazione_righe(
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    return await agenti_proposte.stato_righe_acquisti(Database.get_db())


@router.post("/classificazione/giro")
async def avvia_classificazione_righe(
    limit: int = Query(20, ge=1, le=50),
    _admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """Elabora un lotto; salva soltanto proposte e non scritture contabili."""
    return await agenti_proposte.giro_righe_acquisti(Database.get_db(), limite=limit)


@router.post("/classificazione/{riga_id:path}/decisione")
async def decidi_classificazione_riga(
    riga_id: str,
    body: Dict[str, Any] = Body(...),
    admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    utente = str(admin.get("email") or admin.get("user_id") or "admin")
    try:
        record = await agenti_proposte.decidi_riga_acquisto(
            Database.get_db(), riga_id, utente,
            azione=str(body.get("azione") or ""),
            motivazione=str(body.get("motivazione") or ""),
            correzione=body.get("classificazione") if isinstance(body.get("classificazione"), dict) else None,
            regola_fiscale=str(body.get("regola_fiscale") or ""),
        )
    except agenti_proposte.PropostaNonTrovata as exc:
        raise HTTPException(status_code=404, detail="Proposta di riga non trovata") from exc
    except agenti_proposte.PropostaNonApplicabile as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"classificazione": record}
