"""Archivio dei contenuti binari del modulo HR (PDF in base64).

Il runtime documentale del gestionale tiene TUTTI i documenti in memoria e
li scrive su ``gestionale.documents``. I PDF di cedolini, bonifici e
documenti dei dipendenti pesano centinaia di MB: non possono stare nella
cache del processo (Render Starter, 512 MiB). Qui vivono in una tabella
separata ``gestionale.blobs`` letta solo su richiesta, tramite le stesse RPC
protette dalla chiave runtime.

Una chiave blob e' ``<collezione>/<_id>/<campo>`` ed e' salvata nel documento
sotto ``_blobs`` (vedi ``db_adapter``): cosi' il documento resta piccolo e il
contenuto si recupera anche quando la proiezione toglie ``_id``.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

Rpc = Callable[[str, Dict[str, Any]], Awaitable[Any]]


def blob_key(collection: str, doc_id: Any, field: str) -> str:
    return f"{collection}/{doc_id}/{field}"


class BlobStore:
    """Interfaccia minima: put/get/delete/stats."""

    persistent: bool = False

    async def put(self, key: str, data: str) -> None:
        raise NotImplementedError

    async def get(self, key: str) -> Optional[str]:
        raise NotImplementedError

    async def delete(self, keys: Iterable[str]) -> int:
        raise NotImplementedError

    async def stats(self, prefix: str) -> Dict[str, int]:
        raise NotImplementedError


class SupabaseBlobStore(BlobStore):
    """Persistenza su ``gestionale.blobs`` via RPC ``gc_*_blob``."""

    persistent = True

    def __init__(self, rpc: Rpc):
        self._rpc = rpc

    async def put(self, key: str, data: str) -> None:
        await self._rpc("gc_put_blob", {"p_key": key, "p_data": data})

    async def get(self, key: str) -> Optional[str]:
        result = await self._rpc("gc_get_blob", {"p_key": key})
        if result is None or result == "":
            return None
        return str(result)

    async def delete(self, keys: Iterable[str]) -> int:
        clean = [k for k in keys if k]
        if not clean:
            return 0
        result = await self._rpc("gc_delete_blobs", {"p_keys": clean})
        return int(result or 0)

    async def stats(self, prefix: str) -> Dict[str, int]:
        result = await self._rpc("gc_blob_stats", {"p_prefix": prefix}) or {}
        return {"count": int(result.get("count", 0)), "bytes": int(result.get("bytes", 0))}


class MemoryBlobStore(BlobStore):
    """Solo per test e sviluppo locale senza Supabase: niente persistenza."""

    persistent = False

    def __init__(self):
        self._data: Dict[str, str] = {}

    async def put(self, key: str, data: str) -> None:
        self._data[key] = data

    async def get(self, key: str) -> Optional[str]:
        return self._data.get(key)

    async def delete(self, keys: Iterable[str]) -> int:
        removed = 0
        for key in keys:
            if self._data.pop(key, None) is not None:
                removed += 1
        return removed

    async def stats(self, prefix: str) -> Dict[str, int]:
        keys: List[str] = [k for k in self._data if k.startswith(prefix)]
        return {"count": len(keys), "bytes": sum(len(self._data[k]) for k in keys)}


def blob_store_per_runtime(runtime: Any) -> BlobStore:
    """Sceglie l'archivio in base al runtime documentale attivo.

    Con ``DATA_BACKEND=supabase`` il runtime espone ``_rpc``: i blob vanno su
    ``gestionale.blobs``. Con il runtime Sheets (o nei test) resta la memoria,
    e lo si dice chiaramente nel log: i file caricati non sopravviverebbero a
    un riavvio.
    """
    rpc = getattr(runtime, "_rpc", None)
    if callable(rpc):
        return SupabaseBlobStore(rpc)
    logger.warning(
        "Modulo HR: archivio binari IN MEMORIA (runtime senza Supabase). "
        "PDF e documenti caricati non sono persistenti: impostare DATA_BACKEND=supabase."
    )
    return MemoryBlobStore()
