"""Esecuzione portabile delle operazioni bulk usate da Lotti.

``mongomock`` e PyMongo non mantengono sempre sincronizzata la firma interna
di ``bulk_write`` (PyMongo 4.16 passa, per esempio, il parametro ``sort`` che
alcune versioni di mongomock non accettano).  L'app non ha bisogno delle
ottimizzazioni del protocollo Mongo: il deposito autorevole e' Supabase.
Questa funzione applica quindi le richieste una alla volta tramite l'adattatore
documentale, conservando la semantica ordinata/non ordinata e i contatori utili
ai chiamanti.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Iterable

#: Ogni quante operazioni il ciclo cede il loop. Il deposito documentale
#: lavora in memoria: un ``update_one`` non attende niente di reale, e 500
#: upsert di fila tenevano fermo l'event loop per ~10 s (07/10/2026: Render
#: non riceveva /api/health e riavviava l'istanza, uccidendo il giro della
#: cartella unica). Con una pausa ogni poche operazioni il servizio risponde.
OPERAZIONI_PER_RESPIRO = 25


@dataclass
class BulkCompatResult:
    matched_count: int = 0
    modified_count: int = 0
    deleted_count: int = 0
    inserted_count: int = 0
    upserted_count: int = 0


async def bulk_write_compat(collection: Any, requests: Iterable[Any], *, ordered: bool = True) -> BulkCompatResult:
    result = BulkCompatResult()
    errors: list[Exception] = []
    for indice, request in enumerate(requests):
        if indice and indice % OPERAZIONI_PER_RESPIRO == 0:
            await asyncio.sleep(0)
        name = type(request).__name__
        try:
            if name == "UpdateOne":
                outcome = await collection.update_one(
                    request._filter,
                    request._doc,
                    upsert=bool(request._upsert),
                )
                result.matched_count += int(outcome.matched_count)
                result.modified_count += int(outcome.modified_count)
                result.upserted_count += int(outcome.upserted_id is not None)
            elif name == "UpdateMany":
                outcome = await collection.update_many(
                    request._filter,
                    request._doc,
                    upsert=bool(request._upsert),
                )
                result.matched_count += int(outcome.matched_count)
                result.modified_count += int(outcome.modified_count)
                result.upserted_count += int(outcome.upserted_id is not None)
            elif name == "DeleteOne":
                outcome = await collection.delete_one(request._filter)
                result.deleted_count += int(outcome.deleted_count)
            elif name == "DeleteMany":
                outcome = await collection.delete_many(request._filter)
                result.deleted_count += int(outcome.deleted_count)
            elif name == "InsertOne":
                await collection.insert_one(request._doc)
                result.inserted_count += 1
            elif name == "ReplaceOne":
                outcome = await collection.replace_one(
                    request._filter,
                    request._doc,
                    upsert=bool(request._upsert),
                )
                result.matched_count += int(outcome.matched_count)
                result.modified_count += int(outcome.modified_count)
                result.upserted_count += int(outcome.upserted_id is not None)
            else:
                raise TypeError(f"Operazione bulk non supportata: {name}")
        except Exception as exc:  # noqa: BLE001 - conserva ordered=False
            if ordered:
                raise
            errors.append(exc)
    if errors:
        raise errors[0]
    return result
