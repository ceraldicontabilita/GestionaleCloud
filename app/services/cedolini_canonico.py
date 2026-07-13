"""Consolidamento cedolini (PROMPT_DEFINITIVO §5.3) — collezione canonica UNICA per
il CEDOLINO ELABORATO: `cedolini`.

Distinzione (dal piano):
- file ricevuto  → `cedolini_email_attachments` (documento origine, NON si tocca);
- cedolino elaborato → `cedolini` (CANONICA);
- riepilogo aggregato → `riepilogo_cedolini` (resta separato);
- `payslips` = alias inglese LEGACY del cedolino elaborato → migrare in `cedolini`.

`buste_paga` (Libro Unico Zucchetti + distinte BPM + TFR/acconti) è un sottosistema
VIVO con schema/chiave propri (stato_pagamento, acconti, netto_mese, periodo): NON
viene toccato qui, sarà consolidato in una fase dedicata insieme al flusso paghe.

Fornisce:
- `COLL` = "cedolini";
- `chiave_cedolino(doc)`: chiave naturale (contribuente + anno + mese);
- `salva_cedolino(db, doc, source)`: upsert idempotente per chiave naturale.
"""
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

COLL = "cedolini"


def _contribuente(doc: Dict[str, Any]) -> str:
    return str(
        doc.get("codice_fiscale")
        or doc.get("cf")
        or doc.get("employee_id")
        or doc.get("dipendente_id")
        or doc.get("matricola")
        or ""
    ).strip().upper()


def _anno_mese(doc: Dict[str, Any]):
    """Ricava (anno, mese) da schemi diversi: campi espliciti oppure `periodo`
    tipo '2026-03' / '03/2026' / 'marzo 2026'."""
    anno = doc.get("anno")
    mese = doc.get("mese")
    if anno and mese:
        try:
            return int(anno), int(mese)
        except (TypeError, ValueError):
            pass
    periodo = str(doc.get("periodo") or doc.get("periodo_competenza") or doc.get("mese_anno") or "")
    m = re.search(r"(\d{4})[-/ ]?(\d{1,2})", periodo)          # 2026-03
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d{1,2})[-/ ](\d{4})", periodo)           # 03/2026
    if m:
        return int(m.group(2)), int(m.group(1))
    return anno, mese


def chiave_cedolino(doc: Dict[str, Any]) -> str:
    """Chiave naturale stabile di un cedolino: contribuente + anno + mese."""
    anno, mese = _anno_mese(doc)
    try:
        mese_str = f"{int(mese):02d}" if mese is not None else ""
    except (TypeError, ValueError):
        mese_str = str(mese or "")
    return f"ced_{_contribuente(doc)}_{anno or ''}_{mese_str}"


async def salva_cedolino(db, doc: Dict[str, Any], source: Optional[str] = None) -> Optional[str]:
    """Upsert idempotente di un cedolino nella collezione canonica `cedolini`,
    deduplicando per chiave naturale. Non duplica lo stesso cedolino (stesso
    contribuente/anno/mese); se esiste, ritorna l'id senza sovrascrivere."""
    doc = dict(doc)
    doc.pop("_id", None)
    contrib = _contribuente(doc)
    anno, mese = _anno_mese(doc)
    if not contrib or not anno or not mese:
        return None  # dati insufficienti per una chiave affidabile

    chiave = chiave_cedolino(doc)
    doc["cedolino_dedup_key"] = chiave
    if source:
        doc.setdefault("import_source", source)

    esistente = await db[COLL].find_one({"cedolino_dedup_key": chiave}, {"_id": 0, "id": 1})
    if esistente:
        return esistente.get("id")

    doc.setdefault("id", str(uuid4()))
    doc.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    await db[COLL].insert_one(doc.copy())
    return doc["id"]
