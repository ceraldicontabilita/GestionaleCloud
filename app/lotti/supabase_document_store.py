"""Persistenza Supabase compatibile con l'API Motor usata da Lotti.

L'applicazione storica usa intensamente l'API MongoDB. Per preservare router,
test e soprattutto il frontend, questo modulo mantiene la semantica Mongo in
memoria tramite ``mongomock-motor`` e rende ogni scrittura persistente in una
tabella JSONB privata su Supabase.

Vincoli intenzionali:
* una sola istanza applicativa (il servizio Render corrente);
* RLS chiusa sulle tabelle; l'accesso avviene solo tramite RPC autenticate con
  un segreto applicativo;
* caricamento pigro per collezione e serializzazione delle scritture, così i
  restart di Render non perdono dati.
"""

from __future__ import annotations

import asyncio
import base64
import copy
import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable, Iterable, Optional

import httpx
from bson import Binary, ObjectId
from mongomock_motor import AsyncMongoMockClient


def _json_safe(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return {"$oid": str(value)}
    if isinstance(value, datetime):
        return {"$date_iso": value.isoformat()}
    if isinstance(value, date):
        return {"$date_only": value.isoformat()}
    if isinstance(value, Decimal):
        return {"$decimal": str(value)}
    if isinstance(value, (bytes, bytearray, Binary)):
        return {"$binary_base64": base64.b64encode(bytes(value)).decode("ascii")}
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _json_restore(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {"$binary_base64"}:
            return Binary(base64.b64decode(value["$binary_base64"]))
        if set(value) == {"$oid"}:
            return ObjectId(value["$oid"])
        if set(value) == {"$date_iso"}:
            return datetime.fromisoformat(value["$date_iso"])
        if set(value) == {"$date_only"}:
            return date.fromisoformat(value["$date_only"])
        if set(value) == {"$decimal"}:
            return Decimal(value["$decimal"])
        return {k: _json_restore(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_restore(v) for v in value]
    return value


def _doc_id(doc: dict) -> str:
    current = doc.get("_id")
    if current is None:
        current = doc.get("id") or str(uuid.uuid4())
        doc["_id"] = current
    return str(current)


class SupabaseRpcStore:
    def __init__(self, url: str, api_key: str, secret: str):
        self.url = url.rstrip("/")
        self.secret = secret
        self.client = httpx.AsyncClient(
            base_url=f"{self.url}/rest/v1",
            headers={
                "apikey": api_key,
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(60.0, connect=15.0),
        )

    async def _rpc(self, name: str, payload: dict) -> Any:
        response = await self.client.post(f"/rpc/{name}", json=payload)
        response.raise_for_status()
        if not response.content:
            return None
        return response.json()

    async def list_collections(self) -> list[str]:
        result = await self._rpc("lotti_list_collections", {"p_secret": self.secret})
        return list(result or [])

    async def list_docs(self, collection: str) -> list[dict]:
        offset = 0
        items: list[dict] = []
        while True:
            page = await self._rpc(
                "lotti_list_docs",
                {
                    "p_secret": self.secret,
                    "p_collection": collection,
                    "p_offset": offset,
                    "p_limit": 500,
                },
            )
            rows = (page or {}).get("items") or []
            items.extend(_json_restore(row.get("data") or {}) for row in rows)
            offset += len(rows)
            if not rows or offset >= int((page or {}).get("total") or 0):
                return items

    async def upsert_docs(self, collection: str, docs: Iterable[dict]) -> int:
        rows = []
        total = 0
        for original in docs:
            doc = copy.deepcopy(original)
            rows.append({"doc_id": _doc_id(doc), "data": _json_safe(doc)})
            if len(rows) >= 200:
                total += int(await self._rpc("lotti_upsert_docs", {
                    "p_secret": self.secret, "p_collection": collection, "p_rows": rows
                }) or 0)
                rows = []
        if rows:
            total += int(await self._rpc("lotti_upsert_docs", {
                "p_secret": self.secret, "p_collection": collection, "p_rows": rows
            }) or 0)
        return total

    async def delete_docs(self, collection: str, doc_ids: Iterable[Any]) -> int:
        ids = [str(x) for x in doc_ids]
        if not ids:
            return 0
        return int(await self._rpc("lotti_delete_docs", {
            "p_secret": self.secret, "p_collection": collection, "p_doc_ids": ids
        }) or 0)

    async def delete_collection(self, collection: str) -> int:
        return int(await self._rpc("lotti_delete_collection", {
            "p_secret": self.secret, "p_collection": collection
        }) or 0)

    async def rename_collection(self, source: str, target: str, drop_target: bool) -> int:
        return int(await self._rpc("lotti_rename_collection", {
            "p_secret": self.secret,
            "p_source": source,
            "p_target": target,
            "p_drop_target": drop_target,
        }) or 0)

    async def close(self) -> None:
        await self.client.aclose()


class LazyCursor:
    def __init__(self, collection: "PersistentCollection", factory: Callable[[], Any]):
        self.collection = collection
        self.factory = factory
        self.operations: list[tuple[str, tuple, dict]] = []
        self._iterator = None

    def _chain(self, name: str, *args, **kwargs):
        self.operations.append((name, args, kwargs))
        return self

    def sort(self, *args, **kwargs):
        return self._chain("sort", *args, **kwargs)

    def skip(self, *args, **kwargs):
        return self._chain("skip", *args, **kwargs)

    def limit(self, *args, **kwargs):
        return self._chain("limit", *args, **kwargs)

    def batch_size(self, *args, **kwargs):
        return self._chain("batch_size", *args, **kwargs)

    async def _cursor(self):
        await self.collection._ensure_loaded()
        cursor = self.factory()
        for name, args, kwargs in self.operations:
            cursor = getattr(cursor, name)(*args, **kwargs)
        return cursor

    async def to_list(self, length: Optional[int] = None):
        cursor = await self._cursor()
        return await cursor.to_list(length)

    def __aiter__(self):
        self._iterator = self._iterate()
        return self._iterator

    async def _iterate(self):
        cursor = await self._cursor()
        async for item in cursor:
            yield item

    async def close(self):
        if self._iterator and hasattr(self._iterator, "aclose"):
            await self._iterator.aclose()


class PersistentCollection:
    def __init__(self, database: "PersistentDatabase", name: str):
        self.database = database
        self.name = name
        self.raw = database.raw[name]
        self._loaded = False
        self._load_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()

    async def _ensure_loaded(self):
        if self._loaded:
            return
        async with self._load_lock:
            if self._loaded:
                return
            docs = await self.database.store.list_docs(self.name)
            if docs:
                await self.raw.insert_many(docs)
            self._loaded = True

    def find(self, *args, **kwargs):
        return LazyCursor(self, lambda: self.raw.find(*args, **kwargs))

    def aggregate(self, *args, **kwargs):
        return LazyCursor(self, lambda: self.raw.aggregate(*args, **kwargs))

    async def find_one(self, *args, **kwargs):
        await self._ensure_loaded()
        return await self.raw.find_one(*args, **kwargs)

    async def count_documents(self, *args, **kwargs):
        await self._ensure_loaded()
        return await self.raw.count_documents(*args, **kwargs)

    async def distinct(self, *args, **kwargs):
        await self._ensure_loaded()
        return await self.raw.distinct(*args, **kwargs)

    async def create_index(self, *args, **kwargs):
        await self._ensure_loaded()
        return await self.raw.create_index(*args, **kwargs)

    async def index_information(self, *args, **kwargs):
        await self._ensure_loaded()
        return await self.raw.index_information(*args, **kwargs)

    async def insert_one(self, document, *args, **kwargs):
        async with self._write_lock:
            await self._ensure_loaded()
            result = await self.raw.insert_one(document, *args, **kwargs)
            await self.database.store.upsert_docs(self.name, [document])
            return result

    async def insert_many(self, documents, *args, **kwargs):
        docs = list(documents)
        async with self._write_lock:
            await self._ensure_loaded()
            result = await self.raw.insert_many(docs, *args, **kwargs)
            await self.database.store.upsert_docs(self.name, docs)
            return result

    async def _persist_matches(self, query: dict):
        docs = await self.raw.find(query).to_list(None)
        await self.database.store.upsert_docs(self.name, docs)

    async def update_one(self, query, update, *args, **kwargs):
        async with self._write_lock:
            await self._ensure_loaded()
            before = await self.raw.find_one(query, {"_id": 1})
            result = await self.raw.update_one(query, update, *args, **kwargs)
            persisted = False
            if before is not None:
                after = await self.raw.find_one({"_id": before["_id"]})
                if after is not None:
                    await self.database.store.upsert_docs(self.name, [after])
                    persisted = True
            if not persisted and kwargs.get("upsert"):
                await self._persist_matches(query)
            return result

    async def update_many(self, query, update, *args, **kwargs):
        async with self._write_lock:
            await self._ensure_loaded()
            before = await self.raw.find(query, {"_id": 1}).to_list(None)
            result = await self.raw.update_many(query, update, *args, **kwargs)
            ids = [d["_id"] for d in before]
            after = await self.raw.find({"_id": {"$in": ids}}).to_list(None) if ids else []
            if after:
                await self.database.store.upsert_docs(self.name, after)
            if not after and kwargs.get("upsert"):
                await self._persist_matches(query)
            return result

    async def update_documents_by_id(self, updates: Iterable[tuple[Any, dict]]) -> int:
        """Applica set differenti e li persiste con un solo upsert remoto.

        Serve ai processi batch: la memoria resta coerente con l'API Mongo, ma
        Supabase riceve un unico lotto invece di una richiesta per documento.
        """
        changes = list(updates)
        if not changes:
            return 0
        async with self._write_lock:
            await self._ensure_loaded()
            docs = []
            for doc_id, fields in changes:
                result = await self.raw.update_one(
                    {"_id": doc_id},
                    {"$set": fields},
                )
                if result.matched_count:
                    after = await self.raw.find_one({"_id": doc_id})
                    if after is not None:
                        docs.append(after)
            if docs:
                await self.database.store.upsert_docs(self.name, docs)
            return len(docs)

    async def replace_one(self, query, replacement, *args, **kwargs):
        async with self._write_lock:
            await self._ensure_loaded()
            before = await self.raw.find_one(query, {"_id": 1})
            result = await self.raw.replace_one(query, replacement, *args, **kwargs)
            if before is not None:
                after = await self.raw.find_one({"_id": before["_id"]})
                if after is not None:
                    await self.database.store.upsert_docs(self.name, [after])
            elif kwargs.get("upsert"):
                await self._persist_matches(query)
            return result

    async def find_one_and_update(self, query, update, *args, **kwargs):
        async with self._write_lock:
            await self._ensure_loaded()
            before = await self.raw.find_one(query, {"_id": 1})
            result = await self.raw.find_one_and_update(query, update, *args, **kwargs)
            if before is not None:
                after = await self.raw.find_one({"_id": before["_id"]})
                if after is not None:
                    await self.database.store.upsert_docs(self.name, [after])
            elif kwargs.get("upsert"):
                await self._persist_matches(query)
            return result

    async def find_one_and_delete(self, query, *args, **kwargs):
        async with self._write_lock:
            await self._ensure_loaded()
            before = await self.raw.find_one(query)
            result = await self.raw.find_one_and_delete(query, *args, **kwargs)
            if before is not None:
                await self.database.store.delete_docs(self.name, [_doc_id(before)])
            return result

    async def delete_one(self, query, *args, **kwargs):
        async with self._write_lock:
            await self._ensure_loaded()
            before = await self.raw.find_one(query)
            result = await self.raw.delete_one(query, *args, **kwargs)
            if before is not None:
                await self.database.store.delete_docs(self.name, [_doc_id(before)])
            return result

    async def delete_many(self, query, *args, **kwargs):
        async with self._write_lock:
            await self._ensure_loaded()
            before = await self.raw.find(query, {"_id": 1}).to_list(None)
            result = await self.raw.delete_many(query, *args, **kwargs)
            await self.database.store.delete_docs(self.name, [d["_id"] for d in before])
            return result

    async def bulk_write(self, requests, *args, **kwargs):
        async with self._write_lock:
            await self._ensure_loaded()
            result = await self.raw.bulk_write(requests, *args, **kwargs)
            await self._replace_remote_from_memory()
            return result

    async def _replace_remote_from_memory(self):
        docs = await self.raw.find({}).to_list(None)
        await self.database.store.delete_collection(self.name)
        await self.database.store.upsert_docs(self.name, docs)

    async def drop(self):
        async with self._write_lock:
            await self._ensure_loaded()
            await self.raw.drop()
            await self.database.store.delete_collection(self.name)

    async def rename(self, new_name: str, dropTarget: bool = False, **kwargs):
        async with self._write_lock:
            await self._ensure_loaded()
            await self.database.store.rename_collection(self.name, new_name, dropTarget)
            result = await self.raw.rename(new_name, dropTarget=dropTarget, **kwargs)
            self.database._collections.pop(self.name, None)
            self.name = new_name
            self.database._collections[new_name] = self
            return result


class PersistentDatabase:
    def __init__(self, store: SupabaseRpcStore, name: str):
        self.store = store
        self.name = name
        self.raw = AsyncMongoMockClient()[name]
        self._collections: dict[str, PersistentCollection] = {}

    def __getitem__(self, name: str) -> PersistentCollection:
        if name not in self._collections:
            self._collections[name] = PersistentCollection(self, name)
        return self._collections[name]

    def __getattr__(self, name: str) -> PersistentCollection:
        if name.startswith("_"):
            raise AttributeError(name)
        return self[name]

    async def list_collection_names(self, *args, **kwargs):
        return await self.store.list_collections()

    async def close(self):
        await self.store.close()


def build_supabase_database() -> PersistentDatabase:
    # Variabili prefissate LOTTI_: il progetto Supabase di Lotti e' distinto da
    # quello di GestionaleCloud (che usa SUPABASE_URL per conto proprio).
    missing = [
        key for key in ("LOTTI_SUPABASE_URL", "LOTTI_SUPABASE_ANON_KEY", "LOTTI_DB_SECRET")
        if not os.environ.get(key)
    ]
    if missing:
        raise RuntimeError("Configurazione Supabase Lotti incompleta: " + ", ".join(missing))
    store = SupabaseRpcStore(
        os.environ["LOTTI_SUPABASE_URL"],
        os.environ["LOTTI_SUPABASE_ANON_KEY"],
        os.environ["LOTTI_DB_SECRET"],
    )
    return PersistentDatabase(store, os.environ.get("LOTTI_DB_NAME", "Gestionale"))
