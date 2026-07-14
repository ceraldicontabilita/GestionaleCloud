"""
Servizio deduplica dipendenti.

Rileva duplicati e unifica le schede mantenendo:
- Tutti i campi non vuoti (prende dal record "più ricco")
- Tutti i cedolini/presenze/verbali SENZA duplicarli (re-point al target)
- Logica idempotente: un duplicato già merged non viene ri-processato

Chiavi di match:
- Codice fiscale normalizzato (upper+strip)
- Nome + cognome normalizzati (lower+strip)
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

from app.database import Database, Collections

logger = logging.getLogger(__name__)


def _norm_str(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def _norm_cf(s: Optional[str]) -> str:
    return (s or "").strip().upper()


def _score_completezza(d: Dict[str, Any]) -> int:
    """Assegna un punteggio di completezza al record dipendente."""
    score = 0
    campi_pesanti = [
        "codice_fiscale", "iban", "mansione",
        "data_assunzione", "telefono", "email", "indirizzo", "importo_netto",
        "importo_stipendio", "paga_base", "progressivi", "tfr", "ultimo_cedolino",
    ]
    for k in campi_pesanti:
        v = d.get(k)
        if v not in (None, "", [], {}, 0):
            score += 2
    # Bonus per presenza di dati strutturati
    if isinstance(d.get("progressivi"), dict) and d["progressivi"]:
        score += 5
    if isinstance(d.get("tfr"), dict) and d["tfr"]:
        score += 5
    return score


async def trova_duplicati() -> Dict[str, Any]:
    """
    Ritorna gruppi di dipendenti sospetti di essere duplicati.

    Strategie:
    - stesso codice_fiscale (UPPER)
    - stesso nome+cognome (LOWER)
    """
    db = Database.get_db()
    coll = db[Collections.EMPLOYEES]

    all_dips = await coll.find(
        {"merged_into": {"$exists": False}},
        {"_id": 0},
    ).to_list(5000)

    by_cf: Dict[str, List[Dict[str, Any]]] = {}
    by_nomecog: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}

    for d in all_dips:
        cf = _norm_cf(d.get("codice_fiscale"))
        if cf:
            by_cf.setdefault(cf, []).append(d)
        nome = _norm_str(d.get("nome"))
        cognome = _norm_str(d.get("cognome"))
        if not nome and d.get("nome_completo"):
            parts = _norm_str(d.get("nome_completo")).split()
            if len(parts) >= 2:
                cognome = cognome or parts[0]
                nome = nome or " ".join(parts[1:])
        if nome and cognome:
            by_nomecog.setdefault((cognome, nome), []).append(d)

    gruppi: List[Dict[str, Any]] = []
    visti: set = set()

    for cf, records in by_cf.items():
        if len(records) > 1:
            ids = tuple(sorted(r["id"] for r in records))
            visti.add(ids)
            gruppi.append({
                "tipo": "codice_fiscale_identico",
                "chiave": cf,
                "dipendenti": records,
                "certezza": "alta",
            })

    for (cog, nom), records in by_nomecog.items():
        if len(records) > 1:
            ids = tuple(sorted(r["id"] for r in records))
            if ids in visti:
                continue
            visti.add(ids)
            # Certezza "alta" se i CF sono tutti vuoti o tutti uguali.
            # "media" se CF diversi (potrebbero essere persone diverse omonime).
            cfs = {_norm_cf(r.get("codice_fiscale")) for r in records}
            cfs.discard("")
            certezza = "alta" if len(cfs) <= 1 else "media"
            gruppi.append({
                "tipo": "nome_cognome_identico",
                "chiave": f"{cog} {nom}",
                "dipendenti": records,
                "certezza": certezza,
            })

    return {
        "totale_gruppi": len(gruppi),
        "totale_duplicati": sum(len(g["dipendenti"]) - 1 for g in gruppi),
        "gruppi": gruppi,
    }


async def _migra_riferimenti(db, from_id: str, to_id: str, from_cf: str, to_cf: str) -> Dict[str, int]:
    """
    Migra riferimenti di cedolini/presenze/verbali/giustificativi
    dal dipendente 'from' al dipendente 'to', evitando di duplicare:
    - cedolini già presenti (match su anno+mese)
    """
    stats = {
        "cedolini_migrati": 0,
        "cedolini_skippati_duplicati": 0,
        "presenze_migrate": 0,
        "giustificativi_migrati": 0,
        "verbali_migrati": 0,
        "bonifici_migrati": 0,
    }

    # ── Cedolini: evitare duplicati (anno+mese).
    cedolini_from = await db["cedolini"].find(
        {"$or": [{"dipendente_id": from_id}, {"codice_fiscale": from_cf} if from_cf else {"_impossible": True}]},
        {"_id": 0, "id": 1, "anno": 1, "mese": 1}
    ).to_list(5000) if from_cf or from_id else []

    for ced in cedolini_from:
        anno = ced.get("anno")
        mese = ced.get("mese")
        exists = await db["cedolini"].find_one({
            "dipendente_id": to_id,
            "anno": anno,
            "mese": mese,
        }, {"_id": 1})
        if exists and ced.get("id"):
            # Duplicato: elimina quello del record from (è ridondante)
            await db["cedolini"].delete_one({"id": ced["id"]})
            stats["cedolini_skippati_duplicati"] += 1
        else:
            await db["cedolini"].update_one(
                {"id": ced["id"]},
                {"$set": {"dipendente_id": to_id, "codice_fiscale": to_cf or ced.get("codice_fiscale")}}
            )
            stats["cedolini_migrati"] += 1

    # ── Presenze: re-point senza controlli (duplicati già gestiti a livello UI)
    if "presenze" in await db.list_collection_names():
        res = await db["presenze"].update_many(
            {"dipendente_id": from_id},
            {"$set": {"dipendente_id": to_id}}
        )
        stats["presenze_migrate"] = res.modified_count

    # ── Giustificativi
    if "giustificativi" in await db.list_collection_names():
        res = await db["giustificativi"].update_many(
            {"dipendente_id": from_id},
            {"$set": {"dipendente_id": to_id}}
        )
        stats["giustificativi_migrati"] = res.modified_count

    # ── Verbali noleggio
    if "verbali_noleggio" in await db.list_collection_names():
        res = await db["verbali_noleggio"].update_many(
            {"dipendente_id": from_id},
            {"$set": {"dipendente_id": to_id}}
        )
        stats["verbali_migrati"] = res.modified_count

    # ── Bonifici stipendio / movimenti
    if "estratto_conto_movimenti" in await db.list_collection_names():
        res = await db["estratto_conto_movimenti"].update_many(
            {"dipendente_id": from_id},
            {"$set": {"dipendente_id": to_id}}
        )
        stats["bonifici_migrati"] = res.modified_count

    return stats


async def merge_dipendenti(target_id: str, duplicate_id: str, soft: bool = True) -> Dict[str, Any]:
    """
    Unifica `duplicate_id` dentro `target_id`:
    - I campi non vuoti di `duplicate` completano il target dove il target è vuoto.
    - I cedolini e altre entità collegate al `duplicate` vengono re-point al target
      (evitando duplicati cedolini sullo stesso anno+mese).
    - Se `soft=True`, il duplicato non viene cancellato ma marcato
      `in_carico=False, stato='merged', merged_into=<target_id>`.
      Se `soft=False`, il duplicato viene cancellato.
    """
    db = Database.get_db()
    coll = db[Collections.EMPLOYEES]

    target = await coll.find_one({"id": target_id}, {"_id": 0})
    dup = await coll.find_one({"id": duplicate_id}, {"_id": 0})
    if not target or not dup:
        raise ValueError("Target o duplicato non trovati")
    if target_id == duplicate_id:
        raise ValueError("target_id e duplicate_id sono uguali")

    # Merge dei campi: il duplicato completa il target dove il target è vuoto
    merge_update: Dict[str, Any] = {}
    for k, v in dup.items():
        if k in ("id", "_id", "created_at", "in_carico", "stato", "merged_into"):
            continue
        if v in (None, "", [], {}, 0):
            continue
        current = target.get(k)
        if current in (None, "", [], {}, 0):
            merge_update[k] = v
        elif k in ("progressivi", "tfr") and isinstance(current, dict) and isinstance(v, dict):
            # Merge delle chiavi anno mancanti
            merged = {**v, **current}
            if merged != current:
                merge_update[k] = merged

    merge_update["updated_at"] = datetime.now(timezone.utc).isoformat()

    await coll.update_one({"id": target_id}, {"$set": merge_update})

    # Migrazione riferimenti
    to_cf = _norm_cf(target.get("codice_fiscale"))
    from_cf = _norm_cf(dup.get("codice_fiscale"))
    stats = await _migra_riferimenti(db, duplicate_id, target_id, from_cf, to_cf)

    # Soft/hard delete del duplicato
    if soft:
        await coll.update_one(
            {"id": duplicate_id},
            {"$set": {
                "in_carico": False,
                "stato": "merged",
                "merged_into": target_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )
        action = "soft_merged"
    else:
        await coll.delete_one({"id": duplicate_id})
        action = "hard_deleted"

    logger.info(f"✅ Merge dipendenti: {duplicate_id} → {target_id} ({action}). Stats: {stats}")

    return {
        "success": True,
        "target_id": target_id,
        "duplicate_id": duplicate_id,
        "action": action,
        "campi_aggiunti_al_target": list(merge_update.keys()),
        "stats_migrazione": stats,
    }


async def auto_merge_tutti(dry_run: bool = True) -> Dict[str, Any]:
    """
    Esegue auto-merge di tutti i duplicati ad alta certezza.
    Il record scelto come target è quello con punteggio di completezza più alto.
    """
    gruppi = (await trova_duplicati())["gruppi"]
    merges_effettuati: List[Dict[str, Any]] = []

    for g in gruppi:
        if g["certezza"] != "alta":
            continue
        records = sorted(g["dipendenti"], key=_score_completezza, reverse=True)
        target = records[0]
        for dup in records[1:]:
            if dry_run:
                merges_effettuati.append({
                    "target_id": target["id"],
                    "duplicate_id": dup["id"],
                    "target_score": _score_completezza(target),
                    "dup_score": _score_completezza(dup),
                    "dry_run": True,
                })
            else:
                res = await merge_dipendenti(target["id"], dup["id"], soft=True)
                merges_effettuati.append(res)

    return {
        "dry_run": dry_run,
        "gruppi_analizzati": len(gruppi),
        "merges": merges_effettuati,
        "totale_merges": len(merges_effettuati),
    }
