"""
Servizio deduplica fornitori.

Analogo a app/services/dipendenti_dedupe.py — colma il gap #1 di
memoria/moduli/FORNITORI.md: non esisteva alcuna funzione di merge per
fornitori duplicati, a differenza di Dipendenti. Se due fornitori duplicati
venivano creati, il duplicato restava permanente con le fatture storicamente
sparse su due supplier_id diversi.

Chiavi di match:
- Partita IVA normalizzata (letta sia da 'partita_iva' che da 'piva' — la
  ricerca di ensure_supplier_exists in fatture_upload.py usa già entrambi
  i nomi campo, quindi un fornitore storico con la P.IVA sotto 'piva'
  invece che 'partita_iva' elude l'indice unico su 'partita_iva' e può
  generare un vero duplicato).
- Denominazione con fuzzy match reale (difflib.SequenceMatcher), non solo
  il prefix-regex usato da ensure_supplier_exists — gap #2 di FORNITORI.md:
  riconosce forme societarie diverse ("Rossi Srl" vs "Rossi S.r.l.").
"""
from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone

from app.database import Database, Collections

logger = logging.getLogger(__name__)

# Soglia di similarità (0-1) sopra la quale due denominazioni sono
# considerate lo stesso fornitore con certezza "media" (mai "alta": un nome
# simile non è una prova forte quanto una P.IVA identica).
SOGLIA_FUZZY_NOME = 0.82

_FORME_SOCIETARIE = re.compile(
    r"\b(s\.?r\.?l\.?|s\.?p\.?a\.?|s\.?n\.?c\.?|s\.?a\.?s\.?|s\.?s\.?|ditta individuale)\b",
    re.IGNORECASE,
)


def _norm_piva(s: Optional[str]) -> str:
    """Normalizza una P.IVA: rimuove spazi/punteggiatura, upper, strip prefisso IT."""
    if not s:
        return ""
    cleaned = re.sub(r"[^0-9A-Za-z]", "", s).upper()
    if cleaned.startswith("IT") and len(cleaned) == 13:
        cleaned = cleaned[2:]
    return cleaned


