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
import base64
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

COLL = "f24_unificato"
COLL_QUIETANZE = "quietanze_f24"


def richiedi_quadratura_f24(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """Rifiuta un PDF F24 privo di quadratura positiva esplicita."""
    validation = parsed.get("validazione") or {}
    section_statuses = {
        str(value.get("stato") or "")
        for value in (validation.get("quadrature_sezioni") or {}).values()
        if isinstance(value, dict)
    }
    if validation.get("saldo_quadrato") is not True or (
        validation.get("sezioni_quadrate") is False
        or "ERRORE" in section_statuses
    ):
        difference = validation.get("differenza_saldo")
        raise ValueError(
            "F24 non quadrato o non validato: salvataggio bloccato"
            + (f" (differenza {difference})" if difference is not None else "")
        )
    return validation


def normalizza_righe_tributo(doc: Dict[str, Any]) -> list[Dict[str, Any]]:
    """Unica vista applicativa di debiti, crediti e periodi delle righe F24."""
    from app.services.f24_fiscal_evidence import normalize_f24_evidence_rows

    return normalize_f24_evidence_rows(doc)


async def importa_quietanza(
    db, content: bytes, filename: str, *, source: str = "upload_manuale"
) -> Dict[str, Any]:
    """Ingresso canonico delle quietanze, condiviso da ogni canale."""
    from app.services.quietanze_import import importa_quietanza_bytes

    return await importa_quietanza_bytes(db, content, filename, fonte=source)


async def importa_modello_bytes(
    db, content: bytes, filename: str, *, source: str = "upload_manuale"
) -> Dict[str, Any]:
    """Importa un modello F24 direttamente in ``f24_unificato``.

    Conserva il PDF, tutte le righe a debito/credito e usa la stessa chiave
    idempotente degli altri canali. Non alimenta le collezioni legacy.
    """
    from app.services.parser_f24 import parse_f24_commercialista

    parsed = parse_f24_commercialista(pdf_content=content)
    if not parsed or parsed.get("error"):
        return {
            "success": False,
            "filename": filename,
            "error": (parsed or {}).get("error", "Parsing F24 fallito"),
        }
    try:
        validation = richiedi_quadratura_f24(parsed)
    except ValueError as exc:
        return {
            "success": False,
            "filename": filename,
            "error": str(exc),
            "validazione": parsed.get("validazione") or {},
        }

    documento = dict(parsed)
    documento.update({
        "file_name": filename,
        "pdf_data": base64.b64encode(content).decode("utf-8"),
        "pdf_hash": hashlib.sha256(content).hexdigest(),
        "status": "da_pagare",
        "riconciliato": False,
        "pagato": False,
        "import_date": datetime.now(timezone.utc).isoformat(),
    })
    documento["f24_dedup_key"] = chiave_f24(documento)
    existing = await db[COLL].find_one(
        {"f24_dedup_key": documento["f24_dedup_key"]}, {"_id": 0, "id": 1}
    )
    f24_id = await salva_f24(db, documento, source=source)
    rows = normalizza_righe_tributo(documento)
    from app.services.fiscal_accounting_policy import build_journal_proposal

    # Il modello viene conservato come fonte documentale, ma non produce mai
    # una scrittura definitiva. La proposta e' calcolata in memoria e resa
    # visibile all'operatore/commercialista.
    journal_proposal = build_journal_proposal(
        documento,
        document_type="F24_MODELLO",
        context={"source": source},
    )
    return {
        "success": True,
        "duplicate": bool(existing),
        "f24_id": f24_id,
        "filename": filename,
        "righe_tributo": len(rows),
        "righe_credito": sum(1 for row in rows if row["credit_amount"] > 0),
        "validazione": validation,
        "journal_proposal": journal_proposal,
    }


def _saldo(doc: Dict[str, Any]) -> float:
    tot = doc.get("totali") or {}
    val = (
        doc.get("saldo")
        or doc.get("saldo_finale")
        or doc.get("saldo_netto")
        or doc.get("totale_versato")
        or doc.get("totale_versamento")
        or doc.get("importo")
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
        or dg.get("data_stampa")
        or dg.get("data_compilazione")
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


async def salva_f24(
    db,
    doc: Dict[str, Any],
    source: Optional[str] = None,
    *,
    existing_id: Optional[str] = None,
) -> str:
    """Scrive un modello F24 nella collezione canonica in modo IDEMPOTENTE:
    se un F24 con la stessa chiave naturale esiste già lo aggiorna (senza
    duplicarlo), altrimenti lo inserisce. Ritorna l'`id` canonico."""
    doc = dict(doc)
    doc.pop("_id", None)
    validation = doc.get("validazione")
    if validation is not None and (
        validation.get("saldo_quadrato") is not True
        or any(
            isinstance(value, dict) and value.get("stato") == "ERRORE"
            for value in (validation.get("quadrature_sezioni") or {}).values()
        )
    ):
        richiedi_quadratura_f24(doc)
    chiave = chiave_f24(doc)
    doc["f24_dedup_key"] = chiave
    if source:
        doc.setdefault("import_source", source)

    if existing_id:
        doc["id"] = existing_id
        patch = {k: v for k, v in doc.items() if k not in ("id", "_id")}
        await db[COLL].update_one({"id": existing_id}, {"$set": patch})
        return existing_id

    esistente = await db[COLL].find_one({"f24_dedup_key": chiave}, {"_id": 0, "id": 1})
    if esistente:
        patch = {k: v for k, v in doc.items() if k not in ("id", "_id")}
        await db[COLL].update_one({"f24_dedup_key": chiave}, {"$set": patch})
        return esistente.get("id")

    doc.setdefault("id", str(uuid4()))
    doc.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    await db[COLL].insert_one(doc.copy())
    return doc["id"]
