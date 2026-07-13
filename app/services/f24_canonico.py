"""Consolidamento F24 (PROMPT_DEFINITIVO §5.1) — collezione canonica UNICA per i
modelli F24: `f24_unificato`. Le quietanze restano in `quietanze_f24`.

Questo modulo fornisce:
- la costante canonica `COLL`;
- `chiave_f24(doc)`: chiave naturale di deduplica (contribuente + periodo + saldo
  + hash PDF + protocollo), robusta ai vari schemi storici;
- `salva_f24(db, doc, source)`: unico punto di scrittura canonico, idempotente
  (upsert per chiave naturale, non duplica).

Le collezioni legacy dei MODELLI F24 (`f24_models`, `f24_commercialista` letterale,
`f24_uploaded`, `f24`) vanno migrate qui con `app/scripts/migra_f24_unificato.py`
(non distruttivo). Il sottosistema parser paghe (`f24_pagamenti`/`tributi_pagati`/
`distinte_f24`) e la classificazione (`f24_tributi`) restano separati: sono vivi e
verranno consolidati in una fase dedicata.
"""
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

COLL = "f24_unificato"
COLL_QUIETANZE = "quietanze_f24"


def _saldo(doc: Dict[str, Any]) -> float:
    tot = doc.get("totali") or {}
    val = (
        doc.get("saldo")
        or doc.get("saldo_finale")
        or doc.get("saldo_netto")
        or tot.get("saldo_netto")
        or tot.get("saldo_finale")
        or 0
    )
    try:
        return round(float(val or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _periodo(doc: Dict[str, Any]) -> str:
    dg = doc.get("dati_generali") or {}
    return str(
        doc.get("periodo")
        or doc.get("periodo_competenza")
        or doc.get("scadenza")
        or doc.get("data_scadenza")
        or dg.get("data_versamento")
        or dg.get("data_scadenza")
        or ""
    ).strip()


def _contribuente(doc: Dict[str, Any]) -> str:
    dg = doc.get("dati_generali") or {}
    return str(
        doc.get("codice_fiscale")
        or dg.get("codice_fiscale")
        or doc.get("contribuente")
        or dg.get("contribuente")
        or ""
    ).strip().upper()


def chiave_f24(doc: Dict[str, Any]) -> str:
    """Chiave naturale stabile di un modello F24 per la deduplica: stesso
    contribuente + periodo + saldo + hash PDF + protocollo → stessa chiave.
    Non dipende dall'`id` (che varia tra le collezioni legacy)."""
    pdf_hash = str(doc.get("pdf_hash") or doc.get("pdf_data_hash") or doc.get("file_hash") or "")
    protocollo = str(doc.get("protocollo") or doc.get("protocollo_telematico") or "")
    base = f"{_contribuente(doc)}|{_periodo(doc)}|{_saldo(doc)}|{pdf_hash}|{protocollo}"
    return "f24_" + hashlib.md5(base.encode("utf-8")).hexdigest()[:20]


async def salva_f24(db, doc: Dict[str, Any], source: Optional[str] = None) -> str:
    """Scrive un modello F24 nella collezione canonica in modo IDEMPOTENTE:
    se un F24 con la stessa chiave naturale esiste già lo aggiorna (senza
    duplicarlo), altrimenti lo inserisce. Ritorna l'`id` canonico."""
    doc = dict(doc)
    doc.pop("_id", None)
    chiave = chiave_f24(doc)
    doc["f24_dedup_key"] = chiave
    if source:
        doc.setdefault("import_source", source)

    esistente = await db[COLL].find_one({"f24_dedup_key": chiave}, {"_id": 0, "id": 1})
    if esistente:
        patch = {k: v for k, v in doc.items() if k not in ("id", "_id")}
        await db[COLL].update_one({"f24_dedup_key": chiave}, {"$set": patch})
        return esistente.get("id")

    doc.setdefault("id", str(uuid4()))
    doc.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    await db[COLL].insert_one(doc.copy())
    return doc["id"]
