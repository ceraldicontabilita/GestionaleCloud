"""Consolidamento fatture passive (PROMPT_DEFINITIVO §5.4) — collezione canonica
UNICA `invoices`. La legacy `fatture_passive` (alimentata solo dal ponte ERP
esterno) viene migrata qui e il dedup runtime a due sorgenti viene rimosso.

Fornisce:
- `COLL` = "invoices";
- `invoice_key(numero, piva, data)`: chiave stabile (numero+P.IVA+data), identica
  a `generate_invoice_key` usata dalla pipeline di import;
- `mappa_fattura_passiva(doc)`: converte lo schema legacy/ponte
  (numero/fornitore_denominazione/importo_totale/…) nello schema canonico
  (invoice_number/supplier_name/total_amount/…);
- `salva_invoice_passiva(db, doc, source)`: upsert idempotente in `invoices` per
  `invoice_key` (non duplica se la fattura è già presente).
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

COLL = "invoices"


def invoice_key(numero: str, piva: str, data: str) -> str:
    """Chiave univoca fattura: numero_piva_data (identica a generate_invoice_key)."""
    key = f"{numero}_{piva}_{data}"
    return key.replace(" ", "").replace("/", "-").upper()


def mappa_fattura_passiva(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Converte un documento in schema legacy `fatture_passive`/ponte ERP nello
    schema canonico di `invoices`. Accetta anche campi già canonici (idempotente)."""
    numero = doc.get("invoice_number") or doc.get("numero") or doc.get("numero_documento") or ""
    piva = doc.get("supplier_vat") or doc.get("fornitore_piva") or doc.get("fornitore_partita_iva") or ""
    data = str(doc.get("invoice_date") or doc.get("data") or doc.get("data_documento") or "")[:10]
    totale = doc.get("total_amount")
    if totale is None:
        totale = doc.get("importo_totale") or doc.get("totale") or 0
    fornitore = (
        doc.get("supplier_name")
        or doc.get("fornitore_denominazione")
        or doc.get("fornitore")
        or ""
    )
    righe = doc.get("linee") or doc.get("righe") or []
    canonico = {
        "invoice_number": numero,
        "supplier_name": fornitore,
        "supplier_vat": piva,
        "invoice_date": data,
        "total_amount": round(float(totale or 0), 2),
        "imponibile": round(float(doc.get("imponibile") or 0), 2),
        "iva": round(float(doc.get("iva") or 0), 2),
        "anno": doc.get("anno") or (int(data[:4]) if data[:4].isdigit() else None),
        "status": doc.get("status") or doc.get("stato") or "imported",
        "linee": righe,
        "source": doc.get("source") or "fatture_passive",
        "invoice_key": invoice_key(numero, piva, data),
    }
    # preserva xml_filename/id se presenti (utile per anagrafica/dedup contenuto)
    for campo in ("xml_filename", "id"):
        if doc.get(campo):
            canonico[campo] = doc[campo]
    return canonico


async def salva_invoice_passiva(db, doc: Dict[str, Any], source: Optional[str] = None) -> Optional[str]:
    """Upsert idempotente di una fattura passiva nella collezione canonica
    `invoices`, deduplicando per `invoice_key`. Non sovrascrive campi derivati
    già presenti su una fattura esistente (stato pagamento, IVA, ecc.): aggiorna
    solo se il documento è nuovo."""
    canonico = mappa_fattura_passiva(doc)
    if source:
        canonico["source"] = source
    key = canonico["invoice_key"]
    if not canonico["invoice_number"] or not canonico["supplier_vat"]:
        return None  # dati insufficienti per una chiave affidabile

    esistente = await db[COLL].find_one({"invoice_key": key}, {"_id": 0, "id": 1})
    if esistente:
        # non toccare lo stato derivato di una fattura già gestita: aggiorna solo
        # i campi anagrafici/importo se mancanti (merge conservativo).
        return esistente.get("id")

    canonico.setdefault("id", str(uuid4()))
    canonico.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    await db[COLL].insert_one(canonico.copy())
    return canonico["id"]
