"""Libro giornale e libro mastro — genera e persiste le scritture in partita
doppia agli eventi della fattura, e ne ricava i mastrini per conto.

Vedi memoria/LOGICA_LIBRO_MASTRO.md per la logica contabile.

- Motore partita doppia: app/services/contabilita_generale.py (ScritturaContabile
  + generatori scrittura_*).
- Libro giornale: collezione `scritture_contabili` (cronologico), separata da
  `invoices` → sopravvive all'azzeramento.
- Chiave stabile: ogni scrittura da fattura porta `invoice_key` (numero+P.IVA+
  data) → al reimport si riconosce e NON si duplica (dedup per hash).
- Libro mastro: aggregazione delle righe per conto → saldo (mastrino).
"""
import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

COLL = "scritture_contabili"


def _hash_scrittura(invoice_key: str, tipo_operazione: str,
                    righe: List[Dict[str, Any]]) -> str:
    """Impronta stabile: stessa fattura + stesso tipo + stesse righe → stesso
    hash. Evita di scrivere due volte la stessa scrittura (anche al reimport)."""
    base = f"{invoice_key}|{tipo_operazione}|"
    base += ";".join(
        f"{r.get('conto')}:{r.get('dare', 0)}:{r.get('avere', 0)}"
        for r in righe
    )
    return hashlib.md5(base.encode("utf-8")).hexdigest()


async def registra_scrittura(
    db, scrittura: Dict[str, Any], invoice_key: Optional[str] = None,
    documento: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Salva una scrittura (dict da ScritturaContabile.to_dict) nel libro
    giornale, con dedup per hash. Ritorna l'id salvato (o quello esistente)."""
    righe = scrittura.get("righe") or []
    h = _hash_scrittura(invoice_key or "", scrittura.get("tipo_operazione", ""), righe)
    esistente = await db[COLL].find_one({"hash": h}, {"_id": 0, "id": 1})
    if esistente:
        return esistente.get("id")
    doc = dict(scrittura)
    doc["hash"] = h
    doc["invoice_key"] = invoice_key
    doc["documento"] = documento or {}
    doc["data_documento"] = scrittura.get("data")
    doc.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    await db[COLL].insert_one(doc.copy())
    return doc.get("id")


def _importi_fattura(invoice: Dict[str, Any]) -> Dict[str, float]:
    imponibile = float(invoice.get("imponibile") or 0)
    iva = float(invoice.get("iva") or 0)
    totale = float(invoice.get("total_amount") or invoice.get("importo_totale") or 0)
    if not imponibile and totale:
        imponibile = round(totale - iva, 2)
    return {"imponibile": imponibile, "iva": iva, "totale": totale or round(imponibile + iva, 2)}


async def genera_scrittura_acquisto(db, invoice: Dict[str, Any]) -> Optional[str]:
    """Alla registrazione di una fattura d'acquisto: DARE Acquisti + IVA credito /
    AVERE Debiti v/fornitori. Best-effort, non blocca l'import."""
    try:
        from app.services.contabilita_generale import scrittura_acquisto_merce
        imp = _importi_fattura(invoice)
        if imp["imponibile"] <= 0 and imp["totale"] <= 0:
            return None
        # aliquota media dedotta da imponibile/iva quando possibile
        aliquota = 22
        if imp["imponibile"] > 0 and imp["iva"] > 0:
            aliquota = round(imp["iva"] / imp["imponibile"] * 100)
        scr = scrittura_acquisto_merce(
            data=invoice.get("invoice_date") or invoice.get("data_fattura") or "",
            fornitore=invoice.get("supplier_name") or invoice.get("cedente_denominazione") or "",
            imponibile=imp["imponibile"] or round(imp["totale"] / (1 + aliquota / 100), 2),
            aliquota_iva=aliquota,
            descrizione=f"Fattura {invoice.get('invoice_number', '')}",
        )
        return await registra_scrittura(
            db, scr.to_dict(), invoice_key=invoice.get("invoice_key"),
            documento={"tipo": "fattura_acquisto", "id": invoice.get("id"),
                       "numero": invoice.get("invoice_number")},
        )
    except Exception:
        logger.exception("genera_scrittura_acquisto fallita")
        return None


async def genera_scrittura_pagamento(db, invoice: Dict[str, Any],
                                     mezzo: str = "banca") -> Optional[str]:
    """Al pagamento di una fattura: DARE Debiti v/fornitori / AVERE Banca o Cassa."""
    try:
        from app.services.contabilita_generale import scrittura_pagamento_fornitore
        imp = _importi_fattura(invoice)
        if imp["totale"] <= 0:
            return None
        scr = scrittura_pagamento_fornitore(
            data=(invoice.get("data_pagamento") or datetime.now(timezone.utc).date().isoformat()),
            fornitore=invoice.get("supplier_name") or invoice.get("cedente_denominazione") or "",
            importo=imp["totale"],
            mezzo_pagamento="cassa" if mezzo == "cassa" else "banca",
        )
        return await registra_scrittura(
            db, scr.to_dict(), invoice_key=invoice.get("invoice_key"),
            documento={"tipo": "pagamento_fattura", "id": invoice.get("id"),
                       "numero": invoice.get("invoice_number"), "mezzo": mezzo},
        )
    except Exception:
        logger.exception("genera_scrittura_pagamento fallita")
        return None


async def libro_mastro(db, data_da: Optional[str] = None,
                       data_a: Optional[str] = None) -> List[Dict[str, Any]]:
    """Libro mastro: aggrega le righe delle scritture per conto → saldo (mastrino).
    Ritorna una lista di mastrini {conto, conto_nome, dare, avere, saldo, righe}."""
    match: Dict[str, Any] = {}
    if data_da or data_a:
        match["data_documento"] = {}
        if data_da:
            match["data_documento"]["$gte"] = data_da
        if data_a:
            match["data_documento"]["$lte"] = data_a
    pipeline: List[Dict[str, Any]] = []
    if match:
        pipeline.append({"$match": match})
    pipeline += [
        {"$unwind": "$righe"},
        {"$group": {
            "_id": "$righe.conto",
            "conto_nome": {"$last": "$righe.conto_nome"},
            "dare": {"$sum": {"$toDouble": {"$ifNull": ["$righe.dare", 0]}}},
            "avere": {"$sum": {"$toDouble": {"$ifNull": ["$righe.avere", 0]}}},
            "righe": {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
    ]
    out = []
    async for m in db[COLL].aggregate(pipeline):
        dare = round(m.get("dare", 0), 2)
        avere = round(m.get("avere", 0), 2)
        out.append({
            "conto": m["_id"],
            "conto_nome": m.get("conto_nome"),
            "dare": dare,
            "avere": avere,
            "saldo": round(dare - avere, 2),
            "movimenti": m.get("righe", 0),
        })
    return out
