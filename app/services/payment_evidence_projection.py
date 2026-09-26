"""Proiezione read-only delle prove di pagamento collegate a una fattura.

Le prove collegate (assegni, bonifici, movimento di banca) si leggono **in
blocco** per tutte le fatture della pagina: tre letture in tutto, non tre per
fattura. La versione per fattura faceva fino a tre letture per ognuna delle
~1.400 fatture dell'anno, e l'archivio Fatture impiegava da 3 a 46 secondi.
La composizione della singola prova non cambia.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List

from app.services.payment_allocation_validator import allocation_status, to_cents

# Solo i campi che la proiezione legge: niente payload.
_CAMPI_ASSEGNO = {
    "_id": 0, "id": 1, "data_incasso": 1, "data": 1, "numero": 1,
    "movimento_estratto_conto_id": 1, "movimento_id": 1, "document_hash": 1, "sha256": 1,
}
_CAMPI_BONIFICO = {
    "_id": 0, "id": 1, "movimento_estratto_conto_id": 1, "importo": 1, "data": 1,
    "causale": 1, "transaction_code": 1, "document_hash": 1, "sha256": 1, "match_rule": 1,
}
_CAMPI_MOVIMENTO = {
    "_id": 0, "id": 1, "importo": 1, "data": 1, "descrizione": 1, "document_hash": 1, "sha256": 1,
}


def _id_assegni(invoice: Dict[str, Any]) -> List[str]:
    return [
        str(x.get("assegno_id")) for x in (invoice.get("assegni_collegati") or [])
        if isinstance(x, dict) and x.get("assegno_id")
    ]


def _id_bonifici(invoice: Dict[str, Any]) -> List[str]:
    return [str(x) for x in (invoice.get("payment_document_ids") or invoice.get("bonifico_ids") or []) if x]


async def _per_id(db, collezione: str, ids: Iterable[str], campi: Dict[str, int]) -> Dict[str, Dict[str, Any]]:
    unici = sorted({i for i in ids if i})
    if not unici:
        return {}
    righe = await db[collezione].find({"id": {"$in": unici}}, campi).to_list(len(unici) + 10)
    return {str(r.get("id")): r for r in righe if r.get("id")}


def _componi(invoice: Dict[str, Any], assegni: Dict[str, Dict[str, Any]],
             bonifici: Dict[str, Dict[str, Any]], movimenti: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    invoice_id = str(invoice.get("id") or "")
    status = allocation_status(invoice)
    result: List[Dict[str, Any]] = []

    for raw in invoice.get("payment_evidence") or []:
        if not isinstance(raw, dict):
            continue
        result.append({
            "type": raw.get("type") or raw.get("tipo") or "payment_document",
            "status": raw.get("status") or "documented",
            "amount_cents": raw.get("amount_cents", to_cents(raw.get("amount") or raw.get("importo"))),
            "date": raw.get("date") or raw.get("data"),
            "reference": raw.get("reference") or raw.get("riferimento"),
            "bank_movement_id": raw.get("bank_movement_id") or raw.get("movimento_bancario_id"),
            "document_id": raw.get("document_id") or raw.get("id"),
            "source_hash": raw.get("source_hash") or raw.get("sha256"),
            "allocation_id": raw.get("allocation_id"),
            "rule": raw.get("rule") or "stored_evidence",
            "confidence": raw.get("confidence", 1.0),
            "conflict_reason": raw.get("conflict_reason") if status == "conflicting" else None,
        })

    for link in invoice.get("assegni_collegati") or []:
        if not isinstance(link, dict):
            continue
        aid = str(link.get("assegno_id") or "")
        check = assegni.get(aid, {})
        result.append({
            "type": "assegno",
            "status": "confirmed" if link.get("banca_confermata") else "pending_bank",
            "amount_cents": to_cents(link.get("quota")),
            "date": link.get("data_collegamento") or check.get("data_incasso") or check.get("data"),
            "reference": link.get("numero") or check.get("numero"),
            "bank_movement_id": check.get("movimento_estratto_conto_id") or check.get("movimento_id"),
            "document_id": aid or None,
            "source_hash": check.get("document_hash") or check.get("sha256"),
            "allocation_id": f"assegno:{aid}:{invoice_id}" if aid else None,
            "rule": link.get("match_livello") or "assegno_allocation",
            "confidence": 1.0 if link.get("banca_confermata") else 0.5,
            "conflict_reason": "quota_supera_totale_fattura" if status == "conflicting" else None,
        })

    # Stesso ordine di prima: quello in cui il database restituiva i bonifici,
    # cioe' l'ordine degli id sulla fattura per quelli che esistono.
    for tid in dict.fromkeys(_id_bonifici(invoice)):
        transfer = bonifici.get(tid)
        if transfer is None:
            continue
        result.append({
            "type": "bonifico_pdf",
            "status": "confirmed" if transfer.get("movimento_estratto_conto_id") else "documented",
            "amount_cents": abs(to_cents(transfer.get("importo") or 0)),
            "date": str(transfer.get("data") or "")[:10],
            "reference": transfer.get("causale") or transfer.get("transaction_code"),
            "bank_movement_id": transfer.get("movimento_estratto_conto_id"),
            "document_id": tid,
            "source_hash": transfer.get("document_hash") or transfer.get("sha256"),
            "allocation_id": f"bonifico:{tid}:{invoice_id}",
            "rule": transfer.get("match_rule") or "payment_document_link",
            "confidence": 1.0 if transfer.get("movimento_estratto_conto_id") else 0.7,
            "conflict_reason": None,
        })

    if invoice.get("movimento_bancario_id"):
        movement_id = str(invoice["movimento_bancario_id"])
        movement = movimenti.get(movement_id)
        result.append({
            "type": "bank_movement",
            "status": "confirmed" if movement else "missing",
            "amount_cents": abs(to_cents((movement or {}).get("importo") or 0)),
            "date": (movement or {}).get("data"),
            "reference": (movement or {}).get("descrizione") or movement_id,
            "bank_movement_id": movement_id,
            "document_id": movement_id,
            "source_hash": (movement or {}).get("document_hash") or (movement or {}).get("sha256"),
            "allocation_id": f"bank:{movement_id}:{invoice_id}",
            "rule": "invoice_bank_movement_link",
            "confidence": 1.0 if movement else 0.0,
            "conflict_reason": "movimento_non_trovato" if not movement else None,
        })
    return result


async def project_payment_evidence_many(db, invoices: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    """Le prove di tutte le fatture, nello stesso ordine: tre letture in tutto."""
    assegni = await _per_id(db, "assegni", (i for f in invoices for i in _id_assegni(f)), _CAMPI_ASSEGNO)
    bonifici = await _per_id(db, "bonifici_transfers", (i for f in invoices for i in _id_bonifici(f)), _CAMPI_BONIFICO)
    movimenti = await _per_id(
        db, "estratto_conto_movimenti",
        (str(f["movimento_bancario_id"]) for f in invoices if f.get("movimento_bancario_id")),
        _CAMPI_MOVIMENTO,
    )
    return [_componi(f, assegni, bonifici, movimenti) for f in invoices]


async def project_invoice_payment_evidence(db, invoice: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Restituisce prove navigabili senza creare o modificare record."""
    return (await project_payment_evidence_many(db, [invoice]))[0]
