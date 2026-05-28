"""
Vista unificata read-only sulle 3+ collezioni documenti.

Oggi esistono in parallelo:
- documents_inbox        (~803 docs) — buca della posta principale
- documenti_classificati (~1967 docs) — classificati
- documenti_non_associati(~285 docs) — quarantena utente

Tutte e tre sono usate da decine di servizi in scrittura. Per evitare
rotture, NON migro i dati. Espongo invece una vista virtuale che fa
$unionWith e proietta un formato comune. Cosi' la UI e gli endpoint
GET vedono "documenti" come una collezione sola, anche se sotto restano
fisicamente separate.

La migrazione fisica dei dati restera' un task offline a parte (script
in app/scripts/migrazione_documenti.py, ancora da scrivere e da eseguire
solo dopo un punto fermo concordato).
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional


# Mappa: collezione fisica -> "stato" logico nella vista unificata.
COLLEZIONI_DOCUMENTI: Dict[str, str] = {
    "documents_inbox": "inbox",
    "documenti_classificati": "classificato",
    "documenti_non_associati": "non_associato",
}


def _proiezione_comune(stato_logico: str) -> Dict[str, Any]:
    """Proiezione che porta i nomi-campo eterogenei a un set comune.

    Cosi' chi legge la lista unificata trova sempre: id, hash, nome_file,
    mittente, data, tipo, stato, link_modulo, link_id, raw.
    """
    return {
        "_id": 0,
        "id": {"$ifNull": ["$id", {"$toString": "$_id"}]},
        "hash": {"$ifNull": ["$file_hash", "$sha256"]},
        "nome_file": {"$ifNull": ["$filename", "$file_name"]},
        "mittente": {"$ifNull": ["$mittente", "$from"]},
        "data": {"$ifNull": ["$data", "$created_at"]},
        "tipo": {"$ifNull": ["$tipo", "$categoria"]},
        "stato": {"$literal": stato_logico},
        "fonte_collection": {"$literal": "_COLL_"},
        "link_modulo": {"$ifNull": ["$linked_modulo", None]},
        "link_id": {"$ifNull": ["$linked_id", None]},
    }


def _pipeline_lista(
    filtro: Optional[Dict[str, Any]] = None,
    skip: int = 0,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Pipeline di aggregazione sulla prima collezione + $unionWith sulle altre.

    Il chiamante usa db['documents_inbox'].aggregate(_pipeline_lista(...)).
    """
    filtro = filtro or {}
    pipelines = []
    coll_principale, stato_principale = next(iter(COLLEZIONI_DOCUMENTI.items()))
    pip_principale: List[Dict[str, Any]] = []
    if filtro:
        pip_principale.append({"$match": filtro})
    proj = _proiezione_comune(stato_principale)
    proj["fonte_collection"]["$literal"] = coll_principale
    pip_principale.append({"$project": proj})
    pipelines.extend(pip_principale)

    # union con le altre
    for coll, stato in list(COLLEZIONI_DOCUMENTI.items())[1:]:
        sub: List[Dict[str, Any]] = []
        if filtro:
            sub.append({"$match": filtro})
        proj_sub = _proiezione_comune(stato)
        proj_sub["fonte_collection"]["$literal"] = coll
        sub.append({"$project": proj_sub})
        pipelines.append({"$unionWith": {"coll": coll, "pipeline": sub}})

    # ordinamento + paginazione DOPO la union
    pipelines.append({"$sort": {"data": -1}})
    if skip:
        pipelines.append({"$skip": int(skip)})
    pipelines.append({"$limit": int(limit)})
    return pipelines


async def conta_totali(db) -> Dict[str, int]:
    """Conta documenti per stato logico."""
    out: Dict[str, int] = {}
    for coll, stato in COLLEZIONI_DOCUMENTI.items():
        out[stato] = await db[coll].count_documents({})
    out["totale"] = sum(out.values())
    return out


async def lista_unificata(
    db,
    filtro: Optional[Dict[str, Any]] = None,
    skip: int = 0,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Restituisce la lista unificata dei documenti, ordinata per data desc."""
    coll_principale = next(iter(COLLEZIONI_DOCUMENTI.keys()))
    pipeline = _pipeline_lista(filtro=filtro, skip=skip, limit=max(1, min(limit, 200)))
    cursor = db[coll_principale].aggregate(pipeline, allowDiskUse=True)
    return await cursor.to_list(length=limit)


async def trova_per_id(db, documento_id: str) -> Optional[Dict[str, Any]]:
    """Cerca un documento per id in tutte e tre le collezioni.

    Restituisce il primo trovato, con il campo `fonte_collection` valorizzato.
    """
    for coll in COLLEZIONI_DOCUMENTI.keys():
        doc = await db[coll].find_one({"id": documento_id}, {"_id": 0})
        if doc:
            doc["fonte_collection"] = coll
            return doc
    return None