def _norm_nome(s: Optional[str]) -> str:
    """Normalizza una denominazione per il confronto fuzzy: minuscolo, senza
    forma societaria, senza punteggiatura, spazi collassati."""
    if not s:
        return ""
    n = s.lower()
    n = _FORME_SOCIETARIE.sub("", n)
    n = re.sub(r"[^\w\s]", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return n


def _get_piva(d: Dict[str, Any]) -> str:
    return _norm_piva(d.get("partita_iva") or d.get("piva"))


def _get_nome(d: Dict[str, Any]) -> str:
    return d.get("ragione_sociale") or d.get("nome") or d.get("denominazione") or ""


def _score_completezza(d: Dict[str, Any]) -> int:
    """Punteggio di completezza: il record più ricco diventa il target del merge."""
    score = 0
    campi_pesanti = [
        "partita_iva", "codice_fiscale", "iban", "metodo_pagamento",
        "indirizzo", "cap", "comune", "provincia", "telefono", "email",
        "giorni_pagamento", "centro_costo_id",
    ]
    for k in campi_pesanti:
        v = d.get(k)
        if v not in (None, "", [], {}, 0):
            score += 2
    if d.get("metodo_pagamento") not in (None, "", "sospesa", "da_configurare"):
        score += 5  # un metodo di pagamento configurato è un forte segnale di record "vero"
    score += int(d.get("fatture_count") or 0)  # più fatture collegate = record più usato
    return score


async def trova_duplicati() -> Dict[str, Any]:
    """
    Ritorna gruppi di fornitori sospetti di essere duplicati.

    Strategie:
    - stessa P.IVA normalizzata (letta da partita_iva O piva — l'indice
      unico DB copre solo 'partita_iva', quindi non basta a prevenire
      questo caso)
    - denominazione fuzzy-simile (soglia 0.82, forma societaria ignorata)
    """
    db = Database.get_db()
    coll = db[Collections.SUPPLIERS]

    all_fornitori = await coll.find(
        {"merged_into": {"$exists": False}}, {"_id": 0}
    ).to_list(10000)
    # Fornitori storici senza campo "id" non sono referenziabili per il merge.
    all_fornitori = [f for f in all_fornitori if f.get("id")]

    by_piva: Dict[str, List[Dict[str, Any]]] = {}
    for f in all_fornitori:
        piva = _get_piva(f)
        if piva:
            by_piva.setdefault(piva, []).append(f)

    gruppi: List[Dict[str, Any]] = []
    visti: set = set()

    for piva, records in by_piva.items():
        if len(records) > 1:
            ids = tuple(sorted(r["id"] for r in records))
            visti.add(ids)
            gruppi.append({
                "tipo": "partita_iva_identica",
                "chiave": piva,
                "fornitori": records,
                "certezza": "alta",
            })

    # Fuzzy match sui nomi, solo tra fornitori non già raggruppati per P.IVA
    # (O(n^2) sulla denominazione normalizzata — accettabile fino a qualche
    # migliaio di fornitori, dimensione tipica di questo dataset).
    non_raggruppati = [
        f for f in all_fornitori
        if not any(f["id"] in ids for ids in visti)
    ]
    normalizzati = [(f, _norm_nome(_get_nome(f))) for f in non_raggruppati]
    normalizzati = [(f, n) for f, n in normalizzati if n]

    for i in range(len(normalizzati)):
        f1, n1 = normalizzati[i]
        if f1["id"] in {rid for ids in visti for rid in ids}:
            continue
        candidati = [f1]
        for j in range(i + 1, len(normalizzati)):
            f2, n2 = normalizzati[j]
            if f2["id"] in {rid for ids in visti for rid in ids}:
                continue
            similarita = SequenceMatcher(None, n1, n2).ratio()
            if similarita >= SOGLIA_FUZZY_NOME:
                candidati.append(f2)
        if len(candidati) > 1:
            ids = tuple(sorted(c["id"] for c in candidati))
            if ids in visti:
                continue
            visti.add(ids)
            gruppi.append({
                "tipo": "denominazione_simile",
                "chiave": n1,
                "fornitori": candidati,
                "certezza": "media",
            })

    return {
        "totale_gruppi": len(gruppi),
        "totale_duplicati": sum(len(g["fornitori"]) - 1 for g in gruppi),
        "gruppi": gruppi,
    }


async def _migra_riferimenti(db, from_id: str, to_id: str) -> Dict[str, int]:
    """
    Re-punta le entità collegate al fornitore duplicato verso il target.
    Le collezioni chiave per P.IVA (non per supplier_id) convergono da sole
    una volta unificata la P.IVA sul record superstite — non richiedono
    migrazione esplicita qui.
    """
    stats = {"fatture_migrate": 0, "scadenze_migrate": 0}

    res = await db[Collections.INVOICES].update_many(
        {"supplier_id": from_id},
        {"$set": {"supplier_id": to_id}},
    )
    stats["fatture_migrate"] = res.modified_count

    if "scadenziario_fornitori" in await db.list_collection_names():
        res = await db["scadenziario_fornitori"].update_many(
            {"fornitore_id": from_id},
            {"$set": {"fornitore_id": to_id}},
        )
        stats["scadenze_migrate"] = res.modified_count

    return stats


async def merge_fornitori(target_id: str, duplicate_id: str, soft: bool = True) -> Dict[str, Any]:
    """
    Unifica `duplicate_id` dentro `target_id`:
    - I campi non vuoti del duplicato completano il target dove il target è vuoto.
    - Le fatture (supplier_id) e le scadenze (fornitore_id) collegate al
      duplicato vengono re-puntate al target.
    - Se `soft=True` (default), il duplicato non viene cancellato ma marcato
      `merged_into=<target_id>` (esclude i futuri find di trova_duplicati/
      ensure_supplier_exists, che non filtrano su merged_into: va tenuto
      presente se in futuro si vuole nasconderlo anche lì).
      Se `soft=False`, il duplicato viene cancellato.
    """
    db = Database.get_db()
    coll = db[Collections.SUPPLIERS]

    target = await coll.find_one({"id": target_id}, {"_id": 0})
    dup = await coll.find_one({"id": duplicate_id}, {"_id": 0})
    if not target or not dup:
        raise ValueError("Target o duplicato non trovati")
    if target_id == duplicate_id:
        raise ValueError("target_id e duplicate_id sono uguali")

    merge_update: Dict[str, Any] = {}
    for k, v in dup.items():
        if k in ("id", "_id", "created_at", "merged_into"):
            continue
        if v in (None, "", [], {}, 0):
            continue
        if target.get(k) in (None, "", [], {}, 0):
            merge_update[k] = v

    # Il numero di fatture collegate va sommato, non sovrascritto.
    fatture_count_target = int(target.get("fatture_count") or 0)
    fatture_count_dup = int(dup.get("fatture_count") or 0)
    if fatture_count_dup:
        merge_update["fatture_count"] = fatture_count_target + fatture_count_dup

    merge_update["updated_at"] = datetime.now(timezone.utc).isoformat()
    if merge_update:
        await coll.update_one({"id": target_id}, {"$set": merge_update})

    stats = await _migra_riferimenti(db, duplicate_id, target_id)

    if soft:
        await coll.update_one(
            {"id": duplicate_id},
            {"$set": {
                "merged_into": target_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }},
        )
        action = "soft_merged"
    else:
        await coll.delete_one({"id": duplicate_id})
        action = "hard_deleted"

    logger.info(f"✅ Merge fornitori: {duplicate_id} → {target_id} ({action}). Stats: {stats}")

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
    Esegue auto-merge dei duplicati a certezza "alta" (stessa P.IVA).
    I duplicati a certezza "media" (solo nome simile) NON vengono mai
    auto-mergiati: un nome simile non è prova sufficiente per un'azione
    automatica su un'anagrafica fiscale — richiedono conferma manuale
    tramite merge_fornitori() diretto.
    """
    gruppi = (await trova_duplicati())["gruppi"]
    merges_effettuati: List[Dict[str, Any]] = []

    for g in gruppi:
        if g["certezza"] != "alta":
            continue
        records = sorted(g["fornitori"], key=_score_completezza, reverse=True)
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
                res = await merge_fornitori(target["id"], dup["id"], soft=True)
                merges_effettuati.append(res)

    return {
        "dry_run": dry_run,
        "gruppi_analizzati": len(gruppi),
        "merges": merges_effettuati,
        "totale_merges": len(merges_effettuati),
    }
