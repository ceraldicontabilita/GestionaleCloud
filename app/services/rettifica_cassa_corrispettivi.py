"""Rettifica reversibile delle entrate Cassa create col lordo RT.

Il documento ``corrispettivi`` e' l'unica fonte ammessa. La riga viene
modificata soltanto se porta il suo ``corrispettivo_id`` e il documento
collegato contiene una quota ``pagato_contanti`` numerica e valida.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Dict, List, Optional


MIGRATION_ID = "cassa-corrispettivi-solo-contanti-v1"


async def _rows(cursor, limit: int = 100000) -> List[Dict[str, Any]]:
    if hasattr(cursor, "to_list"):
        return await cursor.to_list(limit)
    return [row async for row in cursor]


CENT = Decimal("0.01")


def _money(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        amount = Decimal(str(value).replace(",", ".")).quantize(
            CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError):
        return None
    return amount if amount >= Decimal("0") else None


def _json_money(value: Decimal) -> float:
    """Il document store JSON usa numeri; i calcoli restano Decimal."""
    return float(value)


def _year_query(anno: Optional[int]) -> Dict[str, Any]:
    query: Dict[str, Any] = {
        "tipo": "entrata",
        "categoria": "Corrispettivi",
        "corrispettivo_id": {"$nin": [None, ""]},
        "status": {"$nin": ["deleted", "archived"]},
    }
    if anno:
        query["data"] = {"$regex": f"^{int(anno)}-"}
    return query


async def analizza(db, anno: Optional[int] = None) -> Dict[str, Any]:
    righe = await _rows(db["prima_nota_cassa"].find(
        _year_query(anno), {"_id": 0}))
    report = {
        "anno": anno,
        "righe_esaminate": len(righe),
        "gia_corrette": 0,
        "da_rettificare": 0,
        "da_verificare": 0,
        "collegamenti_inversi_da_completare": 0,
        "importo_prima": 0.0,
        "importo_contanti_documentato": 0.0,
        "differenza": 0.0,
        "cancellazioni": 0,
    }
    for riga in righe:
        corr_id = riga.get("corrispettivo_id")
        corr = await db["corrispettivi"].find_one(
            {"id": corr_id}, {"_id": 0})
        cash = _money((corr or {}).get("pagato_contanti"))
        totale = _money((corr or {}).get("totale"))
        corrente = _money(riga.get("importo"))
        if not corr or cash is None or corrente is None or (
                totale is not None and cash > totale + CENT):
            report["da_verificare"] += 1
            continue
        report["importo_prima"] += _json_money(corrente)
        report["importo_contanti_documentato"] += _json_money(cash)
        if abs(corrente - cash) < CENT:
            report["gia_corrette"] += 1
        else:
            report["da_rettificare"] += 1
        if corr.get("prima_nota_cassa_id") != riga.get("id"):
            report["collegamenti_inversi_da_completare"] += 1
    for key in ("importo_prima", "importo_contanti_documentato"):
        report[key] = round(report[key], 2)
    report["differenza"] = round(
        report["importo_prima"] - report["importo_contanti_documentato"], 2)
    return report


async def applica(db, anno: Optional[int] = None,
                  actor: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    prima = await analizza(db, anno)
    now = datetime.now(timezone.utc).isoformat()
    actor = actor or {}
    actor_id = actor.get("sub") or actor.get("user_id") or "sistema"
    righe = await _rows(db["prima_nota_cassa"].find(
        _year_query(anno), {"_id": 0}))
    rettificate = collegamenti = 0
    audit_rows: List[Dict[str, Any]] = []

    for riga in righe:
        corr_id = riga.get("corrispettivo_id")
        corr = await db["corrispettivi"].find_one(
            {"id": corr_id}, {"_id": 0})
        cash = _money((corr or {}).get("pagato_contanti"))
        totale = _money((corr or {}).get("totale"))
        corrente = _money(riga.get("importo"))
        if not corr or cash is None or corrente is None or (
                totale is not None and cash > totale + CENT):
            continue

        if abs(corrente - cash) >= CENT:
            snapshot = {
                "importo": riga.get("importo"),
                "amount": riga.get("amount"),
                "pagato_contanti": riga.get("pagato_contanti"),
                "contanti": riga.get("contanti"),
            }
            await db["prima_nota_cassa"].update_one(
                {"id": riga["id"], "corrispettivo_id": corr_id},
                {"$set": {
                    "importo": _json_money(cash),
                    "amount": _json_money(cash),
                    "pagato_contanti": _json_money(cash),
                    "contanti": _json_money(cash),
                    "totale_corrispettivo": (
                        _json_money(totale) if totale is not None else None),
                    "rettifica_cassa_migration_id": MIGRATION_ID,
                    "rettifica_cassa_originale": snapshot,
                    "rettifica_cassa_at": now,
                    "rettifica_cassa_by": actor_id,
                    "rettifica_cassa_fonte": "corrispettivi.pagato_contanti",
                }},
            )
            audit_rows.append({
                "id": f"{MIGRATION_ID}:{riga['id']}",
                "migration_id": MIGRATION_ID,
                "prima_nota_cassa_id": riga["id"],
                "corrispettivo_id": corr_id,
                "prima": snapshot,
                "dopo": {"importo": _json_money(cash)},
                "fonte": "corrispettivi.pagato_contanti",
                "documento_hash": (corr.get("content_hash")
                                    or (corr.get("source_hashes") or [None])[0]),
                "documento_origine": corr.get("source"),
                "documento_file": corr.get("filename"),
                "actor": actor_id,
                "created_at": now,
            })
            rettificate += 1

        if corr.get("prima_nota_cassa_id") != riga.get("id"):
            await db["corrispettivi"].update_one(
                {"id": corr_id},
                {"$set": {
                    "prima_nota_cassa_id": riga["id"],
                    "prima_nota_id": riga["id"],
                    "collegamento_cassa_verificato_at": now,
                }},
            )
            collegamenti += 1

    for audit in audit_rows:
        await db["rettifiche_contabili_audit"].update_one(
            {"id": audit["id"]}, {"$setOnInsert": audit}, upsert=True)

    dopo = await analizza(db, anno)
    return {
        "migration_id": MIGRATION_ID,
        "prima": prima,
        "dopo": dopo,
        "righe_rettificate": rettificate,
        "collegamenti_inversi_completati": collegamenti,
        "audit_creati": len(audit_rows),
        "cancellazioni": 0,
    }
