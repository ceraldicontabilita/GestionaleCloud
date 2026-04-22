"""
migrate_dedup_prima_nota.py
===========================
Migrazione one-shot per Prima Nota Cassa e Banca.

Fa due cose:
  1. DEDUP: elimina (hard delete) i movimenti duplicati già presenti nel DB.
     Per ogni gruppo di duplicati, mantiene il documento più vecchio
     (created_at minore) e cancella gli altri.

  2. INDICI UNICI: crea indici MongoDB parziali che impediscono fisicamente
     nuovi duplicati di fatture in futuro.

Strategia di dedup
------------------
Due movimenti sono considerati duplicati se condividono:
  a) lo stesso fattura_id         (chiave primaria fattura)
  b) o lo stesso riferimento FATT-{id}  (chiave alternativa usata da sync)
  c) o stesso numero_fattura + importo + data  (fallback per vecchi documenti)

I corrispettivi hanno una loro logica: dedup su corrispettivo_id separato.

Esecuzione
----------
  python scripts/migrate_dedup_prima_nota.py [--dry-run]

  --dry-run  Stampa cosa farebbe senza modificare il DB.

Richiede la variabile d'ambiente MONGODB_ATLAS_URI (o MONGO_URL).
"""
import asyncio
import os
import sys
import logging
from collections import defaultdict
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)

DRY_RUN = "--dry-run" in sys.argv

CASSA = "prima_nota_cassa"
BANCA = "prima_nota_banca"
DB_NAME = "azienda_erp_db"

STATUSES_VIVI = {"$nin": ["deleted", "archived"]}


def get_mongo_uri() -> str:
    uri = os.getenv("MONGODB_ATLAS_URI") or os.getenv("MONGO_URL")
    if not uri:
        raise RuntimeError(
            "Imposta MONGODB_ATLAS_URI o MONGO_URL prima di eseguire lo script."
        )
    return uri


# ──────────────────────────────────────────────
# 1. DEDUP
# ──────────────────────────────────────────────

def _dedup_key(doc: dict) -> str | None:
    """Ritorna la chiave di dedup o None se il documento non è una fattura."""
    fid = doc.get("fattura_id")
    if fid:
        return f"fid:{fid}"

    rif = doc.get("riferimento") or ""
    if rif.startswith("FATT-"):
        return f"rif:{rif}"

    num = doc.get("numero_fattura") or ""
    imp = doc.get("importo")
    dat = doc.get("data") or ""
    if num and imp is not None:
        return f"num:{num}|imp:{imp}|dat:{dat}"

    return None  # non è una fattura, ignora


def _dedup_key_corrispettivo(doc: dict) -> str | None:
    cid = doc.get("corrispettivo_id")
    src = doc.get("source", "")
    if cid and src in ("corrispettivi_sync",):
        return f"corr:{cid}"
    return None


async def dedup_collection(db, collection_name: str) -> dict:
    """Trova e rimuove i duplicati in una collection.
    Ritorna un dict con statistiche."""

    log.info("── DEDUP %s ──────────────────────────", collection_name)
    coll = db[collection_name]

    # Carica tutti i movimenti vivi
    docs = await coll.find(
        {"status": STATUSES_VIVI},
        {"_id": 1, "id": 1, "fattura_id": 1, "riferimento": 1,
         "numero_fattura": 1, "importo": 1, "data": 1,
         "corrispettivo_id": 1, "source": 1, "created_at": 1}
    ).to_list(100_000)

    log.info("  Documenti vivi trovati: %d", len(docs))

    # Raggruppa per chiave di dedup
    gruppi: dict[str, list] = defaultdict(list)
    for doc in docs:
        key = _dedup_key(doc) or _dedup_key_corrispettivo(doc)
        if key:
            gruppi[key].append(doc)

    # Identifica i duplicati
    ids_da_eliminare = []
    campione = []
    for key, gruppo in gruppi.items():
        if len(gruppo) <= 1:
            continue
        # Ordina per created_at crescente: il più vecchio si tiene
        gruppo.sort(key=lambda d: d.get("created_at") or "9999-99-99")
        da_tenere = gruppo[0]
        da_togliere = gruppo[1:]
        ids_mongo = [d["_id"] for d in da_togliere]
        ids_da_eliminare.extend(ids_mongo)
        if len(campione) < 20:
            campione.append({
                "chiave": key,
                "tenuto": da_tenere.get("id"),
                "tenuto_data": da_tenere.get("data"),
                "eliminati": [d.get("id") for d in da_togliere],
                "n": len(da_togliere),
            })

    log.info("  Gruppi duplicati: %d", len([g for g in gruppi.values() if len(g) > 1]))
    log.info("  Movimenti da eliminare: %d", len(ids_da_eliminare))

    if campione:
        log.info("  Campione (primi %d):", len(campione))
        for c in campione[:5]:
            log.info("    chiave=%s  eliminati=%s", c["chiave"], c["n"])

    deleted = 0
    if ids_da_eliminare:
        if DRY_RUN:
            log.info("  [DRY-RUN] eliminazione saltata.")
        else:
            result = await coll.delete_many({"_id": {"$in": ids_da_eliminare}})
            deleted = result.deleted_count
            log.info("  ✓ Eliminati: %d documenti", deleted)

    return {
        "collection": collection_name,
        "documenti_vivi": len(docs),
        "gruppi_duplicati": len([g for g in gruppi.values() if len(g) > 1]),
        "da